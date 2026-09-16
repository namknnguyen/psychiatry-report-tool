"""SQLite persistence with record-level PHI encryption.

Nothing containing PHI is written to disk in plaintext.  Structural columns
(ids, timestamps, status flags, foreign keys) stay in the clear so the
database can be queried; every clinical or identifying payload lives in a
sealed BLOB whose associated data binds it to its table and row id.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from . import crypto

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    credentials TEXT NOT NULL DEFAULT '',
    npi TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until REAL NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at REAL NOT NULL,
    last_seen REAL NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mrn TEXT UNIQUE NOT NULL,
    blob BLOB NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    created_by INTEGER NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    form_id TEXT NOT NULL,
    encounter_date TEXT NOT NULL,
    blob BLOB NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_by INTEGER NOT NULL,
    signed_by INTEGER,
    signed_at REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS authorizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    blob BLOB NOT NULL,
    recipient_type TEXT NOT NULL,
    scopes TEXT NOT NULL DEFAULT '[]',
    signed_date TEXT NOT NULL,
    expires_date TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    obtained_by INTEGER NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    template_id TEXT NOT NULL,
    authorization_id INTEGER,
    title TEXT NOT NULL,
    blob BLOB NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    source_eval_ids TEXT NOT NULL DEFAULT '[]',
    amends_report_id INTEGER,
    created_by INTEGER NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    signed_by INTEGER,
    signed_at REAL,
    signature TEXT
);

CREATE TABLE IF NOT EXISTS disclosures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    patient_id INTEGER NOT NULL,
    method TEXT NOT NULL,
    blob BLOB NOT NULL,
    authorization_id INTEGER,
    released_by INTEGER NOT NULL,
    released_at REAL NOT NULL,
    content_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    user_id INTEGER,
    username TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    entity TEXT NOT NULL DEFAULT '',
    entity_id INTEGER,
    patient_id INTEGER,
    detail TEXT NOT NULL DEFAULT '',
    prev_hash TEXT NOT NULL DEFAULT '',
    hash TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS assistant_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    blob BLOB NOT NULL,
    ts REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_eval_patient ON evaluations(patient_id);
CREATE INDEX IF NOT EXISTS idx_report_patient ON reports(patient_id);
CREATE INDEX IF NOT EXISTS idx_auth_patient ON authorizations(patient_id);
CREATE INDEX IF NOT EXISTS idx_audit_patient ON audit(patient_id);
CREATE INDEX IF NOT EXISTS idx_msg_patient ON assistant_messages(patient_id, ts);
"""

DEFAULT_PASSPHRASE = "demo-passphrase-change-me"


class Store:
    """Thread-safe SQLite wrapper that seals/unseals PHI transparently."""

    def __init__(self, path: str, passphrase: Optional[str] = None):
        self.path = path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._cache: Dict[str, Any] = {}
        first_time = not os.path.exists(path) or os.path.getsize(path) == 0
        conn = self._conn()
        conn.executescript(SCHEMA)
        conn.commit()
        passphrase = passphrase or os.environ.get("PSYCHREPORT_PASSPHRASE") or DEFAULT_PASSPHRASE
        self.using_default_passphrase = passphrase == DEFAULT_PASSPHRASE
        self._unlock(passphrase, first_time)

    # -- connection ------------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def query(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        return self._conn().execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        return self._conn().execute(sql, params).fetchone()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            conn = self._conn()
            cur = conn.execute(sql, params)
            conn.commit()
            return cur

    # -- key management --------------------------------------------------
    def _unlock(self, passphrase: str, first_time: bool) -> None:
        row = self.one("SELECT value FROM meta WHERE key='kdf_salt'")
        if row is None:
            salt = os.urandom(16)
            kek = crypto.derive_kek(passphrase, salt)
            data_key = crypto.new_data_key()
            wrapped = crypto.seal(kek, data_key, b"datakey")
            self.execute("INSERT INTO meta(key,value) VALUES('kdf_salt',?)", (salt.hex(),))
            self.execute("INSERT INTO meta(key,value) VALUES('wrapped_key',?)", (wrapped.hex(),))
            self._data_key = data_key
        else:
            salt = bytes.fromhex(row["value"])
            kek = crypto.derive_kek(passphrase, salt)
            wrapped = bytes.fromhex(self.one("SELECT value FROM meta WHERE key='wrapped_key'")["value"])
            try:
                self._data_key = crypto.unseal(kek, wrapped, b"datakey")
            except ValueError:
                raise SystemExit(
                    "Could not unlock the PHI store: PSYCHREPORT_PASSPHRASE does not match the "
                    "database at %s. Use the original passphrase or delete the database to start fresh."
                    % self.path
                )

    # -- sealed payload helpers -----------------------------------------
    def _aad(self, table: str, row_id: int) -> bytes:
        return f"{table}:{row_id}".encode("utf-8")

    def seal_json(self, obj: Any, table: str, row_id: int) -> bytes:
        raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return crypto.seal(self._data_key, raw, self._aad(table, row_id))

    def unseal_json(self, blob: bytes, table: str, row_id: int) -> Any:
        raw = crypto.unseal(self._data_key, bytes(blob), self._aad(table, row_id))
        return json.loads(raw.decode("utf-8"))

    def insert_sealed(self, table: str, columns: Dict[str, Any], payload: Any) -> int:
        """Insert a row, then seal the payload against the assigned row id."""
        cols = list(columns.keys()) + ["blob"]
        placeholders = ",".join("?" for _ in cols)
        with self._lock:
            conn = self._conn()
            cur = conn.execute(
                f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})",
                tuple(columns.values()) + (b"\x00",),
            )
            row_id = cur.lastrowid
            conn.execute(
                f"UPDATE {table} SET blob=? WHERE id=?",
                (self.seal_json(payload, table, row_id), row_id),
            )
            conn.commit()
        self._cache.pop(f"{table}:{row_id}", None)
        return row_id

    def update_sealed(self, table: str, row_id: int, payload: Any, columns: Optional[Dict[str, Any]] = None) -> None:
        sets = ["blob=?"]
        vals: List[Any] = [self.seal_json(payload, table, row_id)]
        for col, val in (columns or {}).items():
            sets.append(f"{col}=?")
            vals.append(val)
        vals.append(row_id)
        self.execute(f"UPDATE {table} SET {','.join(sets)} WHERE id=?", tuple(vals))
        self._cache.pop(f"{table}:{row_id}", None)

    def payload(self, table: str, row: sqlite3.Row) -> Any:
        """Decrypt a row's payload, memoised on (table, id, updated_at)."""
        keys = row.keys()
        stamp = row["updated_at"] if "updated_at" in keys else (row["ts"] if "ts" in keys else 0)
        cache_key = f"{table}:{row['id']}"
        hit = self._cache.get(cache_key)
        if hit and hit[0] == stamp:
            return hit[1]
        value = self.unseal_json(row["blob"], table, row["id"])
        if len(self._cache) > 2000:
            self._cache.clear()
        self._cache[cache_key] = (stamp, value)
        return value


def now() -> float:
    return time.time()
