"""strip_training_artifacts:組 prompt 前過濾 training data 內的 LLM 既有建議。"""


def test_strip_removes_suggested_action_line():
    from doc_classifier.classifier import strip_training_artifacts
    raw = (
        "# action: 公告\n"
        "# suggested_action: 公告 (信心:高)\n"
        "# cited_examples: MW001\n"
        "主旨:資安宣導\n"
    )
    result = strip_training_artifacts(raw)
    assert "# action: 公告" in result
    assert "suggested_action" not in result
    assert "cited_examples" not in result
    assert "主旨:資安宣導" in result


def test_strip_preserves_action_only_doc():
    from doc_classifier.classifier import strip_training_artifacts
    raw = "# action: 存查\n主旨:備查\n"
    assert strip_training_artifacts(raw) == raw


def test_strip_handles_no_artifacts():
    from doc_classifier.classifier import strip_training_artifacts
    raw = "主旨:備查\n說明:無\n"
    assert strip_training_artifacts(raw) == raw
