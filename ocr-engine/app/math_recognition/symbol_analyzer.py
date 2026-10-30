"""Mathematical symbol recognition and ambiguity analysis service."""

import logging
import re
from typing import List, Set, Tuple

from app.math_recognition.schemas import SymbolDetection

logger = logging.getLogger(__name__)

# Symbol classification tables
OPERATOR_SYMBOLS = {
    "+": "addition",
    "-": "subtraction",
    "*": "multiplication",
    "\\times": "multiplication",
    "\\cdot": "multiplication",
    "/": "division",
    "\\div": "division",
    "=": "equals",
    "\\neq": "not_equal",
    "!=": "not_equal",
    "<": "less_than",
    ">": "greater_than",
    "\\le": "less_equal",
    "\\ge": "greater_equal",
    "<=": "less_equal",
    ">=": "greater_equal",
    "\\pm": "plus_minus",
    "\\approx": "approximately_equal",
    "\\equiv": "identical_to",
}

GREEK_SYMBOLS = {
    "\\pi": "pi",
    "\\theta": "theta",
    "\\lambda": "lambda",
    "\\alpha": "alpha",
    "\\beta": "beta",
    "\\gamma": "gamma",
    "\\delta": "delta",
    "\\epsilon": "epsilon",
    "\\mu": "mu",
    "\\sigma": "sigma",
    "\\omega": "omega",
    "\\phi": "phi",
    "\\psi": "psi",
    "\\Delta": "Delta",
    "\\Sigma": "Sigma",
}

CALCULUS_SYMBOLS = {
    "\\int": "integral",
    "\\iint": "double_integral",
    "\\oint": "contour_integral",
    "\\sum": "summation",
    "\\prod": "product",
    "\\partial": "partial_derivative",
    "\\nabla": "gradient",
    "\\lim": "limit",
    "\\infty": "infinity",
}

# Known visual ambiguities in student handwritten math
AMBIGUITY_MAP = {
    "0": ["O (uppercase O)", "0 (zero)", "\\theta (theta)"],
    "O": ["0 (zero)", "O (uppercase O)"],
    "1": ["l (lowercase L)", "1 (one)", "| (vertical bar)"],
    "l": ["1 (one)", "l (lowercase L)", "| (vertical bar)"],
    "|": ["1 (one)", "| (vertical bar)"],
    "x": ["\\times (multiplication)", "x (variable)"],
    "\\times": ["x (variable)", "\\times (multiplication)"],
    "+": ["t (letter t)", "+ (plus)"],
    "t": ["+ (plus)", "t (letter t)"],
    "-": ["_ (subscript / underscore)", "- (minus / dash)"],
    "_": ["- (minus)", "_ (subscript)"],
    "v": ["\\nu (Greek nu)", "v (variable)"],
    "\\nu": ["v (variable)", "\\nu (Greek nu)"],
    "p": ["\\rho (Greek rho)", "p (variable)"],
    "\\rho": ["p (variable)", "\\rho (Greek rho)"],
    "w": ["\\omega (Greek omega)", "w (variable)"],
    "\\omega": ["w (variable)", "\\omega (Greek omega)"],
    "u": ["\\mu (Greek mu)", "u (variable)"],
    "\\mu": ["u (variable)", "\\mu (Greek mu)"],
    "E": ["\\sum (summation)", "E (variable)"],
}


class MathSymbolAnalyzer:
    """Extracts, categorizes, and audits ambiguous mathematical symbols in expressions."""

    @classmethod
    def analyze_symbols(cls, expression: str) -> Tuple[List[SymbolDetection], List[str]]:
        """Identify mathematical symbols and flag visual ambiguities without altering the expression.

        Args:
            expression: LaTeX or mathematical text string.

        Returns:
            Tuple of (detected_symbols_list, ambiguity_warnings_list).
        """
        if not expression:
            return [], []

        detections: List[SymbolDetection] = []
        warnings: List[str] = []
        seen_symbols: Set[str] = set()

        # 1. Match LaTeX control sequences (e.g. \pi, \int, \frac, \le)
        latex_commands = re.findall(r"\\[a-zA-Z]+", expression)
        for cmd in latex_commands:
            cat = "symbol"
            if cmd in OPERATOR_SYMBOLS:
                cat = "operator"
            elif cmd in GREEK_SYMBOLS:
                cat = "greek"
            elif cmd in CALCULUS_SYMBOLS:
                cat = "calculus"
            elif cmd in ("\\sqrt", "\\frac", "\\matrix", "\\pmatrix"):
                cat = "structure"

            is_ambig = cmd in AMBIGUITY_MAP
            alts = AMBIGUITY_MAP.get(cmd, [])

            if cmd not in seen_symbols:
                seen_symbols.add(cmd)
                detections.append(
                    SymbolDetection(
                        symbol=cmd,
                        category=cat,
                        is_ambiguous=is_ambig,
                        suggested_alternatives=alts,
                    )
                )
                if is_ambig:
                    warnings.append(
                        f"Potentially ambiguous mathematical symbol '{cmd}' detected. Possible alternatives: {', '.join(alts)}."
                    )

        # 2. Match standard ASCII mathematical operators and single-character symbols
        # Remove LaTeX commands first to avoid double counting
        clean_exp = re.sub(r"\\[a-zA-Z]+", " ", expression)

        for char in clean_exp:
            if char.isspace() or char in ("{", "}"):
                continue

            if char in seen_symbols:
                continue

            seen_symbols.add(char)
            cat = "variable"
            if char in OPERATOR_SYMBOLS:
                cat = "operator"
            elif char in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
                cat = "number"
            elif char in ("(", ")", "[", "]", "|"):
                cat = "delimiter"
            elif char in ("^", "_"):
                cat = "structure"

            is_ambig = char in AMBIGUITY_MAP
            alts = AMBIGUITY_MAP.get(char, [])

            detections.append(
                SymbolDetection(
                    symbol=char,
                    category=cat,
                    is_ambiguous=is_ambig,
                    suggested_alternatives=alts,
                )
            )

            if is_ambig:
                warnings.append(
                    f"Ambiguous handwritten glyph '{char}' detected. Verify whether student intended: {', '.join(alts)}."
                )

        return detections, warnings

