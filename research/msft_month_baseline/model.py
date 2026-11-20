import torch
from torch import nn
from torch.nn import functional as F
from features import NODE, FLOW

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


class MinuteEncoder(nn.Module):
    def __init__(self, hidden=48):
        super().__init__()
        self.embed = nn.Sequential(nn.Linear(len(NODE),hidden),nn.GELU())
        self.hg = nn.ModuleList([HyperLayer(hidden,True) for _ in range(2)])
        self.gru = nn.GRU(2*hidden+len(FLOW)+4,hidden,batch_first=True)
        self.head = nn.Sequential(nn.Linear(hidden+9,hidden),nn.GELU())
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
        return self.head(torch.cat([state[-1],b["ctx"]],-1))

class SessionEnergy(nn.Module):
    """Causal prefix score, including a running max to retain earlier activity."""
    def __init__(self, hidden=48):
        super().__init__()
        self.minute = MinuteEncoder(hidden)
        self.temporal = nn.GRU(hidden, hidden, batch_first=True)
        self.energy = nn.Sequential(nn.Linear(2*hidden, hidden), nn.GELU(), nn.Linear(hidden,1))

    def embed_minutes(self, batch, block=32):
        from torch.utils.checkpoint import checkpoint
        parts = []
        for j in range(0, len(batch["ctx"]), block):
            subset = {k: v[j:j+block] for k,v in batch.items()}
            if self.training:
                parts.append(checkpoint(self.minute, subset, use_reentrant=False))
            else:
                parts.append(self.minute(subset))
        return torch.cat(parts)

    def trajectory(self, embedding, state=None):
        previous_hidden, previous_peak = (None,None) if state is None else state
        h, final_hidden = self.temporal(embedding, previous_hidden)
        peak = h.cummax(dim=1).values
        if previous_peak is not None:
            peak = torch.maximum(peak, previous_peak)
        scores = self.energy(torch.cat((h,peak),dim=-1)).squeeze(-1)
        return scores, (final_hidden,peak[:,-1:])
