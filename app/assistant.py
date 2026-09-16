"""The clinical assistant.

Scope is deliberately narrow: it answers questions about *one* patient's own
record and generated reports, always with citations, and it never invents
clinical content.  With no model configured it runs as a retrieval-and-quote
assistant, which is still useful and is fully deterministic.

Guardrails:
  * Retrieval is hard-scoped to the requested patient id -- cross-patient
    questions cannot pull another chart into context.
  * Psychotherapy process notes are excluded from the assistant's context.
  * Any answer that touches risk content is accompanied by the current risk
    stratification and crisis resources.
  * The assistant refuses to issue treatment directives; it reports what the
    record says and flags what is missing.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from . import llm, redaction
from .forms import label_of, sensitivity_of
from .generator import build_record, to_text

STOPWORDS = set("""a an and are as at be by for from has have how in is it its of on or that the to was were what
when where which who why with will would should could this these those there their them they he she his her i you
your do does did not no yes about into over under between during than then""".split())

REFUSAL = (
    "I can summarise and locate what is in this patient's record, but I can't provide clinical "
    "direction or make a diagnostic or medication decision. That judgment is yours."
)

DIRECTIVE_PATTERNS = re.compile(
    r"\b(what should i (prescribe|do|start)|which (medication|drug|antidepressant) should|"
    r"how much .* should i (give|prescribe)|is it safe to (discharge|stop)|diagnose (this|the) patient|"
    r"should i (start|stop|increase|decrease|discharge|admit))\b", re.IGNORECASE)


# A light suffix stripper. Without it, "functional impairments" fails to match
# "impairment in ... functioning", which is exactly how clinicians write.
_SUFFIXES = ("ations", "ation", "ments", "ment", "ings", "ing", "ies", "ness",
             "ally", "ly", "ed", "es", "al", "s")


def _stem(word: str) -> str:
    if word.endswith("sis"):          # diagnosis/diagnoses, analysis/analyses
        return word[:-2]
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            base = word[: -len(suffix)]
            return base + "y" if suffix == "ies" else base
    return word


def _tokens(text: str) -> List[str]:
    return [_stem(t) for t in re.findall(r"[a-z0-9]+", text.lower())
            if t not in STOPWORDS and len(t) > 2]


class Passage:
    __slots__ = ("id", "title", "text", "meta")

    def __init__(self, pid, title, text, meta):
        self.id = pid
        self.title = title
        self.text = text
        self.meta = meta


def build_passages(evaluations: List[dict], reports: List[dict]) -> List[Passage]:
    passages: List[Passage] = []
    record = build_record(evaluations)
    for field_id, entries in record.items():
        if sensitivity_of(field_id) == "process_note":
            continue  # psychotherapy notes are out of scope for the assistant
        for entry in entries:
            passages.append(Passage(
                f"eval:{entry['eval_id']}:{field_id}",
                f"{entry['label']}",
                entry["value"],
                {"kind": "evaluation", "date": entry["date"], "form": entry["form_name"],
                 "eval_id": entry["eval_id"], "field_id": field_id,
                 "sensitivity": sensitivity_of(field_id)},
            ))
    for report in reports:
        content = report.get("content") or {}
        for index, section in enumerate(content.get("sections", [])):
            text = to_text({"sections": [section]})
            passages.append(Passage(
                f"report:{report['id']}:{index}",
                f"{content.get('template_name', 'Report')} - {section['title']}",
                text,
                {"kind": "report", "report_id": report["id"], "status": report.get("status"),
                 "template": content.get("template_name", ""), "date": content.get("generated_at", "")[:10]},
            ))
    return passages


def retrieve(question: str, passages: List[Passage], k: int = 6) -> List[Tuple[Passage, float]]:
    """BM25-style lexical retrieval -- deterministic, local, no embeddings."""
    query = _tokens(question)
    if not query:
        return []
    docs = [_tokens(p.title + " " + p.text) for p in passages]
    n = len(docs) or 1
    avgdl = sum(len(d) for d in docs) / n if n else 1
    df = Counter()
    for doc in docs:
        for term in set(doc):
            df[term] += 1
    scored = []
    k1, b = 1.5, 0.75
    for passage, doc in zip(passages, docs):
        counts = Counter(doc)
        score = 0.0
        for term in query:
            if term not in counts:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            tf = counts[term]
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * len(doc) / (avgdl or 1)))
        if score > 0:
            scored.append((passage, score))
    scored.sort(key=lambda item: -item[1])
    return scored[:k]


SYSTEM = (
    "You are a documentation assistant embedded in a psychiatric record system. You answer only "
    "from the excerpts provided, which come from one patient's chart and generated reports.\n"
    "Rules:\n"
    "1. Every factual claim must come from an excerpt and cite it as [1], [2] etc.\n"
    "2. If the excerpts do not answer the question, say so plainly and name what is missing from "
    "the record. Never fill a gap with clinical knowledge.\n"
    "3. Do not give treatment, medication or diagnostic directives. You may report what the "
    "clinician documented.\n"
    "4. Be concise. Prefer short paragraphs or bullets.\n"
    "5. If the question touches suicide, violence or safety, state the documented risk level and "
    "recommend the clinician review the safety plan."
)


def answer(question: str, evaluations: List[dict], reports: List[dict],
           patient_names: List[str]) -> dict:
    passages = build_passages(evaluations, reports)
    hits = retrieve(question, passages, k=6)
    record = build_record(evaluations)
    risk = redaction.assess_risk(record)
    touches_risk = bool(re.search(r"\b(suicid|self.?harm|risk|safety|violen|homicid|danger|crisis)\w*",
                                  question, re.IGNORECASE))

    citations = [{
        "n": i + 1, "title": p.title, "kind": p.meta["kind"], "date": p.meta.get("date", ""),
        "source": p.meta.get("form") or p.meta.get("template", ""),
        "excerpt": (p.text[:400] + ("..." if len(p.text) > 400 else "")),
    } for i, (p, _score) in enumerate(hits)]

    notes: List[str] = []
    if DIRECTIVE_PATTERNS.search(question):
        return {"answer": REFUSAL, "citations": citations, "mode": "guardrail",
                "risk": risk if touches_risk else None,
                "notes": ["The assistant declines clinical directives by design."]}

    if not hits:
        return {
            "answer": "I could not find anything in this patient's record that answers that. "
                      "The chart may not contain it, or it may be recorded under different wording. "
                      "Try naming the section (for example \"mental status\", \"medication trials\", "
                      "\"safety plan\").",
            "citations": [], "mode": "no-match", "risk": risk if touches_risk else None, "notes": notes,
        }

    context = "\n\n".join(
        f"[{i + 1}] ({p.meta.get('date','')} - {p.title}) {p.text[:1200]}"
        for i, (p, _s) in enumerate(hits)
    )

    if llm.usable():
        payload = context
        if not llm.CONFIG.is_local:
            payload = redaction.deidentify(context, patient_names)
            notes.append("Content was de-identified before being sent to the remote model endpoint.")
        response = llm.complete(SYSTEM, f"Question: {question}\n\nExcerpts:\n{payload}", max_tokens=700)
        if response:
            text = response
            mode = "model"
        else:
            text, mode = _extractive(question, hits), "extractive"
            notes.append("Model endpoint did not respond; fell back to retrieval-only answering.")
    else:
        text, mode = _extractive(question, hits), "extractive"
        notes.append("No language model is configured. Answers are direct quotations from the chart.")

    if touches_risk:
        notes.append(f"Documented risk stratification: {risk['level']}"
                     + (f" ({risk['date']})" if risk.get("date") else "") + ".")
        for gap in risk.get("gaps", []):
            notes.append("Safety gap: " + gap)

    return {"answer": text, "citations": citations, "mode": mode,
            "risk": risk if touches_risk else None, "notes": notes}


def _extractive(question: str, hits) -> str:
    lines = ["Here is what the record says, quoted directly:", ""]
    for i, (passage, _score) in enumerate(hits[:4]):
        date = passage.meta.get("date", "")
        source = passage.meta.get("form") or passage.meta.get("template", "")
        excerpt = passage.text.strip()
        if len(excerpt) > 600:
            excerpt = excerpt[:600].rsplit(" ", 1)[0] + "..."
        lines.append(f"[{i + 1}] {passage.title}"
                     + (f" - {source}, {date}" if date else "") + f"\n{excerpt}")
        lines.append("")
    lines.append("These are excerpts, not a clinical interpretation.")
    return "\n".join(lines).strip()


# --------------------------------------------------------------------------
# Structured checks the assistant offers as one-click actions
# --------------------------------------------------------------------------

def completeness_check(evaluations: List[dict]) -> dict:
    """Which required fields of each evaluation are still empty."""
    from .forms import FORMS, required_fields
    findings = []
    for ev in evaluations:
        answers = ev.get("answers") or {}
        missing = [label_of(fid) for fid in required_fields(ev["form_id"])
                   if not str(answers.get(fid, "")).strip()]
        if missing:
            findings.append({"eval_id": ev["id"], "form": FORMS[ev["form_id"]]["name"],
                             "date": ev.get("encounter_date", ""), "missing": missing})
    return {"findings": findings,
            "summary": ("All required fields are complete." if not findings
                        else f"{sum(len(f['missing']) for f in findings)} required field(s) are still empty.")}


def consistency_check(report_content: dict, evaluations: List[dict],
                      extra_source: str = "") -> dict:
    """Every number, code, dose and date in a report must be traceable.

    The corpus is the chart itself plus the non-clinical facts a letter
    legitimately adds -- practice contact details, the clinician's NPI, the
    crisis numbers and the patient's own demographics.  Anything else that
    appears in the report came from an edit or a model, and is reported.
    """
    source = " ".join(
        str(entry["value"]) for entries in build_record(evaluations).values() for entry in entries)
    source += " " + extra_source
    body = to_text(report_content, include_header=False)
    ok, problems = llm.fact_guard(source, body)
    unsupported = [p for p in problems if "longer than the source" not in p]
    return {
        "ok": not unsupported,
        "problems": unsupported,
        "summary": ("Every number, code and date in this report is traceable to the chart."
                    if not unsupported else
                    f"{len(unsupported)} item(s) in this report could not be traced to the chart."),
    }
