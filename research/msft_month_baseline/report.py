"""Generate a standalone Vietnamese report and the EDA tables and charts."""
import argparse
import base64
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
TEAL="#087e83"
NAVY="#203c62"
ORANGE="#ba531e"


def figure_html(path,alt):
    payload=base64.b64encode(path.read_bytes()).decode("ascii")
    return f'<img alt="{alt}" src="data:image/png;base64,{payload}">'


def save(fig,path):
    fig.tight_layout()
    fig.savefig(path,dpi=145,bbox_inches="tight")
    plt.close(fig)


def main(out):
    result=json.loads((out/"metrics.json").read_text())
    m=result["proxy_metrics"]
    manifest=pd.read_csv(out/"sessions.csv")
    tr=manifest[manifest.split=="train"]
    frames=[]
    segments=[]
    for r in tr.itertuples():
        with np.load(out/"sessions"/(r.day+".npz")) as d:
            frame=pd.DataFrame({k:d[k] for k in ("minute","spread","trade_volume","cancel_count","depth")})
        frame["day"]=r.day
        frames.append(frame)
        period=np.select([frame.minute<30,frame.minute>=r.minutes-30],["opening","closing"],default="middle")
        segments.append(frame.assign(period=period))
    observed=pd.concat(frames,ignore_index=True)
    profile=observed.groupby("minute")[["trade_volume","spread","cancel_count","depth"]].median()
    profile.to_csv(out/"eda_intraday_train.csv")
    segments=pd.concat(segments,ignore_index=True).groupby("period")[list(profile.columns)].median()
    segments.to_csv(out/"eda_session_segments.csv")
    plt.rcParams.update({"axes.spines.top":False,"axes.spines.right":False,"axes.grid":True,
                         "grid.alpha":.2,"font.family":"DejaVu Sans","axes.titlelocation":"left"})
    fig,axes=plt.subplots(2,2,figsize=(10,6))
    for ax,(name,title) in zip(axes.flat, [("trade_volume","Cổ phiếu khớp mỗi phút"),
            ("spread","Chênh lệch giá mua–bán (bps)"),("cancel_count","Số lượt hủy lệnh mỗi phút"),
            ("depth","Độ sâu trung bình mỗi phía ở 5 mức giá (cổ phiếu)")]):
        ax.plot(profile.index+1,profile[name],color=TEAL,lw=1)
        ax.set(title=title,xlabel="Phút kể từ khi mở cửa")
    save(fig,out/"eda_train.png")
    history=pd.read_csv(out/"history.csv")
    fig,ax=plt.subplots(figsize=(8,2.8))
    ax.plot(history.epoch,history.train_loss,label="Train",color=TEAL,marker=".")
    ax.plot(history.epoch,history.validation_loss,label="Validation",color=NAVY,marker=".")
    ax.axvline(result["selected_epoch"],ls=":",color="grey",label="Checkpoint")
    ax.set(xlabel="Epoch",ylabel="Contrastive loss")
    ax.legend()
    save(fig,out/"learning_curve.png")
    end=pd.read_csv(out/"test_sessions.csv")
    curves=pd.read_csv(out/"test_intraday.csv")
    proxy_events=[]
    for day, group in curves.groupby("day",sort=True):
        period=group[group.injected]
        # Is the synthetic path above the threshold while the original at the same time is below?
        added=period[(period.synthetic_energy>period.threshold) & ~period.observed_alert]
        proxy_events.append(dict(day=day, added_alert_during_injection=not added.empty,
                    added_alert_minutes=len(added), first_added_alert_delay_minutes=(
                    int(added.elapsed_minutes.iloc[0]-period.elapsed_minutes.iloc[0]+1) if len(added) else None)))
    events=pd.DataFrame(proxy_events)
    events.to_csv(out/"proxy_intraday_events.csv",index=False)
    within=int(events.added_alert_during_injection.sum())
    real_days=int((end.observed_alert_minutes>0).sum())
    pathways=dict(test_sessions=len(end),sessions_with_any_observed_alert=real_days,
                  total_observed_alert_minutes=int(curves.observed_alert.sum()),
                  total_observed_test_minutes=len(curves),
                  synthetic_sessions_with_additional_alert_during_injection=within)
    (out/"intraday_metrics.json").write_text(json.dumps(pathways,indent=2))
    dates=end.day.str[5:]
    fig,ax=plt.subplots(figsize=(9,3.1))
    ax.plot(dates,end.observed_margin,marker="o",color=TEAL,label="Phiên quan sát")
    ax.plot(dates,end.synthetic_margin,marker=".",color=ORANGE,label="Phiên giả lập")
    ax.axhline(0,c="black",lw=.8,ls="--",label="Ngưỡng")
    ax.set(ylabel="Năng lượng cuối phiên trừ ngưỡng",xlabel="Ngày test (tháng-ngày)")
    ax.legend(ncol=3,fontsize=8)
    save(fig,out/"close_scores.png")
    fig,axes=plt.subplots(4,3,figsize=(12,9),sharex=True,sharey=True)
    for ax,(day,df) in zip(axes.flat,curves.groupby("day",sort=True)):
        ax.plot(df.elapsed_minutes,df.observed_energy,c=TEAL,lw=1)
        ax.plot(df.elapsed_minutes,df.threshold,c=ORANGE,lw=.8,alpha=.85)
        ax.set_title(day,fontsize=10)
    fig.supxlabel("Phút đã trôi qua trong phiên")
    fig.supylabel("Điểm quan sát (xanh) và ngưỡng (cam)")
    save(fig,out/"test_paths.png")
    total_minutes=int(manifest.minutes.sum())
    ranges=manifest.groupby("split").agg(first=("day","min"),last=("day","max"),
                                         days=("day","count"),usable=("usable","sum"))
    ranges=ranges.loc[["train","validation","calibration","test"]]
    ranges.columns=["Phiên đầu","Phiên cuối","Số phiên","Số phút hợp lệ"]
    close=end[["day","n_minutes","observed_energy","threshold","observed_alert","observed_alert_minutes","synthetic_energy"]].copy()
    close["observed_alert"]=close.observed_alert.map({True:"Có",False:"—"})
    close.columns=["Ngày","Phút","Điểm thực","Ngưỡng","Cảnh báo cuối phiên","Số phút vượt ngưỡng","Điểm giả lập"]
    percent=lambda x:f"{x*100:.1f}%"
    table=lambda d,ix=False:d.to_html(index=ix,border=0,float_format=lambda n:f"{n:,.3f}")
    summary=pd.DataFrame(dict(
        metric=["Accuracy","Precision","Recall","F1","ROC-AUC","Average precision","Xếp đúng cặp"],
        value=[percent(m["accuracy"]),percent(m["precision"]),percent(m["recall"]),f'{m["f1"]:.3f}',
               f'{m["roc_auc"]:.3f}',f'{m["average_precision"]:.3f}', f'{m["paired_wins"]}/{len(end)}']))
    contents=f"""<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MSFT · Baseline DHGNN + EBM cấp phiên</title><style>body{{font:16px/1.55 system-ui,sans-serif;color:#172b3b;background:#f3f6f7;margin:0}}main{{margin:auto;max-width:1020px;padding:32px;background:white}}h1,h2{{line-height:1.16;color:#183451}}h2{{margin-top:2em}}img{{width:100%;height:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:7px;text-align:left;border-bottom:1px solid #d8e3e5}}th{{color:#154b5b}}.wrap{{overflow:auto}}p{{max-width:92ch}}@media(max-width:650px){{main{{padding:12px}}}}</style><main>
<h1>MSFT · Phát hiện bất thường theo phiên</h1>
<p>Baseline tự giám sát trên dữ liệu Nasdaq TotalView-ITCH. Cứ sau một phút giao dịch hoàn tất, mô hình chấm lại toàn bộ diễn biến từ mở cửa đến thời điểm đó. Điểm cuối cùng dùng để so sánh giữa các ngày.</p>
<h2>Dữ liệu và phân chia</h2><p>MBO của MSFT cùng OHLCV-1m của SPY và QQQ, lấy từ bộ Databento đã tải. Có {result["records"]:,} bản ghi MBO trong giờ giao dịch chính và {result["usable_minutes"]:,}/{total_minutes:,} phút đủ điều kiện. Từng tệp đầu vào được đối chiếu SHA-256 với manifest. Giờ ghi trong bảng chi tiết là New York. Phiên 27/11 và 24/12 đóng cửa sớm.</p>
{table(ranges,True)}
<h2>Phân tích tháng huấn luyện</h2><p>Đường trên từng biểu đồ là trung vị theo phút kể từ mở cửa. Tháng 11 có {int(tr.records.sum()):,} sự kiện trong {len(tr)} phiên. Trong bảng dưới, opening và closing là 30 phút đầu và cuối theo lịch thực của từng ngày; middle là phần còn lại. Các giá trị là trung vị theo phút.</p>
{figure_html(out/"eda_train.png","Hồ sơ theo phút của bốn đặc trưng")} {table(segments,True)}
<h2>Huấn luyện</h2><p>Mỗi mẫu là một phiên. Dựng lại sổ lệnh, lấy tối đa 32 lệnh ở mỗi snapshot, sáu snapshot mỗi phút và tổng dòng lệnh trong sáu đoạn 10 giây. Mô hình dùng hyperedge theo phía mua/bán, mức giá và tuổi lệnh, bổ sung lân cận động dựa trên embedding. GRU tích lũy biểu diễn theo phút, EBM nhận trạng thái hiện tại và cực đại tích lũy để xuất năng lượng. Thống kê chuẩn hóa chỉ lấy từ tập train.</p>
<p>Mỗi phiên đối chiếu có một đoạn 30 phút trong đó toàn bộ đồ thị lệnh bị trễ 1–5 phút so với dòng giao dịch. Tối ưu thứ tự năng lượng ở cuối đoạn bị trễ, một mốc sau đó và cuối phiên. Dừng sớm khi validation loss không cải thiện trong bốn epoch. Seed {result["seed"]}, số epoch đã chạy {result["epochs"]}, checkpoint được chọn ở epoch {result["selected_epoch"]}.</p>
{figure_html(out/"learning_curve.png","Loss theo epoch")}
<h2>Đánh giá trên các phiên chưa thấy</h2><p>Với mỗi phút đã trôi qua, lấy năng lượng lớn nhất của 5 phiên hiệu chỉnh tại đúng phút đó làm ngưỡng thực nghiệm. Điểm vượt ngưỡng sẽ phát cảnh báo. 5 phiên là mẫu nhỏ để ước lượng đuôi phân phối. Ngày 24/12 so với phút 210 của các phiên hiệu chỉnh thông thường.</p>
<p>Chỉ số dưới đây áp dụng cho {len(end)} phiên quan sát và {len(end)} bản giả lập ghép cặp. Nhãn tác vụ là bản quan sát (0) và bản bị làm trễ (1). Accuracy, precision, recall và F1 dùng quyết định cuối phiên. ROC-AUC và average precision dùng năng lượng cuối phiên trừ ngưỡng. Không có nhãn bất thường thực tế. Cặp dùng lại cùng một phiên gốc nên cỡ mẫu độc lập chỉ là {len(end)} ngày.</p>
{table(summary)}<p>Ma trận nhầm lẫn trên tác vụ giả lập có TN={m["tn"]}, FP={m["fp"]}, FN={m["fn"]}, TP={m["tp"]}. Trong {len(end)} phiên thực, {m["observed_close_alerts"]} phiên vượt ngưỡng lúc đóng cửa. Một phiên có thể vượt ngưỡng trong ngày rồi trở xuống dưới ngưỡng khi đóng cửa.</p>
{figure_html(out/"close_scores.png","Điểm thực và điểm giả lập cuối ngày")}
<div class="wrap">{table(close)}</div>
<h2>Điểm từ đầu đến cuối phiên</h2>
<p>Trong {len(end)} phiên test, {real_days} phiên có ít nhất một phút thực vượt ngưỡng; tổng cộng {int(curves.observed_alert.sum())}/{len(curves)} phút. Trong 30 phút gây trễ, {within}/{len(end)} phiên giả lập xuất hiện ít nhất một phút cảnh báo mới mà bản gốc cùng thời điểm chưa báo. Các phút liên tiếp có phụ thuộc thời gian.</p>
{figure_html(out/"test_paths.png","Đường điểm cho toàn bộ ngày test")}
<p>Đã kiểm tra trạng thái GRU và cực đại tích lũy bằng cách phát lại các embedding tuần tự theo đoạn 13 phút. Sai số tuyệt đối lớn nhất so với tính cả chuỗi là {result["max_online_difference"]:.3g}. Đây là kiểm tra tính nhất quán của phần tính điểm; độ trễ đầu cuối trên nguồn live chưa được đo.</p>
<p>Thí nghiệm chỉ bao phủ MSFT và một kiểu nhiễu tổng hợp. Phạm vi đánh giá hiện tại là khoanh vùng phiên để rà soát. Tệp test_intraday.csv lưu điểm sau từng phút; test_sessions.csv lưu điểm đóng cửa, ngưỡng, thời điểm cảnh báo đầu và số phút cảnh báo.</p></main></html>"""
    (out/"report.html").write_text(contents,encoding="utf-8")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,default=ROOT/"results")
    main(p.parse_args().out)
