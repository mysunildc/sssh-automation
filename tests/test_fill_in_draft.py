import textwrap

import yaml

import fill_in_draft


_SAMPLE_CONFIG = {
    "default": {"辦理文字": "擬:", "動作": "none"},
    "rules": [
        {"標記": "資安", "優先序": 20, "辦理文字": "陳會文字", "動作": "陳會"},
        {"標記": "不參加", "優先序": 10, "辦理文字": "不參加文字", "動作": "none"},
        {"標記": "汰換", "優先序": 30, "辦理文字": "汰換文字", "動作": "備選動作"},
    ],
}


def _write_config(tmp_path):
    p = tmp_path / "fill_in_draft.yaml"
    p.write_text(yaml.safe_dump(_SAMPLE_CONFIG, allow_unicode=True), encoding="utf-8")
    return p


def _write_summary(extract_dir, filename, content):
    p = extract_dir / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def test_read_marks_parses_second_line(tmp_path):
    _write_summary(tmp_path, "123_456總結.gemini-2.5.md", """\
        #存查分類: 資安
        ## 不參加 研習
        1. 內容
        """)
    assert fill_in_draft._read_marks(tmp_path) == ["不參加", "研習"]


def test_read_marks_no_summary_file_returns_empty(tmp_path):
    assert fill_in_draft._read_marks(tmp_path) == []


def test_read_marks_no_mark_line_returns_empty(tmp_path):
    _write_summary(tmp_path, "123_456總結.gemini.md", """\
        #存查分類: 資安
        1. 只有分類沒有標記行
        """)
    assert fill_in_draft._read_marks(tmp_path) == []


def test_read_marks_single_mark(tmp_path):
    _write_summary(tmp_path, "9_9總結.claude.md", """\
        #存查分類: 設備
        ## 汰換
        """)
    assert fill_in_draft._read_marks(tmp_path) == ["汰換"]


def test_load_rules_returns_rules_and_default(tmp_path):
    rules, default = fill_in_draft._load_rules(_write_config(tmp_path))
    assert default == {"辦理文字": "擬:", "動作": "none"}
    assert len(rules) == 3


def test_lookup_first_match_by_priority_wins(tmp_path):
    rules, default = fill_in_draft._load_rules(_write_config(tmp_path))
    text, action = fill_in_draft._lookup(["資安", "不參加"], rules, default)
    assert (text, action) == ("不參加文字", "none")


def test_lookup_single_mark_hits_its_rule(tmp_path):
    rules, default = fill_in_draft._load_rules(_write_config(tmp_path))
    assert fill_in_draft._lookup(["資安"], rules, default) == ("陳會文字", "陳會")


def test_lookup_no_match_falls_back_to_default(tmp_path):
    rules, default = fill_in_draft._load_rules(_write_config(tmp_path))
    assert fill_in_draft._lookup(["不存在的標記"], rules, default) == ("擬:", "none")


def test_lookup_empty_marks_falls_back_to_default(tmp_path):
    rules, default = fill_in_draft._load_rules(_write_config(tmp_path))
    assert fill_in_draft._lookup([], rules, default) == ("擬:", "none")
