let current = null;
let score = 0, asked = 0, streak = 0;

const $ = (id) => document.getElementById(id);

async function newRound() {
  const domain = $("domain").value;
  $("feedback").textContent = "";
  $("options").innerHTML = "";
  const r = await fetch(`/api/game/round?domain=${encodeURIComponent(domain)}`);
  if (!r.ok) { $("feedback").textContent = "Could not load a round."; return; }
  current = await r.json();
  $("question").textContent = current.question;
  const player = $("player");
  player.src = current.audio_url;
  player.style.display = "block";
  player.load();
  const opts = $("options");
  current.options.forEach((opt) => {
    const b = document.createElement("button");
    b.textContent = opt;
    b.onclick = () => answer(opt);
    opts.appendChild(b);
  });
}

async function answer(choice) {
  if (!current) return;
  const r = await fetch("/api/game/answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ round_id: current.round_id, answer: choice }),
  });
  const res = await r.json();
  asked += 1;
  if (res.correct) { score += 1; streak += 1; } else { streak = 0; }
  $("score").textContent = score;
  $("asked").textContent = asked;
  $("streak").textContent = streak;
  const ex = res.explanation || {};
  $("feedback").innerHTML =
    `<div class="${res.correct ? "good" : "wrong"}">${res.correct ? "✓ Correct" : "✗ Not quite"} — ` +
    `answer: <strong>${res.correct_label}</strong></div>` +
    `<p>${ex.finding || ""}</p><p class="muted">${ex.awareness || ""}</p>`;
  document.querySelectorAll("#options button").forEach((b) => { b.disabled = true; });
  const next = document.createElement("button");
  next.textContent = "Next round →";
  next.className = "primary";
  next.onclick = newRound;
  $("options").appendChild(next);
}

document.addEventListener("DOMContentLoaded", () => {
  $("start").onclick = newRound;
});
