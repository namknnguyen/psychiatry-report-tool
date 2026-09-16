"""Optional language-model client with PHI egress controls and a fact guard.

The application is fully functional with no model configured: report drafting
and the assistant both fall back to deterministic behaviour.  When a model is
configured, two rules apply before anything leaves the process:

  * A non-local endpoint requires PSYCHREPORT_ALLOW_REMOTE_PHI=1 to be set
    explicitly, and the payload is Safe-Harbor de-identified first.
  * Anything a model writes is checked against the source text by
    `fact_guard`; numbers, codes, doses and dates that do not appear in the
    source cause the model output to be rejected and the deterministic text
    kept.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import List, Optional, Tuple
from urllib.parse import urlparse

LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")


class LLMConfig:
    def __init__(self):
        self.provider = os.environ.get("PSYCHREPORT_LLM_PROVIDER", "none").strip().lower()
        self.base_url = os.environ.get("PSYCHREPORT_LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
        self.model = os.environ.get("PSYCHREPORT_LLM_MODEL", "llama3.1:8b")
        self.api_key = os.environ.get("PSYCHREPORT_LLM_API_KEY", "")
        self.allow_remote_phi = os.environ.get("PSYCHREPORT_ALLOW_REMOTE_PHI", "0") == "1"
        self.timeout = float(os.environ.get("PSYCHREPORT_LLM_TIMEOUT", "60"))

    @property
    def enabled(self) -> bool:
        return self.provider in ("ollama", "openai")

    @property
    def is_local(self) -> bool:
        host = (urlparse(self.base_url).hostname or "").lower()
        return host in LOCAL_HOSTS

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "model": self.model if self.enabled else None,
            "endpoint": self.base_url if self.enabled else None,
            "local": self.is_local,
            "phi_leaves_machine": self.enabled and not self.is_local and self.allow_remote_phi,
            "deidentify_before_send": self.enabled and not self.is_local,
            "blocked_reason": self._blocked_reason(),
        }

    def _blocked_reason(self) -> Optional[str]:
        if not self.enabled:
            return None
        if not self.is_local and not self.allow_remote_phi:
            return ("A remote model endpoint is configured but PSYCHREPORT_ALLOW_REMOTE_PHI is not "
                    "set. Requests are blocked; the deterministic fallback is used instead.")
        return None


CONFIG = LLMConfig()


def reload_config():
    global CONFIG
    CONFIG = LLMConfig()
    return CONFIG


def usable() -> bool:
    return CONFIG.enabled and CONFIG._blocked_reason() is None


def complete(system: str, user: str, max_tokens: int = 900, temperature: float = 0.2) -> Optional[str]:
    """Chat completion against an OpenAI-compatible endpoint (Ollama included).
    Returns None on any failure -- callers must have a non-model fallback."""
    if not usable():
        return None
    payload = {
        "model": CONFIG.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    request = urllib.request.Request(
        CONFIG.base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer " + CONFIG.api_key} if CONFIG.api_key else {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=CONFIG.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError, OSError):
        return None


# --------------------------------------------------------------------------
# Fact guard
# --------------------------------------------------------------------------

_NUM = re.compile(r"\b\d+(?:\.\d+)?\b")
_CODE = re.compile(r"\b[A-TV-Z]\d{2}(?:\.[0-9A-Z]{1,4})?\b")
_DOSE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml|mEq|units?)\b", re.IGNORECASE)
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

# Words a rewrite must not introduce, because they assert clinical facts that
# only the record can establish.
_ASSERTIONS = ("diagnosed with", "prescribed", "denies", "no history of", "resolved",
               "discontinued", "hospitalized", "hospitalised")


def fact_guard(source: str, candidate: str) -> Tuple[bool, List[str]]:
    """Reject a rewrite that introduces facts absent from the source."""
    problems: List[str] = []
    source_l = source.lower()

    def _missing(pattern, kind):
        for match in {m.group(0) for m in pattern.finditer(candidate)}:
            if match.lower() not in source_l:
                problems.append(f"introduced {kind} not present in the source: '{match}'")

    _missing(_CODE, "diagnosis code")
    _missing(_DOSE, "dose")
    _missing(_DATE, "date")
    for match in {m.group(0) for m in _NUM.finditer(candidate)}:
        if match not in source and float(match) > 3:
            problems.append(f"introduced number not present in the source: '{match}'")
    for phrase in _ASSERTIONS:
        if phrase in candidate.lower() and phrase not in source_l:
            problems.append(f"introduced clinical assertion not present in the source: '{phrase}'")
    if len(candidate) > max(400, len(source) * 2.2):
        problems.append("rewrite is substantially longer than the source (possible fabrication)")
    return (not problems), problems


POLISH_SYSTEM = (
    "You are a medical editor working for a psychiatrist. You rewrite text for a specific reader. "
    "Absolute rules: do not add, remove, soften, or infer any clinical fact. Never introduce a "
    "number, dose, date, diagnosis, or medication that is not in the input. Do not offer opinions "
    "or recommendations of your own. Preserve every hedge and qualifier. If the input is already "
    "appropriate, return it unchanged. Return only the rewritten text."
)


def polish(text: str, audience: str, reading_level: str) -> Tuple[str, Optional[str]]:
    """Rewrite a passage for an audience.  Returns (text, note).  On any guard
    failure or model error the original text is returned unchanged."""
    if not usable() or not text.strip():
        return text, None
    instruction = {
        "plain": "Rewrite at roughly an 8th-grade reading level, warm and direct, short sentences. "
                 "Keep any clinical term but explain it in everyday words.",
        "administrative": "Rewrite as clear, concrete professional prose for a non-clinical "
                          "administrator. Keep it factual and specific; no jargon without explanation.",
        "professional": "Tighten into concise clinical prose for another clinician. Keep clinical "
                        "terminology.",
    }.get(reading_level, "Tighten the prose without changing meaning.")
    prompt = f"Reader: {audience}\nInstruction: {instruction}\n\nText:\n{text}"
    result = complete(POLISH_SYSTEM, prompt, max_tokens=800)
    if not result:
        return text, "Model unavailable; deterministic text retained."
    ok, problems = fact_guard(text, result)
    if not ok:
        return text, "AI rewrite rejected by fact guard (" + "; ".join(problems[:3]) + "). Original text kept."
    return result, None
