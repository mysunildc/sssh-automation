"""validate_action:檢查 LLM 回的動作是否在 actions.yaml 清單內。"""


def test_validate_action_in_list():
    from doc_classifier.classifier import validate_action
    assert validate_action("公告", ["公告", "存查"]) is True


def test_validate_action_not_in_list():
    from doc_classifier.classifier import validate_action
    assert validate_action("自創動作", ["公告", "存查"]) is False


def test_validate_action_strips_whitespace():
    from doc_classifier.classifier import validate_action
    assert validate_action(" 公告 ", ["公告", "存查"]) is True
