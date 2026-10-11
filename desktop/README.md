# Asculto desktop app (Electron + ONNX Runtime)

Offline-first desktop build: ship the int8 ONNX heads and run them on local CPU
(zero cloud cost per user, humanitarian/offline mission, funnel into paid cloud).

## Layout

- `main.js` — Electron main process; loads the ONNX manifest and runs heads.
- `preload.js` — context-isolated IPC bridge.
- `renderer/` — built from `../frontend` (`npm run build` there first).
- `scripts/fetch-models.mjs` — downloads + checksum-verifies model artifacts.

## Model artifacts

Produced by `cardia.export.onnx_serve` (see `docs/Deployment.md` §4) and hosted
on GitHub Releases or R2. Sizes per `docs/MobileCompute.md`: ResNet-18 ~11 MB
int8, Transformer ~2 MB int8, all 5 ~36 MB.

```bash
node scripts/fetch-models.mjs --base https://releases.example/asculto/models
```

## Develop / package

```bash
cd ../frontend && npm install && npm run build
cd ../desktop && npm install && npm run fetch-models && npm start
npm run dist:linux   # AppImage + deb; see electron-builder config
```

## Signing & distribution (plan §7)

- macOS: Apple Developer $99/yr + notarization (free).
- Windows: Microsoft Store MSIX re-signs free, or Azure Artifact Signing ~$9.99/mo.
- Auto-update: `electron-updater` against GitHub Releases.

Weights trained on CC BY 4.0 data ship with attribution; app source under
MIT/Apache-2.0, later clinical-grade weights proprietary.
