"""Static pre-processor. Fully decoupled from the LLM prompt templates (SRS 5.4)."""
from dataclasses import dataclass, field, asdict
from typing import List


class ParseError(Exception):
    """Raised when a snippet cannot be parsed in the selected language (REQ-CSD-3)."""


@dataclass
class FunctionMetrics:
    name: str
    start_line: int
    end_line: int
    line_count: int
    param_count: int
    cyclomatic: int
    max_nesting: int
    owner: str = ""  # enclosing class, if any


@dataclass
class ClassMetrics:
    name: str
    start_line: int
    end_line: int
    method_count: int
    field_count: int
    coupling: int
    coupled_types: List[str] = field(default_factory=list)


@dataclass
class Metrics:
    language: str
    total_lines: int
    functions: List[FunctionMetrics]
    classes: List[ClassMetrics]

    def to_dict(self):
        return asdict(self)


def extract_metrics(code: str, language: str) -> Metrics:
    if language == "python":
        from .python_metrics import extract
    elif language == "java":
        from .java_metrics import extract
    else:
        raise ParseError(f"Unsupported language: {language}")
    return extract(code)
