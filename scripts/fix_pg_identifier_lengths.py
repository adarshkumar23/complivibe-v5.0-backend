#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIOLATIONS = ROOT / "scripts" / "pg_identifier_violations.json"
RENAMES_MD = ROOT / "scripts" / "pg_identifier_renames.md"

TARGET_GLOBS = [
    "alembic/versions/*.py",
    "app/**/*.py",
]

ABBR = {
    "organization": "org",
    "organizations": "orgs",
    "governance": "gov",
    "assignment": "assign",
    "assignments": "assigns",
    "diagnostic": "diag",
    "recommendation": "rec",
    "recommendations": "recs",
    "classification": "class",
    "classifications": "classes",
    "dimension": "dim",
    "dimensions": "dims",
    "residual": "resid",
    "calculated": "calc",
    "autopilot": "ap",
    "execution": "exec",
    "approval": "appr",
    "approvals": "apprs",
    "versions": "vers",
    "version": "ver",
    "compare": "cmp",
    "preset": "pst",
    "policy": "pol",
    "profiles": "profs",
    "profile": "prof",
    "history": "hist",
    "report": "rpt",
    "reports": "rpts",
    "templates": "tpls",
    "template": "tpl",
    "snapshots": "snaps",
    "snapshot": "snap",
    "manifest": "mnfst",
    "verification": "verif",
    "acknowledgements": "acks",
    "dispositions": "disp",
    "constraint": "c",
}


def shorten(name: str) -> str:
    parts = name.split("_")
    out: list[str] = []
    for p in parts:
        out.append(ABBR.get(p, p))
    s = "_".join(out)
    s = re.sub(r"_+", "_", s).strip("_")
    h = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    if len(s.encode("utf-8")) > 53:
        # trim by bytes, preserve utf-8 integrity (ascii expected)
        s = s.encode("utf-8")[:53].decode("utf-8", "ignore").rstrip("_")
    candidate = f"{s}_{h}"
    if len(candidate.encode("utf-8")) > 62:
        base = candidate.encode("utf-8")[:62].decode("utf-8", "ignore")
        candidate = base.rstrip("_")
    return candidate


def main() -> None:
    data = json.loads(VIOLATIONS.read_text(encoding="utf-8"))
    violations = data.get("violations", [])
    names = sorted({v["name"] for v in violations})

    mapping: dict[str, str] = {}
    used: set[str] = set()
    for old in names:
        new = shorten(old)
        i = 1
        while new in used or new == old:
            h = hashlib.sha1(f"{old}:{i}".encode("utf-8")).hexdigest()[:8]
            base = new.split("_")[0]
            base = base.encode("utf-8")[:53].decode("utf-8", "ignore").rstrip("_")
            new = f"{base}_{h}"
            i += 1
        mapping[old] = new
        used.add(new)

    # Apply exact string literal replacements across repo targets.
    paths: list[Path] = []
    for g in TARGET_GLOBS:
        paths.extend(ROOT.glob(g))

    touched: dict[str, list[tuple[str, str]]] = {}
    for p in sorted(set(paths)):
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        orig = text
        file_changes: list[tuple[str, str]] = []
        for old, new in mapping.items():
            if old in text:
                text = text.replace(old, new)
                file_changes.append((old, new))
        if text != orig:
            p.write_text(text, encoding="utf-8")
            touched[str(p.relative_to(ROOT))] = file_changes

    lines = ["# PostgreSQL Identifier Renames", ""]
    for old in names:
        lines.append(f"- `{old}` -> `{mapping[old]}`")
    lines.append("")
    lines.append("## Files Updated")
    for f in sorted(touched):
        lines.append(f"- `{f}`")
    RENAMES_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Renamed {len(mapping)} identifiers.")
    print(f"Touched {len(touched)} files.")
    print(f"Wrote {RENAMES_MD}")


if __name__ == "__main__":
    main()
