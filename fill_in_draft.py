"""4-2:承辦中公文擬寫辦理文字。

依 docs/superpowers/specs/2026-05-27-fill-in-draft-design.md。
讀 summarize_doc 產出的總結檔取標記 → 查 fill_in_draft.yaml 對應表得
「辦理文字 + 動作」→ 於公文閱覽器分頁填字、儲存、依動作決定不動作/陳會。
"""

import pathlib

import yaml

_BASE_DIR = pathlib.Path(__file__).resolve().parent
CONFIG_PATH = _BASE_DIR / "fill_in_draft.yaml"


def _read_marks(extract_dir):
    """從 extract_dir 找 *總結*.md,解析 `## 標記1 標記2` 行,回標記 list。

    找不到總結檔、或沒有以 `##` 開頭的標記行 → 回 []。
    (存查分類行開頭是單一 `#`,不會被誤判為標記行。)
    """
    extract_dir = pathlib.Path(extract_dir)
    summaries = sorted(extract_dir.glob("*總結*.md"))
    if not summaries:
        return []
    for raw in summaries[0].read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("##"):
            return line.lstrip("#").split()
    return []


def _load_rules(config_path=CONFIG_PATH):
    """讀 yaml 設定,回 (rules, default)。

    rules:list of dict(標記/優先序/辦理文字/動作);default:dict(辦理文字/動作)。
    """
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    rules = cfg.get("rules") or []
    default = cfg.get("default") or {"辦理文字": "擬:", "動作": "none"}
    return rules, default


def _lookup(marks, rules, default):
    """依優先序由小到大掃描 rules,第一個 `標記 in marks` 命中的決定一切。

    全部沒命中 → 回 default 的 (辦理文字, 動作)。
    """
    for rule in sorted(rules, key=lambda r: r.get("優先序", 0)):
        if rule.get("標記") in marks:
            return rule.get("辦理文字", ""), rule.get("動作", "none")
    return default.get("辦理文字", ""), default.get("動作", "none")
