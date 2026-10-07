export const SEVERITIES = ["high", "medium", "low"];
export const label = (c) => c.replace(/_/g, " ").replace(/^\w/, (m) => m.toUpperCase());
const range = (s) => (s.start_line === s.end_line ? `line ${s.start_line}` : `lines ${s.start_line}–${s.end_line}`);

// REQ-RRG-3: Markdown export
export function toMarkdown(report) {
  const { summary: s } = report;
  const out = [
    "# Code Review Report",
    "",
    `**Language:** ${report.language} · **Lines:** ${report.total_lines}`,
    `**Issues:** ${s.total} (High: ${s.high}, Medium: ${s.medium}, Low: ${s.low})`,
    "",
    `> ${report.disclaimer}`,
    "",
  ];
  if (!report.smells.length) out.push("No design-level issues detected.");
  for (const m of report.smells) {
    out.push(`## ${m.id}. [${m.severity.toUpperCase()}] ${label(m.category)} — ${range(m)}`);
    if (m.target) out.push(`**Target:** \`${m.target}\``);
    out.push("", m.description, "");
    out.push(`**Suggested refactor${m.refactoring_pattern ? ` (${m.refactoring_pattern})` : ""}:** ${m.suggestion}`, "");
  }
  return out.join("\n");
}

export function download(filename, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}
