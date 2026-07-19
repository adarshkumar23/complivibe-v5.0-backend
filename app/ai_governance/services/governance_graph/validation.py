"""Pure contract checks for the 'Satellites Compute, Core Decides' flow.

DB-free / FastAPI-free. Ported verbatim from P2
core-side-patch/validation.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def validate_obligation_control_ids(
    payload: Mapping[str, Sequence[str]], catalog: Mapping[str, set | Sequence]
) -> list[str]:
    """Return the ids in the payload's derived_obligations / derived_controls
    that are NOT present in the catalog's active obligation / control_type sets.

    An empty return means every submitted id references a live catalog entry.
    """
    obligation_catalog = set(catalog.get("obligation") or ())
    control_catalog = set(catalog.get("control_type") or ())
    bad: list[str] = []
    for oid in payload.get("derived_obligations") or ():
        if oid not in obligation_catalog:
            bad.append(oid)
    for cid in payload.get("derived_controls") or ():
        if cid not in control_catalog:
            bad.append(cid)
    return bad


def compare_derivation(submitted: Mapping[str, Sequence[str]], reference: Mapping[str, Sequence[str]]) -> bool:
    """True iff the submitted derivation matches core's independent re-derivation
    (set equality on both obligations and controls; order/duplicates ignored).
    """
    return (
        set(submitted.get("derived_obligations") or ()) == set(reference.get("derived_obligations") or ())
        and set(submitted.get("derived_controls") or ()) == set(reference.get("derived_controls") or ())
    )
