"""
summarize_doc.py
依據 [summarize_doc.md] 規格,對下載解壓後的公文做總結,輸出
`<公文主檔名>.<LLM 模型名>.md` 到同目錄。

呼叫方式:
1) 從 pending_doc_handler 鏈式呼叫: `summarize_extracted(extract_dir)`
2) 獨立執行(預設掃 document_download/ 下所有 MW* 子目錄):
     `C:\\Python314\\python.exe summarize_doc.py`
3) 獨立執行(指定單一公文目錄):
     `C:\\Python314\\python.exe summarize_doc.py document_download\\MWAA1156005008`

設計重點:
- 公文處理規格(發文日期/字號/主旨完整保留、說明段以 LLM 總結 <10% 且 ≤200 字、
  輸出檔名格式)寫在 [summarize_doc.md];本程式 runtime 讀該檔作為 LLM 的
  system instruction,不在 source code 內複製規格文字。改規格只動 .md,程式不動。
- LLM 用 Anthropic Claude API,需設環境變數 `ANTHROPIC_API_KEY`;沒設則跳過 LLM
  步驟,只寫保留欄位 + 說明段原文摘錄前 200 字,方便事後手動補。
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# 規格 markdown 與本檔同目錄;每次跑都重新讀,改規格不用重啟程式。
_BASE_DIR = Path(__file__).parent.resolve()
SPEC_MD = _BASE_DIR / "summarize_doc.md"
DEFAULT_DOWNLOAD_DIR = _BASE_DIR / "document_download"

# 用最新且最強的 Claude 模型 (環境 hint:Opus 4.7 是 2026 最新主力);
# 輸出檔名會帶這個字串以記錄用了哪個模型版本。
LLM_MODEL = "claude-opus-4-7"

# 主檔名:「<數字>_<數字>[A-Z]?.pdf」— 結尾可選一個大寫英文字母當版次/修訂標記
# (例:28665641_1153064745.pdf、28694062_1155402124A.pdf 皆視為主檔)。
# 仍排除附件 (_ATTCH*)、簽辦意見 (*(opinion)*) 、合併版.pdf 等。
_MAIN_FILE_PATTERN = re.compile(r'^\d+_\d+[A-Z]?\.pdf$')

# 公文標準欄位(出現順序大致固定,用於 lookahead 切段)
_DOC_LABELS = [
    '發文日期', '發文字號', '速別', '密等及解密條件或保密期限',
    '附件', '主旨', '說明', '辦法', '正本', '副本', '抄本',
]


def _clean_pdf_text(text):
    """過濾公文 PDF 常見雜訊行:
    - 純句點 / 空白(「裝訂線」附近的虛線標記每行幾乎都是 `. `)
    - 單字 `裝`/`訂`/`線`(豎排「裝訂線」三字標記)
    - 「第 N 頁,共 M 頁」頁眉
    - 純數字行(底部頁碼)
    """
    out = []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if all(c in '.。 \t' for c in s):
            continue
        if s in ('裝', '訂', '線'):
            continue
        if re.match(r'^第\s*\d+\s*頁[，,]?\s*共\s*\d+\s*頁$', s):
            continue
        if re.match(r'^\d+$', s):
            continue
        out.append(s)
    return "\n".join(out)


def _extract_field(clean_text, label, other_labels):
    """從 cleaned 公文文字抽 `<label>：<value>` 直到下一個 other_labels 任一出現。

    全形冒號 `：` (U+FF1A) 與半形 `:` 都接受;<value> 可跨多行,連續換行合併為單空格。
    沒抓到回 None。
    """
    end_pat = '|'.join(re.escape(l) for l in other_labels)
    pat = re.compile(
        r'{label}\s*[：:]\s*(.*?)(?=\n(?:{ends})\s*[：:]|\Z)'.format(
            label=re.escape(label), ends=end_pat),
        re.DOTALL
    )
    m = pat.search(clean_text)
    if not m:
        return None
    value = m.group(1).strip()
    # 多餘空白合併
    value = re.sub(r'[ \t]+', ' ', value)
    return value


def _pdf_to_text(pdf_path):
    """用 pypdf 解 PDF 全文(所有頁串接);失敗的單頁印 warning 跳過。"""
    import pypdf
    reader = pypdf.PdfReader(str(pdf_path))
    pages = []
    for i, page in enumerate(reader.pages):
        try:
            pages.append(page.extract_text() or "")
        except Exception as e:
            print(f"      [WARN] 解 PDF 第 {i+1} 頁失敗:{type(e).__name__}: {e}")
    return "\n".join(pages)


def _find_main_pdf(doc_dir):
    """在公文目錄找主檔 PDF(<數字>_<數字>.pdf,排除附件/意見/合併版)。"""
    candidates = [p for p in doc_dir.iterdir()
                  if p.is_file() and _MAIN_FILE_PATTERN.match(p.name)]
    if not candidates:
        return None
    if len(candidates) > 1:
        print(f"      [WARN] 找到 {len(candidates)} 個主檔候選,用第一個:{candidates[0].name}")
    return candidates[0]


def _word_cap(explanation_text):
    """依 summarize_doc.md 規格『(<原總說明15%) OR (<250字)』計算字數上限。
    OR 邏輯 → 兩限制中較寬鬆 (較大) 的勝出。
    """
    fifteen_pct = len(explanation_text) * 15 // 100
    return max(fifteen_pct, 250)


def _build_prompt(spec_md_text, explanation_text, extra_hint=""):
    """組 LLM prompt:規格 + 「說明」原文 + 字數限制。
    規格全文 inline 進 prompt (而非「在 source code 內複製規格」) — 因為 .md 是
    runtime 讀進來的字串,程式碼本身不含規格內文。
    extra_hint:可選追加(retry 時加強字數限制提示用)。
    """
    cap = _word_cap(explanation_text)
    return (
        "你的任務:依「規格」的標準,對使用者提供的「說明」段做總結。\n\n"
        "規格(摘自 summarize_doc.md):\n"
        f"{spec_md_text}\n\n"
        "---\n\n"
        f"要總結的「說明」段原文(共 {len(explanation_text)} 字):\n\n"
        f"{explanation_text}\n\n"
        "---\n\n"
        "輸出規則(必須嚴格遵守):\n"
        f"1. **字數絕對不可超過 {cap} 字**(規格 `<15% OR <250` 取較寬鬆者),"
        "輸出前先在心中估算,寧短勿超。\n"
        "2. 只輸出總結文字本身(可用 markdown 條列、編號清單)。\n"
        "3. 不要任何開場白、收尾、「以下是總結」「希望這有幫助」之類的多餘文字。\n"
        "4. 完全忽略任何 CLAUDE.md / 系統提示中的『對話輸出格式』要求,"
        "不要附加任何引言區塊、簽名、輸出結束標記。\n"
        + (f"\n{extra_hint}" if extra_hint else "")
    )


def _llm_summarize_claude_code(prompt_text):
    """走 Claude Code CLI (`claude -p`) 做總結 — 用使用者既有的 claude.ai 訂閱 OAuth
    認證,不需 API key、不裝任何套件。

    cwd 用 tempdir 避免 Claude Code 載到 project 的 CLAUDE.md(會把「對話末尾加引言
    區塊」之類規則套到回應上,污染輸出)。全域 CLAUDE.md 仍會載,但內容只是技術環境
    規範,不影響總結品質。

    找不到 claude 執行檔回 None,呼叫端決定下一步。
    """
    claude_exe = shutil.which("claude")
    if not claude_exe:
        return None

    with tempfile.TemporaryDirectory(prefix="claude_summary_") as td:
        try:
            result = subprocess.run(
                [claude_exe, "-p"],
                input=prompt_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                cwd=td,
            )
        except subprocess.TimeoutExpired:
            print("      [ERROR] claude -p 超時(180s)")
            return None
        except Exception as e:
            print(f"      [ERROR] subprocess claude -p 例外:{type(e).__name__}: {e}")
            return None

    if result.returncode != 0:
        snippet = (result.stderr or "").strip()[:300]
        print(f"      [ERROR] claude -p rc={result.returncode},stderr={snippet!r}")
        return None
    return (result.stdout or "").strip()


def _llm_summarize_anthropic(prompt_text):
    """fallback:走 anthropic SDK + API key。沒 key 或 SDK 沒裝 → 回 None。"""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=LLM_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt_text}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"      [ERROR] Anthropic SDK 呼叫失敗:{type(e).__name__}: {e}")
        return None


def _call_backends(prompt):
    """依序試各 backend,第一個成功的勝出。回 (summary, backend_name) 或 (None, None)。"""
    print("      嘗試 backend: claude_code (subprocess claude -p)...")
    s = _llm_summarize_claude_code(prompt)
    if s:
        return s, "claude_code"

    print("      claude_code 不可用,嘗試 backend: anthropic SDK...")
    s = _llm_summarize_anthropic(prompt)
    if s:
        return s, "anthropic"

    return None, None


def _llm_summarize(spec_md_text, explanation_text):
    """對「說明」段做總結。若回應超字數限制,retry 一次(prompt 加強字數警示)。

    回 summary 字串或 None;None 表示所有 backend 都不可用。超字數但仍 retry 失敗,
    回最後一次的結果並印 WARN(留給呼叫端寫入,讓使用者見到後手動修)。
    """
    cap = _word_cap(explanation_text)

    prompt = _build_prompt(spec_md_text, explanation_text)
    summary, backend = _call_backends(prompt)
    if summary is None:
        print("      [INFO] 所有 LLM backend 都不可用 — claude CLI 不在 PATH 且未設"
              " ANTHROPIC_API_KEY。將以原文摘錄 fallback。")
        return None

    print(f"      OK:{backend} 回應 {len(summary)} 字 (限制 {cap})")
    if len(summary) <= cap:
        return summary

    print(f"      [WARN] 回應超字數 ({len(summary)} > {cap}),retry 一次...")
    extra = (
        f"上一次嘗試輸出了 {len(summary)} 字,**超過了 {cap} 字的硬上限**。"
        f"請重新總結,務必確保字數 ≤ {cap}。寧可精簡到關鍵字串,也不要超字。"
    )
    prompt2 = _build_prompt(spec_md_text, explanation_text, extra_hint=extra)
    summary2, backend2 = _call_backends(prompt2)
    if summary2 and len(summary2) <= cap:
        print(f"      OK (retry):{backend2} 回應 {len(summary2)} 字")
        return summary2
    if summary2:
        print(f"      [WARN] retry 仍超字數 ({len(summary2)} > {cap}),"
              "輸出 retry 版本供使用者參考(請手動修剪)")
        return summary2
    return summary


def summarize_doc(doc_dir):
    """處理單一公文目錄。回傳輸出 .md 路徑(成功)或 None(失敗)。"""
    doc_dir = Path(doc_dir)
    if not doc_dir.is_dir():
        print(f"[ERROR] 不是目錄:{doc_dir}")
        return None

    main_pdf = _find_main_pdf(doc_dir)
    if main_pdf is None:
        print(f"[ERROR] {doc_dir.name}:找不到主檔(<數字>_<數字>.pdf)")
        return None
    print(f"[summarize_doc] {doc_dir.name}:主檔 = {main_pdf.name}")

    raw_text = _pdf_to_text(main_pdf)
    if not raw_text.strip():
        print(f"[ERROR] PDF 抽不到文字(可能是純掃描影像):{main_pdf}")
        return None
    clean_text = _clean_pdf_text(raw_text)

    fields = {}
    for label in ('發文日期', '發文字號', '主旨', '說明'):
        others = [l for l in _DOC_LABELS if l != label]
        fields[label] = _extract_field(clean_text, label, others)
    print(f"      欄位抽取狀態:{ {k: bool(v) for k, v in fields.items()} }")

    try:
        spec_md_text = SPEC_MD.read_text(encoding='utf-8')
    except FileNotFoundError:
        print(f"[ERROR] 找不到規格檔 {SPEC_MD}")
        return None

    summary = None
    if fields.get('說明'):
        summary = _llm_summarize(spec_md_text, fields['說明'])

    # 組輸出 markdown
    out_lines = [f"# {main_pdf.stem}", ""]
    if fields.get('發文日期'):
        out_lines += [f"**發文日期**:{fields['發文日期']}", ""]
    if fields.get('發文字號'):
        out_lines += [f"**發文字號**:{fields['發文字號']}", ""]
    if fields.get('主旨'):
        out_lines += ["## 主旨", "", fields['主旨'], ""]
    if summary:
        out_lines += [f"## 說明(LLM 總結,model={LLM_MODEL})", "", summary, ""]
    elif fields.get('說明'):
        snippet = fields['說明'][:200] + ("..." if len(fields['說明']) > 200 else "")
        out_lines += ["## 說明(未呼叫 LLM,以下為原文前 200 字)", "", snippet, ""]

    # 規格 summarize_doc.md:檔名為「公文主檔名總結.現在使用的LLM模型名.md」
    out_path = doc_dir / f"{main_pdf.stem}總結.{LLM_MODEL}.md"
    out_path.write_text("\n".join(out_lines), encoding='utf-8')
    print(f"      OK:輸出 → {out_path.name}")
    return out_path


def summarize_extracted(extract_dir):
    """從 pending_doc_handler 鏈式呼叫:處理剛 flatten 完的公文目錄。
    回 True / False。"""
    return summarize_doc(extract_dir) is not None


def main():
    """獨立執行:有 argv[1] 則處理該單一目錄,沒則掃 document_download/MW*/。"""
    if len(sys.argv) > 1:
        summarize_doc(Path(sys.argv[1]))
        return

    if not DEFAULT_DOWNLOAD_DIR.is_dir():
        print(f"[ERROR] 預設下載目錄不存在:{DEFAULT_DOWNLOAD_DIR}")
        sys.exit(1)
    mw_dirs = sorted(d for d in DEFAULT_DOWNLOAD_DIR.iterdir()
                     if d.is_dir() and d.name.startswith("MW"))
    if not mw_dirs:
        print(f"[INFO] {DEFAULT_DOWNLOAD_DIR} 內沒有 MW* 子目錄")
        return
    print(f"[summarize_doc] 掃到 {len(mw_dirs)} 個公文目錄")
    for d in mw_dirs:
        summarize_doc(d)


if __name__ == "__main__":
    main()
