// Live temporal chart: head probabilities vs time, with an audio playhead.
(function () {
  const dataEl = document.getElementById("series-data");
  if (!dataEl) return;
  const series = JSON.parse(dataEl.textContent);
  const canvas = document.getElementById("live-canvas");
  const headSel = document.getElementById("live-head");
  const audio = document.getElementById("report-audio");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const PALETTE = ["#4cc2c4", "#4c72b0", "#c44e52", "#55a868", "#8172b2",
                   "#ccb974", "#64b5cd", "#e17c05", "#937860", "#da8bc3",
                   "#8c8c8c", "#c7c7c7"];

  function current() { return series[headSel.value]; }

  function draw() {
    const s = current();
    if (!s) return;
    const W = canvas.width, H = canvas.height;
    const padL = 54, padR = 12, padT = 12, padB = 34;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    ctx.clearRect(0, 0, W, H);

    const tmax = Math.max.apply(null, s.times.concat([1]));
    const X = (t) => padL + (t / tmax) * plotW;
    const Y = (p) => padT + (1 - p) * plotH;

    // grid + y labels
    ctx.strokeStyle = "#2b3a49"; ctx.fillStyle = "#93a4b5";
    ctx.font = "11px system-ui, sans-serif"; ctx.lineWidth = 1;
    [0, 0.25, 0.5, 0.75, 1].forEach((p) => {
      ctx.beginPath(); ctx.moveTo(padL, Y(p)); ctx.lineTo(W - padR, Y(p)); ctx.stroke();
      ctx.fillText(p.toFixed(2), 8, Y(p) + 4);
    });
    // x ticks
    const nt = 6;
    for (let i = 0; i <= nt; i++) {
      const t = (tmax * i) / nt;
      ctx.fillText(t.toFixed(1) + "s", X(t) - 10, H - 12);
    }
    // series lines
    s.classes.forEach((cls, ci) => {
      ctx.strokeStyle = PALETTE[ci % PALETTE.length];
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      s.times.forEach((t, i) => {
        const x = X(t), y = Y(s.probs[i][ci]);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();
    });
    // playhead
    if (audio && audio.currentTime > 0) {
      const px = X(Math.min(audio.currentTime, tmax));
      ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(px, padT); ctx.lineTo(px, padT + plotH); ctx.stroke();
      // current argmax label
      const nearest = s.times.reduce((bi, t, i) =>
        Math.abs(t - audio.currentTime) < Math.abs(s.times[bi] - audio.currentTime) ? i : bi, 0);
      const probs = s.probs[nearest];
      let ai = 0; probs.forEach((v, i) => { if (v > probs[ai]) ai = i; });
      ctx.fillStyle = "#ffffff";
      ctx.fillText(s.classes[ai] + " " + (probs[ai] * 100).toFixed(0) + "%", Math.min(px + 6, W - 160), padT + 14);
    }
    // legend
    ctx.font = "11px system-ui, sans-serif";
    s.classes.forEach((cls, ci) => {
      const lx = padL + (ci % 6) * 165, ly = padT + 12 + Math.floor(ci / 6) * 14;
      ctx.fillStyle = PALETTE[ci % PALETTE.length];
      ctx.fillRect(lx, ly - 8, 10, 10);
      ctx.fillStyle = "#e8eef5";
      ctx.fillText(cls, lx + 14, ly + 1);
    });
  }

  headSel && headSel.addEventListener("change", draw);
  if (audio) {
    audio.addEventListener("timeupdate", draw);
    audio.addEventListener("seeked", draw);
  }
  draw();
})();
