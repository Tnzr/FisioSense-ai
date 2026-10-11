// Asculto desktop main process.
//
// The app is offline-first: it loads the int8 ONNX heads from ./models (fetched
// on first run by scripts/fetch-models.mjs), runs them locally on CPU, and uses
// the offline narrative synthesizer. A cloud account can optionally be linked
// for sync/batch/LLM (the funnel into the paid cloud tiers).
const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const { autoUpdater } = require("electron-updater");

const MODELS_DIR = path.join(__dirname, "models");
let ort = null;
let sessions = null;

function loadManifest() {
  const p = path.join(MODELS_DIR, "onnx_manifest.json");
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

async function ensureSessions() {
  if (sessions) return sessions;
  const manifest = loadManifest();
  if (!manifest) throw new Error("models not found — run `npm run fetch-models`");
  ort = ort || require("onnxruntime-node");
  sessions = {};
  for (const head of manifest.heads) {
    sessions[head.key] = await ort.InferenceSession.create(
      path.join(MODELS_DIR, head.served.file),
      { executionProviders: ["cpu"] },
    );
  }
  return sessions;
}

// Preprocessing (resample -> peak-normalize -> band-pass -> fixed length ->
// log-mel) mirrors ml/cardia/data/transforms.py. Wire the JS port here; the
// ONNX contract is input "input" [1,1,64,376] -> output "probs".
async function inferHead(headKey, melFrame) {
  const s = await ensureSessions();
  const session = s[headKey];
  if (!session) throw new Error(`head ${headKey} not loaded`);
  const tensor = new ort.Tensor("float32", melFrame, [1, 1, 64, 376]);
  const out = await session.run({ input: tensor });
  return Array.from(out.probs.data);
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1180,
    height: 820,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
}

app.whenReady().then(() => {
  ipcMain.handle("models:status", () => {
    const m = loadManifest();
    return m ? { ready: true, heads: m.heads.map((h) => h.key) } : { ready: false, heads: [] };
  });
  ipcMain.handle("infer", async (_evt, { head, mel }) => inferHead(head, mel));

  createWindow();
  autoUpdater.checkForUpdatesAndNotify().catch(() => {});

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
