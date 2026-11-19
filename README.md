# Nasdaq Replay

Terminal phát lại phiên giao dịch Nasdaq theo thời gian nén, kèm cảnh báo bất thường **mô phỏng** — dựng lại từ artifact nghiên cứu HTML đơn trang thành ứng dụng self-host đa nền tảng (web + PWA cài được, đọc offline).

Backend **FastAPI + SQLite (WAL)**, frontend **vanilla JS / ES modules** (không bundler), renderer canvas giữ nguyên 12 loại biểu đồ HOSE. Một tiến trình phục vụ cả UI lẫn API, đồng bộ trong LAN, **không cloud, không telemetry**.

> ## ⚠️ DỮ LIỆU MẪU — không phải thị trường thật
> Toàn bộ nến và tín hiệu là **mẫu sinh tất định** từ hạt giống của artifact nghiên cứu, không phải dữ liệu sàn thật. Mọi cảnh báo gắn nhãn **DỮ LIỆU MẪU**. Đây là công cụ trình diễn / nghiên cứu UX phân vai:
> - **Không** phải hệ thống giám sát thị trường thật.
> - **Không** phải khuyến nghị mua bán / tư vấn đầu tư.
> - Quyền sử dụng dữ liệu thị trường thật (Databento…) chưa thu xếp — xem [Lộ trình](#lộ-trình).

## Tính năng chính

- **Kho dữ liệu mẫu:** 50 mã × 11 phiên ≈ **214.500 nến 1 phút** + sự kiện tín hiệu, nạp tất định từ `tools/seed_manifest.json` ngay lần chạy đầu.
- **Phát lại:** 12 loại biểu đồ (candles, hollow, bars, columns, line, marked, step, area, hlc, baseline, highlow, ha), 5 khung thời gian (1m/5m/15m/1h/1D), tốc độ tới **64×**, MA/VWAP, follow/loop, zoom/density.
- **6 vai trò phân quyền phía server** (không chỉ ẩn UI): mỗi vai trò một bộ năng lực, phạm vi tín hiệu và quyền xuất dữ liệu riêng — xem [bảng vai trò](#6-vai-trò).
- **Tín hiệu nhân quả (as-of):** chỉ dùng dữ liệu tới thời điểm hiện tại của phiên; kèm suppression / outbox / điểm chất lượng nguồn.
- **Quy trình tuân thủ:** hàng đợi cảnh báo, nhãn rà soát (review), lý do chặn, chế độ **blind** chống thiên kiến neo; vai trò giám sát/tuân thủ bị **khoá nhìn trước** (force-future) bắt buộc.
- **PWA:** cài được lên màn hình chính, **đọc offline** (read-only) qua service worker + IndexedDB; cần HTTPS (secure context) khi truy cập từ IP LAN.
- **Audit log**, **backup/restore v2**, và **migration** import toàn bộ tài khoản từ bản localStorage của artifact cũ (khớp theo username, rehash PBKDF2 → argon2id lười ở lần đăng nhập đầu — không reset mật khẩu, không mất dữ liệu).
- **Xuất dữ liệu phân quyền:** PNG / CSV / CSV tín hiệu tuỳ vai trò.
- **Bảo mật:** mật khẩu **argon2id**, cookie phiên `HttpOnly`/`SameSite=Lax`/`Secure` (khi HTTPS), hạn 30 ngày tuyệt đối, giới hạn đăng nhập **5 lần/phút/IP**.

## 6 vai trò

Năng lực enforced ở server (`backend/app/roles.py`, `RoleCaps`). Tóm tắt:

| Vai trò | Xem / làm gì | Xuất dữ liệu |
|---|---|---|
| **Quan sát** (`observer`) | Chỉ đọc: xem lại phiên + tiêu đề tín hiệu mẫu theo mã. Khoá nhìn trước. | Không |
| **NĐT cá nhân** (`retail`) | Biểu đồ, watchlist, cảnh báo mẫu diễn giải dễ hiểu. | PNG |
| **NĐT tổ chức & rủi ro** (`institutional`) | Điểm số, ngưỡng q98, phân rã lỗi theo feature; toàn bộ công cụ. | PNG + CSV + CSV tín hiệu |
| **Tuân thủ CTCK** (`compliance`) | Hàng đợi cảnh báo, nhãn rà soát, lý do chặn, outbox; blind + khoá nhìn trước. | PNG + CSV + CSV tín hiệu |
| **Giám sát sở/QLNN** (`regulator`) | Quét bất thường toàn bộ 50 mã, chất lượng nguồn, outbox; khoá nhìn trước. | PNG + CSV + CSV tín hiệu |
| **Nghiên cứu/quant** (`quant`) | Toàn bộ công cụ, điểm số thô, phân rã `error_`/`share_`, siêu dữ liệu mô hình. | PNG + CSV + CSV tín hiệu |

*Tín hiệu mẫu, không phải khuyến nghị mua bán.*

## Kiến trúc

```
nasdaq-replay/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI: mount API /api/v1 + StaticFiles "/" (UI)
│   │   ├── config.py        # biến môi trường NQ_* (host/port/db/https/cert)
│   │   ├── db.py            # SQLite WAL, session
│   │   ├── models.py        # SQLAlchemy: users, symbols, sessions, bars, signals…
│   │   ├── auth.py          # argon2id + verify legacy (PBKDF2/sha256), rate-limit
│   │   ├── roles.py         # RoleCaps: 6 vai trò, năng lực enforced server
│   │   ├── seed.py          # nạp seed_manifest.json + tài khoản demo lần đầu
│   │   ├── routers/         # auth, market, signals, prefs, views, watchlist,
│   │   │                    #   data (backup/restore/migration), export, reviews, audit
│   │   └── services/        # bars, signals (as-of), audit
│   ├── tests/               # 54 test (pytest + httpx TestClient)
│   └── pyproject.toml       # deps + requires-python >=3.11
├── frontend/
│   ├── index.html           # UI gốc (12 loại biểu đồ, rail phân vai)
│   ├── styles.css           # responsive: breakpoint ≤1400/1240/1060/820/520
│   ├── src/                 # ES modules: api.js (fetch same-origin), main.js, renderer…
│   ├── sw.js                # service worker (offline read-only)
│   ├── manifest.webmanifest # PWA
│   └── icons/
├── tools/
│   ├── seed_manifest.json   # seed tất định (committed; checksum đóng băng)
│   ├── seed_from_artifact.mjs  # sinh lại seed từ artifact gốc (Node ≥22)
│   ├── make_icons.mjs
│   └── legacy_vector.*      # vector kiểm thử tương thích hash cũ
├── docs/OPERATIONS.md       # vận hành: HTTPS/mkcert, seed, backup, migration, troubleshooting
├── data/                    # SQLite runtime (gitignore)
├── certs/                   # cert TLS tự ký (gitignore — không commit key)
└── pyproject.toml           # cấu hình pytest
```

**Một backend cho mỗi instance.** Frontend gọi API same-origin (`fetch('/api/v1' + path)`), không có cấu hình trỏ backend từ xa. Ai clone về chạy server của chính họ, với SQLite riêng (`data/nqreplay.db`, gitignore) được tự nạp seed + tài khoản demo. Không dùng chung backend, không lộ dữ liệu giữa các instance.

## Chạy nhanh

Yêu cầu: **Python ≥ 3.11** (đã kiểm chứng 3.11.9). Chạy server **không cần Node**.

```bash
# 1. Cài dependencies
python -m pip install --user fastapi "uvicorn[standard]" sqlalchemy argon2-cffi pydantic

# 2. Chạy server (HTTP)
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Mở **http://localhost:8000**. Lần chạy đầu lifespan tự nạp seed (50 mã × 11 phiên) và tạo tài khoản demo:

```
username: demo
password: demo1234
```

Đổi vai trò trong UI để xem năng lực từng nhóm. Muốn DB riêng (test/demo song song): đặt `NQ_DB=/đường/dẫn/khac.db` — seed tự nạp lại vào DB mới.

### HTTPS, mobile & PWA

- **Đăng nhập từ điện thoại/máy khác trong LAN chạy được qua HTTP** (cookie `Secure` chỉ bật khi HTTPS).
- **Cài PWA + đọc offline cần HTTPS** (secure context) khi truy cập bằng IP LAN; `localhost` HTTP vẫn là origin tin cậy.
- Sinh cert tự ký bằng **mkcert** + cài trust root CA trên từng thiết bị: xem **[docs/OPERATIONS.md](docs/OPERATIONS.md)** mục 3 (HTTPS) và mục PWA.

> `mkcert -install` (ghi vào trust store hệ thống) là thao tác của người dùng — không tự chạy trong script.

## Seed & dữ liệu

- `tools/seed_manifest.json` là seed **committed, checksum đóng băng**: nến sinh tất định từ RNG/genSymbol/genSignals của artifact gốc (Node V8). **Không** port các hàm siêu việt sang Python (V8 vs CPython không bit-identical).
- Sinh lại seed (chỉ khi cần, yêu cầu artifact gốc **không** phân phối kèm repo):
  ```bash
  node tools/seed_from_artifact.mjs   # Node ≥22; phải khớp manifest byte-for-byte
  ```
- Chi tiết seed / backup / restore / migration: [docs/OPERATIONS.md](docs/OPERATIONS.md).

## Kiểm thử

```bash
# từ gốc repo
python -m pytest backend/tests -q          # 54 test
```

Trên Windows nên thêm `--basetemp=.pytest-tmp` và đặt `PYTHONIOENCODING=utf-8`. Bộ test phủ auth/roles, seed, signals as-of, prefs clamp, backup/import/restore validation, export phân quyền, reviews/blind, audit.

## Quyền riêng tư & self-host

- **Không cloud, không telemetry, không gọi provider ngoài.** Mọi thứ chạy trên máy bạn.
- `certs/` (key TLS) và `*.db`/`-wal`/`-shm` (SQLite) đã **gitignore** — không đẩy lên remote.
- Repo public chỉ chứa mã nguồn + seed mẫu tất định, **không** chứa dữ liệu thị trường thật hay bí mật.
- Mỗi người clone về vận hành instance độc lập của riêng họ.

## Lộ trình

- **P1** — backend + DB + web parity: ✅ hoàn thành.
- **P2** — PWA / HTTPS / audit / backup-restore: ✅ hoàn thành.
- **P3** — wrapper native (Capacitor/Tauri) + dữ liệu thật (Databento…): **chưa mở**, chỉ thực hiện khi có yêu cầu rõ ràng và đã thu xếp quyền dữ liệu.

## Tài liệu

- **[docs/OPERATIONS.md](docs/OPERATIONS.md)** — hướng dẫn vận hành đầy đủ: cài đặt, chạy HTTP/HTTPS, mkcert + trust từng thiết bị, biến môi trường `NQ_*`, sinh lại seed, backup/restore, migration từ artifact cũ, troubleshooting.