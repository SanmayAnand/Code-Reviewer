"""Assemble the review report: validate/normalise LLM output, merge with static findings, summarise."""
import re
from .prompts import CATEGORIES

SEVERITIES = ("high", "medium", "low")
_RANK = {s: i for i, s in enumerate(SEVERITIES)}
MAX_SUGGESTION_WORDS = 100  # REQ-RSG-4
DISCLAIMER = ("These findings and suggestions are AI-assisted recommendations, not guaranteed-correct fixes. "
              "Review them critically before applying them to production code.")
NO_SUGGESTION = "No suggestion is available for this issue."


def _trim_words(text: str, limit: int = MAX_SUGGESTION_WORDS) -> str:
    words = text.split()
    return text.strip() if len(words) <= limit else " ".join(words[:limit]).rstrip(".,;:") + "…"


def _int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def normalise_llm_smells(raw, total_lines: int) -> list:
    items = raw.get("smells") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        desc = str(it.get("description") or "").strip()
        if not desc:
            continue
        cat = str(it.get("category") or "other").strip().lower()
        sev = str(it.get("severity") or "medium").strip().lower()
        start = min(max(_int(it.get("start_line"), 1), 1), max(total_lines, 1))
        end = min(max(_int(it.get("end_line"), start), 1), max(total_lines, 1))
        if end < start:
            start, end = end, start
        sugg = str(it.get("suggestion") or "").strip()
        out.append({
            "category": cat if cat in CATEGORIES else "other",
            "severity": sev if sev in SEVERITIES else "medium",
            "start_line": start, "end_line": end,
            "target": str(it.get("target") or "").strip(),
            "description": desc,
            "refactoring_pattern": str(it.get("refactoring_pattern") or "").strip(),
            "suggestion": _trim_words(sugg) if sugg else "",
            "source": "ai",
        })
    return out


def _overlaps(a, b) -> bool:
    return a["start_line"] <= b["end_line"] and b["start_line"] <= a["end_line"]


def merge_smells(static: list, ai: list) -> list:
    """Static findings are authoritative for measured facts; the AI enriches them or adds new ones.
    AI findings are only reconciled against static ones, never against each other."""
    merged = [dict(s) for s in static]
    extra = []
    for a in ai:
        twin = next((s for s in merged if s["category"] == a["category"] and _overlaps(s, a)
                     and (not a["target"] or not s["target"]
                          or a["target"].split(".")[-1] == s["target"].split(".")[-1])), None)
        if twin:
            if a["suggestion"]:  # prefer the AI's tailored wording but keep the measured description
                twin["suggestion"] = a["suggestion"]
                twin["refactoring_pattern"] = a["refactoring_pattern"] or twin["refactoring_pattern"]
                twin["source"] = "static+ai"
        else:
            extra.append(a)
    return merged + extra


def build_report(language: str, metrics: dict, static: list, ai: list, llm: dict, warnings: list) -> dict:
    smells = merge_smells(static, ai)
    for s in smells:
        s["suggestion_available"] = bool(s["suggestion"])  # REQ-RSG-5
        if not s["suggestion"]:
            s["suggestion"] = NO_SUGGESTION
    smells.sort(key=lambda s: (_RANK[s["severity"]], s["start_line"]))
    for i, s in enumerate(smells, 1):
        s["id"] = i
    summary = {"total": len(smells), **{sev: sum(1 for s in smells if s["severity"] == sev) for sev in SEVERITIES}}
    return {"language": language, "total_lines": metrics["total_lines"], "summary": summary, "smells": smells,
            "metrics": metrics, "llm": llm, "warnings": warnings, "disclaimer": DISCLAIMER}
