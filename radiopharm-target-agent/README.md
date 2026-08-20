# radiopharm-target-agent

A multi-agent system for radiopharmaceutical target assessment and prioritisation.

## Overview
Given one or more candidate targets, an indication, and an isotope context, this agent gathers:
- Tumour vs. normal expression evidence (HPA, GTEx)
- Organ-at-Risk (OAR) safety panels with explicit missing-data handling
- Single-cell compartment localization and heterogeneity (Cell2Sentence / AnnData)
- Clinical trial landscape and eligibility criteria (ClinicalTrials.gov API v2)
- Full-text literature synthesis with dosimetric parameter extraction (PubMed / PMC / MedGemma)
- Target dynamics, internalization, shedding, and tractability (UniProt / TxGemma / PubChem)

The agent produces an auditable, deterministically scored prioritisation briefing with immutable provenance and source references.

## Key Design Principles
1. **Evidence is typed, not prose:** All specialists return validated `Claim` objects.
2. **Anti-hallucination source enforcement:** A measured claim without a source cannot be constructed (`Claim(status="measured", sources=[])` raises `ValidationError`).
3. **Deterministic Python scoring:** `scorer.py` produces all numeric values and rankings using `weights.yaml`.
4. **Missing data is not zero:** Distinguishes `not_detected` from `not_measured`.
5. **Enrichment models off critical path:** LLM enrichment failures gracefully degrade to `unavailable` status without failing the pipeline.

## Usage
```bash
poetry run pytest
poetry run python query_agent.py
```
