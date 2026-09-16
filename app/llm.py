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
import socket
import urllib.error
import urllib.request
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from . import redaction

LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"


class LLMConfig:
    def __init__(self, provider=None, base_url=None, model=None, api_key=None,
                 allow_remote_phi=None, timeout=None, user_supplied=False):
        env = os.environ.get
        self.provider = (provider if provider is not None
                         else env("PSYCHREPORT_LLM_PROVIDER", "none")).strip().lower()
        self.base_url = (base_url if base_url is not None
                         else env("PSYCHREPORT_LLM_BASE_URL", "http://localhost:11434/v1")).rstrip("/")
        self.model = model if model is not None else env("PSYCHREPORT_LLM_MODEL", "llama3.1:8b")
        self.api_key = api_key if api_key is not None else env("PSYCHREPORT_LLM_API_KEY", "")
        self.allow_remote_phi = (allow_remote_phi if allow_remote_phi is not None
                                 else env("PSYCHREPORT_ALLOW_REMOTE_PHI", "0") == "1")
        self.timeout = float(timeout if timeout is not None else env("PSYCHREPORT_LLM_TIMEOUT", "60"))
        # True when a signed-in user supplied this key through the UI for their
        # own session, rather than an operator configuring the whole service.
        self.user_supplied = user_supplied

    @classmethod
    def for_session(cls, api_key: str, model: str = "", base_url: str = "") -> "LLMConfig":
        return cls(provider="openai", base_url=base_url or OPENROUTER_BASE_URL,
                   model=model or DEFAULT_OPENROUTER_MODEL, api_key=api_key,
                   allow_remote_phi=False, user_supplied=True)

    @property
    def enabled(self) -> bool:
        return self.provider in ("ollama", "openai")

    @property
    def is_local(self) -> bool:
        host = (urlparse(self.base_url).hostname or "").lower()
        return host in LOCAL_HOSTS

    @property
    def scrub_before_send(self) -> bool:
        """A key typed into the UI belongs to an outside provider, so it counts
        as off-machine even when the endpoint happens to look local."""
        return self.enabled and (not self.is_local or self.user_supplied)

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "model": self.model if self.enabled else None,
            "endpoint": self.base_url if self.enabled else None,
            "local": self.is_local,
            "phi_leaves_machine": self.enabled and not self.is_local
                                  and (self.allow_remote_phi or self.user_supplied),
            "deidentify_before_send": self.scrub_before_send,
            "blocked_reason": self._blocked_reason(),
            "user_supplied": self.user_supplied,
            # Enough to recognise which key is in use, never enough to use it.
            "key_hint": ("..." + self.api_key[-4:]) if (self.user_supplied and len(self.api_key) > 4) else "",
        }

    def _blocked_reason(self) -> Optional[str]:
        if not self.enabled:
            return None
        if not self.is_local and not self.allow_remote_phi and not self.user_supplied:
            return ("A remote model endpoint is configured but PSYCHREPORT_ALLOW_REMOTE_PHI is not "
                    "set. Requests are blocked; the deterministic fallback is used instead.")
        return None


CONFIG = LLMConfig()


def reload_config():
    global CONFIG
    CONFIG = LLMConfig()
    return CONFIG


def usable(cfg: Optional[LLMConfig] = None) -> bool:
    cfg = cfg or CONFIG
    return cfg.enabled and cfg._blocked_reason() is None


def _build_request(cfg: LLMConfig, system: str, user: str, max_tokens: int, temperature: float):
    payload = {
        "model": cfg.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    return urllib.request.Request(
        cfg.base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer " + cfg.api_key} if cfg.api_key else {})},
        method="POST",
    )


def complete(system: str, user: str, max_tokens: int = 900, temperature: float = 0.2,
             cfg: Optional[LLMConfig] = None) -> Optional[str]:
    """Chat completion against an OpenAI-compatible endpoint (Ollama included).
    Returns None on any failure -- callers must have a non-model fallback."""
    cfg = cfg or CONFIG
    if not usable(cfg):
        return None
    try:
        with urllib.request.urlopen(_build_request(cfg, system, user, max_tokens, temperature),
                                    timeout=cfg.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError, OSError):
        return None


def verify(cfg: LLMConfig) -> Tuple[bool, str]:
    """One tiny call, so a bad key is reported when it is entered rather than
    silently degrading to the deterministic fallback later. Provider responses
    are summarised by status code only -- their bodies can echo the key back."""
    try:
        request = _build_request(cfg, "Reply with the single word: ready.", "ready?", 5, 0.0)
        with urllib.request.urlopen(request, timeout=min(cfg.timeout, 20)) as response:
            json.loads(response.read().decode("utf-8"))
        return True, "Key accepted by %s." % (urlparse(cfg.base_url).hostname or "the endpoint")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, "The provider rejected this key (HTTP %d). Check it is correct and active." % exc.code
        if exc.code == 402:
            return False, "The provider reports no credit available for this key (HTTP 402)."
        if exc.code == 404:
            return False, "The provider does not recognise the model '%s' (HTTP 404)." % cfg.model
        if exc.code == 429:
            return False, "The provider is rate limiting this key (HTTP 429). Try again shortly."
        return False, "The provider returned HTTP %d." % exc.code
    except (TimeoutError, socket.timeout):
        return False, "The endpoint did not respond within %d seconds." % min(cfg.timeout, 20)
    except (urllib.error.URLError, OSError):
        return False, "Could not reach %s." % (urlparse(cfg.base_url).hostname or cfg.base_url)
    except (ValueError, KeyError):
        return False, "The endpoint replied with something that is not an OpenAI-compatible response."


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


def polish(text: str, audience: str, reading_level: str,
           cfg: Optional[LLMConfig] = None, identifiers=()) -> Tuple[str, Optional[str]]:
    """Rewrite a passage for an audience.  Returns (text, note).  On any guard
    failure or model error the original text is returned unchanged."""
    cfg = cfg or CONFIG
    if not usable(cfg) or not text.strip():
        return text, None
    payload, mapping = (redaction.pseudonymise(text, identifiers)
                        if cfg.scrub_before_send else (text, {}))
    instruction = {
        "plain": "Rewrite at roughly an 8th-grade reading level, warm and direct, short sentences. "
                 "Keep any clinical term but explain it in everyday words.",
        "administrative": "Rewrite as clear, concrete professional prose for a non-clinical "
                          "administrator. Keep it factual and specific; no jargon without explanation.",
        "professional": "Tighten into concise clinical prose for another clinician. Keep clinical "
                        "terminology.",
    }.get(reading_level, "Tighten the prose without changing meaning.")
    marker_rule = ("\nNames, dates and record numbers have been replaced by markers such as "
                   "\u00ab1\u00bb. Reproduce every marker exactly as it appears and invent no new ones."
                   if mapping else "")
    prompt = f"Reader: {audience}\nInstruction: {instruction}{marker_rule}\n\nText:\n{payload}"
    result = complete(POLISH_SYSTEM, prompt, max_tokens=800, cfg=cfg)
    if not result:
        return text, "Model unavailable; deterministic text retained."
    if mapping:
        missing = [m for m in mapping if m not in result]
        if missing or len(redaction.MARKER.findall(result)) != len(redaction.MARKER.findall(payload)):
            return text, ("AI rewrite rejected: the model did not return the identifiers it was given. "
                          "Original text kept.")
        result = redaction.restore(result, mapping)
    ok, problems = fact_guard(text, result)
    if not ok:
        return text, "AI rewrite rejected by fact guard (" + "; ".join(problems[:3]) + "). Original text kept."
    return result, None
