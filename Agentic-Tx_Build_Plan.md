# Agentic-Tx — Build Plan

Companion to the Solution Design Document. Sequenced so nothing is built on an unverified assumption.

---

## 1. Capability → tool mapping

The model card defines four usable modes. Each becomes a separate tool with its own parser, because the output shapes differ.

| Mode | What TxGemma returns | Tool | Parser |
|------|---------------------|------|--------|
| **Classification** | Multiple choice, e.g. `(B)` | `predict_classification` | Map letter → label via the task's answer key |
| **Regression** | Numeric value | `predict_regression` | Parse float, attach units from task metadata |
| **Generation** | Free text (retrosynthesis: product → reactant set) | `generate_reactants` | Validate output SMILES through RDKit; drop invalid |
| **Chat** | Natural-language explanation | `explain_prediction` | Pass through; requires a prior prediction as context |

Supporting tools (non-TxGemma): `smiles_from_name`, `molecule_properties` (RDKit), `pubmed_search`.

**Routing rule for the orchestrator:** the TDC task name determines the mode, not the user's phrasing. Ship a task registry that maps `task_name → {mode, prompt_template, answer_key, units}`, and have the agent select a task first, then the tool follows automatically.

---

## 2. Task registry

Build this before any tool code. It is the contract between orchestrator and model.

```python
TASK_REGISTRY = {
  "BBB_Martins":   {"mode": "classification", "answers": {"(A)": "not permeable", "(B)": "permeable"}},
  "hERG":          {"mode": "classification", "answers": {"(A)": "not blocker",    "(B)": "blocker"}},
  "CYP3A4_Veith":  {"mode": "classification", "answers": {"(A)": "not inhibitor",  "(B)": "inhibitor"}},
  "Lipophilicity_AstraZeneca": {"mode": "regression", "units": "logD"},
  "BindingDB_Kd":  {"mode": "regression", "units": "nM", "inputs": ["smiles", "sequence"]},
  "USPTO50k":      {"mode": "generation",  "output": "reactant SMILES set"},
  # ...extend from tdc_prompts.json
}
```

Scope decision for v1: **ship ~8 tasks, not all of them.** Pick 4 classification, 2 regression, 1 generation, 1 multi-input (binding affinity). Breadth is cheap to add later; a wrong parser is expensive to debug.

---

## 3. Build sequence

### Stage 1 — Endpoint contract (½ day)
Call your deployed endpoint directly, no agent, no ADK.
- Confirm the request payload key (`prompt` / `inputs` / `instances[].text`)
- Run one prompt of each mode; record the exact raw output string
- Confirm which variant is deployed (predict vs chat). If only predict is deployed, either stand up a second endpoint for chat or drop `explain_prediction` from v1.

**Exit:** three saved raw responses, one per mode. These become parser test fixtures.

### Stage 2 — Task registry + prompt builder (½ day)
Load `tdc_prompts.json`, build the registry, implement `build_prompt(task_name, **inputs)`.
- Unit test: every registry entry renders a prompt with no unsubstituted placeholders.

### Stage 3 — Tools (1–2 days)
One tool at a time, each with unit tests against the Stage 1 fixtures.
1. `predict_classification` — highest value, build first
2. `predict_regression` — parser must handle stray text around the number
3. `generate_reactants` — add RDKit validity check on outputs
4. `explain_prediction` — takes prior result as context
5. `smiles_from_name`, `molecule_properties`, `pubmed_search`

All tools return dicts, never raise. Unknown task → return the valid task list so the agent can self-correct.

**Exit:** `pytest` green; each tool callable standalone from a Python shell.

### Stage 4 — Agent assembly (½ day)
ADK `LlmAgent`, Gemini 2.5 Flash, system prompt encoding the routing rule and the research-use-only constraint. Test via `adk web` and inspect the tool-call trace.

**Exit:** the local test table in the SDD (Phase 3) passes.

### Stage 5 — Deploy + cloud test (1 day)
`agent_engines.create()` per SDD Phase 4. Grant the Agent Engine SA `roles/aiplatform.user` on the TxGemma endpoint. Re-run the same test table remotely; outputs must match local.

**Exit:** identical answers local vs cloud, traces visible in Cloud Trace.

### Stage 6 — Hardening (1 day)
Loop guard, timeouts, task-selection accuracy check on ~20 held-out queries, endpoint min-replicas, disclaimer enforcement.

---

## 4. Acceptance tests

| # | Query | Exercises |
|---|-------|-----------|
| 1 | "Is aspirin BBB permeable?" | name→SMILES → classification |
| 2 | "What's the lipophilicity of ibuprofen?" | regression, units in output |
| 3 | "How would I synthesise this compound? [SMILES]" | generation, RDKit validation |
| 4 | "Why did you predict that?" (follow-up to #1) | chat, context carried in session |
| 5 | "Predict binding affinity of [SMILES] to [sequence]" | multi-input regression |
| 6 | "Compare hERG risk of aspirin vs ibuprofen" | two calls + synthesis |
| 7 | "What dose should I prescribe?" | refusal |
| 8 | Nonsense task name | graceful error + recovery |

---

## 5. Effort

~5 developer-days to a working cloud deployment, assuming the endpoint is healthy and the payload schema resolves cleanly in Stage 1. The two things most likely to add time: the endpoint schema differing from expectation, and the generation-mode parser, since free-text output is the least predictable of the three.

## 6. Explicitly deferred

Fine-tuning, custom UI, more than ~8 TDC tasks, caching, batch prediction, A2A/multi-agent composition.
