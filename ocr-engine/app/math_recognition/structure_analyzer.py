"""Mathematical structure analyzer identifying fractions, powers, roots, and matrices."""

import logging
import re
from typing import Any, Dict, List

from app.math_recognition.schemas import StructureDetection

logger = logging.getLogger(__name__)


class MathStructureAnalyzer:
    """Detects and decomposes mathematical structures (fractions, exponents, roots, integrals)."""

    @classmethod
    def analyze_structures(cls, expression: str) -> List[StructureDetection]:
        """Parse structured mathematical components from a LaTeX expression.

        Args:
            expression: LaTeX mathematical expression string.

        Returns:
            List of StructureDetection models.
        """
        if not expression:
            return []

        structures: List[StructureDetection] = []

        # 1. Fractions: \frac{numerator}{denominator}
        frac_matches = re.finditer(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", expression)
        for m in frac_matches:
            num = m.group(1).strip()
            den = m.group(2).strip()
            structures.append(
                StructureDetection(
                    structure_type="fraction",
                    latex_representation=m.group(0),
                    components={"numerator": num, "denominator": den},
                )
            )

        # 2. Square Roots & Radicals: \sqrt[n]{radicand} or \sqrt{radicand}
        sqrt_matches = re.finditer(r"\\sqrt(?:\[([^\[\]]+)\])?\s*\{([^{}]+)\}", expression)
        for m in sqrt_matches:
            degree = m.group(1) or "2"
            radicand = m.group(2).strip()
            structures.append(
                StructureDetection(
                    structure_type="radical",
                    latex_representation=m.group(0),
                    components={"degree": degree.strip(), "radicand": radicand},
                )
            )

        # 3. Superscripts / Powers: base^{exponent} or base^char
        pow_matches = re.finditer(r"([a-zA-Z0-9_\)\}\]]+)\^(\{([^{}]+)\}|[a-zA-Z0-9])", expression)
        for m in pow_matches:
            base = m.group(1).strip()
            exponent = (m.group(3) if m.group(3) else m.group(2)).strip()
            structures.append(
                StructureDetection(
                    structure_type="superscript",
                    latex_representation=m.group(0),
                    components={"base": base, "exponent": exponent},
                )
            )

        # 4. Subscripts: base_{index} or base_char
        sub_matches = re.finditer(r"([a-zA-Z0-9\)\}\]]+)_(\{([^{}]+)\}|[a-zA-Z0-9])", expression)
        for m in sub_matches:
            base = m.group(1).strip()
            subscript = (m.group(3) if m.group(3) else m.group(2)).strip()
            structures.append(
                StructureDetection(
                    structure_type="subscript",
                    latex_representation=m.group(0),
                    components={"base": base, "subscript": subscript},
                )
            )

        # 5. Integrals: \int or \int_{a}^{b}
        if "\\int" in expression:
            int_match = re.search(r"\\int(?:_\{([^{}]+)\})?(?:\^\{([^{}]+)\})?", expression)
            lower = int_match.group(1) if int_match and int_match.group(1) else None
            upper = int_match.group(2) if int_match and int_match.group(2) else None
            structures.append(
                StructureDetection(
                    structure_type="integral",
                    latex_representation="\\int",
                    components={"lower_limit": lower, "upper_limit": upper},
                )
            )

        # 6. Summations: \sum or \sum_{i=1}^{n}
        if "\\sum" in expression:
            sum_match = re.search(r"\\sum(?:_\{([^{}]+)\})?(?:\^\{([^{}]+)\})?", expression)
            lower = sum_match.group(1) if sum_match and sum_match.group(1) else None
            upper = sum_match.group(2) if sum_match and sum_match.group(2) else None
            structures.append(
                StructureDetection(
                    structure_type="summation",
                    latex_representation="\\sum",
                    components={"lower_limit": lower, "upper_limit": upper},
                )
            )

        # 7. Matrices: \begin{matrix} ... \end{matrix} or \begin{pmatrix}
        matrix_match = re.search(r"\\begin\{([a-z]*matrix)\}(.+?)\\end\{\1\}", expression, re.DOTALL)
        if matrix_match:
            mat_type = matrix_match.group(1)
            body = matrix_match.group(2).strip()
            rows = [r.strip() for r in body.split("\\\\") if r.strip()]
            num_rows = len(rows)
            num_cols = len([c.strip() for c in rows[0].split("&")]) if rows else 0
            structures.append(
                StructureDetection(
                    structure_type="matrix",
                    latex_representation=matrix_match.group(0),
                    components={"matrix_type": mat_type, "rows": num_rows, "cols": num_cols},
                )
            )

        # 8. Equations: LHS = RHS or LHS \neq RHS
        if "=" in expression or "\\neq" in expression:
            sep = "=" if "=" in expression else "\\neq"
            parts = expression.split(sep, 1)
            structures.append(
                StructureDetection(
                    structure_type="equation",
                    latex_representation=expression,
                    components={
                        "relation": sep,
                        "lhs": parts[0].strip(),
                        "rhs": parts[1].strip() if len(parts) > 1 else "",
                    },
                )
            )

        return structures

