"""Command-line entry point and composition root.

This is the only module that wires concrete adapters to use cases (D-004). Exit codes are part of
the contract and are asserted by tests:

===  ==========================================================
0    success
1    unexpected error
2    configuration invalid (FR-4)
3    unsupported schema version (FR-2)
4    database locked by another process (FR-8)
===  ==========================================================
"""

from __future__ import annotations

import argparse
import importlib
import platform
import sys
from collections.abc import Sequence
from pathlib import Path

from gtaf.application.config import ConfigError
from gtaf.application.initialize import SchemaVersionError, initialize_database, read_schema_version
from gtaf.infrastructure.config_io import load_configuration
from gtaf.infrastructure.db import (
    DatabaseLockedError,
    DatabaseNotFoundError,
    connect,
    migration_sql_path,
    open_database,
)
from gtaf.infrastructure.logging_setup import log_event, setup_logging

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFIG = 2
EXIT_SCHEMA = 3
EXIT_LOCKED = 4

_REQUIRED_IMPORTS: tuple[str, ...] = ("duckdb", "pydantic", "yaml")


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="gtaf", description="Georgian TV Agenda & Framing — pipeline foundation"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_db = sub.add_parser("init-db", help="create or verify the database schema")
    init_db.add_argument("path", type=Path, help="database file path")
    init_db.add_argument("--log-dir", type=Path, default=Path("logs"))

    schema_version = sub.add_parser("schema-version", help="print the database schema version")
    schema_version.add_argument("path", type=Path, help="database file path")

    check_config = sub.add_parser("check-config", help="validate the corpus configuration")
    check_config.add_argument("--config-dir", type=Path, default=Path("config"))

    doctor = sub.add_parser("doctor", help="check interpreter and dependencies (FR-12)")
    doctor.add_argument("--json", action="store_true", help="emit a JSON object")
    doctor.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="directory the write probe targets (default: data)",
    )

    return parser


def _cmd_init_db(path: Path, log_dir: Path) -> int:
    """Create the schema if absent; verify it if present (FR-1, FR-2, FR-3)."""
    logger = setup_logging(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    sql = migration_sql_path().read_text(encoding="utf-8")

    conn = connect(path, read_only=False)
    try:
        result = initialize_database(conn, sql)
    finally:
        conn.close()

    if result.applied:
        log_event(logger, 20, "db.created", path=str(path), schema_version=result.schema_version)
        print(f"created {path} (schema_version={result.schema_version})")
    else:
        log_event(logger, 20, "db.opened", path=str(path), read_only=False,
                  schema_version=result.schema_version)
        print(f"{path} already at schema_version={result.schema_version}; nothing to do")
    return EXIT_OK


def _cmd_schema_version(path: Path) -> int:
    """Print the stored schema version, refusing an unsupported one (FR-2)."""
    conn = open_database(path, read_only=True)
    try:
        version = read_schema_version(conn)
    finally:
        conn.close()
    print(version)
    return EXIT_OK


def _cmd_check_config(config_dir: Path) -> int:
    """Validate configuration and report counts (FR-7)."""
    bundle = load_configuration(config_dir)
    print(
        f"configuration OK: {bundle.channel_count} channels, "
        f"{bundle.programme_count} programmes"
    )
    return EXIT_OK


def _cmd_doctor(as_json: bool, data_dir: Path) -> int:
    """Report interpreter and dependency health (FR-12)."""
    import duckdb

    checks: list[dict[str, object]] = []
    python_ok = sys.version_info[:2] >= (3, 12)
    checks.append(
        {
            "name": "python",
            "ok": python_ok,
            "detail": platform.python_version(),
            "required": ">=3.12",
        }
    )

    for module_name in _REQUIRED_IMPORTS:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - a failed import is the result being reported
            checks.append(
                {"name": module_name, "ok": False, "detail": f"{type(exc).__name__}: {exc}",
                 "required": "importable"}
            )
        else:
            checks.append(
                {
                    "name": module_name,
                    "ok": True,
                    "detail": str(getattr(module, "__version__", "version unknown")),
                    "required": "importable",
                }
            )

    probe_ok, probe_detail = _write_probe(data_dir)
    checks.append({"name": "db_write_probe", "ok": probe_ok, "detail": probe_detail,
                   "required": "can create a database file"})

    ok = all(bool(check["ok"]) for check in checks)

    if as_json:
        import json

        print(json.dumps({"ok": ok, "duckdb": duckdb.__version__, "checks": checks}, indent=2))
    else:
        for check in checks:
            mark = "OK  " if check["ok"] else "FAIL"
            detail = check["detail"]
            required = check["required"]
            print(f"  [{mark}] {check['name']:<16} {detail}  (required: {required})")
        print(f"\nVERDICT: {'healthy' if ok else 'problems found'}")
    return EXIT_OK if ok else EXIT_ERROR


def _write_probe(probe_dir: Path) -> tuple[bool, str]:
    """Create and drop a throwaway database where real data will live.

    Probing the project's data directory rather than the OS temp directory is deliberate: a
    machine can have a writable temp dir and an unwritable data dir (or the reverse), and only
    the latter determines whether the pipeline can run. It also avoids reporting a sandboxed
    temp directory as a database problem.

    Args:
        probe_dir: Directory to create and remove the probe database in.

    Returns:
        A ``(ok, detail)`` pair suitable for a doctor check row.
    """
    import duckdb

    probe = probe_dir / "_doctor_probe.duckdb"
    try:
        probe_dir.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(probe))
        try:
            conn.execute("CREATE TABLE t (x INTEGER)")
        finally:
            conn.close()
        probe.unlink(missing_ok=True)
        return True, f"created and removed a database in {probe_dir}"
    except Exception as exc:  # noqa: BLE001 - the probe exists to catch any failure
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        probe.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Arguments without the program name; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code.
    """
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "init-db":
            return _cmd_init_db(args.path, args.log_dir)
        if args.command == "schema-version":
            return _cmd_schema_version(args.path)
        if args.command == "check-config":
            return _cmd_check_config(args.config_dir)
        if args.command == "doctor":
            return _cmd_doctor(args.json, args.data_dir)
    except ConfigError as exc:
        for violation in exc.violations:
            print(f"  - {violation}", file=sys.stderr)
        print(f"configuration invalid: {len(exc.violations)} problem(s)", file=sys.stderr)
        return EXIT_CONFIG
    except SchemaVersionError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_SCHEMA
    except DatabaseLockedError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_LOCKED
    except DatabaseNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001 - top-level guard; anything else is exit 1
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ERROR

    print(f"unknown command: {args.command}", file=sys.stderr)
    return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
