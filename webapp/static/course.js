// Asculto training course: client-side progress (localStorage), practice
// rounds (reuses the game API), checkpoint grading, and certificate.
const $ = (id) => document.getElementById(id);
const KEY = "asculto_course_progress";
const NAME_KEY = "asculto_course_name";

function getProgress() {
  try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch { return {}; }
}
function saveProgress(p) { localStorage.setItem(KEY, JSON.stringify(p)); }
function markPassed(id) {
  const p = getProgress();
  p[id] = true;
  saveProgress(p);
  return p;
}
function allDone(moduleIds) {
  const p = getProgress();
  return moduleIds.every((id) => p[id] === true);
}

// --------------------------------------------------------------- course hub
function renderHub() {
  const p = getProgress();
  document.querySelectorAll(".module-card").forEach((card) => {
    const id = card.dataset.module;
    if (p[id]) {
      const badge = card.querySelector(".badge-done");
      if (badge) badge.hidden = false;
      card.classList.add("done");
    }
  });
  const count = $("progress-count");
  if (count) count.textContent = String(Object.values(p).filter(Boolean).length);
}

// ---------------------------------------------------------------- practice
let practice = null;
let practiceScore = 0;
let practiceAsked = 0;

async function practiceRound() {
  const state = readState();
  $("practice-feedback").textContent = "";
  $("practice-options").innerHTML = "";
  const url = `/api/game/round?domain=${encodeURIComponent(state.practice_domain)}`;
  const r = await fetch(url);
  if (!r.ok) { $("practice-feedback").textContent = "Could not load a round."; return; }
  practice = await r.json();
  $("practice-question").textContent = practice.question;
  const player = $("practice-player");
  player.src = practice.audio_url;
  player.style.display = "block";
  player.load();
  practice.options.forEach((opt) => {
    const b = document.createElement("button");
    b.textContent = opt;
    b.onclick = () => practiceAnswer(opt);
    $("practice-options").appendChild(b);
  });
}

async function practiceAnswer(choice) {
  if (!practice) return;
  const r = await fetch("/api/game/answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ round_id: practice.round_id, answer: choice }),
  });
  const res = await r.json();
  practiceAsked += 1;
  if (res.correct) practiceScore += 1;
  $("practice-score").innerHTML =
    `This session: <strong>${practiceScore}</strong> / <span>${practiceAsked}</span> correct`;
  const ex = res.explanation || {};
  $("practice-feedback").innerHTML =
    `<div class="${res.correct ? "good" : "wrong"}">${res.correct ? "✓ Correct" : "✗ Not quite"} — ` +
    `answer: <strong>${esc(res.correct_label)}</strong></div>` +
    `<p>${esc(ex.finding || "")}</p><p class="muted">${esc(ex.awareness || "")}</p>`;
  document.querySelectorAll("#practice-options button").forEach((b) => { b.disabled = true; });
  const next = document.createElement("button");
  next.textContent = "Next round →";
  next.className = "primary";
  next.onclick = practiceRound;
  $("practice-options").appendChild(next);
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function readState() {
  const el = $("course-state");
  return el ? JSON.parse(el.textContent) : {};
}

// ---------------------------------------------------------------- checkpoint
function answersFromForm() {
  const state = readState();
  const out = [];
  for (let i = 0; i < state.quiz_total; i++) {
    const checked = document.querySelector(`input[name="q${i}"]:checked`);
    out.push(checked ? checked.value : null);
  }
  return out;
}

async function submitQuiz(ev) {
  ev.preventDefault();
  const state = readState();
  const status = $("quiz-status");
  status.textContent = "Grading…";
  const r = await fetch("/api/course/quiz", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ module_id: state.module_id, answers: answersFromForm() }),
  });
  const res = await r.json();
  if (res.error) { status.textContent = res.error; return; }
  status.textContent = `Score ${res.score}/${res.total} — ${res.passed ? "passed ✓" : "keep practising"}`;

  const wrap = $("quiz-results");
  wrap.innerHTML = "";
  res.results.forEach((rq, i) => {
    const el = document.createElement("div");
    el.className = `quiz-result ${rq.correct ? "good" : "wrong"}`;
    el.innerHTML =
      `<p><strong>Q${i + 1}</strong> ${rq.correct ? "✓" : "✗"} — correct: <strong>${esc(rq.correct_label)}</strong></p>` +
      `<p>${esc(rq.finding || "")}</p>` +
      `<p class="muted">${esc(rq.awareness || "")}</p>` +
      (rq.note ? `<p class="muted small">${esc(rq.note)}</p>` : "");
    wrap.appendChild(el);
  });
  document.querySelectorAll("#quiz-form input").forEach((inp) => { inp.disabled = true; });

  if (res.passed) {
    const p = markPassed(state.module_id);
    const next = $("next-module");
    next.hidden = false;
    next.innerHTML = "";
    const h = document.createElement("p");
    h.innerHTML = `<strong>Module complete!</strong>`;
    next.appendChild(h);
    const idx = state.module_index;
    if (idx + 1 < state.total_modules) {
      const a = document.createElement("a");
      a.href = `/course/${state.module_ids[idx + 1]}`;
      a.className = "btn primary";
      a.textContent = "Next module →";
      next.appendChild(a);
    }
    if (allDone(state.module_ids)) showCertificate();
    else {
      const back = document.createElement("a");
      back.href = "/course";
      back.className = "btn";
      back.textContent = "Back to course";
      next.appendChild(back);
    }
  }
}

// ---------------------------------------------------------------- certificate
function showCertificate() {
  const cert = $("certificate");
  if (cert) cert.hidden = false;
}
function generateCertificate() {
  const state = readState();
  const name = ($("cert-name").value || "Student").trim();
  localStorage.setItem(NAME_KEY, name);
  const d = new Date().toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
  $("cert-panel").innerHTML = `
    <div class="cert-inner">
      <h2>Asculto — Certificate of Completion</h2>
      <p class="cert-sub">Interactive auscultation training course</p>
      <p class="cert-name">${esc(name)}</p>
      <p>has completed all ${state.total_modules} modules of the Asculto auscultation
         training course using real heart and lung sounds from the HLS-CMDS dataset.</p>
      <p class="muted">Date: ${esc(d)}</p>
      <p class="muted small">Educational / research course — not a clinical qualification.
         Models and dataset: HLS-CMDS (CC BY 4.0).</p>
    </div>`;
  $("cert-panel").hidden = false;
  $("cert-print").hidden = false;
}
function printCertificate() {
  const panel = $("cert-panel");
  const body = document.body;
  panel.classList.add("printing");
  window.print();
  panel.classList.remove("printing");
}

// ------------------------------------------------------------------- init
document.addEventListener("DOMContentLoaded", () => {
  renderHub();
  const start = $("practice-start");
  if (start) start.onclick = practiceRound;
  const form = $("quiz-form");
  if (form) form.onsubmit = submitQuiz;
  const go = $("cert-go");
  if (go) go.onclick = generateCertificate;
  const print = $("cert-print");
  if (print) print.onclick = printCertificate;
  const savedName = localStorage.getItem(NAME_KEY);
  if (savedName && $("cert-name")) $("cert-name").value = savedName;
  if (allDone(readState().module_ids || [])) showCertificate();
});
