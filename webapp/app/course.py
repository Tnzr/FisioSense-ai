"""Free educational auscultation training course.

A structured, dataset-backed curriculum: lessons with curated listening
examples, practice rounds (reusing the game engine), and checkpoint quizzes
graded against HLS-CMDS ground truth. Purely educational — no inference and no
accounts required; progress lives client-side (localStorage) since the course
is a free service.

Course audio is served through `webapp.app.playback` so it plays in browsers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from . import config, game


@dataclass
class Example:
    label: str
    task: str
    scheme: str
    sample_id: str
    note: str = ""


@dataclass
class Lesson:
    id: str
    title: str
    paragraphs: List[str] = field(default_factory=list)
    examples: List[Example] = field(default_factory=list)


@dataclass
class Question:
    prompt: str
    options: List[str]
    correct: int
    knowledge_key: str
    sample_id: str = ""      # listening questions only
    task: str = ""
    scheme: str = ""
    note: str = ""


@dataclass
class Module:
    id: str
    title: str
    summary: str
    lessons: List[Lesson] = field(default_factory=list)
    practice_domain: str = ""           # key into game.DOMAINS for drills
    quiz: List[Question] = field(default_factory=list)
    pass_score: int = 3


def knowledge(label: str) -> Tuple[str, str]:
    """Plain-language finding + awareness blurb for a label (NOT advice)."""
    return config.KNOWLEDGE.get(label, ("", ""))


def audio_url(sample_id: str, task: str, scheme: str) -> str:
    return f"/game/audio/{sample_id}?task={task}&scheme={scheme}"


def _pick(task: str, scheme: str, label: str) -> Example:
    """Deterministic example: the first manifest row of `label` for a scheme."""
    m = game._manifest(task, scheme)
    sub = m[m["task_label"] == label]
    sid = str(sub.iloc[0]["sample_id"]) if not sub.empty else ""
    return Example(label=label, task=task, scheme=scheme, sample_id=sid)


def _listening(prompt: str, task: str, scheme: str, label: str,
               options: List[str], correct: int, note: str = "") -> Question:
    ex = _pick(task, scheme, label)
    return Question(prompt=prompt, options=options, correct=correct,
                    knowledge_key=label, sample_id=ex.sample_id,
                    task=task, scheme=scheme, note=note)


# --------------------------------------------------------------------- course
MODULES: List[Module] = [
    Module(
        id="intro",
        title="Heart & lung sounds — what you'll hear",
        summary="The building blocks: S1/S2, breath sounds, and how this course uses real recordings.",
        lessons=[
            Lesson(
                id="sound-basics",
                title="The sounds of the chest",
                paragraphs=[
                    "A normal heartbeat produces two sounds through a stethoscope: S1 ('lub') from "
                    "closure of the mitral and tricuspid valves, then S2 ('dub') from the aortic and "
                    "pulmonary valves. Breath sounds are heard as air moves through the airways.",
                    "This course uses the HLS-CMDS dataset: 535 digital-stethoscope recordings from a "
                    "clinical manikin, with ground-truth labels for source (heart / lung / mixed), "
                    "normal vs abnormal screening, and fine-grained typing (10 heart classes, 6 lung "
                    "classes). Every clip you hear here is a real dataset recording.",
                    "Work through the modules in order. Each ends with a short checkpoint; pass it to "
                    "unlock the next one. Progress is stored in your browser only.",
                ],
                examples=[
                    _pick("heart", "10class", "Normal"),
                    _pick("lung", "6class", "Normal"),
                ],
            ),
        ],
        quiz=[
            Question("A normal heart sound is best described as:",
                     ["A clear 'lub-dub' (S1 then S2) rhythm", "A single loud thump",
                      "A whistling sound", "A creaking sound"],
                     0, "Normal",
                     note="S1 and S2 mark the two valve closures of each cardiac cycle."),
            Question("A wheeze is most characteristic of:",
                     ["Narrowed airways, as in asthma or COPD", "Inflamed pleura",
                      "Fluid in the lungs", "A stiffened heart valve"],
                     0, "Wheezing",
                     note="Wheezing is a high-pitched whistling sound from narrowed airways."),
            Question("Fine crackles are best described as:",
                     ["Short, high-pitched sounds, often at the lung bases", "Low-pitched rattling "
                      "from large airways", "A high-pitched whistle", "A creaking sound"],
                     0, "Fine Crackles",
                     note="Fine crackles are short, popping sounds that can accompany fibrosis or early fluid."),
            Question("In this dataset, the screening head predicts:",
                     ["normal or abnormal", "heart, lung or mixed", "10 heart classes or 6 lung classes",
                      "the gender of the patient"],
                     0, "normal",
                     note="Screening is binary: normal vs abnormal for heart and for lung."),
        ],
        pass_score=3,
    ),
    Module(
        id="source",
        title="Heart, lung, or both? Identifying the source",
        summary="Recognise whether a clip is a heart sound, a lung sound, or a mixed recording.",
        lessons=[
            Lesson(
                id="source-identification",
                title="Where the sound comes from",
                paragraphs=[
                    "Heart sounds are rhythmic and tied to the heartbeat (S1/S2, murmurs, gallops). "
                    "Lung sounds are breath-related: air movement, crackles, wheeze. A 'mixed' clip "
                    "contains both, and the service runs both sets of models on it.",
                    "A good first exercise is source identification: before typing anything, decide "
                    "which body system produced the recording. That routing is itself one of the "
                    "prediction heads in the app.",
                ],
                examples=[
                    _pick("sound", "binary", "heart"),
                    _pick("sound", "binary", "lung"),
                    _pick("sound", "binary", "mixed"),
                ],
            ),
        ],
        practice_domain="source",
        quiz=[
            _listening("Listen. This clip is:", "sound", "binary", "heart",
                       ["heart", "lung", "mixed"], 0),
            _listening("Listen. This clip is:", "sound", "binary", "lung",
                       ["heart", "lung", "mixed"], 1),
            Question("Which sounds make up the normal cardiac cycle heard through a stethoscope?",
                     ["S1 'lub' then S2 'dub'", "S3 then S4", "A continuous murmur",
                      "Crackles then wheeze"], 0, "heart"),
            Question("Why does the service run both heart and lung models on a mixed clip?",
                     ["The clip may contain both heart and lung sounds", "It is faster",
                      "Only one label exists", "Mixed clips need no analysis"], 0, "mixed"),
        ],
        pass_score=3,
    ),
    Module(
        id="heart-screen",
        title="Heart sounds: normal or abnormal?",
        summary="Learn what a normal heart sounds like and when a recording should be flagged for review.",
        lessons=[
            Lesson(
                id="heart-screening",
                title="Screening the heart",
                paragraphs=[
                    "Screening asks a binary question: does this heart-sound recording look normal or "
                    "abnormal? Normal recordings show a clean S1/S2 pattern; abnormalities include "
                    "murmurs (extra turbulence around the valves), gallops (S3 or S4), and irregular "
                    "rhythms such as atrial fibrillation.",
                    "Screening is a triage tool, not a diagnosis. A flagged recording means a clinician "
                    "should interpret it with the full history and examination.",
                ],
                examples=[
                    _pick("heart", "binary", "normal"),
                    _pick("heart", "binary", "abnormal"),
                ],
            ),
        ],
        practice_domain="heart_binary",
        quiz=[
            _listening("Listen. This heart clip is:", "heart", "binary", "normal",
                       ["normal", "abnormal"], 0),
            _listening("Listen. This heart clip is:", "heart", "binary", "abnormal",
                       ["normal", "abnormal"], 1),
            Question("In adults, an S3 gallop is most often a sign of:",
                     ["Reduced heart pumping function", "A perfectly healthy valve",
                      "High-fidelity headphones", "A lung infection"], 0, "S3"),
            Question("An irregular rhythm that raises stroke risk is most consistent with:",
                     ["Atrial fibrillation", "A pleural rub", "Fine crackles",
                      "A normal S1/S2"], 0, "Atrial Fibrillation"),
        ],
        pass_score=3,
    ),
    Module(
        id="heart-types",
        title="Heart sound typing (10 classes)",
        summary="Tell murmurs, gallops and rhythm disturbances apart using the dataset's 10-class labels.",
        lessons=[
            Lesson(
                id="heart-typing",
                title="Typing heart sounds",
                paragraphs=[
                    "Beyond screening, the dataset types heart sounds into 10 classes: Normal, murmurs "
                    "by timing (early / mid / late systolic, late diastolic), S3 and S4 gallops, "
                    "Atrial Fibrillation, Tachycardia, and AV Block.",
                    "Timing matters: murmurs are described by when they occur in the cardiac cycle. "
                    "Late-diastolic murmurs, for example, are classically linked to mitral stenosis; "
                    "an irregular rhythm with raised stroke risk points toward atrial fibrillation.",
                ],
                examples=[
                    _pick("heart", "10class", "Normal"),
                    _pick("heart", "10class", "Atrial Fibrillation"),
                    _pick("heart", "10class", "S3"),
                    _pick("heart", "10class", "Late Diastolic Murmur"),
                ],
            ),
        ],
        practice_domain="heart_types",
        quiz=[
            _listening("Listen. Which heart sound is this?", "heart", "10class", "Normal",
                       ["Normal", "Atrial Fibrillation", "S3", "Late Diastolic Murmur"], 0),
            _listening("Listen. Which heart sound is this?", "heart", "10class", "Atrial Fibrillation",
                       ["Normal", "Atrial Fibrillation", "S3", "Late Diastolic Murmur"], 1),
            Question("A late diastolic murmur is classically associated with:",
                     ["Mitral stenosis", "Aortic stenosis only", "Normal aging", "Wheezing"],
                     0, "Late Diastolic Murmur"),
            Question("AV block is best described as:",
                     ["A conduction disturbance of the heartbeat", "A type of lung sound",
                      "A normal S2", "A murmur heard only in children"], 0, "AV Block"),
        ],
        pass_score=3,
    ),
    Module(
        id="lung-types",
        title="Lung sounds: wheeze, crackles, rhonchi, rub",
        summary="Recognise the dataset's six lung classes: Normal, Wheezing, Fine and Coarse Crackles, Rhonchi, Pleural Rub.",
        lessons=[
            Lesson(
                id="lung-typing",
                title="Typing lung sounds",
                paragraphs=[
                    "Wheezing is a high-pitched whistle from narrowed airways (asthma, COPD). Fine "
                    "crackles are short, high-pitched popping sounds, often at the bases, that can "
                    "accompany fibrosis or early fluid. Coarse crackles are lower, bubbling sounds "
                    "from larger airways with secretions.",
                    "Rhonchi are low-pitched rattling sounds that may ease with coughing. A pleural "
                    "rub is a creaking sound from inflamed pleural surfaces, as in pleurisy. All six "
                    "labels are part of the app's lung-typing head.",
                ],
                examples=[
                    _pick("lung", "6class", "Normal"),
                    _pick("lung", "6class", "Wheezing"),
                    _pick("lung", "6class", "Fine Crackles"),
                    _pick("lung", "6class", "Coarse Crackles"),
                ],
            ),
        ],
        practice_domain="lung_types",
        quiz=[
            _listening("Listen. Which lung sound is this?", "lung", "6class", "Wheezing",
                       ["Wheezing", "Fine Crackles", "Coarse Crackles", "Pleural Rub"], 0),
            _listening("Listen. Which lung sound is this?", "lung", "6class", "Fine Crackles",
                       ["Wheezing", "Fine Crackles", "Coarse Crackles", "Pleural Rub"], 1),
            Question("Fine crackles are commonly heard in conditions such as:",
                     ["Pulmonary fibrosis or early fluid", "Asthma only",
                      "A perfectly healthy chest", "A fractured rib"], 0, "Fine Crackles"),
            Question("A creaking sound from inflamed pleural surfaces is a:",
                     ["Pleural rub", "Wheeze", "Coarse crackle", "Normal S1"], 0, "Pleural Rub"),
        ],
        pass_score=3,
    ),
    Module(
        id="final",
        title="Final assessment",
        summary="A mixed listening test across everything you have practised — pass it to earn your certificate.",
        lessons=[
            Lesson(
                id="final-recap",
                title="Putting it together",
                paragraphs=[
                    "This assessment mixes source identification, heart screening/typing and lung "
                    "typing. Listen carefully to each clip before choosing. Pass the checkpoint to "
                    "complete the course and unlock your certificate.",
                ],
            ),
        ],
        practice_domain="heart_types",
        quiz=[
            _listening("Listen. What is the source of this clip?", "sound", "binary", "heart",
                       ["heart", "lung", "mixed"], 0),
            _listening("Listen. Which heart pattern is this?", "heart", "10class", "Atrial Fibrillation",
                       ["Normal", "Atrial Fibrillation", "S3", "Late Diastolic Murmur"], 1),
            _listening("Listen. Which lung sound is this?", "lung", "6class", "Wheezing",
                       ["Normal", "Wheezing", "Fine Crackles", "Pleural Rub"], 1),
            Question("A person with an irregular, fast-feeling heart rhythm should:",
                     ["Discuss it with a clinician and confirm with an ECG", "Ignore it completely",
                      "Only exercise more", "Take an aspirin without advice"], 0, "Atrial Fibrillation"),
        ],
        pass_score=3,
    ),
]

_BY_ID: Dict[str, Module] = {m.id: m for m in MODULES}


def by_id(module_id: str):
    return _BY_ID.get(module_id)


def landing_examples() -> List[Example]:
    """Four canonical clips for the landing page sample players."""
    return [
        _pick("heart", "binary", "normal"),
        _pick("heart", "binary", "abnormal"),
        _pick("lung", "binary", "normal"),
        _pick("lung", "6class", "Wheezing"),
    ]


def grade_quiz(module_id: str, answers: List) -> dict:
    """Grade a checkpoint submission against module ground truth."""
    mod = by_id(module_id)
    if not mod:
        return {"error": "unknown module"}
    results = []
    for i, q in enumerate(mod.quiz):
        pick = answers[i] if i < len(answers) else None
        try:
            pick_i = None if pick is None else int(pick)
        except (TypeError, ValueError):
            pick_i = None
        correct = pick_i == q.correct
        finding, awareness = knowledge(q.knowledge_key)
        results.append({
            "prompt": q.prompt,
            "options": q.options,
            "correct": correct,
            "correct_label": q.options[q.correct] if q.options else "",
            "sample_id": q.sample_id,
            "finding": finding,
            "awareness": awareness,
            "note": q.note,
        })
    score = sum(1 for r in results if r["correct"])
    return {
        "module_id": module_id,
        "total": len(results),
        "score": score,
        "passed": score >= mod.pass_score,
        "pass_score": mod.pass_score,
        "results": results,
    }
