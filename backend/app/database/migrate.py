"""
Minimal, repeatable SQL migrations.

Applies backend/migrations/NNNN_*.sql in order.  Each file runs in its own
transaction and is recorded in ``schema_migrations``; applied files are
skipped, and an applied file whose content later changes is reported as an
error (write a new migration instead of editing an old one).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class MigrationError(RuntimeError):
    pass


def _files(directory: Path) -> list[Path]:
    files = sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    versions = [f.name[:4] for f in files]
    if len(versions) != len(set(versions)):
        raise MigrationError(f"Duplicate migration numbers in {directory}")
    return files


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def pending(conn: psycopg.Connection[Any], directory: Path = MIGRATIONS_DIR) -> list[Path]:
    conn.execute(
        """create table if not exists schema_migrations (
               version     text primary key,
               filename    text not null,
               checksum    text not null,
               applied_at  timestamptz not null default now())"""
    )
    conn.execute("alter table schema_migrations enable row level security")
    applied = {
        v: (fn, cs)
        for v, fn, cs in conn.execute("select version, filename, checksum from schema_migrations")
    }
    todo: list[Path] = []
    for f in _files(directory):
        version = f.name[:4]
        if version in applied:
            if applied[version][1] != _checksum(f):
                raise MigrationError(
                    f"{f.name} changed after it was applied. Add a new migration instead."
                )
        else:
            todo.append(f)
    return todo


def migrate(conn: psycopg.Connection[Any], directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations; returns the filenames applied."""
    with conn.transaction():
        todo = pending(conn, directory)
    done: list[str] = []
    for f in todo:
        with conn.transaction():
            conn.execute(f.read_text(encoding="utf-8"))  # type: ignore[call-overload]
            conn.execute(
                "insert into schema_migrations (version, filename, checksum) values (%s, %s, %s)",
                (f.name[:4], f.name, _checksum(f)),
            )
        done.append(f.name)
    return done
