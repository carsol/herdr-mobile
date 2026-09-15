/* Shared helpers: API calls, escaping, agent icons, composer wiring. */
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (r.status === 401) { location.href = "/login"; throw new Error("unauthorized"); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

const ICONS = { claude: "✳︎", codex: "◆", gemini: "✦", pi: "π", opencode: "⌘", agy: "⟁", cline: "⚙", copilot: "◎", amp: "⚡" };
const agentIcon = (a) => ICONS[a] || (a ? "●" : ">_");

const paneFromPath = () => decodeURIComponent(location.pathname.split("/").slice(2).join("/"));

/* Per-pane view preference (terminal vs chat), remembered on this device. */
const viewPref = {
  get(id) { try { return localStorage.getItem("view:" + id) || ""; } catch { return ""; } },
  set(id, v) { try { localStorage.setItem("view:" + id, v); } catch {} },
};

/* Composer: textarea + send + key row. Used by both terminal and chat views. */
function wireComposer(paneId, { onSent } = {}) {
  const ta = $("#prompt"), send = $("#send");
  const autosize = () => { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 140) + "px"; };
  ta.addEventListener("input", autosize);
  const submit = async () => {
    const text = ta.value.replace(/\n$/, "");
    if (!text.trim()) return;
    send.disabled = true;
    try {
      await api(`/api/panes/${encodeURIComponent(paneId)}/text`, { method: "POST", body: { text, enter: true } });
      ta.value = ""; autosize(); onSent?.(text);
    } catch (e) { alert(e.message); }
    finally { send.disabled = false; ta.focus(); }
  };
  send.addEventListener("click", submit);
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && window.matchMedia("(min-width: 900px)").matches) {
      e.preventDefault(); submit();
    }
  });
  document.querySelectorAll(".keys button[data-key]").forEach((b) =>
    b.addEventListener("click", () => api(`/api/panes/${encodeURIComponent(paneId)}/keys`, { method: "POST", body: { keys: [b.dataset.key] } }).catch((e) => alert(e.message))));
}

async function closePane(paneId) {
  if (!confirm("Close this pane? The process inside will be killed.")) return;
  await api(`/api/panes/${encodeURIComponent(paneId)}/close`, { method: "POST" });
  location.href = "/";
}
