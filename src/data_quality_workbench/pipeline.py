"""CSV ingestion, validation, SQLite modelling, and report generation."""

from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

REQUIRED_COLUMNS = ("order_id", "customer_id", "ordered_at", "region", "amount_eur", "status")
ALLOWED_STATUSES = {"complete", "pending", "refunded"}


@dataclass(frozen=True)
class RejectedRow:
    row_number: int
    order_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PipelineResult:
    source: str
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    duplicate_rows: int
    quality_score: float
    issue_counts: dict[str, int]
    database: str
    outputs: dict[str, str]


def _parse_amount(raw: str) -> Decimal:
    value = Decimal(raw.strip())
    if not value.is_finite() or value < 0:
        raise InvalidOperation
    return value.quantize(Decimal("0.01"))


def _read_and_validate(source: Path) -> tuple[list[dict[str, Any]], list[RejectedRow], Counter[str], int, int]:
    accepted: list[dict[str, Any]] = []
    rejected: list[RejectedRow] = []
    issues: Counter[str] = Counter()
    seen_ids: set[str] = set()
    duplicate_rows = 0

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = tuple(reader.fieldnames or ())
        missing = [column for column in REQUIRED_COLUMNS if column not in headers]
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")

        for row_number, raw in enumerate(reader, start=2):
            values = {key: (value or "").strip() for key, value in raw.items() if key is not None}
            reasons: list[str] = []
            order_id = values.get("order_id", "")
            customer_id = values.get("customer_id", "")
            region = values.get("region", "")
            status = values.get("status", "").lower()

            for key in ("order_id", "customer_id", "ordered_at", "region", "amount_eur", "status"):
                if not values.get(key):
                    reasons.append(f"missing_{key}")

            if order_id and order_id in seen_ids:
                duplicate_rows += 1
                reasons.append("duplicate_order_id")
            elif order_id:
                seen_ids.add(order_id)

            try:
                ordered_at = date.fromisoformat(values.get("ordered_at", ""))
            except ValueError:
                ordered_at = None
                if "missing_ordered_at" not in reasons:
                    reasons.append("invalid_ordered_at")

            try:
                amount = _parse_amount(values.get("amount_eur", ""))
            except (InvalidOperation, ValueError):
                amount = None
                if "missing_amount_eur" not in reasons:
                    reasons.append("invalid_amount_eur")

            if status and status not in ALLOWED_STATUSES:
                reasons.append("invalid_status")

            if reasons:
                issues.update(reasons)
                rejected.append(RejectedRow(row_number, order_id, tuple(reasons)))
                continue

            assert ordered_at is not None and amount is not None
            accepted.append({
                "order_id": order_id,
                "customer_id": customer_id,
                "ordered_at": ordered_at.isoformat(),
                "region": region,
                "amount_eur": str(amount),
                "status": status,
            })

    return accepted, rejected, issues, duplicate_rows, len(accepted) + len(rejected)


def _build_database(path: Path, rows: list[dict[str, Any]]) -> None:
    if path.exists():
        path.unlink()
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript("""
            CREATE TABLE dim_region (
                region_id INTEGER PRIMARY KEY,
                region_name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE fact_orders (
                order_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                ordered_at TEXT NOT NULL,
                region_id INTEGER NOT NULL REFERENCES dim_region(region_id),
                amount_eur TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('complete', 'pending', 'refunded'))
            );
            CREATE INDEX idx_fact_orders_ordered_at ON fact_orders(ordered_at);
            CREATE INDEX idx_fact_orders_region ON fact_orders(region_id);
        """)
        regions = sorted({row["region"] for row in rows})
        connection.executemany("INSERT INTO dim_region(region_name) VALUES (?)", ((name,) for name in regions))
        region_ids = dict(connection.execute("SELECT region_name, region_id FROM dim_region"))
        connection.executemany(
            "INSERT INTO fact_orders(order_id, customer_id, ordered_at, region_id, amount_eur, status) VALUES (?, ?, ?, ?, ?, ?)",
            ((row["order_id"], row["customer_id"], row["ordered_at"], region_ids[row["region"]], row["amount_eur"], row["status"]) for row in rows),
        )


def _write_csv(path: Path, headers: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def run_pipeline(source: Path, output_dir: Path) -> PipelineResult:
    source = source.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Input file does not exist: {source}")
    output_dir.mkdir(parents=True, exist_ok=True)

    accepted, rejected, issues, duplicate_rows, total_rows = _read_and_validate(source)
    database = output_dir / "warehouse.sqlite"
    _build_database(database, accepted)

    with sqlite3.connect(database) as connection:
        daily = [dict(zip(("ordered_at", "order_count", "gross_amount_eur", "completed_amount_eur"), row)) for row in connection.execute("""
            SELECT ordered_at, COUNT(*), ROUND(SUM(CAST(amount_eur AS REAL)), 2),
                   ROUND(SUM(CASE WHEN status='complete' THEN CAST(amount_eur AS REAL) ELSE 0 END), 2)
            FROM fact_orders GROUP BY ordered_at ORDER BY ordered_at
        """)]
        regional = [dict(zip(("region", "order_count", "gross_amount_eur", "completed_orders"), row)) for row in connection.execute("""
            SELECT d.region_name, COUNT(*), ROUND(SUM(CAST(f.amount_eur AS REAL)), 2),
                   SUM(CASE WHEN f.status='complete' THEN 1 ELSE 0 END)
            FROM fact_orders f JOIN dim_region d USING(region_id)
            GROUP BY d.region_name ORDER BY d.region_name
        """)]

    rejected_path = output_dir / "rejected_rows.csv"
    _write_csv(rejected_path, ("row_number", "order_id", "reasons"), [
        {"row_number": item.row_number, "order_id": item.order_id, "reasons": ";".join(item.reasons)}
        for item in rejected
    ])
    daily_path = output_dir / "daily_summary.csv"
    _write_csv(daily_path, ("ordered_at", "order_count", "gross_amount_eur", "completed_amount_eur"), daily)
    regional_path = output_dir / "regional_summary.csv"
    _write_csv(regional_path, ("region", "order_count", "gross_amount_eur", "completed_orders"), regional)

    quality_score = round((len(accepted) / total_rows) * 100, 1) if total_rows else 100.0
    result = PipelineResult(
        source=str(source), total_rows=total_rows, accepted_rows=len(accepted),
        rejected_rows=len(rejected), duplicate_rows=duplicate_rows,
        quality_score=quality_score, issue_counts=dict(sorted(issues.items())),
        database=str(database), outputs={
            "rejected_rows": str(rejected_path), "daily_summary": str(daily_path),
            "regional_summary": str(regional_path),
        },
    )
    report_path = output_dir / "quality_report.json"
    report_path.write_text(json.dumps(asdict(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result
