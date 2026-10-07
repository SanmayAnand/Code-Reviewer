"""FastAPI backend: orchestrates detect -> parse/metrics -> LLM -> report -> history."""
import asyncio
import hashlib
import logging
import os
import re
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import llm
from .config import Settings, load_settings
from .db import Database
from .language import detect_language
from .metrics import ParseError, extract_metrics
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .report import build_report, normalise_llm_smells
from .static_smells import static_smells

log = logging.getLogger("reviewer")
_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class ReviewRequest(BaseModel):
    code: str
    language: str = "auto"  # auto | python | java
    save_code: bool = False  # opt-in: keep raw snippet in history


def create_app(settings: Optional[Settings] = None, db: Optional[Database] = None) -> FastAPI:
    s = settings or load_settings()
    store = db or Database(s.db_path)
    app = FastAPI(title="Code Reviewer & Technical Debt Flagger", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])

    def session(x_session_id: Optional[str]) -> str:
        if not x_session_id or not _SESSION_RE.match(x_session_id):
            raise HTTPException(400, "Missing or invalid X-Session-Id header.")
        return x_session_id

    @app.get("/api/config")
    def config(x_session_id: Optional[str] = Header(None)):
        sid = session(x_session_id)
        llm_on = s.kind != "none" and (s.kind != "gemini" or bool(s.api_key))
        return {"provider": s.provider, "model": s.model if llm_on else None, "llm_enabled": llm_on,
                "long_method_lines": s.long_method_lines, "max_lines": s.max_lines,
                "daily_limit": s.daily_limit, "used_today": store.used_today(sid) if llm_on else 0}

    @app.post("/api/review")
    async def review(req: ReviewRequest, x_session_id: Optional[str] = Header(None)):
        sid = session(x_session_id)
        code = req.code.replace("\r\n", "\n")
        if not code.strip():
            raise HTTPException(422, "Please paste or upload some code first.")
        if len(code) > s.max_chars or len(code.splitlines()) > s.max_lines:  # REQ-CSD-1
            raise HTTPException(413, f"Snippet too large (max {s.max_lines} lines).")
        lang = req.language.lower()
        if lang not in ("auto", "python", "java"):
            raise HTTPException(422, "Language must be auto, python or java.")
        detected = detect_language(code) if lang == "auto" else lang

        try:  # REQ-CSD-3: reject unparseable code
            metrics = (await asyncio.to_thread(extract_metrics, code, detected)).to_dict()
        except ParseError as e:
            raise HTTPException(422, str(e))

        static = static_smells(metrics_obj(metrics), s.long_method_lines)
        warnings, ai_smells = [], []
        llm_info = {"provider": s.provider, "model": s.model or None, "status": "skipped"}
        llm_on = s.kind != "none"
        if not llm_on:
            warnings.append({"code": "no_llm", "retry": False,
                             "message": "AI analysis is off (LLM_PROVIDER=none). Showing static-analysis findings only."})
        elif s.kind == "gemini" and not s.api_key:
            llm_info["status"] = "error"
            warnings.append({"code": "no_key", "retry": False,
                             "message": "No LLM API key configured. Showing static-analysis findings only."})
        elif store.used_today(sid) >= s.daily_limit:  # SRS 5.5
            raise HTTPException(429, f"Daily limit of {s.daily_limit} AI reviews reached. Try again tomorrow.")
        else:
            try:
                raw = await llm.analyze(s, SYSTEM_PROMPT, build_user_prompt(code, detected, metrics, s.long_method_lines))
                ai_smells = normalise_llm_smells(raw, metrics["total_lines"])
                llm_info["status"] = "ok"
                store.bump_usage(sid)
            except llm.LLMTimeout as e:  # REQ-CSD-7
                llm_info["status"] = "timeout"
                warnings.append({"code": "timeout", "retry": True, "message": str(e) + " Showing static findings; you can retry."})
            except llm.LLMError as e:
                llm_info["status"] = "error"
                warnings.append({"code": "llm_error", "retry": True, "message": f"{e} Showing static findings only."})
            except Exception:  # never crash because the LLM misbehaved (SRS 5.4)
                log.exception("unexpected LLM failure")
                llm_info["status"] = "error"
                warnings.append({"code": "llm_error", "retry": True, "message": "Unexpected AI error. Showing static findings only."})

        report = build_report(detected, metrics, static, ai_smells, llm_info, warnings)
        review_id = None
        if llm_info["status"] in ("ok", "skipped"):  # REQ-RH-1: persist completed reviews only
            h = hashlib.sha256(code.encode()).hexdigest()
            review_id = store.add_review(sid, h, detected, report, code if req.save_code else None)
        return {"id": review_id, "report": report,
                "used_today": store.used_today(sid), "daily_limit": s.daily_limit}

    @app.get("/api/history")
    def history(x_session_id: Optional[str] = Header(None)):
        return {"items": store.list_reviews(session(x_session_id), 20)}  # REQ-RH-2

    @app.get("/api/history/{review_id}")
    def history_item(review_id: int, x_session_id: Optional[str] = Header(None)):
        item = store.get_review(session(x_session_id), review_id)  # REQ-RH-3: no LLM call
        if not item:
            raise HTTPException(404, "Review not found.")
        return item

    @app.delete("/api/history/{review_id}")
    def history_delete(review_id: int, x_session_id: Optional[str] = Header(None)):
        if not store.delete_review(session(x_session_id), review_id):  # REQ-RH-4, Business rule 5.5
            raise HTTPException(404, "Review not found.")
        return {"deleted": review_id}

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="ui")
    return app


def metrics_obj(d: dict):
    """Rebuild a Metrics object from its dict form (the dict is what the prompt/report use)."""
    from .metrics import Metrics, FunctionMetrics, ClassMetrics
    return Metrics(d["language"], d["total_lines"], [FunctionMetrics(**f) for f in d["functions"]],
                   [ClassMetrics(**c) for c in d["classes"]])


app = create_app() if os.getenv("CREATE_APP_ON_IMPORT", "1") == "1" else None
