// Aloud voice console. Push-to-talk (Space or the big button) or typed text goes to POST /api/turn;
// the reply streams back as NDJSON events (step / alert / say / done) that are spoken and logged.
"use strict";

const $ = (id) => document.getElementById(id);
const els = {
  talk: $("talk"), talkLabel: $("talk-label"), form: $("form"), say: $("say"), status: $("status"),
  log: $("log"), alert: $("alert"), confirm: $("confirm"), confirmText: $("confirm-text"),
  yes: $("yes"), no: $("no"), speak: $("speak"), steps: $("steps"), sounds: $("sounds"),
  rate: $("rate"), rateOut: $("rate-out"), lang: $("lang"),
};
const session = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
let lastReply = "";
let busy = false;
let controller = null;

// Settings persist per browser; storage can be unavailable (private window), so every access is guarded.
const SETTINGS = ["speak", "steps", "sounds", "rate", "lang"];
function loadSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem("aloud") || "{}");
    for (const k of SETTINGS) {
      if (!(k in saved)) continue;
      if (els[k].type === "checkbox") els[k].checked = saved[k];
      else els[k].value = saved[k];
    }
  } catch { /* defaults stay */ }
  els.rateOut.textContent = Number(els.rate.value).toFixed(1);
}
function saveSettings() {
  const out = {};
  for (const k of SETTINGS) out[k] = els[k].type === "checkbox" ? els[k].checked : els[k].value;
  try { localStorage.setItem("aloud", JSON.stringify(out)); } catch { /* not persisted */ }
}

// ---- Earcons: short tones so a listener knows the state without words. ----
let audio = null;
function tone(freqs, dur = 0.09, type = "sine", gain = 0.12) {
  if (!els.sounds.checked) return;
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    let t = audio.currentTime;
    for (const f of freqs) {
      const o = audio.createOscillator(), g = audio.createGain();
      o.type = type; o.frequency.value = f;
      g.gain.setValueAtTime(gain, t);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g).connect(audio.destination);
      o.start(t); o.stop(t + dur);
      t += dur * 0.9;
    }
  } catch { /* no audio device */ }
}
const earcon = {
  listen: () => tone([660, 880]),
  stop: () => tone([880, 660]),
  working: () => tone([520], 0.05, "triangle", 0.06),
  done: () => tone([784, 1047], 0.08),
  blocked: () => tone([220, 175], 0.18, "square", 0.08),
  confirm: () => tone([587, 587, 784], 0.1, "triangle"),
};

// ---- Speech out. Replies queue; steps are dropped if speech is already busy; alerts interrupt. ----
function speak(text, { interrupt = false, droppable = false } = {}) {
  if (!els.speak.checked || !("speechSynthesis" in window) || !text) return;
  if (interrupt) speechSynthesis.cancel();
  else if (droppable && (speechSynthesis.speaking || speechSynthesis.pending)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.rate = Number(els.rate.value);
  u.lang = els.lang.value;
  speechSynthesis.speak(u);
}

function status(text) { els.status.textContent = text; }

function logEntry(kind, who, text, extra) {
  const li = document.createElement("li");
  li.className = kind;
  const w = document.createElement("span");
  w.className = "who"; w.textContent = who;
  li.append(w, document.createTextNode(text));
  if (extra) {
    const m = document.createElement("span");
    m.className = "ms"; m.textContent = " " + extra;
    li.append(m);
  }
  els.log.append(li);
  li.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  return li;
}

// ---- One turn: send text, read the NDJSON stream, act on each event. ----
async function send(text, via = "typed") {
  text = text.trim();
  if (!text) return;
  if (busy) { speak("Still working on the last request. Press Escape to stop it.", { interrupt: true }); return; }
  busy = true;
  document.documentElement.dataset.busy = "1";  // lets tests and the recorder wait for a turn
  hideConfirm();
  els.alert.hidden = true;
  logEntry("you", via === "voice" ? "You said" : "You", text);
  status("Working…");
  earcon.working();
  controller = new AbortController();
  let said = false;
  try {
    const res = await fetch("/api/turn", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session, text }), signal: controller.signal,
    });
    if (!res.ok || !res.body) throw new Error(`server answered ${res.status}`);
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const raw = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (raw) said = handle(JSON.parse(raw)) || said;
      }
    }
  } catch (e) {
    if (e.name === "AbortError") { status("Stopped."); logEntry("aloud", "Aloud", "Stopped."); }
    else {
      const msg = `Something went wrong: ${e.message}.`;
      status(msg); logEntry("blocked", "Error", msg); speak(msg, { interrupt: true });
    }
  } finally {
    busy = false;
    document.documentElement.dataset.busy = "0";
    controller = null;
    if (!said) status("Ready.");
  }
}

// Returns true when the event produced a spoken reply.
function handle(ev) {
  if (ev.type === "step") {
    status(ev.text + "…");
    earcon.working();
    if (els.steps.checked) speak(ev.text, { droppable: true });
    return false;
  }
  if (ev.type === "alert") {
    const label = { blocked: "Blocked", confirm: "Needs your yes", warning: "Warning" }[ev.kind] || "Guardian";
    logEntry(ev.kind, `Guardian · ${label}`, ev.text);
    els.alert.textContent = `Guardian: ${label}.`;
    els.alert.hidden = false;
    (ev.kind === "confirm" ? earcon.confirm : earcon.blocked)();
    speak(ev.text, { interrupt: true });
    lastReply = ev.text;
    if (ev.kind === "confirm") showConfirm(ev.text);
    return true;
  }
  if (ev.type === "say") {
    logEntry("aloud", "Aloud", ev.text);
    speak(ev.text);
    lastReply = ev.text;
    return true;
  }
  if (ev.type === "error") {
    logEntry("blocked", "Error", ev.text);
    earcon.blocked();
    speak(ev.text, { interrupt: true });
    lastReply = ev.text;
    return true;
  }
  if (ev.type === "done") {
    earcon.done();
    status(ev.quick ? `Answered from the page in ${ev.ms} ms.` : `Done in ${(ev.ms / 1000).toFixed(1)} s.`);
    return false;
  }
  return false;
}

function showConfirm(text) {
  els.confirmText.textContent = text;
  els.confirm.hidden = false;
  els.yes.focus();
}
function hideConfirm() { els.confirm.hidden = true; }
els.yes.addEventListener("click", () => send("yes"));
els.no.addEventListener("click", () => send("no"));

// ---- Speech in: Web Speech recognition, push-to-talk. ----
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let rec = null;
let heard = "";
let listening = false;

function startListening() {
  if (listening) return;
  if (!Recognition) {
    status("Voice input is not available in this browser. Type in the box instead.");
    speak("Voice input is not available in this browser. Type in the box instead.", { interrupt: true });
    els.say.focus();
    return;
  }
  speechSynthesis && speechSynthesis.cancel();
  heard = "";
  rec = new Recognition();
  rec.lang = els.lang.value;
  rec.interimResults = true;
  rec.continuous = true;
  rec.onresult = (e) => {
    heard = Array.from(e.results).map((r) => r[0].transcript).join(" ");
    status(`Hearing: ${heard}`);
  };
  rec.onerror = (e) => { if (e.error !== "aborted") status(`Microphone: ${e.error}.`); };
  rec.onend = () => {
    setListening(false);
    if (heard.trim()) send(heard, "voice");
  };
  rec.start();
  setListening(true);
}
function stopListening() { if (rec && listening) rec.stop(); }
function setListening(on) {
  listening = on;
  els.talk.setAttribute("aria-pressed", String(on));
  els.talkLabel.textContent = on ? "Listening… let go to send" : "Hold to talk";
  if (on) { earcon.listen(); status("Listening…"); } else earcon.stop();
}

els.talk.addEventListener("pointerdown", (e) => { e.preventDefault(); startListening(); });
els.talk.addEventListener("pointerup", stopListening);
els.talk.addEventListener("pointerleave", stopListening);
// Keyboard and screen-reader activation of the button toggles instead of holding.
els.talk.addEventListener("click", (e) => { if (e.detail === 0) listening ? stopListening() : startListening(); });

function spaceTalks(target) {
  // Space keeps its usual meaning on inputs and other controls.
  return target === document.body || target === els.talk || target === els.log || target.tagName === "MAIN";
}
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (listening) { rec.abort(); heard = ""; }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    if (controller) controller.abort();
    status("Stopped.");
    return;
  }
  const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName);
  if (e.code === "Space" && spaceTalks(e.target)) {
    e.preventDefault();
    if (!e.repeat) startListening();
  } else if (!typing && !e.metaKey && !e.ctrlKey && !e.altKey) {
    if (e.key === "r" || e.key === "R") { e.preventDefault(); speak(lastReply || "Nothing to repeat yet.", { interrupt: true }); }
    else if (e.key === "/") { e.preventDefault(); els.say.focus(); }
  }
});
document.addEventListener("keyup", (e) => {
  if (e.code === "Space" && spaceTalks(e.target)) { e.preventDefault(); stopListening(); }
});

// ---- Typed input and settings. ----
els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = els.say.value;
  els.say.value = "";
  send(text);
});
els.rate.addEventListener("input", () => { els.rateOut.textContent = Number(els.rate.value).toFixed(1); saveSettings(); });
for (const k of ["speak", "steps", "sounds", "lang"]) els[k].addEventListener("change", saveSettings);
els.speak.addEventListener("change", () => { if (!els.speak.checked && "speechSynthesis" in window) speechSynthesis.cancel(); });

// Lets a test or the demo recorder hand in a recognised sentence without a microphone. It walks
// the same states as the microphone path (listening, hearing, sent) so the screen matches.
window.aloudHeard = async (text, ms = 1200) => {
  setListening(true);
  status(`Hearing: ${text}`);
  await new Promise((r) => setTimeout(r, ms));
  setListening(false);
  return send(text, "voice");
};

loadSettings();
