"""Small end-to-end dynamic hypergraph + margin-energy pilot.

Primary endpoint is observed-vs-permuted lifecycle discrimination, not manipulation.
Architecture, splits, seeds and tests are fixed before reading test outcomes.
"""
from pathlib import Path
import os
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'work' / 'mbo_pilot_deps'))
os.environ.setdefault('OMP_NUM_THREADS', '4')
import copy
import json
import time
import random
import argparse
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from sklearn.metrics import roc_auc_score, average_precision_score

OUT = ROOT / 'outputs' / 'dhgnn_ebm_pilot'
SEEDS = [11, 22, 33]
MODELS = ['DeepSets_EBM', 'StaticHG_EBM', 'DynamicHG_EBM']
torch.set_num_threads(4)
torch.set_num_interop_threads(1)


def permute_lifecycles(x, mask, seed, fraction=1.0):
    """Reassign complete as-observed lifecycle traces to prices on the SAME side.

    Preserves per-side lifecycle marginals, masks, volume trajectories, quantity
    conservation and chronology. This is feature-level reassignment, not a replayed
    exchange tape, and is not a confirmed manipulation pattern.
    """
    rng = np.random.default_rng(seed)
    out, om = x.copy(), mask.copy()
    for b in range(len(x)):
        for side in [-1., 1.]:
            available = np.flatnonzero(mask[b,-1] & (x[b,-1,:,0] == side))
            if len(available) < 2:
                continue
            count = max(2, int(np.ceil(len(available) * fraction)))
            dst = rng.choice(available, count, replace=False)
            src = np.roll(dst, 1)
            for d, s in zip(dst, src):
                out[b,:,d,2:] = x[b,:,s,2:]
                om[b,:,d] = mask[b,:,s]
                out[b,:,d,0] = side * om[b,:,d]
                out[b,:,d,1] = x[b,-1,d,1] * om[b,:,d]
    # Quantity balance and every within-side marginal trajectory are preserved.
    assert np.array_equal(mask.sum(-1), om.sum(-1))
    assert np.allclose(x[...,2:].sum(2), out[...,2:].sum(2), atol=2e-5)
    assert np.all(out[...,4:7].sum(-1) <= 1.000001)
    return out, om


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


class EnergyModel(nn.Module):
    def __init__(self, kind, xm, xs, cm, cs, hidden=32):
        super().__init__()
        self.kind = kind
        for name,value in [('xm',xm),('xs',xs),('cm',cm),('cs',cs)]:
            self.register_buffer(name,torch.tensor(value,dtype=torch.float32))
        self.input_mlp = nn.Sequential(nn.Linear(len(xm),hidden), nn.GELU())
        if kind == 'DeepSets_EBM':
            self.layers = nn.ModuleList([nn.Sequential(nn.Linear(hidden,hidden*2),
                    nn.GELU(),nn.Linear(hidden*2,hidden),nn.LayerNorm(hidden)) for _ in range(2)])
        else:
            self.layers = nn.ModuleList([HyperLayer(hidden,kind=='DynamicHG_EBM') for _ in range(2)])
        self.temporal = nn.GRU(hidden*2+1,hidden,batch_first=True)
        self.energy_head = nn.Sequential(nn.Linear(hidden+len(cm),32),nn.GELU(),nn.Linear(32,1))

    def semantic_incidence(self, raw, mask):
        side = (raw[...,0] > 0).long()
        price_band = torch.bucketize(raw[...,1].contiguous(),
                    torch.tensor([-.2,-.05,.05,.2],device=raw.device))
        birth_band = (raw[...,8]*6).long().clamp(0,5)
        # Membership is generic: side, side/price band, side/birth-time cohort.
        a = torch.cat([F.one_hot(side,2), F.one_hot(side*5+price_band,10),
                       F.one_hot(side*6+birth_band,12)],dim=-1).float()
        return a * mask[:,:,None]

    def forward(self, x, mask, context, incidence=None):
        b,t,n,f = x.shape
        raw, m = x.reshape(b*t,n,f), mask.reshape(b*t,n)
        z = ((raw-self.xm)/self.xs).clamp(-8,8)
        h = self.input_mlp(z) * m[:,:,None]
        if incidence is None:
            incidence = self.semantic_incidence(raw,m)
        else:
            incidence = incidence.reshape(b*t,n,-1) * m[:,:,None]
        for layer in self.layers:
            if self.kind == 'DeepSets_EBM':
                h = (h + layer(h)) * m[:,:,None]
            else:
                h = layer(h,m,incidence)
        count = m.sum(1).clamp_min(1.)
        mean = h.sum(1)/count[:,None]
        mx = h.masked_fill(~m[:,:,None],-1e6).max(1).values
        mx = torch.where(m.any(1)[:,None],mx,torch.zeros_like(mx))
        pooled = torch.cat([mean,mx,(m.sum(1)/n)[:,None]],-1).reshape(b,t,-1)
        _,state = self.temporal(pooled)
        ctx = ((context-self.cm)/self.cs).clamp(-8,8)
        return self.energy_head(torch.cat([state[-1],ctx],-1)).squeeze(-1)


def scores(model, x, mask, context):
    model.eval()
    out=[]
    with torch.no_grad():
        for k in range(0,len(x),32):
            out.append(model(torch.from_numpy(x[k:k+32]),torch.from_numpy(mask[k:k+32]),
                             torch.from_numpy(context[k:k+32])).numpy())
    return np.concatenate(out)


def metrics(e_obs,e_alt,threshold):
    labels=np.r_[np.zeros(len(e_obs)),np.ones(len(e_alt))]
    pred=np.r_[e_obs,e_alt]
    return dict(roc_auc=float(roc_auc_score(labels,pred)),
        average_precision=float(average_precision_score(labels,pred)),
        paired_ranking_accuracy=float(np.mean((e_alt>e_obs)+.5*(e_alt==e_obs))),
        observed_alert_rate=float(np.mean(e_obs>threshold)),
        synthetic_detection_rate=float(np.mean(e_alt>threshold)),
        average_energy_gap=float(np.mean(e_alt-e_obs)))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--epochs',type=int,default=30)
    parser.add_argument('--seeds',type=int,nargs='+',default=SEEDS)
    parser.add_argument('--reuse-baselines',action='store_true')
    args=parser.parse_args()
    start=time.perf_counter()
    d=np.load(OUT/'pilot_samples.npz')
    x,mask,context,split=d['x'],d['mask'],d['context'],d['split']
    idx={name:np.flatnonzero(split==j) for j,name in enumerate(['train','val','test'])}
    tr,va,te=idx['train'],idx['val'],idx['test']
    vals=x[tr][mask[tr]]
    xm,xs=vals.mean(0),np.maximum(vals.std(0),.05)
    cm,cs=context[tr].mean(0),np.maximum(context[tr].std(0),.01)
    vx,vm=permute_lifecycles(x[va],mask[va],8801)
    tx,tm=permute_lifecycles(x[te],mask[te],9901)
    px,pm=permute_lifecycles(x[te],mask[te],9902,.25)
    config=dict(epochs=args.epochs,patience=7,seeds=args.seeds,models=MODELS,
        hidden=32,layers=2,snapshots=6,knn_neighbors='6 including all near-ties',batch_size=16,learning_rate=.001,
        weight_decay=.0001,energy_anchor=.001,margin=1.,
        train_corruption='same-side full lifecycle-to-price reassignment; regenerated each epoch',
        test_corruptions=['full reassignment','25-percent reassignment (held-out severity)'],
        normality_labels=False,market_index_present=False,
        note='DynamicHG is a compact custom temporal hypergraph encoder, not a reproduction of original DHGNN.',
        score='Higher energy means less compatible with the observed training distribution, not proven manipulation.',
        torch_version=torch.__version__,numpy_version=np.__version__,device='CPU',
        preprocessing='Normalization fitted on train only. Fixed chronological split with 4 purged minutes.')
    (OUT/'experiment_config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    runs=[]; predictions=[]
    if args.reuse_baselines:
        previous=json.loads((OUT/'training_results.json').read_text(encoding='utf-8'))
        (OUT/'before_tie_fix_results.json').write_text(json.dumps(previous,indent=2),encoding='utf-8')
        runs=[r for r in previous['runs'] if r['model']!='DynamicHG_EBM']
        predictions=[r for r in previous['predictions'] if r['model']!='DynamicHG_EBM']
    for kind in MODELS:
        for seed in args.seeds:
            if any(r['model']==kind and r['seed']==seed for r in runs):
                continue
            torch.manual_seed(seed); random.seed(seed); np.random.seed(seed)
            model=EnergyModel(kind,xm,xs,cm,cs)
            opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.0001)
            best=float('inf'); beststate=None; bestepoch=0; history=[]; gradient_audit={}
            initial={name:p.detach().clone() for name,p in model.named_parameters()}
            runtime=time.perf_counter()
            for epoch in range(args.epochs):
                ax,am=permute_lifecycles(x[tr],mask[tr],4400+epoch)
                order=np.random.default_rng(1000+seed+epoch).permutation(len(tr))
                model.train(); losses=[]
                for batch in range(0,len(tr),16):
                    local=order[batch:batch+16]; real=tr[local]; count=len(local)
                    bx=torch.from_numpy(np.concatenate([x[real],ax[local]]))
                    bm=torch.from_numpy(np.concatenate([mask[real],am[local]]))
                    bc=torch.from_numpy(np.concatenate([context[real],context[real]]))
                    opt.zero_grad()
                    en=model(bx,bm,bc); er,ea=en[:count],en[count:]
                    loss=F.relu(1.+er-ea).mean()+.001*en.square().mean()
                    assert torch.isfinite(loss)
                    loss.backward()
                    if epoch==0 and batch==0:
                        for prefix in ['input_mlp','layers','temporal','energy_head']:
                            norm=sum(float(p.grad.square().sum()) for name,p in model.named_parameters()
                                     if name.startswith(prefix) and p.grad is not None)**.5
                            gradient_audit[prefix]=norm
                            assert norm>0, (kind,prefix,'No gradient')
                    nn.utils.clip_grad_norm_(model.parameters(),5.)
                    opt.step(); losses.append(float(loss.detach()))
                vr=scores(model,x[va],mask[va],context[va]); ve=scores(model,vx,vm,context[va])
                vl=float(np.maximum(0,1.+vr-ve).mean()+.001*np.r_[vr,ve].__pow__(2).mean())
                history.append(dict(epoch=epoch+1,train_loss=float(np.mean(losses)),val_loss=vl,
                    val_auc=float(roc_auc_score(np.r_[np.zeros(len(vr)),np.ones(len(ve))],np.r_[vr,ve]))))
                if vl<best-1e-5:
                    best=vl; beststate=copy.deepcopy(model.state_dict()); bestepoch=epoch+1
                if (epoch+1)%5==0:
                    print(json.dumps(dict(model=kind,seed=seed,**history[-1])),flush=True)
                if epoch+1-bestepoch>=7:
                    break
            model.load_state_dict(beststate)
            threshold=float(np.quantile(scores(model,x[va],mask[va],context[va]),.95))
            er=scores(model,x[te],mask[te],context[te]); ef=scores(model,tx,tm,context[te])
            ep=scores(model,px,pm,context[te])
            # Harmless node reindexing should not change the score.
            permutation=np.random.default_rng(9910).permutation(x.shape[2])
            ei=scores(model,x[te][:,:,permutation],mask[te][:,:,permutation],context[te])
            invariance=float(np.max(np.abs(er-ei)))
            assert invariance<1e-3, (kind,invariance)
            changes={prefix:sum(float((p.detach()-initial[name]).square().sum())
                 for name,p in model.named_parameters() if name.startswith(prefix))**.5
                 for prefix in ['input_mlp','layers','temporal','energy_head']}
            assert all(v>0 for v in changes.values())
            run=dict(model=kind,seed=seed,parameters=sum(p.numel() for p in model.parameters()),
                epochs_completed=len(history),best_epoch=bestepoch,threshold=threshold,
                runtime_seconds=time.perf_counter()-runtime,history=history,
                initial_gradient_norm=gradient_audit,parameter_change_l2=changes,
                node_permutation_max_energy_difference=invariance,
                full=metrics(er,ef,threshold),partial=metrics(er,ep,threshold))
            runs.append(run)
            for j,ix in enumerate(te):
                predictions.append(dict(model=kind,seed=seed,window_start_ns=int(d['times'][ix]),
                    energy_observed=float(er[j]),energy_full=float(ef[j]),energy_partial=float(ep[j]),
                    threshold=threshold))
            torch.save(dict(state_dict=beststate,kind=kind,seed=seed,config=config),
                       OUT/f'{kind}_seed{seed}.pt')
            print(json.dumps({k:v for k,v in run.items() if k not in ['history','initial_gradient_norm','parameter_change_l2']}),flush=True)
            (OUT/'training_results.json').write_text(json.dumps(dict(config=config,runs=runs,
                predictions=predictions,elapsed_seconds=time.perf_counter()-start),indent=2),encoding='utf-8')
    print('ALL_RUNS_COMPLETE',time.perf_counter()-start,flush=True)


if __name__=='__main__':
    main()
