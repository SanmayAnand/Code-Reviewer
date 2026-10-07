"""Diagnose your AI setup:  python check_llm.py
Shows which models your key can use and which ones actually answer right now."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import run  # loads .env
import httpx
from dataclasses import replace
from app import llm
from app.config import load_settings

s = load_settings()
print(f"Provider: {s.provider} | Model: {s.model} | Key set: {bool(s.api_key)}")
if s.kind == "none":
    sys.exit("LLM_PROVIDER is 'none' or unrecognised. Use gemini, groq, openrouter or ollama.")

models = []
try:
    if s.kind == "gemini":
        r = httpx.get(f"{s.base_url}/models?pageSize=200", headers={"x-goog-api-key": s.api_key}, timeout=20)
        print("List models ->", r.status_code)
        if r.status_code == 200:
            models = [m["name"].split("/")[-1] for m in r.json().get("models", [])
                      if "generateContent" in m.get("supportedGenerationMethods", [])]
        else:
            print(r.text[:300])
    else:
        r = httpx.get(f"{s.base_url}/models", headers={"Authorization": f"Bearer {s.api_key}"}, timeout=20)
        print("List models ->", r.status_code)
        if r.status_code == 200:
            models = [m["id"] for m in r.json().get("data", [])]
except Exception as e:
    sys.exit(f"Cannot reach the provider: {e}")

cand = [m for m in models if "flash" in m or "lite" in m][:12] or models[:12]
print("\nTrying a tiny request on each candidate model:")
for m in cand:
    try:
        asyncio.run(llm._analyze_one(replace(s, model=m, timeout=30), "Reply with JSON only.", 'Return {"smells": []}'))
        print(f"  OK       {m}")
    except Exception as e:
        print(f"  FAILED   {m}  ->  {e}")
print("\nPut a model marked OK into backend/.env as LLM_MODEL=<name>")