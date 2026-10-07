"""Deterministic smell rules driven purely by measured metrics (REQ-CSD-8 and friends).
These always run, so the tool is useful even when the LLM is unavailable."""
from .metrics import Metrics

LONG_PARAMS = 5
NEST_MED, NEST_HIGH = 4, 5
CC_MED, CC_HIGH = 10, 20
GOD_METHODS, GOD_FIELDS = 15, 12
COUPLING_MED, COUPLING_HIGH = 8, 12


def _label(f) -> str:
    return f"{f.owner}.{f.name}" if f.owner else f.name


def static_smells(m: Metrics, long_method_lines: int) -> list:
    out = []

    def add(cat, sev, start, end, target, desc, pattern, suggestion):
        out.append({"category": cat, "severity": sev, "start_line": start, "end_line": end, "target": target,
                    "description": desc, "refactoring_pattern": pattern, "suggestion": suggestion,
                    "source": "static"})

    for f in m.functions:
        n = _label(f)
        if f.line_count > long_method_lines:
            sev = "high" if f.line_count > 2 * long_method_lines else "medium"
            add("long_method", sev, f.start_line, f.end_line, n,
                f"`{n}` is {f.line_count} lines long (threshold: {long_method_lines}).", "Extract Method",
                f"Split `{n}` into smaller single-responsibility functions. Group related statements, give each "
                f"group a descriptive name, and let `{f.name}` read as a short sequence of those calls.")
        if f.param_count > LONG_PARAMS:
            add("long_parameter_list", "medium", f.start_line, f.start_line, n,
                f"`{n}` takes {f.param_count} parameters.", "Introduce Parameter Object",
                f"Bundle the related parameters of `{n}` into a small object or dataclass, or split the function "
                f"if the parameters serve different purposes.")
        if f.max_nesting >= NEST_MED:
            sev = "high" if f.max_nesting >= NEST_HIGH else "medium"
            add("deep_nesting", sev, f.start_line, f.end_line, n,
                f"`{n}` nests control flow {f.max_nesting} levels deep.", "Replace Nested Conditional with Guard Clauses",
                f"Flatten `{n}` using early returns/guard clauses, or extract the inner blocks into helper methods.")
        if f.cyclomatic > CC_MED:
            sev = "high" if f.cyclomatic > CC_HIGH else "medium"
            add("high_complexity", sev, f.start_line, f.end_line, n,
                f"`{n}` has an estimated cyclomatic complexity of {f.cyclomatic}.", "Decompose Conditional",
                f"Reduce branching in `{n}` by extracting conditions into well-named helpers or replacing "
                f"type/flag-based branching with polymorphism or a lookup table.")

    for c in m.classes:
        if c.method_count > GOD_METHODS or c.field_count > GOD_FIELDS:
            sev = "high" if c.method_count > 2 * GOD_METHODS else "medium"
            add("god_class", sev, c.start_line, c.end_line, c.name,
                f"`{c.name}` has {c.method_count} methods and {c.field_count} fields, suggesting too many "
                f"responsibilities.", "Extract Class",
                f"Identify groups of fields and methods in `{c.name}` that change together and move each group "
                f"into its own class, keeping `{c.name}` as a thin coordinator.")
        if c.coupling >= COUPLING_MED:
            sev = "high" if c.coupling >= COUPLING_HIGH else "medium"
            add("high_coupling", sev, c.start_line, c.end_line, c.name,
                f"`{c.name}` depends on {c.coupling} distinct external types.", "Introduce Facade / Dependency Inversion",
                f"Reduce what `{c.name}` knows about: depend on narrow interfaces, inject collaborators, or hide "
                f"clusters of related dependencies behind a facade.")
    return out
