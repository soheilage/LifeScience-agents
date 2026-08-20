# Comprehensive Assessment: AI Agent Architecture for Radiopharmaceutical Target Prioritization

## 1. Executive Summary & Problem Framing

### 1.1 Problem Statement
Evaluating and prioritizing biological targets for radiopharmaceuticals (targeted radionuclide therapies and radiotheranostics) is a multi-dimensional, time-consuming process. It requires researchers to cross-reference disconnected data modalities:
1. **Target Expression & Specificity:** Differential expression between malignant tumor cells and critical organs-at-risk (OAR).
2. **Target Biology & Dynamics:** Cell-surface localization, internalization rates, and antigen shedding.
3. **Clinical & Trial Landscape:** Ongoing clinical trials, patient eligibility criteria, therapeutic combinations, and clinical safety/efficacy evidence.
4. **Radiochemical & Dosimetric Feasibility:** Organ-absorbed doses, biodistribution, and therapeutic index.

### 1.2 Repository Evaluation Summary
The existing codebase contains strong, modular foundations across three agents:
- **`clinical-research-synthesizer`** provides end-to-end clinical trial mining (ClinicalTrials.gov) and full-text literature extraction (PubMed/PMC/PDF + MedGemma).
- **`drug-discovery-agent` (Agentic-Tx)** provides candidate trade-off evaluation frameworks and integration with deployed **TxGemma** models.
- **`medical-research`** demonstrates multi-model routing between MedGemma and TxGemma.

**Core Gap:** None of the existing agents possess tools to query **quantitative target expression data (Tumour vs. Normal tissue)**. Integrating the **Cell2Sentence (C2S)** single-cell transcriptomic framework alongside curated reference databases (Human Protein Atlas, GTEx) bridges this gap.

---

## 2. Assessment of Existing Agents in the Repository

```
+---------------------------------------------------------------------------------------------------------+
|                                    REPOSITORY AGENT CAPABILITIES                                        |
+-----------------------------+------------------------------------+--------------------------------------+
| Agent                       | Core Strengths                     | Gaps for Radiopharm Use Case         |
+-----------------------------+------------------------------------+--------------------------------------+
| drug-discovery-agent        | • TxGemma chat/predict endpoints   | • No target expression data          |
| (Agentic-Tx)                | • PubMed abstract retrieval        | • No clinical trial search           |
|                             | • Multi-step comparative reasoning | • Small-molecule ClinTox focused     |
+-----------------------------+------------------------------------+--------------------------------------+
| clinical-research-          | • ClinicalTrials.gov API v2 search | • No omics/expression databases     |
| synthesizer                 | • PMC full text & PDF extraction   | • No radiopharm-specific heuristics  |
|                             | • MedGemma structured summaries    | • Does not leverage TxGemma          |
+-----------------------------+------------------------------------+--------------------------------------+
| medical-research            | • TxGemma + MedGemma co-deployment | • No autonomous planning/synthesis   |
|                             | • Disease background Q&A           | • No external search/retrieval tools |
|                             |                                    | • Rigid single-task prediction (BBB) |
+-----------------------------+------------------------------------+--------------------------------------+
```

### 2.1 `drug-discovery-agent` (Agentic-Tx)
- **Coordinator:** `discovery_coordinator` (`gemini-2.5-pro`)
- **Specialists:** `compound_analyzer` (PubChem, TxGemma ClinTox predict) and `literature_researcher` (PubMed API, TxGemma Chat).
- **Assessment:** Excellent at evaluating candidate trade-offs and domain chat reasoning via TxGemma. However, it cannot query expression levels across tissues or verify clinical trials.

### 2.2 `clinical-research-synthesizer`
- **Coordinator:** `research_coordinator` (`gemini-3.1-pro-preview`)
- **Specialists:** `literature_researcher` (PubMed + PMC + MedGemma 27B), `clinical_trial_specialist` (ClinicalTrials.gov), `search_specialist` (PMC full text).
- **Assessment:** Directly solves the **clinical evidence gathering** requirement. It extracts trial phases, eligibility criteria, and structured findings from full-text literature with citation tracking. It lacks expression tools and radiopharmaceutical prioritization parameters.

### 2.3 `medical-research`
- **Coordinator:** `medical_coordinator` (`gemini-2.5-pro`)
- **Specialists:** `medical_analyst` (TxGemma BBB prediction) and `medical_search` (MedGemma Q&A).
- **Assessment:** Functions as a simple single-turn router without autonomous research planning or external data retrieval APIs.

---

## 3. Evaluation of the Cell2Sentence (C2S) Model

Cell2Sentence (C2S) transforms single-cell RNA sequencing (scRNA-seq) matrices into text "sentences" by ranking gene names in order of relative abundance/expression per cell.

### 3.1 What Cell2Sentence Solves
1. **Single-Cell Tumour vs. Stroma Deconvolution:** Bulk RNA sequencing averages cancer cells with stromal fibroblasts, endothelial cells, and immune infiltrates. C2S distinguishes whether target expression is on malignant epithelial cells or bystander cells.
2. **Granular Organ-at-Risk (OAR) Cell-Type Screening:** C2S enables querying specific vulnerable single-cell lineages (e.g., renal proximal tubule epithelial cells, salivary gland acinar cells, hematopoietic stem cells) to identify off-target toxicity risks.
3. **Native LLM / TxGemma Compatibility:** Because transcriptomic states are tokenized as text sequences, C2S integrates directly into causal language model prompts without specialized numeric tensor wrappers.
4. **Expression Heterogeneity:** Evaluates whether target expression is uniform across tumor cells or confined to a subclone.

### 3.2 Limitations of Cell2Sentence
1. **Rank-Based (Ordinal) vs. Absolute Receptor Copy Number:** C2S provides relative gene rankings rather than absolute quantification (TPM, copies per cell). Radiopharmaceuticals require high absolute surface density ($>10^5$ receptors/cell) for sufficient radiation payload delivery.
2. **mRNA Abundance vs. Cell-Surface Protein Presentation:** C2S models transcriptomic mRNA, not post-translational surface localization or membrane accessibility.
3. **Generative vs. Deterministic Ground Truth:** C2S can smooth over or hallucinate rare cell states; regulatory target assessment requires auditable reference datasets (e.g., HPA, GTEx).

---

## 4. Recommended Integrated Architecture

```
                          ┌─────────────────────────────────────────────────────────────┐
                          │    Radiopharmaceutical Target Prioritization Coordinator     │
                          │                (Gemini 2.5 / 3.1 Pro Engine)                │
                          └──────────────────────────────┬──────────────────────────────┘
                                                         │
         ┌───────────────────────────────┬───────────────┴───────────────┬───────────────────────────────┐
         ▼                               ▼                               ▼                               ▼
┌───────────────────┐           ┌───────────────────┐           ┌───────────────────┐           ┌───────────────────┐
│ Target Expression │           │ Single-Cell (C2S) │           │ Clinical Evidence │           │  TxGemma / Med-   │
│ Specialist (APIs) │           │ Transcriptomics   │           │    Specialist     │           │  Gemma Evaluator  │
├───────────────────┤           ├───────────────────┤           ├───────────────────┤           ├───────────────────┤
│ • Human Protein   │           │ • Single-cell     │           │ • ClinicalTrials  │           │ • Target biology  │
│   Atlas (HPA) API │           │   malignant vs.   │           │   API v2 search   │           │   & tractability  │
│ • GTEx Normal     │           │   stroma contrast │           │ • Trial criteria  │           │ • Internalization │
│   Tissue API      │           │ • OAR cell-type   │           │   & phase parsing │           │   & shedding text │
│ • TCGA Tumour RNA │           │   safety checks   │           │ • PMC/PDF Full-   │           │ • ClinTox ligand  │
│ • Macro T/N ratio │           │ • Heterogeneity   │           │   Text Synthesis  │           │   safety rating   │
└───────────────────┘           └───────────────────┘           └───────────────────┘           └───────────────────┘
```

---

## 5. Scope Analysis: Covered vs. Partially Covered vs. Not Covered

### 5.1 Aspects the Integrated Agent CAN Address (Fully / High Confidence)

| Capability | Implementation Mechanism | Radiopharmaceutical Value |
| :--- | :--- | :--- |
| **Macro Tumour vs. Normal Expression Contrast** | HPA API + GTEx REST endpoints | Evaluates bulk tumor-to-normal contrast ratio and baseline healthy organ expression. |
| **Single-Cell Tumour Specificity** | Cell2Sentence (C2S) Engine | Confirms target expression is restricted to malignant cells and not non-malignant tumor stroma. |
| **Organ-at-Risk (OAR) Screening** | C2S + GTEx / HPA | Screens critical radiation-sensitive cell lineages (renal tubules, bone marrow, salivary glands). |
| **Clinical Trial Landscape Mapping** | `clinical_trial_specialist` (ClinicalTrials.gov) | Identifies active, completed, and recruiting radioligand trials ($^{177}\text{Lu}$, $^{225}\text{Ac}$, $^{68}\text{Ga}$). |
| **Trial Eligibility & Criteria Parsing** | `get_eligibility_criteria_from_api` | Identifies patient selection criteria, baseline imaging SUV cutoffs, and prior lines of therapy. |
| **Full-Text Literature Synthesis** | `literature_researcher` + MedGemma 27B / TxGemma | Synthesizes published clinical endpoints (ORR, PFS, OS, MTD, dosimetry findings) with citations. |
| **Target Expression Heterogeneity** | C2S single-cell cluster dispersion | Identifies bimodal expression or subclonal distribution indicating risk of treatment escape. |
| **Multi-Criteria Prioritization Scorecard** | Coordinator Decision Engine (Gemini Pro) | Synthesizes expression, safety, and clinical pipeline maturity into an auditable target ranking score. |

---

### 5.2 Aspects the Integrated Agent CAN Address PARTIALLY (Literature & Inference)

| Parameter | What the Agent CAN Do | Fundamental Gap / Limitation |
| :--- | :--- | :--- |
| **Target Internalization & Kinetics** | Mines literature for reported endocytosis mechanisms, internalization rates, and intracellular radiometal retention ($^{177}\text{Lu-DOTA}$). | Cannot computationally simulate de novo internalization kinetics or trafficking for novel uncharacterized targets. |
| **Target Shedding / Soluble Antigen Sink** | Identifies known soluble splice variants, shed extracellular domains (ECD), or circulating serum baselines (e.g., shed HER2, soluble Mesothelin) via UniProt/literature. | Cannot predict de novo shedding rates or circulating blood-pool sink effects without empirical ELISA data. |
| **Cell-Surface Accessibility & Localization** | Verifies annotated transmembrane domains and membrane vs. intracellular subcellular localization via UniProt and HPA. | Cannot model 3D steric accessibility, epitope masking, or glycosylation interference in solid tissue matrices. |
| **Comparative Candidate Profiling** | Ranks multiple candidate targets side-by-side using structured scoring templates. | Weightings require manual calibration based on isotope modality (e.g., short-range alpha vs. long-range beta). |

---

### 5.3 Aspects the Integrated Agent CANNOT Address (Out-of-Scope / Hard Limitations)

These areas represent physical, biophysical, or wet-lab constraints that require specialized numerical modeling software or laboratory assays:

1. **Patient-Specific Radiation Dosimetry & Pharmacokinetics (PK/PD):**
   * *Limitation:* Radiopharmaceutical safety depends on organ-absorbed doses ($\text{Gy/GBq}$) in kidneys, bone marrow, and salivary glands.
   * *Why:* Language models and scRNA-seq cannot simulate whole-body clearance rates, renal reabsorption, or voxel-based dosimetry. This requires clinical imaging timepoints (SPECT/PET) and physics tools (OLINDA/EXM, MIRDcalc).
2. **Radiochemical & Chelator Stability in Silico:**
   * *Limitation:* The agent cannot simulate in vivo radiolabeling stability (e.g., $^{225}\text{Ac}$ recoil daughter detachment, $^{177}\text{Lu}$ transchelation, radiolysis).
   * *Why:* Requires empirical wet-lab radiochemistry and HPLC/mass-spectrometry assays.
3. **Absolute Surface Receptor Density ($B_{\text{max}}$):**
   * *Limitation:* C2S outputs relative rank; bulk RNA-seq outputs population TPM. Neither provides absolute receptor copy numbers per cell ($>10^5\text{ to }10^6$ required for therapy).
   * *Why:* Requires quantitative Scatchard analysis, quantitative flow cytometry, or calibrated autoradiography.
4. **Radiation Biophysics & Particle Cross-Fire Range Simulation:**
   * *Limitation:* Cannot calculate physical energy deposition tracks ($50\text{–}100\,\mu\text{m}$ alpha vs. $1\text{–}2\,\text{mm}$ beta) relative to heterogeneous target-negative cells in a tumor mass.

---

## 6. Target Evaluation Scorecard Template

When running a target query (e.g., *"Evaluate and compare FOLH1 (PSMA) vs. SSTR2 for radiopharmaceutical development"*), the integrated agent generates a structured target briefing:

```markdown
### Radiopharmaceutical Target Assessment: [Target Gene Symbol]

#### 1. Expression Contrast Profile
- **Tumour Expression (TCGA / C2S):** High in >85% malignant epithelial cells (Top 5th percentile rank).
- **Tumour Stroma Contrast (C2S):** Target confined to malignant cells; negative on CAFs and immune infiltrates.
- **Normal Tissue Baseline (GTEx / HPA):** Minimal expression in vital organs; moderate expression in [Organ X].
- **Organ-at-Risk (OAR) Single-Cell Check (C2S):** Low in renal proximal tubules; moderate in salivary acinar cells.

#### 2. Target Biology & Dynamics
- **Cellular Localization:** Transmembrane (UniProt confirmed, HPA membrane staining 3+).
- **Internalization Evidence:** Receptor-mediated endocytosis reported in literature ([Source 1]).
- **Shedding Risk:** No significant soluble circulating isoform reported.
- **Heterogeneity:** Homogeneous in primary lesions; subclonal variation noted in neuroendocrine metastases ([Source 2]).

#### 3. Clinical & Trial Evidence
- **Active Radioligand Trials:** 24 active trials (Phase 1–3) evaluating 177Lu- and 225Ac-conjugated targeting vectors.
- **Key Trial Pre-conditions:** SUVmax >= 15 on diagnostic 68Ga PET scan (NCT03511664).
- **Dose-Limiting Toxicities Reported:** Xerostomia (salivary gland) and myelosuppression (bone marrow).

#### 4. Target Prioritization Summary
- **Tumour Selectivity Score:** 9/10
- **Safety / OAR Margin:** 7/10 (Salivary gland / renal monitoring required)
- **Clinical Validation Level:** High (Established clinical track record)
- **Recommendation:** High-priority candidate for targeted alpha/beta therapy.
```

---

## 7. Strategic Recommendations & Roadmap

1. **Step 1: Unify Existing Agent Modules:** Merge `clinical_trial_specialist` and `literature_researcher` from `clinical-research-synthesizer` into a new `radiopharm_assessment_agent` powered by Gemini 2.5/3.1 Pro.
2. **Step 2: Add Expression Specialist Tools:** Implement Python tool functions wrapping REST APIs for:
   - Human Protein Atlas (HPA) API (IHC & tissue RNA).
   - GTEx Portal API (Normal tissue expression baselines).
3. **Step 3: Integrate Cell2Sentence Endpoint:** Deploy a C2S-finetuned model or scRNA-seq rank retrieval service as an ADK tool for single-cell deconvolution.
4. **Step 4: Specialize TxGemma Prompts:** Configure TxGemma to score radiopharmaceutical tractability, membrane localization, and off-target liability profiles.
