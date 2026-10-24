"""Export the live OpenAPI spec to openapi.yaml.

Usage: python scripts/export_openapi.py
Requires the app to be importable (dependencies installed).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from app.main import app


def main():
    schema = app.openapi()
    out_path = Path(__file__).parent.parent / "openapi.yaml"
    with out_path.open("w", encoding="utf-8") as f:
        yaml.dump(schema, f, allow_unicode=True, sort_keys=False)
    print(f"OpenAPI spec written to {out_path}")


if __name__ == "__main__":
    main()
