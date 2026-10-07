"""Provider-agnostic LLM client. Supports Gemini (free tier) and any OpenAI-compatible API
(Groq, OpenRouter, Ollama). The API key stays server-side (SRS 3.4, 5.3)."""
import asyncio
from dataclasses import replace
import json
import re
import httpx
from .config import Settings


class LLMTimeout(Exception):
    pass


class LLMError(Exception):
    pass


class LLMTransient(LLMError):
    """Temporary provider-side problem (overloaded / rate limited). Worth retrying."""


def parse_json_object(text: str) -> dict:
    """Tolerant parse: strips ```json fences and surrounding prose."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise LLMError("The AI returned a response that was not valid JSON.")


def _detail(resp: httpx.Response) -> str:
    try:
        msg = resp.json()["error"]["message"]
        return f" Provider says: {str(msg)[:200]}"
    except Exception:
        return ""


def _http_error(resp: httpx.Response) -> LLMError:
    code = resp.status_code
    if code in (401, 403):
        return LLMError("The LLM API rejected the API key (check LLM_API_KEY).")
    if code == 429:
        return LLMTransient("The LLM API rate limit was hit. Wait a minute and retry.")
    if code in (500, 502, 503, 504):
        return LLMTransient(f"The AI model is overloaded or temporarily unavailable (HTTP {code}). "
                            "Try again in a moment, or set LLM_MODEL to a different model." + _detail(resp))
    if code == 404:
        return LLMError("The LLM model was not found (check LLM_MODEL).")
    if code == 413:
        return LLMError("The snippet is too large for this provider's free tier. Try a shorter snippet.")
    return LLMError(f"The LLM API returned HTTP {code}.")


async def _gemini(s: Settings, system: str, user: str) -> str:
    url = f"{s.base_url}/models/{s.model}:generateContent"
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}
    async with httpx.AsyncClient(timeout=s.timeout) as c:
        r = await c.post(url, json=body, headers={"x-goog-api-key": s.api_key})
    if r.status_code != 200:
        raise _http_error(r)
    try:
        parts = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, ValueError) as e:
        raise LLMError("The AI returned an empty or blocked response.") from e


async def _openai_compat(s: Settings, system: str, user: str) -> str:
    body = {"model": s.model, "temperature": 0.2,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"}}
    headers = {"Authorization": f"Bearer {s.api_key}"} if s.api_key else {}
    async with httpx.AsyncClient(timeout=s.timeout) as c:
        r = await c.post(f"{s.base_url}/chat/completions", json=body, headers=headers)
    if r.status_code != 200:
        raise _http_error(r)
    try:
        return r.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        raise LLMError("The AI returned an empty response.") from e


async def _analyze_one(s: Settings, system: str, user: str) -> dict:
    fn = _gemini if s.kind == "gemini" else _openai_compat
    delays = [2]  # 2 attempts per model on temporary errors
    for attempt in range(len(delays) + 1):
        try:
            text = await asyncio.wait_for(fn(s, system, user), timeout=s.timeout + 1)
            return parse_json_object(text)
        except (asyncio.TimeoutError, httpx.TimeoutException) as e:
            raise LLMTimeout(f"The AI did not respond within {s.timeout:g} seconds.") from e
        except httpx.HTTPError as e:
            raise LLMError(f"Could not reach the LLM API ({type(e).__name__}).") from e
        except LLMTransient:
            if attempt == len(delays):
                raise
            await asyncio.sleep(delays[attempt])


async def analyze(s: Settings, system: str, user: str) -> dict:
    """Return the parsed JSON object from the LLM. Raises LLMTimeout / LLMError.
    If a model stays overloaded, the models in s.fallback_models are tried in order."""
    if s.kind == "none":
        raise LLMError("No LLM provider configured.")
    if s.kind == "gemini" and not s.api_key:
        raise LLMError("No API key set. Add LLM_API_KEY to backend/.env (see README).")
    last = None
    for model in [s.model] + [m for m in s.fallback_models if m != s.model]:
        try:
            return await _analyze_one(replace(s, model=model), system, user)
        except LLMTransient as e:
            last = e  # try the next model
    raise last