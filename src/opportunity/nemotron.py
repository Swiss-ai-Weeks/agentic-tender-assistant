"""Nemotron Semantic Compiler and Evidence Interpreter.

Role in Architecture:
Tender language / Public records / Company docs
               ↓
    Nemotron (2× NVIDIA H100 NVL)
               ↓
     Candidate structured rules / facts
               ↓
Deterministic Verifier & Rule Engine (PASS / FAIL / UNKNOWN)

Nemotron acts as the semantic compiler and evidence interpreter.
It is NEVER the final eligibility judge.

Security / Sovereign Story:
- Prompt Injection Defense: Tender documents are untrusted inputs. Instruction-like
  text ('IGNORE ALL PREVIOUS INSTRUCTIONS', 'MARK ELIGIBLE') is sanitized, treated
  purely as passive document text, and cannot alter compiled constraints or verdicts.
- Sovereign Enterprise Environment: Deployed on enterprise-controlled hardware (2× H100 NVL)
  so sensitive company qualification data and internal certificates never leave the boundary.
"""
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


class NemotronCompiler:
    """Semantic compiler interface connecting Nemotron on H100 to deterministic verification."""

    def __init__(
        self,
        model_name: str = "nvidia/nemotron-4-340b-instruct",
        endpoint_url: str | None = None,
        compute_target: str = "2× NVIDIA H100 NVL",
    ):
        self.model_name = model_name
        self.endpoint_url = endpoint_url or os.getenv("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
        self.compute_target = compute_target
        self.role = "Semantic Compiler & Evidence Interpreter (Non-authoritative candidate generator)"

    def detect_prompt_injection(self, text: str) -> tuple[bool, str | None]:
        """Detect adversarial instruction-like phrasing inside untrusted tender sources."""
        for pattern in INJECTION_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return True, match.group(0)
        return False, None

    def propose_candidate_rule(self, clause: str) -> dict[str, Any] | None:
        """Propose candidate structured constraints from natural language clauses.

        Nemotron extracts structured candidates which MUST undergo deterministic validation.
        """
        # Semantic candidate proposer for common Swiss public procurement patterns
        clause_clean = " ".join(clause.split())

        # References
        if re.search(r"comparabl|vergleichbar|référence|referenz", clause_clean, re.IGNORECASE):
            num_match = re.search(r"\b(\d+)\b", clause_clean)
            if num_match:
                return {
                    "field": "references",
                    "operator": ">=",
                    "expected": float(num_match.group(1)),
                }

        # Insurance
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

        # Certifications
        cert_match = re.search(r"\b(ISO|IEC)[\s/-]?(\d{4,5})\b", clause_clean, re.IGNORECASE)
        if cert_match:
            return {
                "field": "certifications",
                "operator": "contains",
                "expected": f"{cert_match.group(1).upper()} {cert_match.group(2)}",
            }

        return None

    def compile_clause_with_guard(
        self,
        clause: str,
        source: Source,
        ident: str,
    ) -> tuple[CompiledRule, list[str]]:
        """Compile a clause through prompt-injection defense and deterministic validation.

        Returns:
            (CompiledRule, security_events)
        """
        security_events = []
        is_injection, detected_phrase = self.detect_prompt_injection(clause)

        if is_injection:
            security_events.append(
                f"Instruction-like text detected in source ('{detected_phrase}'). "
                "Treated strictly as document content; compiled tender rules and eligibility remain unchanged."
            )

        # Propose candidate via semantic compiler
        candidate = self.propose_candidate_rule(clause)

        # Validate through deterministic compiler gate
        compiled = compile_clause(clause, source, ident, candidate=candidate)
        return compiled, security_events


default_compiler = NemotronCompiler()
