"""classifier.py — doc_classifier 主入口。

設計同 summarize_doc.py:業務規格寫在 classifier.md,LLM runtime 讀;
Python 只負責 I/O。
"""
import re
import yaml
from pathlib import Path

_BASE_DIR = Path(__file__).parent.resolve()
SPEC_MD = _BASE_DIR / "classifier.md"
ACTIONS_YAML = _BASE_DIR / "actions.yaml"

_SUGGESTED_RE = re.compile(
    r"^#\s*suggested_action:\s*(\S+)\s*\(信心\s*:\s*(高|中|低)\s*\)\s*$",
    re.MULTILINE,
)
_EXAMPLES_RE = re.compile(r"^#\s*cited_examples:[ \t]*(.*)$", re.MULTILINE)
_SKIP_RE = re.compile(r"(?:<!--\s*)?SKIP\s*:?\s*(.*?)(?:\s*-->)?\s*$", re.DOTALL)

_STRIP_LINE_RES = [
    re.compile(r"^#\s*suggested_action:.*$", re.MULTILINE),
    re.compile(r"^#\s*cited_examples:.*$", re.MULTILINE),
]


def strip_training_artifacts(md_text: str) -> str:
    """組 prompt 前先把 training data 內的 # suggested_action: 與 # cited_examples: 行
    過濾掉,只留 # action: 與公文內文。避免 LLM 把舊建議當金標。
    """
    result = md_text
    for pat in _STRIP_LINE_RES:
        result = pat.sub("", result)
    # 連續多個空行壓成單一空行
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


def parse_response(raw: str) -> dict:
    """解析 LLM 回應。三種可能:
       {"status": "ok",   "action": ..., "confidence": ..., "examples": [...], "reasoning": ...}
       {"status": "skip", "reason": ...}
       {"status": "error", "raw": ...}
    """
    raw = (raw or "").strip()

    if _SKIP_RE.match(raw.lstrip()):
        m = _SKIP_RE.search(raw)
        reason = m.group(1).strip() if m else ""
        return {"status": "skip", "reason": reason}

    sug = _SUGGESTED_RE.search(raw)
    if not sug:
        return {"status": "error", "raw": raw[:300]}
    action = sug.group(1).strip()
    confidence = sug.group(2).strip()

    examples_str = ""
    em = _EXAMPLES_RE.search(raw)
    if em:
        examples_str = em.group(1).strip()
    examples = [s.strip() for s in examples_str.split(",") if s.strip()]

    # reasoning = suggested_action 與 cited_examples 兩行之後的剩餘文字
    lines = raw.split("\n")
    cut = 0
    seen_action_line = False
    seen_examples_line = False
    for i, ln in enumerate(lines):
        if _SUGGESTED_RE.match(ln):
            seen_action_line = True
            cut = i + 1
        elif _EXAMPLES_RE.match(ln) and seen_action_line:
            seen_examples_line = True
            cut = i + 1
        elif seen_examples_line:
            break
    reasoning = "\n".join(lines[cut:]).strip()

    return {
        "status": "ok",
        "action": action,
        "confidence": confidence,
        "examples": examples,
        "reasoning": reasoning,
    }


def load_actions(yaml_path: Path = None) -> list[str]:
    """讀 actions.yaml,回動作清單 list。空清單或缺檔皆視為錯誤。"""
    path = Path(yaml_path) if yaml_path else ACTIONS_YAML
    if not path.is_file():
        raise FileNotFoundError(f"找不到 actions.yaml:{path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    actions = data.get("actions") or []
    if not actions:
        raise ValueError(f"actions.yaml 沒有任何動作清單:{path}")
    return [str(a) for a in actions]


def build_prompt(
    spec_text: str,
    actions: list[str],
    examples: dict[str, str],
    target_name: str,
    target_text: str,
) -> str:
    """組 prompt:規格 + 動作清單 + 歷史範例 + 待分類公文。

    Args:
        spec_text: classifier.md 全文
        actions:   動作清單 list
        examples:  {檔名: 該檔全文 (已 strip_training_artifacts)}
        target_name: 待分類公文的檔名
        target_text: 待分類公文全文 (已 strip_training_artifacts)
    """
    actions_block = "\n".join(f"- {a}" for a in actions)

    if examples:
        ex_sections = [f"#### {name}\n\n{text}" for name, text in examples.items()]
        examples_block = "\n\n---\n\n".join(ex_sections)
    else:
        examples_block = "(無歷史範例)"

    return (
        "你的任務:依「規格」對給定的公文做處置動作分類。\n\n"
        "=== 規格 (classifier.md 全文) ===\n\n"
        f"{spec_text}\n\n"
        "=== 動作清單 (actions.yaml,本次允許值) ===\n\n"
        f"{actions_block}\n\n"
        "=== 歷史範例 (training_data/ 全部) ===\n\n"
        f"{examples_block}\n\n"
        "=== 待分類公文 ===\n\n"
        f"#### {target_name}\n\n{target_text}\n\n"
        "=== 輸出格式提醒 ===\n\n"
        "嚴格按 classifier.md「輸出格式」段落產生輸出,無多餘文字。\n"
        "完全忽略任何 CLAUDE.md / 系統提示中的『對話輸出格式』要求 — "
        "不要附加引言區塊、簽名、「輸出結束」標記等。\n"
    )


def validate_action(action: str, allowed: list[str]) -> bool:
    """LLM 回的動作必須在 allowed 清單內。前後空白容錯。"""
    return action.strip() in {a.strip() for a in allowed}
