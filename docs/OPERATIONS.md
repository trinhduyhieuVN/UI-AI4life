# Vận hành Nasdaq Replay

Tài liệu vận hành self-host. Mục dưới đây covers HTTPS tự ký (mkcert) và cài trust root CA cho thiết bị trong LAN.

## HTTPS tự ký (mkcert) & cookie Secure

Mặc định server chạy HTTP ở `0.0.0.0:8000`. Để bật HTTPS (bắt buộc khi truy cập từ điện thoại/máy khác trong LAN, vì cookie phiên chỉ gửi qua kết nối an toàn khi `Secure`):

### 1. Cài mkcert

- Windows: `winget install --id FiloSottile.mkcert -e`
- macOS: `brew install mkcert`
- Linux: `sudo apt install mkcert` (hoặc tải binary từ GitHub releases)

### 2. Sinh chứng chỉ cho localhost + IP LAN

Đặt `CAROOT` trỏ vào thư mục `certs/` của repo để root CA nằm cùng chỗ với cert (thư mục này đã gitignore — **không commit key**):

```bash
# từ gốc repo; thay 192.168.1.183 bằng IP LAN thật của máy chạy server
export CAROOT="$PWD/certs"
mkcert -cert-file certs/cert.pem -key-file certs/key.pem 127.0.0.1 localhost 192.168.1.183
```

Lệnh sinh ra `certs/cert.pem`, `certs/key.pem` và root CA `certs/rootCA.pem` (+ `rootCA-key.pem`).
Đổi IP LAN hoặc thêm hostname → chạy lại lệnh với danh sách mới. Cert hết hạn sau ~27 tháng (ghi ở đầu ra mkcert); sinh lại khi hết hạn.

### 3. Chạy server HTTPS

```bash
cd backend
NQ_HTTPS=1 NQ_PORT=8000 python -m app.main
```

- `NQ_HTTPS=1` → uvicorn nhận `ssl_certfile`/`ssl_keyfile` (mặc định `certs/cert.pem`, `certs/key.pem`; ghi đè bằng `NQ_CERTFILE`/`NQ_KEYFILE`).
- Cookie phiên `nq_session` tự gắn cờ `Secure` khi HTTPS (`secure=SETTINGS.https`), nên chỉ gửi qua TLS.
- Kiểm tra nhanh: `curl --cacert certs/rootCA.pem https://127.0.0.1:8000/` phải trả 200.

### 4. Cài trust root CA trên máy chạy server (tuỳ chọn)

```bash
mkcert -install
```

Lệnh này thêm root CA của mkcert vào trust store hệ thống để browser trên **máy này** tin cert không cảnh báo. Chỉ cần khi muốn browser cục bộ hết cảnh báo; test tự động đã verify thẳng bằng `certs/rootCA.pem` nên không bắt buộc.

### 5. Cài trust root CA trên điện thoại / desktop khác

Thiết bị khác phải tin **root CA của máy server** (`certs/rootCA.pem`), không phải CA mkcert cục bộ của chúng. Chép `certs/rootCA.pem` sang thiết bị rồi:

- **iOS / iPadOS:** gửi file (AirDrop/mail) → mở → *Settings → Profile Downloaded → Install*. Sau đó *Settings → General → About → Certificate Trust Settings* → bật full trust cho root CA vừa cài.
- **Android:** *Settings → Security → Encryption & credentials → Install a certificate → CA certificate* → chọn `rootCA.pem` (chấp nhận cảnh báo "network may be monitored"). Một số máy cần đặt tên file `.crt`.
- **Windows:** double-click `rootCA.pem` → *Install Certificate → Local Machine → Place all certificates in: Trusted Root Certification Authorities*. Hoặc `certmgr.msc` → import vào *Trusted Root Certification Authorities*.
- **macOS:** *Keychain Access* → kéo `rootCA.pem` vào keychain **System** → double-click → *Trust → Always Trust*.

Sau khi tin CA, mở `https://<IP-LAN>:8000` trên thiết bị — không còn cảnh báo chứng chỉ và cookie `Secure` hoạt động.

### Lưu ý an toàn

- `certs/` đã nằm trong `.gitignore`; giữ `rootCA-key.pem`/`key.pem` bí mật, không chia sẻ ngoài thiết bị cần tin.
- Đây là CA tự ký cho **mạng LAN nội bộ / nghiên cứu**, không phải chứng chỉ công cộng; không dùng cho dịch vụ Internet công khai.
- Gỡ trust khi thôi dùng: xoá profile/CA đã cài trên thiết bị, hoặc `mkcert -uninstall` trên máy đã chạy `-install`.