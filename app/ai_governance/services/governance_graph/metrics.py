"""Dependency-free mismatch metric.

P2 used prometheus_client; core does not depend on it, so this logs structured
mismatch/validated counts. Swap for a real backend later without touching call
sites.
"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger("governance_graph.mismatch_metrics")


class MismatchMetrics:
    @staticmethod
    def record(org_id: uuid.UUID, validation_status: str) -> None:
        logger.info(
            "governance_graph.derivation_validation",
            extra={"organization_id": str(org_id), "validation_status": validation_status},
        )
