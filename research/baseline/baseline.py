"""Auditable, unlabeled VIAC MBO anomaly baseline. See README.md for scope."""
from __future__ import annotations
import argparse
import csv
import hashlib
import html
import json
import platform
import struct
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest

ROOT = Path(__file__).resolve().parents[1]
NS = 1_000_000_000
START = int(datetime(2021, 3, 23, 13, 30, tzinfo=timezone.utc).timestamp()) * NS
END = START + 390 * 60 * NS
DT = np.dtype([
    ('length', 'u1'), ('rtype', 'u1'), ('publisher_id', '<u2'),
    ('instrument_id', '<u4'), ('ts_event', '<u8'), ('order_id', '<u8'),
    ('price', '<i8'), ('size', '<u4'), ('flags', 'u1'), ('channel_id', 'u1'),
    ('action', 'S1'), ('side', 'S1'), ('ts_recv', '<u8'),
    ('ts_in_delta', '<i4'), ('sequence', '<u4')])
# Group balancing prevents a group with more columns dominating the robust score.
GROUPS = {
    'activity': ['log_add_count', 'log_cancel_count', 'log_replace_count', 'log_trade_count',
                 'log_add_qty', 'log_cancel_qty', 'log_trade_qty', 'cancel_add_ratio'],
    'order_structure': ['add_buy_fraction', 'cancel_buy_fraction',
                        'log_add_size_median', 'log_add_size_p90', 'log_cancel_age_median_ms',
                        'short_cancel_fraction'],
    'price': ['return_bps', 'trade_volatility_bps', 'trade_range_bps'],
}
FEATURES = sum(GROUPS.values(), [])


def iso(ns):
    return datetime.fromtimestamp(int(ns)/NS, timezone.utc).isoformat()


def ny_label(ns):
    # This narrowly scoped dataset is on 2021-03-23, when New York is UTC-4.
    return datetime.fromtimestamp(int(ns)/NS, timezone(timedelta(hours=-4))).strftime('%H:%M')


def load_dbn(path):
    with Path(path).open('rb') as stream:
        header = stream.read(8)
    if header[:4] != b'DBN\x01':
        raise ValueError('This audited adapter accepts uncompressed DBN v1 only.')
    offset = 8 + struct.unpack_from('<I', header, 4)[0]
    if (Path(path).stat().st_size-offset) % DT.itemsize:
        raise ValueError('Unexpected record size.')
    data = np.memmap(path, dtype=DT, mode='r', offset=offset)
    if not (np.all(data['length'] == 14) and np.all(data['rtype'] == 160)):
        raise ValueError('Mixed/unsupported record types; do not silently reinterpret.')
    if len(np.unique(data['instrument_id'])) != 1:
        raise ValueError('Adapter requires one instrument per file.')
    if np.any(data['ts_event'][1:] < data['ts_event'][:-1]):
        raise ValueError('Out-of-order event timestamps.')
    if not set(np.unique(data['action'])) <= {b'A', b'C', b'F', b'R', b'T'}:
        raise ValueError('Unsupported action in this source-specific adapter.')
    return data


def classifications(data):
    """Only inspected XNAS DBN-v1 normalization, not a generic MBO rule."""
    execution = np.zeros(len(data), bool)
    replacement = np.zeros(len(data), bool)
    same = ((data['sequence'][1:] == data['sequence'][:-1]) &
            (data['ts_event'][1:] == data['ts_event'][:-1]))
    execution[1:] = (same & (data['order_id'][1:] == data['order_id'][:-1]) &
                     (data['action'][:-1] == b'F') & (data['action'][1:] == b'C'))
    replacement[:-1] = same & (data['action'][:-1] == b'C') & (data['action'][1:] == b'A')
    if np.any(execution & replacement):
        raise ValueError('Ambiguous cancel classification.')
    return execution, replacement


def extract(data, start=START, end=END):
    """Completed half-open minutes. No future-window values enter a feature.

    Lifecycle state is only used for observed cancellation age; this is NOT a
    full depth-of-book reconstruction. Snapshot births remain unknown.
    """
    execution, replacement = classifications(data)
    snapshot = (data['flags'] & 32) != 0
    orders = {}
    last_trade = None
    audit = Counter()
    cursor = 0
    rows = []
    for left in range(start, end, 60*NS):
        right = left + 60*NS
        counts = Counter()
        sizes, ages, prices = [], [], []
        anchor = last_trade
        while cursor < len(data) and int(data[cursor]['ts_event']) < right:
            r = data[cursor]
            t, oid, qty = int(r['ts_event']), int(r['order_id']), int(r['size'])
            act, side = bytes(r['action']), bytes(r['side'])
            is_snap = bool(snapshot[cursor])
            inside = t >= left and not is_snap
            if t < left:
                audit['warmup_records'] += 1
            if is_snap:
                audit['snapshot_records'] += 1
            if act == b'R':
                orders.clear()
                if inside:
                    counts['reset_count'] += 1
            elif act == b'A':
                if oid in orders:
                    audit['duplicate_active_add'] += 1
                orders[oid] = [qty, None if is_snap else t, side]
                if inside:
                    counts['add_count'] += 1
                    counts['add_qty'] += qty
                    counts['add_buy_count'] += side == b'B'
                    sizes.append(qty)
            elif act == b'C':
                category = 'execution' if execution[cursor] else ('replace' if replacement[cursor] else 'cancel')
                old = orders.get(oid)
                if inside:
                    counts[category+'_count'] += 1
                    counts[category+'_qty'] += qty
                    if category == 'cancel':
                        counts['cancel_buy_count'] += side == b'B'
                        if old is not None and old[1] is not None:
                            ages.append((t-old[1])/1e6)
                if old is None:
                    if inside:
                        counts['unmatched_cancel_count'] += 1
                else:
                    if qty > old[0]:
                        if inside:
                            counts['over_cancel_count'] += 1
                    old[0] -= qty
                    if old[0] <= 0:
                        del orders[oid]
            elif act == b'T' and not is_snap:
                px = int(r['price'])/1e9
                if 0 < px < 1e6:
                    if inside:
                        if anchor is None:
                            anchor = last_trade
                        counts['trade_count'] += 1
                        counts['trade_qty'] += qty
                        prices.append(px)
                    last_trade = px
                    if t < left:
                        anchor = px
                elif inside:
                    counts['bad_trade_price'] += 1
            if inside:
                counts['raw_records'] += 1
            cursor += 1
        ret = (np.log(prices[-1]/anchor)*1e4 if prices and anchor else np.nan)
        path = ([anchor] if anchor else []) + prices
        rv = float(np.sqrt(np.sum(np.diff(np.log(path))**2))*1e4) if len(path)>1 else np.nan
        span = float(np.log(max(prices)/min(prices))*1e4) if prices else np.nan
        row = dict(window_start_utc=iso(left), window_end_utc=iso(right),
                   minute=(left-start)//(60*NS), time_ny=ny_label(left),
                   last_trade_price=last_trade if last_trade else np.nan,
                   raw_records=counts['raw_records'],
                   age_coverage=len(ages)/counts['cancel_count'] if counts['cancel_count'] else 0,
                   quality_ok=int(counts['raw_records']>0 and not any(counts[k] for k in
                       ['reset_count','over_cancel_count','unmatched_cancel_count','bad_trade_price'])))
        row.update({f'log_{key}': float(np.log1p(counts[key])) for key in
                    ['add_count','cancel_count','replace_count','trade_count','add_qty','cancel_qty','trade_qty']})
        row.update(cancel_add_ratio=counts['cancel_count']/max(counts['add_count'],1),
                   add_buy_fraction=counts['add_buy_count']/counts['add_count'] if counts['add_count'] else np.nan,
                   cancel_buy_fraction=counts['cancel_buy_count']/counts['cancel_count'] if counts['cancel_count'] else np.nan,
                   log_add_size_median=float(np.log1p(np.median(sizes))) if sizes else np.nan,
                   log_add_size_p90=float(np.log1p(np.percentile(sizes,90))) if sizes else np.nan,
                   log_cancel_age_median_ms=float(np.log1p(np.median(ages))) if ages else np.nan,
                   short_cancel_fraction=float(np.mean(np.array(ages)<100)) if ages else np.nan,
                   return_bps=ret, trade_volatility_bps=rv, trade_range_bps=span)
        rows.append(row)
        for k in ['raw_records','execution_count','replace_count','cancel_count',
                  'unmatched_cancel_count','over_cancel_count','reset_count','bad_trade_price']:
            audit[k] += counts[k]
    return rows, dict(audit)


class RobustBaseline:
    def fit(self, x):
        self.median = np.nanmedian(x, axis=0)
        if not np.isfinite(self.median).all():
            raise ValueError('A feature is entirely missing in train.')
        clean = np.where(np.isfinite(x), x, self.median)
        mad = np.median(np.abs(clean-self.median), axis=0)*1.4826
        iqr = (np.percentile(clean,75,axis=0)-np.percentile(clean,25,axis=0))/1.349
        # Quantized order sizes can make both MAD and IQR exactly zero.
        # Train-only standard deviation fallback + domain floors avoid exploding scores.
        fallback = np.where(iqr>1e-8, iqr, np.std(clean,axis=0))
        floors = np.array([.1 if f.startswith('log_') else (1.0 if f.endswith('_bps') else .02)
                           for f in FEATURES])
        self.scale = np.maximum(np.where(mad>1e-8, mad, fallback), floors)
        return self

    def transform(self, x):
        clean = np.where(np.isfinite(x), x, self.median)
        return (clean-self.median)/self.scale

    def score(self, x):
        z = np.abs(self.transform(x))
        groups = np.stack([np.sqrt(np.mean(z[:, [FEATURES.index(f) for f in fs]]**2,axis=1))
                           for fs in GROUPS.values()],axis=1)
        # Average the two strongest groups; not a probability.
        return np.sort(groups,axis=1)[:,-2:].mean(axis=1)


def matrix(rows):
    return np.asarray([[float(r[f]) for f in FEATURES] for r in rows])


def splits(n):
    if n != 390:
        raise ValueError('Pilot split is explicitly defined for 390 minutes.')
    s = np.full(n, 'purged', dtype='<U12')
    s[:233] = 'train'
    s[235:311] = 'calibration'
    s[313:] = 'evaluation'
    return s


def csv_write(path, rows):
    with Path(path).open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def predict(bundle, rows):
    x = matrix(rows)
    robust = RobustBaseline()
    robust.median = bundle['robust_state']['median']
    robust.scale = bundle['robust_state']['scale']
    z = robust.transform(x)
    scores = {'robust':robust.score(x), 'isolation_forest':-bundle['forest'].score_samples(z)}
    result = []
    for i, row in enumerate(rows):
        top = np.argsort(np.abs(z[i]))[-3:][::-1]
        record = {k:row[k] for k in ['window_start_utc','window_end_utc','time_ny','minute','quality_ok']}
        record['missing_feature_count'] = int((~np.isfinite(x[i])).sum())
        record['top_deviations'] = '; '.join(f'{FEATURES[j]} ({z[i,j]:+.2f} robust-z)' for j in top
                                             if np.isfinite(x[i,j]))
        for model, values in scores.items():
            value = float(values[i])
            record[model+'_score'] = value
            record[model+'_reference_percentile'] = float(100*np.mean(bundle['reference'][model]<=value))
            record[model+'_alert'] = int(value>bundle['thresholds'][model] and int(row['quality_ok']) == 1)
        result.append(record)
    return result


def events(predictions, model):
    result=[]
    for row in predictions:
        if row['split'] != 'evaluation' or not row[model+'_alert']:
            continue
        if result and result[-1]['end_utc']==row['window_start_utc']:
            event=result[-1]
            event['end_utc']=row['window_end_utc']; event['windows']+=1
            if row[model+'_score']>event['peak_score']:
                event['peak_score']=row[model+'_score']; event['evidence']=row['top_deviations']
        else:
            result.append(dict(model=model,start_utc=row['window_start_utc'],end_utc=row['window_end_utc'],
                               windows=1,peak_score=row[model+'_score'],evidence=row['top_deviations']))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'work/viac23.dbn')
    parser.add_argument('--out',type=Path,default=ROOT/'outputs/anomaly_baseline')
    parser.add_argument('--score-csv',type=Path,help='Score feature rows with a saved, trusted bundle; no refit.')
    parser.add_argument('--model',type=Path)
    args=parser.parse_args(); args.out.mkdir(parents=True,exist_ok=True)
    if args.score_csv:
        if not args.model:
            parser.error('--score-csv requires --model (load trusted local artifacts only)')
        bundle=joblib.load(args.model)
        with args.score_csv.open(encoding='utf-8-sig',newline='') as stream:
            rows=list(csv.DictReader(stream))
        csv_write(args.out/'rescored.csv',predict(bundle,rows))
        print('Wrote rescored.csv without refitting.'); return
    data=load_dbn(args.source)
    rows,audit=extract(data)
    x=matrix(rows); split=splits(len(rows)); quality=np.array([r['quality_ok'] for r in rows],bool)
    train=(split=='train') & quality; calibration=(split=='calibration') & quality
    if train.sum()<100 or calibration.sum()<30:
        raise ValueError('Too few quality-approved windows to fit/calibrate.')
    robust=RobustBaseline().fit(x[train])
    forest=IsolationForest(n_estimators=300,max_samples=min(128,int(train.sum())),
                           contamination='auto',random_state=42,n_jobs=1).fit(robust.transform(x[train]))
    reference={'robust':robust.score(x[calibration]),
               'isolation_forest':-forest.score_samples(robust.transform(x[calibration]))}
    thresholds={k:float(np.quantile(v,.95,method='higher')) for k,v in reference.items()}
    bundle=dict(robust_state=dict(median=robust.median,scale=robust.scale),forest=forest,reference=reference,thresholds=thresholds,
                features=FEATURES,groups=GROUPS,version=1)
    joblib.dump(bundle,args.out/'model.joblib')
    predictions=predict(bundle,rows)
    for r,s in zip(predictions,split): r['split']=str(s)
    for r,s in zip(rows,split): r['split']=str(s)
    csv_write(args.out/'features.csv',rows); csv_write(args.out/'scores.csv',predictions)
    all_events=sum((events(predictions,m) for m in thresholds),[])
    (args.out/'events.json').write_text(json.dumps(all_events,indent=2),encoding='utf-8')
    summary=dict(ticker='VIAC',date='2021-03-23',source=str(args.source.resolve()),
        sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),records=len(data),audit=audit,
        feature_count=len(FEATURES),features=FEATURES,groups=GROUPS,
        split_counts=dict(Counter(split.tolist())),quality_excluded=int((~quality).sum()),
        train_used=int(train.sum()),calibration_used=int(calibration.sum()),thresholds=thresholds,
        threshold_policy='95th percentile of calibration, higher interpolation; strict >; fixed before evaluation',
        normalization=dict(median=robust.median.tolist(),scale=robust.scale.tolist(),
          policy='train median; 1.4826 MAD -> IQR/1.349 -> std fallback; floors: log=.1, bps=1, other=.02'),
        models={},versions=dict(python=platform.python_version(),numpy=np.__version__,sklearn=sklearn.__version__),
        limitations=['One ticker / venue / session; chronological engineering demonstration, not independent-day validation.',
          'No anomaly labels; no accuracy, recall or false-positive-rate claims.',
          'Reference observations are unlabeled, not certified normal.',
          'No index, full-book depth, spread or time-of-day seasonal model in this version.',
          'Explanations are robust feature deviations, not causal or Isolation Forest attribution.',
          'Same-session calibration cannot establish future-session alert rates.',
          'Source-specific DBN-v1 adapter; not a general live API implementation.'])
    for m in thresholds:
        evaluated=[r for r in predictions if r['split']=='evaluation' and r['quality_ok']]
        summary['models'][m]=dict(evaluation_windows=len(evaluated),
          alerted_windows=sum(r[m+'_alert'] for r in evaluated),
          merged_events=sum(e['model']==m for e in all_events),
          top_windows=[dict(time_ny=r['time_ny'],score=r[m+'_score'],evidence=r['top_deviations'])
                       for r in sorted(evaluated,key=lambda r:r[m+'_score'],reverse=True)[:5]])
    # Exact batch-vs-single-window scoring verifies model inference has no batch dependence.
    single=predict(bundle,[rows[-1]])[0]
    assert abs(single['robust_score']-predictions[-1]['robust_score'])<1e-10
    assert abs(single['isolation_forest_score']-predictions[-1]['isolation_forest_score'])<1e-10
    summary['batch_single_inference_check']='passed'
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    render(args.out,rows,predictions,summary)
    print(json.dumps({k:summary[k] for k in ['records','audit','feature_count','split_counts','quality_excluded','models']},indent=2))


def render(out,rows,predictions,summary):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
    fig,axes=plt.subplots(3,1,figsize=(13,8),sharex=True,layout='constrained')
    minute=np.arange(len(rows))
    axes[0].plot(minute,[r['last_trade_price'] for r in rows],color='#193b58',lw=1.3)
    axes[0].set_ylabel('Last trade (USD)')
    for ax,m,color in zip(axes[1:],summary['models'],['#008f87','#ad6522']):
        ax.plot(minute,[r[m+'_score'] for r in predictions],color=color,lw=1.1)
        ax.axhline(summary['thresholds'][m],color='#b33743',ls='--',label='Calibration threshold (95th percentile)')
        hits=[r for r in predictions if r['split']=='evaluation' and r[m+'_alert']]
        ax.scatter([int(r['minute']) for r in hits],[r[m+'_score'] for r in hits],s=22,color='#b33743',zorder=3)
        ax.set_ylabel(m.replace('_',' ').title()); ax.legend(loc='upper left',fontsize=8)
    for ax in axes:
        ax.axvspan(235,311,alpha=.10,color='#e8a739')
        ax.axvspan(313,390,alpha=.07,color='#258cc0')
        ax.grid(alpha=.15); ax.spines[['top','right']].set_visible(False)
    ticks=list(range(0,390,30)); axes[-1].set_xticks(ticks,[rows[t]['time_ny'] for t in ticks])
    axes[-1].set_xlabel('New York time | minute completed before scoring')
    fig.suptitle('VIAC / 23 March 2021 — unlabeled anomaly baseline\nTrain 09:30–13:23 · calibration 13:25–14:41 · evaluation 14:43–16:00',fontsize=14)
    fig.savefig(out/'baseline_results.png',dpi=160); plt.close(fig)
    cards=''.join(f'<article><h3>{html.escape(m.replace("_"," ").title())}</h3><strong>{v["alerted_windows"]} / {v["evaluation_windows"]}</strong><p>flagged evaluation windows · {v["merged_events"]} merged events</p></article>' for m,v in summary['models'].items())
    tables=''
    for m,v in summary['models'].items():
        body=''.join(f'<tr><td>{r["time_ny"]}</td><td>{r["score"]:.4f}</td><td>{html.escape(r["evidence"])}</td></tr>' for r in v['top_windows'])
        tables+=f'<h2>{html.escape(m.replace("_"," ").title())}: highest evaluation scores</h2><table><tr><th>Window start NY</th><th>Score</th><th>Observed deviations (not causal attribution)</th></tr>{body}</table>'
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><title>VIAC anomaly baseline</title><style>body{font:16px/1.6 system-ui,sans-serif;color:#203449;background:#f4f7fa;max-width:1150px;margin:40px auto;padding:0 24px}h1{font-size:34px;line-height:1.2}h2{font-size:21px;margin-top:32px}.tag{color:#187f78;font-weight:700;letter-spacing:2px}.notice{background:#fff2d6;padding:20px;border-left:4px solid #cb912d}.cards{display:flex;gap:20px}article{background:white;padding:24px;border-radius:12px;flex:1}strong{font-size:28px}img{width:100%;background:white;border-radius:10px}table{width:100%;border-collapse:collapse;background:white;font-size:13px}td,th{text-align:left;padding:12px;border-bottom:1px solid #dde4ec}a{color:#087b76}</style><p class="tag">RESEARCH ENGINEERING / BASELINE 01</p><h1>Locate unusual trading activity.<br>Keep the evidence visible.</h1><p>VIAC · Nasdaq MBO · 23 March 2021 · completed 60-second windows</p><p class="notice">Engineering demonstration on one previously inspected session. These are unlabeled observations. Alerts identify deviation from a reference period; they do not establish manipulation or detection accuracy. Red points are evaluation alerts only.</p>'''
    page+='<div class="cards">'+cards+'</div><h2>Chronological replay</h2><img src="baseline_results.png" alt="Price and anomaly scores over the session">'+tables
    page+='<h2>Method and limitations</h2><p>17 features from all session events: activity, order structure and price. Median/MAD scaling fits only training windows. Isolation Forest uses 300 trees and seed 42. Thresholds use only the separate calibration segment; four boundary minutes are purged. Yellow shading is calibration; blue is evaluation.</p><p>Feature evidence is the same robust deviation diagnostic for both models, not an explanation of the forest decision. Cancellation age uses observed births only. No full-book spread/depth or external market context is included.</p><p><a href="scores.csv">All scores</a> · <a href="features.csv">Features</a> · <a href="events.json">Merged alerts</a> · <a href="summary.json">Audit and configuration</a></p></html>'
    (out/'report.html').write_text(page,encoding='utf-8')


if __name__=='__main__':
    main()
