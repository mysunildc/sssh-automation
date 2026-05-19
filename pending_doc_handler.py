"""
pending_doc_handler.py
承辦中公文「點完最上方公文 + 新視窗開啟後」的處理。

職責切割：
- document_system.pending_doc：負責「切到承辦中 frame + 點最上方公文 link」，
  公文閱覽器分頁開啟後即 hand off 給本模組
- 本模組 handle_opened_document(driver)：切到新分頁、後續流程（檢視內容、
  簽辦、送件、結案等，第一版只切換 + 印 URL/title 觀察，TODO 擴充）

呼叫方式：
1) 從 document_system.pending_doc 串接（main.py 主流程會走到）
2) 單獨執行階段測試：
     C:\\Python314\\python.exe pending_doc_handler.py
   會跑 document_system standalone 同樣的路徑（開 edoc → cascade →
   pending_doc）,跑完後 chain 自動觸發本模組。session 過期就提示
   去跑 main.py 重登。
"""

import sys
import time

sys.stdout.reconfigure(encoding='utf-8')


def handle_opened_document(driver):
    """承辦中公文點完最上方 link、新分頁開啟後的處理流程。

    呼叫時機:document_system.pending_doc 點完公文 + sleep 等新 window 開啟之後。
    driver focus 仍在原(承辦中清單) window;本函式負責切到新公文閱覽器分頁。

    流程:
    1. 確認 window_handles 數 > 1 (新分頁已開)
    2. 切到非主 handle 的 window(通常是最新開的公文閱覽器)
    3. 等載入 + 印 URL/title 確認到位
    4. TODO:在公文閱覽器內做後續動作 (檢視內容/簽辦/送件/結案等)

    回 True 表示順利切換並執行;False 表示沒找到新 window 或切換失敗。
    """
    try:
        main_handle = driver.current_window_handle
        handles = driver.window_handles
    except Exception as e:
        print(f"[pending_doc_handler] 讀 window_handles 失敗:{type(e).__name__}: {e}")
        return False

    if len(handles) <= 1:
        print("[pending_doc_handler] 只有 1 個 window,沒偵測到公文閱覽器新分頁。")
        return False

    new_handle = None
    for h in handles:
        if h != main_handle:
            new_handle = h
    if new_handle is None:
        print("[pending_doc_handler] 沒找到非主 window 的 handle。")
        return False

    try:
        driver.switch_to.window(new_handle)
    except Exception as e:
        print(f"[pending_doc_handler] 切 window 失敗:{type(e).__name__}: {e}")
        return False

    # 公文閱覽器 (公文簽核 v1.0.344) 載入 PDF + JS 需要幾秒;eager strategy
    # 已等到 DOMContentLoaded,但 PDF 渲染可能還沒完
    time.sleep(1)

    try:
        print(f"[pending_doc_handler] 切到公文閱覽器分頁,URL={driver.current_url}")
        print(f"[pending_doc_handler] 標題={driver.title}")
    except Exception as e:
        print(f"[pending_doc_handler] 讀狀態失敗:{type(e).__name__}: {e}")

    # TODO:在公文閱覽器內做後續動作 (檢視內容/簽辦/送件/結案等)
    print("[pending_doc_handler] TODO:公文閱覽器內動作待實作")

    return True


if __name__ == "__main__":
    # standalone 階段測試:跑 document_system 同樣的路徑 (開 edoc → cascade →
    # pending_doc),跑完後 document_system.pending_doc 內已 chain 呼叫
    # handle_opened_document,所以本入口只需跑 process_document_system 即可。
    # 之所以另外提供本入口而非用 document_system.py:語義上「本檔關心新分頁
    # 之後的處理」,跑這檔代表「在測試新分頁那段」;document_system.py 則代表
    # 「測整個公文系統流程」。未來若加 Chrome --remote-debugging-port + driver
    # attach,可以改為「只 attach 既有 Chrome session 跳到新分頁直接測」,
    # 不必每次從 edoc 首頁開始。
    from taipeion_login_selenium import _setup_stdout_logging
    _setup_stdout_logging()

    from document_system import (
        _standalone_open_chrome_at_edoc,
        process_document_system,
    )
    driver = _standalone_open_chrome_at_edoc()
    if driver is None:
        sys.exit(1)

    ok = process_document_system(driver)
    sys.exit(0 if ok else 1)
