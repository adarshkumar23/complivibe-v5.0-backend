"""P2 governance knowledge-graph feature.

Ported from the standalone P2 satellite's core-side-patch/, reconciled to core:
UUID-native tables/ids (was BigInteger/String), real AuditService/require_permission,
real request-scoped Session, a scoped-key registry for the satellite endpoints,
per-hop org-scoped traversal, and an atomic ON CONFLICT upsert for the
"Core Decides" write target.
"""
