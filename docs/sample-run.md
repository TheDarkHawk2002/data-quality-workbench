# Sample run

The bundled sample has 25 synthetic order rows covering four regions and three order states. Run:

```powershell
data-quality --input data/sample_orders.csv --output-dir output
```

The expected report summary is:

- Input rows: 25
- Accepted rows: 25
- Rejected rows: 0
- Quality score: 100.0%

The generated CSV summaries show daily order totals and regional order/revenue totals. Try copying the sample and introducing an invalid date, duplicate `order_id`, blank region, or unknown status to see how the rejected-row report explains each failure.
