"""Create a small, auditable order-lifecycle pilot from the supplied DBN v1 file.

This is a representation/contrastive-learning pilot, NOT labeled manipulation data.
No original market data files are modified.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import struct
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'dhgnn_ebm_pilot'
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = ROOT / 'work' / 'viac23.dbn'
DT = np.dtype([
    ('length', 'u1'), ('rtype', 'u1'), ('publisher_id', '<u2'),
    ('instrument_id', '<u4'), ('ts_event', '<u8'), ('order_id', '<u8'),
    ('price', '<i8'), ('size', '<u4'), ('flags', 'u1'), ('channel_id', 'u1'),
    ('action', 'S1'), ('side', 'S1'), ('ts_recv', '<u8'),
    ('ts_in_delta', '<i4'), ('sequence', '<u4')])
FEATURES = ['side', 'price_vs_start_trade_pct', 'log_initial_size',
            'log_remaining_size', 'filled_fraction', 'cancelled_fraction',
            'replaced_fraction', 'observed_age_minutes', 'birth_within_minute',
            'closed_as_of_snapshot', 'log_cancel_count', 'log_fill_count']
NS = 1_000_000_000
START = int(datetime(2021, 3, 23, 13, 30, tzinfo=timezone.utc).timestamp()) * NS
END = int(datetime(2021, 3, 23, 20, 0, tzinfo=timezone.utc).timestamp()) * NS
NODES, STEPS = 24, 6


def main():
    with SOURCE.open('rb') as f:
        header = f.read(8)
    assert header[:4] == b'DBN\x01'
    offset = 8 + struct.unpack_from('<I', header, 4)[0]
    assert (SOURCE.stat().st_size - offset) % DT.itemsize == 0
    a = np.memmap(SOURCE, dtype=DT, mode='r', offset=offset)
    assert np.all(a['length'] == 14) and np.all(a['rtype'] == 160)
    assert np.all(a['ts_event'][1:] >= a['ts_event'][:-1])
    assert set(np.unique(a['action'])) <= {b'A', b'C', b'F', b'R', b'T'}
    action, seq, oid = a['action'], a['sequence'], a['order_id']
    same_previous = (seq[1:] == seq[:-1]) & (oid[1:] == oid[:-1])
    execution_cancel = np.zeros(len(a), bool)
    execution_cancel[1:] = ((action[1:] == b'C') & (action[:-1] == b'F') & same_previous)
    replacement_cancel = np.zeros(len(a), bool)
    replacement_cancel[:-1] = ((action[:-1] == b'C') & (action[1:] == b'A')
                               & (seq[:-1] == seq[1:]))
    assert execution_cancel.sum() == (action == b'F').sum()
    assert not np.any(execution_cancel & replacement_cancel)
    snapshots = (a['flags'] & 32) != 0
    regular = (a['ts_event'] >= START) & (a['ts_event'] < END) & ~snapshots
    assert not np.any(regular & (action == b'R'))
    ti = np.flatnonzero((action == b'T') & ~snapshots & (a['price'] < 2**62))
    trade_times, trade_px = a['ts_event'][ti], a['price'][ti] / 1e9
    x_list, masks, contexts, times, node_ids, window_stats = [], [], [], [], [], []
    prev_counts, prev_volumes, prev_returns = [], [], []
    audited_orders = 0
    for minute in range(390):
        start, end = START + minute * 60 * NS, START + (minute + 1) * 60 * NS
        i0, i1 = np.searchsorted(a['ts_event'], [start, end], side='left')
        prior = np.searchsorted(trade_times, start, side='left') - 1
        assert prior >= 0
        anchor_px = float(trade_px[prior])
        episodes = {}
        for i in range(int(i0), int(i1)):
            row = a[i]
            act, ident = bytes(row['action']), int(row['order_id'])
            t = (int(row['ts_event']) - int(start)) / NS
            if act == b'A' and not snapshots[i]:
                assert ident not in episodes
                price, size = int(row['price']) / 1e9, int(row['size'])
                if size <= 0 or abs(price / anchor_px - 1) > .01:
                    continue
                episodes[ident] = dict(side=1. if row['side'] == b'B' else -1.,
                    px=(price / anchor_px - 1) * 100, size=size, birth=t,
                    rem=size, fill=0, cancel=0, replace=0, nc=0, nf=0,
                    states=[(t, size, 0, 0, 0, 0, 0)])
            elif act == b'C' and ident in episodes:
                e, q = episodes[ident], int(row['size'])
                assert 0 <= q <= e['rem'], (minute, ident, q, e['rem'])
                e['rem'] -= q
                if execution_cancel[i]:
                    e['fill'] += q
                    e['nf'] += 1
                elif replacement_cancel[i]:
                    e['replace'] += q
                else:
                    e['cancel'] += q
                    e['nc'] += 1
                assert e['size'] == e['rem'] + e['fill'] + e['cancel'] + e['replace']
                e['states'].append((t, e['rem'], e['fill'], e['cancel'],
                                    e['replace'], e['nc'], e['nf']))
        audited_orders += len(episodes)
        ids = sorted(episodes)
        x = np.zeros((STEPS, NODES, len(FEATURES)), np.float32)
        mask = np.zeros((STEPS, NODES), bool)
        if len(ids) >= 8:
            rng = np.random.default_rng(731 + minute)
            chosen = rng.choice(ids, size=min(NODES, len(ids)), replace=False).tolist()
            chosen.sort(key=lambda k: episodes[k]['birth'])
            padded_ids = np.zeros(NODES, np.uint64)
            for j, ident in enumerate(chosen):
                e = episodes[ident]
                padded_ids[j] = ident
                state_times = np.array([s[0] for s in e['states']])
                for k, cutoff in enumerate(np.linspace(10, 60, STEPS)):
                    if e['birth'] >= cutoff:
                        continue
                    # Snapshot is left-open at cutoff; no record at/after cutoff is used.
                    ix = np.searchsorted(state_times, cutoff, side='left') - 1
                    st, rem, fill, cancel, replace, nc, nf = e['states'][ix]
                    closed = rem == 0
                    age = ((st if closed else cutoff) - e['birth']) / 60
                    x[k, j] = [e['side'], e['px'], np.log1p(e['size']),
                        np.log1p(rem), fill / e['size'], cancel / e['size'],
                        replace / e['size'], age, e['birth'] / 60,
                        float(closed), np.log1p(nc), np.log1p(nf)]
                    mask[k, j] = True
            prior_count = prev_counts[-1] if prev_counts else 0
            prior_volume = prev_volumes[-1] if prev_volumes else 0
            prior_return = prev_returns[-1] if prev_returns else 0
            prior_volatility = float(np.std(prev_returns[-5:])) if prev_returns else 0
            context = [np.sin(2*np.pi*minute/390), np.cos(2*np.pi*minute/390),
                       np.log1p(prior_count), np.log1p(prior_volume),
                       prior_return, prior_volatility]
            x_list.append(x); masks.append(mask); contexts.append(context)
            times.append(int(start)); node_ids.append(padded_ids)
            window_stats.append(dict(minute=minute, eligible_orders=len(ids),
                sampled_orders=len(chosen), raw_records=int(i1-i0), anchor_price=anchor_px))
        rows = a[i0:i1]
        trade_mask = rows['action'] == b'T'
        prev_counts.append(int(i1-i0))
        prev_volumes.append(int(rows['size'][trade_mask].astype(np.int64).sum()))
        last = np.searchsorted(trade_times, end, side='left') - 1
        prev_returns.append(float(np.log(trade_px[last]/anchor_px)*100))
    x, mask = np.stack(x_list), np.stack(masks)
    context, times, ids = np.asarray(contexts, np.float32), np.asarray(times), np.stack(node_ids)
    minute = ((times - START) // (60 * NS)).astype(int)
    # Fixed chronological split; four minutes are purged around boundaries.
    split = np.full(len(times), -1, int)
    split[minute < 233] = 0
    split[(minute >= 235) & (minute < 311)] = 1
    split[minute >= 313] = 2
    for left, right in [(0,1), (0,2), (1,2)]:
        l = set(ids[split == left].ravel()) - {0}
        r = set(ids[split == right].ravel()) - {0}
        assert not l.intersection(r)
    assert np.all(x[...,4:7].sum(axis=-1) <= 1.000001)
    assert np.isfinite(x).all() and np.isfinite(context).all()
    np.savez_compressed(OUT / 'pilot_samples.npz', x=x, mask=mask,
                        context=context, times=times, ids=ids, split=split)
    summary = dict(source=str(SOURCE), source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        ticker='VIAC', date='2021-03-23', dataset='XNAS.ITCH', schema='MBO / DBN v1',
        total_records=len(a), regular_session_records=int(regular.sum()),
        execution_cancels_excluded_from_voluntary_cancel=int(execution_cancel.sum()),
        replacement_cancels_separately_classified=int(replacement_cancel.sum()),
        synthetic_snapshot_records_excluded=int(snapshots.sum()),
        audited_new_order_lifecycles=audited_orders, windows=len(x),
        nodes_per_window=NODES, snapshots_per_window=STEPS, seconds_per_window=60,
        features=FEATURES, context_features=['time_sin','time_cos','lag_log_record_count',
            'lag_log_trade_volume','lag_return_pct','lag_5min_volatility_pct'],
        splits={name:int((split==k).sum()) for k,name in enumerate(['train','validation','test'])},
        purged_windows=int((split==-1).sum()), window_stats=window_stats,
        limitations=['Observed VIAC samples have no window-level manipulation labels.',
            'Background observations are not certified normal and may contain manipulation.',
            'No market-index series was supplied; only time and lagged VIAC context are used.',
            'One ticker, one regular session, one venue; no account identities.',
            'Only newly added near-price orders are sampled; carry-in and distant orders are omitted.',
            'Six snapshots per minute can miss sub-second behavior.',
            'Recorded windows are scored retrospectively at window end; no early-warning claim.'])
    (OUT / 'data_audit.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k != 'window_stats'}, indent=2), flush=True)


if __name__ == '__main__':
    main()
