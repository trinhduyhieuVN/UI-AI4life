# XNAS.ITCH preprocessing for DHGNN + EBM

Run from the workspace root with Python 3.14 and NumPy. The replay reads
compressed DBN v1 files directly from `D:/DATA_AI4LIFE`.

```powershell
python work/preprocess_mbo.py
python work/check_mbo_pipeline.py
```

The default run processes 10 November 2020 and 27 November 2020 for all
eight stocks. Specify `--days` or `--symbols` for a subset. Use
`--all --out outputs/mbo_full` for the 146 regular sessions in scope.
Output files are independent per symbol and session. To resume a partial
run, select the missing days and symbols. `--nodes` controls sampling,
with half of the slots allocated to each side of the book.

## Output

Each NPZ contains one row per completed minute. The replay processes all
MBO messages before each cutoff. It uses the midnight snapshot and
pre-market events to initialize and warm up the book. The final sample
excludes source events at the closing boundary itself.

| Array | Content |
| --- | --- |
| x, mask, order_id | 60 snapshots per minute with up to 32 active orders per second. Orders are selected by price priority and then insertion order at the level. IDs link orders across snapshots. |
| edge_group | Three hyperedge families rebuilt every second: side, price-rank band, observed age band. Negative IDs mark padding. The existing dynamic layer adds embedding-based neighborhoods. |
| flow, flow_minute | Ten full-feed count and quantity features at second and minute resolution. Replacements are counted once and tracked separately from voluntary cancellations. |
| book, book_valid | Mid and spread from the reconstructed book, depth at the best five levels per side and depth imbalance. Invalid mid and spread are NaN. |
| market | SPY and QQQ close and volume for the minute that has just completed, in that ETF order. This context becomes available at the minute cutoff. |
| cutoff_ns | UTC nanosecond timestamp at the end of each minute. |

The replay applies the normalized cancel following a fill as a book
reduction once. Trade volume uses Trade records. For orders inherited from
synthetic snapshots, age and original size are missing and birth_known is
false. The order features represent the active book, so orders entering and
leaving between snapshots appear in flow aggregates but may have no node.

Each session JSON records event coverage, reconstruction counters, valid book
seconds, runtime and file size. The pilot checker validates the tensor
contract and runs a forward/backward pass on random model weights. It does
not produce a trained checkpoint. Fit normalization on train dates only.
Load one session shard at a time when training.

| Dates | Role |
| --- | --- |
| October 2020 | Reference history |
| 2020-11-02–2021-01-29 | Train |
| 2021-02-01–2021-02-12 | Model selection |
| 2021-02-16–2021-02-26 | Alert calibration |
| March 2021 | Time-based evaluation, with VIAC 23 March reserved for retrospective illustration |
| April 2021 | Additional evaluation |
