import json
import logging

from app.logging_config import JsonFormatter


def test_json_formatter_includes_extra_fields():
    record = logging.makeLogRecord(
        {"name": "app.tasks", "levelname": "INFO", "msg": "Price check %s", "args": ("done",)}
    )
    record.part_id = 7
    record.outcome = "saved"

    entry = json.loads(JsonFormatter().format(record))

    assert entry["message"] == "Price check done"
    assert entry["level"] == "INFO"
    assert entry["part_id"] == 7
    assert entry["outcome"] == "saved"
    assert "ts" in entry
