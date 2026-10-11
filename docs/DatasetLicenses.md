# Dataset License Registry

Commercial-use gate for every dataset that trains, evaluates, or ships with a
Asculto model. **Rule:** a dataset enters the commercial pipeline only after a
dated sign-off below. Do not train, fine-tune, or ship weights from a dataset
marked *unverified* until it has been reviewed.

Verified against the sources listed **2026-10-06**.

| Dataset | License | Commercial use | Where used | Sign-off |
|---|---|---|---|---|
| **HLS-CMDS** | CC BY 4.0 (Zenodo [15376628](https://zenodo.org/records/15376628); DOI [10.1109/IEEEDATA.2025.3566012](https://doi.org/10.1109/IEEEDATA.2025.3566012)) | **Yes, with attribution** | All served heads (source, heart, lung) and the game audio | ✅ 2026-10-06 |
| PhysioNet/CinC 2016 | ODC-BY 1.0 | **Yes, with attribution** | Benchmarks only (not shipped) | ✅ 2026-10-06 |
| CirCor DigiScope | ODC-BY 1.0 | **Yes, with attribution** | Benchmarks only (not shipped) | ✅ 2026-10-06 |
| ICBHI 2017 | Unverified — research-only terms reported | **Assume no until reviewed** | Not used | ⛔ not cleared |
| BMD-HS | Unverified | **Assume no until reviewed** | Not used | ⛔ not cleared |

## Attribution implementation (HLS-CMDS, CC BY 4.0)

Attribution is surfaced in the product and the report payload:

- App footer: `webapp/templates/base.html` (every page).
- Report credits: `webapp/templates/report.html` from `report.credits`.
- Report/API JSON: `credits` field built in `webapp/app/report.py` from
  `config.DATASET_CREDIT`.

Citation text:

> Torabi, Y., Shirani, S., & Reilly, J. P. (2025). *HLS-CMDS: Heart and Lung
> Sounds Dataset Recorded from a Clinical Manikin using Digital Stethoscope.*
> IEEE Data Descriptions. DOI 10.1109/IEEEDATA.2025.3566012. Licensed CC BY 4.0.

## Restricted-data handling

PhysioNet's MIMIC-family DUAs prohibit third-party LLM/API processing. Do **not**
route restricted data through cloud LLMs; the offline `LLMSynthesizer` and a
local Ollama endpoint keep processing on-device.

## Review log

| Date | Reviewer | Change |
|---|---|---|
| 2026-10-06 | Implementation (plan task 1) | Initial registry; HLS-CMDS cleared for commercial use with attribution; ICBHI/BMD-HS flagged unverified. |
