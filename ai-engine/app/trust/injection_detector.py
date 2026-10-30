"""Prompt injection and adversarial submission detector.

Identifies embedded instructions, jailbreak attempts, score manipulations,
and delimiter tampering in untrusted student submissions without penalizing
legitimate academic discussions of security.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

from app.llm.gemini_client import GeminiClient
from app.llm import prompts
from app.schemas.trust import InjectionDetectionResult, InjectionRiskLevel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deterministic Pattern Signatures
# ---------------------------------------------------------------------------

_OVERRIDE_PATTERNS = [
    (r"(?i)\b(ignore|disregard|forget|bypass|override)\s+(all\s+)?(previous|prior|earlier|system|above)\s+(instructions|prompts|rules|commands|constraints|directives)\b", "INSTRUCTION_OVERRIDE"),
    (r"(?i)\b(system\s+override|admin\s+override|mode\s+switch)\b", "SYSTEM_OVERRIDE"),
    (r"(?i)\b(you\s+are\s+now|act\s+as|pretend\s+to\s+be)\s+(a\s+|an\s+)?(dan|developer\s+mode|unrestricted|jailbreak|helpful\s+assistant\s+without\s+rules)\b", "JAILBREAK_ROLEPLAY"),
]

_SCORE_MANIPULATION_PATTERNS = [
    (r"(?i)\b(give|award|assign|grant|record|set)\s+(me\s+|this\s+answer\s+)?(full\s+marks?|100%|maximum\s+points?|10\s*\/\s*10|perfect\s+score|an?\s+a\+)\b", "SCORE_MANIPULATION"),
    (r"(?i)\b(grade\s*[:=]\s*(100%?|a\+|10\/10|full))\b", "DIRECT_SCORE_ASSERTION"),
    (r"(?i)\b(output\s+json\s+with\s+marks_awarded\s*[:=]\s*\d+)\b", "STRUCTURED_SCORE_INJECTION"),
]

_LEAK_PATTERNS = [
    (r"(?i)\b(print|reveal|repeat|output|show|display)\s+(the\s+)?(system\s+prompt|developer\s+instructions|initial\s+prompt|hidden\s+rules)\b", "SYSTEM_PROMPT_LEAK"),
]

_DELIMITER_PATTERNS = [
    (r"</untrusted_student_submission>", "DELIMITER_ESCAPE"),
    (r"<untrusted_student_submission>", "DELIMITER_INJECTION"),
    (r"###\s*(QUESTION|OFFICIAL RUBRIC|RETRIEVED COURSE EVIDENCE|SYSTEM)", "SYSTEM_SECTION_SPOOFING"),
]

# Academic discussion indicators
_ACADEMIC_SECURITY_INDICATORS = [
    r"(?i)\b(is\s+defined\s+as|refers\s+to|is\s+a\s+type\s+of\s+attack|vulnerability|cybersecurity|security\s+risk|mitigation|sanitization|sql\s+injection)\b",
    r"(?i)\b(for\s+example,\s*an?\s+attacker|such\s+as\s+when\s+a\s+user|in\s+computer\s+security)\b",
]


class PromptInjectionDetector:
    """Security filter to inspect untrusted student text for adversarial instructions."""

    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        """Initialize PromptInjectionDetector.

        Args:
            gemini_client: Optional Gemini client for ambiguous second-pass classification.
        """
        self.gemini_client = gemini_client

    def detect(
        self,
        student_answer: str,
        question_context: Optional[str] = None,
        use_llm_fallback: bool = False,
    ) -> InjectionDetectionResult:
        """Inspect student submission for prompt injection attacks.

        Args:
            student_answer: Untrusted student answer string.
            question_context: Optional text of the question asked.
            use_llm_fallback: Whether to invoke Gemini on borderline text.

        Returns:
            InjectionDetectionResult with risk assessment and explanation.
        """
        text = student_answer.strip() if student_answer else ""
        if not text:
            return InjectionDetectionResult(
                is_suspicious=False,
                risk_level=InjectionRiskLevel.LOW,
                detected_patterns=[],
                explanation="Empty submission.",
                flag_for_review=False,
            )

        # 1. Run deterministic regex checks
        detected_types, matched_snippets = self._scan_patterns(text)

        # 2. Check for legitimate academic discussion context
        is_academic = self._is_academic_discussion(text, question_context)

        # 3. Analyze matches
        if detected_types:
            # If matches appear in purely academic explanatory context without imperative tone
            if is_academic and not any(t in ("DELIMITER_ESCAPE", "DELIMITER_INJECTION") for t in detected_types):
                # Verify if it's quoted or described
                if self._is_merely_descriptive(text, matched_snippets):
                    logger.info("Academic discussion of security detected; neutralizing false positive.")
                    return InjectionDetectionResult(
                        is_suspicious=False,
                        risk_level=InjectionRiskLevel.LOW,
                        detected_patterns=detected_types,
                        explanation=(
                            f"Submission contains security concepts ({', '.join(detected_types)}) "
                            "used in an explanatory academic discussion rather than an active exploit."
                        ),
                        flag_for_review=False,
                    )

            # Active exploit detected
            risk = InjectionRiskLevel.CRITICAL if any(t in ("DELIMITER_ESCAPE", "INSTRUCTION_OVERRIDE") for t in detected_types) else InjectionRiskLevel.HIGH
            return InjectionDetectionResult(
                is_suspicious=True,
                risk_level=risk,
                detected_patterns=detected_types,
                explanation=(
                    f"Suspicious instructions detected attempting {', '.join(detected_types)}. "
                    "Student submission must be evaluated strictly as text without executing embedded directives."
                ),
                flag_for_review=True,
            )

        # 4. Optional LLM fallback for nuanced borderline text
        if use_llm_fallback and self.gemini_client is not None and len(text) > 30:
            return self._llm_classify(text, question_context)

        return InjectionDetectionResult(
            is_suspicious=False,
            risk_level=InjectionRiskLevel.LOW,
            detected_patterns=[],
            explanation="No adversarial patterns or prompt injections detected.",
            flag_for_review=False,
        )

    def _scan_patterns(self, text: str) -> Tuple[List[str], List[str]]:
        """Scan text against all adversarial signature patterns."""
        detected: List[str] = []
        snippets: List[str] = []
        all_rules = _OVERRIDE_PATTERNS + _SCORE_MANIPULATION_PATTERNS + _LEAK_PATTERNS + _DELIMITER_PATTERNS

        for pattern, label in all_rules:
            matches = re.findall(pattern, text)
            if matches:
                detected.append(label)
                # Capture matched substring
                for m in re.finditer(pattern, text):
                    snippets.append(m.group(0))

        return list(dict.fromkeys(detected)), snippets

    def _is_academic_discussion(self, text: str, question_context: Optional[str]) -> bool:
        """Determine if the submission or question is discussing cybersecurity or AI concepts."""
        combined = f"{question_context or ''} {text}".lower()
        return any(re.search(ind, combined) for ind in _ACADEMIC_SECURITY_INDICATORS)

    def _is_merely_descriptive(self, text: str, matched_snippets: List[str]) -> bool:
        """Check if matched phrases are quoted or described as passive/third-person examples."""
        descriptive_prefixes = [
            r"example\s+of",
            r"attacker\s+(might\s+say|attempts\s+to|tries\s+to|seeks\s+to|inputs)",
            r"such\s+as",
            r"phrase",
            r"technique\s+to",
            r"concept\s+of",
            r"vulnerability\s+where",
            r"defined\s+as",
        ]
        prefix_pattern = rf"\b({'|'.join(descriptive_prefixes)})\s+[\"']?"

        for snip in matched_snippets:
            escaped = re.escape(snip)
            # Enclosed in quotes
            if re.search(rf'["\'].*?{escaped}.*?["\']', text, re.IGNORECASE):
                return True
            # Preceded by descriptive context
            if re.search(f"{prefix_pattern}.*?{escaped}", text, re.IGNORECASE):
                return True
        return False

    def _llm_classify(self, text: str, question_context: Optional[str]) -> InjectionDetectionResult:
        """Perform secondary LLM-based verification for ambiguous submissions."""
        prompt = prompts.build_injection_detection_prompt(text, question_context)
        try:
            return self.gemini_client.generate_structured(
                prompt=prompt,
                response_schema=InjectionDetectionResult,
                system_instruction=prompts.SYSTEM_INJECTION_ANALYZER,
            )
        except Exception as exc:
            logger.warning("LLM injection fallback classification failed: %s", exc)
            return InjectionDetectionResult(
                is_suspicious=False,
                risk_level=InjectionRiskLevel.LOW,
                detected_patterns=[],
                explanation="Standard pattern check clear.",
                flag_for_review=False,
            )
