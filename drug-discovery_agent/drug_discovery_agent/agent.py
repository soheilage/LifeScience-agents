# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Defines the main 'discovery_coordinator' agent."""
import os

# Ensure project details and Vertex AI mode are set for ADK models
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
    os.environ["GOOGLE_CLOUD_PROJECT"] = os.environ.get("CLOUD_ML_PROJECT_ID", "txgemma-501602")
if not os.environ.get("GOOGLE_CLOUD_LOCATION"):
    os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"

from google.adk.agents import Agent

from . import prompt

from .specialists.compound_analyzer import agent as compound_analyzer_agent
from .specialists.literature_researcher import agent as literature_researcher_agent

# Use a powerful model for the coordinator's reasoning.
MODEL = "gemini-2.5-pro"

discovery_coordinator = Agent(
    name="discovery_coordinator",
    model=MODEL,
    description="The main agent that coordinates drug discovery tasks.",
    instruction=prompt.DISCOVERY_COORDINATOR_PROMPT,
    sub_agents=[
        compound_analyzer_agent.compound_analyzer,
        literature_researcher_agent.literature_researcher,
    ],
)

# The root_agent is the entry point for the ADK.
root_agent = discovery_coordinator
