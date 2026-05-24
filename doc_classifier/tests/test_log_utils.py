"""log_utils 的單元測試:rotate 規則與 ISO 8601 時戳。"""
import re
from pathlib import Path
import pytest


def test_append_log_writes_iso_timestamp(tmp_path):
    from doc_classifier.log_utils import append_log
    log_path = tmp_path / "runs.log"
    append_log(log_path, "MW999 suggested=公告 confidence=高")
    text = log_path.read_text(encoding="utf-8")
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\s", text)
    assert "MW999 suggested=公告" in text


def test_append_log_multiple_lines(tmp_path):
    from doc_classifier.log_utils import append_log
    log_path = tmp_path / "runs.log"
    append_log(log_path, "first")
    append_log(log_path, "second")
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert "first" in lines[0]
    assert "second" in lines[1]


def test_rotate_when_log_exceeds_10mb(tmp_path):
    """超過 10MB 時 rotate,原檔變 .1。"""
    from doc_classifier.log_utils import append_log
    log_path = tmp_path / "runs.log"
    # 寫一個 >10MB 的 log
    log_path.write_text("x" * (10 * 1024 * 1024 + 100), encoding="utf-8")

    append_log(log_path, "new line after rotate")

    assert (tmp_path / "runs.log.1").exists()
    new_text = log_path.read_text(encoding="utf-8")
    assert "new line after rotate" in new_text
    assert "x" * 1000 not in new_text  # 新檔不該含舊內容


def test_rotate_chain_max_6_backups(tmp_path):
    """rotate 連鎖最多保留 .1 ~ .6。"""
    from doc_classifier.log_utils import append_log
    log_path = tmp_path / "runs.log"
    # 預備 .1 ~ .6 都已存在
    for i in range(1, 7):
        (tmp_path / f"runs.log.{i}").write_text(f"old{i}", encoding="utf-8")
    log_path.write_text("y" * (10 * 1024 * 1024 + 100), encoding="utf-8")

    append_log(log_path, "trigger rotate")

    # .1 應變成「上一次 .log 內容(y...)」, 原 .1 變 .2 ... 原 .6 被丟掉
    for i in range(1, 7):
        assert (tmp_path / f"runs.log.{i}").exists()
    assert not (tmp_path / "runs.log.7").exists()
