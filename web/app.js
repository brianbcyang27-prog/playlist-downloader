/* Playlist Downloader — front-end logic (vanilla JS, no build step). */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const state = {
  settings: {},
  defaults: {},
  tools: {},
  playlists: [],
  currentPlaylist: null,
  items: [],
  run: { running: false, paused: false, active: [] },
  queue: new Map(),          // item id -> row element
  live: new Map(),           // item id -> live progress payload
  lastCompare: null,
  browse: null,
};

/* ------------------------------------------------------------------ utils */
function toast(title, body = "", kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = `<b>${esc(title)}</b>${body ? `<span>${esc(body)}</span>` : ""}`;
  $("#toasts").appendChild(el);
  setTimeout(() => {
    el.style.transition = "opacity .3s, transform .3s";
    el.style.opacity = "0";
    el.style.transform = "translateX(24px)";
    setTimeout(() => el.remove(), 320);
  }, kind === "error" ? 7000 : 3800);
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}
function fmtBytes(n) {
  if (!n && n !== 0) return "";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}
function fmtTime(s) {
  if (s === null || s === undefined) return "";
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`
           : `${m}:${String(sec).padStart(2, "0")}`;
}
function bar(pct, cls = "") {
  return `<div class="track"><i class="${cls}" style="width:${Math.min(100, pct || 0)}%"></i></div>`;
}

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `${res.status} ${res.statusText}`);
  }
  return data;
}

/* ------------------------------------------------------------------- tabs */
$$(".tab").forEach(tab => tab.addEventListener("click", () => {
  $$(".tab").forEach(t => t.classList.remove("active"));
  $$(".panel").forEach(p => p.classList.remove("active"));
  tab.classList.add("active");
  $(`#tab-${tab.dataset.tab}`).classList.add("active");
}));
$$(".mini-tab").forEach(tab => tab.addEventListener("click", () => {
  $$(".mini-tab").forEach(t => t.classList.remove("active"));
  $$(".cres").forEach(c => c.classList.remove("active"));
  tab.classList.add("active");
  $(`#cres-${tab.dataset.cres}`).classList.add("active");
}));

/* -------------------------------------------------------------- bootstrap */
async function loadState() {
  const s = await api("/api/state");
  state.settings = s.settings;
  state.defaults = s.defaults;
  state.tools = s.tools;
  state.run = s.run;
  $("#version").textContent = `v${s.version} · ${s.platform}`;
  fillSettings(s.settings);
  renderTools(s.tools);
  updateStats(s.stats);
  await loadPlaylists();
}

async function loadPlaylists() {
  const { playlists } = await api("/api/playlists");
  state.playlists = playlists;
  renderPlaylists();
  renderComparePlaylists();
}

/* --------------------------------------------------------------- settings */
const BOOL_KEYS = [
  "tag_metadata", "embed_cover_art", "write_cover_file", "rename_to_metadata",
  "use_archive", "skip_existing_files", "resolve_missing_to_youtube",
  "auto_retry_failed", "dry_run",
];
const TEXT_KEYS = [
  "download_dir", "audio_format", "audio_quality", "audio_filename",
  "video_format", "video_quality", "video_filename", "rate_limit_kbps",
  "retries", "retry_delay_seconds", "socket_timeout", "sleep_between_requests",
  "proxy", "cookies_from_browser", "ffmpeg_path", "spotify_client_id",
  "spotify_client_secret",
];
const RANGE_KEYS = ["concurrent_downloads", "concurrent_fragments", "item_retries"];

function fillSettings(s) {
  TEXT_KEYS.forEach(k => {
    const el = $(`#set-${k}`);
    if (el) el.value = s[k] ?? "";
  });
  BOOL_KEYS.forEach(k => {
    const el = $(`#set-${k}`);
    if (el) el.checked = !!s[k];
  });
  RANGE_KEYS.forEach(k => {
    const el = $(`#set-${k}`);
    if (el) el.value = s[k];
  });
  $("#lbl-workers").textContent = s.concurrent_downloads;
  $("#lbl-frags").textContent = s.concurrent_fragments;
  $("#lbl-item-retries").textContent = s.item_retries;
}
$("#set-concurrent_downloads").addEventListener("input", e =>
  $("#lbl-workers").textContent = e.target.value);
$("#set-concurrent_fragments").addEventListener("input", e =>
  $("#lbl-frags").textContent = e.target.value);
$("#set-item_retries").addEventListener("input", e =>
  $("#lbl-item-retries").textContent = e.target.value);

async function saveSettings() {
  const body = {};
  TEXT_KEYS.forEach(k => { const el = $(`#set-${k}`); if (el) body[k] = el.value; });
  BOOL_KEYS.forEach(k => { const el = $(`#set-${k}`); if (el) body[k] = el.checked; });
  RANGE_KEYS.forEach(k => { const el = $(`#set-${k}`); if (el) body[k] = Number(el.value); });
  try {
    const res = await api("/api/settings", { method: "POST", body });
    state.settings = res.settings;
    renderTools(res.tools);
    toast("Settings saved", "", "ok");
  } catch (e) { toast("Could not save", e.message, "error"); }
}
$("#btn-save").addEventListener("click", saveSettings);
$("#btn-reveal").addEventListener("click", async () => {
  try { await api("/api/reveal", { method: "POST", body: { path: $("#set-download_dir").value } }); }
  catch (e) { toast("Could not open folder", e.message, "error"); }
});

function renderTools(t) {
  const js = (t.js_runtimes && t.js_runtimes.length) ? t.js_runtimes.join("/") : "";
  $("#tool-status").innerHTML = `
    <span class="tool"><i class="dot ${t.ytdlp_ok ? "ok" : ""}"></i>yt-dlp <b>${t.ytdlp_ok ? "ready" : "missing"}</b></span>
    <span class="tool"><i class="dot ${t.ffmpeg_ok ? "ok" : ""}"></i>ffmpeg <b>${t.ffmpeg_ok ? "ready" : "missing"}</b></span>
    <span class="tool"><i class="dot ${t.ejs_ok ? "ok" : ""}"></i>JS challenge <b>${t.ejs_ok ? (js || "ready") : "missing"}</b></span>
    <span class="tool"><i class="dot ${t.rapidfuzz_installed ? "ok" : ""}"></i>fast match <b>${t.rapidfuzz_installed ? "ready" : "slow"}</b></span>
  `;
}

/* ------------------------------------------------------------------ stats */
function updateStats(stats) {
  $("#stat-total").textContent = stats.total;
  $("#stat-done").textContent = stats.done;
  $("#stat-skipped").textContent = stats.skipped || 0;
  $("#stat-pending").textContent = stats.pending;
  $("#stat-failed").textContent = stats.failed;
  $("#stat-active").textContent = state.live.size || stats.downloading || 0;
}

/* -------------------------------------------------------------- playlists */
function renderPlaylists() {
  const box = $("#playlist-list");
  if (!state.playlists.length) {
    box.innerHTML = `<p class="empty">No playlists yet.</p>`;
    return;
  }
  box.innerHTML = state.playlists.map(p => {
    const done = p.done || 0, skipped = p.skipped || 0, total = p.total || 1;
    const pct = Math.round((done + skipped) / total * 100);
    const active = state.currentPlaylist === p.id ? "active" : "";
    return `
      <div class="playlist ${active}" data-id="${p.id}">
        <div class="playlist-top">
          <span class="playlist-name" title="${esc(p.name)}">${esc(p.name)}</span>
          <button class="icon-btn" data-del="${p.id}" title="Remove playlist">✕</button>
        </div>
        <div class="playlist-meta">
          <span>${esc(p.source)} · ${done + skipped}/${p.total} done</span>
          ${p.failed ? `<span style="color:var(--bad)">${p.failed} failed</span>` : ""}
        </div>
        <div class="bar"><i style="width:${pct}%"></i></div>
      </div>`;
  }).join("");

  $$(".playlist", box).forEach(el => el.addEventListener("click", ev => {
    if (ev.target.dataset.del) return;
    selectPlaylist(Number(el.dataset.id));
  }));
  $$("[data-del]", box).forEach(btn => btn.addEventListener("click", async ev => {
    ev.stopPropagation();
    const id = Number(btn.dataset.del);
    const p = state.playlists.find(x => x.id === id);
    if (!confirm(`Remove “${p.name}” and its queue? Downloaded files are not deleted.`)) return;
    await api(`/api/playlists/${id}`, { method: "DELETE" });
    if (state.currentPlaylist === id) { state.currentPlaylist = null; state.items = []; renderQueue(); }
    await loadPlaylists();
  }));
}

async function selectPlaylist(id) {
  state.currentPlaylist = id;
  const p = state.playlists.find(x => x.id === id);
  $("#queue-title").textContent = p ? `Queue — ${p.name}` : "Queue";
  renderPlaylists();
  await loadItems();
}

async function loadItems() {
  if (!state.currentPlaylist) { state.items = []; renderQueue(); return; }
  const { items } = await api(`/api/playlists/${state.currentPlaylist}/items`);
  state.items = items;
  renderQueue();
}

/* ------------------------------------------------------------------ queue */
function filteredItems() {
  const q = $("#queue-filter").value.trim().toLowerCase();
  const st = $("#queue-status-filter").value;
  return state.items.filter(it => {
    if (st && it.status !== st) return false;
    if (!q) return true;
    return (`${it.title || ""} ${it.artist || ""}`).toLowerCase().includes(q);
  });
}

function renderQueue() {
  const body = $("#queue-body");
  const items = filteredItems();
  if (!items.length) {
    body.innerHTML = `<tr><td colspan="6" class="empty">${state.currentPlaylist ? "No items match this filter." : "Import a playlist to get started."}</td></tr>`;
    state.queue.clear();
    return;
  }
  const frag = document.createDocumentFragment();
  state.queue.clear();

  items.forEach((it, i) => {
    const tr = document.createElement("tr");
    tr.dataset.id = it.id;
    tr.className = it.status;
    tr.innerHTML = rowHtml(it, i + 1);
    frag.appendChild(tr);
    state.queue.set(it.id, tr);
  });
  body.replaceChildren(frag);
  // Re-apply live progress so a re-render does not lose the moving bars.
  state.live.forEach((p, id) => applyProgress(id, p));
}

function rowHtml(it, num) {
  return `
    <td class="col-num">${num}</td>
    <td><div class="cell-title" title="${esc(it.title || it.url)}">${esc(it.title || it.url)}</div></td>
    <td class="col-artist"><div class="cell-title" title="${esc(it.artist || "")}">${esc(it.artist || "")}</div></td>
    <td class="col-status"><span class="pill ${it.status}">${it.status}</span></td>
    <td class="col-progress">${progressCell(it)}</td>
    <td class="col-actions">${it.status === "failed"
      ? `<button class="icon-btn" data-retry="${it.id}" title="Retry">↻</button>` : ""}
      ${it.filepath ? `<button class="icon-btn" data-open="${esc(it.filepath)}" title="Show in folder">📁</button>` : ""}
    </td>`;
}

function progressCell(it) {
  if (it.status === "downloading") {
    return `<div class="progress">${bar(it.progress)}<span class="meta">${(it.progress || 0).toFixed(0)}%</span></div>`;
  }
  if (it.status === "done") {
    return `<div class="progress">${bar(100, "done")}<span class="meta">done</span></div>`;
  }
  if (it.status === "failed") {
    return `<span class="meta" title="${esc(it.error || "")}" style="color:var(--bad)">${esc((it.error || "failed").slice(0, 46))}</span>`;
  }
  return `<span class="meta">${it.duration ? fmtTime(it.duration) : ""}</span>`;
}

function applyProgress(id, p) {
  const tr = state.queue.get(id);
  if (!tr) return;
  const cell = $(".col-progress", tr);
  if (cell) {
    cell.innerHTML = `<div class="progress">${bar(p.progress)}<span class="meta">${
      (p.progress || 0).toFixed(0)}% · ${fmtBytes(p.speed)}/s${p.eta ? " · " + fmtTime(p.eta) : ""}</span></div>`;
  }
  const pill = $(".pill", tr);
  if (pill) { pill.className = "pill downloading"; pill.textContent = p.stage || "downloading"; }
}
$("#queue-filter").addEventListener("input", () => renderQueue());
$("#queue-status-filter").addEventListener("change", () => renderQueue());

$("#queue-body").addEventListener("click", async ev => {
  const retry = ev.target.dataset.retry;
  const open = ev.target.dataset.open;
  if (retry) {
    await api(`/api/items/${retry}/retry`, { method: "POST", body: {} });
    const item = state.items.find(x => x.id === Number(retry));
    if (item) { item.status = "pending"; item.error = null; }
    renderQueue();
  } else if (open) {
    await api("/api/reveal", { method: "POST", body: { path: open } });
  }
});

/* ------------------------------------------------------------- download UI */
$("#btn-import").addEventListener("click", doImport);
async function doImport() {
  const location = $("#import-input").value.trim();
  const source = $("#import-source").value;
  const mode = $("#import-mode").value;
  if (!location) { toast("Nothing to import", "Paste a link or file path.", "warn"); return; }
  $("#btn-import").disabled = true;
  $("#import-hint").textContent = "Reading playlist…";
  try {
    await api("/api/playlist/import", { method: "POST", body: { source, location, mode } });
  } catch (e) {
    $("#import-hint").textContent = "";
    $("#btn-import").disabled = false;
    toast("Import failed", e.message, "error");
  }
}

$("#btn-start").addEventListener("click", async () => {
  try {
    const res = await api("/api/download/start", {
      method: "POST",
      body: { playlist_id: state.currentPlaylist, retry_failed: false },
    });
    toast("Download started", `${res.queued} items queued across ${res.workers} workers.`, "ok");
  } catch (e) { toast("Could not start", e.message, "error"); }
});
$("#btn-pause").addEventListener("click", () => api("/api/download/pause", { method: "POST" }));
$("#btn-resume").addEventListener("click", () => api("/api/download/resume", { method: "POST" }));
$("#btn-stop").addEventListener("click", () => api("/api/download/stop", { method: "POST" }));
$("#btn-retry").addEventListener("click", async () => {
  try {
    const r = await api("/api/items/retry-failed", {
      method: "POST", body: { playlist_id: state.currentPlaylist },
    });
    toast("Re-queued", `${r.requeued} failed items are pending again.`, "ok");
    await loadItems();
  } catch (e) { toast("Nothing to retry", e.message, "warn"); }
});

$("#btn-quit").addEventListener("click", async () => {
  const running = +$("#stat-active").textContent;
  const warn = running ? "\n\nA download is still running — it will be stopped." : "";
  if (!confirm(`Quit Playlist Downloader?${warn}\n\nYour queue is saved, so you can pick up where you left off.`)) return;
  $("#btn-quit").disabled = true;
  try { await api("/api/shutdown", { method: "POST" }); } catch { /* the server is going away */ }
  await new Promise(r => setTimeout(r, 800));
  document.body.innerHTML = `
    <div class="quit-screen">
      <div class="card">
        <h2>Playlist Downloader has quit</h2>
        <p class="hint">The background service has stopped and your queue was saved.
        Close this tab, or click the app icon to start it again.</p>
        <button class="primary" onclick="window.close()">Close this tab</button>
      </div>
    </div>`;
});

function setRunUI() {
  const { running, paused } = state.run;
  $("#btn-start").hidden = running;
  $("#btn-pause").hidden = !running || paused;
  $("#btn-resume").hidden = !running || !paused;
  $("#btn-stop").hidden = !running;
  updateStats({
    total: +$("#stat-total").textContent,
    done: +$("#stat-done").textContent,
    pending: +$("#stat-pending").textContent,
    failed: +$("#stat-failed").textContent,
  });
}

/* ----------------------------------------------------------------- events */
function connectEvents() {
  const es = new EventSource("/api/events");
  es.onopen = () => { $("#conn").className = "conn live"; $("#conn").textContent = "live"; };
  es.onerror = () => {
    $("#conn").className = "conn down";
    $("#conn").textContent = "reconnecting…";
  };
  es.onmessage = ev => {
    let e;
    try { e = JSON.parse(ev.data); } catch { return; }
    handleEvent(e.type, e.data);
  };
}

function handleEvent(type, d) {
  switch (type) {
    case "item_started": {
      state.live.set(d.id, { progress: 0, stage: "downloading" });
      const it = state.items.find(x => x.id === d.id);
      if (it) { it.status = "downloading"; it.progress = 0; }
      const tr = state.queue.get(d.id);
      if (tr) { tr.className = "downloading"; const pill = $(".pill", tr); if (pill) { pill.className = "pill downloading"; pill.textContent = "downloading"; } }
      bumpStat("active", 1);
      break;
    }
    case "item_progress": {
      state.live.set(d.id, d);
      applyProgress(d.id, d);
      break;
    }
    case "item_stage": {
      const p = state.live.get(d.id) || {};
      p.stage = d.stage;
      state.live.set(d.id, p);
      const tr = state.queue.get(d.id);
      if (tr) { const pill = $(".pill", tr); if (pill) { pill.className = "pill downloading"; pill.textContent = d.stage; } }
      break;
    }
    case "item_done": {
      state.live.delete(d.id);
      bumpStat("active", -1);
      const it = state.items.find(x => x.id === d.id);
      const skipped = !!d.skipped;
      if (it) {
        it.status = skipped ? "skipped" : "done";
        it.progress = 100;
        it.filepath = d.filepath;
      }
      const tr = state.queue.get(d.id);
      if (tr) {
        tr.className = skipped ? "skipped" : "done";
        const pill = $(".pill", tr);
        if (pill) {
          pill.className = `pill ${skipped ? "skipped" : "done"}`;
          pill.textContent = skipped ? "skipped" : "done";
        }
        const cell = $(".col-progress", tr);
        if (cell) {
          cell.innerHTML = skipped
            ? `<span class="meta" title="${esc(d.reason || "")}">${esc(d.reason || "already have it")}</span>`
            : `<div class="progress">${bar(100, "done")}<span class="meta">done</span></div>`;
        }
      }
      if (skipped) bumpStat("skipped", 1); else bumpStat("done", 1);
      bumpStat("pending", -1);
      break;
    }
    case "item_retrying": {
      state.live.set(d.id, { progress: 0, stage: `retry ${d.attempt}/${d.of}` });
      const tr = state.queue.get(d.id);
      if (tr) {
        const pill = $(".pill", tr);
        if (pill) { pill.className = "pill downloading"; pill.textContent = `retry ${d.attempt}`; }
        const cell = $(".col-progress", tr);
        if (cell) cell.innerHTML = `<span class="meta" style="color:var(--warn)">retrying in ${d.delay}s (${esc((d.error || "").slice(0, 30))})</span>`;
      }
      break;
    }
    case "item_failed": {
      state.live.delete(d.id);
      bumpStat("active", -1);
      const it = state.items.find(x => x.id === d.id);
      if (it) { it.status = "failed"; it.error = d.error; }
      const tr = state.queue.get(d.id);
      if (tr) {
        tr.className = "failed";
        const pill = $(".pill", tr); if (pill) { pill.className = "pill failed"; pill.textContent = "failed"; }
        const cell = $(".col-progress", tr);
        if (cell) cell.innerHTML = `<span class="meta" style="color:var(--bad)" title="${esc(d.error)}">${esc((d.error || "").slice(0, 46))}</span>`;
      }
      bumpStat("failed", 1); bumpStat("pending", -1);
      logLine("error", `${d.title || "item"}: ${d.error}`);
      break;
    }
    case "run_started":
      state.run.running = true; state.run.paused = false; setRunUI();
      toast("Running", `${d.queued} items · ${d.workers} workers`, "ok");
      break;
    case "run_paused": state.run.paused = true; setRunUI(); break;
    case "run_resumed": state.run.paused = false; setRunUI(); break;
    case "run_stopping": state.run.running = false; setRunUI(); break;
    case "run_finished":
      state.run.running = false; state.run.paused = false;
      state.live.clear(); setRunUI();
      toast("Finished", `${d.stats.done} done · ${d.stats.failed} failed`, d.stats.failed ? "warn" : "ok");
      refreshAll();
      break;
    case "playlists_changed": loadPlaylists(); break;
    case "import_progress": {
      $("#import-hint").textContent = d.message || "";
      if (d.stage === "done") {
        $("#btn-import").disabled = false;
        $("#import-input").value = "";
        $("#import-hint").textContent = "";
        toast("Imported", d.message, "ok");
        loadPlaylists().then(() => { if (d.job) refreshPlaylistProgress(); });
        setTimeout(() => { if (state.currentPlaylist == null && state.playlists[0]) selectPlaylist(state.playlists[0].id); }, 400);
      } else if (d.stage === "error") {
        $("#btn-import").disabled = false;
        $("#import-hint").textContent = "";
      }
      break;
    }
    case "compare_progress":
      $("#compare-status").textContent = d.message || "";
      $("#btn-compare").disabled = d.stage !== "done" && d.stage !== "error";
      break;
    case "log": logLine(d.level, d.message); break;
  }
}

async function refreshPlaylistProgress() {
  await loadPlaylists();
}

function bumpStat(key, delta) {
  const map = {
    done: "#stat-done", pending: "#stat-pending", failed: "#stat-failed",
    active: "#stat-active", skipped: "#stat-skipped",
  };
  const el = $(map[key]);
  if (el) el.textContent = Math.max(0, (+el.textContent || 0) + delta);
}

async function refreshAll() {
  const s = await api("/api/state");
  state.run = s.run;
  updateStats(s.stats);
  setRunUI();
  await loadPlaylists();
  if (state.currentPlaylist) await loadItems();
}

/* -------------------------------------------------------------------- log */
const LOG_MAX = 500;
function logLine(level, message) {
  const view = $("#log-view");
  const el = document.createElement("div");
  el.className = `log-line ${level}`;
  const t = new Date().toLocaleTimeString();
  el.innerHTML = `<time>${t}</time><span>${esc(message)}</span>`;
  view.appendChild(el);
  while (view.childElementCount > LOG_MAX) view.removeChild(view.firstChild);
  if (view.scrollHeight - view.scrollTop - view.clientHeight < 120) view.scrollTop = view.scrollHeight;
}
$("#btn-clear-log").addEventListener("click", () => $("#log-view").replaceChildren());

/* ---------------------------------------------------------------- compare */
let comparePoll = null;

$("#compare-threshold").addEventListener("input", e => {
  const v = Number(e.target.value);
  $("#threshold-label").textContent = v <= 0.6 ? "loose" : v >= 0.85 ? "strict" : "balanced";
});

function renderComparePlaylists() {
  const sel = $("#compare-playlist");
  const cur = sel.value;
  sel.innerHTML = `<option value="">— choose —</option>` + state.playlists.map(p =>
    `<option value="${p.id}">${esc(p.name)} (${p.total})</option>`).join("");
  if (cur) sel.value = cur;
}

$("#compare-ignore-extra").addEventListener("change", () => {
  if (!state.lastCompare) return;
  renderCompare(state.lastCompare, $("#compare-ignore-extra").checked);
});

$("#btn-compare").addEventListener("click", async () => {
  const playlist_id = $("#compare-playlist").value;
  const folder = $("#compare-folder").value.trim();
  if (!playlist_id) { toast("Pick a playlist", "Choose which playlist to check.", "warn"); return; }
  if (!folder) { toast("Pick a folder", "Choose the folder to scan.", "warn"); return; }

  $("#btn-compare").disabled = true;
  $("#compare-status").textContent = "Starting…";
  try {
    const { job } = await api("/api/compare", {
      method: "POST",
      body: {
        playlist_id: Number(playlist_id),
        folder,
        threshold: Number($("#compare-threshold").value),
        recursive: $("#compare-recursive").checked,
        read_tags: $("#compare-read-tags").checked,
      },
    });
    pollJob(job);
  } catch (e) {
    $("#btn-compare").disabled = false;
    $("#compare-status").textContent = "";
    toast("Compare failed", e.message, "error");
  }
});

function pollJob(id) {
  clearInterval(comparePoll);
  comparePoll = setInterval(async () => {
    let job;
    try { ({ job } = await api(`/api/job/${id}`)); }
    catch { clearInterval(comparePoll); return; }
    if (job.status === "running") return;
    clearInterval(comparePoll);
    $("#btn-compare").disabled = false;
    if (job.status === "error") {
      $("#compare-status").textContent = "";
      toast("Compare failed", job.error, "error");
      return;
    }
    state.lastCompare = job.result;
    renderCompare(job.result, $("#compare-ignore-extra").checked);
    $("#compare-status").textContent = "";
    toast("Comparison complete",
      `${job.result.counts.missing} missing of ${job.result.counts.playlist} tracks`,
      job.result.counts.missing ? "warn" : "ok");
  }, 600);
}

function renderCompare(r, ignoreExtra) {
  $("#compare-results").hidden = false;
  const c = r.counts;
  $("#compare-summary").innerHTML = `
    <div class="summary-chip"><b>${c.playlist}</b>in playlist</div>
    <div class="summary-chip"><b>${c.folder}</b>files on disk</div>
    <div class="summary-chip missing"><b>${c.missing}</b>missing</div>
    <div class="summary-chip matched"><b>${c.matched}</b>matched</div>
    <div class="summary-chip extra"><b>${c.extra}</b>extra</div>`;

  $("#missing-table tbody").innerHTML = r.missing.length ? r.missing.map((m, i) => `
    <tr>
      <td class="col-num">${i + 1}</td>
      <td><div class="cell-title" title="${esc(m.title)}">${esc(m.title)}</div></td>
      <td>${esc(m.artist || "")}</td>
      <td><div class="cell-file" title="${esc((m.closest || {}).file || "")}">${
        m.closest ? `${esc(m.closest.name)} <span class="muted">(${m.closest.score})</span>` : "<span class='muted'>—</span>"
      }</div></td>
    </tr>`).join("") : `<tr><td colspan="4" class="empty">🎉 Nothing missing — every playlist track is on disk.</td></tr>`;

  $("#matched-table tbody").innerHTML = r.matched.length ? r.matched.map((m, i) => `
    <tr>
      <td class="col-num">${i + 1}</td>
      <td><div class="cell-title">${esc(m.artist ? m.artist + " - " + m.title : m.title)}</div></td>
      <td><div class="cell-file" title="${esc(m.file)}">${esc(m.file_name)}</div></td>
      <td class="col-score"><span class="pill ${m.score > 0.9 ? "done" : ""}">${m.score}</span></td>
    </tr>`).join("") : `<tr><td colspan="4" class="empty">No matches yet.</td></tr>`;

  $("#extra-table tbody").innerHTML = r.extra.length ? r.extra.map((m, i) => `
    <tr>
      <td class="col-num">${i + 1}</td>
      <td><div class="cell-file" title="${esc(m.file)}">${esc(m.name)}</div></td>
      <td>${esc(m.artist || "")}</td>
      <td>${esc(m.album || "")}</td>
    </tr>`).join("") : `<tr><td colspan="4" class="empty">No extra files.</td></tr>`;
}

$("#btn-export-missing").addEventListener("click", () => {
  const r = state.lastCompare;
  if (!r || !r.missing.length) { toast("Nothing to export", "", "warn"); return; }
  const lines = r.missing.map(m => m.artist ? `${m.artist} - ${m.title}` : m.title);
  const blob = new Blob([lines.join("\n")], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `missing-from-${r.label.replace(/\W+/g, "-").slice(0, 40)}.txt`;
  a.click();
  URL.revokeObjectURL(a.href);
});

$("#btn-import-missing").addEventListener("click", async () => {
  const r = state.lastCompare;
  if (!r || !r.missing.length) { toast("Nothing missing", "", "warn"); return; }
  try {
    const res = await api("/api/compare/import-missing", {
      method: "POST",
      body: {
        name: `Missing from ${r.label}`.slice(0, 90),
        items: r.missing.map(m => ({
          title: m.title, artist: m.artist, album: m.album,
          duration: m.duration, url: m.url,
        })),
      },
    });
    toast("Added to queue", `${res.added} tracks in a new playlist.`, "ok");
    await loadPlaylists();
    await selectPlaylist(res.playlist_id);
    $$(".tab").find(t => t.dataset.tab === "download")?.click();
  } catch (e) { toast("Could not add", e.message, "error"); }
});

/* ------------------------------------------------------------ folder popup */
$("#btn-browse").addEventListener("click", async () => {
  const start = $("#compare-folder").value || "";
  await openBrowser(start, path => { $("#compare-folder").value = path; closeModal(); });
});

async function openBrowser(path, onPick) {
  const data = await api(`/api/browse?path=${encodeURIComponent(path)}`);
  state.browse = data;
  $("#modal-path").textContent = data.path;
  $("#modal-list").innerHTML = data.entries.length
    ? data.entries.map(e => `<div class="modal-item" data-path="${esc(e.path)}">📁 ${esc(e.name)}</div>`).join("")
    : `<p class="empty">No sub-folders here.</p>`;
  $$("#modal-list .modal-item").forEach(el => el.addEventListener("click", () => openBrowser(el.dataset.path, onPick)));
  $("#modal-up").onclick = () => openBrowser(data.parent, onPick);
  $("#modal-pick").onclick = () => onPick(data.path);
  $("#modal").hidden = false;
}
function closeModal() { $("#modal").hidden = true; }
$("#modal-close").addEventListener("click", closeModal);
$("#modal").addEventListener("click", e => { if (e.target.id === "modal") closeModal(); });

/* --------------------------------------------------------------- kick-off */
(async function init() {
  try {
    await loadState();
    setRunUI();
    connectEvents();
    logLine("info", "Ready. Import a playlist to begin.");
  } catch (e) {
    toast("Could not reach the app", e.message, "error");
    $("#conn").className = "conn down";
    $("#conn").textContent = "offline";
  }
})();
