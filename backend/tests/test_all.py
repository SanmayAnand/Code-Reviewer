import pytest
from fastapi.testclient import TestClient
from app import llm
from app.config import Settings
from app.db import Database
from app.language import detect_language
from app.main import create_app
from app.metrics import ParseError, extract_metrics
from app.report import MAX_SUGGESTION_WORDS, NO_SUGGESTION, normalise_llm_smells, build_report
from app.static_smells import static_smells

PY_LONG = "def big(a, b, c, d, e, f):\n" + "\n".join(f"    x{i} = {i}" for i in range(45)) + "\n    return a\n"
PY_NEST = """def deep(a):
    for i in a:
        if i:
            while i:
                for j in i:
                    pass
"""
JAVA = """public class Shop extends Base {
    private int a, b;
    private Repo repo = new Repo();
    public int calc(int x, String s) {
        int r = 0;
        for (int i = 0; i < x; i++) {
            if (i > 2 && s != null) { r += Util.twice(i); } else if (i == 1) { r--; }
        }
        return r;
    }
}
"""


def settings(kind="openai", provider="groq", key="k", limit=20, tmp="x"):
    return Settings(provider=provider, kind=kind, base_url="http://x", model="m", api_key=key, timeout=2,
                    long_method_lines=40, max_lines=2000, max_chars=200000, daily_limit=limit, db_path=":memory:")


def client(**kw):
    s = settings(**kw)
    return TestClient(create_app(s, Database(":memory:"))), s


H = {"X-Session-Id": "session-abcdef12"}


# ---- metrics (REQ-CSD-4/5) ----
def test_python_function_metrics():
    m = extract_metrics(PY_NEST, "python")
    f = m.functions[0]
    assert (f.name, f.param_count, f.max_nesting, f.cyclomatic) == ("deep", 1, 4, 5)


def test_python_class_metrics_and_coupling():
    code = "from lib import Client\nclass A(Base):\n    x = 1\n    def __init__(self):\n        self.c = Client()\n        self.d = Other()\n"
    c = extract_metrics(code, "python").classes[0]
    assert (c.method_count, c.field_count) == (1, 3)
    assert set(c.coupled_types) == {"Client", "Other", "Base"}


def test_java_metrics():
    m = extract_metrics(JAVA, "java")
    f = m.functions[0]
    assert (f.name, f.param_count, f.cyclomatic, f.max_nesting, f.start_line, f.end_line) == ("calc", 2, 5, 2, 4, 10)
    c = m.classes[0]
    assert (c.method_count, c.field_count) == (1, 3) and set(c.coupled_types) == {"Base", "Repo", "Util"}


def test_java_bare_method_keeps_line_numbers():
    f = extract_metrics("int add(int a, int b) {\n  return a+b;\n}", "java").functions[0]
    assert (f.start_line, f.end_line, f.owner) == (1, 3, "")


# ---- parse errors (REQ-CSD-3) ----
def test_parse_errors():
    with pytest.raises(ParseError):
        extract_metrics("def f(:\n  pass", "python")
    with pytest.raises(ParseError):
        extract_metrics("public class { int x = ; }", "java")


# ---- language detection (REQ-CSD-2) ----
def test_detect_language():
    assert detect_language(PY_LONG) == "python"
    assert detect_language(JAVA) == "java"


# ---- static smells (REQ-CSD-8) ----
def test_long_method_flagged_at_threshold():
    m = extract_metrics(PY_LONG, "python")
    cats = {s["category"] for s in static_smells(m, 40)}
    assert {"long_method", "long_parameter_list"} <= cats
    assert "long_method" not in {s["category"] for s in static_smells(m, 100)}


# ---- report building (REQ-RSG-4/5, REQ-RRG-4/5) ----
def test_report_normalisation():
    raw = {"smells": [{"category": "weird", "severity": "extreme", "start_line": 99, "end_line": 1,
                       "description": "d", "suggestion": " ".join(["w"] * 300)},
                      {"description": "no suggestion here", "start_line": 1, "end_line": 1}, "junk", {"x": 1}]}
    out = normalise_llm_smells(raw, 10)
    assert len(out) == 2
    assert out[0]["category"] == "other" and out[0]["severity"] == "medium"
    assert (out[0]["start_line"], out[0]["end_line"]) == (1, 10)
    assert len(out[0]["suggestion"].split()) <= MAX_SUGGESTION_WORDS
    rep = build_report("python", {"total_lines": 10}, [], out, {}, [])
    assert rep["smells"][1]["suggestion"] == NO_SUGGESTION and not rep["smells"][1]["suggestion_available"]
    assert rep["summary"]["total"] == 2


def test_zero_smells_report():
    assert build_report("python", {"total_lines": 1}, [], [], {}, [])["summary"]["total"] == 0


# ---- API flow ----
def fake_llm(result=None, exc=None):
    async def _f(*a, **k):
        if exc:
            raise exc
        return result
    return _f


def test_review_with_ai_history_and_quota(monkeypatch):
    c, _ = client(limit=2)
    ai = {"smells": [{"category": "duplicated_code", "severity": "low", "start_line": 1, "end_line": 5,
                      "target": "big", "description": "dupe", "refactoring_pattern": "Extract Method",
                      "suggestion": "Extract the shared block from big."}]}
    monkeypatch.setattr(llm, "analyze", fake_llm(ai))
    r = c.post("/api/review", json={"code": PY_LONG, "language": "auto"}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    cats = {s["category"] for s in body["report"]["smells"]}
    assert {"long_method", "duplicated_code"} <= cats and body["id"]
    # history: list, reopen without LLM, delete (REQ-RH-2/3/4)
    monkeypatch.setattr(llm, "analyze", fake_llm(exc=AssertionError("must not call LLM")))
    assert len(c.get("/api/history", headers=H).json()["items"]) == 1
    assert c.get(f"/api/history/{body['id']}", headers=H).json()["report"]["summary"]["total"] >= 2
    assert c.get(f"/api/history/{body['id']}", headers={"X-Session-Id": "other-session-1"}).status_code == 404
    assert c.delete(f"/api/history/{body['id']}", headers=H).status_code == 200
    assert c.get("/api/history", headers=H).json()["items"] == []
    # quota (SRS 5.5)
    monkeypatch.setattr(llm, "analyze", fake_llm({"smells": []}))
    assert c.post("/api/review", json={"code": PY_NEST}, headers=H).status_code == 200
    assert c.post("/api/review", json={"code": PY_NEST}, headers=H).status_code == 429


def test_timeout_falls_back_and_is_not_persisted(monkeypatch):
    c, _ = client()
    monkeypatch.setattr(llm, "analyze", fake_llm(exc=llm.LLMTimeout("slow")))
    body = c.post("/api/review", json={"code": PY_LONG}, headers=H).json()
    assert body["report"]["llm"]["status"] == "timeout" and body["report"]["warnings"][0]["retry"] is True
    assert body["id"] is None and any(s["category"] == "long_method" for s in body["report"]["smells"])
    assert c.get("/api/history", headers=H).json()["items"] == []


def test_validation_errors():
    c, _ = client(kind="none", provider="none", key="")
    assert c.post("/api/review", json={"code": "def f(:"}, headers=H).status_code == 422
    assert c.post("/api/review", json={"code": "  "}, headers=H).status_code == 422
    assert c.post("/api/review", json={"code": "x=1\n" * 2001}, headers=H).status_code == 413
    assert c.post("/api/review", json={"code": "x=1"}).status_code == 400
    assert c.post("/api/review", json={"code": "x=1", "language": "cobol"}, headers=H).status_code == 422


def test_no_llm_mode_still_reports():
    c, _ = client(kind="none", provider="none", key="")
    body = c.post("/api/review", json={"code": PY_LONG}, headers=H).json()
    assert body["report"]["summary"]["total"] >= 1 and body["id"]


def test_save_code_is_opt_in():
    c, _ = client(kind="none", provider="none", key="")
    a = c.post("/api/review", json={"code": "x = 1"}, headers=H).json()["id"]
    b = c.post("/api/review", json={"code": "y = 2", "save_code": True}, headers=H).json()["id"]
    assert c.get(f"/api/history/{a}", headers=H).json()["code"] is None
    assert c.get(f"/api/history/{b}", headers=H).json()["code"] == "y = 2"


def test_parse_json_tolerance():
    assert llm.parse_json_object('```json\n{"smells": []}\n```') == {"smells": []}
    assert llm.parse_json_object('Sure! {"smells": []} Hope it helps') == {"smells": []}
    with pytest.raises(llm.LLMError):
        llm.parse_json_object("not json")
