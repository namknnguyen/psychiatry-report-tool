"""HTTP API: patients, evaluations, authorizations, reports, assistant, compliance."""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import date, datetime
from typing import List, Optional

import threading
import time

from . import assistant, audit, auth, config, generator, llm, redaction
from .db import Store, now
from .forms import FORMS, SENSITIVITY_LABELS, SPECIALLY_PROTECTED, required_fields
from .server import HttpError, Request, Response, Router
from .templates import TEMPLATES

router = Router()

PRACTICE = {
    "name": "Ridgeway Behavioral Health",
    "address": "128 Alder Street, Suite 300, Springfield",
    "phone": "(555) 010-4477",
    "fax": "(555) 010-4478",
}

SESSION_COOKIE = "psychreport_session"


class Context:
    def __init__(self, store: Store):
        self.store = store
        self.practice = PRACTICE


# --------------------------------------------------------------------------
# Auth helpers
# --------------------------------------------------------------------------

def current_user(ctx: Context, req: Request) -> dict:
    token = req.cookie(SESSION_COOKIE)
    user, error = auth.resolve_session(ctx.store, token)
    if user is None:
        raise HttpError(401, error or "Please sign in.")
    return user


def require(user: dict, permission: str) -> None:
    if not auth.can(user, permission):
        raise HttpError(403, "Your role (%s) does not permit this action." % auth.ROLE_LABELS.get(
            user["role"], user["role"]))


def require_clinical(user: dict) -> None:
    if not auth.can(user, "eval.read"):
        raise HttpError(403, "Clinical content is not available to the %s role. "
                             "Only demographics and scheduling data are." % user["role"])


# --------------------------------------------------------------------------
# Serialisation
# --------------------------------------------------------------------------

def _patient_row(ctx: Context, patient_id: int):
    row = ctx.store.one("SELECT * FROM patients WHERE id=?", (patient_id,))
    if row is None:
        raise HttpError(404, "No such patient.")
    return row


def _evaluations(ctx: Context, patient_id: int, eval_ids: Optional[List[int]] = None) -> List[dict]:
    rows = ctx.store.query(
        "SELECT * FROM evaluations WHERE patient_id=? ORDER BY encounter_date, id", (patient_id,))
    out = []
    for row in rows:
        if eval_ids and row["id"] not in eval_ids:
            continue
        payload = ctx.store.payload("evaluations", row)
        out.append({
            "id": row["id"], "patient_id": row["patient_id"], "form_id": row["form_id"],
            "form_name": FORMS[row["form_id"]]["name"] if row["form_id"] in FORMS else row["form_id"],
            "encounter_date": row["encounter_date"], "status": row["status"],
            "created_by": row["created_by"], "signed_by": row["signed_by"], "signed_at": row["signed_at"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "answers": payload.get("answers", {}),
        })
    return out


def _authorizations(ctx: Context, patient_id: int) -> List[dict]:
    rows = ctx.store.query("SELECT * FROM authorizations WHERE patient_id=? ORDER BY id DESC", (patient_id,))
    today = date.today().isoformat()
    out = []
    for row in rows:
        expired = row["expires_date"] < today
        payload = ctx.store.payload("authorizations", row)
        out.append({
            "id": row["id"], "patient_id": row["patient_id"],
            "recipient_name": payload.get("recipient_name", ""),
            "recipient_type": row["recipient_type"], "scopes": json.loads(row["scopes"]),
            "purpose": payload.get("purpose", ""), "signed_date": row["signed_date"],
            "expires_date": row["expires_date"], "revoked": bool(row["revoked"]),
            "expired": expired, "valid": (not row["revoked"]) and not expired,
        })
    return out


def _report_row(ctx: Context, report_id: int):
    row = ctx.store.one("SELECT * FROM reports WHERE id=?", (report_id,))
    if row is None:
        raise HttpError(404, "No such report.")
    return row


def _report_dict(ctx: Context, row, include_content: bool = True) -> dict:
    item = {
        "id": row["id"], "patient_id": row["patient_id"], "template_id": row["template_id"],
        "template_name": TEMPLATES[row["template_id"]]["name"] if row["template_id"] in TEMPLATES
        else row["template_id"],
        "recipient_type": TEMPLATES.get(row["template_id"], {}).get("recipient_type", ""),
        "title": row["title"], "status": row["status"],
        "authorization_id": row["authorization_id"],
        "source_eval_ids": json.loads(row["source_eval_ids"]),
        "amends_report_id": row["amends_report_id"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "signed_by": row["signed_by"], "signed_at": row["signed_at"], "signature": row["signature"],
    }
    if include_content:
        item["content"] = ctx.store.payload("reports", row)
    return item


def _patient_summary(ctx: Context, row, clinical: bool) -> dict:
    payload = ctx.store.payload("patients", row)
    summary = {
        "id": row["id"], "mrn": row["mrn"], "status": row["status"],
        "tags": json.loads(row["tags"]),
        "name": generator.patient_display(payload),
        "first_name": payload.get("first_name", ""), "last_name": payload.get("last_name", ""),
        "preferred_name": payload.get("preferred_name", ""),
        "dob": payload.get("dob", ""), "age": generator._age(payload.get("dob", "")),
        "pronouns": payload.get("pronouns", ""),
        "updated_at": row["updated_at"],
    }
    counts = ctx.store.one(
        "SELECT (SELECT COUNT(*) FROM evaluations WHERE patient_id=?) e,"
        " (SELECT COUNT(*) FROM reports WHERE patient_id=?) r,"
        " (SELECT MAX(encounter_date) FROM evaluations WHERE patient_id=?) d", (row["id"],) * 3)
    summary["evaluation_count"] = counts["e"]
    summary["report_count"] = counts["r"]
    summary["last_encounter"] = counts["d"] or ""
    if clinical:
        record = generator.build_record(_evaluations(ctx, row["id"]))
        risk = redaction.assess_risk(record)
        summary["risk_level"] = risk["level"]
        summary["risk_gaps"] = risk["gaps"]
        primary = generator.parse_diagnoses(
            (record.get("dsm_diagnoses") or [{}])[-1].get("value", "") if record.get("dsm_diagnoses") else "")
        summary["diagnoses"] = primary[:3]
    return summary


def _full_patient(ctx: Context, row) -> dict:
    payload = ctx.store.payload("patients", row)
    return {
        "id": row["id"], "mrn": row["mrn"], "status": row["status"], "tags": json.loads(row["tags"]),
        "demographics": payload,
        "name": generator.patient_display(payload),
        "age": generator._age(payload.get("dob", "")),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


# --------------------------------------------------------------------------
# Session routes
# --------------------------------------------------------------------------

# Hosted-demo sign-in throttle: failures per connection, in memory.
THROTTLE_MAX_FAILURES = 10
THROTTLE_WINDOW_SECONDS = 15 * 60
_throttle_lock = threading.Lock()
_failures: dict = {}


def _recent_failures(client: str) -> list:
    cutoff = time.time() - THROTTLE_WINDOW_SECONDS
    kept = [t for t in _failures.get(client, []) if t > cutoff]
    if kept:
        _failures[client] = kept
    else:
        _failures.pop(client, None)
    return kept


def reset_throttle() -> None:
    with _throttle_lock:
        _failures.clear()


@router.get("/api/public-config")
def public_config(ctx: Context, req: Request):
    """Unauthenticated, so the sign-in page can show the demo banner. Carries
    nothing about patients or users."""
    return {"hosted": config.HOSTED, "practice": ctx.practice["name"]}


@router.post("/api/login")
def login(ctx: Context, req: Request):
    body = req.json
    if config.HOSTED:
        with _throttle_lock:
            if len(_recent_failures(req.client)) >= THROTTLE_MAX_FAILURES:
                raise HttpError(429, "Too many failed sign-in attempts from this connection. "
                                     "Wait 15 minutes and try again.")
    user, error = auth.authenticate(ctx.store, str(body.get("username", "")), str(body.get("password", "")),
                                    lock_accounts=not config.HOSTED)
    if user is None:
        if config.HOSTED:
            with _throttle_lock:
                _failures.setdefault(req.client, []).append(time.time())
        audit.log(ctx.store, None, "login.failed", detail=str(body.get("username", ""))[:64])
        raise HttpError(401, error or "Sign-in failed.")
    token = auth.start_session(ctx.store, user["id"])
    audit.log(ctx.store, user, "login.success")
    response = Response({"user": user, "role_label": auth.ROLE_LABELS[user["role"]]})
    response.set_cookie(SESSION_COOKIE, token, max_age=auth.ABSOLUTE_TIMEOUT)
    return response


@router.post("/api/logout")
def logout(ctx: Context, req: Request):
    token = req.cookie(SESSION_COOKIE)
    if token:
        user, _ = auth.resolve_session(ctx.store, token)
        auth.end_session(ctx.store, token)
        if user:
            audit.log(ctx.store, user, "logout")
    response = Response({"ok": True})
    response.set_cookie(SESSION_COOKIE, "", max_age=0)
    return response


@router.get("/api/me")
def me(ctx: Context, req: Request):
    user = current_user(ctx, req)
    return {
        "user": user,
        "role_label": auth.ROLE_LABELS[user["role"]],
        "permissions": sorted(auth.PERMISSIONS[user["role"]]),
        "idle_timeout": auth.IDLE_TIMEOUT,
    }


@router.get("/api/bootstrap")
def bootstrap(ctx: Context, req: Request):
    current_user(ctx, req)
    return {
        "forms": [{"id": f["id"], "name": f["name"], "cpt": f["cpt"], "description": f["description"],
                   "sections": f["sections"]} for f in FORMS.values()],
        "templates": [{"id": t["id"], "name": t["name"], "recipient_type": t["recipient_type"],
                       "purpose": t["purpose"], "reading_level": t["reading_level"],
                       "requires_authorization": t["requires_authorization"],
                       "identifiers": t["identifiers"], "audience_note": t["audience_note"],
                       "allowed_sens": list(t["allowed_sens"])} for t in TEMPLATES.values()],
        "sensitivity_labels": SENSITIVITY_LABELS,
        "protected_classes": list(SPECIALLY_PROTECTED),
        "practice": ctx.practice,
        "hosted": config.HOSTED,
        "llm": llm.CONFIG.status(),
        "crisis_resources": redaction.CRISIS_RESOURCES,
    }


# --------------------------------------------------------------------------
# Patients
# --------------------------------------------------------------------------

@router.get("/api/patients")
def list_patients(ctx: Context, req: Request):
    user = current_user(ctx, req)
    if not (auth.can(user, "patient.read") or auth.can(user, "patient.read.demographics")):
        raise HttpError(403, "Your role does not permit access to the patient list.")
    clinical = auth.can(user, "eval.read")
    query = (req.q("q") or "").strip().lower()
    tag = (req.q("tag") or "").strip()
    status = req.q("status") or "active"
    rows = ctx.store.query("SELECT * FROM patients ORDER BY updated_at DESC")
    out = []
    for row in rows:
        if status != "all" and row["status"] != status:
            continue
        summary = _patient_summary(ctx, row, clinical)
        if tag and tag not in summary["tags"]:
            continue
        if query and query not in (summary["name"] + " " + summary["mrn"] + " "
                                   + " ".join(summary["tags"])).lower():
            continue
        out.append(summary)
    all_tags = sorted({t for row in rows for t in json.loads(row["tags"])})
    filters = "; ".join(f for f in ((f"search={query!r}" if query else ""),
                                    (f"tag={tag!r}" if tag else "")) if f)
    audit.log(ctx.store, user, "patient.list", detail=filters)
    return {"patients": out, "tags": all_tags, "clinical_visible": clinical}


@router.post("/api/patients")
def create_patient(ctx: Context, req: Request):
    user = current_user(ctx, req)
    if not (auth.can(user, "patient.write") or auth.can(user, "patient.write.demographics")):
        raise HttpError(403, "Your role does not permit creating patients.")
    body = req.json
    demographics = body.get("demographics") or {}
    if not str(demographics.get("last_name", "")).strip():
        raise HttpError(400, "A last name is required.")
    dob = str(demographics.get("dob", "")).strip()
    if dob and not re.match(r"^\d{4}-\d{2}-\d{2}$", dob):
        raise HttpError(400, "Date of birth must be in YYYY-MM-DD format.")
    mrn = str(body.get("mrn") or "").strip() or _next_mrn(ctx)
    if ctx.store.one("SELECT id FROM patients WHERE mrn=?", (mrn,)):
        raise HttpError(409, "That medical record number is already in use.")
    patient_id = ctx.store.insert_sealed("patients", {
        "mrn": mrn, "tags": json.dumps(body.get("tags") or []),
        "status": "active", "created_by": user["id"], "created_at": now(), "updated_at": now(),
    }, demographics)
    audit.log(ctx.store, user, "patient.create", "patient", patient_id, patient_id)
    return {"patient": _full_patient(ctx, _patient_row(ctx, patient_id))}


def _next_mrn(ctx: Context) -> str:
    row = ctx.store.one("SELECT COUNT(*) c FROM patients")
    return "MRN-%05d" % (100 + (row["c"] or 0) + 1)


@router.get("/api/patients/{pid}")
def get_patient(ctx: Context, req: Request):
    user = current_user(ctx, req)
    patient_id = int(req.params["pid"])
    row = _patient_row(ctx, patient_id)
    if not (auth.can(user, "patient.read") or auth.can(user, "patient.read.demographics")):
        raise HttpError(403, "Your role does not permit access to patient records.")
    audit.log(ctx.store, user, "patient.view", "patient", patient_id, patient_id)
    result = {"patient": _full_patient(ctx, row), "authorizations": _authorizations(ctx, patient_id)}
    if not auth.can(user, "eval.read"):
        result["clinical_restricted"] = True
        result["evaluations"] = []
        result["reports"] = []
        result["patient"]["demographics"] = {
            k: v for k, v in result["patient"]["demographics"].items()
            if k in ("first_name", "last_name", "preferred_name", "dob", "phone", "email",
                     "address", "insurance", "emergency_contact", "preferred_language", "pronouns")
        }
        return result
    evaluations = _evaluations(ctx, patient_id)
    record = generator.build_record(evaluations)
    result["evaluations"] = evaluations
    result["reports"] = [_report_dict(ctx, r, include_content=False)
                         for r in ctx.store.query(
                             "SELECT * FROM reports WHERE patient_id=? ORDER BY id DESC", (patient_id,))]
    result["risk"] = redaction.assess_risk(record)
    result["completeness"] = assistant.completeness_check(evaluations)
    result["disclosures"] = _disclosure_rows(ctx, patient_id)
    return result


@router.put("/api/patients/{pid}")
def update_patient(ctx: Context, req: Request):
    user = current_user(ctx, req)
    if not (auth.can(user, "patient.write") or auth.can(user, "patient.write.demographics")):
        raise HttpError(403, "Your role does not permit editing patients.")
    patient_id = int(req.params["pid"])
    row = _patient_row(ctx, patient_id)
    body = req.json
    demographics = body.get("demographics")
    columns = {"updated_at": now()}
    if "tags" in body:
        columns["tags"] = json.dumps(body.get("tags") or [])
    if "status" in body and body["status"] in ("active", "inactive", "archived"):
        columns["status"] = body["status"]
    payload = ctx.store.payload("patients", row)
    if demographics is not None:
        payload = {**payload, **demographics}
    ctx.store.update_sealed("patients", patient_id, payload, columns)
    audit.log(ctx.store, user, "patient.update", "patient", patient_id, patient_id,
              detail=",".join(sorted((demographics or {}).keys()))[:200])
    return {"patient": _full_patient(ctx, _patient_row(ctx, patient_id))}


# --------------------------------------------------------------------------
# Evaluations
# --------------------------------------------------------------------------

def _validate_answers(form_id: str, answers: dict) -> dict:
    if form_id not in FORMS:
        raise HttpError(400, "Unknown evaluation form.")
    valid_ids = set()
    for section in FORMS[form_id]["sections"]:
        for field in section["fields"]:
            valid_ids.add(field["id"])
    cleaned = {}
    for key, value in (answers or {}).items():
        if key not in valid_ids:
            continue
        if isinstance(value, list):
            cleaned[key] = [str(v) for v in value]
        elif value is None:
            continue
        else:
            cleaned[key] = str(value)
    return cleaned


@router.post("/api/patients/{pid}/evaluations")
def create_evaluation(ctx: Context, req: Request):
    user = current_user(ctx, req)
    require(user, "eval.write")
    patient_id = int(req.params["pid"])
    _patient_row(ctx, patient_id)
    body = req.json
    form_id = str(body.get("form_id", ""))
    answers = _validate_answers(form_id, body.get("answers") or {})
    encounter_date = str(body.get("encounter_date") or answers.get("encounter_date") or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", encounter_date):
        raise HttpError(400, "A valid date of service (YYYY-MM-DD) is required.")
    answers["encounter_date"] = encounter_date
    eval_id = ctx.store.insert_sealed("evaluations", {
        "patient_id": patient_id, "form_id": form_id, "encounter_date": encounter_date,
        "status": "draft", "created_by": user["id"], "created_at": now(), "updated_at": now(),
    }, {"answers": answers})
    audit.log(ctx.store, user, "evaluation.create", "evaluation", eval_id, patient_id, detail=form_id)
    return {"evaluation": _evaluations(ctx, patient_id, [eval_id])[0]}


@router.put("/api/evaluations/{eid}")
def update_evaluation(ctx: Context, req: Request):
    user = current_user(ctx, req)
    require(user, "eval.write")
    eval_id = int(req.params["eid"])
    row = ctx.store.one("SELECT * FROM evaluations WHERE id=?", (eval_id,))
    if row is None:
        raise HttpError(404, "No such evaluation.")
    if row["status"] == "signed" and not auth.can(user, "admin"):
        raise HttpError(409, "This evaluation is signed. Signed notes cannot be edited; "
                             "add an addendum with a follow-up note instead.")
    body = req.json
    answers = _validate_answers(row["form_id"], body.get("answers") or {})
    encounter_date = str(body.get("encounter_date") or row["encounter_date"])
    answers["encounter_date"] = encounter_date
    ctx.store.update_sealed("evaluations", eval_id, {"answers": answers},
                            {"updated_at": now(), "encounter_date": encounter_date})
    audit.log(ctx.store, user, "evaluation.update", "evaluation", eval_id, row["patient_id"])
    return {"evaluation": _evaluations(ctx, row["patient_id"], [eval_id])[0]}


@router.post("/api/evaluations/{eid}/sign")
def sign_evaluation(ctx: Context, req: Request):
    user = current_user(ctx, req)
    require(user, "eval.sign")
    eval_id = int(req.params["eid"])
    row = ctx.store.one("SELECT * FROM evaluations WHERE id=?", (eval_id,))
    if row is None:
        raise HttpError(404, "No such evaluation.")
    payload = ctx.store.payload("evaluations", row)
    missing = [fid for fid in required_fields(row["form_id"])
               if not str((payload.get("answers") or {}).get(fid, "")).strip()]
    if missing:
        from .forms import label_of
        raise HttpError(400, "Cannot sign: required field(s) are empty - "
                        + ", ".join(label_of(f) for f in missing))
    ctx.store.execute("UPDATE evaluations SET status='signed', signed_by=?, signed_at=?, updated_at=? "
                      "WHERE id=?", (user["id"], now(), now(), eval_id))
    audit.log(ctx.store, user, "evaluation.sign", "evaluation", eval_id, row["patient_id"])
    return {"evaluation": _evaluations(ctx, row["patient_id"], [eval_id])[0]}


# --------------------------------------------------------------------------
# Authorizations (release of information)
# --------------------------------------------------------------------------

@router.post("/api/patients/{pid}/authorizations")
def create_authorization(ctx: Context, req: Request):
    user = current_user(ctx, req)
    require(user, "auth.manage")
    patient_id = int(req.params["pid"])
    _patient_row(ctx, patient_id)
    body = req.json
    recipient_name = str(body.get("recipient_name", "")).strip()
    recipient_type = str(body.get("recipient_type", "")).strip()
    if not recipient_name or not recipient_type:
        raise HttpError(400, "Recipient name and recipient type are required.")
    scopes = [s for s in (body.get("scopes") or []) if s in SPECIALLY_PROTECTED]
    signed_date = str(body.get("signed_date") or date.today().isoformat())
    expires_date = str(body.get("expires_date") or "")
    for value, label in ((signed_date, "signed date"), (expires_date, "expiration date")):
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            raise HttpError(400, f"A valid {label} (YYYY-MM-DD) is required.")
    if expires_date <= signed_date:
        raise HttpError(400, "The expiration date must be after the date signed.")
    auth_id = ctx.store.insert_sealed("authorizations", {
        "patient_id": patient_id, "recipient_type": recipient_type, "scopes": json.dumps(scopes),
        "signed_date": signed_date, "expires_date": expires_date, "obtained_by": user["id"],
        "created_at": now(),
    }, {"recipient_name": recipient_name, "purpose": str(body.get("purpose", ""))})
    audit.log(ctx.store, user, "authorization.create", "authorization", auth_id, patient_id,
              detail=f"{recipient_type}; scopes={','.join(scopes) or 'none'}")
    return {"authorizations": _authorizations(ctx, patient_id)}


@router.post("/api/authorizations/{aid}/revoke")
def revoke_authorization(ctx: Context, req: Request):
    user = current_user(ctx, req)
    require(user, "auth.manage")
    auth_id = int(req.params["aid"])
    row = ctx.store.one("SELECT * FROM authorizations WHERE id=?", (auth_id,))
    if row is None:
        raise HttpError(404, "No such authorization.")
    ctx.store.execute("UPDATE authorizations SET revoked=1 WHERE id=?", (auth_id,))
    audit.log(ctx.store, user, "authorization.revoke", "authorization", auth_id, row["patient_id"])
    return {"authorizations": _authorizations(ctx, row["patient_id"])}


def _pick_authorization(ctx: Context, patient_id: int, template: dict,
                        explicit_id: Optional[int]) -> Optional[dict]:
    authorizations = _authorizations(ctx, patient_id)
    if explicit_id:
        for item in authorizations:
            if item["id"] == explicit_id:
                return item if item["valid"] else None
        return None
    matches = [a for a in authorizations if a["valid"] and a["recipient_type"] == template["recipient_type"]]
    if not matches:
        return None
    # Prefer the authorization granting the most scope, then the newest.
    matches.sort(key=lambda a: (len(a["scopes"]), a["signed_date"]), reverse=True)
    return matches[0]


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------

def _build(ctx: Context, patient_row, template_id: str, eval_ids: List[int], clinician: dict,
           options: dict) -> dict:
    if template_id not in TEMPLATES:
        raise HttpError(400, "Unknown report template: %s" % template_id)
    template = TEMPLATES[template_id]
    patient_id = patient_row["id"]
    evaluations = _evaluations(ctx, patient_id, eval_ids or None)
    if not evaluations:
        raise HttpError(400, "Select at least one evaluation to build this report from.")
    authorization = _pick_authorization(ctx, patient_id, template, options.get("authorization_id"))
    demographics = ctx.store.payload("patients", patient_row)
    content = generator.generate(
        demographics, patient_row["mrn"], evaluations, template_id, clinician, ctx.practice,
        authorization=authorization, deidentify=bool(options.get("deidentify")),
    )
    content["authorization"] = authorization
    if options.get("ai_polish"):
        content = _ai_polish(content, template)
    return content


def _ai_polish(content: dict, template: dict) -> dict:
    notes = []
    changed = 0
    for section in content["sections"]:
        if section["kind"] not in ("narrative", "bullets"):
            continue
        if section["kind"] == "narrative":
            original = "\n\n".join(str(b) for b in section["body"])
            polished, note = llm.polish(original, template["recipient_type"], template["reading_level"])
            if note:
                notes.append(f"{section['title']}: {note}")
            if polished != original:
                section["body"] = [p.strip() for p in polished.split("\n\n") if p.strip()]
                section["ai_edited"] = True
                changed += 1
        else:
            new_items = []
            for item in section["body"]:
                polished, note = llm.polish(item, template["recipient_type"], template["reading_level"])
                if note:
                    notes.append(f"{section['title']}: {note}")
                new_items.append(polished)
            if new_items != section["body"]:
                section["body"] = new_items
                section["ai_edited"] = True
                changed += 1
    content["ai_assisted"] = changed > 0
    content["ai_notes"] = notes
    if changed:
        content["warnings"] = list(content.get("warnings", [])) + [
            "AI-assisted language was used in %d section(s). Every AI-edited passage passed the "
            "fact guard, but a clinician must still read and approve the wording before signing." % changed]
    return content


@router.post("/api/patients/{pid}/reports/preview")
def preview_report(ctx: Context, req: Request):
    user = current_user(ctx, req)
    require(user, "report.generate")
    patient_row = _patient_row(ctx, int(req.params["pid"]))
    body = req.json
    content = _build(ctx, patient_row, str(body.get("template_id", "")),
                     [int(i) for i in (body.get("eval_ids") or [])], user, body)
    audit.log(ctx.store, user, "report.preview", "patient", patient_row["id"], patient_row["id"],
              detail=str(body.get("template_id")))
    return {"content": content}


@router.post("/api/patients/{pid}/reports")
def create_reports(ctx: Context, req: Request):
    """Generate one report per selected template -- the core fan-out action."""
    user = current_user(ctx, req)
    require(user, "report.generate")
    patient_row = _patient_row(ctx, int(req.params["pid"]))
    body = req.json
    template_ids = body.get("template_ids") or ([body["template_id"]] if body.get("template_id") else [])
    if not template_ids:
        raise HttpError(400, "Select at least one report template.")
    eval_ids = [int(i) for i in (body.get("eval_ids") or [])]
    created = []
    for template_id in template_ids:
        content = _build(ctx, patient_row, template_id, eval_ids, user, body)
        title = "%s - %s" % (TEMPLATES[template_id]["name"],
                             generator.patient_display(ctx.store.payload("patients", patient_row)))
        report_id = ctx.store.insert_sealed("reports", {
            "patient_id": patient_row["id"], "template_id": template_id,
            "authorization_id": (content.get("authorization") or {}).get("id"),
            "title": title, "status": "draft", "source_eval_ids": json.dumps(eval_ids),
            "created_by": user["id"], "created_at": now(), "updated_at": now(),
        }, content)
        audit.log(ctx.store, user, "report.create", "report", report_id, patient_row["id"],
                  detail=template_id)
        created.append(_report_dict(ctx, _report_row(ctx, report_id)))
    return {"reports": created}


@router.get("/api/reports/{rid}")
def get_report(ctx: Context, req: Request):
    user = current_user(ctx, req)
    require_clinical(user)
    row = _report_row(ctx, int(req.params["rid"]))
    audit.log(ctx.store, user, "report.view", "report", row["id"], row["patient_id"])
    return {"report": _report_dict(ctx, row)}


@router.put("/api/reports/{rid}")
def edit_report(ctx: Context, req: Request):
    user = current_user(ctx, req)
    require(user, "report.edit")
    row = _report_row(ctx, int(req.params["rid"]))
    if row["status"] in ("final", "released"):
        raise HttpError(409, "This report is signed and cannot be altered. Use 'Create amended "
                             "version' to issue a corrected document that supersedes it.")
    content = ctx.store.payload("reports", row)
    body = req.json
    index = body.get("section_index")
    if index is None:
        raise HttpError(400, "section_index is required.")
    index = int(index)
    if not 0 <= index < len(content["sections"]):
        raise HttpError(400, "No such section.")
    section = content["sections"][index]
    new_body = body.get("body")
    if section["kind"] in ("narrative", "signature"):
        section["body"] = [str(p) for p in (new_body or []) if str(p).strip()]
    elif section["kind"] == "bullets":
        section["body"] = [str(p) for p in (new_body or []) if str(p).strip()]
    elif section["kind"] == "kv":
        section["body"] = {str(k): str(v) for k, v in (new_body or {}).items()}
    else:
        raise HttpError(400, "This section type is generated and cannot be edited directly.")
    section["edited_by_clinician"] = True
    content["content_hash"] = hashlib.sha256(
        generator.to_text(content).encode("utf-8")).hexdigest()
    ctx.store.update_sealed("reports", row["id"], content, {"updated_at": now()})
    audit.log(ctx.store, user, "report.edit", "report", row["id"], row["patient_id"],
              detail=section["title"])
    return {"report": _report_dict(ctx, _report_row(ctx, row["id"]))}


@router.post("/api/reports/{rid}/amend")
def amend_report(ctx: Context, req: Request):
    """A signed document is immutable. Correcting one means issuing a new
    version that says what it supersedes -- the same thing a practice does on
    paper, and the reason the edit path refuses to touch a signed report."""
    user = current_user(ctx, req)
    require(user, "report.generate")
    row = _report_row(ctx, int(req.params["rid"]))
    if row["status"] == "draft":
        raise HttpError(409, "This report is still a draft - edit it directly.")
    patient_row = _patient_row(ctx, row["patient_id"])
    eval_ids = json.loads(row["source_eval_ids"])
    regenerate = bool(req.json.get("regenerate"))

    if regenerate:
        # Rebuild from the chart, picking up anything documented since.
        content = _build(ctx, patient_row, row["template_id"], eval_ids, user, req.json)
    else:
        content = ctx.store.payload("reports", row)
        content.pop("signature", None)
        content.pop("signed_by", None)
        for section in content.get("sections", []):
            section.pop("edited_by_clinician", None)

    signed_on = (datetime.fromtimestamp(row["signed_at"]).strftime("%Y-%m-%d")
                 if row["signed_at"] else "an earlier date")
    content["amends"] = {"report_id": row["id"], "signed_on": signed_on,
                         "regenerated": regenerate}
    content["warnings"] = ["This is an amended version of a report signed on %s%s. The earlier "
                           "version and any disclosure of it remain in the record."
                           % (signed_on, " and rebuilt from the current chart" if regenerate else "")
                           ] + list(content.get("warnings", []))
    content["footer"] = ("Amended version, superseding the report of %s. " % signed_on) + content["footer"]

    report_id = ctx.store.insert_sealed("reports", {
        "patient_id": row["patient_id"], "template_id": row["template_id"],
        "authorization_id": (content.get("authorization") or {}).get("id"),
        "title": row["title"] + " (amended)", "status": "draft",
        "source_eval_ids": json.dumps(eval_ids), "amends_report_id": row["id"],
        "created_by": user["id"], "created_at": now(), "updated_at": now(),
    }, content)
    audit.log(ctx.store, user, "report.amend", "report", report_id, row["patient_id"],
              detail="supersedes report #%d%s" % (row["id"], "; regenerated" if regenerate else ""))
    return {"report": _report_dict(ctx, _report_row(ctx, report_id))}


@router.post("/api/reports/{rid}/sign")
def sign_report(ctx: Context, req: Request):
    user = current_user(ctx, req)
    require(user, "report.sign")
    row = _report_row(ctx, int(req.params["rid"]))
    if row["status"] != "draft":
        raise HttpError(409, "Only a draft can be signed.")
    content = ctx.store.payload("reports", row)
    attested = bool(req.json.get("attest"))
    if not attested:
        raise HttpError(400, "You must attest that you have reviewed the report before signing.")
    blocking = [w for w in content.get("warnings", []) if w.startswith("Required section")]
    if blocking and not req.json.get("acknowledge_incomplete"):
        raise HttpError(409, "This draft is missing required sections. Acknowledge explicitly to "
                             "sign anyway.", warnings=blocking)
    signature = "%s, %s - signed %s" % (user["display_name"], user.get("credentials", ""),
                                        datetime.now().isoformat(timespec="seconds"))
    content["signature"] = signature
    content["signed_by"] = user["display_name"]
    ctx.store.update_sealed("reports", row["id"], content, {
        "status": "final", "signed_by": user["id"], "signed_at": now(),
        "signature": signature, "updated_at": now()})
    audit.log(ctx.store, user, "report.sign", "report", row["id"], row["patient_id"])
    return {"report": _report_dict(ctx, _report_row(ctx, row["id"]))}


@router.post("/api/reports/{rid}/release")
def release_report(ctx: Context, req: Request):
    user = current_user(ctx, req)
    require(user, "report.release")
    row = _report_row(ctx, int(req.params["rid"]))
    if row["status"] == "draft":
        raise HttpError(409, "Sign the report before releasing it.")
    template = TEMPLATES[row["template_id"]]
    body = req.json
    recipient = str(body.get("recipient", "")).strip()
    method = str(body.get("method", "")).strip()
    purpose = str(body.get("purpose") or template["purpose"])
    override = str(body.get("override_reason", "")).strip()
    if not recipient or not method:
        raise HttpError(400, "Recipient and delivery method are required for the disclosure log.")
    content = ctx.store.payload("reports", row)
    authorization = content.get("authorization")
    if template["requires_authorization"]:
        valid = None
        if authorization:
            for item in _authorizations(ctx, row["patient_id"]):
                if item["id"] == authorization["id"] and item["valid"]:
                    valid = item
        if not valid and not override:
            raise HttpError(403, "A current signed authorization is required to release this report. "
                                 "Record one, or document an override reason (for example an "
                                 "emergency disclosure permitted without authorization).")
    disclosure_id = ctx.store.insert_sealed("disclosures", {
        "report_id": row["id"], "patient_id": row["patient_id"], "method": method,
        "authorization_id": (authorization or {}).get("id"), "released_by": user["id"],
        "released_at": now(), "content_hash": content.get("content_hash", ""),
    }, {"recipient": recipient, "purpose": purpose, "override_reason": override})
    ctx.store.execute("UPDATE reports SET status='released', updated_at=? WHERE id=?", (now(), row["id"]))
    # The audit detail deliberately carries no recipient name: the log is read by
    # people who may not be entitled to the content of the disclosure itself.
    audit.log(ctx.store, user, "report.release", "report", row["id"], row["patient_id"],
              detail=f"{TEMPLATES[row['template_id']]['recipient_type']} via {method}"
                     + ("; disclosure override documented" if override else ""))
    return {"report": _report_dict(ctx, _report_row(ctx, row["id"])),
            "disclosure_id": disclosure_id,
            "disclosures": _disclosure_rows(ctx, row["patient_id"])}


@router.post("/api/reports/{rid}/consistency")
def report_consistency(ctx: Context, req: Request):
    user = current_user(ctx, req)
    require_clinical(user)
    row = _report_row(ctx, int(req.params["rid"]))
    content = ctx.store.payload("reports", row)
    evaluations = _evaluations(ctx, row["patient_id"], json.loads(row["source_eval_ids"]) or None)
    result = assistant.consistency_check(content, evaluations,
                                         extra_source=_non_clinical_facts(ctx, row["patient_id"], content))
    audit.log(ctx.store, user, "report.consistency_check", "report", row["id"], row["patient_id"])
    return result


def _non_clinical_facts(ctx: Context, patient_id: int, content: dict) -> str:
    """Facts a letter may legitimately contain that are not in the chart:
    letterhead, the signing clinician, crisis numbers, the patient's own
    demographics, and today's date."""
    patient_row = ctx.store.one("SELECT * FROM patients WHERE id=?", (patient_id,))
    demographics = ctx.store.payload("patients", patient_row) if patient_row else {}

    def flatten(value):
        if isinstance(value, dict):
            return " ".join(flatten(v) for v in value.values())
        if isinstance(value, list):
            return " ".join(flatten(v) for v in value)
        return str(value)

    users = ctx.store.query("SELECT display_name, credentials, npi FROM users")
    return " ".join([
        flatten(ctx.practice), flatten(demographics), patient_row["mrn"] if patient_row else "",
        " ".join(flatten(dict(r)) for r in users),
        " ".join(redaction.CRISIS_RESOURCES),
        " ".join("%s %s" % (m[1], m[2]) for m in generator.MEASURE_FIELDS),
        date.today().isoformat(), content.get("generated_at", ""),
        " ".join(str(v) for v in (content.get("header") or {}).values()),
        content.get("signature", "") or "",
    ])


@router.get("/api/reports/{rid}/export")
def export_report(ctx: Context, req: Request):
    user = current_user(ctx, req)
    require_clinical(user)
    row = _report_row(ctx, int(req.params["rid"]))
    content = ctx.store.payload("reports", row)
    fmt = req.q("format", "html")
    audit.log(ctx.store, user, "report.export", "report", row["id"], row["patient_id"], detail=fmt)
    if fmt == "txt":
        text = _export_text(content, row, ctx)
        return Response(raw=text.encode("utf-8"), content_type="text/plain; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="report-%d.txt"' % row["id"]})
    return Response(raw=_export_html(content, row, ctx).encode("utf-8"),
                    content_type="text/html; charset=utf-8")


def _export_text(content: dict, row, ctx: Context) -> str:
    lines = [ctx.practice["name"], ctx.practice["address"], ctx.practice["phone"], "",
             content["template_name"].upper(), ""]
    for key, value in content["header"].items():
        lines.append(f"{key}: {value}")
    lines.append("")
    if row["status"] == "draft":
        lines.append("*** DRAFT - NOT FOR RELEASE ***")
        lines.append("")
    lines.append(generator.to_text(content))
    if content.get("signature"):
        lines += ["", content["signature"]]
    return "\n".join(lines)


def _export_html(content: dict, row, ctx: Context) -> str:
    """A standalone printable document. Styling and the print button live in
    /print.css and /print.js because the CSP forbids inline style and script."""
    esc = html.escape
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>%s</title>" % esc(content["template_name"]),
        "<link rel='stylesheet' href='/print.css'>",
        "<script src='/print.js' defer></script></head><body>",
        "<div class='meta'><strong>%s</strong><br>%s<br>%s</div>" % (
            esc(ctx.practice["name"]), esc(ctx.practice["address"]), esc(ctx.practice["phone"])),
        "<h1>%s</h1>" % esc(content["template_name"]),
        "<div class='meta'>Prepared for: %s &middot; Purpose: %s &middot; Generated %s</div>" % (
            esc(content["recipient_type"]), esc(content["purpose"]), esc(content["generated_at"])),
        "<div class='toolbar'><button id='printBtn' type='button'>Print / Save as PDF</button></div>",
    ]
    if row["status"] == "draft":
        parts.append("<p class='draft'>DRAFT &mdash; NOT FOR RELEASE &mdash; CLINICIAN REVIEW REQUIRED</p>")
    parts.append("<div class='hdr'>" + "<br>".join(
        "<strong>%s:</strong> %s" % (esc(k), esc(str(v))) for k, v in content["header"].items()) + "</div>")
    for section in content["sections"]:
        parts.append("<h2>%s</h2>" % esc(section["title"]))
        if section.get("intro"):
            parts.append("<p><em>%s</em></p>" % esc(section["intro"]))
        kind, body = section["kind"], section["body"]
        if kind in ("narrative", "signature"):
            parts += ["<p>%s</p>" % esc(str(p)).replace("\n", "<br>") for p in body]
        elif kind == "bullets":
            parts.append("<ul>" + "".join("<li>%s</li>" % esc(str(b)) for b in body) + "</ul>")
        elif kind == "kv":
            parts.append("<table>" + "".join(
                "<tr><th>%s</th><td>%s</td></tr>" % (esc(str(k)), esc(str(v))) for k, v in body.items())
                + "</table>")
        elif kind == "codes":
            parts.append("<ul>" + "".join(
                "<li><strong>%s</strong> %s</li>" % (esc(c["code"]), esc(c["description"])) for c in body)
                + "</ul>")
        elif kind == "table":
            head = "".join("<th>%s</th>" % esc(c) for c in section.get("columns", []))
            rows = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % esc(str(cell)) for cell in r)
                           for r in body)
            parts.append("<table><tr>%s</tr>%s</table>" % (head, rows))
    if content.get("signature"):
        parts.append("<p class='meta'><em>Electronically signed: %s</em></p>" % esc(content["signature"]))
    if content.get("part2_notice"):
        parts.append("<p class='foot'><strong>42 CFR Part 2 notice.</strong> %s</p>"
                     % esc(content["part2_notice"]))
    parts.append("<p class='foot'>%s</p>" % esc(content["footer"]))
    parts.append("</body></html>")
    return "".join(parts)


# --------------------------------------------------------------------------
# Assistant
# --------------------------------------------------------------------------

@router.post("/api/patients/{pid}/assistant")
def ask_assistant(ctx: Context, req: Request):
    user = current_user(ctx, req)
    require(user, "assistant.use")
    patient_id = int(req.params["pid"])
    patient_row = _patient_row(ctx, patient_id)
    question = str(req.json.get("question", "")).strip()
    if not question:
        raise HttpError(400, "Ask a question.")
    if len(question) > 2000:
        raise HttpError(400, "Question is too long.")
    evaluations = _evaluations(ctx, patient_id)
    reports = [_report_dict(ctx, r) for r in
               ctx.store.query("SELECT * FROM reports WHERE patient_id=? ORDER BY id", (patient_id,))]
    demographics = ctx.store.payload("patients", patient_row)
    names = [demographics.get("first_name", ""), demographics.get("last_name", ""),
             demographics.get("preferred_name", "")]
    result = assistant.answer(question, evaluations, reports, names)
    ctx.store.insert_sealed("assistant_messages", {
        "patient_id": patient_id, "user_id": user["id"], "role": "user", "ts": now()},
        {"text": question})
    ctx.store.insert_sealed("assistant_messages", {
        "patient_id": patient_id, "user_id": user["id"], "role": "assistant", "ts": now()},
        {"text": result["answer"], "citations": result["citations"], "mode": result["mode"],
         "notes": result["notes"]})
    audit.log(ctx.store, user, "assistant.query", "patient", patient_id, patient_id,
              detail="mode=" + result["mode"])
    return result


@router.get("/api/patients/{pid}/assistant")
def assistant_history(ctx: Context, req: Request):
    user = current_user(ctx, req)
    require(user, "assistant.use")
    patient_id = int(req.params["pid"])
    rows = ctx.store.query(
        "SELECT * FROM assistant_messages WHERE patient_id=? ORDER BY id LIMIT 200", (patient_id,))
    messages = []
    for row in rows:
        payload = ctx.store.payload("assistant_messages", row)
        messages.append({"id": row["id"], "role": row["role"], "ts": row["ts"], **payload})
    return {"messages": messages}


# --------------------------------------------------------------------------
# Compliance
# --------------------------------------------------------------------------

def _disclosure_rows(ctx: Context, patient_id: int) -> List[dict]:
    rows = ctx.store.query(
        "SELECT d.*, u.display_name FROM disclosures d LEFT JOIN users u ON u.id=d.released_by "
        "WHERE d.patient_id=? ORDER BY d.id DESC", (patient_id,))
    out = []
    for r in rows:
        payload = ctx.store.payload("disclosures", r)
        out.append({
            "id": r["id"], "report_id": r["report_id"], "method": r["method"],
            "recipient": payload.get("recipient", ""), "purpose": payload.get("purpose", ""),
            "override_reason": payload.get("override_reason", ""),
            "released_by": r["display_name"] or "", "released_at": r["released_at"],
            "authorization_id": r["authorization_id"],
        })
    return out


@router.get("/api/audit")
def audit_log(ctx: Context, req: Request):
    user = current_user(ctx, req)
    if not (auth.can(user, "audit.read") or auth.can(user, "audit.read.own")):
        raise HttpError(403, "Your role does not permit access to the audit log.")
    patient_id = req.q("patient_id")
    limit = min(int(req.q("limit", "300")), 1000)
    if patient_id:
        rows = ctx.store.query(
            "SELECT * FROM audit WHERE patient_id=? ORDER BY id DESC LIMIT ?", (int(patient_id), limit))
    else:
        rows = ctx.store.query("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))
    if auth.can(user, "audit.read.own") and not auth.can(user, "audit.read"):
        rows = [r for r in rows if r["user_id"] == user["id"]]
    return {"entries": [{
        "id": r["id"], "ts": r["ts"], "user": r["username"], "action": r["action"],
        "entity": r["entity"], "entity_id": r["entity_id"], "patient_id": r["patient_id"],
        "detail": r["detail"], "hash": r["hash"][:12],
    } for r in rows], "scope": "all" if auth.can(user, "audit.read") else "own"}


@router.get("/api/audit/verify")
def audit_verify(ctx: Context, req: Request):
    user = current_user(ctx, req)
    if not (auth.can(user, "audit.read") or auth.can(user, "audit.read.own")):
        raise HttpError(403, "Your role does not permit access to the audit log.")
    return audit.verify_chain(ctx.store)


@router.get("/api/patients/{pid}/disclosures")
def disclosures(ctx: Context, req: Request):
    user = current_user(ctx, req)
    if not (auth.can(user, "patient.read") or auth.can(user, "audit.read")):
        raise HttpError(403, "Not permitted.")
    patient_id = int(req.params["pid"])
    return {"disclosures": _disclosure_rows(ctx, patient_id)}


@router.get("/api/compliance")
def compliance(ctx: Context, req: Request):
    user = current_user(ctx, req)
    store = ctx.store
    chain = audit.verify_chain(store)
    counts = store.one("SELECT (SELECT COUNT(*) FROM patients) p,(SELECT COUNT(*) FROM evaluations) e,"
                       "(SELECT COUNT(*) FROM reports) r,(SELECT COUNT(*) FROM disclosures) d")
    controls = [
        {"name": "PHI encrypted at rest",
         "status": "on",
         "detail": "AES-256-GCM per record, key wrapped with PBKDF2-HMAC-SHA256 (600,000 iterations). "
                   "Associated data binds each ciphertext to its table and row."},
        {"name": "Operator passphrase",
         "status": "warn" if store.using_default_passphrase else "on",
         "detail": ("The built-in demonstration passphrase is in use. Set PSYCHREPORT_PASSPHRASE "
                    "before entering real patient information."
                    if store.using_default_passphrase else
                    "A custom passphrase from PSYCHREPORT_PASSPHRASE is in use.")},
        ({"name": "Network exposure",
          "status": "warn",
          "detail": "Public demonstration deployment. TLS is terminated by the hosting provider's "
                    "proxy; session cookies are Secure and HSTS is sent. The database is erased and "
                    "reseeded on every restart. Fictional data only - a public deployment must never "
                    "hold real patient information."}
         if config.HOSTED else
         {"name": "Network exposure",
          "status": "on",
          "detail": "Bound to 127.0.0.1. No outbound connections are made unless a model endpoint "
                    "is explicitly configured."}),
        {"name": "Language model",
         "status": ("on" if not llm.CONFIG.enabled else
                    ("on" if llm.CONFIG.is_local else "warn")),
         "detail": ("No model configured; drafting and the assistant run fully offline."
                    if not llm.CONFIG.enabled else
                    ("Local endpoint %s - PHI stays on this machine." % llm.CONFIG.base_url
                     if llm.CONFIG.is_local else
                     "Remote endpoint %s. Content is de-identified before sending%s."
                     % (llm.CONFIG.base_url,
                        "" if llm.CONFIG.allow_remote_phi else ", and requests are currently blocked")))},
        {"name": "Audit trail",
         "status": "on" if chain["ok"] else "off",
         "detail": chain["message"]},
        {"name": "Automatic logoff", "status": "on",
         "detail": "Sessions end after %d minutes idle and %d hours absolute."
                   % (auth.IDLE_TIMEOUT // 60, auth.ABSOLUTE_TIMEOUT // 3600)},
        {"name": "Minimum necessary",
         "status": "on",
         "detail": "Each template declares the sensitivity classes it may carry; everything else is "
                   "withheld and itemised on the draft."},
        {"name": "42 CFR Part 2",
         "status": "on",
         "detail": "Substance use content is withheld unless the patient's authorization names it, "
                   "and a redisclosure notice is attached when it is included."},
        {"name": "Psychotherapy notes",
         "status": "on",
         "detail": "Process-note fields are excluded from every generated report and from the "
                   "assistant's context, without exception."},
    ]
    return {"controls": controls, "chain": chain,
            "counts": {"patients": counts["p"], "evaluations": counts["e"],
                       "reports": counts["r"], "disclosures": counts["d"]},
            "role": user["role"]}
