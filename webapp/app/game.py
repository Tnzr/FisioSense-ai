"""Educational game mode: dataset-backed listening rounds with ground truth."""
from __future__ import annotations

import os
import random
import sys
import uuid
from typing import Dict, List, Optional

from . import config

ML = config.ML
if ML not in sys.path:
    sys.path.insert(0, ML)

from cardia.data.hls_cmds import build_task_manifest  # noqa: E402

DOMAINS: Dict[str, dict] = {
    "heart_types": {"task": "heart", "scheme": "10class",
                    "question": "Which heart sound is this?", "label": "Heart sound typing (10 classes)"},
    "lung_types": {"task": "lung", "scheme": "6class",
                   "question": "Which lung sound is this?", "label": "Lung sound typing (6 classes)"},
    "heart_binary": {"task": "heart", "scheme": "binary",
                     "question": "Is this heart sound normal or abnormal?", "label": "Heart normal vs abnormal"},
    "lung_binary": {"task": "lung", "scheme": "binary",
                    "question": "Is this lung sound normal or abnormal?", "label": "Lung normal vs abnormal"},
    "source": {"task": "sound", "scheme": "binary",
               "question": "Is this clip heart, lung, or mixed?", "label": "Source identification"},
}

_MANIFEST_CACHE: Dict[tuple, "object"] = {}
_ROUNDS: Dict[str, dict] = {}
_MAX_ROUNDS = 500


def _manifest(task: str, scheme: str):
    key = (task, scheme)
    if key not in _MANIFEST_CACHE:
        _MANIFEST_CACHE[key] = build_task_manifest(
            config.DATA_DIR, task, scheme, os.path.join(ML, "runs", "manifests"))
    return _MANIFEST_CACHE[key]


def _classes_for(domain: str, manifest) -> List[str]:
    if domain == "heart_types":
        return [c for c in config.model_registry() if c.key == "heart_types"][0].classes
    if domain == "lung_types":
        return [c for c in config.model_registry() if c.key == "lung_types"][0].classes
    return sorted(manifest["task_label"].unique().tolist())


def new_round(domain: str) -> Dict:
    if domain not in DOMAINS:
        raise ValueError(f"unknown domain {domain}")
    spec = DOMAINS[domain]
    manifest = _manifest(spec["task"], spec["scheme"])
    row = manifest.sample(n=1, random_state=random.randint(0, 10**9)).iloc[0]
    correct = str(row["task_label"])
    classes = _classes_for(domain, manifest)
    distractors = [c for c in classes if c != correct]
    random.shuffle(distractors)
    options = [correct] + distractors[: max(0, min(3, len(distractors)))]
    random.shuffle(options)

    round_id = uuid.uuid4().hex
    if len(_ROUNDS) > _MAX_ROUNDS:
        _ROUNDS.clear()
    _ROUNDS[round_id] = {
        "sample_id": row["sample_id"], "correct": correct, "domain": domain,
        "task": spec["task"], "scheme": spec["scheme"],
    }
    return {
        "round_id": round_id,
        "domain": domain,
        "domain_label": spec["label"],
        "question": spec["question"],
        "options": options,
        "audio_url": f"/game/audio/{row['sample_id']}?task={spec['task']}&scheme={spec['scheme']}",
    }


def grade(round_id: str, answer: str) -> Dict:
    r = _ROUNDS.get(round_id)
    if r is None:
        return {"error": "round not found or expired; request a new round"}
    correct = r["correct"]
    finding, awareness = config.KNOWLEDGE.get(correct, ("", ""))
    return {
        "correct": answer == correct,
        "answer": answer,
        "correct_label": correct,
        "sample_id": r["sample_id"],
        "explanation": {
            "finding": finding,
            "awareness": awareness,
        },
    }


def resolve_audio_path(sample_id: str, task: str, scheme: str) -> Optional[str]:
    manifest = _manifest(task, scheme)
    sub = manifest[manifest["sample_id"] == sample_id]
    if sub.empty:
        return None
    path = sub.iloc[0]["file_path"]
    return path if os.path.isfile(path) else None
