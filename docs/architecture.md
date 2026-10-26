# Architecture and data contract

## Components

1. The CSV reader checks the header before processing records.
2. The validator accumulates row-level reasons, rather than silently dropping bad data.
3. Accepted records are loaded into SQLite. `dim_region` stores distinct regions and `fact_orders` stores the transactional records with a foreign key.
4. SQL queries produce daily and regional summaries. CSV reports are convenient for spreadsheet review; JSON is suitable for a later integration.

## Rules

| Field or rule | Requirement | Failure handling |
|---|---|---|
| `order_id` | Non-empty and unique | Reject row; report duplicate IDs |
| `customer_id` | Non-empty | Reject row |
| `ordered_at` | Valid ISO date | Reject row |
| `region` | Non-empty | Reject row |
| `amount_eur` | Finite decimal, zero or greater | Reject row |
| `status` | `complete`, `pending`, or `refunded` | Reject row |

The quality score is `accepted rows / input rows * 100`. An empty input receives 100.0 because it contains no rule violations; the report still shows zero total rows so this cannot be mistaken for useful coverage.

## Reproducibility

No external APIs or random values are used. Given the same input, the same accepted/rejected records, table contents, and sorted summaries are produced. Generated artifacts belong in a caller-selected output directory and are excluded from version control.
