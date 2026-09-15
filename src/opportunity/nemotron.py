"""Optional model candidate proposer with a deterministic acceptance gate.

The model proposes candidate structured rules; the deterministic compiler in
``src.opportunity.compiler`` decides. Default operation never contacts a model:
remote inference runs only when explicitly enabled via ``TENDER_LLM_ENABLED=1``
and explicitly requested per call (``use_llm=True``).

Tender documents are untrusted input. Instruction-like text is detected,
reported, and treated as passive document content only.
"""
import json
import logging
import os
import re
from typing import Any

from src.opportunity.compiler import CompiledRule, compile_clause, validate_candidate
from src.opportunity.models import Source

logger = logging.getLogger(__name__)

INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?previous\s+instructions",
    r"system\s*override",
    r"mark\s+(?:this\s+)?company\s+(?:as\s+)?eligible",
    r"disregard\s+(?:all\s+)?prior\s+prompts?",
    r"you\s+are\s+now\s+in\s+developer\s+mode",
    r"set\s+decision\s*=\s*['\"]?go['\"]?",
    r"bypass\s+mandatory\s+checks?",
]

ALLOWED_FIELDS = {"references", "insurance", "certifications", "revenue", "languages"}
ALLOWED_OPERATORS = {">=", "contains"}

SYSTEM_PROMPT = (
    "Extract one enforceable tender requirement as strict JSON. "
    'Reply with exactly one JSON object: {"field": one of '
    '["references","insurance","certifications","revenue","languages"], '
    '"operator": one of [">=","contains"], "expected": number or string}. '
    'If the clause states no explicit threshold, identifier, or named language, '
    'reply {"abstain": true}. No other text.'
)


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _timeout_s() -> float:
    try:
        return max(1.0, float(os.getenv("TENDER_LLM_TIMEOUT_S", "8")))
    except ValueError:
        return 8.0


class NemotronCompiler:
    """Candidate generator. Never the eligibility judge."""

    def __init__(
        self,
        model_name: str | None = None,
        endpoint_url: str | None = None,
        compute_target: str | None = None,
    ):
        self.model_name = model_name or os.getenv("TENDER_LLM_MODEL", "not-configured")
        self.endpoint_url = endpoint_url or os.getenv("TENDER_LLM_BASE_URL", "")
        self.compute_target = compute_target or os.getenv("TENDER_LLM_COMPUTE", "not-configured")
        self.role = "Candidate proposer (non-authoritative; deterministic compiler decides)"

    def is_enabled(self) -> bool:
        """True only with explicit opt-in plus endpoint and model configured."""
        return bool(_env_flag("TENDER_LLM_ENABLED") and self.endpoint_url and self.model_name != "not-configured")

    def status(self) -> dict[str, Any]:
        """Truthful connectivity state. Never probes the network."""
        if not _env_flag("TENDER_LLM_ENABLED"):
            return {"state": "disabled", "enabled": False, "endpoint": "", "model": self.model_name,
                    "detail": "Model inference is disabled (TENDER_LLM_ENABLED is not set). Deterministic rules only."}
        if not self.endpoint_url or self.model_name == "not-configured":
            return {"state": "configured-incomplete", "enabled": False, "endpoint": self.endpoint_url,
                    "model": self.model_name,
                    "detail": "TENDER_LLM_ENABLED is set but endpoint/model are incomplete. Deterministic rules only."}
        return {"state": "configured", "enabled": True, "endpoint": self.endpoint_url, "model": self.model_name,
                "detail": "Model candidate generation is configured and available on explicit request only."}

    def detect_prompt_injection(self, text: str) -> tuple[bool, str | None]:
        """Detect adversarial instruction-like phrasing inside untrusted tender sources."""
        for pattern in INJECTION_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return True, match.group(0)
        return False, None

    def propose_candidate_rule(self, clause: str) -> dict[str, Any] | None:
        """Local heuristic candidate. No network access. Must still pass validation."""
        clause_clean = " ".join(clause.split())

        if re.search(r"comparabl|vergleichbar|référence|referenz", clause_clean, re.IGNORECASE):
            num_match = re.search(r"\b(\d+)\b", clause_clean, re.IGNORECASE)
            if num_match:
                return {
                    "field": "references",
                    "operator": ">=",
                    "expected": float(num_match.group(1)),
                }

        if re.search(r"liability|assurance\s+responsabilité|haftpflicht", clause_clean, re.IGNORECASE):
            amt_match = re.search(r"(\d+(?:[',]\d{3})*|\d+)\s*(?:million|mio|m\b)?", clause_clean, re.IGNORECASE)
            if amt_match:
                raw_val = float(re.sub(r"[',]", "", amt_match.group(1)))
                if "million" in clause_clean.lower() or "mio" in clause_clean.lower():
                    raw_val *= 1_000_000
                return {
                    "field": "insurance",
                    "operator": ">=",
                    "expected": raw_val,
                }

        cert_match = re.search(r"\b(ISO|IEC)[\s/-]?(\d{4,5})\b", clause_clean, re.IGNORECASE)
        if cert_match:
            return {
                "field": "certifications",
                "operator": "contains",
                "expected": f"{cert_match.group(1).upper()} {cert_match.group(2)}",
            }

        return None

    def fetch_remote_candidate(self, clause: str) -> tuple[dict[str, Any] | None, str]:
        """Bounded OpenAI-compatible candidate fetch. Returns (candidate|None, detail)."""
        if not self.is_enabled():
            return None, "disabled: model inference is not enabled; no request was sent."
        trimmed = " ".join(clause.split())[: int(os.getenv("TENDER_LLM_MAX_CHARS", "2000"))]
        if not trimmed:
            return None, "error: empty clause; no request was sent."
        try:
            import httpx
        except ImportError as exc:
            return None, f"error: httpx is unavailable ({exc}); no request was sent."
        url = self.endpoint_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        api_key = os.getenv("TENDER_LLM_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": trimmed},
            ],
            "temperature": 0,
            "max_tokens": 256,
            "response_format": {"type": "json_object"},
        }
        try:
            with httpx.Client(timeout=_timeout_s()) as client:
                response = client.post(url, json=payload, headers=headers)
        except Exception as exc:
            logger.warning("model candidate fetch failed: %s", exc)
            return None, f"error: model request failed ({type(exc).__name__}); conservative fallback to deterministic rules."
        if response.status_code != 200:
            return None, f"error: model endpoint returned HTTP {response.status_code}; conservative fallback to deterministic rules."
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content) if isinstance(content, str) else content
        except Exception as exc:
            return None, f"error: malformed model response ({type(exc).__name__}); conservative fallback to deterministic rules."
        if isinstance(parsed, dict) and parsed.get("abstain") is True:
            return None, "success: model abstained; clause stays in human review."
        candidate, problem = self.validate_remote_shape(parsed)
        if problem:
            return None, f"error: unsupported model candidate ({problem}); conservative fallback to deterministic rules."
        return candidate, "success: model candidate received; subject to deterministic validation."

    @staticmethod
    def validate_remote_shape(parsed: Any) -> tuple[dict[str, Any] | None, str | None]:
        """Strict structural check before the clause-anchored compiler gate."""
        if not isinstance(parsed, dict):
            return None, "response is not a JSON object"
        field, operator, expected = parsed.get("field"), parsed.get("operator"), parsed.get("expected")
        if field not in ALLOWED_FIELDS:
            return None, f"unsupported field {field!r}"
        if operator not in ALLOWED_OPERATORS:
            return None, f"unsupported operator {operator!r}"
        if field in {"references", "insurance", "revenue"}:
            if not isinstance(expected, (int, float)) or not (0 < expected < 1_000_000_000_000):
                return None, f"non-numeric or out-of-range expected {expected!r}"
        else:
            if not isinstance(expected, str) or not expected.strip() or len(expected) > 64:
                return None, f"invalid expected string {expected!r}"
        extra = set(parsed) - {"field", "operator", "expected"}
        if extra:
            return None, f"unexpected keys {sorted(extra)}"
        return {"field": field, "operator": operator, "expected": expected}, None

    def compile_clause_with_guard(
        self,
        clause: str,
        source: Source,
        ident: str,
        use_llm: bool = False,
    ) -> tuple[CompiledRule, list[str]]:
        """Compile a clause with injection defense and deterministic validation.

        ``use_llm=True`` requests a remote candidate only when explicitly enabled;
        otherwise (and on any model failure) compilation falls back to the
        deterministic path. Returns (CompiledRule, security_events).
        """
        security_events = []
        is_injection, detected_phrase = self.detect_prompt_injection(clause)

        if is_injection:
            security_events.append(
                f"Instruction-like text detected in source ('{detected_phrase}'). "
                "Treated strictly as document content; compiled tender rules and eligibility remain unchanged."
            )

        candidate: dict[str, Any] | None = None
        if use_llm:
            remote, detail = self.fetch_remote_candidate(clause)
            if detail.startswith("success: model candidate"):
                candidate = remote
            elif detail.startswith("success: model abstained"):
                security_events.append("Model abstained on this clause; it stays in human review.")
            elif detail.startswith("disabled"):
                security_events.append("Model inference is disabled; deterministic compilation only (no request sent).")
            else:
                security_events.append(detail)
        compiled = compile_clause(clause, source, ident, candidate=candidate)
        if candidate is not None and compiled.status == "NEEDS_REVIEW":
            security_events.append("Model candidate could not be anchored to the clause text; escalated to human review.")
        _ = validate_candidate  # deterministic gate lives in compiler.validate_candidate
        return compiled, security_events


default_compiler = NemotronCompiler()
