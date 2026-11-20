# MBO anomaly baselines — VIAC engineering pilot

Two runnable baselines for **unlabeled anomaly triage**, not a manipulation classifier:

1. Group-balanced robust deviation score (activity, order structure, price).
2. Scikit-learn Isolation Forest, 300 trees, max_samples=128, seed=42.

## Run (PowerShell, repository root)

```powershell
python baseline/baseline.py
python baseline/test_baseline.py
python baseline/baseline.py --score-csv outputs/anomaly_baseline/features.csv --model outputs/anomaly_baseline/model.joblib --out outputs/anomaly_baseline/rescore
```

Install dependencies if needed: `python -m pip install -r baseline/requirements.txt`.
Only load trusted joblib models; joblib is executable Python serialization.

Defaults read `work/viac23.dbn`, an existing uncompressed DBN-v1 file. The original
user data is not edited. `--source` and `--out` override paths. **The extraction
adapter and session boundaries are intentionally restricted to the audited
VIAC/XNAS 2021-03-23 source. Do not point it at arbitrary dates or DBN versions.**
For other sessions, implement metadata-driven calendar/symbol handling and a
validated DBN adapter before using this extractor.

## Data and causal processing

- All 1,010,478 regular-session records are processed; no 24-order subsampling.
- 390 non-overlapping, completed one-minute windows, [09:30,16:00) New York.
- A score is available only after its window ends; it is not an early prediction.
- Snapshot events initialize observed lifecycle state but do not count as adds.
- In this inspected normalization, a fill `F` followed by a same-order `C` at the
  same sequence/timestamp is an execution reduction, not a voluntary cancel.
- A `C` followed by `A` at the same sequence/timestamp is counted separately as
  replacement. The same-timestamp constraint keeps classification within the
  completed window. Buffer the complete source event in a future live adapter.
- `T` records define trade statistics; `F` is not added again to trade volume.
- Ages are measured only for orders whose birth was observed. Snapshot age is
  unknown. `age_coverage` reports coverage and missing features are explicit.
- No spread/depth reconstruction, market index, participant identity, or
  same-time-of-day seasonal reference is implemented in this version.
- The lifecycle tracker checks cancel quantities but is not a full order book.
- `quality_ok=0` suppresses alerts for empty, reset, unmatched/over-cancel or bad
  trade-price windows; it is not proof that every possible feed defect is absent.

## Features (17)

Activity: log1p of add/cancel/replacement/trade counts; add/cancel/trade quantity;
cancel/add count ratio. Order structure: buy fractions of adds/cancels, log1p
median/p90 add size, log1p median known cancellation age in milliseconds, fraction
of known cancellation ages below 100ms. Price: last-to-prior-window trade log
return in basis points, square root of summed squared trade log returns in bps,
and log(max/min traded price) in bps. `return_bps` uses the prior observed trade,
not the first trade of the current minute. An absent traded path is missing,
not invented zero activity.

## Fitting and calibration

Chronological engineering split (not an independent-day test):

- Train: 09:30–13:23, 233 windows.
- Calibration: 13:25–14:41, 76 windows.
- Evaluation: 14:43–16:00, 77 windows.
- Four boundary windows excluded. Boundaries are end-exclusive.

Missing feature imputation and median/scales fit train only. Scale is 1.4826 MAD;
fallback IQR/1.349, then training standard deviation. Minimum scales are 0.1 for
log features, 1 basis point for price features and 0.02 otherwise. These fixed
floors prevent quantized/constant order sizes from exploding the score.

Robust score: RMS of absolute standardized features within each group, then mean
of the two largest group scores. Forest score: negative `score_samples` (larger
means more unusual). Calibration reference percentiles are NOT probabilities.
Each threshold is the higher-interpolated 95th percentile of calibration scores;
strictly greater values trigger alerts, subject to quality checks. This does not
guarantee a 5% future alert rate. No hyperparameters are optimized against labels.

Adjacent evaluation alerts are merged separately for each model. Evidence lists
the three largest absolute robust deviations. These are descriptive diagnostics,
**not feature attribution for Isolation Forest and not causal explanations**.

## Outputs

`outputs/anomaly_baseline/` contains:

- `report.html` and `baseline_results.png`: visual report.
- `features.csv`: computed features and quality metadata.
- `scores.csv`: both scores, thresholds via summary, calibration percentiles,
  alert flags, descriptive evidence, and split identifiers.
- `events.json`: merged evaluation alerts with start/end and peak score.
- `model.joblib`: trained scaler, forest, calibration references and thresholds.
- `summary.json`: source hash, versions, audit, split, normalization and results.

Training-period/calibration flags are diagnostics only; the report summarizes
evaluation alerts. The score-CSV command loads the frozen bundle and does not fit
or calibrate again. A future API connector should deliver identically defined
completed-window features to this inference function, not raw ticks directly.

## Verification and interpretation

Tests check execution-vs-cancel accounting, replacement separation, snapshot
age/activity exclusion, frozen robust scaling, and actual-data causal-prefix
equality. The runner checks batch-vs-one-window scoring equivalence. Audit checks
do not validate an entire exchange feed implementation.

No labeled anomalies are available. **Do not report accuracy, recall, AUC, or
false-positive rate from these observations.** Close-of-day alerts can reflect
normal intraday seasonality and the shift from morning training to afternoon
evaluation. This session has already been inspected in prior research, so it is
not a pristine holdout. Next validation requires multiple complete sessions,
chronological date splits, seasonal context, and blinded review of alerts and
random non-alert windows. Models trained on 2021 data are not deployment-ready
for today's market.
