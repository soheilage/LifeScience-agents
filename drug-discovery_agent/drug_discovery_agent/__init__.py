# Copyright 2025 Google LLC
import os

# Set fallback project and location defaults if not specified
if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
    os.environ["GOOGLE_CLOUD_PROJECT"] = os.environ.get("CLOUD_ML_PROJECT_ID", "txgemma-501602")
if not os.environ.get("GOOGLE_CLOUD_LOCATION"):
    os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"
