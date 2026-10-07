"""Language auto-detection (REQ-CSD-2). Score-based, with a parse-based tie-break."""
import ast
import re

_JAVA = [
    r"^\s*package\s+[\w.]+\s*;", r"^\s*import\s+(static\s+)?[\w.*]+\s*;", r"System\.(out|err)\.print",
    r"\b(public|private|protected)\s+(static\s+)?(final\s+)?[\w<>\[\],? ]+\s+\w+\s*\(",
    r"\b(class|interface|enum)\s+\w+[^\n{]*\{", r"\bnew\s+[A-Z]\w*\s*[(<\[]", r"\bvoid\b", r"@Override",
    r"\b(String|int|boolean|double|long)\s+\w+\s*(=|;|,|\))",
]
_PY = [
    r"^\s*def\s+\w+\s*\(.*\)\s*(->\s*[^:]+)?:", r"^\s*class\s+\w+\s*(\(.*\))?\s*:", r"^\s*from\s+[\w.]+\s+import\s+",
    r"^\s*import\s+[\w.]+(\s+as\s+\w+)?\s*$", r"\bself\b", r"^\s*(elif|else|try|except|finally|with)\b.*:\s*$",
    r"^\s*@\w+", r"\bprint\(", r"\bNone\b|\bTrue\b|\bFalse\b", r"^\s*(for|while|if)\b.*:\s*$",
]


def detect_language(code: str) -> str:
    j = sum(len(re.findall(p, code, re.M)) for p in _JAVA)
    p = sum(len(re.findall(p_, code, re.M)) for p_ in _PY)
    if j > p:
        return "java"
    if p > j:
        return "python"
    try:
        ast.parse(code)
        return "python"
    except SyntaxError:
        return "java" if ";" in code or "{" in code else "python"
