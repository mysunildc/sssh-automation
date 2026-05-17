"""
selenium_login_test.py
最小 Selenium 範例 — 驗證能否走完 TAIPEION 登入流程的前兩步。

實驗目的（第一階段）：
  1. 確認 Selenium 能在 Python 3.14 + 現有 Chrome 啟動
  2. 確認可定位並點擊「自然人憑證」分頁（不靠像素，改用 DOM）
  3. 確認可定位並點擊「登入」按鈕
  4. 觀察 Windows 憑證選擇對話框的出現時機

本範例不處理（保留至第二階段再評估）：
  - AutoSelectCertificateForUrls 群組原則（讓憑證對話框自動選取）
  - 使用既有 Chrome Profile 2（避免與已開啟視窗衝突）
  - 螢幕鎖定下的執行
  - 失敗重試 / 截圖儲存

執行方式：
    C:\\Python314\\python.exe -m pip install selenium
    C:\\Python314\\python.exe selenium_login_test.py

執行後請觀察：
  A. 是否成功點到「自然人憑證」分頁（畫面切換）
  B. 是否成功點到「登入」按鈕
  C. 是否跳出 Windows 憑證選擇對話框（若有讀卡機 + 卡片）
"""

import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, WebDriverException

URL = "https://login.gov.taipei/login.php"

# 嘗試多組 XPath，依序測試
CERT_TAB_XPATHS = [
    "//a[contains(., '自然人憑證')]",
    "//button[contains(., '自然人憑證')]",
    "//li[contains(., '自然人憑證')]",
    "//*[@role='tab' and contains(., '自然人憑證')]",
    "//*[contains(text(), '自然人憑證')]",
]

LOGIN_BTN_XPATHS = [
    "//button[normalize-space()='登入']",
    "//input[@type='submit' and contains(@value, '登入')]",
    "//a[normalize-space()='登入']",
    "//button[contains(., '登入')]",
]


def try_click(driver, xpaths, label, timeout=8):
    """依序嘗試多組 XPath，回傳第一個成功點到的元素描述；全失敗則回傳 None。"""
    wait = WebDriverWait(driver, timeout)
    for xp in xpaths:
        try:
            el = wait.until(EC.element_to_be_clickable((By.XPATH, xp)))
            el.click()
            print(f"      OK：以 XPath 命中 → {xp}")
            return xp
        except TimeoutException:
            print(f"      x  XPath 失敗 → {xp}")
            continue
    print(f"[ERROR] {label} 全部 XPath 都失敗。")
    return None


def dump_page_for_debug(driver):
    """流程卡住時印出頁面標題與部分 HTML，方便調整 selector。"""
    print("\n─── 除錯資訊 ───")
    print(f"目前網址：{driver.current_url}")
    print(f"頁面標題：{driver.title}")
    try:
        html = driver.page_source
        # 只印前 2000 字，避免洗版
        snippet = html[:2000].replace("\n", " ")
        print(f"HTML 前 2000 字：\n{snippet}")
    except Exception as e:
        print(f"無法讀取 page_source：{e}")
    print("────────────────")


def main():
    options = Options()
    options.add_argument("--start-maximized")
    # 跑完不要關閉瀏覽器，方便人工觀察 / 接手登入
    options.add_experimental_option("detach", True)
    # 抑制 USB / Bluetooth 等噪音 log
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    print("[1/4] 啟動 Chrome（Selenium Manager 自動下載對應 ChromeDriver）...")
    try:
        driver = webdriver.Chrome(options=options)
    except WebDriverException as e:
        print(f"[FATAL] 無法啟動 Chrome：{e}")
        return

    try:
        print(f"[2/4] 開啟 {URL}")
        driver.get(URL)
        time.sleep(2)
        print(f"      頁面標題：{driver.title}")

        print("[3/4] 點選『自然人憑證』分頁...")
        if not try_click(driver, CERT_TAB_XPATHS, "自然人憑證分頁"):
            dump_page_for_debug(driver)
            return
        time.sleep(1.5)

        print("[4/4] 點選『登入』按鈕...")
        if not try_click(driver, LOGIN_BTN_XPATHS, "登入按鈕"):
            dump_page_for_debug(driver)
            return
        time.sleep(3)

        print("\n[完成] 已執行到憑證對話框出現的階段。")
        print("      請觀察：")
        print("        A. 是否成功切換到自然人憑證分頁？")
        print("        B. 是否成功點到登入按鈕？")
        print("        C. 是否跳出 Windows 憑證選擇對話框？")
        print("      瀏覽器保持開啟，可接手人工完成或關閉。")

    except Exception as e:
        print(f"[ERROR] 流程中斷：{e}")
        dump_page_for_debug(driver)


if __name__ == "__main__":
    main()
