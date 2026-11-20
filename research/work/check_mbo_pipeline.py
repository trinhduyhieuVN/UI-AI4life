"""Validate pilot outputs and run a forward/backward pass through DHGNN + EBM."""
import argparse
from collections import Counter
from datetime import date
from pathlib import Path
import json

import numpy as np
from preprocess_mbo import SYMBOLS, NS, session_bounds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('outputs/mbo_preprocessing'))
    args = parser.parse_args()
    reports = []
    sample = None
    for path in sorted(args.out.glob('*.npz')):
        report = json.loads(path.with_suffix('.json').read_text())
        with np.load(path) as data:
            x, mask, groups = (data[k] for k in ('x', 'mask', 'edge_group'))
            minutes = report['minutes']
            assert x.shape[:2] == (minutes, 60)
            assert np.array_equal(mask, data['order_id'] != 0)
            assert np.all(groups[~mask] == -1) and np.all(groups[mask] >= 0)
            assert np.all(x[..., 2][mask] > 0)
            assert np.all(x[..., 3][mask & (x[..., 4] == 1)] >= 0)
            assert np.isfinite(data['market']).all()
            start, expected_minutes = session_bounds(date.fromisoformat(report['day']))
            assert minutes == expected_minutes
            assert np.array_equal(data['cutoff_ns'], start + np.arange(1, minutes + 1) * 60 * NS)
            assert np.array_equal(data['flow'].sum(axis=1), data['flow_minute'])
            assert data['flow_minute'][:, 9].sum() == report['trade_qty']
            assert np.all(data['book'][..., 1][data['book_valid']] > 0)
            if sample is None:
                sample = tuple(np.copy(data[k][:2]) for k in
                               ('x', 'mask', 'edge_group', 'flow_minute', 'market'))
        reports.append(report)
    assert {(r['day'], r['symbol']) for r in reports} == {
        (day, symbol) for day in ('2020-11-10', '2020-11-27') for symbol in SYMBOLS
    }, 'Expected all sixteen pilot sessions'
    anomalies = Counter()
    for report in reports:
        anomalies.update({key: value for key, value in report['audit'].items()
                          if key not in ('snapshot_resets', 'source_resets', 'regular_records')})

    from train_mbo_pilot import EnergyModel, torch

    x, mask, groups, flow, market = sample
    # Smoke test only. For training, fit feature transforms on training sessions.
    x = np.nan_to_num(x)
    x[..., [2, 3, 5, 6, 7]] = np.log1p(x[..., [2, 3, 5, 6, 7]])
    incidence = np.concatenate(
        [groups[..., i, None] == np.arange(width) for i, width in enumerate((2, 6, 10))],
        axis=-1).astype(np.float32)
    context = np.concatenate([np.log1p(flow), np.log1p(market).reshape(len(x), -1)], axis=1)
    context = context.astype(np.float32)
    torch.manual_seed(42)
    model = EnergyModel('DynamicHG_EBM', np.zeros(x.shape[-1]), np.ones(x.shape[-1]),
                        np.zeros(context.shape[-1]), np.ones(context.shape[-1]))
    energy = model(torch.from_numpy(x), torch.from_numpy(mask),
                   torch.from_numpy(context), torch.from_numpy(incidence))
    assert energy.shape == (2,) and torch.isfinite(energy).all()
    energy.square().mean().backward()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())
    result = dict(sessions=len(reports), minutes=sum(r['minutes'] for r in reports),
                  records=sum(r['audit']['regular_records'] for r in reports),
                  bytes=sum(r['bytes'] for r in reports), processing_seconds=sum(r['seconds'] for r in reports),
                  reconstruction_audit=dict(anomalies),
                  invalid_book_seconds=sum(r['minutes'] * 60 - r['valid_book_seconds'] for r in reports),
                  energy_smoke_test=energy.detach().tolist(), sessions_detail=reports)
    (args.out / 'pilot_audit.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'sessions_detail'}))


if __name__ == '__main__':
    main()
