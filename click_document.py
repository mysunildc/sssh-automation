"""
click_document.py
TAIPEION 入口網儀表板 — 點擊「公文(學校)」方塊，進入公文系統。

設計：登入完成後接著跑此腳本，省去使用者手動找方塊的步驟。

呼叫方式：
  1) 從 main.py 自然人憑證登入成功後串接：
       from click_document import click_document
       click_document(driver)             # 用既有 Selenium driver 繼續操作
  2) 單獨執行：
       C:\\Python314\\python.exe click_document.py
       → 會先呼叫 login_taipeion_selenium() 重新登入拿到 driver，再點公文
"""

import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

sys.stdout.reconfigure(encoding='utf-8')

# 儀表板上的「公文(學校)」方塊。實測該方塊由 div 包標籤文字 + 數字計數構成，
# 整塊都可點 — 用 contains 抓含「公文」文字的元素，再 ancestor 跳到可點的容器。
DOCUMENT_XPATHS = [
    "//a[contains(normalize-space(), '公文(學校)')]",
    "//*[normalize-space()='公文(學校)']/ancestor::a[1]",
    "//*[normalize-space()='公文(學校)']/ancestor::*[@role='link' or @role='button'][1]",
    "//*[normalize-space()='公文(學校)']/ancestor::div[contains(@class, 'card') or contains(@class, 'tile') or contains(@class, 'block')][1]",
    "//*[normalize-space()='公文(學校)']",
    "//*[contains(normalize-space(), '公文(學校)')]",
]


def _click_first_match(driver, xpaths, label, timeout=8):
    """依序嘗試 XPath 候選清單，找到第一個可見元素就用 JS 點下去（繞遮罩）。"""
    wait = WebDriverWait(driver, timeout)
    for xp in xpaths:
        try:
            el = wait.until(EC.presence_of_element_located((By.XPATH, xp)))
            if not el.is_displayed():
                continue
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)
            print(f"      OK：點到 {label}（XPath: {xp}）")
            return True
        except TimeoutException:
            continue
        except Exception as e:
            print(f"      x  {label} 點擊例外：{type(e).__name__}: {e}")
            continue
    print(f"[ERROR] {label} 全部 XPath 都失敗")
    return False


def click_document(driver=None):
    """點擊 TAIPEION 入口網儀表板上的「公文(學校)」方塊。

    參數：
        driver: 既有 Selenium WebDriver；若為 None 則自動呼叫 login_taipeion_selenium 重新登入。
    回傳：
        True 表示已點到目標；False 表示失敗。
    """
    own_driver = False
    if driver is None:
        print("[click_document] 未提供 driver，先呼叫 login_taipeion_selenium 取得登入 session...")
        from taipeion_login_selenium import login_taipeion_selenium
        driver = login_taipeion_selenium(return_driver=True)
        own_driver = True
        if driver is None:
            print("[ERROR] 登入失敗，無法點公文")
            return False

    print("[click_document] 等儀表板載入後點『公文(學校)』...")
    # 跳轉到 TAIPEION 入口後儀表板需要時間渲染（API 抓未讀數）— 給 8 秒緩衝
    if not _click_first_match(driver, DOCUMENT_XPATHS, "公文(學校) 方塊", timeout=8):
        print("[click_document] 點擊失敗 — 列印目前頁面狀態以利除錯：")
        try:
            print(f"      URL：{driver.current_url}")
            print(f"      標題：{driver.title}")
        except Exception:
            pass
        return False

    # 點擊後可能會跳新分頁或同分頁導向公文系統，等一下再印狀態
    time.sleep(3)
    try:
        # 若公文系統開在新分頁，把焦點切過去（最後一個 handle）
        if len(driver.window_handles) > 1:
            driver.switch_to.window(driver.window_handles[-1])
            print(f"[click_document] 已切換至新分頁")
        print(f"[click_document] 當前 URL：{driver.current_url}")
        print(f"[click_document] 當前標題：{driver.title}")
    except Exception as e:
        print(f"[click_document] 讀狀態失敗：{e}")

    print("[完成] 公文方塊點擊流程結束。")
    # 獨立執行時保持 Chrome 開啟讓使用者繼續操作（與 login_taipeion_selenium 的 detach 行為一致）
    if own_driver:
        print("[click_document] Chrome 保持開啟，請手動關閉。")
    return True


if __name__ == "__main__":
    click_document()
