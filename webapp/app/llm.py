"""LLM integration for automated, personalized auscultation reports.

Two modes:

* ``LLMClient`` — OpenAI-compatible chat-completions via HTTP, configured with
  environment variables (`CARDIASENSE_LLM_*`). Produces a personalized,
  structured report grounded in the head probabilities and patient context.
* ``LLMSynthesizer`` — deterministic offline fallback that returns the same
  structured shape (summary, findings, recommendations for medicine / diet /
  environment, next steps, disclaimer) from the knowledge base, so the
  product works and stays testable without any API key.

Both return the same JSON structure, so the web app and tests are
provider-agnostic. Guardrails: the prompt/system instructs the model to treat
the output as educational, never a diagnosis, and to not fabricate clinical
facts; PHI is only sent when explicitly provided by the user.
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

from . import config

DISCLAIMER = config.DISCLAIMER

# recommended-message outlines per predicted class (extended knowledge)
REC_MEDICAL = {
    "Atrial Fibrillation": ["Discuss anticoagulation/rate-control options with a clinician",
                            "Confirm with a 12-lead ECG if symptoms suggest AF"],
    "AV Block": ["Review the rhythm with a clinician; ECG is usually needed"],
    "Tachycardia": ["If persistent or symptomatic, seek medical advice"],
    "S3": ["In adults an S3 may relate to reduced pumping function; correlate clinically"],
    "S4": ["S4 is often a stiffening marker (e.g., hypertension); review blood-pressure control"],
    "Wheezing": ["Evaluate for asthma/COPD with a clinician; use reliever inhalers as prescribed"],
    "Fine Crackles": ["Consider follow-up for possible interstitial/fluid changes"],
    "Coarse Crackles": ["Secretions may be present; notify a clinician if breathing worsens"],
    "Rhonchi": ["Ease secretions with hydration/coughing; review if persistent"],
    "Pleural Rub": ["Review for pleurisy/infection; seek care if chest pain or fever"],
    "Late Diastolic Murmur": ["Echocardiography is often indicated; discuss with a doctor"],
    "Mid Systolic Murmur": ["Common and often innocent; confirm origin with auscultation by a clinician"],
    "Late Systolic Murmur": ["Ddx includes mitral valve prolapse; clinical exam advised"],
    "Early Systolic Murmur": ["Usually benign; clinical correlation advised"],
}
REC_DIET = {
    "Atrial Fibrillation": ["Keep caffeine and alcohol modest", "Stay hydrated; avoid large meals late at night"],
    "Tachycardia": ["Limit high-caffeine energy drinks if they trigger palpitations"],
    "S4": ["Prefer a low-sodium pattern if blood pressure is high"],
    "AV Block": ["Balanced diet; avoid excessive stimulants"],
    "Wheezing": ["Avoid known food triggers if asthma is food-sensitive", "Stay hydrated to keep airways moist"],
    "Rhonchi": ["Warm fluids can help clear mucus"],
    "Fine Crackles": ["Stay well hydrated; follow any fluid-restriction advice from a clinician"],
    "Pleural Rub": ["Hydration and, if prescribed, anti-inflammatory intake with food"],
}
REC_ENV = {
    "Wheezing": ["Reduce smoke, dust and strong fumes", "Keep indoor humidity moderate"],
    "Rhonchi": ["Avoid smoky/ dusty environments", "Maintain good ventilation"],
    "Fine Crackles": ["Minimise exposure to airborne irritants and mould"],
    "Coarse Crackles": ["Avoid smoke inhalation; keep the airway environment clean"],
    "Pleural Rub": ["Avoid respiratory irritants while inflammation settles"],
    "Atrial Fibrillation": ["Reduce stress triggers that worsen palpitations"],
    "Tachycardia": ["Moderate intense exercise while symptoms are being assessed"],
}

GENERAL_MEDICAL = "If you have symptoms or concerns, discuss this recording with a healthcare professional."
GENERAL_DIET = "A balanced, low-processed diet generally supports heart and lung health."
GENERAL_ENV = "Avoid tobacco smoke and keep living spaces ventilated."

CONTEXT_HINTS = {
    "asthma": "Patient context mentions asthma — airway findings should be weighed accordingly.",
    "copd": "Patient context mentions COPD — chronic airway disease context applies.",
    "shortness of breath": "Patient reports shortness of breath — assess symptom severity clinically.",
    "palpitations": "Patient reports palpitations — correlate with rhythm findings and ECG.",
    "chest pain": "Patient reports chest pain — recommend urgent care guidance.",
    "smoking": "Smoking history noted — strengthens lung-exposure considerations.",
    "cough": "Cough reported — consider infection/adventitious-sound correlation.",
    "high blood pressure": "History of high blood pressure — heart-stiffness findings are relevant.",
    "diabetes": "Diabetes history noted — cardiometabolic guidance applies.",
}


def _finding_summary(heads: List[dict]) -> str:
    lines = []
    for h in heads:
        probs = h.get("probs") or []
        classes = h.get("classes") or []
        top = ", ".join(f"{c}={p:.0%}" for c, p in
                        sorted(zip(classes, probs), key=lambda x: x[1], reverse=True)[:3] if c)
        conf = h.get("confidence", 0) or 0
        lines.append(f"- {h.get('label', h.get('key', ''))}: **{h.get('pred')}** (confidence {conf:.0%})"
                     + (f"; top: {top}" if top else ""))
    return "\n".join(lines) if lines else "- no predictions available"


def build_prompt(findings: List[dict], patient_context: str = "", history: Optional[List[dict]] = None) -> str:
    ctx = f"\nPatient context / conversation:\n{patient_context}" if patient_context.strip() else \
        "\nPatient context: none provided (anonymous)."
    conv = ""
    if history:
        conv = "\nConversation so far:\n" + "\n".join(
            f"- {m.get('role')}: {m.get('content')}" for m in history[-8:])
    return f"""You are CardiaSense, an educational health-awareness assistant for
heart/lung sound analysis. You write brief, plain-language reports.

Auscultation model findings (ensemble of neural heads):
{_finding_summary(findings)}
{ctx}{conv}

Write a personalized report as a single JSON object:
{{"summary": "...", "findings": ["..."], "recommendations": {{"medical": ["..."], "diet": ["..."], "environment": ["..."]}}, "next_steps": ["..."], "disclaimer": "{DISCLAIMER}"}}

Rules: keep it educational, not a diagnosis; ground recommendations in the
findings and patient context; avoid inventing lab values or diagnoses; 2-4 items
per recommendation area; concise."""


def parse_llm_json(text: str) -> Optional[dict]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


class LLMClient:
    def __init__(self) -> None:
        self.base_url = os.environ.get("CARDIASENSE_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.environ.get("CARDIASENSE_LLM_MODEL", "gpt-4o-mini")
        self.api_key = os.environ.get("CARDIASENSE_LLM_API_KEY", "")
        self.timeout = float(os.environ.get("CARDIASENSE_LLM_TIMEOUT", "30"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def complete(self, messages: List[dict]) -> Optional[str]:
        import urllib.request

        body = json.dumps({"model": self.model, "messages": messages,
                           "temperature": 0.4, "response_format": {"type": "json_object"}}).encode()
        req = urllib.request.Request(
            self.base_url + "/chat/completions", data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"]


class LLMSynthesizer:
    """Offline deterministic narrative (same output shape as the LLM client)."""

    def __init__(self) -> None:
        self.model = "rule-based-synthesizer-v1"

    def synthesize(self, findings: List[dict], patient_context: str = "") -> dict:
        ctx = patient_context.strip().lower()
        hints = [v for k, v in CONTEXT_HINTS.items() if k in ctx]
        med: List[str] = []; diet: List[str] = []; env: List[str] = []
        fnds: List[str] = []
        abnormal = False
        for h in findings:
            pred = h.get("pred", "unknown")
            conf = h.get("confidence", 0)
            fnds.append(f"{h.get('label', h.get('key'))}: {pred} (confidence {conf:.0%})")
            if pred.lower() != "normal" and h.get("kind") == "binary":
                abnormal = True
            med += REC_MEDICAL.get(pred, [])
            diet += REC_DIET.get(pred, [])
            env += REC_ENV.get(pred, [])
        med = list(dict.fromkeys(med)) or [GENERAL_MEDICAL]
        diet = list(dict.fromkeys(diet)) or [GENERAL_DIET]
        env = list(dict.fromkeys(env)) or [GENERAL_ENV]
        if hints:
            med.insert(0, "Personalized from your stated context: " + "; ".join(hints))
        summary = ("The model flagged at least one possible abnormality. A clinician should "
                   "interpret these findings with your full history and an examination."
                   if abnormal else
                   "No abnormality was flagged in this recording. This is reassuring but does not "
                   "exclude disease, especially from a short recording.")
        return {
            "provider": "synthesizer", "model": self.model,
            "summary": summary, "findings": fnds,
            "recommendations": {"medical": med, "diet": diet, "environment": env},
            "next_steps": ["Repeat and compare over a few days if symptoms persist",
                           "Share this recording with your clinician at the next visit"],
            "personalized": bool(ctx), "disclaimer": DISCLAIMER,
        }


def generate_narrative(findings: List[dict], patient_context: str = "",
                       history: Optional[List[dict]] = None) -> dict:
    """Return a structured narrative; LLM when configured, else the synthesizer."""
    client = LLMClient()
    if client.enabled:
        try:
            content = client.complete([
                {"role": "system", "content": "You produce educational auscultation reports as JSON only."},
                {"role": "user", "content": build_prompt(findings, patient_context, history)},
            ])
            parsed = parse_llm_json(content or "")
            if parsed:
                parsed["provider"] = "llm"
                parsed["model"] = client.model
                parsed.pop("system_reminder", None)
                return parsed
        except Exception as e:  # fall back to the synthesizer on any failure
            print(f"[llm] LLM call failed ({type(e).__name__}: {e}); using synthesizer.")
    return LLMSynthesizer().synthesize(findings, patient_context)