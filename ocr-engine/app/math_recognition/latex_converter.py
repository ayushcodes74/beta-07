"""LaTeX conversion and syntactic validation service for mathematical expressions."""

import logging
import re
from typing import List, Optional, Tuple

from app.math_recognition.config import MathRecognitionConfig, DEFAULT_MATH_CONFIG

logger = logging.getLogger(__name__)

# Unicode character maps to LaTeX
UNICODE_SUPER_MAP = {
    "⁰": "^{0}",
    "¹": "^{1}",
    "²": "^{2}",
    "³": "^{3}",
    "⁴": "^{4}",
    "⁵": "^{5}",
    "⁶": "^{6}",
    "⁷": "^{7}",
    "⁸": "^{8}",
    "⁹": "^{9}",
    "⁺": "^{+}",
    "⁻": "^{-}",
    "ⁿ": "^{n}",
    "ˣ": "^{x}",
    "ʸ": "^{y}",
}

UNICODE_SUB_MAP = {
    "₀": "_{0}",
    "₁": "_{1}",
    "₂": "_{2}",
    "₃": "_{3}",
    "₄": "_{4}",
    "₅": "_{5}",
    "₆": "_{6}",
    "₇": "_{7}",
    "₈": "_{8}",
    "₉": "_{9}",
    "ᵢ": "_{i}",
    "ⱼ": "_{j}",
    "ₖ": "_{k}",
    "ₙ": "_{n}",
}

UNICODE_MATH_MAP = {
    "π": "\\pi",
    "θ": "\\theta",
    "λ": "\\lambda",
    "α": "\\alpha",
    "β": "\\beta",
    "γ": "\\gamma",
    "δ": "\\delta",
    "ε": "\\epsilon",
    "μ": "\\mu",
    "σ": "\\sigma",
    "ω": "\\omega",
    "φ": "\\phi",
    "∑": "\\sum",
    "∫": "\\int",
    "∂": "\\partial",
    "√": "\\sqrt",
    "∞": "\\infty",
    "±": "\\pm",
    "≈": "\\approx",
    "≠": "\\neq",
    "≤": "\\le",
    "≥": "\\ge",
    "×": "\\times",
    "÷": "\\div",
    "·": "\\cdot",
}


class LaTeXConverter:
    """Converts recognized mathematical representations to structured LaTeX and checks syntax."""

    def __init__(self, config: Optional[MathRecognitionConfig] = None) -> None:
        self.config = config or DEFAULT_MATH_CONFIG

    @classmethod
    def convert_to_latex(cls, raw_text: str) -> Tuple[str, List[str]]:
        """Convert a recognized mathematical text expression into structured LaTeX.

        Preserves exact student expression structure without altering mathematical semantics.

        Args:
            raw_text: Raw OCR transcript or mathematical string.

        Returns:
            Tuple of (latex_string, warnings_list).
        """
        if not raw_text or not raw_text.strip():
            return "", []

        warnings: List[str] = []
        text = raw_text.strip()

        # If text is already valid LaTeX produced by a dedicated model like pix2tex, preserve it
        if "\\" in text and ("\\frac" in text or "\\sqrt" in text or "\\int" in text or "\\sum" in text):
            valid, err = cls.validate_delimiters(text)
            if not valid:
                warnings.append(f"Unbalanced LaTeX delimiters: {err}")
            return text, warnings

        # 1. Map Unicode mathematical symbols and Greek letters
        for u_char, latex_repl in UNICODE_MATH_MAP.items():
            if u_char in text:
                text = text.replace(u_char, f" {latex_repl} ")

        # 2. Map Unicode superscripts and subscripts
        for u_char, latex_repl in UNICODE_SUPER_MAP.items():
            text = text.replace(u_char, latex_repl)
        for u_char, latex_repl in UNICODE_SUB_MAP.items():
            text = text.replace(u_char, latex_repl)

        # 3. Square roots: sqrt(...) or \sqrt(...) or √(x)
        text = re.sub(r"(?:\\sqrt|sqrt)\s*\(([^()]+)\)", r"\\sqrt{\1}", text)

        # 4. Fractions: (num)/(den) -> \frac{num}{den}
        text = re.sub(r"\(([^()]+)\)\s*/\s*\(([^()]+)\)", r"\\frac{\1}{\2}", text)
        text = re.sub(r"\(([^()]+)\)\s*/\s*([a-zA-Z0-9]+)", r"\\frac{\1}{\2}", text)
        text = re.sub(r"([a-zA-Z0-9]+)\s*/\s*\(([^()]+)\)", r"\\frac{\1}{\2}", text)
        # Simple word fractions: a/b -> \frac{a}{b}
        text = re.sub(r"\b([a-zA-Z0-9]+)\s*/\s*([a-zA-Z0-9]+)\b", r"\\frac{\1}{\2}", text)

        # 5. Superscripts: x^2 -> x^{2}
        text = re.sub(r"([a-zA-Z0-9_\)\}\]])\^([a-zA-Z0-9])(?![^{]*\})", r"\1^{\2}", text)

        # 6. Subscripts: x_1 -> x_{1}
        text = re.sub(r"([a-zA-Z0-9\)\}\]])_([a-zA-Z0-9])(?![^{]*\})", r"\1_{\2}", text)

        # 7. Common Operators
        text = re.sub(r"\s*\+-\s*", r" \\pm ", text)
        text = re.sub(r"\s*!=\s*", r" \\neq ", text)
        text = re.sub(r"\s*<=\s*", r" \\le ", text)
        text = re.sub(r"\s*>=\s*", r" \\ge ", text)

        # Clean multiple spaces
        text = re.sub(r"[ \t]+", " ", text).strip()

        # Syntax / Delimiter Validation
        is_balanced, delim_err = cls.validate_delimiters(text)
        if not is_balanced:
            warnings.append(f"Unbalanced mathematical delimiters in LaTeX: {delim_err}")

        # Optional SymPy structural validation
        sympy_valid, sympy_msg = cls._validate_with_sympy(text)
        if sympy_msg:
            warnings.append(sympy_msg)

        return text, warnings

    @classmethod
    def validate_delimiters(cls, latex_str: str) -> Tuple[bool, Optional[str]]:
        """Check matching brackets and braces in LaTeX string."""
        stack: List[Tuple[str, int]] = []
        matching = {")": "(", "}": "{", "]": "["}

        for idx, ch in enumerate(latex_str):
            if ch in ("(", "{", "["):
                stack.append((ch, idx))
            elif ch in (")", "}", "]"):
                if not stack:
                    return False, f"Unexpected closing delimiter '{ch}' at position {idx}"
                top, _ = stack.pop()
                if top != matching[ch]:
                    return False, f"Mismatched delimiter '{top}' closed by '{ch}' at position {idx}"

        if stack:
            unclosed, pos = stack[-1]
            return False, f"Unclosed delimiter '{unclosed}' opened at position {pos}"

        return True, None

    @classmethod
    def _validate_with_sympy(cls, latex_str: str) -> Tuple[bool, Optional[str]]:
        """Optionally check syntax with SymPy if installed (WITHOUT solving or grading)."""
        try:
            import sympy
            from sympy.parsing.latex import parse_latex

            # Only attempt on complete formulas without ellipses or wildcards
            if "..." in latex_str or "\\ldots" in latex_str:
                return True, None

            # Attempt parsing
            parse_latex(latex_str)
            return True, None
        except ImportError:
            # SymPy not installed: non-fatal, return neutral
            return True, None
        except Exception as e:
            logger.debug("SymPy parse notice for '%s': %s", latex_str, e)
            return False, f"Expression structure may be mathematically non-standard: {e}"

