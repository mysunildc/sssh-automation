"""parse_response 解析 LLM 輸出的單元測試。"""
import pytest


def test_parse_normal_response():
    from doc_classifier.classifier import parse_response
    raw = (
        "# suggested_action: 公告 (信心:高)\n"
        "# cited_examples: MW001, MW005\n"
        "因主旨提到「校園資安宣導」,與 MW001、MW005 標記皆為「資安」,皆判為公告。\n"
    )
    result = parse_response(raw)
    assert result["status"] == "ok"
    assert result["action"] == "公告"
    assert result["confidence"] == "高"
    assert result["examples"] == ["MW001", "MW005"]
    assert "資安" in result["reasoning"]


def test_parse_skip_response():
    from doc_classifier.classifier import parse_response
    raw = "SKIP: training_data 為空,無歷史範例可推論"
    result = parse_response(raw)
    assert result["status"] == "skip"
    assert "無歷史範例" in result["reason"]


def test_parse_with_html_comment_skip():
    from doc_classifier.classifier import parse_response
    raw = "<!-- SKIP: training_data 為空 -->"
    result = parse_response(raw)
    assert result["status"] == "skip"


def test_parse_reasoning_preserves_internal_blank_lines():
    from doc_classifier.classifier import parse_response
    raw = (
        "# suggested_action: 存查 (信心:中)\n"
        "# cited_examples: MW010\n"
        "第一段。\n"
        "\n"
        "第二段。\n"
    )
    result = parse_response(raw)
    assert result["reasoning"] == "第一段。\n\n第二段。"


def test_parse_format_error():
    from doc_classifier.classifier import parse_response
    raw = "這是 LLM 亂講的回應,沒有 suggested_action 那行"
    result = parse_response(raw)
    assert result["status"] == "error"


def test_parse_examples_empty_string():
    """cited_examples 可以是空 (LLM 表示無範例可引)。"""
    from doc_classifier.classifier import parse_response
    raw = (
        "# suggested_action: 存查 (信心:低)\n"
        "# cited_examples: \n"
        "無強範例,依語意推測。\n"
    )
    result = parse_response(raw)
    assert result["status"] == "ok"
    assert result["examples"] == []


def test_parse_skip_no_space_after_html_comment():
    """`<!--SKIP:` (無空格) 也要被識別為 SKIP,不能 fall through 到 error。"""
    from doc_classifier.classifier import parse_response
    raw = "<!--SKIP: training_data 為空-->"
    result = parse_response(raw)
    assert result["status"] == "skip"


def test_parse_examples_space_separated_kept_as_single_string():
    """document current behavior:LLM 若用空格分隔 examples (違反 spec),
    目前 split(',') 會把它當單一字串。這是已知行為,不修;classifier.md
    規格明示 comma-separated,LLM 應遵守。
    """
    from doc_classifier.classifier import parse_response
    raw = (
        "# suggested_action: 公告 (信心:高)\n"
        "# cited_examples: MW001 MW005\n"
        "reasoning here\n"
    )
    result = parse_response(raw)
    assert result["status"] == "ok"
    # 空格分隔被當單一字串 — document current behavior
    assert result["examples"] == ["MW001 MW005"]
