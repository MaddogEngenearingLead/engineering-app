"""Extract complete drawing size expressions without matching partial fractions."""
import re

_NUMBER = r"(?:\d+\s*[- ]\s*\d+\s*/\s*\d+|\d+\s*/\s*\d+|\d+(?:\.\d+)?|(?:\d+\s*)?[¼½¾])"
_DIMENSION = rf"{_NUMBER}\s*[\"”″]"
SIZE_EXPRESSION = re.compile(
    rf"(?<![\w./-])({_DIMENSION}(?:\s*[xX×]\s*{_DIMENSION})*)(?![\w./])"
)


def sizes_in(text: str) -> list[str]:
    sizes = []
    for match in SIZE_EXPRESSION.finditer(text):
        size = match.group(1).replace("”", '"').replace("″", '"').replace("×", "x")
        size = re.sub(r"\s*/\s*", "/", size)
        size = re.sub(r'\s*"\s*', '"', size)
        size = re.sub(r"\s*[xX]\s*", "x", size)
        sizes.append(size)
    return sizes
