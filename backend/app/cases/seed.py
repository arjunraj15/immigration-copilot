"""Command line entry: python -m app.cases.seed [--intake-only]. Prints what changed. Safe to run any number of times.
--intake-only loads the notes, messages, profiles and events and derives the cases, with no documents."""

import sys
from pathlib import Path

from app.cases.loader import KitMissingError, load_intake_files, load_starter_kit
from app.core.config import get_settings
from app.db.session import SessionLocal


def main() -> int:
    kit_dir = Path(get_settings().starter_kit_dir)
    with SessionLocal() as db:
        try:
            report = (load_intake_files if "--intake-only" in sys.argv[1:] else load_starter_kit)(db, kit_dir)
        except KitMissingError as error:
            print(error, file=sys.stderr)
            return 1
    for name, table in report.tables.items():
        counts = f"inserted {table.inserted:4} updated {table.updated:4} unchanged {table.unchanged:4}"
        print(f"{name:18} {counts} skipped {table.skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
