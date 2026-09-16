"""Deterministic report composition.

The base of every report is generated without a language model: the clinician's
own words are selected, ordered, and framed for the recipient.  Nothing is
invented.  Optional AI polish (app/llm.py) may only rephrase what this module
produced, and is fact-guarded before it is accepted.

Every rendered section carries provenance -- which evaluation, which visit
date, and which field each statement came from -- so a clinician can verify a
report against the chart line by line.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Dict, List, Optional

from . import redaction
from .forms import ALL_FIELDS, FORMS, label_of, sensitivity_of
from .templates import ADMINISTRATIVE, FULL, GLOSSARY, LIMITED, MINIMAL, PLAIN, TEMPLATES

# Fields whose value is a current state (latest visit wins) rather than an
# accumulating narrative.
STATE_FIELDS = {
    "mse_appearance", "mse_attitude", "mse_motor", "mse_speech", "mse_mood", "mse_affect",
    "mse_thought_process", "mse_thought_content", "mse_perception", "mse_cognition",
    "mse_insight", "mse_judgment", "risk_level", "risk_rationale", "si_ideation", "si_intent",
    "si_plan", "si_means", "hi_ideation", "hi_detail", "safety_plan", "protective",
    "current_medications", "medication_current", "allergies", "followup", "capacity",
    "dsm_diagnoses", "severity_specifiers", "presentation", "severity", "prognosis",
    "phq9", "gad7", "cssrs", "audit_c", "dast10", "mdq", "ymrs", "pcl5", "whodas",
    "encounter_setting", "encounter_duration", "interpreter", "chronological_age",
}

MEASURE_FIELDS = [
    ("phq9", "PHQ-9 (depression)", "0-27", 27),
    ("gad7", "GAD-7 (anxiety)", "0-21", 21),
    ("pcl5", "PCL-5 (PTSD symptoms)", "0-80", 80),
    ("ymrs", "YMRS (mania)", "0-60", 60),
    ("audit_c", "AUDIT-C (alcohol)", "0-12", 12),
    ("dast10", "DAST-10 (drug use)", "0-10", 10),
    ("mdq", "MDQ (bipolar screen)", "", None),
    ("cssrs", "C-SSRS (suicide risk screen)", "", None),
    ("whodas", "WHODAS 2.0 (function)", "", None),
    ("other_measures", "Other instruments", "", None),
]

ICD_RE = re.compile(r"\b([A-TV-Z]\d{2}(?:\.[0-9A-Z]{1,4})?)\b")


# --------------------------------------------------------------------------
# Record assembly
# --------------------------------------------------------------------------

def build_record(evaluations: List[dict]) -> Dict[str, list]:
    """Merge one or more evaluations into field_id -> [entry...] ordered by
    encounter date (oldest first).  Multiple sessions accumulate; the caller
    decides whether to use the latest entry or the whole series."""
    record: Dict[str, list] = {}
    for ev in sorted(evaluations, key=lambda e: (e.get("encounter_date") or "", e.get("id") or 0)):
        answers = ev.get("answers") or {}
        for field_id, value in answers.items():
            if value is None:
                continue
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value if str(v).strip())
            value = str(value).strip()
            if not value:
                continue
            record.setdefault(field_id, []).append({
                "value": value,
                "date": ev.get("encounter_date") or "",
                "form_id": ev.get("form_id"),
                "form_name": FORMS.get(ev.get("form_id"), {}).get("name", ev.get("form_id")),
                "eval_id": ev.get("id"),
                "field_id": field_id,
                "label": label_of(field_id),
                "sens": sensitivity_of(field_id),
            })
    return record


def _selected(entries: List[dict], field_id: str) -> List[dict]:
    if field_id in STATE_FIELDS or len(entries) == 1:
        return entries[-1:]
    seen, out = set(), []
    for entry in entries:
        key = entry["value"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out


# --------------------------------------------------------------------------
# Language handling
# --------------------------------------------------------------------------

_ABBREV = {
    r"\bpt\b": "the patient", r"\bpts\b": "patients", r"\bhx\b": "history",
    r"\bsx\b": "symptoms", r"\btx\b": "treatment", r"\bdx\b": "diagnosis",
    r"\bfx\b": "function", r"\bw/\b": "with", r"\bw/o\b": "without",
    r"\byo\b": "year-old", r"\by/o\b": "year-old", r"\bc/o\b": "reports",
    r"\bSI\b": "thoughts of suicide", r"\bHI\b": "thoughts of harming others",
    r"\bNPO\b": "nothing by mouth", r"\bWNL\b": "within normal limits",
    r"\bADLs\b": "everyday self-care activities", r"\bETOH\b": "alcohol",
}

# The trailing lookahead keeps a term from firing inside an instrument name:
# "GAD" must not be rewritten inside "GAD-7", nor "ASD" inside "ASD-3".
_GLOSSARY_RES = sorted(
    ((re.compile(r"\b%s\b(?![-\d])" % re.escape(term), re.IGNORECASE), plain)
     for term, plain in GLOSSARY.items()),
    key=lambda pair: -len(pair[0].pattern),
)


def _plain_language(text: str, patient_word: str) -> str:
    """Translate clinical shorthand for a non-clinical reader.  Substitutions
    are lexical only -- no clinical content is added, removed or reordered."""
    out = text
    for pattern, repl in _ABBREV.items():
        out = re.sub(pattern, repl, out)
    for regex, plain in _GLOSSARY_RES:
        out = regex.sub(plain, out, count=2)
    out = re.sub(r"\bthe patient\b", patient_word, out)
    out = re.sub(r"\bThe patient\b", patient_word.capitalize() if patient_word[0].islower() else patient_word, out)
    return out


def _humanise(text: str, template: dict, patient_word: str) -> str:
    text = text.strip()
    if template.get("reading_level") == PLAIN:
        text = _plain_language(text, patient_word)
    return text


def _bullets_from(text: str) -> List[str]:
    parts: List[str] = []
    for raw_line in text.replace("\r", "").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*•]\s*", "", line)
        line = re.sub(r"^\d+[.)]\s*", "", line)
        if line:
            parts.append(line)
    return parts


def parse_diagnoses(text: str) -> List[dict]:
    out = []
    for line in _bullets_from(text):
        match = ICD_RE.search(line)
        code = match.group(1) if match else ""
        desc = line.replace(code, "", 1).strip(" -–:\t") if code else line
        out.append({"code": code, "description": desc})
    return out


# --------------------------------------------------------------------------
# Identity block
# --------------------------------------------------------------------------

def _age(dob: str, on: Optional[str] = None) -> Optional[int]:
    try:
        born = datetime.strptime(dob, "%Y-%m-%d").date()
    except Exception:
        return None
    ref = date.today()
    if on:
        try:
            ref = datetime.strptime(on, "%Y-%m-%d").date()
        except Exception:
            pass
    return ref.year - born.year - ((ref.month, ref.day) < (born.month, born.day))


def patient_display(patient: dict) -> str:
    preferred = (patient.get("preferred_name") or "").strip()
    first = (patient.get("first_name") or "").strip()
    last = (patient.get("last_name") or "").strip()
    if preferred and preferred.lower() != first.lower():
        return f"{first} “{preferred}” {last}".strip()
    return f"{first} {last}".strip() or "(unnamed patient)"


def _identity_block(patient: dict, template: dict, mrn: str) -> dict:
    policy = template.get("identifiers", LIMITED)
    name = patient_display(patient)
    block = {"Patient": name}
    if policy in (FULL, LIMITED):
        if patient.get("dob"):
            age = _age(patient["dob"])
            block["Date of birth"] = patient["dob"] + (f" (age {age})" if age is not None else "")
    if policy == FULL:
        block["Medical record number"] = mrn
        insurance = patient.get("insurance") or {}
        if insurance.get("carrier"):
            block["Insurance"] = insurance.get("carrier", "")
        if insurance.get("member_id"):
            block["Member ID"] = insurance.get("member_id", "")
        if insurance.get("group_number"):
            block["Group number"] = insurance.get("group_number", "")
    if policy == MINIMAL:
        block = {"Employee/Patient": name}
    if patient.get("pronouns"):
        block["Pronouns"] = patient["pronouns"]
    return block


# --------------------------------------------------------------------------
# Custom section builders
# --------------------------------------------------------------------------

def _clinician_line(clinician: dict) -> str:
    parts = [clinician.get("display_name", "")]
    if clinician.get("credentials"):
        parts.append(clinician["credentials"])
    line = ", ".join(p for p in parts if p)
    if clinician.get("npi"):
        line += f" (NPI {clinician['npi']})"
    return line


class _Ctx:
    def __init__(self, patient, record, template, clinician, practice, risk, mrn, patient_word,
                 allowed=()):
        self.patient = patient
        self.record = record
        self.template = template
        self.clinician = clinician
        self.practice = practice
        self.risk = risk
        self.mrn = mrn
        self.patient_word = patient_word
        self.allowed = set(allowed)
        self.dropped_diagnoses = []

    def diagnoses(self):
        """Diagnosis lines, with substance use disorder codes removed unless
        Part 2 content is authorised for this recipient.  A diagnosis of
        F10-F19 is itself substance use disorder information."""
        parsed = parse_diagnoses(self.latest("dsm_diagnoses"))
        if "sud" in self.allowed:
            return parsed
        kept = []
        for item in parsed:
            if redaction.is_sud_diagnosis(item["code"]):
                self.dropped_diagnoses.append(item)
            else:
                kept.append(item)
        return kept

    def latest(self, field_id, default=""):
        entries = self.record.get(field_id)
        return entries[-1]["value"] if entries else default

    def prov(self, *field_ids):
        out = []
        for field_id in field_ids:
            for entry in self.record.get(field_id, [])[-1:]:
                out.append({"field_id": field_id, "label": entry["label"], "date": entry["date"],
                            "form_name": entry["form_name"], "eval_id": entry["eval_id"]})
        return out


def _b_crisis(ctx: _Ctx):
    return {"kind": "bullets", "body": list(redaction.CRISIS_RESOURCES), "provenance": []}


def _b_safety_family(ctx: _Ctx):
    risk = ctx.risk
    level = risk["level"]
    plain = {
        "Low": "Right now, the risk of self-harm looks low. That can change, so it is worth staying aware.",
        "Moderate": "There is some current risk of self-harm. Please take the safety steps below seriously.",
        "High": "There is significant current risk of self-harm. The safety steps below matter a great deal, "
                "and close support over the coming days is important.",
        "Imminent": "There is immediate concern for safety. Do not leave the person alone, and follow the "
                    "emergency steps below now.",
    }.get(level, "Safety was reviewed at this visit.")
    lines = [plain]
    if risk.get("protective"):
        lines.append("Things that are protective right now: " + risk["protective"])
    if risk.get("safety_plan"):
        lines.append("The safety plan we agreed on: " + risk["safety_plan"])
    means = ctx.latest("si_means")
    if means:
        lines.append("Reducing access to anything that could be used for self-harm is one of the most "
                     "effective things a household can do. What we discussed: " + means)
    return {"kind": "narrative", "body": [_humanise(l, ctx.template, ctx.patient_word) for l in lines],
            "provenance": ctx.prov("risk_level", "protective", "safety_plan", "si_means")}


def _b_safety_plan_patient(ctx: _Ctx):
    plan = ctx.latest("safety_plan")
    if not plan:
        return {"kind": "narrative", "body": [
            "We did not write a formal safety plan today. If you start to feel unsafe, use the crisis "
            "numbers below and contact the clinic."], "provenance": []}
    return {"kind": "bullets", "body": _bullets_from(plan), "provenance": ctx.prov("safety_plan")}


def _b_contact(ctx: _Ctx):
    body = {
        "Clinician": _clinician_line(ctx.clinician),
        "Practice": ctx.practice.get("name", ""),
        "Phone": ctx.practice.get("phone", ""),
        "Secure fax": ctx.practice.get("fax", ""),
    }
    return {"kind": "kv", "body": {k: v for k, v in body.items() if v}, "provenance": []}


def _b_school_intro(ctx: _Ctx):
    name = patient_display(ctx.patient)
    age = _age(ctx.patient.get("dob", ""))
    dx = ctx.diagnoses()
    dx_text = dx[0]["description"] if dx else "the concerns raised in the referral"
    body = [
        f"I am the treating psychiatrist for {name}"
        + (f", age {age}" if age is not None else "") + ". "
        f"This letter is provided at the family's written request to support the school team's "
        f"planning. It summarises the findings of a clinical evaluation completed on "
        f"{ctx.latest('encounter_date') or 'the date shown below'} and the supports I recommend "
        f"in the educational setting.",
        f"The evaluation identified {dx_text}. Clinical detail beyond what is needed for "
        f"educational planning has been intentionally omitted.",
    ]
    return {"kind": "narrative", "body": body, "provenance": ctx.prov("dsm_diagnoses", "encounter_date")}


def _b_employer_intro(ctx: _Ctx):
    body = [
        "This letter is provided at the request of my patient to support a request for workplace "
        "accommodation. It describes functional limitations and the adjustments I recommend. "
        "Consistent with the Americans with Disabilities Act, I have not included diagnosis or "
        "clinical history; the employer's obligation is to the functional limitations described here.",
    ]
    return {"kind": "narrative", "body": body, "provenance": []}


def _b_treatment_relationship(ctx: _Ctx):
    dates = sorted({e["date"] for entries in ctx.record.values() for e in entries if e["date"]})
    span = ""
    if dates:
        span = (f"from {dates[0]} to {dates[-1]}" if len(dates) > 1 else f"on {dates[0]}")
    body = {
        "Clinician": _clinician_line(ctx.clinician),
        "Practice": ctx.practice.get("name", ""),
        "Nature of relationship": "Treating psychiatrist",
        "Encounters reflected in this report": f"{len(dates)} documented encounter(s) {span}".strip(),
    }
    return {"kind": "kv", "body": {k: v for k, v in body.items() if v}, "provenance": []}


def _b_insurance_header(ctx: _Ctx):
    patient = ctx.patient
    insurance = patient.get("insurance") or {}
    dx = ctx.diagnoses()
    forms_used = sorted({e["form_id"] for entries in ctx.record.values() for e in entries if e.get("form_id")})
    cpt = ", ".join(sorted({FORMS[f]["cpt"] for f in forms_used if f in FORMS}))
    body = {
        "Member": patient_display(patient),
        "Date of birth": patient.get("dob", ""),
        "Member ID": insurance.get("member_id", ""),
        "Group": insurance.get("group_number", ""),
        "Carrier": insurance.get("carrier", ""),
        "Primary diagnosis": (f"{dx[0]['code']} {dx[0]['description']}".strip() if dx else ""),
        "Services rendered / requested (CPT)": cpt,
        "Rendering provider": _clinician_line(ctx.clinician),
        "Practice": ctx.practice.get("name", ""),
        "Date of this letter": date.today().isoformat(),
    }
    return {"kind": "kv", "body": {k: v for k, v in body.items() if v},
            "provenance": ctx.prov("dsm_diagnoses")}


def _b_measures(ctx: _Ctx):
    rows = []
    for field_id, name, scale, _max in MEASURE_FIELDS:
        entries = ctx.record.get(field_id) or []
        if not entries:
            continue
        if sensitivity_of(field_id) != "general" and field_id not in ctx.record:
            continue
        series = [f"{e['value']}{' (' + e['date'] + ')' if e['date'] else ''}" for e in entries]
        rows.append({"measure": name, "range": scale, "values": "; ".join(series),
                     "latest": entries[-1]["value"], "trend": _trend(entries)})
    if not rows:
        return None
    return {"kind": "table", "columns": ["Measure", "Range", "Result(s)", "Trend"],
            "body": [[r["measure"], r["range"], r["values"], r["trend"]] for r in rows],
            "provenance": ctx.prov(*[f[0] for f in MEASURE_FIELDS])}


def _trend(entries: List[dict]) -> str:
    numeric = []
    for entry in entries:
        try:
            numeric.append(float(str(entry["value"]).strip()))
        except ValueError:
            return "-"
    if len(numeric) < 2:
        return "single measurement"
    delta = numeric[-1] - numeric[0]
    if abs(delta) < 1e-9:
        return "unchanged"
    return f"{'improved' if delta < 0 else 'worsened'} by {abs(delta):g} points since {entries[0]['date']}"


def _b_risk_clinical(ctx: _Ctx):
    risk = ctx.risk
    lines = [f"Stratified risk of suicide: {risk['level']}"
             + (f" (as documented {risk['date']})" if risk.get("date") else "") + "."]
    if risk.get("escalated"):
        lines.append("Note: the recorded stratification was escalated by rule because ideation with "
                     "intent, plan, or an identified target is documented.")
    if risk.get("rationale"):
        lines.append("Rationale: " + risk["rationale"])
    for flag in risk.get("flags", []):
        lines.append(flag)
    if risk.get("protective"):
        lines.append("Protective factors: " + risk["protective"])
    if risk.get("safety_plan"):
        lines.append("Safety plan in place: " + risk["safety_plan"])
    duty = ctx.latest("duty_to_warn")
    if duty:
        lines.append("Duty-to-warn analysis: " + duty)
    return {"kind": "narrative", "body": lines,
            "provenance": ctx.prov("risk_level", "risk_rationale", "si_ideation", "hi_ideation",
                                   "protective", "safety_plan", "duty_to_warn")}


def _b_necessity(ctx: _Ctx):
    dx = ctx.diagnoses()
    primary = (f"{dx[0]['code']} {dx[0]['description']}".strip() if dx else "the diagnosis documented above")
    impair = ctx.latest("func_impact_summary") or ctx.latest("impairment") or ctx.latest("func_work_school")
    prior = ctx.latest("medication_trials") or ctx.latest("prior_treatment")
    plan = ctx.latest("treatment_plan")
    risk = ctx.risk
    lines = [
        f"The services described above are medically necessary for the treatment of {primary}.",
    ]
    if impair:
        lines.append("Documented functional impairment: " + impair)
    if prior:
        lines.append("Prior treatment and response, establishing that less intensive or alternative "
                     "care has been insufficient: " + prior)
    if risk["level"] not in ("Not documented", "Low"):
        lines.append(f"Current risk stratification is {risk['level']}, which raises the level of "
                     f"monitoring required.")
    if plan:
        lines.append("The requested services are expected to address these impairments as follows: " + plan)
    lines.append("Denial or interruption of these services would be expected to result in symptom "
                 "worsening and further loss of function.")
    return {"kind": "narrative", "body": lines,
            "provenance": ctx.prov("dsm_diagnoses", "func_impact_summary", "medication_trials",
                                   "treatment_plan", "risk_level")}


def _b_attestation(ctx: _Ctx):
    body = [
        "I attest that the information in this report is drawn from my own examination of the "
        "patient and from the clinical record, and is accurate to the best of my knowledge.",
        "",
        _clinician_line(ctx.clinician),
        ctx.practice.get("name", ""),
        f"Date: {date.today().isoformat()}",
    ]
    return {"kind": "signature", "body": [b for b in body if b is not None], "provenance": []}


def _b_coordination(ctx: _Ctx):
    body = [
        "Division of care: I am managing diagnosis, medication and risk monitoring. Psychotherapy "
        "goals and frequency are yours to set.",
        "Please contact me directly, rather than by message, for any new suicidal ideation with "
        "intent or plan, new psychotic symptoms, manic switch, or a medication adverse effect.",
        "Contact: " + _clinician_line(ctx.clinician) + " - " + (ctx.practice.get("phone", "") or "see letterhead"),
    ]
    return {"kind": "narrative", "body": body, "provenance": []}


BUILDERS = {
    "crisis_resources": _b_crisis,
    "safety_family": _b_safety_family,
    "safety_plan_patient": _b_safety_plan_patient,
    "contact_block": _b_contact,
    "school_intro": _b_school_intro,
    "employer_intro": _b_employer_intro,
    "treatment_relationship": _b_treatment_relationship,
    "insurance_header": _b_insurance_header,
    "measures_table": _b_measures,
    "risk_summary_clinical": _b_risk_clinical,
    "necessity_statement": _b_necessity,
    "attestation": _b_attestation,
    "coordination_block": _b_coordination,
}


# --------------------------------------------------------------------------
# Section rendering
# --------------------------------------------------------------------------

def _render_section(spec: dict, ctx: _Ctx, kept: Dict[str, list]) -> Optional[dict]:
    kind = spec["kind"]
    if kind == "custom":
        builder = BUILDERS.get(spec["builder"])
        if not builder:
            return None
        built = builder(ctx)
        if not built:
            return None
        built["title"] = spec["title"]
        if spec.get("intro"):
            built["intro"] = spec["intro"]
        return built

    present = [(fid, _selected(kept[fid], fid)) for fid in spec["sources"] if kept.get(fid)]
    if not present:
        return None

    provenance = []
    for field_id, entries in present:
        for entry in entries:
            provenance.append({"field_id": field_id, "label": entry["label"], "date": entry["date"],
                               "form_name": entry["form_name"], "eval_id": entry["eval_id"]})

    if kind == "narrative":
        body = []
        multi_date = len({p["date"] for p in provenance if p["date"]}) > 1
        for field_id, entries in present:
            for entry in entries:
                text = _humanise(entry["value"], ctx.template, ctx.patient_word)
                if multi_date and entry["date"] and len(present) + len(entries) > 2:
                    text = f"[{entry['date']}] {text}"
                body.append(text)
        return {"title": spec["title"], "kind": "narrative", "body": body,
                "provenance": provenance, "intro": spec.get("intro", "")}

    if kind == "bullets":
        seen, body = set(), []
        for field_id, entries in present:
            field_spec = ALL_FIELDS.get(field_id, {})
            # A short answer from a picker ("Module 3") is meaningless on its own
            # in a bulleted list, so it carries its field label.
            label_it = field_spec.get("type") in ("select", "number", "text", "date")
            for entry in entries:
                for bullet in _bullets_from(entry["value"]):
                    text = _humanise(bullet, ctx.template, ctx.patient_word)
                    if label_it and len(text) < 80:
                        text = "%s: %s" % (label_of(field_id), text)
                    key = text.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    body.append(text)
        return {"title": spec["title"], "kind": "bullets", "body": body,
                "provenance": provenance, "intro": spec.get("intro", "")}

    if kind == "kv":
        body = {}
        for field_id, entries in present:
            value = entries[-1]["value"]
            body[label_of(field_id)] = _humanise(value, ctx.template, ctx.patient_word)
        return {"title": spec["title"], "kind": "kv", "body": body,
                "provenance": provenance, "intro": spec.get("intro", "")}

    if kind == "codes":
        codes = []
        for field_id, entries in present:
            for entry in entries:
                for item in parse_diagnoses(entry["value"]):
                    if "sud" not in ctx.allowed and redaction.is_sud_diagnosis(item["code"]):
                        ctx.dropped_diagnoses.append(item)
                        continue
                    codes.append(item)
        deduped, seen = [], set()
        for item in codes:
            key = (item["code"], item["description"].lower())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return {"title": spec["title"], "kind": "codes", "body": deduped,
                "provenance": provenance, "intro": spec.get("intro", "")}

    return None


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def generate(patient: dict, mrn: str, evaluations: List[dict], template_id: str,
             clinician: dict, practice: dict, authorization: Optional[dict] = None,
             deidentify: bool = False) -> dict:
    template = TEMPLATES[template_id]
    record = build_record(evaluations)
    risk = redaction.assess_risk(record)
    kept, withheld = redaction.filter_record(record, template, authorization)

    if deidentify:
        names = [patient.get("first_name", ""), patient.get("last_name", ""),
                 patient.get("preferred_name", "")]
        kept = redaction.deidentify_record(kept, names)

    patient_word = (patient.get("preferred_name") or patient.get("first_name") or "the patient")
    if template["reading_level"] != PLAIN:
        patient_word = "the patient"
    allowed, _blocked = redaction.allowed_sensitivities(template, authorization)
    ctx = _Ctx(patient, kept, template, clinician, practice, risk, mrn, patient_word, allowed)

    sections, missing = [], []
    for spec in template["sections"]:
        rendered = _render_section(spec, ctx, kept)
        if rendered:
            sections.append(rendered)
        elif spec.get("required"):
            missing.append(spec["title"])

    for item in {(d["code"], d["description"]) for d in ctx.dropped_diagnoses}:
        withheld.append({
            "field_id": "dsm_diagnoses",
            "label": "Diagnosis: %s %s" % item,
            "sensitivity": "sud",
            "sensitivity_label": "Substance use (42 CFR Part 2)",
            "reason": "A substance use disorder diagnosis is itself Part 2 information and requires "
                      "an authorization that names substance use content.",
            "dates": [],
        })

    warnings = []
    if missing:
        warnings.append("Required section(s) could not be filled from the record: "
                        + ", ".join(missing) + ". Complete the evaluation or edit the draft before signing.")
    for gap in risk.get("gaps", []):
        warnings.append("Safety: " + gap)
    if template.get("requires_authorization") and not authorization:
        warnings.append("This recipient type requires a signed patient authorization on file. "
                        "The report cannot be released until one is recorded.")
    if redaction.contains_part2(kept):
        warnings.append("This report includes substance use disorder content protected by 42 CFR "
                        "Part 2; the Part 2 redisclosure notice has been attached.")

    header = _identity_block(patient, template, mrn)
    body_text = to_text({"sections": sections})
    report = {
        "template_id": template_id,
        "template_name": template["name"],
        "recipient_type": template["recipient_type"],
        "purpose": template["purpose"],
        "reading_level": template["reading_level"],
        "audience_note": template["audience_note"],
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "header": header,
        "sections": sections,
        "withheld": withheld,
        "warnings": warnings,
        "risk": risk,
        "footer": template["footer"],
        "part2_notice": redaction.PART2_NOTICE if redaction.contains_part2(kept) else "",
        "deidentified": deidentify,
        "ai_assisted": False,
        "ai_notes": [],
        "source_dates": sorted({e["date"] for entries in record.values() for e in entries if e["date"]}),
        "content_hash": hashlib.sha256(body_text.encode("utf-8")).hexdigest(),
    }
    return report


# --------------------------------------------------------------------------
# Plain-text rendering (used for export, hashing and the AI assistant)
# --------------------------------------------------------------------------

def to_text(report: dict, include_header: bool = False) -> str:
    lines: List[str] = []
    if include_header:
        for key, value in (report.get("header") or {}).items():
            lines.append(f"{key}: {value}")
        lines.append("")
    for section in report.get("sections", []):
        lines.append(section["title"].upper())
        if section.get("intro"):
            lines.append(section["intro"])
        kind, body = section["kind"], section["body"]
        if kind in ("narrative", "signature"):
            lines.extend(str(b) for b in body)
        elif kind == "bullets":
            lines.extend(f"  - {b}" for b in body)
        elif kind == "kv":
            lines.extend(f"  {k}: {v}" for k, v in body.items())
        elif kind == "codes":
            lines.extend(f"  {(c['code'] + ' ') if c['code'] else ''}{c['description']}" for c in body)
        elif kind == "table":
            lines.append("  " + " | ".join(section.get("columns", [])))
            lines.extend("  " + " | ".join(str(cell) for cell in row) for row in body)
        lines.append("")
    if report.get("part2_notice"):
        lines.append(report["part2_notice"])
    if report.get("footer"):
        lines.append(report["footer"])
    return "\n".join(lines).strip()
