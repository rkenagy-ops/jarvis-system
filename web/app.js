const $ = (id) => document.getElementById(id);

const state = {
  sessionId: localStorage.getItem("jarvis.session") || crypto.randomUUID(),
  live: false,
  rec: false,
  media: null,
  chunks: [],
  ws: null,
  audioCtx: null,
  playTime: 0,
};

localStorage.setItem("jarvis.session", state.sessionId);

function setStatus(text) {
  $("status").textContent = text.toUpperCase();
}

function addMsg(role, text, who) {
  if (!text) return;
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.innerHTML = `<div class="who">${who || role}</div><div></div>`;
  el.lastChild.textContent = text;
  $("transcript").appendChild(el);
  $("transcript").scrollTop = $("transcript").scrollHeight;
}

function addMind(kind, title, body) {
  const el = document.createElement("div");
  el.className = `item ${kind}`;
  el.innerHTML = `<b>${title}</b><div></div>`;
  el.lastChild.textContent = body;
  const feed = $("mind");
  feed.prepend(el);
  while (feed.children.length > 24) feed.lastChild.remove();
}

function setAgentBusy(id, busy) {
  const node = document.querySelector(`[data-agent="${id}"]`);
  if (node) node.classList.toggle("busy", busy);
}

async function refreshStatus() {
  const res = await fetch("/api/status");
  const data = await res.json();
  $("xai-dot").className = `dot ${data.xai_configured ? "on" : "off"}`;
  $("gh-dot").className = `dot ${data.github_configured ? "on" : "off"}`;
  $("xai-label").textContent = data.xai_configured ? "XAI READY" : "XAI MISSING";
  const gh = data.github && data.github.login;
  $("gh-label").textContent = gh ? `GH ${gh}` : data.github_configured ? "GITHUB" : "GH MISSING";
  if (!data.xai_configured) $("modal").classList.add("show");

  const box = $("agents");
  box.innerHTML = "";
  (data.agents || []).forEach((a) => {
    const row = document.createElement("div");
    row.className = "agent";
    row.dataset.agent = a.id;
    row.innerHTML = `<span class="dot on" style="background:${a.color}"></span>
      <div><div class="name">${a.name}</div><div class="role">${a.role}</div></div>
      <span class="role">${a.can_spawn ? "LEAD" : "NODE"}</span>`;
    box.appendChild(row);
  });

  const mem = data.memory || {};
  $("mind").innerHTML = "";
  (mem.recent_insights || []).forEach((i) => addMind("insight", i.agent, i.claim));
  (mem.facts_list || []).slice(0, 6).forEach((f) => addMind("fact", f.key, f.value));
  refreshWidgets();
}

async function refreshWidgets() {
  try {
    const [m, a] = await Promise.all([
      fetch("/api/markets").then((r) => r.json()),
      fetch("/api/autonomy").then((r) => r.json()),
    ]);
    const box = $("tickers");
    if (box) {
      box.innerHTML = "";
      (m.watchlist || []).forEach((q) => {
        if (!q.symbol || q.error) return;
        const el = document.createElement("div");
        const pct = q.change_pct;
        el.className = `ticker ${pct > 0 ? "up" : pct < 0 ? "down" : ""}`;
        el.innerHTML = `<div>${q.symbol}</div><div class="px">${q.price != null ? Number(q.price).toFixed(2) : "—"} ${pct != null ? `(${pct.toFixed(2)}%)` : ""}</div>`;
        box.appendChild(el);
      });
    }
    const acc = m.account || {};
    if ($("equity")) {
      $("equity").textContent = `${(acc.mode || "paper").toUpperCase()} EQ ${acc.equity != null ? Number(acc.equity).toFixed(2) : "—"}  CASH ${acc.cash != null ? Number(acc.cash).toFixed(2) : "—"}`;
    }
    const auto = $("auto");
    if (auto) {
      auto.innerHTML = "";
      (a.jobs || []).forEach((j) => {
        const el = document.createElement("div");
        el.className = "item";
        el.innerHTML = `<b>${j.name}</b><div></div>`;
        el.lastChild.textContent = `${j.enabled ? "ON" : "OFF"} / ${j.every_sec}s — ${j.last_result || "pending"}`;
        auto.appendChild(el);
      });
      (a.goals || []).forEach((g) => {
        const el = document.createElement("div");
        el.className = "item insight";
        el.innerHTML = `<b>GOAL</b><div></div>`;
        el.lastChild.textContent = g.title;
        auto.appendChild(el);
      });
    }
    const sk = $("skills");
    if (sk) {
      sk.innerHTML = "";
      (a.skills || []).forEach((s) => {
        const el = document.createElement("div");
        el.className = "item";
        el.innerHTML = `<b>${s.name}</b><div></div>`;
        el.lastChild.textContent = `${s.uses} uses — ${s.playbook}`;
        sk.appendChild(el);
      });
    }
  } catch {}
}

function handleEvent(ev) {
  if (ev.type === "session") state.sessionId = ev.session_id;
  if (ev.type === "status") setStatus(ev.text || ev.event || "working");
  if (ev.type === "agent_start") {
    setAgentBusy(ev.agent, true);
    setStatus(`${ev.agent} engaged`);
  }
  if (ev.type === "agent_done") setAgentBusy(ev.agent, false);
  if (ev.type === "swarm") {
    setStatus(`swarm ${ (ev.agents || []).join(" · ") }`);
    addMind("insight", "SWARM", ev.task);
  }
  if (ev.type === "tool_call") {
    addMind("item", ev.name, JSON.stringify(ev.arguments || {}).slice(0, 180));
    setStatus(`tool ${ev.name}`);
  }
  if (ev.type === "tool_result") {
    const preview = typeof ev.result === "string" ? ev.result : JSON.stringify(ev.result);
    addMind("item", `${ev.name} ✓`, String(preview).slice(0, 220));
  }
  if (ev.type === "insight") addMind("insight", ev.agent, ev.text);
  if (ev.type === "token") {
    $("orb").classList.add("talk");
    let last = $("transcript").querySelector(".msg.assistant:last-child .stream");
    if (!last) {
      const wrap = document.createElement("div");
      wrap.className = "msg assistant";
      wrap.innerHTML = `<div class="who">${(ev.agent || "jarvis").toUpperCase()}</div><div class="stream"></div>`;
      $("transcript").appendChild(wrap);
      last = wrap.querySelector(".stream");
    }
    last.textContent += ev.text;
    $("transcript").scrollTop = $("transcript").scrollHeight;
  }
  if (ev.type === "assistant") addMsg("assistant", ev.text, "JARVIS");
  if (ev.type === "user") addMsg("user", ev.text, "YOU");
  if (ev.type === "error") {
    setStatus(ev.message);
    addMsg("assistant", ev.message, "SYSTEM");
  }
  if (ev.type === "done") {
    $("orb").classList.remove("talk");
    setAgentBusy(ev.agent || "jarvis", false);
    setStatus("systems ready");
    if (ev.text && ev.speak !== false) maybeSpeak(ev.text);
  }
}

async function sendText(text, { speak = true } = {}) {
  if (!text.trim()) return;
  addMsg("user", text, "YOU");
  $("input").value = "";
  setStatus("thinking");
  $("orb").classList.add("talk");
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text, session_id: state.sessionId }),
  });
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop();
    for (const part of parts) {
      const line = part.replace(/^data: /, "");
      if (!line) continue;
      try { handleEvent({ speak, ...JSON.parse(line) }); } catch {}
    }
  }
  $("orb").classList.remove("talk");
}

async function maybeSpeak(text) {
  if (state.live || !text) return;
  try {
    const body = new FormData();
    body.append("text", text.slice(0, 1200));
    const res = await fetch("/api/voice/tts", { method: "POST", body });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => URL.revokeObjectURL(url);
    await audio.play();
  } catch {}
}

async function startHoldToTalk() {
  state.media = await navigator.mediaDevices.getUserMedia({ audio: true });
  state.chunks = [];
  const rec = new MediaRecorder(state.media);
  state.recorder = rec;
  rec.ondataavailable = (e) => { if (e.data.size) state.chunks.push(e.data); };
  rec.onstop = async () => {
    $("orb").classList.remove("listen");
    $("mic").classList.remove("rec");
    const blob = new Blob(state.chunks, { type: rec.mimeType || "audio/webm" });
    state.media.getTracks().forEach((t) => t.stop());
    const fd = new FormData();
    fd.append("file", blob, "speech.webm");
    setStatus("transcribing");
    const res = await fetch("/api/voice/stt", { method: "POST", body: fd });
    const data = await res.json();
    if (data.text) await sendText(data.text);
    else setStatus("no speech detected");
  };
  rec.start();
  state.rec = true;
  $("orb").classList.add("listen");
  $("mic").classList.add("rec");
  setStatus("listening");
}

function stopHoldToTalk() {
  if (state.recorder && state.rec) {
    state.rec = false;
    state.recorder.stop();
  }
}

function pcmToBase64(float32) {
  const pcm = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const bytes = new Uint8Array(pcm.buffer);
  let bin = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(bin);
}

function playPcm16(b64) {
  const ctx = state.audioCtx || new AudioContext({ sampleRate: 24000 });
  state.audioCtx = ctx;
  const raw = atob(b64);
  const buf = new ArrayBuffer(raw.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < raw.length; i++) view[i] = raw.charCodeAt(i);
  const pcm = new Int16Array(buf);
  const audio = ctx.createBuffer(1, pcm.length, 24000);
  const ch = audio.getChannelData(0);
  for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 32768;
  const src = ctx.createBufferSource();
  src.buffer = audio;
  src.connect(ctx.destination);
  const now = ctx.currentTime;
  if (state.playTime < now) state.playTime = now;
  src.start(state.playTime);
  state.playTime += audio.duration;
  $("orb").classList.add("talk");
  src.onended = () => $("orb").classList.remove("talk");
}

async function toggleLive() {
  if (state.live) {
    state.live = false;
    if (state.ws) state.ws.close();
    if (state.media) state.media.getTracks().forEach((t) => t.stop());
    $("btn-live").classList.remove("on");
    setStatus("live voice offline");
    return;
  }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/live?session_id=${state.sessionId}`);
  state.ws = ws;
  ws.onopen = async () => {
    state.live = true;
    $("btn-live").classList.add("on");
    setStatus("live voice online");
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    state.media = stream;
    const ctx = new AudioContext({ sampleRate: 24000 });
    state.audioCtx = ctx;
    const src = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    const mute = ctx.createGain();
    mute.gain.value = 0;
    src.connect(proc);
    proc.connect(mute);
    mute.connect(ctx.destination);
    proc.onaudioprocess = (e) => {
      if (!state.live || ws.readyState !== 1) return;
      const data = e.inputBuffer.getChannelData(0);
      ws.send(JSON.stringify({ type: "audio", data: pcmToBase64(data) }));
    };
    state.processor = proc;
  };
  ws.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    if (ev.type === "audio" && ev.data) playPcm16(ev.data);
    else handleEvent(ev);
  };
  ws.onclose = () => {
    state.live = false;
    $("btn-live").classList.remove("on");
    setStatus("live voice closed");
  };
}

$("form").addEventListener("submit", (e) => {
  e.preventDefault();
  sendText($("input").value);
});
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendText($("input").value);
  }
});
$("mic").addEventListener("mousedown", startHoldToTalk);
$("mic").addEventListener("mouseup", stopHoldToTalk);
$("mic").addEventListener("mouseleave", stopHoldToTalk);
$("mic").addEventListener("touchstart", (e) => { e.preventDefault(); startHoldToTalk(); });
$("mic").addEventListener("touchend", (e) => { e.preventDefault(); stopHoldToTalk(); });
$("btn-live").addEventListener("click", toggleLive);
$("btn-settings").addEventListener("click", () => $("modal").classList.add("show"));
$("close-modal").addEventListener("click", () => $("modal").classList.remove("show"));
$("save-keys").addEventListener("click", async () => {
  await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      xai_api_key: $("key-xai").value || undefined,
      github_token: $("key-gh").value || undefined,
      github_username: $("key-user").value || undefined,
      voice: $("key-voice").value,
    }),
  });
  $("modal").classList.remove("show");
  refreshStatus();
});

refreshStatus().catch(() => setStatus("backend offline"));
setInterval(refreshWidgets, 60000);
setStatus("systems ready — good evening");
