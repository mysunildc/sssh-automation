"""classify_dir() 整合測試:用 monkeypatch 注入假 LLM 回應跑全流程。"""
from pathlib import Path
import pytest


@pytest.fixture
def stage(tmp_path, monkeypatch):
    """準備一個 doc_classifier 的最小執行環境:
       - actions.yaml (含「公告」「存查」)
       - classifier.md (簡化版)
       - training_data/ (含 1 份已標 # action: 公告)
       - 目標 MW999 目錄(僅 1 份待分類)
    """
    # actions.yaml
    actions_yaml = tmp_path / "actions.yaml"
    actions_yaml.write_text("actions:\n  - 公告\n  - 存查\n", encoding="utf-8")
    # classifier.md
    spec_md = tmp_path / "classifier.md"
    spec_md.write_text("# 規格\n依範例分類。\n", encoding="utf-8")
    # training_data
    training = tmp_path / "training_data"
    training.mkdir()
    (training / "1140001總結.md").write_text(
        "# action: 公告\n主旨:資安宣導\n", encoding="utf-8"
    )
    # 目標
    mw999 = tmp_path / "document_download" / "MW999"
    mw999.mkdir(parents=True)
    target_md = mw999 / "1140999總結.md"
    target_md.write_text("主旨:校園資安宣導活動\n", encoding="utf-8")
    # runs.log
    runs_log = tmp_path / "runs.log"

    return {
        "mw_dir": mw999,
        "target_md": target_md,
        "actions_yaml": actions_yaml,
        "spec_md": spec_md,
        "training": training,
        "runs_log": runs_log,
    }


def test_classify_dir_writes_suggestion_back(stage, monkeypatch):
    from doc_classifier import classifier
    fake_response = (
        "# suggested_action: 公告 (信心:高)\n"
        "# cited_examples: 1140001\n"
        "與範例皆為資安主題。\n"
    )
    monkeypatch.setattr(classifier, "_call_llm", lambda prompt: fake_response)

    result = classifier.classify_dir(
        mw_dir=stage["mw_dir"],
        actions_yaml=stage["actions_yaml"],
        spec_md=stage["spec_md"],
        training_root=stage["training"],
        runs_log=stage["runs_log"],
    )

    assert result["status"] == "ok"
    written = stage["target_md"].read_text(encoding="utf-8")
    assert written.startswith("# suggested_action: 公告 (信心:高)")
    assert "# cited_examples: 1140001" in written
    assert "校園資安宣導活動" in written  # 原內容保留
    assert "公告" in stage["runs_log"].read_text(encoding="utf-8")


def test_classify_dir_skip_when_no_training_data(stage, monkeypatch, tmp_path):
    from doc_classifier import classifier
    # 清空 training_data
    for f in stage["training"].iterdir():
        f.unlink()
    monkeypatch.setattr(
        classifier, "_call_llm",
        lambda p: pytest.fail("training 空時不該打 LLM"),
    )

    result = classifier.classify_dir(
        mw_dir=stage["mw_dir"],
        actions_yaml=stage["actions_yaml"],
        spec_md=stage["spec_md"],
        training_root=stage["training"],
        runs_log=stage["runs_log"],
    )

    assert result["status"] == "skip"
    # 不寫回
    assert "suggested_action" not in stage["target_md"].read_text(encoding="utf-8")
    assert "SKIP" in stage["runs_log"].read_text(encoding="utf-8")


def test_classify_dir_skips_if_already_classified(stage, monkeypatch):
    from doc_classifier import classifier
    stage["target_md"].write_text(
        "# suggested_action: 存查 (信心:中)\n# cited_examples: \n之前跑過了\n主旨:x\n",
        encoding="utf-8",
    )
    called = {"v": False}

    def _no_call(p):
        called["v"] = True
        return ""

    monkeypatch.setattr(classifier, "_call_llm", _no_call)

    result = classifier.classify_dir(
        mw_dir=stage["mw_dir"],
        actions_yaml=stage["actions_yaml"],
        spec_md=stage["spec_md"],
        training_root=stage["training"],
        runs_log=stage["runs_log"],
        force=False,
    )

    assert result["status"] == "already_classified"
    assert called["v"] is False


def test_classify_dir_force_overwrites(stage, monkeypatch):
    from doc_classifier import classifier
    stage["target_md"].write_text(
        "# suggested_action: 存查 (信心:中)\n# cited_examples: \n舊建議\n主旨:x\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        classifier, "_call_llm",
        lambda p: (
            "# suggested_action: 公告 (信心:高)\n"
            "# cited_examples: 1140001\n"
            "新建議。\n"
        ),
    )

    result = classifier.classify_dir(
        mw_dir=stage["mw_dir"],
        actions_yaml=stage["actions_yaml"],
        spec_md=stage["spec_md"],
        training_root=stage["training"],
        runs_log=stage["runs_log"],
        force=True,
    )

    assert result["status"] == "ok"
    text = stage["target_md"].read_text(encoding="utf-8")
    assert text.startswith("# suggested_action: 公告 (信心:高)")
    # 舊「存查」建議行不該還在
    assert text.count("# suggested_action:") == 1


def test_classify_dir_rejects_action_not_in_yaml(stage, monkeypatch):
    from doc_classifier import classifier
    monkeypatch.setattr(
        classifier, "_call_llm",
        lambda p: (
            "# suggested_action: 自創動作 (信心:高)\n"
            "# cited_examples: \n"
            "亂講。\n"
        ),
    )

    result = classifier.classify_dir(
        mw_dir=stage["mw_dir"],
        actions_yaml=stage["actions_yaml"],
        spec_md=stage["spec_md"],
        training_root=stage["training"],
        runs_log=stage["runs_log"],
    )

    assert result["status"] == "rejected"
    assert "suggested_action" not in stage["target_md"].read_text(encoding="utf-8")
    assert "違反清單" in stage["runs_log"].read_text(encoding="utf-8")


def test_classify_dir_missing_summary_md_raises(stage, monkeypatch, tmp_path):
    from doc_classifier import classifier
    # 刪掉 target.md,讓目錄沒任何 *總結*.md
    stage["target_md"].unlink()

    with pytest.raises(FileNotFoundError):
        classifier.classify_dir(
            mw_dir=stage["mw_dir"],
            actions_yaml=stage["actions_yaml"],
            spec_md=stage["spec_md"],
            training_root=stage["training"],
            runs_log=stage["runs_log"],
        )


def test_classify_dir_llm_backend_unavailable(stage, monkeypatch):
    from doc_classifier import classifier
    monkeypatch.setattr(classifier, "_call_llm", lambda p: None)

    result = classifier.classify_dir(
        mw_dir=stage["mw_dir"],
        actions_yaml=stage["actions_yaml"],
        spec_md=stage["spec_md"],
        training_root=stage["training"],
        runs_log=stage["runs_log"],
    )

    assert result["status"] == "llm_unavailable"
    assert "LLM_UNAVAILABLE" in stage["runs_log"].read_text(encoding="utf-8")


def test_classify_dir_force_does_not_accumulate_reasoning(stage, monkeypatch):
    """force=True 重跑兩次,target_md 不該累積舊的 reasoning 文字。"""
    from doc_classifier import classifier

    # 第一次 LLM 回 reasoning_A
    monkeypatch.setattr(
        classifier, "_call_llm",
        lambda p: (
            "# suggested_action: 公告 (信心:高)\n"
            "# cited_examples: 1140001\n"
            "REASONING_FIRST_RUN_ABC\n"
        ),
    )
    classifier.classify_dir(
        mw_dir=stage["mw_dir"],
        actions_yaml=stage["actions_yaml"],
        spec_md=stage["spec_md"],
        training_root=stage["training"],
        runs_log=stage["runs_log"],
        force=True,
    )

    # 第二次 LLM 回 reasoning_B
    monkeypatch.setattr(
        classifier, "_call_llm",
        lambda p: (
            "# suggested_action: 存查 (信心:中)\n"
            "# cited_examples: 1140001\n"
            "REASONING_SECOND_RUN_XYZ\n"
        ),
    )
    classifier.classify_dir(
        mw_dir=stage["mw_dir"],
        actions_yaml=stage["actions_yaml"],
        spec_md=stage["spec_md"],
        training_root=stage["training"],
        runs_log=stage["runs_log"],
        force=True,
    )

    text = stage["target_md"].read_text(encoding="utf-8")
    # 第二次的 reasoning 在
    assert "REASONING_SECOND_RUN_XYZ" in text
    # 第一次的 reasoning 已被剝掉
    assert "REASONING_FIRST_RUN_ABC" not in text
    # 原公文內容仍在
    assert "校園資安宣導活動" in text
    # 仍然只有一個 # suggested_action: 行
    assert text.count("# suggested_action:") == 1
