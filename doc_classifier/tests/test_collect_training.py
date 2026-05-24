"""collect_training.sync() 的單元測試。"""
import time
from pathlib import Path
import pytest


def test_sync_copies_only_files_with_action(fake_doc_download, fake_training_dir):
    """有 # action: 的 .md 才複製;沒 # action: 的不複製。"""
    from doc_classifier.collect_training import sync

    stats = sync(doc_download_root=fake_doc_download, training_root=fake_training_dir)

    assert (fake_training_dir / "1140001_001A總結.claude-opus-4-7.md").exists()
    assert (fake_training_dir / "1140002_001A總結.claude-opus-4-7.md").exists()
    assert not (fake_training_dir / "1140003_001A總結.claude-opus-4-7.md").exists()
    assert stats["added"] == 2
    assert stats["updated"] == 0
    assert stats["orphan_kept"] == 0


def test_sync_overwrites_when_source_newer(fake_doc_download, fake_training_dir):
    """document_download/ 較新 → 覆蓋 training_data/。"""
    from doc_classifier.collect_training import sync

    sync(doc_download_root=fake_doc_download, training_root=fake_training_dir)

    # 改 document_download 那份內容,並把 mtime 推到未來
    src = fake_doc_download / "MW001" / "1140001_001A總結.claude-opus-4-7.md"
    src.write_text("# action: 轉發\n\n主旨:改過了\n", encoding="utf-8")
    future = time.time() + 100
    import os
    os.utime(src, (future, future))

    stats = sync(doc_download_root=fake_doc_download, training_root=fake_training_dir)

    target = fake_training_dir / "1140001_001A總結.claude-opus-4-7.md"
    assert "# action: 轉發" in target.read_text(encoding="utf-8")
    assert stats["updated"] == 1


def test_sync_keeps_orphan_when_source_deleted(fake_doc_download, fake_training_dir):
    """training_data/ 有、document_download/ 已刪 → 保留不動。"""
    from doc_classifier.collect_training import sync

    sync(doc_download_root=fake_doc_download, training_root=fake_training_dir)
    # 刪掉 document_download MW001
    import shutil
    shutil.rmtree(fake_doc_download / "MW001")

    stats = sync(doc_download_root=fake_doc_download, training_root=fake_training_dir)

    assert (fake_training_dir / "1140001_001A總結.claude-opus-4-7.md").exists()
    assert stats["orphan_kept"] == 1


def test_sync_action_must_be_at_line_start(tmp_path):
    """# action: 必須是一整行,不能是「說明中提到 # action: ...」這種誤判。"""
    from doc_classifier.collect_training import sync

    root = tmp_path / "document_download"
    root.mkdir()
    (root / "MW999").mkdir()
    (root / "MW999" / "x總結.md").write_text(
        "主旨:本案需先 # action: 確認再簽\n",  # 行中段 # action:,不是欄位
        encoding="utf-8",
    )
    training = tmp_path / "training_data"
    training.mkdir()

    stats = sync(doc_download_root=root, training_root=training)
    assert stats["added"] == 0


def test_sync_action_removed_not_counted_as_orphan(fake_doc_download, fake_training_dir):
    """source 仍存在但使用者拿掉 # action: 後重跑 → 不該算成 orphan_kept。"""
    from doc_classifier.collect_training import sync

    # 第一次:複製進去
    sync(doc_download_root=fake_doc_download, training_root=fake_training_dir)
    assert (fake_training_dir / "1140001_001A總結.claude-opus-4-7.md").exists()

    # 把 source 的 # action 拿掉 (source 還在,只是不再有 action 標記)
    src = fake_doc_download / "MW001" / "1140001_001A總結.claude-opus-4-7.md"
    src.write_text("發文日期:2026-05-20\n主旨:辦理校園資安宣導\n", encoding="utf-8")

    stats = sync(doc_download_root=fake_doc_download, training_root=fake_training_dir)

    # source 還在,只是失去 action 標記 → 算 skipped_no_action,不算 orphan
    assert stats["skipped_no_action"] == 2  # MW001 (剛拿掉的) + MW003 (本來就沒 action)
    assert stats["orphan_kept"] == 0  # 沒有真正的孤兒 (source 都還在)
