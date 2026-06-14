"""collect_training.py — 把 document_download/ 內有 # action: 的總結.md
同步到 doc_classifier/training_data/。

設計:
- 純 I/O,不打 LLM
- training_data/ 是「訓練資料永久家」:document_download/ 被使用者刪了,training_data/ 那份仍保留
- 來源較新就覆蓋(以 mtime 為準)

可獨立執行:
    py doc_classifier\\collect_training.py
"""
import re
import shutil
import sys
from pathlib import Path

_BASE_DIR = Path(__file__).parent.resolve()
_REPO_ROOT = _BASE_DIR.parent
DEFAULT_DOC_DOWNLOAD = _REPO_ROOT / "document_download"
DEFAULT_TRAINING = _BASE_DIR / "training_data"

# 行首允許前置空白,但 # action: 必須是該行第一個非空白 token (避免誤判內文)
_ACTION_LINE_RE = re.compile(r"^\s*#\s*action:\s*\S+", re.MULTILINE)


def _has_action_field(md_text: str) -> bool:
    """檢查 markdown 是否含有效的 `# action: <值>` 行。"""
    return bool(_ACTION_LINE_RE.search(md_text))


def sync(doc_download_root: Path = None, training_root: Path = None) -> dict:
    """把 doc_download_root 下所有 MW*/ 內的 `*總結*.md`(含 # action 欄位)
    複製到 training_root。回 stats dict。

    Args:
        doc_download_root: 預設 ../document_download (相對 doc_classifier/)
        training_root:     預設 training_data/

    Returns:
        {"added": N, "updated": N, "skipped_no_action": N, "orphan_kept": N}
    """
    src_root = Path(doc_download_root) if doc_download_root else DEFAULT_DOC_DOWNLOAD
    dst_root = Path(training_root) if training_root else DEFAULT_TRAINING
    dst_root.mkdir(parents=True, exist_ok=True)

    stats = {"added": 0, "updated": 0, "skipped_no_action": 0, "orphan_kept": 0}

    if not src_root.is_dir():
        # 源頭不存在,training_data/ 全是 orphan
        stats["orphan_kept"] = sum(1 for _ in dst_root.glob("*.md"))
        return stats

    src_all_names = set()  # 凡是被掃到的檔名都算(不管有沒 action)
    for mw_dir in sorted(src_root.iterdir()):
        if not mw_dir.is_dir():
            continue
        for md in mw_dir.glob("*總結*.md"):
            src_all_names.add(md.name)
            text = md.read_text(encoding="utf-8", errors="replace")
            if not _has_action_field(text):
                stats["skipped_no_action"] += 1
                continue
            dst = dst_root / md.name
            if not dst.exists():
                shutil.copy2(md, dst)
                stats["added"] += 1
            elif md.stat().st_mtime > dst.stat().st_mtime:
                shutil.copy2(md, dst)
                stats["updated"] += 1

    # 算 orphan:training_data 內,但 source 完全沒掃到的(source 被刪了)
    for existing in dst_root.glob("*.md"):
        if existing.name not in src_all_names:
            stats["orphan_kept"] += 1

    return stats


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    stats = sync()
    print(
        f"[collect_training] added={stats['added']} updated={stats['updated']} "
        f"orphan_kept={stats['orphan_kept']} skipped_no_action={stats['skipped_no_action']}"
    )


if __name__ == "__main__":
    main()
