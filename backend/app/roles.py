from dataclasses import dataclass

ALL_TYPES = ["bars", "candles", "hollow", "columns", "line", "marked", "step", "area", "hlc", "baseline", "highlow", "ha"]
ALL_TFS = ["1m", "5m", "15m", "1h", "1D"]


@dataclass(frozen=True)
class RoleCaps:
    id: str
    label: str
    short: str
    controls: bool
    rail: str
    views: bool
    addSymbol: bool
    selectMode: bool
    sort: bool
    types: tuple
    tfs: tuple
    maxSpd: int
    ctl: dict
    acts: dict
    signals: str
    sigScope: str
    review: bool
    blind: bool
    sigCSV: bool
    forceFuture: bool
    dataManager: bool
    drawerEdit: bool
    png: bool
    csv: bool


ROLES = {
    "observer": RoleCaps(
        id="observer", label="Quan sát",
        short="Công chúng — xem lại phiên và tiêu đề tín hiệu mẫu. Chỉ đọc, không xuất dữ liệu.",
        controls=False, rail="ro", views=False, addSymbol=False, selectMode=False, sort=False,
        types=("line", "area", "candles"), tfs=("5m",), maxSpd=3,
        ctl={"speed": True, "follow": False, "loop": False, "rate": False, "tf": False, "density": False, "zoom": False, "vol": False,
             "ma1": False, "ma2": False, "maSteppers": False, "vwap": False, "grid": False, "cross": False, "future": False, "theme": False, "glow": False, "sound": False},
        acts={"reset": False, "random": False, "png": False, "csv": False, "full": False},
        signals="headlines", sigScope="symbol", review=False, blind=False, sigCSV=False,
        forceFuture=True, dataManager=False, drawerEdit=False, png=False, csv=False,
    ),
    "retail": RoleCaps(
        id="retail", label="NĐT cá nhân",
        short="Nhà đầu tư cá nhân — biểu đồ, watchlist và cảnh báo mẫu diễn giải dễ hiểu. Không phải khuyến nghị mua bán.",
        controls=True, rail="rw", views=True, addSymbol=True, selectMode=True, sort=True,
        types=("candles", "hollow", "line", "area", "baseline", "ha"), tfs=tuple(ALL_TFS), maxSpd=4,
        ctl={"speed": True, "follow": True, "loop": True, "rate": False, "tf": True, "density": False, "zoom": True, "vol": True,
             "ma1": True, "ma2": True, "maSteppers": False, "vwap": True, "grid": True, "cross": True, "future": True, "theme": True, "glow": False, "sound": True},
        acts={"reset": True, "random": True, "png": True, "csv": False, "full": True},
        signals="simple", sigScope="symbol", review=False, blind=False, sigCSV=False,
        forceFuture=False, dataManager=True, drawerEdit=True, png=True, csv=False,
    ),
    "institutional": RoleCaps(
        id="institutional", label="NĐT tổ chức & rủi ro",
        short="Tổ chức & quản trị rủi ro — điểm số, ngưỡng q98, phân rã lỗi theo feature và xuất CSV. Dữ liệu mô phỏng.",
        controls=True, rail="rw", views=True, addSymbol=True, selectMode=True, sort=True,
        types=tuple(ALL_TYPES), tfs=tuple(ALL_TFS), maxSpd=7,
        ctl={"speed": True, "follow": True, "loop": True, "rate": True, "tf": True, "density": True, "zoom": True, "vol": True,
             "ma1": True, "ma2": True, "maSteppers": True, "vwap": True, "grid": True, "cross": True, "future": True, "theme": True, "glow": True, "sound": True},
        acts={"reset": True, "random": True, "png": True, "csv": True, "full": True},
        signals="risk", sigScope="watch", review=False, blind=False, sigCSV=True,
        forceFuture=False, dataManager=True, drawerEdit=True, png=True, csv=True,
    ),
    "compliance": RoleCaps(
        id="compliance", label="Tuân thủ CTCK",
        short="Tuân thủ công ty chứng khoán — hàng đợi cảnh báo, nhãn rà soát, lý do chặn và outbox. Quy trình mô phỏng, khoá nhìn trước bắt buộc.",
        controls=True, rail="rw", views=True, addSymbol=True, selectMode=True, sort=True,
        types=("candles", "hollow", "bars", "line", "baseline"), tfs=tuple(ALL_TFS), maxSpd=4,
        ctl={"speed": True, "follow": True, "loop": True, "rate": False, "tf": True, "density": False, "zoom": True, "vol": True,
             "ma1": True, "ma2": True, "maSteppers": False, "vwap": True, "grid": True, "cross": True, "future": True, "theme": True, "glow": False, "sound": True},
        acts={"reset": True, "random": False, "png": True, "csv": True, "full": True},
        signals="queue", sigScope="watch", review=True, blind=True, sigCSV=True,
        forceFuture=True, dataManager=True, drawerEdit=True, png=True, csv=True,
    ),
    "regulator": RoleCaps(
        id="regulator", label="Giám sát sở/QLNN",
        short="Giám sát sở giao dịch / cơ quan quản lý — quét bất thường toàn bộ 50 mã, chất lượng nguồn và outbox. Mô phỏng, không phải giám sát thị trường thật.",
        controls=True, rail="rw", views=True, addSymbol=True, selectMode=True, sort=True,
        types=tuple(ALL_TYPES), tfs=tuple(ALL_TFS), maxSpd=7,
        ctl={"speed": True, "follow": True, "loop": True, "rate": True, "tf": True, "density": True, "zoom": True, "vol": True,
             "ma1": True, "ma2": True, "maSteppers": True, "vwap": True, "grid": True, "cross": True, "future": True, "theme": True, "glow": True, "sound": True},
        acts={"reset": True, "random": False, "png": True, "csv": True, "full": True},
        signals="surveillance", sigScope="all", review=False, blind=False, sigCSV=True,
        forceFuture=True, dataManager=True, drawerEdit=True, png=True, csv=True,
    ),
    "quant": RoleCaps(
        id="quant", label="Nghiên cứu/quant",
        short="Nghiên cứu / quant — toàn bộ công cụ, điểm số thô, phân rã error_/share_ và siêu dữ liệu mô hình trên dữ liệu mẫu.",
        controls=True, rail="rw", views=True, addSymbol=True, selectMode=True, sort=True,
        types=tuple(ALL_TYPES), tfs=tuple(ALL_TFS), maxSpd=7,
        ctl={"speed": True, "follow": True, "loop": True, "rate": True, "tf": True, "density": True, "zoom": True, "vol": True,
             "ma1": True, "ma2": True, "maSteppers": True, "vwap": True, "grid": True, "cross": True, "future": True, "theme": True, "glow": True, "sound": True},
        acts={"reset": True, "random": True, "png": True, "csv": True, "full": True},
        signals="research", sigScope="watch", review=False, blind=False, sigCSV=True,
        forceFuture=False, dataManager=True, drawerEdit=True, png=True, csv=True,
    ),
}

FORCE_FUTURE = {r.id for r in ROLES.values() if r.forceFuture}


def caps_for(user) -> RoleCaps:
    p = getattr(user, "prefs", None)
    role = p.role if p is not None else "retail"
    return ROLES.get(role, ROLES["retail"])