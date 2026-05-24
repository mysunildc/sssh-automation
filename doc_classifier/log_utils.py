"""log_utils.py — runs.log 結構化單行寫入 + 10MB rotate。

與 taipeion_login_selenium.py 的 _setup_stdout_logging() 設計不同:
那是 tee stdout (整個 process 的 print 都帶時戳);這裡是「結構化一行」
append 用 (不走 stdout 攔截),適合 runs.log 這種事件紀錄。
"""
import os
from datetime import datetime
from pathlib import Path

_MAX_BYTES = 10 * 1024 * 1024  # 10MB
_MAX_BACKUPS = 6


def _rotate_if_needed(log_path: Path) -> None:
    """檔案 >10MB 時 rotate:.6→丟,.5→.6,...,.1→.2,.log→.1。"""
    if not log_path.is_file():
        return
    if log_path.stat().st_size < _MAX_BYTES:
        return
    # 從尾巴往前推
    for i in range(_MAX_BACKUPS - 1, 0, -1):
        src = log_path.with_name(f"{log_path.name}.{i}")
        dst = log_path.with_name(f"{log_path.name}.{i + 1}")
        if src.exists():
            os.replace(src, dst)
    os.replace(log_path, log_path.with_name(f"{log_path.name}.1"))


def append_log(log_path: Path, line: str) -> None:
    """寫一行 log。自動加 ISO 8601 時戳前綴 + 結尾換行 + rotate 檢查。"""
    log_path = Path(log_path)
    _rotate_if_needed(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat(timespec="seconds")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"{ts} {line}\n")
