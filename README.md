# Code Reviewer & Technical Debt Flagger

A web application that analyzes Python and Java source code for design-level problems (code smells and technical debt) and recommends specific refactorings. A user submits a code snippet and receives a structured review report.

## Overview

The system combines static analysis with a large language model (LLM):

```
Browser (React)  ->  FastAPI backend  ->  language detection
                                       ->  static pre-processor (Python ast / Java javalang)  ->  metrics
                                       ->  deterministic smell rules
                                       ->  LLM analysis grounded by the metrics
                                       ->  merged report  ->  SQLite history
```

1. A language-aware parser measures function length, parameter count, nesting depth, cyclomatic complexity, class size and class coupling.
2. Deterministic rules flag objective problems, for example a method longer than a configurable line threshold.
3. The LLM receives the code together with the measured metrics and reports semantic issues such as duplicated logic, poor naming and classes with too many responsibilities, each with a named refactoring pattern.
4. Static and LLM findings are merged into a single report. If the LLM is unavailable, the static findings are still returned.

## Features

- Code input by paste or file upload, up to 2,000 lines
- Automatic language detection (Python or Java) with manual override
- Detected smells: long method, god class, high coupling, duplicated code, poor naming, deep nesting, high complexity, long parameter list
- One refactoring suggestion per issue (maximum 100 words) that references the specific function or class
- Report cards with severity, line range and description; sorting by severity or line number; copy and Markdown download
- Session history of the 20 most recent reviews; reopening a review does not call the LLM again
- Fallback behavior: automatic retries, fallback models and a static-only mode
- Configurable daily review limit
- Submitted code is not stored unless the user selects "Keep my code in history"

## Technology stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn, httpx |
| Static analysis | `ast` (Python), `javalang` (Java) |
| LLM providers | Gemini, Groq, OpenRouter, Ollama (local) |
| Frontend | React 18, Vite, Prism |
| Database | SQLite |
| Testing | pytest |

## Installation

**Requirements:** Python 3.11 or newer. Node.js is required only to rebuild the frontend; the built frontend is included in the repository.

```bash
git clone https://github.com/SanmayAnand/Code-Reviewer.git
cd code-reviewer/backend

python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -r requirements.txt

# Windows: copy .env.example .env
cp .env.example .env
```

Edit `backend/.env` to select an LLM provider (see [LLM provider setup](#llm-provider-setup)), then start the server:

```bash
python run.py
```

The application is available at http://127.0.0.1:8000. Interactive API documentation is available at http://127.0.0.1:8000/docs.

## LLM provider setup

`LLM_PROVIDER` selects the service. The model is configured separately with `LLM_MODEL`.

| `LLM_PROVIDER` | Requirements |
|---|---|
| `gemini` | API key from https://aistudio.google.com/apikey in `LLM_API_KEY` |
| `groq` | API key from https://console.groq.com/keys in `LLM_API_KEY` |
| `openrouter` | API key from https://openrouter.ai in `LLM_API_KEY`; set `LLM_MODEL` |
| `ollama` | Local Ollama installation (https://ollama.com) and a pulled model, for example `ollama pull qwen2.5-coder:7b`; no API key |
| `none` | No LLM; static analysis only |

Example:

```dotenv
LLM_PROVIDER=gemini
LLM_API_KEY=<your-api-key>
# LLM_MODEL=gemini-flash-latest
```

Restart the server after changing `.env`. The status badge in the page header shows the active provider, or "AI off" when no LLM is configured.

**Data handling:** with hosted providers, submitted code is sent to a third-party service and is subject to that provider's terms. Do not submit code that you are not permitted to share. Use `ollama` to keep all processing on the local machine.

## Configuration

All settings are environment variables, which can be placed in `backend/.env`.

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `none` | `gemini`, `groq`, `openrouter`, `ollama` or `none` |
| `LLM_API_KEY` | empty | Provider API key (kept on the server, never sent to the browser) |
| `LLM_MODEL` | provider default | Model name override |
| `LLM_BASE_URL` | provider default | API base URL override |
| `LLM_FALLBACK_MODELS` | `gemini-flash-lite-latest` (Gemini) | Comma-separated models tried if the primary model is unavailable |
| `LLM_TIMEOUT_SECONDS` | `15` | Timeout for each LLM attempt |
| `LONG_METHOD_LINES` | `40` | Long-method threshold |
| `MAX_SNIPPET_LINES` | `2000` | Maximum lines per snippet |
| `MAX_SNIPPET_CHARS` | `200000` | Maximum characters per snippet |
| `DAILY_REVIEW_LIMIT` | `20` | LLM reviews per session per day |
| `DB_PATH` | `backend/reviews.db` | SQLite database location |
| `PORT` | `8000` | Server port |

### Static smell rules

| Smell | Medium | High |
|---|---|---|
| Long method | more than 40 lines | more than 80 lines |
| Long parameter list | more than 5 parameters | |
| Deep nesting | 4 levels | 5 or more levels |
| High cyclomatic complexity | more than 10 | more than 20 |
| God class | more than 15 methods or 12 fields | more than 30 methods |
| High coupling | 8 or more external types | 12 or more |

## REST API

All endpoints require the header `X-Session-Id` (8 to 64 characters: letters, digits, `-` or `_`).

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/config` | Provider status, limits and usage for the day |
| `POST` | `/api/review` | Request body: `{"code": "...", "language": "auto", "save_code": false}` |
| `GET` | `/api/history` | The 20 most recent reviews of the session |
| `GET` | `/api/history/{id}` | Retrieve a stored report |
| `DELETE` | `/api/history/{id}` | Delete a history entry |

`language` accepts `auto`, `python` or `java`.

## Testing

```bash
cd backend
python -m pytest -v
```

The test suite covers metric extraction, language detection, smell rules, report assembly, history, the daily limit, input validation, timeouts, retries and model fallback. The LLM is mocked, so no API key is needed.

To verify a provider configuration against the live service:

```bash
python check_llm.py
```

The script lists the models available to the configured key and reports which of them respond.

## Troubleshooting

| Symptom | Resolution |
|---|---|
| Header shows "AI off" | `LLM_PROVIDER` must be a provider name such as `gemini`, not a model name. Set the model with `LLM_MODEL` and restart the server. |
| HTTP 503 or "model overloaded" | Temporary provider condition. The application retries and uses fallback models. Run `python check_llm.py` and set `LLM_MODEL` to a responding model. |
| HTTP 429 or rate limit message | The provider rate limit was reached. Wait and retry, or use another provider. |
| "model not found" | Remove `LLM_MODEL` or choose a model reported by `python check_llm.py`. |
| "rejected the API key" | Verify `LLM_API_KEY` for typing errors or surrounding whitespace. |
| Parse error | The snippet is not valid code for the selected language. The message includes the line number. |

## Development

```bash
# Frontend development server (Node.js 18+; backend must be running on port 8000)
cd frontend
npm install
npm run dev          # http://localhost:5173

# Rebuild the production frontend into backend/app/static
npm run build
```

## Project structure

```
code-reviewer/
├── README.md
├── backend/
│   ├── run.py                  application entry point (loads .env)
│   ├── check_llm.py            LLM configuration diagnostic
│   ├── requirements.txt
│   ├── .env.example
│   ├── tests/test_all.py
│   └── app/
│       ├── main.py             API endpoints
│       ├── config.py           settings and provider presets
│       ├── language.py         language detection
│       ├── metrics/            Python and Java metric extraction
│       ├── static_smells.py    deterministic smell rules
│       ├── prompts.py          LLM prompt templates
│       ├── llm.py              LLM client
│       ├── report.py           report validation, merging and summary
│       ├── db.py               SQLite history and usage counters
│       └── static/             built frontend
└── frontend/src/               React source
```

## Limitations

- Single snippets only; whole-repository analysis is not supported
- Python and Java only
- The tool reports design smells; it does not detect bugs, security vulnerabilities or type errors
- Suggestions are AI-generated recommendations and must be reviewed before being applied
- The default configuration serves HTTP on localhost; deploy behind HTTPS for shared use

## Roadmap

- Additional languages (JavaScript, C++)
- Repository and pull-request analysis
- AST-based duplicate code detection
- IDE extension

## Author

Sanmay Anand

## License

Released under the MIT License. See `LICENSE`.