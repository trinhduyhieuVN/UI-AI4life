# Vận hành Nasdaq Replay

Ứng dụng self-host: FastAPI + SQLite (WAL) phục vụ frontend vanilla JS/PWA tại `/`. Dữ liệu thị trường là **mẫu sinh tất định** từ hạt giống của artifact nghiên cứu — không phải dữ liệu sàn thật; mọi tín hiệu cảnh báo gắn nhãn DỮ LIỆU MẪU.

## 1. Yêu cầu & cài đặt

- Python ≥ 3.11 (đã kiểm chứng 3.11.9). Dependencies: `fastapi`, `uvicorn`, `websockets>=14`, `sqlalchemy`, `argon2-cffi`:

```bash
python -m pip install --user fastapi uvicorn "websockets>=14" sqlalchemy argon2-cffi
```

- Node ≥ 22 chỉ cần khi **sinh lại seed** (mục 4); chạy server không cần Node.
- Tùy chọn: `mkcert` cho HTTPS LAN (mục 3).

## 2. Chạy server

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000     # HTTP
# hoặc HTTPS (mục 3):
NQ_HTTPS=1 python -m app.main
```

Mở `http://localhost:8000` (hoặc `https://<IP-LAN>:8000` khi bật TLS). Lần chạy đầu tiên lifespan tự nạp seed từ `tools/seed_manifest.json` vào SQLite (50 mã × 11 phiên, ~214k nến 1m + sự kiện tín hiệu) và tạo tài khoản demo **`demo` / `demo1234`** (cờ `is_demo`).

Biến môi trường (đọc trong `backend/app/config.py`):

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `NQ_HOST` | `0.0.0.0` | Địa chỉ bind |
| `NQ_PORT` | `8000` | Cổng |
| `NQ_DB` | `<repo>/data/nqreplay.db` | File SQLite (WAL: thêm `-wal`, `-shm`) |
| `NQ_HTTPS` | tắt | `1` → uvicorn nhận `ssl_certfile`/`ssl_keyfile` |
| `NQ_CERTFILE` | `<repo>/certs/cert.pem` | Chứng chỉ TLS |
| `NQ_KEYFILE` | `<repo>/certs/key.pem` | Khoá TLS |

- Cookie phiên `nq_session`: hạn **30 ngày tuyệt đối**, `HttpOnly`, `SameSite=Lax`, tự gắn `Secure` khi `NQ_HTTPS=1`.
- Đăng nhập giới hạn **5 lần/phút/IP** (429 khi vượt).
- Muốn DB riêng (test/demo song song): `NQ_DB=/đường/dẫn/khac.db` — seed tự nạp lại vào DB mới.
- Dừng server: Ctrl+C. SQLite WAL an toàn khi tắt đột ngột; không xoá `-wal`/`-shm` khi server đang chạy.

## 3. HTTPS tự ký (mkcert) & cookie Secure

Mặc định server chạy HTTP ở `0.0.0.0:8000`. Để bật HTTPS (bắt buộc khi truy cập từ điện thoại/máy khác trong LAN, vì cookie phiên chỉ gửi qua kết nối an toàn khi `Secure`):

### 3.1. Cài mkcert

- Windows: `winget install --id FiloSottile.mkcert -e`
- macOS: `brew install mkcert`
- Linux: `sudo apt install mkcert` (hoặc tải binary từ GitHub releases)

### 3.2. Sinh chứng chỉ cho localhost + IP LAN

Đặt `CAROOT` trỏ vào thư mục `certs/` của repo để root CA nằm cùng chỗ với cert (thư mục này đã gitignore — **không commit key**):

```bash
# từ gốc repo; thay 192.168.1.183 bằng IP LAN thật của máy chạy server
export CAROOT="$PWD/certs"
mkcert -cert-file certs/cert.pem -key-file certs/key.pem 127.0.0.1 localhost 192.168.1.183
```

Lệnh sinh ra `certs/cert.pem`, `certs/key.pem` và root CA `certs/rootCA.pem` (+ `rootCA-key.pem`).
Đổi IP LAN hoặc thêm hostname → chạy lại lệnh với danh sách mới. Cert hết hạn sau ~27 tháng (ghi ở đầu ra mkcert); sinh lại khi hết hạn.

### 3.3. Chạy server HTTPS

```bash
cd backend
NQ_HTTPS=1 NQ_PORT=8000 python -m app.main
```

- `NQ_HTTPS=1` → uvicorn nhận `ssl_certfile`/`ssl_keyfile` (mặc định `certs/cert.pem`, `certs/key.pem`; ghi đè bằng `NQ_CERTFILE`/`NQ_KEYFILE`).
- Cookie phiên `nq_session` tự gắn cờ `Secure` khi HTTPS (`secure=SETTINGS.https`), nên chỉ gửi qua TLS.
- Kiểm tra nhanh: `curl --cacert certs/rootCA.pem https://127.0.0.1:8000/` phải trả 200.

### 3.4. Cài trust root CA trên máy chạy server (tuỳ chọn)

```bash
mkcert -install
```

Lệnh này thêm root CA của mkcert vào trust store hệ thống để browser trên **máy này** tin cert không cảnh báo. Chỉ cần khi muốn browser cục bộ hết cảnh báo; test tự động đã verify thẳng bằng `certs/rootCA.pem` nên không bắt buộc.

### 3.5. Cài trust root CA trên điện thoại / desktop khác

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

## 4. Sinh lại seed (dữ liệu mẫu)

Seed được trích **một lần** từ chính artifact HTML bằng Node, giữ nguyên từng byte chuỗi giá:

```bash
node tools/seed_from_artifact.mjs [đường-dẫn-artifact.html]
```

- Không tham số → dùng đường dẫn artifact mặc định trong tool. Tool cắt cửa sổ `/* ---------- deterministic RNG` … `function sigCursorMinute` của artifact, chạy `genSymbol`/`genSignals` cho 50 mã × 11 phiên, ghi `tools/seed_manifest.json` (symbols/sessions/bars/stats/signals + checksums sha256 của bars và signals).
- In checksums ra stdout; so với checksum cũ để biết dữ liệu có đổi không.
- **Nạp vào DB mới:** xoá (hoặc đổi tên) `data/nqreplay.db*` rồi khởi động server — lifespan nạp manifest khi DB trống. DB đang chạy không tự nạp lại.
- **Sau khi đổi seed:** tăng tên cache trong `frontend/sw.js` (`CACHE='nq-v1'` → `'nq-v2'`) để service worker purge cache cũ; nếu không, trình duyệt còn cache sẽ đọc bars/signals cũ (cache-first cho 4 endpoint bất biến `/symbols,/sessions,/bars,/signals`).
- Seed là dữ liệu nghiên cứu cục bộ; không gọi API thị trường thật ở bất kỳ bước nào.

## 5. Backup / restore (server, v2)

Trong app: menu tài khoản → **Quản lý dữ liệu** (vai trò có quyền `dataManager`: retail/institutional/compliance/regulator/quant).

- **Tải backup JSON** → `GET /api/v1/data/backup` → file `nasdaq-replay-backup-YYYY-MM-DD.json`. Định dạng v2: `{app:"nasdaq-replay", version:2, exportedAt, users:[{username,email,prefs,watchlist,views,reviews}]}` — **chỉ dữ liệu, không kèm mật khẩu/hash**.
- **Khôi phục từ file…** → `POST /api/v1/data/restore`: tìm mục trùng tên tài khoản đang đăng nhập (không có → 422), **ghi đè** prefs/watchlist/views/reviews của tài khoản đó bằng mục trong file.
  - Vai trò lạ trong file → fallback `retail`; mã không tồn tại trong seed bị bỏ qua.
  - Vai trò khoá nhìn trước (compliance/regulator) luôn bị ép `future=true` bất kể file ghi gì.
  - Đổi vai trò do restore được ghi audit `role_change (via restore)`; bản thân lượt restore ghi `restore_backup` kèm số lượng.
  - Sau restore UI tự nạp lại `/me`, series (nếu đổi khung thời gian) và đồng bộ transport — không mất vị trí phiên phát.
- File hỏng/không phải JSON → 422 "File không phải JSON hợp lệ"; sai `app`/`version` → 422 "Không phải backup v2 của ứng dụng này".
- Backup thủ công kiểu SQLite: chép `data/nqreplay.db` khi server đã dừng (hoặc dùng `sqlite3 .backup` khi đang chạy) — cách này giữ cả mật khẩu, chỉ dùng nội bộ.

## 6. Migration dữ liệu cục bộ cũ (artifact một file)

Artifact cũ lưu mọi thứ trong `localStorage['nqreplay.v1']` của trình duyệt. Đưa lên server:

1. Mở app mới ** trên cùng trình duyệt** còn dữ liệu cũ, đăng nhập (tài khoản trùng tên sẽ được gộp).
2. Menu tài khoản → Quản lý dữ liệu → **Đưa dữ liệu cục bộ lên server** → `POST /api/v1/data/import-backup`.
3. Server nhận mọi tài khoản trong pack: trùng username → gộp watchlist/views/reviews; chưa có → tạo mới với hash legacy.
4. Mật khẩu PBKDF2 cũ được **nâng cấp dần lên argon2id** ở lần đăng nhập thành công kế tiếp (lazy rehash); import không bao giờ hạ hash argon2id xuống legacy.
5. Idempotent theo checksum từng tài khoản (`ImportRecord`): import lại cùng file → `imported 0, skipped N`.
6. Nút **Quản lý dữ liệu & sao lưu** ở màn auth chỉ là lối thoát thông tin (dữ liệu nằm đâu, vào đâu để quản lý) — mọi thao tác dữ liệu thật đều yêu cầu đăng nhập + quyền.

## 7. PWA / offline

- Cài đặt: browser hiện nút cài (manifest + icons + service worker). Android/Chrome: menu → *Install app*; iOS Safari: *Share → Add to Home Screen*.
- Offline: banner amber "Ngoại tuyến…" hiện trên đầu app; **chỉ xem lại** — mọi thao tác ghi bị chặn ở tầng API với toast "Ngoại tuyến — chỉ xem lại, không lưu được thay đổi."
- Dữ liệu offline: nến + tín hiệu của các mã/phiên đã mở được lưu trong IndexedDB (`nq-offline`); khung thời gian khác khung đã lưu → báo thiếu dữ liệu. Mở app lạnh khi offline vẫn ở màn auth (cookie không xác minh được offline).
- Có mạng lại: banner tự ẩn, app tự đồng bộ `/me` (server thắng), giữ nguyên mã/phiên/con trỏ đang xem.
- Service worker: cache-first chỉ cho 4 endpoint seed bất biến (`/symbols,/sessions,/bars,/signals`); `/auth,/prefs,/watchlist,/views,/reviews` luôn đi mạng — không bao giờ phục vụ session/caps cũ.

## 8. Cổng & bảng tra lỗi

Đổi cổng: `NQ_PORT=8001` (cả server lẫn URL). Cổng bận: `netstat -ano | grep :8000` tìm PID chiếm.

| Triệu chứng | Nguyên nhân | Xử lý |
|---|---|---|
| 401 mọi API | Chưa đăng nhập / phiên 30 ngày hết hạn | Đăng nhập lại; giữa phiên phát app tự lưu vị trí và quay về màn auth, đăng nhập xong tiếp tục |
| 403 kèm `cap` | Vai trò không có quyền (`rail_rw`, `views`, `csv`, `sigCSV`, `review`, `scope_all`, `audit`, `dataManager`, `png`, `blind`, `scope_watch`) | Đổi vai trò phù hợp (menu tài khoản → Đổi vai trò); server luôn chặn kể cả khi UI bị vượt qua |
| 409 khi đăng ký | Trùng username | Chọn tên khác |
| 409 `forceFuture` khi PUT prefs | Vai trò compliance/regulator bắt buộc khoá nhìn trước | Không tắt được — đúng thiết kế audit |
| 422 backup/restore | File không phải JSON / không phải v2 / thiếu tài khoản hiện tại | Xem mục 5 |
| 422 signals | `tf`/`scope` ngoài phạm vi vai trò hoặc cursor sai | UI đúng vai trò không gửi tham số này |
| 429 đăng nhập | >5 lần/phút/IP | Chờ 1 phút |
| Toast "Ngoại tuyến — chỉ xem lại…" | Mất mạng, chế độ read-only | Khôi phục mạng; app tự đồng bộ lại |
| Cảnh báo chứng chỉ trên thiết bị LAN | Thiết bị chưa tin root CA | Mục 3.5 |
| Cookie không gửi trên LAN | Đang chạy HTTP, cookie `Secure` chỉ đi TLS | Bật `NQ_HTTPS=1` (mục 3) |
| Dữ liệu offline cũ sau khi đổi seed | SW cache-first chưa purge | Tăng `CACHE` trong `sw.js` (mục 4) |
| Server không lên | Thiếu deps / sai cổng / thiếu cert khi `NQ_HTTPS=1` | Xem traceback uvicorn; `python -m pip install --user …` mục 1 |

## 9. Kiểm chứng

```bash
# từ gốc repo — 51 test backend (auth/roles/prefs/market/signals/reviews/audit/data/https)
PYTHONIOENCODING=utf-8 python -m pytest backend/tests --basetemp=.pytest-tmp -q
```

- `test_https` tự skip khi thiếu cert hoặc cổng 8000 bận — chạy lại khi rảnh cổng để đủ 51.
- Gate UI đầy đủ (P1+P2, 136 checks: vai trò, tín hiệu, export, offline, PWA, audit/backup/restore, mobile) chạy bằng probe CDP riêng trong `%TEMP%/nq-test/probe9.js` (không nằm trong repo): `node probe9.js` cho HTTP; `NQ_PROBE_HTTPS=1 NQ_PROBE_HOST=localhost node probe9.js` và `NQ_PROBE_HOST=<IP-LAN>` cho HTTPS (Chrome tin cert qua SPKI pin, không đụng trust store hệ thống).

## Phát lại dữ liệu MBO lịch sử

Đăng nhập ở trang chủ Nasdaq Replay. Chọn mã trong watchlist, chọn ngày và nhấn **Phát** hoặc kéo thanh thời gian. Đồng hồ dùng giờ New York. Bảng tín hiệu hiển thị năng lượng DHGNN + EBM tại cuối nến đang phát, ngưỡng cảnh báo và các phút đã vượt ngưỡng của mã đang xem. Dữ liệu mẫu vẫn truy cập được qua `/?mode=sample`.

Để tạo hoặc cập nhật kho lịch sử, chạy từ thư mục gốc dự án bằng Python 3.11+ có NumPy, pandas và bộ đọc Zstandard (Python 3.14 có sẵn; ở bản cũ cài thêm `zstandard`).

```powershell
python tools/import_historical.py --data "D:/DATA_AI4LIFE" --model-results "../msft_month_baseline/global8"
```

Trình nhập kiểm tra SHA-256 của MBO, tổng hợp OHLC và khối lượng từ giao dịch trong từng phút, đối chiếu tổng khối lượng với kết quả tiền xử lý và ghép theo thời điểm kết thúc phút. Phút không có giao dịch có khối lượng bằng 0 và giá trống. Năng lượng và ngưỡng được lấy từ kết quả phiên quan sát của checkpoint 8 mã. Tệp SQLite cục bộ `data/historical.db` được thay sau khi kiểm tra thành công toàn bộ lần nhập. Ứng dụng nạp trước nến giá của phiên để hỗ trợ tua. Điểm mô hình được yêu cầu đến mốc đang phát. Khi tua ngược, bảng tín hiệu và dấu trên biểu đồ chỉ hiển thị các phút đã đi qua.
