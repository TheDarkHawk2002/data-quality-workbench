"""Command-line interface for the data quality workbench."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a CSV, load a small SQLite warehouse, and produce summaries.")
    parser.add_argument("--input", required=True, type=Path, help="Path to a CSV file matching the documented input contract")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for the database and generated reports")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        result = run_pipeline(arguments.input, arguments.output_dir)
    except (OSError, ValueError) as error:
        print(f"data-quality: {error}", file=sys.stderr)
        return 2
    print(json.dumps({
        "accepted_rows": result.accepted_rows,
        "rejected_rows": result.rejected_rows,
        "quality_score": result.quality_score,
        "report": str(Path(arguments.output_dir).resolve() / "quality_report.json"),
    }, indent=2))
    return 0
