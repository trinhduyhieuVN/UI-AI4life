"""Render actual saved pilot results; never substitutes illustrative metrics."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import csv
import json
import html
import zipfile
import sys
import platform
from importlib.metadata import version
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.metrics import roc_auc_score

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'/'dhgnn_ebm_pilot'
LABELS={'DeepSets_EBM':'DeepSets + EBM','StaticHG_EBM':'Static HG + EBM',
        'DynamicHG_EBM':'Dynamic HG + EBM'}
COLORS=['#8797A9','#4C79B8','#088B82']


def local_time(ns):
    return datetime.fromtimestamp(ns/1e9,timezone(timedelta(hours=-4))).strftime('%H:%M')


def main():
    audit=json.loads((OUT/'data_audit.json').read_text(encoding='utf-8'))
    data=json.loads((OUT/'training_results.json').read_text(encoding='utf-8'))
    versions=dict(python=sys.version,platform=platform.platform(),
                  numpy=version('numpy'),scikit_learn=version('scikit-learn'),
                  matplotlib=version('matplotlib'),torch=data['config']['torch_version'])
    (OUT/'runtime_versions.json').write_text(json.dumps(versions,indent=2),encoding='utf-8')
    models=data['config']['models']; seeds=data['config']['seeds']
    assert len(data['runs']) == len(models)*len(seeds), 'Wait for all prespecified runs.'
    summary=[]
    for model in models:
        group=[r for r in data['runs'] if r['model']==model]
        row=dict(model=model,parameters=group[0]['parameters'])
        for corruption in ['full','partial']:
            for metric in ['roc_auc','average_precision','paired_ranking_accuracy',
                           'observed_alert_rate','synthetic_detection_rate','average_energy_gap']:
                v=[r[corruption][metric] for r in group]
                row[f'{corruption}_{metric}_mean']=float(np.mean(v))
                row[f'{corruption}_{metric}_sd']=float(np.std(v,ddof=1))
        row['runtime_seconds']=sum(r['runtime_seconds'] for r in group)
        summary.append(row)
    with (OUT/'metrics_summary.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    with (OUT/'test_predictions.csv').open('w',newline='',encoding='utf-8') as f:
        rows=[dict(**r,time_new_york=local_time(r['window_start_ns'])) for r in data['predictions']]
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

    # Paired moving-block bootstrap: variability inside this one test session only.
    arrays={}
    for model in models:
        for seed in seeds:
            r=sorted([r for r in data['predictions'] if r['model']==model and r['seed']==seed],
                     key=lambda r:r['window_start_ns'])
            arrays[model,seed]=np.array([[z['energy_observed'],z['energy_full']] for z in r])
    n=len(arrays[models[0],seeds[0]])
    rng=np.random.default_rng(1021)
    diffs=[]
    for _ in range(500):
        starts=rng.integers(0,n-5+1,size=int(np.ceil(n/5)))
        ix=np.concatenate([np.arange(j,j+5) for j in starts])[:n]
        deltas=[]
        for seed in seeds:
            av=[]
            for model in ['DynamicHG_EBM','DeepSets_EBM']:
                p=arrays[model,seed][ix]
                av.append(roc_auc_score(np.r_[np.zeros(n),np.ones(n)],np.r_[p[:,0],p[:,1]]))
            deltas.append(av[0]-av[1])
        diffs.append(np.mean(deltas))
    delta=summary[2]['full_roc_auc_mean']-summary[0]['full_roc_auc_mean']
    interval=np.quantile(diffs,[.025,.975]).tolist()
    verdict=('Có tín hiệu phân biệt mẫu đối chiếu trong phiên kiểm thử, nhưng chưa chứng minh phát hiện thao túng.'
             if summary[2]['full_roc_auc_mean']>.6 else
             'Thử nghiệm này chưa cho thấy khả năng phân biệt mẫu đối chiếu đủ rõ của Dynamic HG + EBM.')
    comparative=('Dynamic HG có AUC trung bình cao hơn DeepSets trong phép thử này.' if delta>0 else
                 'Dynamic HG chưa vượt DeepSets về AUC trung bình trong phép thử này.')
    if interval[0]<=0<=interval[1]:
        comparative+=' Khoảng bootstrap của chênh lệch bao gồm 0.'
    compact=dict(summary=summary,primary_auc_difference_dynamic_minus_deepsets=delta,
        same_session_block_bootstrap_95pct_interval=interval,
        bootstrap_note='500 paired resamples, contiguous blocks of 5 windows, average difference across seeds. '
            'Only within-session variability; no cross-day/cross-case generalization inference.',
        verdict=verdict,comparative=comparative)
    (OUT/'summary.json').write_text(json.dumps(compact,indent=2,ensure_ascii=False),encoding='utf-8')

    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
        'axes.spines.right':False,'axes.edgecolor':'#CDD5DF','text.color':'#162B40',
        'axes.labelcolor':'#455A70','xtick.color':'#455A70','ytick.color':'#455A70'})
    fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    fig.set_facecolor('#F7F9FC')
    names=['DeepSets','Static HG','Dynamic HG']
    for ax in axes.flat:
        ax.set_facecolor('white');ax.grid(axis='y',color='#E8EDF3',zorder=0)
    for ax,metric,title in [(axes[0,0],'roc_auc','Observed vs. full reassignment | ROC-AUC'),
                            (axes[0,1],'paired_ranking_accuracy','Paired ranking accuracy | full reassignment')]:
        means=[r[f'full_{metric}_mean'] for r in summary]
        sd=[r[f'full_{metric}_sd'] for r in summary]
        ax.bar(names,means,yerr=sd,capsize=5,color=COLORS,zorder=3,width=.55)
        ax.axhline(.5,ls='--',color='#B45A5A',lw=1,label='Chance: 0.50')
        ax.set_ylim(0,1.08);ax.set_title(title,loc='left',fontweight='bold',fontsize=11,pad=14)
        for i,v in enumerate(means):ax.text(i,min(1.035,v+sd[i]+.025),f'{v:.3f}',ha='center',fontweight='bold')
        ax.legend(frameon=False,loc='lower right',fontsize=8)
    ax=axes[1,0]
    for i,model in enumerate(models):
        run=next(r for r in data['runs'] if r['model']==model and r['seed']==seeds[0])
        ax.plot([h['epoch'] for h in run['history']],[h['val_loss'] for h in run['history']],
                label=names[i],color=COLORS[i],lw=2)
    ax.set_title('Validation ranking loss | seed 11',loc='left',fontweight='bold',fontsize=11,pad=14)
    ax.set_xlabel('Epoch');ax.legend(frameon=False,fontsize=8)
    ax=axes[1,1]
    xpos=np.arange(3);w=.32
    ax.bar(xpos-w/2,[s['full_roc_auc_mean'] for s in summary],w,label='Full reassignment',color='#256A9A',zorder=3)
    ax.bar(xpos+w/2,[s['partial_roc_auc_mean'] for s in summary],w,label='25% reassignment',color='#7BB9B0',zorder=3)
    ax.axhline(.5,ls='--',color='#B45A5A',lw=1)
    ax.set_xticks(xpos,names);ax.set_ylim(0,1.08)
    ax.set_title('Held-out corruption severity | ROC-AUC',loc='left',fontweight='bold',fontsize=11,pad=14)
    ax.legend(frameon=False,loc='lower right',fontsize=8)
    fig.suptitle('DHGNN + EBM   /   VIAC pilot',x=.02,ha='left',fontsize=23,fontweight='bold')
    fig.supxlabel('77 chronological test windows | 3 seeds | Error bars: seed SD | Synthetic contrast task; not manipulation accuracy',fontsize=9)
    fig.savefig(OUT/'pilot_results.png',dpi=180,facecolor=fig.get_facecolor())
    plt.close(fig)

    example_times=sorted(set(r['window_start_ns'] for r in data['predictions']))
    selected=[example_times[0],example_times[len(example_times)//2],example_times[-1]]
    examples=[r for r in data['predictions'] if r['model']=='DynamicHG_EBM'
              and r['seed']==seeds[0] and r['window_start_ns'] in selected]
    (OUT/'three_example_windows.json').write_text(json.dumps(examples,indent=2),encoding='utf-8')
    table=''.join('<tr><td>'+LABELS[r['model']]+'</td>'+''.join(
        f'<td>{r[k+"_mean"]:.3f} ± {r[k+"_sd"]:.3f}</td>' for k in
        ['full_roc_auc','full_average_precision','full_paired_ranking_accuracy','partial_roc_auc'])+'</tr>' for r in summary)
    examples_html=''.join(f'<tr><td>{local_time(r["window_start_ns"])}</td>'
        f'<td>{r["energy_observed"]:.3f}</td><td>{r["energy_full"]:.3f}</td>'
        f'<td>{r["energy_partial"]:.3f}</td></tr>' for r in examples)
    max_inv=max(r['node_permutation_max_energy_difference'] for r in data['runs'])
    page=f'''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DHGNN + EBM — VIAC pilot</title><style>
body{{margin:0;background:#f5f7fb;color:#183047;font:16px/1.65 'Segoe UI',Arial,sans-serif}}
main{{max-width:1100px;margin:45px auto;padding:0 30px 65px}}.eyebrow{{color:#088b82;letter-spacing:2px;font-size:13px;font-weight:700}}
h1{{font-size:42px;line-height:1.15;margin:12px 0}}h2{{font-size:24px;margin-top:38px}}.sub{{color:#64758a}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin:26px 0}}.card{{background:white;padding:18px;border-radius:12px;border:1px solid #e2e8ef}}
.number{{font-size:28px;font-weight:700;display:block}}.note{{background:#fff5df;border-left:4px solid #d7a543;padding:18px 22px}}
table{{width:100%;border-collapse:collapse;background:white;font-size:14px}}td,th{{padding:13px 12px;border-bottom:1px solid #e4e9f0;text-align:left}}
th{{background:#eaf0f6}}a{{color:#087e79}}img{{width:100%;margin:22px 0;border-radius:12px}}
code{{background:#eaf0f6;padding:2px 5px}}.fine{{font-size:13px;color:#63768b}}li{{margin:6px 0}}
@media(max-width:700px){{.cards{{grid-template-columns:1fr 1fr}}h1{{font-size:32px}}table{{font-size:12px}}td,th{{padding:8px}}}}
</style><main><div class="eyebrow">EMPIRICAL PILOT · 17 NOV 2026</div>
<h1>Dynamic Hypergraph + Energy-Based Model</h1><p class="sub">Thử nghiệm có thể tái lập trên MBO của VIAC · Nasdaq · 23/03/2021</p>
<div class="cards"><div class="card"><span class="number">1,021,465</span>bản ghi đầu vào</div>
<div class="card"><span class="number">390</span>cửa sổ một phút</div>
<div class="card"><span class="number">233 / 76 / 77</span>train / validation / test</div>
<div class="card"><span class="number">3 × 3</span>mô hình × seed</div></div>
<div class="note"><strong>Phạm vi kết luận:</strong> dữ liệu gốc chưa có nhãn thao túng theo cửa sổ. Nhãn kiểm thử chỉ phân biệt
<em>dữ liệu quan sát</em> và <em>mẫu hoán đổi đặc trưng vòng đời lệnh</em>. Dữ liệu quan sát không được xác nhận là bình thường.
Không thể diễn giải các chỉ số bên dưới thành độ chính xác phát hiện thao túng.</div>
<h2>Kết quả chính</h2><p>{verdict} {comparative}</p>
<table><tr><th>Mô hình</th><th>ROC-AUC</th><th>Average precision</th><th>Paired accuracy</th><th>AUC: hoán đổi 25%</th></tr>{table}</table>
<p class="fine">Trung bình ± độ lệch chuẩn qua seed 11, 22, 33. Test có 77 mẫu gốc + 77 mẫu đối chiếu cho mỗi loại.
AUC và paired accuracy ngẫu nhiên: 0,50; AP nền: 0,50 do tỷ lệ tổng hợp 1:1, không phản ánh tỷ lệ thao túng ngoài thực tế.</p>
<p>Chênh lệch AUC Dynamic HG − DeepSets: <strong>{delta:+.3f}</strong>.
Khoảng bootstrap theo block trong cùng phiên: [{interval[0]:+.3f}, {interval[1]:+.3f}].
Khoảng này không đánh giá khả năng tổng quát sang ngày hoặc vụ việc khác.</p>
<img src="pilot_results.png" alt="Actual model metrics and validation learning curves">
<h2>Thiết kế đã chạy</h2><ol>
<li>Đọc DBN v1, kiểm tra kích thước bản ghi và thứ tự timestamp. Loại snapshot tổng hợp khỏi luồng sự kiện thực.</li>
<li>Nhận diện 71.110 bản ghi giảm lệnh do khớp từ chuỗi F/C, và 39.343 giảm lệnh do thay thế; không cộng chúng vào hủy tự nguyện.</li>
<li>Mỗi phút lấy tối đa 24 lệnh mới trong phạm vi ±1% quanh giá giao dịch đã biết ở đầu phút. Lấy 6 snapshot tại các mốc 10 giây.
Giữ thông tin đã biết đến mỗi snapshot; lệnh chưa kết thúc được ghi nhận là đang mở. Các lệnh từ trước cửa sổ và lệnh xa giá không nằm trong mẫu node.</li>
<li>Hyperedge theo phía, vùng giá và nhóm thời điểm đặt lệnh; Dynamic HG bổ sung nhóm 6 hàng xóm gần nhất trong embedding,
dựng lại ở mỗi snapshot và mỗi tầng; giữ tất cả hàng xóm gần bằng khoảng cách thứ 6 để tránh phụ thuộc đánh số node.
Mô hình dùng 2 tầng tổng hợp node → hyperedge → node có phi tuyến, GRU và energy head.</li>
<li>DeepSets dùng cùng dữ liệu, GRU và energy head nhưng không truyền thông tin qua hyperedge. Static HG chỉ dùng các hyperedge theo quy tắc.
Tên Static HG chỉ phần cấu trúc theo quy tắc; trạng thái node vẫn thay đổi theo thời gian.</li>
<li>Huấn luyện margin loss <code>max(0, 1 + E_observed − E_alternative)</code>, cộng regularization năng lượng;
AdamW, tối đa 30 epoch, early stopping trên validation. Không tính partition function; điểm energy không phải xác suất thao túng.</li>
<li>Mẫu đối chiếu hoán đổi toàn bộ trajectory vòng đời giữa các node cùng phía, giữ giá gắn với node. Bảo toàn phân bố vòng đời theo phía,
số node theo snapshot và cân bằng khối lượng. Đây là perturbation ở mức đặc trưng, chưa kiểm tra bằng replay matching engine.</li>
<li>Train: 09:30–13:23; validation: 13:25–14:41; test: 14:43–16:00, giờ New York (mốc cuối không bao gồm).
Loại 4 phút quanh ranh giới. Không trùng order ID giữa các tập; chuẩn hóa chỉ fit trên train.</li>
</ol>
<h2>Ba cửa sổ minh họa</h2><p>Chọn trước theo vị trí đầu, giữa, cuối tập test; dùng Dynamic HG, seed 11. Giờ là đầu cửa sổ;
điểm chỉ được tính sau khi cửa sổ kết thúc. Các con số là năng lượng tương đối.</p>
<table><tr><th>Giờ New York</th><th>Dữ liệu gốc</th><th>Hoán đổi toàn bộ</th><th>Hoán đổi 25%</th></tr>{examples_html}</table>
<h2>Kiểm tra kỹ thuật</h2><ul><li>Có gradient khác 0 và có cập nhật tham số ở encoder, các tầng truyền thông tin, GRU và energy head trong cả 9 lần chạy.</li>
<li>Hoán vị đồng thời thứ tự node và đặc trưng làm thay đổi năng lượng tối đa {max_inv:.2e}; kiểm tra tính bất biến theo đánh số node đã qua.</li>
<li>Tỷ lệ đóng lệnh cuối cửa sổ của mẫu: khoảng 93,5%; các lệnh còn mở không bị gán thời gian kết thúc tương lai.</li>
<li>Nhánh k-NN dùng lựa chọn rời rạc, không backprop qua thao tác chọn hàng xóm; trọng số thông điệp và encoder vẫn được học chung.</li></ul>
<p class="fine">Lần chạy đầu phát hiện sai lệch khi đổi thứ tự node ở Dynamic HG (seed 22, chênh lệch năng lượng 0,00207).
Đã sửa cách xử lý hàng xóm có khoảng cách gần bằng nhau và chạy lại cả 3 seed Dynamic HG. Giữ nguyên các baseline,
split, corruption, ngân sách huấn luyện và cách chọn checkpoint. Kết quả trước sửa được lưu riêng; không dùng để chọn mô hình tốt hơn.</p>
<h2>Giới hạn và bước tiếp theo</h2><ul>
<li>Một cổ phiếu, một phiên, một venue. Một triệu bản ghi không tương đương một triệu mẫu độc lập.</li>
<li>Chưa có chuỗi chỉ số thị trường: context chỉ gồm giờ giao dịch và thống kê trễ của VIAC. Chưa kiểm thử đầy đủ market-conditioned EBM.</li>
<li>Sampling 24 lệnh và snapshot 10 giây có thể bỏ lỡ tín hiệu ngắn hoặc nhóm lệnh lớn. Chưa có nhãn thật để tinh chỉnh bằng MIL.</li>
<li>Khả năng nhận ra mẫu hoán đổi có thể phản ánh đặc điểm của bộ sinh, chưa phải mẫu thao túng. Cần thử trên nhiều ngày đối chứng và vụ việc độc lập.</li>
<li>Giữ nguyên tập test này; cải tiến sau đó cần một tập test mới. Chưa có cơ sở tuyên bố đóng góp học thuật hay lợi thế vận hành từ pilot.</li></ul>
<h2>Tệp kết quả</h2><p><a href="metrics_summary.csv">Bảng chỉ số</a> · <a href="test_predictions.csv">Điểm từng mẫu test</a> ·
<a href="training_results.json">Lịch sử huấn luyện</a> · <a href="data_audit.json">Kiểm tra dữ liệu</a> ·
<a href="experiment_config.json">Cấu hình</a></p>
<p class="fine">Nguồn quy tắc chuẩn hóa: <a href="https://databento.com/docs/datasets/xnas-itch">Databento XNAS.ITCH</a>.
Nguồn kiến trúc tham khảo: <a href="https://ijcai.org/proceedings/2019/366">DHGNN, IJCAI 2019</a>.
Đây là mô hình pilot tùy biến, không phải bản tái lập nguyên bản bài báo.</p></main></html>'''
    (OUT/'report.html').write_text(page,encoding='utf-8')
    readme='''# DHGNN + EBM pilot

Actual execution on supplied VIAC MBO, 2021-03-23. See outputs/dhgnn_ebm_pilot/report.html.
This is an observed-vs-feature-perturbation contrastive task, NOT confirmed manipulation classification.

## Reproduce

Use Python with numpy, torch, scikit-learn and matplotlib (recorded exact runtime in experiment_config.json).
The training script also checks work/mbo_pilot_deps for a project-local Torch installation.

The archive includes the prepared pilot_samples.npz. To rerun training and reporting:

    python work/train_mbo_pilot.py --epochs 30
    python work/report_mbo_pilot.py

To regenerate samples, put the original decompressed DBN file at work/viac23.dbn, then run:

    python work/prepare_mbo_pilot.py

Original compressed/decompressed source market files and third-party packages are not bundled.
Inspect data_audit.json for source hash and parser assumptions. See the HTML report for limitations.
The .pt files are the trained model checkpoints produced by these scripts.
'''
    (OUT/'README.md').write_text(readme,encoding='utf-8')
    archive=ROOT/'outputs'/'dhgnn_ebm_pilot_reproducible.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in OUT.iterdir():
            if p.is_file():z.write(p,p.relative_to(ROOT))
        for name in ['prepare_mbo_pilot.py','train_mbo_pilot.py','report_mbo_pilot.py']:
            p=ROOT/'work'/name;z.write(p,p.relative_to(ROOT))
    print(json.dumps(compact,ensure_ascii=True,indent=2))
    print(str(archive))


if __name__=='__main__':
    main()
