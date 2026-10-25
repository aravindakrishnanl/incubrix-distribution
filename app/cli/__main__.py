"""Entry point when running python -m app.cli"""

from __future__ import annotations

import sys
from app.cli.main import cli_entrypoint

if __name__ == "__main__":
    sys.exit(cli_entrypoint())
