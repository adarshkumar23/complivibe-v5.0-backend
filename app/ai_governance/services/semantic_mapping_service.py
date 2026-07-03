from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models.cross_framework_obligation_mapping import CrossFrameworkObligationMapping
from app.models.framework import Framework
from app.models.obligation import Obligation


@dataclass
class SemanticSearchStatus:
    pgvector_available: bool
    embedding_model: str | None
    total_embedded: int
    total_obligations: int

    @property
    def coverage_pct(self) -> float:
        if self.total_obligations <= 0:
            return 0.0
        return round((self.total_embedded / self.total_obligations) * 100.0, 2)


class SemanticMappingService:
    def __init__(self) -> None:
        self.pgvector_available = self._check_pgvector()
        self.model = None

    def _check_pgvector(self) -> bool:
        try:
            engine = get_engine()
            if engine.dialect.name != "postgresql":
                return False
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
                return result.fetchone() is not None
        except Exception:
            return False

    def _get_embedding_model(self):
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self.model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception:
                self.model = None
        return self.model

    def embed_text(self, text_value: str) -> list[float] | None:
        model = self._get_embedding_model()
        if model is None:
            return None
        try:
            vector = model.encode(text_value)
            return vector.tolist()
        except Exception:
            return None

    def find_similar_obligations(
        self,
        obligation_id: uuid.UUID,
        db: Session,
        top_k: int = 10,
        min_score: float = 0.70,
        exclude_same_framework: bool = True,
    ) -> list[dict[str, object]]:
        source = db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
        if source is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")

        if self.pgvector_available and self._has_embedding_column(db):
            source_embedding_text = self._get_source_embedding_text(db, obligation_id)
            if source_embedding_text:
                return self._pgvector_search(
                    source=source,
                    db=db,
                    source_embedding_text=source_embedding_text,
                    top_k=top_k,
                    min_score=min_score,
                    exclude_same_framework=exclude_same_framework,
                )

        return self._fallback_search(
            source=source,
            db=db,
            top_k=top_k,
            min_score=min_score,
            exclude_same_framework=exclude_same_framework,
        )

    def _has_embedding_column(self, db: Session) -> bool:
        bind = db.get_bind()
        if bind is None:
            return False
        try:
            columns = [col["name"] for col in bind.dialect.get_columns(bind.connect(), "obligations")]
            return "embedding" in columns
        except Exception:
            return False

    def _get_source_embedding_text(self, db: Session, obligation_id: uuid.UUID) -> str | None:
        try:
            row = db.execute(
                text("SELECT embedding::text AS embedding_text FROM obligations WHERE id = :id"),
                {"id": str(obligation_id)},
            ).first()
            if row is None:
                return None
            return str(row.embedding_text) if row.embedding_text is not None else None
        except Exception:
            return None

    def _pgvector_search(
        self,
        source: Obligation,
        db: Session,
        source_embedding_text: str,
        top_k: int,
        min_score: float,
        exclude_same_framework: bool,
    ) -> list[dict[str, object]]:
        query_parts = [
            "SELECT o.id, o.reference_code, o.title, f.name AS framework_name,",
            "  1 - (o.embedding <=> CAST(:embedding AS vector)) AS similarity_score",
            "FROM obligations o",
            "JOIN frameworks f ON f.id = o.framework_id",
            "WHERE o.id != :source_id",
            "  AND o.embedding IS NOT NULL",
        ]
        if exclude_same_framework:
            query_parts.append("  AND o.framework_id != :framework_id")
        query_parts.extend(
            [
                "  AND 1 - (o.embedding <=> CAST(:embedding AS vector)) >= :min_score",
                "ORDER BY o.embedding <=> CAST(:embedding AS vector)",
                "LIMIT :top_k",
            ]
        )

        rows = db.execute(
            text("\n".join(query_parts)),
            {
                "embedding": source_embedding_text,
                "source_id": str(source.id),
                "framework_id": str(source.framework_id),
                "min_score": min_score,
                "top_k": top_k,
            },
        ).fetchall()

        return [
            {
                "obligation_id": str(row.id),
                "obligation_ref": row.reference_code,
                "obligation_title": row.title,
                "framework_name": row.framework_name,
                "similarity_score": round(float(row.similarity_score), 4),
                "mapping_type": "semantic",
            }
            for row in rows
            if row.similarity_score is not None
        ]

    def _fallback_search(
        self,
        source: Obligation,
        db: Session,
        top_k: int,
        min_score: float,
        exclude_same_framework: bool,
    ) -> list[dict[str, object]]:
        def normalize(text_value: str) -> set[str]:
            words = re.findall(r"\b\w+\b", (text_value or "").lower())
            stopwords = {
                "the",
                "a",
                "an",
                "and",
                "or",
                "of",
                "to",
                "in",
                "for",
                "with",
                "is",
                "are",
                "shall",
                "must",
                "should",
                "that",
                "this",
                "be",
                "by",
                "on",
                "at",
                "from",
                "all",
                "not",
                "have",
                "has",
                "its",
            }
            return {word for word in words if word not in stopwords and len(word) > 3}

        source_words = normalize(f"{source.reference_code} {source.title} {source.description or ''}")
        if not source_words:
            return []

        stmt = select(Obligation, Framework.name).join(Framework, Framework.id == Obligation.framework_id).where(Obligation.id != source.id)
        if exclude_same_framework:
            stmt = stmt.where(Obligation.framework_id != source.framework_id)

        rows = db.execute(stmt).all()
        results: list[dict[str, object]] = []
        for obligation, framework_name in rows:
            words = normalize(f"{obligation.reference_code} {obligation.title} {obligation.description or ''}")
            if not words:
                continue
            intersection = source_words & words
            union = source_words | words
            if not union:
                continue
            jaccard = len(intersection) / len(union)
            if jaccard < min_score:
                continue
            results.append(
                {
                    "obligation_id": str(obligation.id),
                    "obligation_ref": obligation.reference_code,
                    "obligation_title": obligation.title,
                    "framework_name": framework_name,
                    "similarity_score": round(float(jaccard), 4),
                    "mapping_type": "fallback_text",
                }
            )

        results.sort(key=lambda item: float(item["similarity_score"]), reverse=True)
        return results[:top_k]

    def auto_discover_mappings(
        self,
        source_framework_id: uuid.UUID,
        target_framework_id: uuid.UUID,
        db: Session,
        min_score: float = 0.75,
        mapping_type_label: str = "semantic",
    ) -> dict[str, object]:
        source_obligations = db.execute(select(Obligation).where(Obligation.framework_id == source_framework_id)).scalars().all()

        created = 0
        skipped = 0
        for source in source_obligations:
            matches = self.find_similar_obligations(
                obligation_id=source.id,
                db=db,
                top_k=3,
                min_score=min_score,
                exclude_same_framework=True,
            )
            for match in matches:
                target_id = uuid.UUID(str(match["obligation_id"]))
                target = db.execute(select(Obligation).where(Obligation.id == target_id)).scalar_one_or_none()
                if target is None or target.framework_id != target_framework_id:
                    continue

                existing = db.execute(
                    select(CrossFrameworkObligationMapping).where(
                        CrossFrameworkObligationMapping.source_obligation_id == source.id,
                        CrossFrameworkObligationMapping.target_obligation_id == target_id,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    skipped += 1
                    continue

                row = CrossFrameworkObligationMapping(
                    source_obligation_id=source.id,
                    target_obligation_id=target_id,
                    mapping_type="related",
                    semantic_similarity_score=float(match["similarity_score"]),
                    mapping_method=mapping_type_label,
                    notes=f"Auto-discovered via semantic similarity ({match['similarity_score']})",
                )
                db.add(row)
                created += 1

        db.flush()
        return {
            "source_framework": str(source_framework_id),
            "target_framework": str(target_framework_id),
            "mappings_created": created,
            "mappings_skipped": skipped,
            "min_score": min_score,
        }

    def batch_embed_framework(self, framework_id: uuid.UUID, db: Session) -> dict[str, object]:
        if not self.pgvector_available:
            return {"embedded": 0, "skipped": 0, "reason": "pgvector not available"}

        model = self._get_embedding_model()
        if model is None:
            return {"embedded": 0, "skipped": 0, "reason": "sentence-transformers not installed"}

        if not self._has_embedding_column(db):
            return {"embedded": 0, "skipped": 0, "reason": "embedding column not available"}

        obligations = db.execute(select(Obligation).where(Obligation.framework_id == framework_id)).scalars().all()
        embedded = 0
        skipped = 0

        for obligation in obligations:
            source_text = f"{obligation.reference_code}: {obligation.title}. {obligation.description or ''}"
            vector = self.embed_text(source_text)
            if vector is None:
                skipped += 1
                continue

            vector_sql = "[" + ",".join(f"{item:.8f}" for item in vector) + "]"
            db.execute(
                text("UPDATE obligations SET embedding = CAST(:embedding AS vector) WHERE id = :id"),
                {"embedding": vector_sql, "id": str(obligation.id)},
            )
            embedded += 1

        db.flush()
        return {"embedded": embedded, "skipped": skipped, "framework_id": str(framework_id)}

    def status(self, db: Session) -> SemanticSearchStatus:
        total_obligations = int(db.execute(select(func.count(Obligation.id))).scalar_one())

        total_embedded = 0
        if self.pgvector_available and self._has_embedding_column(db):
            try:
                total_embedded = int(
                    db.execute(text("SELECT COUNT(*) FROM obligations WHERE embedding IS NOT NULL")).scalar_one()
                )
            except Exception:
                total_embedded = 0

        return SemanticSearchStatus(
            pgvector_available=self.pgvector_available,
            embedding_model="all-MiniLM-L6-v2" if self._get_embedding_model() is not None else None,
            total_embedded=total_embedded,
            total_obligations=total_obligations,
        )
