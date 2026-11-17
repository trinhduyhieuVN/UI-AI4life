import json

from ..models import AuditLog


def log_audit(db, user_id, action: str, detail: dict | None = None) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            detail_json=json.dumps(detail or {}, ensure_ascii=False),
        )
    )