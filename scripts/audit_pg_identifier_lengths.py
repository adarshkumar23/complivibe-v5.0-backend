#!/usr/bin/env python3
from __future__ import annotations

import ast
import glob
import json
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS_GLOB = str(ROOT / "alembic" / "versions" / "*.py")
OUT_JSON = ROOT / "scripts" / "pg_identifier_violations.json"


@dataclass
class IdentifierRecord:
    migration_file: str
    identifier_type: str
    name: str
    length: int
    violation: bool
    lineno: int
    note: str = ""


def full_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = full_name(node.value)
        if base:
            return f"{base}.{node.attr}"
        return node.attr
    return None


def str_const(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def kwarg_str(call: ast.Call, key: str) -> str | None:
    for kw in call.keywords:
        if kw.arg == key:
            return str_const(kw.value)
    return None


def call_first_str(call: ast.Call) -> str | None:
    if call.args:
        return str_const(call.args[0])
    return None


def add_record(records: list[IdentifierRecord], migration_file: str, identifier_type: str, name: str, lineno: int, note: str = "") -> None:
    length = len(name.encode("utf-8"))
    records.append(
        IdentifierRecord(
            migration_file=migration_file,
            identifier_type=identifier_type,
            name=name,
            length=length,
            violation=length >= 63,
            lineno=lineno,
            note=note,
        )
    )


def scan_file(path: Path) -> list[IdentifierRecord]:
    records: list[IdentifierRecord] = []
    rel = str(path.relative_to(ROOT))
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fname = full_name(node.func) or ""

        # op.create_table('table_name', ...)
        if fname == "op.create_table":
            tname = call_first_str(node)
            if tname:
                add_record(records, rel, "table", tname, node.lineno)

        # op.create_index('idx_name', ...)
        elif fname == "op.create_index":
            iname = call_first_str(node)
            if iname:
                add_record(records, rel, "index", iname, node.lineno)

        # op.create_foreign_key('name', ...)
        elif fname == "op.create_foreign_key":
            cname = call_first_str(node)
            if cname:
                add_record(records, rel, "constraint_fk", cname, node.lineno)

        # op.create_unique_constraint('name', ...)
        elif fname == "op.create_unique_constraint":
            cname = call_first_str(node)
            if cname:
                add_record(records, rel, "constraint_unique", cname, node.lineno)

        # op.create_check_constraint('name', ...)
        elif fname == "op.create_check_constraint":
            cname = call_first_str(node)
            if cname:
                add_record(records, rel, "constraint_check", cname, node.lineno)

        # sa.Index('name', ...)
        elif fname in {"sa.Index", "Index"}:
            iname = call_first_str(node)
            if iname:
                add_record(records, rel, "index", iname, node.lineno)

        # constraints with explicit names
        elif fname in {"sa.ForeignKeyConstraint", "ForeignKeyConstraint"}:
            cname = kwarg_str(node, "name")
            if cname:
                add_record(records, rel, "constraint_fk", cname, node.lineno)

        elif fname in {"sa.UniqueConstraint", "UniqueConstraint"}:
            cname = kwarg_str(node, "name")
            if cname:
                add_record(records, rel, "constraint_unique", cname, node.lineno)

        elif fname in {"sa.CheckConstraint", "CheckConstraint"}:
            cname = kwarg_str(node, "name")
            if cname:
                add_record(records, rel, "constraint_check", cname, node.lineno)

        elif fname in {"sa.PrimaryKeyConstraint", "PrimaryKeyConstraint"}:
            cname = kwarg_str(node, "name")
            if cname:
                add_record(records, rel, "constraint_pk", cname, node.lineno)

        # Column names
        elif fname in {"sa.Column", "Column"}:
            cname = call_first_str(node)
            if cname:
                add_record(records, rel, "column", cname, node.lineno)

        # ForeignKey columns without explicit name: note only (project has no naming_convention)
        elif fname in {"sa.ForeignKey", "ForeignKey"}:
            # SQLAlchemy has no project naming_convention configured in app/db/base.py,
            # so unnamed constraints are backend-generated; nothing static to length-validate.
            pass

    return records


def print_table(rows: list[IdentifierRecord]) -> None:
    header = f"{'migration_file':60} | {'identifier_type':18} | {'name':70} | {'length':6} | {'VIOLATION':9}"
    print(header)
    print("-" * len(header))
    for r in rows:
        vio = "YES" if r.violation else "no"
        m = (r.migration_file[:60]).ljust(60)
        t = (r.identifier_type[:18]).ljust(18)
        n = (r.name[:70]).ljust(70)
        print(f"{m} | {t} | {n} | {str(r.length).rjust(6)} | {vio:9}")


def main() -> None:
    all_records: list[IdentifierRecord] = []
    for f in sorted(glob.glob(VERSIONS_GLOB)):
        all_records.extend(scan_file(Path(f)))

    # Remove exact duplicates (same file/type/name/line)
    dedup: dict[tuple[str, str, str, int], IdentifierRecord] = {}
    for r in all_records:
        dedup[(r.migration_file, r.identifier_type, r.name, r.lineno)] = r
    rows = sorted(dedup.values(), key=lambda x: (x.migration_file, x.lineno, x.identifier_type, x.name))

    violations = [r for r in rows if r.violation]
    print_table(violations)

    payload = {
        "summary": {
            "total_identifiers_scanned": len(rows),
            "total_violations": len(violations),
            "project_naming_convention": "none (app/db/base.py has no MetaData.naming_convention)",
            "auto_fk_note": "Unnamed FK constraint names are backend-generated; static length validation is not applicable without naming_convention.",
        },
        "violations": [asdict(v) for v in violations],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\nSummary:")
    print(f"  Total identifiers scanned: {len(rows)}")
    print(f"  Total violations (>=63 bytes): {len(violations)}")
    print(f"  JSON written: {OUT_JSON}")


if __name__ == "__main__":
    main()
