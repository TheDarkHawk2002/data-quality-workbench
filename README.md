# Data Quality Workbench

A compact, reproducible pipeline that turns a CSV export into a validated SQLite warehouse and understandable analytics outputs. The workflow is deterministic, keeps rejected records visible, and uses only Python's standard library.

The sample order dataset is synthetic. No company, customer, or personal records are included.

## Capabilities

- Checks required columns, missing values, duplicate order IDs, ISO dates, non-negative monetary values, and allowed order states.
- Separates accepted rows from rejected records and records row-level reasons.
- Loads clean records into a small dimensional model: `dim_region` and `fact_orders`.
- Produces daily and regional summaries plus a machine-readable quality report.
- Uses SQLite constraints and indexes for a repeatable local analytical store.

## Run

Requires Python 3.11 or newer. There are no runtime dependencies.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
data-quality --input data/sample_orders.csv --output-dir output
```

You can also run it without installing the console command:

```powershell
$env:PYTHONPATH = "src"
python -m data_quality_workbench --input data/sample_orders.csv --output-dir output
```

The output directory contains `warehouse.sqlite`, `quality_report.json`, `rejected_rows.csv`, `daily_summary.csv`, and `regional_summary.csv`.

## Input contract

CSV columns: `order_id`, `customer_id`, `ordered_at`, `region`, `amount_eur`, `status`. Dates use `YYYY-MM-DD`; amounts are non-negative decimal values; status must be `complete`, `pending`, or `refunded`. Extra columns are ignored. A file missing a required column is rejected before loading.

## Data flow

```text
CSV export -> schema and row validation -> accepted/rejected split
          -> SQLite dimensional model -> daily/regional summaries + quality report
```

See [the architecture and data contract](docs/architecture.md) and [the sample run](docs/sample-run.md) for implementation detail and interpretation.

## Interpretation and limits

The quality score is the percentage of rows accepted by these explicit rules. It is not a business-quality rating or a guarantee that valid rows are correct. Aggregate revenue includes all accepted statuses; the separate completed amount and order count make the business definition visible. This example is designed for local, small-file workflows and does not include orchestration, access control, a cloud warehouse, or production monitoring.

## License

MIT; see [LICENSE](LICENSE).
