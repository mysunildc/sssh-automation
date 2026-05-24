"""CLI 入口測試:argparse 行為與 sync 觸發。"""
import subprocess
import sys
from pathlib import Path


def test_help_does_not_crash():
    result = subprocess.run(
        [sys.executable, "-m", "doc_classifier.classifier", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=Path(__file__).resolve().parents[2],  # repo root
    )
    assert result.returncode == 0
    assert "usage" in result.stdout.lower() or "用法" in result.stdout


def test_classify_runs_sync_before_classification(monkeypatch, tmp_path):
    """classify_dir 被呼叫前,sync 必須先跑過。"""
    from doc_classifier import classifier
    from doc_classifier import collect_training

    call_order = []
    monkeypatch.setattr(
        collect_training, "sync",
        lambda **kw: (call_order.append("sync"), {"added": 0, "updated": 0, "orphan_kept": 0, "skipped_no_action": 0})[1],
    )

    # mw_dir 隨便弄一個有 *總結*.md 的
    mw = tmp_path / "MW1"
    mw.mkdir()
    (mw / "x總結.md").write_text("# suggested_action: 公告 (信心:高)\n", encoding="utf-8")
    # actions yaml
    ay = tmp_path / "actions.yaml"
    ay.write_text("actions:\n  - 公告\n", encoding="utf-8")
    spec = tmp_path / "classifier.md"
    spec.write_text("# 規格\n", encoding="utf-8")
    training = tmp_path / "training_data"
    training.mkdir()

    classifier.run_one(
        mw_dir=mw,
        actions_yaml=ay,
        spec_md=spec,
        training_root=training,
        runs_log=tmp_path / "runs.log",
        force=False,
        do_sync=True,
    )
    assert "sync" in call_order
