"""Prepare causal per-session tensors from local Databento XNAS.ITCH DBN v1."""
import argparse
from collections import Counter
from compression import zstd
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import struct
import time

import numpy as np

NS = 10**9
MBO = struct.Struct('<BBHIQQqIBBccQiI')
BAR = struct.Struct('<BBHIQqqqqQ')
SYMBOLS = {'VIAC', 'DISCA', 'CMCSA', 'FOXA', 'AAPL', 'MSFT', 'INTC', 'CSCO'}
SHORT = {date(2020, 11, 27), date(2020, 12, 24)}
HOLIDAYS = {'2020-11-26', '2020-12-25', '2021-01-01', '2021-01-18',
            '2021-02-15', '2021-04-02'}
NODE = ['side', 'distance_from_mid_bps', 'remaining_shares', 'observed_age_seconds',
        'birth_known', 'initial_shares', 'executed_shares', 'cancelled_shares']
FLOW = ['add_count', 'add_qty', 'cancel_count', 'cancel_qty', 'replace_count',
        'replace_removed_qty', 'fill_count', 'fill_qty', 'trade_count', 'trade_qty']
BOOK = ['mid_usd', 'spread_bps', 'bid_depth_5', 'ask_depth_5', 'depth_imbalance_5']


def dbn_records(path, layout, rtype):
    with zstd.open(path, 'rb') as source:
        head = source.read(8)
        if head[:4] != b'DBN\x01':
            raise ValueError(f'Expected DBN v1: {path}')
        header_size = int.from_bytes(head[4:], 'little')
        if len(source.read(header_size)) != header_size:
            raise ValueError(f'Truncated DBN header: {path}')
        remainder = b''
        while block := source.read(4 * 1024 * 1024):
            block = remainder + block
            end = len(block) // layout.size * layout.size
            for row in layout.iter_unpack(memoryview(block)[:end]):
                if row[:2] != (layout.size // 4, rtype):
                    raise ValueError(f'Unexpected DBN record: {path}')
                yield row
            remainder = block[end:]
        if remainder:
            raise ValueError(f'Truncated DBN record: {path}')


def session_bounds(day):
    # Historical New York offsets for the supported October 2020–April 2021 interval.
    offset = 4 if day < date(2020, 11, 1) or day >= date(2021, 3, 14) else 5
    midnight = datetime.combine(day, datetime.min.time(), timezone.utc)
    start = int((midnight + timedelta(hours=9 + offset, minutes=30)).timestamp())
    minutes = 210 if day in SHORT else 390
    return start * NS, minutes


class OrderBook:
    def __init__(self, audit):
        self.audit = audit
        self.clear()

    def clear(self):
        self.orders = {}
        self.levels = {b'B': {}, b'A': {}}

    def add(self, oid, price, qty, side, birth):
        if side not in self.levels or qty <= 0 or price <= 0 or price >= 2**62:
            self.audit['invalid_add'] += 1
            return
        if oid in self.orders:
            self.audit['duplicate_add'] += 1
            self.remove(oid, self.orders[oid][0], None)
        self.orders[oid] = [qty, side, price, birth, qty if birth is not None else None, 0, 0]
        self.levels[side].setdefault(price, {})[oid] = None

    def remove(self, oid, qty, kind):
        order = self.orders.get(oid)
        if order is None:
            self.audit['unmatched_reduction'] += 1
            return
        if qty > order[0]:
            self.audit['over_reduction'] += 1
        applied = min(qty, order[0])
        order[0] -= applied
        if kind in (5, 6):
            order[kind] += applied
        if order[0] == 0:
            bucket = self.levels[order[1]][order[2]]
            del bucket[oid]
            if not bucket:
                del self.levels[order[1]][order[2]]
            del self.orders[oid]

    def snapshot(self, t, x, ids, groups):
        bids = sorted(self.levels[b'B'], reverse=True)
        asks = sorted(self.levels[b'A'])
        valid = bool(bids and asks and bids[0] < asks[0])
        mid = (bids[0] + asks[0]) / 2 if valid else np.nan
        depths = []
        for half, (side, prices) in enumerate(((b'B', bids), (b'A', asks))):
            levels = self.levels[side]
            depths.append(sum(self.orders[oid][0] for p in prices[:5] for oid in levels[p]))
            slot = half * (len(x) // 2)
            stop = slot + len(x) // 2
            for rank, price in enumerate(prices):
                for oid in levels[price]:
                    qty, _, _, birth, initial, filled, cancelled = self.orders[oid]
                    age = (t - birth) / NS if birth is not None else np.nan
                    x[slot] = [1 if half == 0 else -1, (price / mid - 1) * 1e4,
                               qty, age, birth is not None, initial if initial is not None else np.nan,
                               filled, cancelled]
                    ids[slot] = oid
                    # Each column defines one hyperedge family. IDs are local to this second.
                    groups[slot] = [half, half * 3 + min(rank // 2, 2),
                                    half * 5 + (4 if birth is None else
                                                0 if age < 1 else 1 if age < 5 else 2 if age < 30 else 3)]
                    slot += 1
                    if slot == stop:
                        break
                if slot == stop:
                    break
        bid, ask = depths
        spread = (asks[0] - bids[0]) / mid * 1e4 if valid else np.nan
        return [mid / NS, spread, bid, ask, (bid - ask) / (bid + ask) if bid + ask else np.nan], valid


def read_context(path):
    return {r[4]: (r[8] / NS, r[9]) for r in dbn_records(path, BAR, 33)}


def preprocess(path, symbol, day, context, nodes, output):
    started = time.perf_counter()
    start, minutes = session_bounds(day)
    seconds = minutes * 60
    end = start + seconds * NS
    x = np.full((seconds, nodes, len(NODE)), np.nan, np.float32)
    ids = np.zeros((seconds, nodes), np.uint64)
    groups = np.full((seconds, nodes, 3), -1, np.int8)
    flow = np.zeros((seconds, len(FLOW)), np.int64)
    book_values = np.full((seconds, len(BOOK)), np.nan, np.float32)
    valid = np.zeros(seconds, bool)
    audit = Counter()
    book = OrderBook(audit)
    step = 0
    previous = None
    last_timestamp = -1
    first_event = None
    last_event = None
    raw_trade_qty = 0
    records = iter(dbn_records(path, MBO, 160))
    current = next(records, None)
    while current is not None:
        following = next(records, None)
        _, _, _, _, event, oid, price, qty, flags, channel, action, side, recv, _, seq = current
        synthetic = bool(flags & 32)
        stamp = recv if synthetic else event
        if stamp < last_timestamp:
            audit['timestamp_regressions'] += 1
            stamp = last_timestamp
        last_timestamp = stamp
        while step < seconds and start + (step + 1) * NS <= stamp:
            cutoff = start + (step + 1) * NS
            book_values[step], valid[step] = book.snapshot(cutoff, x[step], ids[step], groups[step])
            step += 1
        if stamp >= end:
            break
        in_session = stamp >= start and not synthetic
        if in_session:
            first_event = stamp if first_event is None else first_event
            last_event = stamp
            audit['regular_records'] += 1
        def match(other, expected_action, same_order=False):
            return (other is not None and other[10] == expected_action and
                    (other[4], other[9], other[14]) == (event, channel, seq) and
                    (not same_order or other[5] == oid))
        offset = None
        if action == b'R':
            book.clear()
            audit['snapshot_resets' if synthetic else 'source_resets'] += 1
        elif action == b'A':
            replaced = match(previous, b'C')
            book.add(oid, price, qty, side, None if synthetic else stamp)
            if not replaced and not synthetic:
                offset = 0
        elif action == b'C':
            if match(previous, b'F', True):
                book.remove(oid, qty, 5)
                offset = 6
            elif match(following, b'A'):
                book.remove(oid, qty, None)
                offset = 4
            else:
                book.remove(oid, qty, 6)
                offset = 2
        elif action == b'T' and 0 < price < 2**62:
            offset = 8
            if in_session:
                raw_trade_qty += qty
        elif action != b'F':
            audit['unexpected_action_or_price'] += 1
        if in_session and offset is not None:
            flow[step, offset] += 1
            flow[step, offset + 1] += qty
        previous, current = current, following
    while step < seconds:
        cutoff = start + (step + 1) * NS
        book_values[step], valid[step] = book.snapshot(cutoff, x[step], ids[step], groups[step])
        step += 1
    if first_event is None:
        raise ValueError(f'No regular-session records: {path}')
    assert int(flow[:, 9].sum()) == raw_trade_qty
    # A DBN bar is keyed by its start. The last completed bar starts 60 seconds before cutoff.
    market = np.full((minutes, 2, 2), np.nan, np.float64)
    for minute in range(minutes):
        bar_start = start + minute * 60 * NS
        for column, etf in enumerate(('SPY', 'QQQ')):
            if bar_start in context[etf]:
                market[minute, column] = context[etf][bar_start]
    output.mkdir(parents=True, exist_ok=True)
    dest = output / f'{day}_{symbol}.npz'
    temporary = dest.with_suffix('.tmp')
    with temporary.open('wb') as stream:
        np.savez_compressed(stream, x=x.reshape(minutes, 60, nodes, len(NODE)),
                            order_id=ids.reshape(minutes, 60, nodes),
                            mask=(ids != 0).reshape(minutes, 60, nodes),
                            edge_group=groups.reshape(minutes, 60, nodes, 3),
                            flow=flow.reshape(minutes, 60, len(FLOW)),
                            flow_minute=flow.reshape(minutes, 60, len(FLOW)).sum(axis=1),
                            book=book_values.reshape(minutes, 60, len(BOOK)),
                            book_valid=valid.reshape(minutes, 60), market=market,
                            cutoff_ns=start + np.arange(1, minutes + 1, dtype=np.int64) * 60 * NS,
                            node_columns=NODE, flow_columns=FLOW, book_columns=BOOK)
    temporary.replace(dest)
    report = dict(symbol=symbol, day=str(day), minutes=minutes, audit=dict(audit),
                  trade_qty=raw_trade_qty, valid_book_seconds=int(valid.sum()),
                  first_event_utc=datetime.fromtimestamp(first_event / NS, timezone.utc).isoformat(),
                  last_event_utc=datetime.fromtimestamp(last_event / NS, timezone.utc).isoformat(),
                  market_missing=int(np.isnan(market[:, :, 0]).sum()),
                  bytes=dest.stat().st_size, seconds=round(time.perf_counter() - started, 2))
    dest.with_suffix('.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('D:/DATA_AI4LIFE'))
    parser.add_argument('--out', type=Path, default=Path('outputs/mbo_preprocessing'))
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--days', nargs='+', type=date.fromisoformat)
    selection.add_argument('--all', action='store_true')
    parser.add_argument('--symbols', nargs='+', choices=sorted(SYMBOLS), default=sorted(SYMBOLS))
    parser.add_argument('--nodes', type=int, default=32)
    args = parser.parse_args()
    if args.nodes < 2 or args.nodes % 2:
        parser.error('--nodes must be a positive even number')
    jobs = {}
    for path in args.data.glob('*/metadata.json'):
        query = json.loads(path.read_text(encoding='utf-8-sig'))['query']
        if query['dataset'] == 'XNAS.ITCH' and len(query['symbols']) == 1:
            key = query['schema'], query['symbols'][0]
            if key in jobs:
                raise ValueError(f'Duplicate job for {key}')
            jobs[key] = path.parent
    context = {}
    for etf in ('SPY', 'QQQ'):
        paths = sorted(jobs['ohlcv-1m', etf].glob('*.ohlcv-1m.dbn.zst'))
        if len(paths) != 1:
            raise ValueError(f'Expected one OHLCV file for {etf}')
        context[etf] = read_context(paths[0])
    first, last = date(2020, 10, 1), date(2021, 4, 30)
    days = args.days or [date(2020, 11, 10), date(2020, 11, 27)]
    if args.all:
        days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
        days = [d for d in days if d.weekday() < 5 and str(d) not in HOLIDAYS]
    for day in days:
        if not first <= day <= last or day.weekday() >= 5 or str(day) in HOLIDAYS:
            parser.error(f'Outside audited trading sessions: {day}')
        for symbol in args.symbols:
            path = jobs['mbo', symbol] / f'xnas-itch-{day:%Y%m%d}.mbo.dbn.zst'
            preprocess(path, symbol, day, context, args.nodes, args.out)


if __name__ == '__main__':
    main()
