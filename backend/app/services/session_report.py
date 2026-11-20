"""Explain the observed intraday score path once a complete replay session closes."""
from datetime import date, datetime
from statistics import median
from zoneinfo import ZoneInfo

SYMBOLS = ("AAPL", "MSFT", "INTC", "CSCO", "CMCSA", "FOXA", "DISCA", "VIAC")


def time_et(ms):
    return datetime.fromtimestamp(ms / 1000, ZoneInfo("America/New_York")).strftime("%H:%M")


def make_report(db, day):
    sessions = list(db.execute("SELECT symbol, minutes, open_ms FROM sessions WHERE day=?", (day,)))
    sessions = [s for s in sessions if s["symbol"] in SYMBOLS]
    if len(sessions) != len(SYMBOLS) or len({(s["minutes"], s["open_ms"]) for s in sessions}) != 1:
        raise ValueError("Phiên chưa đủ dữ liệu cho tám mã.")
    minutes = sessions[0]["minutes"]
    alerts = []
    counts = {}
    for symbol in SYMBOLS:
        rows = list(db.execute("SELECT * FROM points WHERE symbol=? AND day=? ORDER BY minute", (symbol, day)))
        if minutes < 1 or [r["minute"] for r in rows] != list(range(1, minutes + 1)):
            raise ValueError("Thiếu điểm theo phút cho " + symbol)
        counts[symbol] = 0
        run = []
        for r in rows:
            if r["energy"] is None or r["threshold"] is None:
                raise ValueError("Thiếu điểm hoặc ngưỡng cho " + symbol)
            if r["energy"] > r["threshold"]:
                if not run:
                    alerts.append((symbol, run))
                    counts[symbol] += 1
                run.append(r)
            else:
                run = []

    def margin(r):
        return r["energy"] - r["threshold"]

    alerts.sort(key=lambda pair: max(map(margin, pair[1])), reverse=True)
    day_label = date.fromisoformat(day).strftime("%d/%m/%Y")
    opening = sessions[0]["open_ms"]
    hours = f"{time_et(opening)}–{time_et(opening + minutes * 60000)}"
    subject = f"[NevAI · Phát lại] Tổng kết phiên {day_label} | {len(alerts)} đợt bất thường"
    lines = [f"NevAI đã theo dõi 8 mã trong phiên {day_label}, {hours} giờ New York, trên dữ liệu Nasdaq lịch sử.",
             f"Mô hình ghi nhận {len(alerts)} đợt vượt ngưỡng ở {sum(v > 0 for v in counts.values())}/8 mã. "
             "Các phút vượt ngưỡng liên tiếp của cùng một mã được tính là một đợt.",
             "Số đợt theo mã\n" + "  ·  ".join(f"{s} {counts[s]}" for s in SYMBOLS)]
    if alerts:
        lines.append(f"{min(3, len(alerts))} đợt có mức vượt ngưỡng lớn nhất")
    for symbol, run in alerts[:3]:
        first, last = run[0], run[-1]
        peak = max(run, key=margin)
        volume = sum(r["volume"] for r in run)
        text = (f"{symbol} | {time_et(first['end_ms'] - 60000)}–{time_et(last['end_ms'])} | {len(run)} phút\n"
                f"Lúc {time_et(peak['end_ms'])}, điểm EBM đạt {peak['energy']:.4f}, cao hơn ngưỡng "
                f"{peak['threshold']:.4f} tại thời điểm đó {margin(peak):.4f} điểm. ")
        trades = [r for r in run if r["open"] is not None and r["close"] is not None]
        if trades:
            text += f"Giá khớp đầu và cuối khoảng lần lượt là {trades[0]['open']:.2f} và {trades[-1]['close']:.2f} USD. "
        text += f"Khối lượng khớp trên Nasdaq trong khoảng này là {volume:,} cổ phiếu."
        samples = [r[0] for r in db.execute("""
            SELECT SUM(volume) FROM points WHERE symbol=? AND day<? AND minute BETWEEN ? AND ?
            GROUP BY day HAVING COUNT(*)=? ORDER BY day DESC LIMIT 20
        """, (symbol, day, first["minute"], last["minute"], len(run)))]
        if len(samples) >= 3 and median(samples) > 0:
            text += (f" Con số này bằng {volume / median(samples):.2f} lần trung vị của cùng mã, "
                     f"cùng khung giờ trong {len(samples)} phiên trước có dữ liệu.")
        lines.append(text)
    lines.append("Điểm EBM phản ánh mức độ khác thường của giao dịch đã quan sát từ đầu phiên. "
                 "Giá và khối lượng mô tả diễn biến đi kèm. Việc xác định thao túng cần thêm bằng chứng.")
    return {"day": day, "source": "replay", "subject": subject, "body": "\n\n".join(lines), "counts": counts}
