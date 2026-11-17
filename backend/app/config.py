from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    host: str = "0.0.0.0"
    port: int = 8000
    db_path: Path = ROOT / "data" / "nqreplay.db"
    manifest_path: Path = ROOT / "tools" / "seed_manifest.json"
    cookie_name: str = "nq_session"
    session_days: int = 30
    login_rate: int = 5
    https: bool = False
    certfile: Path | None = None
    keyfile: Path | None = None


SETTINGS = Settings()