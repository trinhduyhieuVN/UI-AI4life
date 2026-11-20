# NevAI

Giao diện React Native và Expo dùng chung cho web, Android và iOS. Trang web chạy cùng FastAPI tại `/orbit/`. Biểu đồ nến của Nasdaq Replay vẫn nằm ở `/?view=terminal&mode=historical`.

## Chạy dự án

Từ thư mục `orbital`, chạy `npm ci`. Dùng `npm run build:web` để cập nhật bản web mà FastAPI phục vụ từ `frontend/orbit`.

Để chạy ứng dụng di động, dùng `npm start` với môi trường Expo tương thích SDK 54. Ứng dụng đọc từ FastAPI ở cổng 8000. Android Emulator mặc định dùng `10.0.2.2`, iOS Simulator dùng `127.0.0.1`. Với điện thoại thật, đặt `EXPO_PUBLIC_API_URL` thành địa chỉ backend mà điện thoại truy cập được trước khi khởi động Metro. Có thể dùng HTTPS cho thiết bị thật. Ví dụ PowerShell khi đã có backend HTTPS:

```powershell
$env:EXPO_PUBLIC_API_URL = "https://your-backend.example"
npm start
```

## Dữ liệu và cảnh báo

NevAI tự phát từ giờ mở cửa của phiên mới nhất có đủ tám mã, cùng giờ mở cửa và số phút giao dịch. Danh sách phiên dựa trên kho MBO đã được trình nhập xác minh. Nút tốc độ chuyển giữa 30×, 60×, 120× và 240×. Đồng hồ dùng giờ New York và hỗ trợ phiên đóng sớm.

Đưa chuột lên một hành tinh để xem giá và điểm tại mốc phát. Trên thiết bị cảm ứng, chạm hành tinh để mở thông tin. Vầng sáng cam xuất hiện khi `energy > threshold`. Chuông ở góc trên bên phải hiển thị tổng số đợt bất thường trong phiên đến mốc đang phát. Mỗi thông báo gộp các phút vượt ngưỡng liên tiếp của cùng một mã và ghi khoảng thời gian theo giờ New York cùng điểm EBM cao nhất trong đợt. Bản demo cục bộ dùng tài khoản demo có sẵn khi chưa đăng nhập.

## Bảng tin hiện tại

Tin xuất hiện trực tiếp trên thanh đầu trang. Các tiêu đề nối đuôi nhau từ trái sang phải. Tin vừa nhận được ưu tiên ở vị trí kế tiếp trong dòng chữ. Bấm tiêu đề để mở bài gốc. Khi hết tin mới, dải chữ luân phiên tám tiêu đề gần nhất. Backend kiểm tra Google News RSS cho AAPL, MSFT, INTC, CSCO, CMCSA và FOXA sau mỗi 60 giây. Thời điểm nhận qua RSS phụ thuộc lúc Google lập chỉ mục.

Để nhận thêm tin khi nhà cung cấp phát, cấu hình các biến môi trường `APCA_API_KEY_ID` và `APCA_API_SECRET_KEY` cho tiến trình FastAPI rồi khởi động lại backend. Dùng tài khoản có quyền truy cập [Alpaca Real-time News](https://docs.alpaca.markets/us/docs/streaming-real-time-news). Khóa chỉ nằm ở backend. Khi Alpaca xác nhận đăng ký, backend chuyển tin mới tới dải chữ qua WebSocket.

Công cụ cung cấp `GET /api/v1/news` để lấy bản tin hiện có và WebSocket `/api/v1/news/stream` để nhận cập nhật. Luồng nguồn bắt đầu khi có yêu cầu tin đầu tiên. Mỗi tiến trình backend giữ một bộ đệm trong bộ nhớ. Khi WebSocket phía thiết bị gián đoạn, ứng dụng đọc lại API và tự kết nối lại. Thời gian hiển thị theo múi giờ thiết bị.

## Hình ảnh

Nền `assets/galaxy.png` được tạo bằng ImageGen tích hợp theo yêu cầu ảnh toàn cảnh Ngân Hà xanh đen với dải bụi sao chéo, cụm sao bạc và vùng tối ở trung tâm để đặt hệ hành tinh.

Atlas trong `assets/worlds.png` được tạo bằng ImageGen tích hợp. Yêu cầu hình ảnh là một atlas trong suốt 3 × 3 gồm tám hành tinh quang thực và Mặt Trời vàng ở giữa, nguồn sáng từ phía trên bên trái, mỗi thiên thể nằm trọn trong một ô. Các lớp quỹ đạo, nhãn, tín hiệu và chuyển động được dựng riêng bằng React Native.
