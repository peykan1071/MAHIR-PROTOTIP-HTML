"""Command-line runner for the minimal MAHIR CED validation flow."""

from __future__ import annotations

import sys
from pathlib import Path

from app.validator import validate_ced_file


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    ced_path = project_root / "shared" / "ced-example.json"

    is_valid, message, errors = validate_ced_file(ced_path)
    print(message)

    if not is_valid:
        for error in errors:
            print(f"- {error}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
