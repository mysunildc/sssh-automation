"""
document_closure.py
結案存查功能主模組 — 假設 driver 已導航到 edoc 公文首頁（已登入）。

呼叫方式：
1) 從 main.py 串接（FEATURES[2]，python main.py 3）：
     process_document_closure(driver)
2) 單獨執行（跳過登入，直接開 Chrome 到 edoc）：
     C:\\Python314\\python.exe document_closure/document_closure.py
   session 過期時會提示跑 main.py 重新登入。
"""

import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

# 單獨執行（python document_closure/document_closure.py）時，Python 只把腳本所在的
# document_closure/ 加進 sys.path，找不到專案根目錄的 taipeion_login_selenium /
# document_system 等模組。把專案根目錄（本檔的上層目錄）插進 sys.path 才能 import。
# 從 main.py 以 package 形式 import 時根目錄已在 path，重複插入無害。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# edoc 公文首頁 URL（與 document_system.py 保持一致）
EDOC_HOME_URL = "https://edoc.gov.taipei/tcqb/home/default.jsp?inLine=Y"


def process_document_closure(driver):
    """結案存查主流程。driver 必須已導航到 edoc 公文首頁。

    流程：
        1. 確認 current_url 在 edoc.gov.taipei
        2. 讀左側 sidebar「待結案(N)」數字
           - > 0：點進待結案清單，切到 dTreeContent frame，執行結案存查
           - = 0：印「無待結案公文，跳過」
           - 判讀失敗 (-1)：印警告，return False
        3. 切回 default_content
    回傳 True 表示流程跑完；False 表示前置檢查失敗。
    """
    from document_system import (
        _get_sidebar_paren_count,
        _click_sidebar_item,
        _switch_to_frame_with_xpath,
        _click_first_document_in_pending,
    )

    print("[document_closure] 開始結案存查流程...")

    try:
        current = driver.current_url
    except Exception as e:
        print(f"[ERROR] 讀 current_url 失敗：{type(e).__name__}: {e}")
        return False

    if "edoc.gov.taipei" not in current:
        print(f"[ERROR] 當前 URL 不在 edoc：{current}")
        return False

    # ── 待結案 ────────────────────────────────────────────────────────────
    print("[document_closure] 讀左側 sidebar「待結案」數...")
    count = _get_sidebar_paren_count(driver, "待結案")
    if count < 0:
        print("[document_closure] 無法判讀待結案數，保守不點，結束。")
        return False
    if count == 0:
        print("[document_closure] 待結案 = 0，無待辦，跳過。")
        return True

    print(f"[document_closure] 待結案 = {count}，點選進入...")
    if not _click_sidebar_item(driver, "待結案"):
        print("[document_closure] 點「待結案」失敗，請手動處理。")
        return False

    time.sleep(0.5)
    try:
        print(f"[document_closure] 待結案頁 URL：{driver.current_url}")
        print(f"[document_closure] 待結案頁標題：{driver.title}")
    except Exception as e:
        print(f"[document_closure] 讀狀態失敗：{type(e).__name__}: {e}")

    # ── 切到內容 frame ────────────────────────────────────────────────────
    # 待結案清單在 dTreeContent iframe 內，操作前必須切換 frame
    target_xpath = "//th[contains(normalize-space(), '公文文號')]"
    print("[document_closure] 切到 dTreeContent frame...")
    if not _switch_to_frame_with_xpath(driver, target_xpath, "待結案清單表頭"):
        print("[document_closure] 切不到內容 frame，請手動處理。")
        return False

    # ── 點待結案清單第一筆公文、記下文號 ───────────────────────────────
    # 待結案與承辦中共用同一張含「公文文號」欄的表格，重用 document_system 的
    # _click_first_document_in_pending（回傳公文文號字串）。記下文號供後續
    # 選擇「存查檔號」使用。
    print(f"[document_closure] 待結案清單共 {count} 筆，點選最上方第一筆...")
    doc_no = _click_first_document_in_pending(driver, label="待結案")
    if not doc_no:
        print("[document_closure] 點待結案公文失敗，請手動處理。")
        driver.switch_to.default_content()
        return False

    print("=" * 50)
    print(f"[document_closure] ★ 已選定待結案公文文號：{doc_no}")
    print("[document_closure] ★（此文號供後續選擇存查檔號使用）")
    print("=" * 50)

    # 點公文後系統可能就地切 frame、開新分頁或彈 modal，短 sleep 等回應
    time.sleep(1)
    try:
        print(f"[document_closure] 點開後 URL：{driver.current_url}")
        print(f"[document_closure] 點開後標題：{driver.title}")
        handles = driver.window_handles
        if len(handles) > 1:
            print(f"[document_closure] 偵測到 {len(handles)} 個 window — 公文內容可能開在新分頁")
    except Exception as e:
        print(f"[document_closure] 讀狀態失敗：{type(e).__name__}: {e}")

    # ── TODO: 依 doc_no 選擇存查檔號、完成結案存查 ──────────────────────
    print("[document_closure] TODO: 依文號選擇存查檔號、完成結案存查（尚未實作）")

    driver.switch_to.default_content()
    print("[document_closure] 結案存查流程結束。")
    return True


if __name__ == "__main__":
    # 把 stdout/stderr 同步落地到 run.log — entry point 開頭就 setup，確保
    # Chrome 預清理 / 啟動 / 導航每行 print 都進 log。
    from taipeion_login_selenium import _setup_stdout_logging
    from document_system import _standalone_open_chrome_at_edoc

    _setup_stdout_logging()
    driver = _standalone_open_chrome_at_edoc()
    if driver is None:
        sys.exit(1)
    ok = process_document_closure(driver)
    sys.exit(0 if ok else 1)
