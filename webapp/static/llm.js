// AI narrative follow-up chat: POSTs the current findings + history to /api/llm/report.
(function () {
  const fdEl = document.getElementById("findings-data");
  if (!fdEl) return;
  const findings = JSON.parse(fdEl.textContent);
  const ctxEl = document.getElementById("patient-context-val");
  const patient_context = ctxEl ? ctxEl.textContent.trim() : "";
  const log = document.getElementById("chat-log");
  const input = document.getElementById("chat-input");
  const send = document.getElementById("chat-send");
  if (!log || !input || !send) return;
  const history = [];

  function add(role, text) {
    const div = document.createElement("div");
    div.className = "msg " + role;
    div.textContent = (role === "user" ? "You: " : "AI: ") + text;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  async function ask() {
    const q = input.value.trim();
    if (!q) return;
    add("user", q);
    input.value = "";
    history.push({ role: "user", content: q });
    try {
      const r = await fetch("/api/llm/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ findings, patient_context, history }),
      });
      const res = await r.json();
      const ans = (res.summary || "") +
        ((res.next_steps && res.next_steps.length) ? "  Next steps: " + res.next_steps.join("; ") : "");
      add("ai", ans || "No response.");
      history.push({ role: "assistant", content: ans });
    } catch (e) {
      add("ai", "Error contacting the AI report service.");
    }
  }

  send.addEventListener("click", ask);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });
})();