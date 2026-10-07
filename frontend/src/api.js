// Session id = the "session" in SRS "session-scoped history". Stored in the browser only.
function sessionId() {
  try {
    let id = localStorage.getItem("cr_session");
    if (!id) {
      id = (crypto.randomUUID?.() ?? String(Math.random()).slice(2) + Date.now()).replace(/[^A-Za-z0-9_-]/g, "");
      localStorage.setItem("cr_session", id);
    }
    return id;
  } catch {
    return (window.__cr ||= "mem" + Math.random().toString(36).slice(2, 12));
  }
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", "X-Session-Id": sessionId(), ...(options.headers || {}) },
    });
  } catch {
    throw new Error("Cannot reach the server. Is the backend running?");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

export const api = {
  config: () => request("/api/config"),
  review: (code, language, save_code) =>
    request("/api/review", { method: "POST", body: JSON.stringify({ code, language, save_code }) }),
  history: () => request("/api/history"),
  historyItem: (id) => request(`/api/history/${id}`),
  deleteHistory: (id) => request(`/api/history/${id}`, { method: "DELETE" }),
};
