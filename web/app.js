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
  useBrowserVoice: true,
};

localStorage.setItem("jarvis.session", state.sessionId);
state.token = localStorage.getItem("jarvis.token") || "";
const _fetch = window.fetch.bind(window);
window.fetch = (input, init = {}) => {
  const url = typeof input === "string" ? input : (input && input.url) || "";
  if (typeof url === "string" && url.startsWith("/api/") && state.token) {
    const headers = new Headers(init.headers || (input && input.headers) || {});
    headers.set("X-Jarvis-Token", state.token);
    init = Object.assign({}, init, { headers });
  }
  return _fetch(input, init);
};

async function bootstrapGuard() {
  try {
    const res = await _fetch("/api/guard/bootstrap");
    if (!res.ok) return;
    const data = await res.json();
    if (data.token) {
      state.token = data.token;
      localStorage.setItem("jarvis.token", data.token);
    }
  } catch {}
}

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
  if (res.status === 401) {
    await bootstrapGuard();
    const retry = await fetch("/api/status");
    if (!retry.ok) throw new Error("jarvis locked");
    return applyStatus(await retry.json());
  }
  if (!res.ok) throw new Error("status " + res.status);
  return applyStatus(await res.json());
}

function applyStatus(data) {
  $("xai-dot").className = `dot ${data.xai_configured ? "on" : "off"}`;
  $("gh-dot").className = `dot ${data.github_configured ? "on" : "off"}`;
  $("xai-label").textContent = data.xai_configured ? "XAI KEY" : "XAI MISSING";
  const grok = data.brain === "grok";
  const local = data.brain === "ollama";
  $("brain-dot").className = `dot ${grok ? "on" : local ? "warn" : "warn"}`;
  $("brain-label").textContent = grok ? "GROK" : local ? "OLLAMA" : (data.offline ? "OFFLINE" : "FREE APIS");
  state.useBrowserVoice = !grok;
  if ($("ollama-label")) {
    const ol = data.ollama || {};
    $("ollama-dot").className = `dot ${ol.ok ? "on" : "off"}`;
    $("ollama-label").textContent = ol.ok ? `OLLAMA ${ol.model || ""}`.trim() : "OLLAMA OFF";
  }
  const gh = data.github && data.github.login;
  $("gh-dot").className = `dot ${gh ? "on" : data.github && data.github.error ? "warn" : data.github_configured ? "warn" : "off"}`;
  $("gh-label").textContent = gh ? `GH ${gh}` : (data.github && data.github.error ? "GH AUTH" : data.github_configured ? "GITHUB" : "GH MISSING");
  if (!data.xai_configured) $("modal").classList.add("show");
  const fort = data.fortress || {};
  if ($("lock-label")) {
    $("lock-dot").className = `dot ${fort.loopback_only ? "on" : "warn"}`;
    $("lock-label").textContent = fort.loopback_only ? "LOCAL" : "LAN";
  }
  if ($("net-label")) {
    $("net-dot").className = `dot ${data.online === false ? "off" : "on"}`;
    $("net-label").textContent = data.online === false ? "OFFLINE" : "OUTBOUND";
  }

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

function renderQuotes(quotes) {
  const box = $("tickers");
  if (!box) return;
  box.innerHTML = "";
  (quotes || []).forEach((q) => {
    if (!q.symbol || q.error) return;
    const el = document.createElement("div");
    const pct = q.change_pct;
    el.className = `ticker ${pct > 0 ? "up" : pct < 0 ? "down" : ""}`;
    el.innerHTML = `<div>${q.symbol}</div><div class="px">${q.price != null ? Number(q.price).toFixed(2) : "—"} ${pct != null ? `(${Number(pct).toFixed(2)}%)` : ""}</div>`;
    box.appendChild(el);
  });
}

function renderFeeds(data) {
  if (!data) return;
  renderQuotes(data.quotes || []);
  const news = data.news || [];
  const tape = $("tape-inner");
  if (tape && news.length) {
    tape.innerHTML = news.map((n) => {
      const src = (n.source || "wire").toUpperCase();
      const href = n.link || "#";
      const title = (n.title || "").replace(/</g, "");
      return `<a href="${href}" target="_blank" rel="noreferrer">[${src}] ${title}</a>`;
    }).join("");
  }
  const box = $("newsfeed");
  if (box) {
    box.innerHTML = "";
    news.slice(0, 10).forEach((n) => {
      const el = document.createElement("div");
      el.className = "item click";
      el.innerHTML = `<b>${n.source || "wire"}</b><div></div>`;
      el.lastChild.textContent = n.title || "";
      if (n.link) el.addEventListener("click", () => window.open(n.link, "_blank", "noopener"));
      box.appendChild(el);
    });
  }
}

function startLiveFeeds() {
  if (state.feedEs) return;
  const url = `/api/feeds/stream?token=${encodeURIComponent(state.token || "")}`;
  try {
    const es = new EventSource(url);
    es.onmessage = (ev) => {
      try { renderFeeds(JSON.parse(ev.data)); } catch {}
    };
    es.onerror = () => {};
    state.feedEs = es;
  } catch {}
  fetch("/api/feeds").then((r) => r.json()).then(renderFeeds).catch(() => {});
}

async function refreshWidgets() {
  try {
    const [m, a, v] = await Promise.all([
      fetch("/api/markets").then((r) => r.json()),
      fetch("/api/autonomy").then((r) => r.json()),
      fetch("/api/vault").then((r) => r.json()).catch(() => ({ notes: [] })),
    ]);
    renderQuotes(m.watchlist || []);
    const acc = m.account || {};
    if ($("equity")) {
      $("equity").textContent = `${(acc.mode || "paper").toUpperCase()} EQ ${acc.equity != null ? Number(acc.equity).toFixed(2) : "—"}  CASH ${acc.cash != null ? Number(acc.cash).toFixed(2) : "—"}`;
    }
    try {
      const ib = await fetch("/api/ibkr/status").then((r) => r.json());
      const lab = $("ibkr-label");
      const dot = $("ibkr-dot");
      if (lab && dot) {
        if (ib.ok) {
          dot.className = "dot on";
          lab.textContent = ib.gateway_live ? "IBKR LIVE" : "IBKR PAPER";
        } else if (ib.tws && ib.tws.login_screen) {
          dot.className = "dot warn";
          lab.textContent = "IBKR LOGIN";
        } else if (ib.tws && ib.tws.process) {
          dot.className = "dot warn";
          lab.textContent = "IBKR API OFF";
        } else {
          dot.className = "dot off";
          lab.textContent = "IBKR OFF";
        }
      }
    } catch {}
    try {
      const fin = await fetch("/api/finish").then((r) => r.json());
      const fbox = $("finish");
      if (fbox) {
        fbox.innerHTML = "";
        (fin.items || []).forEach((it) => {
          const el = document.createElement("div");
          el.className = "item";
          el.innerHTML = `<b>${it.ok ? "ok" : "todo"}</b><div></div>`;
          el.lastChild.textContent = it.label;
          fbox.appendChild(el);
        });
      }
    } catch {}
    try {
      const today = await fetch("/api/daily").then((r) => r.json());
      const tbox = $("today");
      if (tbox) {
        tbox.innerHTML = "";
        const bits = [
          ["hello", today.greeting],
          ["vault", today.vault],
          ["obsidian", today.obsidian_installed ? "installed" : "not installed — VAULT still opens the folder"],
        ];
        ((today.calendar && today.calendar.events) || []).slice(0, 4).forEach((e) => {
          bits.push(["cal", `${(e.start || "").slice(11, 16)} ${e.subject || ""}`]);
        });
        (today.meetings || []).slice(0, 3).forEach((m) => bits.push(["mtg", m.title || m.path]));
        (today.goals || []).slice(0, 3).forEach((g) => bits.push(["goal", g.title]));
        (today.tasks || []).slice(0, 3).forEach((task) => bits.push(["task", task.text]));
        bits.forEach(([k, v]) => {
          if (!v) return;
          const el = document.createElement("div");
          el.className = "item";
          el.innerHTML = `<b>${k}</b><div></div>`;
          el.lastChild.textContent = v;
          tbox.appendChild(el);
        });
      }
    } catch {}
    try {
      const room = await fetch("/api/room").then((r) => r.json());
      const rbox = $("room");
      if (rbox) {
        rbox.innerHTML = "";
        (room.lines || []).slice(-8).forEach((line) => {
          const el = document.createElement("div");
          el.className = "item";
          el.innerHTML = `<b>${line.who || "room"}</b><div></div>`;
          el.lastChild.textContent = line.text || "";
          rbox.appendChild(el);
        });
        if (!(room.lines || []).length) {
          rbox.innerHTML = `<div class="item"><b>quiet</b><div>WAKE to fill the room</div></div>`;
        }
      }
    } catch {}
    try {
      const due = await fetch("/api/reminders").then((r) => r.json());
      const dbox = $("due");
      if (dbox) {
        dbox.innerHTML = "";
        (due.open || []).slice(0, 8).forEach((item) => {
          const el = document.createElement("div");
          el.className = "item click";
          el.innerHTML = `<b>${item.kind || "due"}</b><div></div>`;
          el.lastChild.textContent = `${item.title} — ${String(item.when || "").slice(11, 16)} UTC`;
          el.addEventListener("click", async () => {
            await fetch("/api/reminders/dismiss", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ id: item.id }),
            });
            refreshWidgets();
          });
          dbox.appendChild(el);
        });
        if (!(due.open || []).length) {
          dbox.innerHTML = `<div class="item"><b>clear</b><div>no open timers</div></div>`;
        }
      }
    } catch {}
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
    const vaultEl = $("vault");
    if (vaultEl) {
      vaultEl.innerHTML = "";
      (v.notes || []).slice(0, 10).forEach((n) => {
        const el = document.createElement("div");
        el.className = "item click";
        el.innerHTML = `<b>${n.title}</b><div></div>`;
        el.lastChild.textContent = n.path;
        el.addEventListener("click", () => openNote(n.path));
        vaultEl.appendChild(el);
      });
    }
    try {
      const cat = await fetch("/api/catalog").then((r) => r.json());
      const cbox = $("catalog");
      if (cbox) {
        cbox.innerHTML = "";
        (cat.sources || []).slice(0, 16).forEach((s) => {
          const el = document.createElement("div");
          el.className = "item";
          el.innerHTML = `<b>${s.id}</b><div></div>`;
          el.lastChild.textContent = s.desc;
          cbox.appendChild(el);
        });
      }
    } catch {}
    try {
      const t = await fetch("/api/tasks").then((r) => r.json());
      const box = $("tasks");
      if (box) {
        box.innerHTML = "";
        (t.tasks || []).slice(0, 8).forEach((task) => {
          const el = document.createElement("div");
          el.className = "item click";
          el.innerHTML = `<b>○</b><div></div>`;
          el.lastChild.textContent = task.text;
          el.addEventListener("click", async () => {
            await fetch("/api/tasks/toggle", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ path: task.path, line: task.line }),
            });
            refreshWidgets();
          });
          box.appendChild(el);
        });
      }
    } catch {}
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
  if (ev.type === "assistant_delta" && ev.text) {
    // Live voice streams its transcript through this event; nothing consumed it,
    // so the spoken answer left no trace on screen until the turn ended.
    $("orb").classList.add("talk");
    let last = $("transcript").querySelector(".msg.assistant:last-child .stream");
    if (!last) {
      const wrap = document.createElement("div");
      wrap.className = "msg assistant";
      wrap.innerHTML = `<div class="who">JARVIS</div><div class="stream"></div>`;
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
  if (ev.type === "speak" && ev.text && !state.live) {
    state.spokeEarly = true;
    maybeSpeak(ev.text);
  }
  if (ev.type === "done") {
    $("orb").classList.remove("talk");
    setAgentBusy(ev.agent || "jarvis", false);
    setStatus("systems ready");
    if (ev.text && ev.speak !== false && !state.live && !state.spokeEarly) maybeSpeak(ev.text);
    state.spokeEarly = false;
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

function spokenExcerpt(text, limit = 180) {
  const cleaned = String(text || "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/[#*_>`]+/g, " ")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
  const parts = cleaned.split(/(?<=[.!?])\s+/).filter(Boolean);
  const out = [];
  for (const part of parts) {
    if (out.length && out[out.length - 1].toLowerCase() === part.toLowerCase()) continue;
    out.push(part);
    if (out.join(" ").length >= limit || out.length >= 2) break;
  }
  return out.join(" ").slice(0, limit);
}

function stopSpeech() {
  if (window.speechSynthesis) speechSynthesis.cancel();
  if (state.audio) {
    try { state.audio.pause(); } catch {}
    state.audio.src = "";
    state.audio = null;
  }
}

function browserSpeak(text) {
  if (!window.speechSynthesis) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(spokenExcerpt(text));
  u.rate = 1.02;
  speechSynthesis.speak(u);
}

async function maybeSpeak(text) {
  if (state.live || !text) return;
  const spoken = spokenExcerpt(text);
  if (!spoken) return;
  const now = Date.now();
  if (state.lastSpoken === spoken && now - (state.lastSpokenAt || 0) < 8000) return;
  state.lastSpoken = spoken;
  state.lastSpokenAt = now;
  stopSpeech();
  if (state.useBrowserVoice) {
    browserSpeak(spoken);
    return;
  }
  try {
    const body = new FormData();
    body.append("text", spoken);
    const res = await fetch("/api/voice/tts", { method: "POST", body });
    if (!res.ok) {
      browserSpeak(spoken);
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    state.audio = audio;
    audio.onended = () => {
      URL.revokeObjectURL(url);
      if (state.audio === audio) state.audio = null;
    };
    await audio.play();
  } catch {}
}

async function startHoldToTalk() {
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (state.useBrowserVoice && Rec) {
    const rec = new Rec();
    rec.lang = "en-US";
    rec.onresult = (e) => {
      const said = e.results[0][0].transcript;
      $("orb").classList.remove("listen");
      $("mic").classList.remove("rec");
      if (said) sendText(said);
    };
    rec.onerror = () => {
      $("orb").classList.remove("listen");
      $("mic").classList.remove("rec");
      setStatus("browser mic error");
    };
    rec.start();
    state.rec = true;
    $("orb").classList.add("listen");
    $("mic").classList.add("rec");
    setStatus("listening (browser)");
    state.browserRec = rec;
    return;
  }
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
  if (state.browserRec && state.rec) {
    try { state.browserRec.stop(); } catch {}
    state.rec = false;
    return;
  }
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
  if (ctx.state === "suspended") ctx.resume();
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
  if (!state.playTime || state.playTime < now) state.playTime = now;
  if (state.playTime > now + 0.9) return;
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
  const ws = new WebSocket(`${proto}://${location.host}/ws/live?session_id=${state.sessionId}&token=${encodeURIComponent(state.token || "")}`);
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
      const now = ctx.currentTime;
      if ((state.playTime || 0) > now + 0.08) {
        ws.send(JSON.stringify({ type: "audio", data: pcmToBase64(new Float32Array(data.length)) }));
        return;
      }
      ws.send(JSON.stringify({ type: "audio", data: pcmToBase64(data) }));
    };
    state.processor = proc;
  };
  ws.onmessage = (m) => {
    // The server relays upstream binary frames as-is, and a Blob is not JSON.
    // Parsing it unconditionally threw and silently dropped the message.
    if (typeof m.data !== "string") return;
    let ev;
    try { ev = JSON.parse(m.data); } catch { return; }
    if (ev.type === "audio" && ev.data) playPcm16(ev.data);
    else handleEvent(ev);
  };
  ws.onerror = () => setStatus("live voice socket error - see the server log");
  ws.onclose = (e) => {
    state.live = false;
    $("btn-live").classList.remove("on");
    // 4401 is our own code for a rejected token. "closed" told you nothing.
    if (e && e.code === 4401) {
      setStatus("live voice refused: bad token - reload the HUD");
      addMsg("assistant", "Live voice was refused because the token was rejected. Reload the HUD to pick up a fresh one.", "SYSTEM");
    } else {
      setStatus("live voice closed");
    }
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
function toggleWake() {
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Rec) {
    setStatus("wake needs chrome speech recognition");
    return;
  }
  if (state.wake) {
    state.wake = false;
    try { state.wakeRec.stop(); } catch {}
    $("btn-wake").classList.remove("on");
    setStatus("wake word off");
    return;
  }
  const rec = new Rec();
  rec.continuous = true;
  rec.interimResults = false;
  rec.lang = "en-US";
  rec.onresult = (e) => {
    const said = e.results[e.results.length - 1][0].transcript || "";
    const low = said.toLowerCase();
    fetch("/api/room/hear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ who: "room", text: said }),
    }).catch(() => {});
    if (!/\bjarvis\b/.test(low)) return;
    const rest = said.replace(/jarvis[,:]?\s*/i, "").trim();
    setStatus("wake heard");
    $("orb").classList.add("listen");
    if (rest) sendText(rest);
    else setStatus("listening after jarvis");
  };
  rec.onend = () => {
    if (state.wake) try { rec.start(); } catch {}
  };
  rec.start();
  state.wake = true;
  state.wakeRec = rec;
  $("btn-wake").classList.add("on");
  setStatus("say jarvis");
}
$("btn-ms").addEventListener("click", async () => {
  setStatus("microsoft login");
  const res = await fetch("/api/microsoft/login", { method: "POST" });
  const data = await res.json();
  if (data.user_code) {
    addMsg("assistant", `${data.message || "Open " + data.verification_uri + " and enter " + data.user_code}`, "MICROSOFT");
    if (data.verification_uri) window.open(data.verification_uri, "_blank", "noopener");
  } else {
    addMsg("assistant", data.error || JSON.stringify(data), "MICROSOFT");
  }
  setStatus(data.ok ? "enter the code at microsoft.com/devicelogin" : "microsoft setup needed");
});
$("btn-backup").addEventListener("click", async () => {
  setStatus("backing up");
  const res = await fetch("/api/backup", { method: "POST" });
  const data = await res.json();
  setStatus(data.ok ? `backup ${data.files} files` : (data.error || "backup failed"));
  addMsg("assistant", data.path || JSON.stringify(data), "BACKUP");
});
$("btn-vault").addEventListener("click", async () => {
  setStatus("opening vault");
  const res = await fetch("/api/daily/vault", { method: "POST" });
  const data = await res.json();
  setStatus(data.ok ? `vault ${data.via}` : (data.error || "vault failed"));
});
$("btn-wake").addEventListener("click", toggleWake);
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
      wordpress_url: $("key-wp") && $("key-wp").value || undefined,
      wordpress_user: $("key-wp-user") && $("key-wp-user").value || undefined,
      wordpress_app_password: $("key-wp-pass") && $("key-wp-pass").value || undefined,
      x_bearer_token: $("key-x") && $("key-x").value || undefined,
      x_api_key: $("key-x-key") && $("key-x-key").value || undefined,
      x_api_secret: $("key-x-secret") && $("key-x-secret").value || undefined,
      x_access_token: $("key-x-access") && $("key-x-access").value || undefined,
      x_access_secret: $("key-x-access-secret") && $("key-x-access-secret").value || undefined,
      postiz_url: $("key-postiz") && $("key-postiz").value || undefined,
      publer_api_key: $("key-publer") && $("key-publer").value || undefined,
      publer_workspace_id: $("key-publer-ws") && $("key-publer-ws").value || undefined,
      klaviyo_api_key: $("key-klaviyo") && $("key-klaviyo").value || undefined,
      manychat_api_token: $("key-manychat") && $("key-manychat").value || undefined,
      clickfunnels_api_key: $("key-cf") && $("key-cf").value || undefined,
      clickfunnels_api_base: $("key-cf-base") && $("key-cf-base").value || undefined,
      alpaca_key_id: $("key-alpaca-id") && $("key-alpaca-id").value || undefined,
      alpaca_secret_key: $("key-alpaca-secret") && $("key-alpaca-secret").value || undefined,
      alpaca_live: $("key-alpaca-live") && $("key-alpaca-live").value === "true",
      ms_client_id: $("key-ms-client") && $("key-ms-client").value || undefined,
      ms_tenant: $("key-ms-tenant") && $("key-ms-tenant").value || undefined,
      ibkr_port: $("key-ibkr-port") && $("key-ibkr-port").value ? Number($("key-ibkr-port").value) : undefined,
      ibkr_live: $("key-ibkr-live") && $("key-ibkr-live").value === "" ? undefined : $("key-ibkr-live") && $("key-ibkr-live").value === "true",
      marketbeast_root: $("key-beast-root") && $("key-beast-root").value || undefined,
    }),
  });
  $("modal").classList.remove("show");
  refreshStatus();
});

async function openNote(path) {
  const res = await fetch(`/api/vault/note?path=${encodeURIComponent(path)}`);
  const data = await res.json();
  $("note-title").textContent = path;
  $("note-body").textContent = data.text || data.error || "";
  $("note-modal").classList.add("show");
}

$("close-note").addEventListener("click", () => $("note-modal").classList.remove("show"));
$("btn-brief").addEventListener("click", async () => {
  setStatus("compiling briefing");
  const res = await fetch("/api/briefing", { method: "POST" });
  const data = await res.json();
  addMsg("assistant", data.text || "briefing done", "BRIEFING");
  if (data.text) maybeSpeak(data.text);
  refreshWidgets();
  setStatus("briefing written to daily note");
});
document.querySelectorAll("#chips button").forEach((btn) => {
  btn.addEventListener("click", () => sendText(btn.dataset.q));
});
$("upload").addEventListener("change", async (e) => {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  fd.append("dest", "inbox");
  const res = await fetch("/api/workspace/upload", { method: "POST", body: fd });
  const data = await res.json();
  addMsg("assistant", `Stored ${data.path} (${data.bytes} bytes). Ask me to analyze it.`, "WORKSPACE");
  e.target.value = "";
});

async function loadStudio() {
  const dash = await fetch("/api/ops").then((r) => r.json());
  const box = $("studio-queue");
  if (!box) return;
  box.innerHTML = "";
  [...(dash.scheduled || []), ...(dash.drafts || [])].slice(0, 12).forEach((c) => {
    const el = document.createElement("div");
    el.className = "item";
    el.innerHTML = `<b>${c.status}</b><div></div>`;
    el.lastChild.textContent = `${c.title} — ${(c.platforms || []).join(",")}`;
    box.appendChild(el);
  });
}

$("btn-studio").addEventListener("click", () => {
  $("studio-modal").classList.add("show");
  loadStudio();
});
$("close-studio").addEventListener("click", () => $("studio-modal").classList.remove("show"));
$("studio-body").addEventListener("input", () => {
  $("studio-preview").textContent = $("studio-body").value;
});

async function saveDraft(schedule) {
  const plats = $("studio-plats").value.split(",").map((s) => s.trim()).filter(Boolean);
  const res = await fetch("/api/ops/draft", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: $("studio-title").value || "Untitled",
      body: $("studio-body").value,
      kind: $("studio-kind").value,
      platforms: plats,
    }),
  });
  const item = await res.json();
  if (schedule && $("studio-when").value && item.id) {
    await fetch("/api/ops/schedule", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: item.id, when: $("studio-when").value, platforms: plats }),
    });
  }
  addMsg("assistant", `Draft saved: ${item.title || item.id}`, "STUDIO");
  loadStudio();
}
$("studio-save").addEventListener("click", () => saveDraft(false));
$("studio-sched").addEventListener("click", () => saveDraft(true));

function initLivingHud() {
  const ticks = $("ticks");
  if (ticks && !ticks.childElementCount) {
    for (let i = 0; i < 60; i += 1) {
      const el = document.createElement("div");
      el.className = "tick";
      el.style.transform = `rotate(${i * 6}deg)`;
      el.style.opacity = i % 5 === 0 ? "0.9" : "0.28";
      el.style.height = i % 5 === 0 ? "11px" : "6px";
      ticks.appendChild(el);
    }
  }
  const canvas = $("field");
  const hud = $("hud");
  if (canvas && hud && canvas.getContext) {
    const ctx = canvas.getContext("2d");
    const dots = Array.from({ length: 52 }, () => ({
      a: Math.random() * Math.PI * 2,
      r: 0.32 + Math.random() * 0.6,
      s: 0.003 + Math.random() * 0.01,
      z: 0.25 + Math.random() * 0.75,
    }));
    const loop = () => {
      const w = hud.clientWidth;
      const h = hud.clientHeight;
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      ctx.clearRect(0, 0, w, h);
      const cx = w / 2;
      const cy = h / 2;
      const rad = Math.min(w, h) / 2;
      const talk = $("orb") && $("orb").classList.contains("talk");
      const listen = $("orb") && $("orb").classList.contains("listen");
      dots.forEach((d) => {
        d.a += d.s * (talk ? 2.4 : listen ? 1.6 : 1);
        const x = cx + Math.cos(d.a) * rad * d.r;
        const y = cy + Math.sin(d.a) * rad * d.r;
        ctx.beginPath();
        ctx.fillStyle = talk
          ? `rgba(62,224,212,${0.18 + d.z * 0.55})`
          : `rgba(212,176,86,${0.12 + d.z * 0.45})`;
        ctx.arc(x, y, talk ? 1.8 : 1.2, 0, Math.PI * 2);
        ctx.fill();
      });
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }
  const tickClock = () => {
    const el = $("clock");
    if (!el) return;
    const now = new Date();
    el.textContent = now.toISOString().replace("T", "  ").slice(0, 19) + "Z";
  };
  tickClock();
  setInterval(tickClock, 1000);
  fetch("/api/health")
    .then((r) => r.json())
    .then((d) => {
      if ($("edition") && d.version) $("edition").textContent = `v${d.version} · ${d.voice || "eve"} · LIVE`;
    })
    .catch(() => {});
}

initLivingHud();
bootstrapGuard()
  .then(() => refreshStatus())
  .then(() => refreshWidgets())
  .then(() => startLiveFeeds())
  .catch(() => setStatus("backend offline"));
setInterval(refreshWidgets, 30000);
setStatus("systems alive");
