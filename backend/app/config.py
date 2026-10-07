"""Server-side configuration (env vars). The API key never leaves the server (SRS 5.3)."""
import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


# provider -> (kind, default base url, default model)
PRESETS = {
    "gemini": ("gemini", "https://generativelanguage.googleapis.com/v1beta", "gemini-flash-latest"),
    "groq": ("openai", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "openrouter": ("openai", "https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free"),
    "ollama": ("openai", "http://localhost:11434/v1", "qwen2.5-coder:7b"),
    "none": ("none", "", ""),
}


@dataclass
class Settings:
    provider: str
    kind: str
    base_url: str
    model: str
    api_key: str
    timeout: float
    long_method_lines: int
    max_lines: int
    max_chars: int
    daily_limit: int
    db_path: str
    fallback_models: tuple = ()


def load_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "none").strip().lower()
    if provider not in PRESETS:
        provider = "none"
    kind, base, model = PRESETS[provider]
    return Settings(
        provider=provider,
        kind=kind,
        base_url=os.getenv("LLM_BASE_URL", base).rstrip("/"),
        model=os.getenv("LLM_MODEL", model),
        api_key=os.getenv("LLM_API_KEY", ""),
        timeout=_float("LLM_TIMEOUT_SECONDS", 15.0),
        long_method_lines=_int("LONG_METHOD_LINES", 40),
        max_lines=_int("MAX_SNIPPET_LINES", 2000),
        max_chars=_int("MAX_SNIPPET_CHARS", 200_000),
        daily_limit=_int("DAILY_REVIEW_LIMIT", 20),
        fallback_models=tuple(m.strip() for m in os.getenv(
            "LLM_FALLBACK_MODELS", "gemini-flash-lite-latest" if provider == "gemini" else "").split(",") if m.strip()),
        db_path=os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "reviews.db")),
    )