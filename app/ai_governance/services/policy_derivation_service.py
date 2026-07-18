"""Service layer for the agentic policy-derivation feature (patent P3).

Reconciles the standalone repo's `create_app` factory logic onto core:
  * request-scoped SQLAlchemy Session instead of a per-app SQLite engine;
  * real org-scoped AI-system lookup (raise 404 never 403, mirroring
    AISystemService.get_system) instead of the in-memory registry stand-in;
  * durable receipt persistence (ai_guardrail_receipts) with a DB row-lock to
    make the per-(org, ai_system) hash chain concurrency-safe, instead of the
    in-process dict + per-request threading.Lock;
  * core's AuditService for every state-changing action.

The novel derivation logic itself lives untouched in
`app.ai_governance.services.policy_derivation.derivation_engine`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_system_service import AISystemService
from app.ai_governance.services.policy_derivation.derivation_engine import (
    derive_and_compile,
    rego_package_slug,
)
from app.ai_governance.services.policy_derivation.opa_client import OpaClient
from app.ai_governance.services.policy_derivation.policy_provider import CompliVibePolicyProvider
from app.ai_governance.services.policy_derivation.provenance import (
    serialize_constraint_spec,
    source_obligation_ids_from_spec,
)
from app.ai_governance.services.policy_derivation.receipt_chain import verify_chain
from app.ai_governance.services.policy_derivation.receipt_crypto import Receipt, ReceiptSigner
from app.core.config import get_settings
from app.models.ai_derived_guardrail import AiDerivedGuardrail
from app.models.ai_guardrail_check_event import AiGuardrailCheckEvent
from app.models.ai_guardrail_receipt import AiGuardrailReceipt
from app.services.audit_service import AuditService


def _default_policy_provider_factory(
    rego_package: str,
    rego_policy: str,
    *,
    sign_receipt_fn,
    previous_receipt_hash: str | None,
) -> CompliVibePolicyProvider | None:
    """Build a provider pointed at the configured OPA server, or None if OPA is
    not configured (the caller then fails closed with a clear reason).

    `rego_policy` is accepted for parity with test/bridge factories (which need
    the policy text to run a local `opa eval`); a real OPA deployment already
    holds the policy, so this factory ignores it.
    """
    settings = get_settings()
    if not settings.OPA_SERVER_URL:
        return None
    opa_client = OpaClient(
        base_url=settings.OPA_SERVER_URL,
        timeout_seconds=settings.OPA_REQUEST_TIMEOUT_SECONDS,
    )
    return CompliVibePolicyProvider(
        opa_client,
        rego_package,
        sign_receipt_fn=sign_receipt_fn,
        previous_receipt_hash=previous_receipt_hash,
    )


class PolicyDerivationService:
    def __init__(self, db: Session, *, policy_provider_factory=None) -> None:
        self.db = db
        self.ai_system_service = AISystemService(db)
        # Resolved at call-time (falls back to the module default) so tests can
        # monkeypatch the module-level factory without threading it through the
        # router.
        self._policy_provider_factory = policy_provider_factory

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)

    def _opa_binary_path(self) -> str:
        return get_settings().OPA_BINARY_PATH

    def _require_org_system(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> None:
        # Raises 404 (never 403) for missing or cross-org, per core convention.
        self.ai_system_service.get_system(org_id, ai_system_id)

    def _derive(self, obligations, org_id: uuid.UUID):
        try:
            return derive_and_compile(
                obligations, org_id=str(org_id), opa_path=self._opa_binary_path()
            )
        except RuntimeError as exc:
            # No `opa` binary available to compile-check the Rego.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"policy engine (opa) unavailable for guardrail compilation: {exc}",
            ) from exc
        except ValueError as exc:
            # derive_and_compile validates its own Rego; a ValueError means the
            # engine produced syntactically invalid Rego, which must never be
            # persisted.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

    def create_guardrail(
        self,
        org_id: uuid.UUID,
        ai_system_id: uuid.UUID,
        name: str,
        description: str | None,
        obligations,
        actor_user_id: uuid.UUID,
    ) -> AiDerivedGuardrail:
        self._require_org_system(org_id, ai_system_id)
        spec, rego_text = self._derive(obligations, org_id)

        rego_package = f"complivibe.guardrails.org_{rego_package_slug(str(org_id))}"
        row = AiDerivedGuardrail(
            organization_id=org_id,
            ai_system_id=ai_system_id,
            name=name,
            description=description,
            rego_policy=rego_text,
            rego_package=rego_package,
            source_obligation_ids=source_obligation_ids_from_spec(spec),
            constraint_spec_json=serialize_constraint_spec(spec),
            compiled_at=self._utcnow(),
            is_active=True,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ai_derived_guardrail.created",
            entity_type="ai_derived_guardrail",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={
                "name": row.name,
                "ai_system_id": str(ai_system_id),
                "rego_package": row.rego_package,
                "source_obligation_ids": list(row.source_obligation_ids),
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_guardrail(self, org_id: uuid.UUID, guardrail_id: uuid.UUID) -> AiDerivedGuardrail:
        row = self.db.execute(
            select(AiDerivedGuardrail).where(
                AiDerivedGuardrail.organization_id == org_id,
                AiDerivedGuardrail.id == guardrail_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Derived guardrail not found")
        return row

    def recompile_guardrail(
        self,
        org_id: uuid.UUID,
        guardrail_id: uuid.UUID,
        obligations,
        actor_user_id: uuid.UUID,
    ) -> AiDerivedGuardrail:
        row = self.get_guardrail(org_id, guardrail_id)

        submitted_ids = {o.id for o in obligations}
        existing_ids = set(row.source_obligation_ids)
        if submitted_ids != existing_ids:
            # Recompile from the same obligation set, not silently redefine it.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "submitted obligation ids do not match this guardrail's existing "
                    f"source_obligation_ids; expected {sorted(existing_ids)!r}, got "
                    f"{sorted(submitted_ids)!r}"
                ),
            )

        before = {"rego_package": row.rego_package, "source_obligation_ids": list(row.source_obligation_ids)}
        records = [o.to_record() for o in obligations]
        spec, rego_text = self._derive(records, org_id)

        row.rego_policy = rego_text
        row.constraint_spec_json = serialize_constraint_spec(spec)
        row.source_obligation_ids = source_obligation_ids_from_spec(spec)
        row.compiled_at = self._utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ai_derived_guardrail.recompiled",
            entity_type="ai_derived_guardrail",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={"rego_package": row.rego_package, "source_obligation_ids": list(row.source_obligation_ids)},
            metadata_json={"source": "api"},
        )
        return row

    def _active_guardrail_for_system(
        self, org_id: uuid.UUID, ai_system_id: uuid.UUID
    ) -> AiDerivedGuardrail:
        row = self.db.execute(
            select(AiDerivedGuardrail)
            .where(
                AiDerivedGuardrail.organization_id == org_id,
                AiDerivedGuardrail.ai_system_id == ai_system_id,
                AiDerivedGuardrail.is_active.is_(True),
            )
            .order_by(AiDerivedGuardrail.created_at.desc())
        ).scalars().first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="no active derived guardrail configured for this ai_system",
            )
        return row

    def _latest_receipt_locked(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> AiGuardrailReceipt | None:
        # Row-lock the tail of the chain so concurrent check-action calls for the
        # same (org, ai_system) serialize on the chain append rather than both
        # reading the same previous hash and forking the chain. SQLite ignores
        # FOR UPDATE (single-writer anyway); Postgres honors it.
        return self.db.execute(
            select(AiGuardrailReceipt)
            .where(
                AiGuardrailReceipt.organization_id == org_id,
                AiGuardrailReceipt.ai_system_id == ai_system_id,
            )
            .order_by(AiGuardrailReceipt.chain_position.desc())
            .limit(1)
            .with_for_update()
        ).scalars().first()

    def check_action(
        self,
        org_id: uuid.UUID,
        ai_system_id: uuid.UUID,
        raw_action: dict,
        actor_user_id: uuid.UUID,
        signing_key_hex: str | None = None,
    ) -> AiGuardrailCheckEvent:
        """Evaluate a raw agent action against the ai_system's active derived
        guardrail, persist a check event, and (if a signing key is supplied by
        the caller's runtime) sign + persist a chained receipt.

        Key-custody boundary (patent Claim 4): `signing_key_hex` is a transient,
        caller-supplied key used only in-memory for this one signing call and is
        NEVER persisted -- only the resulting signature and the *public* key are
        stored. Core holds no signing key of its own; if none is supplied the
        decision is still returned and stored, just without a receipt.
        """
        self._require_org_system(org_id, ai_system_id)
        guardrail = self._active_guardrail_for_system(org_id, ai_system_id)

        previous = self._latest_receipt_locked(org_id, ai_system_id)
        previous_hash = previous.receipt_hash if previous else None
        next_position = (previous.chain_position + 1) if previous else 0

        signer = ReceiptSigner(signing_key_hex) if signing_key_hex else None
        sign_fn = signer.sign_receipt if signer else None

        factory = self._policy_provider_factory or _default_policy_provider_factory
        provider = factory(
            guardrail.rego_package,
            guardrail.rego_policy,
            sign_receipt_fn=sign_fn,
            previous_receipt_hash=previous_hash,
        )

        timestamp = raw_action.get("timestamp") or self._utcnow().isoformat()

        try:
            if provider is None:
                # OPA not configured: fail closed (deny), never silently allow.
                from app.ai_governance.services.policy_derivation.envelope import build_envelope

                envelope = build_envelope(raw_action)
                decision_allowed = False
                reason = "policy engine (OPA) not configured; failing closed"
                receipt: Receipt | None = None
                envelope_dump = envelope.model_dump()
                latency_ms = 0.0
            else:
                result = provider.check_action(raw_action, timestamp=timestamp)
                decision_allowed = result.decision.allowed
                reason = result.decision.reason
                receipt = result.receipt
                envelope_dump = result.envelope.model_dump()
                latency_ms = result.decision.latency_ms
        except ValueError as exc:
            # Payload-shaped field present in the raw action (envelope guard).
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        finally:
            if provider is not None:
                provider.close()

        decision_label = "allow" if decision_allowed else "deny"

        event = AiGuardrailCheckEvent(
            organization_id=org_id,
            guardrail_id=guardrail.id,
            ai_system_id=ai_system_id,
            decision=decision_label,
            reason=reason,
            action_envelope_json=envelope_dump,
            receipt_id=receipt.receipt_id if receipt else None,
            evaluation_ms=latency_ms,
        )
        self.db.add(event)
        self.db.flush()

        if receipt is not None:
            self.db.add(
                AiGuardrailReceipt(
                    organization_id=org_id,
                    ai_system_id=ai_system_id,
                    guardrail_id=guardrail.id,
                    check_event_id=event.id,
                    chain_position=next_position,
                    receipt_id=receipt.receipt_id,
                    receipt_timestamp=receipt.timestamp,
                    envelope_hash=receipt.envelope_hash,
                    decision=receipt.decision,
                    reasons_json=list(receipt.reasons),
                    previous_receipt_hash=receipt.previous_receipt_hash,
                    signature=receipt.signature,
                    receipt_hash=receipt.receipt_hash,
                    public_key_hex=receipt.public_key_hex,
                )
            )
            self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ai_derived_guardrail.checked",
            entity_type="ai_guardrail_check_event",
            entity_id=event.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"decision": decision_label, "reason": reason},
            metadata_json={"source": "api"},
        )
        return event

    def _load_receipt_chain(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> list[Receipt]:
        rows = self.db.execute(
            select(AiGuardrailReceipt)
            .where(
                AiGuardrailReceipt.organization_id == org_id,
                AiGuardrailReceipt.ai_system_id == ai_system_id,
            )
            .order_by(AiGuardrailReceipt.chain_position.asc())
        ).scalars().all()
        return [
            Receipt(
                receipt_id=r.receipt_id,
                timestamp=r.receipt_timestamp,
                envelope_hash=r.envelope_hash,
                decision=r.decision,
                reasons=list(r.reasons_json or []),
                previous_receipt_hash=r.previous_receipt_hash,
                signature=r.signature,
                receipt_hash=r.receipt_hash,
                public_key_hex=r.public_key_hex,
            )
            for r in rows
        ]

    def get_receipt_chain(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> list[Receipt]:
        self._require_org_system(org_id, ai_system_id)
        return self._load_receipt_chain(org_id, ai_system_id)

    def verify_receipt_chain(self, org_id: uuid.UUID, ai_system_id: uuid.UUID):
        self._require_org_system(org_id, ai_system_id)
        return verify_chain(self._load_receipt_chain(org_id, ai_system_id))
