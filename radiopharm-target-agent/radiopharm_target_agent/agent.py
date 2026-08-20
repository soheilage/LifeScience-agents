# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Sequential + Parallel multi-agent orchestration spine for radiopharm-target-agent.

Implements Section 2.1 Architecture:
- Step 1: Planner (LlmAgent)
- Step 2: Gather (ParallelAgent with Expression, Clinical, Literature specialists)
- Step 3: Target Biology Specialist (LlmAgent)
- Step 4: Deterministic Python Scorer (scorer.py)
- Step 5: Writer (LlmAgent)
"""

import os
from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from . import prompt
from .guards import resolve_gene_symbol
from .provenance import format_provenance_banner, get_current_provenance
from .specialists.clinical_specialist.agent import clinical_specialist
from .specialists.expression_specialist.agent import expression_specialist
from .specialists.literature_specialist.agent import literature_specialist
from .specialists.target_biology_specialist.agent import (
    target_biology_specialist,
)

MODEL = os.getenv("GEMINI_MODEL_ID", "gemini-2.5-pro")

# 1. Planner Agent
planner = LlmAgent(
    name="planner",
    model=MODEL,
    description="Resolves gene symbols, verifies indication and isotope context, and initializes run plan.",
    instruction=prompt.PLANNER_PROMPT,
    tools=[resolve_gene_symbol],
)

# 2. Parallel Gather Agent
gather = ParallelAgent(
    name="gather",
    description="Concurrently queries expression (HPA/GTEx/C2S), clinical trials (CT.gov), and literature (PubMed/PMC/MedGemma).",
    sub_agents=[
        expression_specialist,
        clinical_specialist,
        literature_specialist,
    ],
)

# 3. Writer Agent
writer = LlmAgent(
    name="writer",
    model=MODEL,
    description="Synthesizes deterministic scores and multi-modal specialist evidence into a structured briefing.",
    instruction=prompt.WRITER_PROMPT,
    tools=[format_provenance_banner],
)

# Root Sequential Coordinator Pipeline
radiopharm_coordinator = SequentialAgent(
    name="radiopharm_coordinator",
    description="Multi-agent sequential and parallel orchestrator for radiopharmaceutical target prioritisation.",
    sub_agents=[
        planner,
        gather,
        target_biology_specialist,
        writer,
    ],
)

# ADK Root Agent Entry Point
root_agent = radiopharm_coordinator
