"""
main.py
自動化主程式 — 統一呼叫各功能模組的入口。

執行方式（在專案根目錄）：
    py main.py            # 預設跑 FEATURES[0]（Selenium 版）
    py main.py 2          # 跑 FEATURES[1]（pyautogui 版）

執行後跑指定 FEATURE，結束即回到原本的 PowerShell / CMD 視窗（不再進入選單迴圈）。
"""

import sys

sys.stdout.reconfigure(encoding='utf-8')

from taipeion_login_selenium import (
    login_taipeion_selenium,
    _close_selenium_chrome_only,
    _setup_stdout_logging,
)
from taipeion_login import login_taipeion
from click_document import click_document_card
from document_system import process_document_system
from document_closure.document_closure import process_document_closure
from ime_utils import ensure_english_ime, interactive_desktop_state
from servisign_utils import ensure_servisign

# 先把 stdout/stderr 落地到 run.log（與 main.py 同目錄）— 之後所有 print 都會
# 同步寫進去，下次出問題直接讀檔，不用手動 pipe。在 _close_selenium_chrome_only
# 之前 setup，確保連預清理的 [WARN] 都進 log。
_setup_stdout_logging()
_close_selenium_chrome_only()

# ── 功能清單 ──────────────────────────────────────────────────────────────────
# 每新增一列：(顯示名稱, 主函式, 登入後動作 or None, processor 函式 or None)
# - 若有「登入後動作」，主函式須支援 return_driver=True 並回傳 driver，跑完接著呼叫 post_login(driver)
# - post_login 回 True 後，若 processor 不為 None 則呼叫 processor(driver)
# - 沒有後續動作則第三欄填 None，直接呼叫主函式
# 預設執行 FEATURES[0]；可用 CLI 引數選其他項，例如：
#   python main.py        # 跑 FEATURES[0]（Selenium 版 + 點公文 + 公文系統全流程）
#   python main.py 2      # 跑 FEATURES[1]（pyautogui 像素點擊版）
#   python main.py 3      # 跑 FEATURES[2]（Selenium 版 + 點公文 + 結案存查）

FEATURES = [
    ("臺北市單一帳號認證平台 — 自然人憑證登入 + 點公文（Selenium 版）",
     login_taipeion_selenium, click_document_card, process_document_system),
    ("臺北市單一帳號認證平台 — 自然人憑證登入（pyautogui 像素版）",
     login_taipeion, None, None),
    ("edoc 結案存查 — 自然人憑證登入 + 待結案處理（Selenium 版）",
     login_taipeion_selenium, click_document_card, process_document_closure),
]


# ── 主程式 ────────────────────────────────────────────────────────────────────

def main():
    ensure_english_ime()  # 起手式:把輸入法切回英文，避免後續模擬鍵盤輸入被 IME 攔截
    # 起手式 2:桌面必須是 Active(RDP 連線中/console 登入中)。RDP 斷線後 Selenium 照常
    # 能跑,但 KdApp「匯出公文資料」對話框要靠 SendInput 打路徑,會全被拒 —— 與其跑 40s
    # 後在下載那步莫名失敗,不如啟動前就停下講清楚(2026-09-23 實機事故)。
    desk_ok, desk_reason = interactive_desktop_state()
    if not desk_ok:
        print("!" * 60)
        print(f"[STOP] {desk_reason}")
        print("!" * 60)
        return
    print(f"      OK：{desk_reason}")
    # 起手式 3:簽章元件 TCGServiSign 健康檢查 + 自癒。主程式會自己掉(9/16、9/23 各一次),
    # 掉了登入頁就一直「重新檢測」、看起來像卡片壞了;56420 沒人聽就自動重啟,再用 WinSCard
    # 實測讀卡機是否可見 —— 在 RDP 語境被重啟的元件會讀不到主機的卡,那時要講清楚怎麼辦。
    sign_ok, sign_reason = ensure_servisign(expect_reader_substr="EZ100PU")
    if not sign_ok:
        print("!" * 60)
        print(f"[STOP] {sign_reason}")
        print("!" * 60)
        return
    print(f"      OK：{sign_reason}")
    idx = 0
    if len(sys.argv) > 1:
        try:
            idx = int(sys.argv[1]) - 1
            if not (0 <= idx < len(FEATURES)):
                raise ValueError
        except ValueError:
            print(f"[ERROR] 無效引數 '{sys.argv[1]}'，請傳入 1~{len(FEATURES)}")
            return

    name, func, post_login, processor = FEATURES[idx]
    print(f"▶ 執行：{name}")
    print("-" * 40)
    if post_login is None:
        func()
    else:
        driver = func(return_driver=True)
        if driver is None:
            print("[ERROR] 登入未完成，跳過後續動作。")
        else:
            # post_login 回 True 後呼叫 per-feature 的 processor（若有）。
            if post_login(driver) and processor is not None:
                processor(driver)
    print("-" * 40)
    print("[完成] 程式結束。")


if __name__ == "__main__":
    main()
