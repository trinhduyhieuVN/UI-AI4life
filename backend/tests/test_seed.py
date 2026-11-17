import json
from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[2] / "tools" / "seed_manifest.json"

EVENT_KEYS = {
    "id", "sym", "si", "type", "startIdx", "endIdx", "tStart", "tEnd",
    "windowStart", "segmentId", "score", "threshold", "alert", "reason",
    "label", "suppressed", "suppressedReason", "outbox", "quality",
    "model", "modelVersion", "features", "plain",
}


def test_manifest_shape():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(m["symbols"]) == 50
    assert len(m["sessions"]) == 11
    assert sum(len(v) for s in m["bars"].values() for v in s.values()) == 214500
    for evs in m["signals"].values():
        for e in evs:
            assert set(e) == EVENT_KEYS
            if e["type"] == "point":
                assert e["startIdx"] >= 1
            assert e["endIdx"] <= 389
    assert m["checksums"]["bars"] and m["checksums"]["signals"]