"""build_prompt 與 load_actions 的測試。"""
from pathlib import Path
import pytest


def test_load_actions(tmp_path):
    from doc_classifier.classifier import load_actions
    yaml_path = tmp_path / "actions.yaml"
    yaml_path.write_text("actions:\n  - 公告\n  - 存查\n", encoding="utf-8")
    assert load_actions(yaml_path) == ["公告", "存查"]


def test_load_actions_empty_raises(tmp_path):
    from doc_classifier.classifier import load_actions
    yaml_path = tmp_path / "actions.yaml"
    yaml_path.write_text("actions: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="actions.yaml"):
        load_actions(yaml_path)


def test_load_actions_missing_file_raises(tmp_path):
    from doc_classifier.classifier import load_actions
    with pytest.raises(FileNotFoundError):
        load_actions(tmp_path / "nope.yaml")


def test_build_prompt_includes_all_sections():
    from doc_classifier.classifier import build_prompt
    spec = "# 公文處置分類規格\n\n## 任務\n推論動作。\n"
    actions = ["公告", "存查"]
    examples = {
        "1140001總結.md": "# action: 公告\n主旨:資安\n",
        "1140002總結.md": "# action: 存查\n主旨:備查\n",
    }
    target_name = "1140999總結.md"
    target_text = "主旨:校園資安宣導"

    prompt = build_prompt(spec, actions, examples, target_name, target_text)

    assert "## 任務" in prompt
    assert "公告" in prompt and "存查" in prompt
    assert "1140001總結.md" in prompt
    assert "1140002總結.md" in prompt
    assert target_name in prompt
    assert target_text in prompt
    assert "校園資安宣導" in prompt


def test_build_prompt_empty_examples_section_marker():
    """training_data 為空時,prompt 仍須結構完整(LLM 依規格回 SKIP)。"""
    from doc_classifier.classifier import build_prompt
    prompt = build_prompt(
        spec_text="(spec)",
        actions=["公告"],
        examples={},
        target_name="x.md",
        target_text="主旨:x",
    )
    # 必要區塊都在
    assert "歷史範例" in prompt
    assert "待分類公文" in prompt
