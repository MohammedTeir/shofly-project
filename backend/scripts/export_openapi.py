"""Regenerate the OpenAPI snapshot after an intentional API change: python -m scripts.export_openapi"""
import json
from pathlib import Path
from app.main import app

Path(__file__).resolve().parents[1].joinpath("openapi.snapshot.json").write_text(json.dumps(app.openapi(), sort_keys=True, indent=1) + "\n")
