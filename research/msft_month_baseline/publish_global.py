"""Build the reusable research bundle after train_global.py."""
from pathlib import Path
import json
import zipfile
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT=Path(__file__).resolve().parent
out=ROOT/"global8"
metrics=json.loads((out/"metrics.json").read_text())
data=pd.read_csv(out/"sessions.csv")
history=pd.read_csv(out/"history.csv")
march=pd.read_csv(out/"viac_march_intraday.csv")
symbols=pd.read_csv(out/"metrics_by_symbol.csv")
by_split=data.groupby(["split","symbol"],sort=False).agg(first=("day","min"),last=("day","max"),
            sessions=("day","size"),minutes=("minutes","sum"),usable=("usable","sum"),
            mbo_events=("records","sum")).reset_index()
by_split.to_csv(out/"coverage.csv",index=False)
fig,axes=plt.subplots(1,2,figsize=(11,4.3))
ax=axes[0]
ax.plot(history.epoch,history.train_loss,label="Train",color="#155e68")
ax.plot(history.epoch,history.validation_loss,label="Validation",color="#bf6539")
ax.axvline(metrics["chosen_epoch"],color="#737b82",ls=":",label="Checkpoint được chọn")
ax.set(title="Học trên 160 mã–phiên",xlabel="Epoch",ylabel="Loss đối chiếu")
ax.legend(frameon=False,fontsize=8)
ax=axes[1]
for day,g in march.groupby("day"):
    event=(day=="2021-03-23")
    ax.plot(g.elapsed_minutes,g.margin,c="#136678" if event else "#b8c1ca",lw=1.8 if event else .8,
            alpha=1 if event else .85,label="23/03" if event else "5 phiên VIAC liền trước" if day=="2021-03-16" else None)
ax.axhline(0,c="#b55528",ls="--",lw=1,label="Ngưỡng cảnh báo")
ax.set(title="VIAC tháng 3/2021",xlabel="Phút kể từ mở cửa",ylabel="Năng lượng trừ ngưỡng")
ax.legend(frameon=False,fontsize=8)
for ax in axes:
    ax.spines[["top","right"]].set_visible(False)
    ax.grid(alpha=.15)
fig.tight_layout()
fig.savefig(out/"validation_and_event.png",dpi=150)
plt.close(fig)
readme="""# DHGNN + EBM cấp phiên trên 8 mã

Thư mục global8 chứa đặc trưng MBO đã xử lý cùng mô hình, ngưỡng, điểm kiểm thử và điểm của vụ VIAC. Mỗi mã dùng toàn bộ 20 phiên tháng 11/2020 để train. Tháng 12 tách theo ngày: 01–07 validation, 08–14 hiệu chỉnh, 15–31 test. Mô hình học từ đầu với seed 42 và một bộ trọng số dùng chung. Mỗi mã–phiên huấn luyện sinh một bản đối chiếu bằng cách làm trễ đồ thị trong một đoạn 30 phút. Mỗi epoch bao phủ 160 mã–phiên. Toàn bộ lớp được cập nhật trong 24 epoch, chọn checkpoint theo loss validation.

Ngưỡng chính ở mỗi phút là năng lượng lớn nhất của 40 mã–phiên hiệu chỉnh tại phút đó. Phiên ngắn dùng số phút thực tế. Quy tắc maximum được giữ từ baseline, số phiên hiệu chỉnh đã tăng từ 5 lên 40. matched_msft_metrics.json là phép so sánh phụ dùng đúng 5 phiên MSFT để hiệu chỉnh. Các chỉ số phân loại đo khả năng nhận biết sự lệch nhân tạo; dữ liệu thật không có nhãn theo phút.

Để chạy lại với đặc trưng có sẵn, dùng Python 3.11+:
```console
python -m pip install -r requirements.txt
python train_global.py --epochs 24
```
Chạy từ thư mục có tệp train_global.py. Có thể dùng GPU CUDA nếu môi trường có PyTorch tương thích. Để dựng lại đặc trưng, chạy `python prepare_global.py --data D:/DATA_AI4LIFE`. Tệp resume.pt chỉ được tạo trên máy đang huấn luyện và cho phép khôi phục sau khi gián đoạn. Bản ZIP chỉ đóng gói checkpoint dùng cho suy luận.

Tệp metrics.json tóm tắt kết quả chung, metrics_by_symbol.csv tách theo mã, test_sessions.csv ghi điểm cuối phiên, test_intraday.csv ghi điểm tích lũy từng phút. Hai tệp viac_march_* trình bày riêng ca kiểm tra tháng 3, chưa dùng để chọn trọng số hay ngưỡng. Phiên VIAC chưa thấy nhưng mã VIAC có mặt trong train.
"""
(out/"README.md").write_text(readme,encoding="utf8")
bundle=ROOT.parent/"outputs"/"DHGNN_EBM_global8.zip"
with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED,compresslevel=3) as z:
    for name in ["features.py","model.py","prepare.py","prepare_global.py","train.py",
                 "train_global.py","requirements.txt","publish_global.py","Global8_month.ipynb"]:
        z.write(ROOT/name,"global_model/"+name)
    z.write(out/"README.md","global_model/README.md")
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name!="resume.pt" and not path.name.endswith((".tmp",".partial")):
            z.write(path,"global_model/"+path.relative_to(ROOT).as_posix())
with zipfile.ZipFile(bundle) as z:
    assert z.testzip() is None
print("Bundle:",bundle,bundle.stat().st_size,flush=True)
