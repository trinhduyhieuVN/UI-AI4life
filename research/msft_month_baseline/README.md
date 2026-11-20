# MSFT | DHGNN + EBM cấp phiên

Mẫu train là một ngày giao dịch MSFT. GRU cấp phiên và cực đại tích lũy tạo trạng thái nhân quả, cho phép EBM cập nhật điểm từ đầu phiên đến hiện tại và xuất điểm cuối phiên. Seed 42. Mô hình không nhận tên mã hay nhãn thao túng.

## Chạy

- Trên Google Colab, mở `MSFT_month.ipynb`, chọn gói `MSFT_month_baseline.zip` ở ô đầu tiên rồi chạy các ô theo thứ tự. Có thể dùng CPU hoặc GPU.
- Trên máy cá nhân, giải nén gói, vào thư mục `msft_month_baseline` và dùng Python 3.11+. Với notebook, khởi chạy Jupyter từ thư mục này. Với dòng lệnh:

```console
python -m pip install -r requirements.txt
python train.py
python report.py
```

Các tệp đặc trưng của 42 phiên đã có trong `results/sessions`. Để xử lý lại từ MBO, chạy các lệnh sau. Dữ liệu đầu vào theo cấu trúc các thư mục job Databento, mỗi job chứa một mã, metadata.json, manifest.json và các tệp DBN v1 đã nén.

```console
python prepare.py --data D:/DATA_AI4LIFE --out rebuilt --workers 4
python train.py --out rebuilt
python report.py --out rebuilt
```

## Dữ liệu và phép đo

- 20 phiên tháng 11/2020 dành toàn bộ cho train. Validation từ 01 đến 07/12, hiệu chỉnh từ 08 đến 14/12, test từ 15 đến 31/12. Phân chia theo ngày giao dịch New York.
- Hypergraph dùng 32 vị trí lệnh ở sáu mốc mỗi phút; sáu khoảng 10 giây giữ tổng dòng lệnh. Ngữ cảnh thị trường gồm lợi suất trong phút, biên độ cao–thấp và log khối lượng cho SPY/QQQ. Thời điểm và cờ phiên ngắn lấy từ lịch giao dịch.
- Một phiên đối chiếu cho mỗi phiên gốc có 30 phút mà toàn bộ đồ thị lệnh được thay bằng đồ thị quan sát 1–5 phút trước. Đặc trưng dòng lệnh và bối cảnh vẫn theo đồng hồ gốc. Mất mát xếp hạng năng lượng tại cuối đoạn gây trễ, một mốc sau đó và cuối phiên. Mỗi ngày validation/test dùng biến đổi cố định theo seed. Mỗi phút chấm theo dữ liệu đã kết thúc.
- Ngưỡng ứng với từng phút là điểm lớn nhất tại cùng phút trên năm ngày hiệu chỉnh. Số ngày này quá ít để suy ra phân vị 99% hoặc kiểm soát chắc chắn tần suất cảnh báo.
- `results/report.html` là báo cáo độc lập có biểu đồ. `metrics.json` và `intraday_metrics.json` ghi số đo. `test_sessions.csv` có một dòng cho mỗi ngày test. `test_intraday.csv` có một dòng cho mỗi phút với điểm cuối cửa sổ theo giờ New York. `model.pt`, `normalization.npz` và `thresholds.csv` đi cùng phiên bản này. `sessions.csv` ghi nguồn, checksum và số liệu kiểm tra. Khối lượng và sổ lệnh của MSFT chỉ phản ánh nguồn XNAS.ITCH đã lấy.
- Các chỉ số phân loại được đo trên bài toán nhận ra dữ liệu bị làm trễ. Diễn biến quan sát giữ trạng thái chưa có nhãn bất thường. Dữ liệu một mã và 12 ngày test chưa đánh giá khả năng chuyển sang mã khác hoặc độ chính xác thao túng thực tế.
