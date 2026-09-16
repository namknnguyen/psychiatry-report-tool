"""Minimum-necessary enforcement, de-identification and risk detection.

Three independent controls live here:

1. `filter_record` -- the only path by which evaluation content reaches a
   report.  A field is carried only if its sensitivity class is permitted by
   the template *and* (for specially protected classes) named in a current,
   unrevoked patient authorization.  Everything dropped is reported back so
   the clinician can see exactly what was withheld and why.

2. `deidentify` -- HIPAA Safe Harbor scrubbing (45 CFR 164.514(b)(2)), used
   for de-identified previews and before any text is sent to a remote model.

3. `assess_risk` -- derives an acuity level from the risk fields so the UI and
   the generated reports can surface safety content instead of burying it.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

from .forms import SPECIALLY_PROTECTED, SENSITIVITY_LABELS, label_of, sensitivity_of

# Psychotherapy process notes are never released by this application, with or
# without an authorization.  Releasing them requires a separate, specific
# authorization and a deliberate manual process outside this tool.
NEVER_RELEASE = ("process_note",)

PART2_NOTICE = (
    "This record contains information about substance use disorder treatment protected by "
    "42 CFR Part 2. Federal law prohibits redisclosure without the specific written consent "
    "of the person to whom it pertains, or as otherwise permitted by 42 CFR Part 2."
)


def allowed_sensitivities(template: dict, authorization: dict | None) -> Tuple[set, set]:
    """Which sensitivity classes may appear in this report.

    Two layers, and both must agree:
      * the template declares what is within the minimum necessary for that
        recipient, and
      * a patient authorization can extend that set by explicitly naming a
        protected category.

    Two rules override both: psychotherapy process notes are never released,
    and substance use disorder content requires an authorization that names it
    (42 CFR Part 2), no matter what the template declares.

    Returns (allowed, blocked) where `blocked` lists protected classes that an
    authorization could unlock.
    """
    granted = set((authorization or {}).get("scopes") or [])
    allowed = set(template.get("allowed_sens", ())) | granted
    for never in NEVER_RELEASE:
        allowed.discard(never)
    if "sud" not in granted:
        allowed.discard("sud")
    blocked = {s for s in SPECIALLY_PROTECTED if s not in allowed and s not in NEVER_RELEASE}
    return allowed, blocked


def filter_record(record: Dict[str, list], template: dict, authorization: dict | None):
    """record: field_id -> [entry, ...] (see generator.build_record).

    Returns (kept, withheld) where withheld describes each dropped field.
    """
    allowed, _blocked = allowed_sensitivities(template, authorization)
    granted = set((authorization or {}).get("scopes") or [])
    kept: Dict[str, list] = {}
    withheld: List[dict] = []
    for field_id, entries in record.items():
        sens = sensitivity_of(field_id)
        if sens == "general" or sens in allowed:
            kept[field_id] = entries
            continue
        if sens in NEVER_RELEASE:
            reason = "Psychotherapy process note - excluded from all generated reports."
        elif sens == "sud":
            reason = ("Substance use disorder content is protected by 42 CFR Part 2 and requires an "
                      "authorization that specifically names it. This recipient's authorization does not.")
        elif sens in SPECIALLY_PROTECTED and sens not in granted:
            reason = ("Specially protected (%s) and not named in the patient's authorization for "
                      "this recipient." % SENSITIVITY_LABELS.get(sens, sens))
        else:
            reason = ("Not within the minimum necessary for a %s disclosure."
                      % template.get("recipient_type", "this"))
        withheld.append({
            "field_id": field_id,
            "label": label_of(field_id),
            "sensitivity": sens,
            "sensitivity_label": SENSITIVITY_LABELS.get(sens, sens),
            "reason": reason,
            "dates": [e["date"] for e in entries],
        })
    withheld.sort(key=lambda w: (w["sensitivity"], w["label"]))
    return kept, withheld


def contains_part2(kept: Dict[str, list]) -> bool:
    return any(sensitivity_of(fid) == "sud" for fid in kept)


# --------------------------------------------------------------------------
# Safe Harbor de-identification
# --------------------------------------------------------------------------

_PATTERNS = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"(?:\+?1[-. ])?\(?\b\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b"), "[PHONE]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"\bhttps?://\S+"), "[URL]"),
    (re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"), "[DATE]"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "[DATE]"),
    (re.compile(r"\b(?:MRN|mrn)[:# ]*\s*[A-Z0-9-]+\b"), "[MRN]"),
    (re.compile(r"\b\d{1,5}\s+[A-Z][a-z]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Boulevard|Blvd)\b"),
     "[ADDRESS]"),
    (re.compile(r"\b(?:9[0-9]|1\d\d)[- ]year[- ]old\b"), "[AGE 90+]"),
]

_MONTHS = ("January February March April May June July August September October November December").split()
_DATE_WORDS = re.compile(r"\b(?:%s)\s+\d{1,2},?\s+\d{4}\b" % "|".join(_MONTHS))


def deidentify(text: str, names: Iterable[str] = (), extra: Iterable[str] = ()) -> str:
    """Safe Harbor scrub (45 CFR 164.514(b)(2)).

    Structured identifiers are removed before names, so that a name embedded in
    an email address or a record locator does not break the surrounding pattern
    and leave the rest of it behind.
    """
    if not text:
        return text
    out = _DATE_WORDS.sub("[DATE]", text)
    for pattern, repl in _PATTERNS:
        out = pattern.sub(repl, out)
    for token in sorted({t for t in list(names) + list(extra) if t and len(t) > 2}, key=len, reverse=True):
        out = re.sub(r"\b%s\b" % re.escape(token), "[NAME]", out, flags=re.IGNORECASE)
    return out


MARKER = re.compile(r"\u00ab\d+\u00bb")


def pseudonymise(text: str, names: Iterable[str] = ()) -> Tuple[str, Dict[str, str]]:
    """Replace every identifier with a numbered marker, returning the mapping.

    De-identification is one-way, which suits the assistant but destroys a
    letter. For a rewrite the identifiers have to come back, so they leave as
    markers the model is told to reproduce verbatim and are restored on return.
    """
    mapping: Dict[str, str] = {}
    reverse: Dict[str, str] = {}

    def token(match):
        value = match.group(0)
        if value not in reverse:
            marker = "\u00ab%d\u00bb" % (len(mapping) + 1)
            mapping[marker] = value
            reverse[value] = marker
        return reverse[value]

    out = _DATE_WORDS.sub(token, text)
    for pattern, _repl in _PATTERNS:
        out = pattern.sub(token, out)
    for name in sorted({n for n in names if n and len(n) > 2}, key=len, reverse=True):
        out = re.sub(r"\b%s\b" % re.escape(name), token, out, flags=re.IGNORECASE)
    return out, mapping


def restore(text: str, mapping: Dict[str, str]) -> str:
    for marker, original in mapping.items():
        text = text.replace(marker, original)
    return text


def deidentify_record(record: Dict[str, list], names: Iterable[str]) -> Dict[str, list]:
    scrubbed = {}
    for field_id, entries in record.items():
        scrubbed[field_id] = [dict(e, value=deidentify(str(e["value"]), names)) for e in entries]
    return scrubbed


# --------------------------------------------------------------------------
# Risk detection
# --------------------------------------------------------------------------

RISK_ORDER = {"": 0, "Low": 1, "Moderate": 2, "High": 3, "Imminent": 4}

_ACUTE_PHRASES = (
    "active with intent", "active with intent and plan", "imminent",
    "ideation with identified target",
)


def assess_risk(record: Dict[str, list]) -> dict:
    """Derive a current risk picture from the most recent risk entries."""

    def latest(field_id):
        entries = record.get(field_id) or []
        return entries[-1] if entries else None

    stated = latest("risk_level")
    level = (stated or {}).get("value", "") if stated else ""
    flags: List[str] = []

    si = (latest("si_ideation") or {}).get("value", "")
    hi = (latest("hi_ideation") or {}).get("value", "")
    intent = (latest("si_intent") or {}).get("value", "")
    for value, label in ((si, "Suicidal ideation: %s" % si), (hi, "Violence risk: %s" % hi)):
        if value and value.lower() not in ("none", ""):
            flags.append(label)
    if intent and intent != "None":
        flags.append("Stated intent: %s" % intent)

    derived = level
    joined = " ".join(str(v).lower() for v in (si, hi, intent))
    if any(p in joined for p in _ACUTE_PHRASES) and RISK_ORDER.get(level, 0) < 3:
        derived = "High"
        flags.append("Escalated by rule: ideation with intent/plan or identified target present.")

    plan = (latest("safety_plan") or {}).get("value", "")
    means = (latest("si_means") or {}).get("value", "")
    duty = (latest("duty_to_warn") or {}).get("value", "")
    gaps = []
    if RISK_ORDER.get(derived, 0) >= 2 and not plan.strip():
        gaps.append("Moderate or higher risk without a documented safety plan.")
    if RISK_ORDER.get(derived, 0) >= 2 and not means.strip():
        gaps.append("Risk elevated without documented lethal-means counselling.")
    if hi and "identified target" in hi.lower() and not duty.strip():
        gaps.append("Identified potential victim without a documented duty-to-warn analysis.")

    return {
        "level": derived or "Not documented",
        "stated_level": level,
        "escalated": bool(derived and level and derived != level),
        "flags": flags,
        "gaps": gaps,
        "safety_plan": plan,
        "protective": (latest("protective") or {}).get("value", ""),
        "rationale": (latest("risk_rationale") or {}).get("value", ""),
        "date": (stated or {}).get("date", ""),
    }


# ICD-10-CM F10-F19 are mental and behavioural disorders due to psychoactive
# substance use: the diagnosis line itself is Part 2 content.
SUD_CODE = re.compile(r"^F1[0-9]")


def is_sud_diagnosis(code: str) -> bool:
    return bool(code and SUD_CODE.match(code.strip().upper()))


CRISIS_RESOURCES = [
    "988 Suicide & Crisis Lifeline - call or text 988 (24/7, United States).",
    "Crisis Text Line - text HOME to 741741.",
    "Veterans Crisis Line - dial 988 then press 1.",
    "If there is immediate danger to life, call 911 or go to the nearest emergency department.",
]
