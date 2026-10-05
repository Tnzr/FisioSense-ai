# CardiaSense AI — HLS-CMDS Auscultation Benchmark & Web App

Stage-1 AI proof of concept for automated heart/lung sound analysis on the
[HLS-CMDS](https://doi.org/10.1109/IEEEDATA.2025.3566012) manikin dataset
(Torabi, Shirani & Reilly, IEEE Data Descriptions 2025): 535 recordings, three
classification tasks (source routing, normal/abnormal screening, fine-grained
typing), four model tiers, leakage-safe grouped cross-validation, and a WandB-tracked
benchmark with auditable adopt/skip gates.

## What's here

| path | content |
|---|---|
| `ml/cardia/` | training/evaluation pipeline (data, splits, models, train, report) |
| `ml/scripts/` | sequential campaign orchestrator + gates (`run_sequential.sh`) |
| `webapp/` | FastAPI web app: **Inference-as-a-Service** + **educational game** |
| `docs/` | strategy, architecture, tech-stack, app spec, mobile-compute analysis |
| `setup.sh` | one-shot setup: venv, dependencies, dataset download from Zenodo |

## Quick start

```bash
./setup.sh                 # venv + deps + downloads HLS-CMDS (37.8 MB) if absent
.venv/bin/python -m uvicorn webapp.app.main:app --port 8010   # web app
```

Then open http://localhost:8010 (upload/analyze, batch, multi-scale temporal
reports, and the Learn game).

Training / campaign:

```bash
.venv/bin/python -m cardia.cli --task heart --stage 2 --model resnet18 --smoke
cd ml && SMOKE=1 ./scripts/run_sequential.sh          # full smoke campaign
```

Data is looked up via `CARDIASENSE_DATA_DIR` (env or `.env`); `setup.sh` writes
`.env` for the local download. Training outputs go to `ml/runs/` (git-ignored);
WandB runs sync to project `cardiasense-hls-cmds`.

## Purpose & disclaimer

Educational / research prototype. Models are trained on a **manikin** dataset —
this is not a medical device and does not provide a diagnosis. See
`docs/WebApp.md` and the in-app disclaimers.
