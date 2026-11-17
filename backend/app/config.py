import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    host: str = os.environ.get("NQ_HOST", "0.0.0.0")
    port: int = int(os.environ.get("NQ_PORT", "8000"))
    db_path: Path = Path(os.environ.get("NQ_DB", str(ROOT / "data" / "nqreplay.db")))
    manifest_path: Path = ROOT / "tools" / "seed_manifest.json"
    cookie_name: str = "nq_session"
    session_days: int = 30
    login_rate: int = 5
    https: bool = False
    certfile: Path | None = None
    keyfile: Path | None = None


SETTINGS = Settings()