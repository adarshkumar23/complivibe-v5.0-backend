from __future__ import annotations

"""Export Control Compliance screening service (T4-8).

Grounded methodology
--------------------
- ECCN (Export Control Classification Number): a 5-character alphanumeric
  code (e.g. "4A001") under the US Commerce Control List (CCL), administered
  by BIS. Items not on the CCL default to EAR99 (no specific ECCN, generally
  low control but not license-free in all cases).
- Denied/restricted-party lists: BIS Denied Persons List, BIS Entity List,
  BIS Unverified List, OFAC SDN List, State Dept AECA Debarred List.
- Free public consolidated dataset: trade.gov's Consolidated Screening List
  (CSL), https://www.trade.gov/consolidated-screening-list -- merges 10+ of
  these lists (BIS Denied Persons/Entity/Unverified Lists, OFAC SDN, and
  State Dept AECA Debarred List) into one free, public dataset. The CSL is
  also mirrored via `api.trade.gov` and is one of the source datasets
  aggregated by OpenSanctions' "default" collection (OpenSanctions source id
  `us_trade_csl`).
- License determination logic: `license_required` is a function of (1) the
  ECCN's Reason(s) for Control, (2) destination country cross-referenced
  against the Commerce Country Chart (EAR Supp. 1 to Part 738), OR (3) a
  positive denied-party screening match.

IMPORTANT: this is an INITIAL SCREENING SIGNAL requiring human/legal
confirmation of any export -- it is NOT a final legal determination and does
not claim regulatory completeness.

Denied-party dataset reuse rationale
-------------------------------------
The TPRM sanctions satellite (`app/satellites/tprm_intelligence/
sanctions_screening.py`) already ingests and fuzzy-matches against a generic
denied/sanctioned-party entity table (`app.models.sanctions_entity
.SanctionsEntity`), populated from the OpenSanctions "default" collection FTM
dump via `SanctionsScreeningService.refresh_from_file` /
`download_dataset`. That collection aggregates the BIS Denied Persons List,
BIS Entity List, BIS Unverified List, OFAC SDN List, and the State
Department AECA Debarred List -- i.e. it already covers the trade.gov CSL's
constituent lists. Rather than re-implementing a second denied-party entity
table plus a second fuzzy name-matching algorithm, this service:
  * reuses `SanctionsEntity` directly as the denied-party dataset, and
  * reuses the exact same name-normalization/scoring helpers
    (`_normalize_name`, `_meaningful_tokens`, `_score_names`) and dataset
    ingestion methods (`refresh_from_file`, `download_dataset`) from
    `SanctionsScreeningService`, so tests can seed a fixture the same way
    the sanctions satellite does (a small local JSON-lines FTM file), with
    zero live network calls required.
This follows the phase's "call existing services, don't duplicate logic"
principle. If a future iteration needs export-control-specific lists that
are NOT part of OpenSanctions' aggregation (e.g. a live, dedicated
`api.trade.gov` CSL pull), `download_dataset()` below documents exactly how
that would be wired in without disturbing this reuse.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.export_control_check import ExportControlCheck
from app.models.organization import Organization
from app.models.sanctions_entity import SanctionsEntity
from app.models.vendor import Vendor
from app.satellites.tprm_intelligence.sanctions_screening import (
    SanctionsScreeningService,
    _meaningful_tokens,
    _score_names,
)

# trade.gov Consolidated Screening List API (for a live, dedicated refresh):
#   GET https://api.trade.gov/consolidated_screening_list/search
#       ?api_key=<key>&name=<query>
# Returns JSON `{"results": [{"name": ..., "source": ..., "type": ..., ...}]}`
# covering the same constituent lists as the OpenSanctions collection reused
# below. `download_dataset()` documents this without requiring network
# access for tests.
TRADE_GOV_CSL_SEARCH_URL = "https://api.trade.gov/consolidated_screening_list/search"

ECCN_PATTERN = re.compile(r"^[0-9][A-Z][0-9]{3}$")

# Illustrative, NON-EXHAUSTIVE example of an EAR Country Group E:1-style
# "embargoed/most-restricted destination" list (modeled loosely on EAR Part
# 740 Supp. 1 country groupings). The real Commerce Country Chart
# cross-references dozens of "Reasons for Control" columns against ~180
# destinations. This set exists to demonstrate the license-determination
# *pattern* end-to-end and MUST be replaced with the live Commerce Country
# Chart (or a licensed compliance feed) before any production use.
RESTRICTED_DESTINATIONS: frozenset[str] = frozenset(
    {"cuba", "iran", "north korea", "syria", "russia", "belarus"}
)

# ECCN "Reason for Control" prefixes (illustrative only) that commonly carry
# license requirements to most destinations outside close US allies per the
# Commerce Country Chart (e.g. 9x5xx = "encryption"/munitions-adjacent items,
# 3A/5A = electronics/telecom items with NS or SI control reasons).
#
# Category 5 covers Telecommunications (Part 1) AND Information Security (Part
# 2, i.e. encryption). Both parts share the same five product-group letters
# (A=Systems/Equipment/Components, B=Test/Inspection/Production Equipment,
# C=Materials, D=Software, E=Technology) under the standard CCL scheme, so an
# ECCN like 5D002 (encryption software) or 5E002 (encryption technology) is
# just as license-relevant as 5A002 (encryption hardware/systems) -- omitting
# 5B/5D/5E here silently waved through export-controlled encryption software
# and technology (and 5B test/inspection equipment) while still flagging the
# equivalent hardware. Per BIS Category 5 Part 2 (Information Security):
# 5A002/5A004 (equipment), 5B002 (test/inspection equipment), 5D002 (software
# for 5A002-type items), and 5E002 (technology) are all license-required to
# virtually all destinations outside Canada under License Exception ENC
# eligibility analysis (15 CFR 742.15 / Supp. No. 1 to Part 774, Category 5
# Part 2).
LICENSE_REQUIRING_ECCN_PREFIXES: frozenset[str] = frozenset(
    {"9A", "9B", "9C", "9D", "9E", "3A", "5A", "5B", "5D", "5E"}
)

DENIED_PARTY_MATCH_THRESHOLD = 0.85


class ExportControlScreeningService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Screening
    # ------------------------------------------------------------------
    def screen(
        self,
        organization: Organization,
        vendor: Vendor,
        *,
        item_description: str,
        destination_country: str,
        eccn: str | None = None,
        hs_code: str | None = None,
        computed_by_user_id=None,
    ) -> ExportControlCheck:
        item_description = (item_description or "").strip()
        destination_country = (destination_country or "").strip()
        if not item_description:
            raise ValueError("item_description is required")
        if not destination_country:
            raise ValueError("destination_country is required")

        normalized_eccn: str | None = None
        if eccn is not None and eccn.strip():
            normalized_eccn = eccn.strip().upper()
            if not ECCN_PATTERN.match(normalized_eccn):
                raise ValueError(
                    "eccn must match the pattern <digit><letter><3 digits>, e.g. '4A001' "
                    "(omit for EAR99/unclassified items)"
                )

        denied_party_result = self._screen_denied_party(vendor.name, item_description)

        license_required = False
        basis_parts: list[str] = []

        destination_norm = destination_country.lower()
        if destination_norm in RESTRICTED_DESTINATIONS:
            license_required = True
            basis_parts.append(
                f"Destination '{destination_country}' is in the illustrative EAR Country Group "
                "E:1-style embargoed-destination list; a license is required per the Commerce "
                "Country Chart (EAR Part 740 Supp. 1)."
            )
        if normalized_eccn and normalized_eccn[:2] in LICENSE_REQUIRING_ECCN_PREFIXES:
            license_required = True
            basis_parts.append(
                f"ECCN '{normalized_eccn}' falls under a Reason-for-Control category "
                f"('{normalized_eccn[:2]}') that commonly requires a license to destinations "
                "outside close US allies per the Commerce Country Chart."
            )
        if denied_party_result["match_found"]:
            license_required = True
            top_match = denied_party_result["matches"][0] if denied_party_result["matches"] else {}
            basis_parts.append(
                f"Positive denied-party screening match found ({top_match.get('caption', 'unknown')!r}, "
                f"score={top_match.get('score')}); a license is required pending legal review."
            )

        if not basis_parts:
            basis_parts.append(
                "EAR99/unclassified item (no controlling ECCN Reason-for-Control flag), "
                "destination not in the restricted-destination list, and no denied-party match -- "
                "no license appears to be required. This is a preliminary screening signal only "
                "and requires human/legal confirmation, not a final legal determination."
            )

        # Auto-derive an initial workflow status from the screening outcome
        # (staff can still move it through the 'screened'/'license_pending'/
        # 'cleared'/'blocked' lifecycle manually afterward): a positive
        # denied-party match is the most severe outcome and blocks the
        # transaction pending review; a license-required-but-no-match result
        # is routed to license_pending; a clean screen is cleared outright.
        if denied_party_result["match_found"]:
            status_value = "blocked"
        elif license_required:
            status_value = "license_pending"
        else:
            status_value = "cleared"

        row = ExportControlCheck(
            organization_id=organization.id,
            vendor_id=vendor.id,
            item_description=item_description,
            eccn=normalized_eccn,
            hs_code=hs_code,
            destination_country=destination_country,
            denied_party_screening_result_json=denied_party_result,
            license_required=license_required,
            license_determination_basis=" ".join(basis_parts),
            status=status_value,
            # Set explicitly (rather than relying solely on the DB
            # server_default) so ordering by computed_at is
            # microsecond-precise even on backends (e.g. SQLite) whose
            # CURRENT_TIMESTAMP has only second-level resolution.
            computed_at=datetime.now(timezone.utc),
            computed_by_user_id=computed_by_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def build_check_context(self, row: ExportControlCheck) -> dict[str, Any]:
        """Flag staleness against the denied-party dataset and drift against
        the vendor's prior screening -- a screening result is only as good
        as the denied-party snapshot it was run against.
        """
        flags: list[str] = [
            "preliminary_screening_requires_legal_confirmation: this is an initial screening "
            "signal, not a final legal export-control determination"
        ]
        computed_at = row.computed_at
        if computed_at.tzinfo is None:
            computed_at = computed_at.replace(tzinfo=timezone.utc)

        latest_dataset_activity = self.db.execute(
            select(SanctionsEntity.last_seen).order_by(SanctionsEntity.last_seen.desc()).limit(1)
        ).scalar_one_or_none()
        dataset_stale = False
        if latest_dataset_activity is not None:
            if latest_dataset_activity.tzinfo is None:
                latest_dataset_activity = latest_dataset_activity.replace(tzinfo=timezone.utc)
            if latest_dataset_activity > computed_at:
                dataset_stale = True
                flags.append(
                    "denied_party_dataset_updated_since_screening: the denied-party dataset has "
                    "new/updated entries since this check was run -- re-screen before relying on "
                    "this result"
                )

        previous = self.db.execute(
            select(ExportControlCheck)
            .where(
                ExportControlCheck.organization_id == row.organization_id,
                ExportControlCheck.vendor_id == row.vendor_id,
                ExportControlCheck.id != row.id,
                ExportControlCheck.computed_at < row.computed_at,
            )
            .order_by(ExportControlCheck.computed_at.desc())
        ).scalars().first()
        if previous is not None and previous.status != row.status:
            flags.append(
                f"status_changed_from_previous_check: '{previous.status}' -> '{row.status}'"
            )

        if row.status == "blocked":
            flags.append(
                "blocked_pending_legal_review: a positive denied-party match was found -- do not "
                "proceed with this transaction without legal/export-control officer sign-off"
            )

        return {"denied_party_dataset_stale": dataset_stale, "context_flags": sorted(set(flags))}

    def latest_check(self, organization_id, vendor_id) -> ExportControlCheck | None:
        return self.db.execute(
            select(ExportControlCheck)
            .where(
                ExportControlCheck.organization_id == organization_id,
                ExportControlCheck.vendor_id == vendor_id,
            )
            .order_by(ExportControlCheck.computed_at.desc(), ExportControlCheck.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def list_checks(self, organization_id, vendor_id) -> list[ExportControlCheck]:
        return list(
            self.db.execute(
                select(ExportControlCheck)
                .where(
                    ExportControlCheck.organization_id == organization_id,
                    ExportControlCheck.vendor_id == vendor_id,
                )
                .order_by(ExportControlCheck.computed_at.desc(), ExportControlCheck.id.desc())
            ).scalars().all()
        )

    # ------------------------------------------------------------------
    # Denied-party dataset (reused from the sanctions satellite)
    # ------------------------------------------------------------------
    def refresh_from_file(self, path: str | Path, **kwargs: Any) -> dict[str, int]:
        """Load a denied-party dataset (OpenSanctions FTM JSON-lines format,
        which already aggregates the trade.gov CSL's constituent lists) from
        a local file. Delegates to `SanctionsScreeningService.refresh_from_file`
        since both satellites share the same `SanctionsEntity` cache table --
        avoiding a duplicate ingestion pipeline. Used for offline tests via a
        small fixture file (no network calls required).
        """
        return SanctionsScreeningService(self.db).refresh_from_file(path, **kwargs)

    def download_dataset(self, **kwargs: Any) -> Path:
        """Live dataset refresh stub/documentation.

        Production wiring would either:
          (a) delegate to `SanctionsScreeningService.download_dataset()` to
              refresh the shared OpenSanctions "default" collection (already
              covers BIS/OFAC/AECA lists), or
          (b) call the dedicated trade.gov Consolidated Screening List API
              directly, e.g.:
                GET https://api.trade.gov/consolidated_screening_list/search
                    ?api_key=<TRADE_GOV_API_KEY>&name=<entity name>
              returning `{"results": [{"name": ..., "source": ..., "type":
              ..., "programs": [...], ...}]}` JSON records that would be
              upserted into a denied-party cache table analogous to
              `SanctionsEntity`.
        This method delegates to (a) for consistency with the rest of this
        satellite; no network call is made in tests (only
        `refresh_from_file` is exercised there).
        """
        return SanctionsScreeningService(self.db).download_dataset(**kwargs)

    def _screen_denied_party(self, vendor_name: str, item_description: str) -> dict[str, Any]:
        query_name = vendor_name or item_description
        matches = self._local_search(query_name)
        match_found = bool(matches and matches[0]["score"] >= DENIED_PARTY_MATCH_THRESHOLD)
        return {
            "match_found": match_found,
            "matches": matches,
            "dataset_source": (
                "opensanctions_default (aggregates trade.gov Consolidated Screening List / "
                "BIS Denied Persons & Entity Lists / OFAC SDN / State Dept AECA Debarred List "
                "via OpenSanctions source id 'us_trade_csl')"
            ),
            "screened_at": datetime.now(timezone.utc).isoformat(),
        }

    def _local_search(self, name: str, *, limit: int = 5) -> list[dict[str, Any]]:
        tokens = _meaningful_tokens(name)
        if not tokens:
            return []
        clauses = [SanctionsEntity.caption.ilike(f"%{token}%") for token in tokens]
        candidates = self.db.execute(select(SanctionsEntity).where(or_(*clauses)).limit(500)).scalars().all()
        matches = [
            {
                "entity_id": entity.id,
                "caption": entity.caption,
                "schema": entity.schema_type,
                "score": _score_names(name, entity.caption),
                "datasets": entity.datasets,
            }
            for entity in candidates
        ]
        return sorted(matches, key=lambda item: item["score"], reverse=True)[:limit]
