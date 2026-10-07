import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Editor from "react-simple-code-editor";
import Prism from "prismjs";
import "prismjs/components/prism-clike";
import "prismjs/components/prism-python";
import "prismjs/components/prism-java";
import "prismjs/themes/prism-tomorrow.css";
import { api } from "./api.js";
import { SAMPLES } from "./samples.js";
import { SEVERITIES, label, toMarkdown, download } from "./markdown.js";

const guessLang = (c) => (/\b(public|private|void|System\.out)\b|;\s*$/m.test(c) && !/^\s*def\s/m.test(c) ? "java" : "python");
const range = (s) => (s.start_line === s.end_line ? `Line ${s.start_line}` : `Lines ${s.start_line}–${s.end_line}`);

// Render `inline code` spans from the backend's messages as <code>; everything stays escaped by React.
function Inline({ text }) {
  return text.split(/(`[^`]+`)/g).map((part, i) =>
    part.startsWith("`") && part.endsWith("`") && part.length > 2 ? <code key={i}>{part.slice(1, -1)}</code> : part);
}

function Banner({ kind = "error", children, onClose, action }) {
  return (
    <div className={`banner ${kind}`} role="alert">
      <span>{children}</span>
      {action}
      {onClose && <button className="x" aria-label="Dismiss" onClick={onClose}>×</button>}
    </div>
  );
}

function SmellCard({ s }) {
  return (
    <article className={`card sev-${s.severity}`}>
      <header>
        <span className={`badge ${s.severity}`}>{s.severity}</span>
        <strong>{label(s.category)}</strong>
        <span className="lines">{range(s)}</span>
        <span className="src">{s.source === "static" ? "Static" : s.source === "ai" ? "AI" : "Static + AI"}</span>
      </header>
      {s.target && <code className="target">{s.target}</code>}
      <p><Inline text={s.description} /></p>
      <div className={`fix ${s.suggestion_available ? "" : "muted"}`}>
        <b>Suggested refactor{s.refactoring_pattern ? ` · ${s.refactoring_pattern}` : ""}</b>
        <p><Inline text={s.suggestion} /></p>
      </div>
    </article>
  );
}

function Report({ report, onRetry, busy }) {
  const [sort, setSort] = useState("severity");
  const [dismissed, setDismissed] = useState({});
  const [copied, setCopied] = useState(false);
  useEffect(() => setDismissed({}), [report]);
  const smells = useMemo(() => {
    const a = [...report.smells];
    a.sort(sort === "line" ? (x, y) => x.start_line - y.start_line
      : (x, y) => SEVERITIES.indexOf(x.severity) - SEVERITIES.indexOf(y.severity) || x.start_line - y.start_line);
    return a;
  }, [report, sort]);
  const { summary: sm } = report;
  const copy = async () => {
    try { await navigator.clipboard.writeText(toMarkdown(report)); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch {}
  };
  return (
    <>
      {report.warnings.map((w, i) => !dismissed[i] && (
        <Banner key={i} kind={w.retry ? "error" : "info"} onClose={() => setDismissed({ ...dismissed, [i]: true })}
          action={w.retry && <button className="link" disabled={busy} onClick={onRetry}>Retry</button>}>{w.message}</Banner>
      ))}
      <div className="summary">
        <div><b>{sm.total}</b> issue{sm.total === 1 ? "" : "s"}</div>
        {SEVERITIES.map((v) => <span key={v} className={`badge ${v}`}>{v} {sm[v]}</span>)}
        <span className="spacer" />
        <label>Sort <select value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="severity">Severity</option><option value="line">Line number</option></select></label>
        <button onClick={copy}>{copied ? "Copied ✓" : "Copy"}</button>
        <button onClick={() => download("code-review.md", toMarkdown(report))}>Download .md</button>
      </div>
      <p className="disclaimer">⚠ {report.disclaimer}</p>
      {smells.length === 0
        ? <div className="empty">✅ No design-level issues detected</div>
        : smells.map((s) => <SmellCard key={s.id} s={s} />)}
    </>
  );
}

export default function App() {
  const [code, setCode] = useState("");
  const [language, setLanguage] = useState("auto");
  const [saveCode, setSaveCode] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]);
  const [config, setConfig] = useState(null);
  const [help, setHelp] = useState(false);
  const fileRef = useRef(null);

  const refresh = useCallback(async () => {
    try { setHistory((await api.history()).items); setConfig(await api.config()); } catch (e) { setError(e.message); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const run = async () => {
    setBusy(true); setError(null);
    try {
      const r = await api.review(code, language, saveCode);
      setReport(r.report);
      refresh();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  const open = async (id) => {
    setError(null);
    try {
      const r = await api.historyItem(id);  // no LLM call (REQ-RH-3)
      setReport(r.report);
      if (r.code) { setCode(r.code); setLanguage(r.language); }
    } catch (e) { setError(e.message); }
  };
  const remove = async (id) => { try { await api.deleteHistory(id); refresh(); } catch (e) { setError(e.message); } };

  const upload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setCode(await f.text());
    setLanguage(f.name.endsWith(".java") ? "java" : f.name.endsWith(".py") ? "python" : "auto");
    e.target.value = "";
  };

  const shownLang = language === "auto" ? guessLang(code) : language;
  const highlight = (c) => Prism.highlight(c, Prism.languages[shownLang], shownLang);  // Prism escapes HTML (SRS 5.3)
  const lineCount = code ? code.split("\n").length : 0;

  return (
    <div className="app">
      <header className="top">
        <h1>Code Reviewer <span>&amp; Technical Debt Flagger</span></h1>
        <div className="meta">
          {config && (config.llm_enabled
            ? <span className="pill ok">AI: {config.provider} · {config.used_today}/{config.daily_limit} today</span>
            : <span className="pill warn">AI off · static analysis only</span>)}
          <button onClick={() => setHelp(!help)}>{help ? "Close help" : "How it works"}</button>
        </div>
      </header>

      {help && (
        <section className="help">
          <h3>How it works</h3>
          <p>1) A real parser (Python <code>ast</code> / Java <code>javalang</code>) measures function length, parameters, nesting, complexity and class coupling.
            2) Those measurements plus your code go to an AI model that looks for design smells. 3) You get a report of issues with refactoring suggestions.</p>
          <p><b>Detects:</b> long methods, god classes, high coupling, duplicated logic, poor naming, deep nesting, high complexity, long parameter lists.
            <b> Does not:</b> find bugs, security flaws, type errors or style nits — use a linter/compiler for those. Don't submit code you aren't allowed to share with a third-party AI API.</p>
        </section>
      )}

      <div className="layout">
        <aside className="history">
          <h3>History</h3>
          {history.length === 0 && <p className="muted">No reviews yet.</p>}
          {history.map((h) => (
            <div key={h.id} className="hitem">
              <button className="hopen" onClick={() => open(h.id)}>
                <b>{h.language}</b> · {h.summary.total} issue{h.summary.total === 1 ? "" : "s"}
                <small>{new Date(h.created_at).toLocaleString()}</small>
              </button>
              <button className="x" aria-label="Delete review" onClick={() => remove(h.id)}>🗑</button>
            </div>
          ))}
        </aside>

        <main className="panels">
          <section className="input">
            <div className="toolbar">
              <label>Language <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                <option value="auto">Auto-detect</option><option value="python">Python</option><option value="java">Java</option></select></label>
              <button onClick={() => fileRef.current.click()}>Upload file</button>
              <input ref={fileRef} type="file" accept=".py,.java,.txt" hidden onChange={upload} />
              <select aria-label="Sample snippets" value="" onChange={(e) => { const s = SAMPLES[e.target.value]; if (s) { setCode(s.code); setLanguage(s.language); } }}>
                <option value="">Try a sample…</option>{SAMPLES.map((s, i) => <option key={i} value={i}>{s.name}</option>)}</select>
              <span className="spacer" /><small className="muted">{lineCount} / {config?.max_lines ?? 2000} lines</small>
            </div>
            <div className="editor">
              <Editor value={code} onValueChange={setCode} highlight={highlight} padding={12} tabSize={4}
                placeholder="Paste Python or Java code here…" textareaId="code-input" />
            </div>
            <div className="actions">
              <label className="check"><input type="checkbox" checked={saveCode} onChange={(e) => setSaveCode(e.target.checked)} /> Keep my code in history (off by default)</label>
              <button className="primary" disabled={busy || !code.trim()} onClick={run}>{busy ? <><i className="spin" /> Reviewing…</> : "Review"}</button>
            </div>
          </section>

          <section className="output">
            {error && <Banner onClose={() => setError(null)}>{error}</Banner>}
            {busy && <div className="loading"><i className="spin big" /> Analysing your code…</div>}
            {!busy && report && <Report report={report} onRetry={run} busy={busy} />}
            {!busy && !report && !error && <div className="empty muted">Paste code (or pick a sample) and press <b>Review</b>.</div>}
          </section>
        </main>
      </div>
    </div>
  );
}
