from pathlib import Path
import sys, time, math, json, random, copy
from datetime import date, datetime, timezone
from collections import Counter
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'work'/'mbo_pilot_deps'))
sys.path.insert(0,str(ROOT/'work'))
from preprocess_mbo import dbn_records, MBO, BAR, NODE, BOOK, FLOW, NS, session_bounds, OrderBook
import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.nn import functional as F
from sklearn.metrics import roc_auc_score, average_precision_score
RES = Path(__file__).resolve().parent
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
HIDDEN, BATCH, SEED = 48,48,42
torch.set_num_threads(4)
random.seed(SEED)
torch.manual_seed(SEED)


def read_context(path):
    bars = {}
    for r in dbn_records(path, BAR, 33):
        ts, op, hi, lo, cl, volume = r[4:]
        if ts in bars or not (0 < lo <= min(op, cl) <= max(op, cl) <= hi):
            raise ValueError(f"Invalid or duplicate bar in {path} at {ts}")
        bars[ts] = (1e4 * math.log(cl / op), 1e4 * math.log(hi / lo), math.log1p(volume))
    return bars

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
            for _ in records:
                pass
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
    market = np.full((minutes, 2, 3), np.nan, np.float64)
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
    return report

def session_arrays(row):
    with np.load(row.path) as d:
        good = d["book_valid"].all(1) & np.isfinite(d["market"]).all(axis=(1,2))
        count = len(good)
        ix = np.flatnonzero(good)
        x = d["x"][ix,9::10].copy()
        for k in (2,3,5,6,7): x[...,k] = np.log1p(np.maximum(x[...,k],0))
        x = np.nan_to_num(x)
        mask = d["mask"][ix,9::10]
        edge = d["edge_group"][ix,9::10]
        book = d["book"][ix,9::10,1:].copy()
        book[...,1:3] = np.log1p(book[...,1:3])
        f = d["flow"][ix].reshape(len(ix),6,10,len(FLOW)).sum(2)
        step = np.concatenate([np.log1p(f),book],-1).astype("float32")
        ctx = np.column_stack([d["market"][ix].reshape(len(ix),6),
              np.sin(2*np.pi*ix/390),np.cos(2*np.pi*ix/390),
              np.full(len(ix),count==210)]).astype("float32")
        return dict(x=x,mask=mask,edge=edge,step=step,ctx=ctx), d["cutoff_ns"][ix], ix

class HyperLayer(nn.Module):
    def __init__(self, hidden, dynamic):
        super().__init__()
        self.dynamic = dynamic
        self.edge_mlp = nn.Sequential(nn.Linear(hidden,hidden), nn.GELU(),
                                      nn.Linear(hidden,hidden))
        self.node_mlp = nn.Sequential(nn.Linear(hidden*2,hidden), nn.GELU(),
                                      nn.Linear(hidden,hidden))
        self.norm = nn.LayerNorm(hidden)

    def forward(self, h, mask, incidence):
        a = incidence
        if self.dynamic:
            # Hard kNN is rebuilt for each snapshot and layer. Gradients pass
            # through messages, NOT the discrete neighbor-selection operation.
            with torch.no_grad():
                dist = torch.cdist(h.detach(), h.detach())
                dist = dist.masked_fill(~mask[:,None,:], 1e9)
                # Include all near-ties at the kth distance. Arbitrarily picking
                # tied indices can make node relabeling change the prediction.
                cutoff = dist.topk(min(6,h.shape[1]),dim=-1,largest=False).values[:,:,-1:]
                tolerance = 1e-5 * cutoff.clamp_min(1.)
                knn = (dist <= cutoff + tolerance).to(h.dtype)
                knn = knn * mask[:,:,None] * mask[:,None,:]
                a = torch.cat([a,knn.transpose(1,2)],dim=2)
        degree = a.sum(1).clamp_min(1.)
        edge = torch.bmm(a.transpose(1,2),h) / degree[:,:,None]
        edge = self.edge_mlp(edge)
        back = torch.bmm(a,edge) / a.sum(2).clamp_min(1.)[:,:,None]
        h = self.norm(h + self.node_mlp(torch.cat([h,back],-1)))
        return h * mask[:,:,None]

class DHGNNEnergy(nn.Module):
    def __init__(self):
        super().__init__()
        self.embed = nn.Sequential(nn.Linear(len(NODE),HIDDEN),nn.GELU())
        self.hg = nn.ModuleList([HyperLayer(HIDDEN,True) for _ in range(2)])
        self.gru = nn.GRU(2*HIDDEN+len(FLOW)+4,HIDDEN,batch_first=True)
        self.head = nn.Sequential(nn.Linear(HIDDEN+9,HIDDEN),nn.GELU(),nn.Linear(HIDDEN,1))
    def forward(self,b):
        B,T,N,D = b["x"].shape
        mask = b["mask"].reshape(-1,N)
        group = b["edge"].reshape(-1,N,3).long()
        edges = torch.cat([F.one_hot(group[...,i].clamp_min(0),w)
                           for i,w in enumerate((2,6,10))],-1).float()*mask.unsqueeze(-1)
        h = self.embed(b["x"].reshape(-1,N,D))*mask.unsqueeze(-1)
        for layer in self.hg: h=layer(h,mask,edges)
        mean = h.sum(1)/mask.sum(1,keepdim=True).clamp_min(1)
        maximum = h.masked_fill(~mask.unsqueeze(-1),-1e6).amax(1)
        maximum = torch.where(mask.any(1,keepdim=True),maximum,0.)
        pooled = torch.cat([mean,maximum],-1).reshape(B,T,-1)
        _,state = self.gru(torch.cat([pooled,b["step"]],-1))
        return self.head(torch.cat([state[-1],b["ctx"]],-1)).flatten()

def perturb(b,rng,mild=False):
    B,T = b["x"].shape[:2]
    shift = np.ones(B,dtype=int) if mild else rng.integers(1,T,size=B)
    order = (torch.arange(T,device=DEVICE)[None,:]+torch.as_tensor(shift,device=DEVICE)[:,None])%T
    idx = torch.arange(B,device=DEVICE)[:,None]
    return {**b, **{k:b[k][idx,order] for k in ("x","mask","edge")}}


def main():
    start = time.perf_counter()
    jobs = {}
    for meta in Path('D:/DATA_AI4LIFE').glob('*/metadata.json'):
        q=json.loads(meta.read_text(encoding='utf-8-sig'))['query']
        jobs[q['schema'],q['symbols'][0]] = meta.parent
    day=date(2021,3,23)
    contexts = {s:read_context(next(jobs['ohlcv-1m',s].glob('*.ohlcv-1m.dbn.zst'))) for s in ('SPY','QQQ')}
    report = preprocess(jobs['mbo','VIAC']/'xnas-itch-20210323.mbo.dbn.zst','VIAC',day,contexts,32,RES)
    bad=['duplicate_add','invalid_add','unmatched_reduction','over_reduction','timestamp_regressions','unexpected_action_or_price']
    assert not any(report['audit'].get(k,0) for k in bad), report['audit']
    a,ts,minute=session_arrays(SimpleNamespace(path=RES/'2021-03-23_VIAC.npz'))
    groups = dict(train=minute<234, validation=(minute>=234)&(minute<273),
                  calibration=(minute>=273)&(minute<312),test=minute>=312)
    idx=np.flatnonzero(groups['train'])
    stats={}
    for k in ('x','step','ctx'):
        arr=a[k][idx]
        arr=arr[a['mask'][idx]] if k=='x' else arr.reshape(-1,arr.shape[-1])
        mu=arr.mean(0,dtype=np.float64).astype('float32')
        sd=arr.std(0,dtype=np.float64).astype('float32')
        sd=np.where(sd>1e-5,sd,1)
        stats[k+'_mean']=mu
        stats[k+'_scale']=sd
        a[k]=np.clip((a[k]-mu)/sd,-10,10)
    np.savez(RES/'normalization.npz',**stats)
    pre=time.perf_counter()-start
    model=DHGNNEnergy().to(DEVICE)
    opt=torch.optim.AdamW(model.parameters(),lr=5e-4,weight_decay=1e-4)
    def step(split,seed):
        training=split=='train'
        model.train(training)
        rng=np.random.default_rng(seed)
        ix=np.flatnonzero(groups[split])
        if training: rng.shuffle(ix)
        original,altered,loss_sum=[],[],0.
        with torch.set_grad_enabled(training):
            for j in range(0,len(ix),BATCH):
                select=ix[j:j+BATCH]
                b={k:torch.from_numpy(v[select]).to(DEVICE) for k,v in a.items()}
                obs,alt=model(b),model(perturb(b,rng))
                loss=F.softplus(1+obs-alt).mean()+0.001*(obs.square()+alt.square()).mean()
                if training:
                    opt.zero_grad(set_to_none=True)
                    loss.backward()
                    nn.utils.clip_grad_norm_(model.parameters(),2)
                    opt.step()
                original.extend(obs.detach().cpu().tolist())
                altered.extend(alt.detach().cpu().tolist())
                loss_sum+=float(loss.detach())*len(select)
        return np.array(original),np.array(altered),loss_sum/len(ix)
    train_start=time.perf_counter()
    best=float('inf')
    history=[]
    for epoch in range(1,16):
        _,_,tr=step('train',SEED+epoch)
        _,_,va=step('validation',9107)
        history.append([epoch,tr,va])
        if va<best:
            best,best_epoch,best_state=va,epoch,copy.deepcopy(model.state_dict())
        if epoch-best_epoch>=4: break
    model.load_state_dict(best_state)
    train_seconds=time.perf_counter()-train_start
    cal,_,_=step('calibration',2026)
    threshold=float(np.quantile(cal,0.99,method='higher'))
    obs,alt,_=step('test',2027)
    y=np.r_[np.zeros(len(obs)),np.ones(len(alt))]
    scores=np.r_[obs,alt]
    df=pd.DataFrame(dict(window_end_ny=pd.to_datetime(ts[groups['test']],utc=True).tz_convert('America/New_York'),
                         energy=obs,synthetic_energy=alt,threshold=threshold,alert=obs>threshold))
    df.to_csv(RES/'test_scores.csv',index=False)
    pd.DataFrame(history,columns=['epoch','train_loss','val_loss']).to_csv(RES/'history.csv',index=False)
    torch.save(dict(model=best_state,epoch=best_epoch),RES/'model.pt')
    result=dict(symbol='VIAC',date=str(day),device=str(DEVICE),torch=torch.__version__,seed=SEED,
                counts={k:int(v.sum()) for k,v in groups.items()},reference_records=report['audit'].get('regular_records'),
                epochs=epoch,best_epoch=best_epoch,preprocess_seconds=pre,training_with_validation_seconds=train_seconds,
                paired_accuracy=float((alt>obs).mean()),paired_correct=int((alt>obs).sum()),synthetic_roc_auc=roc_auc_score(y,scores),
                synthetic_average_precision=average_precision_score(y,scores),observed_alerts=int((obs>threshold).sum()),
                synthetic_alerts=int((alt>threshold).sum()),threshold=threshold,
                sample_seconds_total=time.perf_counter()-start)
    (RES/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__': main()
