"""Tamper-evident audit trail and accounting of disclosures.

HIPAA requires (a) an audit trail of access to PHI and (b) an accounting of
disclosures available to the patient.  Each audit row hashes the previous row,
so a deletion or edit inside the log is detectable by `verify_chain`.
"""

from __future__ import annotations

import json
from typing import Optional

from . import crypto
from .db import Store, now

# Actions worth surfacing in the patient-facing accounting of disclosures.
DISCLOSURE_ACTIONS = ("report.release", "report.export", "report.print")


def log(store: Store, user: Optional[dict], action: str, entity: str = "", entity_id: Optional[int] = None,
        patient_id: Optional[int] = None, detail: str = "") -> None:
    row = store.one("SELECT hash FROM audit ORDER BY id DESC LIMIT 1")
    prev_hash = row["hash"] if row else ""
    timestamp = now()
    payload = json.dumps({
        "ts": round(timestamp, 3), "user": (user or {}).get("id"), "action": action,
        "entity": entity, "entity_id": entity_id, "patient_id": patient_id, "detail": detail,
    }, sort_keys=True)
    store.execute(
        "INSERT INTO audit(ts,user_id,username,action,entity,entity_id,patient_id,detail,prev_hash,hash)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        (timestamp, (user or {}).get("id"), (user or {}).get("username", ""), action, entity,
         entity_id, patient_id, detail, prev_hash, crypto.audit_chain(prev_hash, payload)),
    )


def verify_chain(store: Store) -> dict:
    rows = store.query("SELECT * FROM audit ORDER BY id")
    prev_hash = ""
    for row in rows:
        payload = json.dumps({
            "ts": round(row["ts"], 3), "user": row["user_id"], "action": row["action"],
            "entity": row["entity"], "entity_id": row["entity_id"], "patient_id": row["patient_id"],
            "detail": row["detail"],
        }, sort_keys=True)
        expected = crypto.audit_chain(prev_hash, payload)
        if row["prev_hash"] != prev_hash or row["hash"] != expected:
            return {"ok": False, "entries": len(rows), "broken_at": row["id"],
                    "message": f"Audit chain broken at entry {row['id']}: the log has been altered."}
        prev_hash = row["hash"]
    return {"ok": True, "entries": len(rows), "broken_at": None,
            "message": f"Audit chain intact across {len(rows)} entries."}
