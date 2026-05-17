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
  - 螢幕鎖定下的執行
  - 失敗重試 / 截圖儲存

設計重點：
  使用 Selenium 專用 Chrome User Data 目錄（非預設位置），
  繞過 Chrome 136+ 對「預設 User Data dir 啟用 DevTools port」的安全限制。
  此目錄首次執行 Chrome 會自動建立，不影響使用者真正的 Profile 2。
  使用者需在此 profile 內手動登入一次（瀏覽器會儲存密碼），之後即可自動帶入。

執行方式：
    C:\\Python314\\python.exe -m pip install selenium
    C:\\Python314\\python.exe selenium_login_test.py

執行後請觀察：
  A. 是否成功點到「自然人憑證」分頁（畫面切換）
  B. 是否成功點到「登入」按鈕
  C. 結束時自動存截圖 after_login_click.png 供檢查當下畫面
"""

import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

import pyautogui
from PIL import ImageGrab
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, WebDriverException

pyautogui.FAILSAFE = False

URL = "https://login.gov.taipei/login.php"

# Selenium 專用 Chrome User Data 目錄（非預設位置，繞過 Chrome 136+ 自動化限制）
# 首次執行 Chrome 會自動建立此目錄。使用者於此 profile 手動登入一次後，
# 之後執行可自動帶入儲存的密碼。
USER_DATA_DIR = os.path.expandvars(r"%LOCALAPPDATA%\Chrome-Selenium\User Data")
PROFILE_DIR = "Default"

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


def mark_profile_clean_exit():
    """
    將 profile 的 Preferences 標記為正常退出，跳過「Chrome 未正確關閉，是否還原網頁」對話框。
    Selenium 強制接管 profile 時 Chrome 會把上次視為異常終止，需要這個處理。
    """
    prefs_path = os.path.join(USER_DATA_DIR, PROFILE_DIR, "Preferences")
    if not os.path.isfile(prefs_path):
        print(f"      [警告] 找不到 Preferences：{prefs_path}")
        return
    try:
        with open(prefs_path, "r", encoding="utf-8") as f:
            prefs = json.load(f)
        profile = prefs.setdefault("profile", {})
        profile["exit_type"] = "Normal"
        profile["exited_cleanly"] = True
        with open(prefs_path, "w", encoding="utf-8") as f:
            json.dump(prefs, f)
        print("      Preferences 已標記為正常退出，跳過還原網頁提示。")
    except Exception as e:
        print(f"      [警告] 無法修改 Preferences：{e}")


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


def click_chrome_allow_button(driver, timeout=6):
    """
    偵測並點擊 Chrome 站台權限對話框的「允許」按鈕。

    這個對話框是 Chrome 瀏覽器級 UI（不在頁面 DOM 內），Selenium 無法直接點擊，
    必須以螢幕座標 + pyautogui 處理。

    搜尋邏輯：在 URL bar 下方左側區域找 Chrome 主要按鈕的淺藍色像素群集，取其中心點擊。
    Chrome 對話框允許後會記在 profile 內，下次同 origin 不再跳。
    """
    pos = driver.get_window_position()
    size = driver.get_window_size()
    x0 = pos['x']
    y0 = pos['y'] + 95            # URL bar 高度估計
    x1 = x0 + min(700, size['width'])
    y1 = y0 + 260
    print(f"      搜尋區域：({x0},{y0})~({x1},{y1})")

    start = time.time()
    while time.time() - start < timeout:
        img = ImageGrab.grab(bbox=(x0, y0, x1, y1))
        pixels = img.load()
        w, h = img.size
        blue_pts = []
        for y in range(h):
            for x in range(w):
                r, g, b = pixels[x, y][:3]
                # Chrome 主要動作鈕的淺藍背景（約 #C7DEFF 範圍）
                if b > 230 and g > 200 and r < 225 and (b - r) > 25 and (b - g) > 5:
                    blue_pts.append((x, y))
        if len(blue_pts) >= 200:
            cx = sum(p[0] for p in blue_pts) // len(blue_pts)
            cy = sum(p[1] for p in blue_pts) // len(blue_pts)
            click_x, click_y = x0 + cx, y0 + cy
            pyautogui.click(click_x, click_y)
            print(f"      ✓ 已點擊「允許」於螢幕座標 ({click_x},{click_y})（{len(blue_pts)} 個藍色像素）")
            return True
        time.sleep(0.3)

    print("      x  逾時未偵測到「允許」按鈕（可能 Chrome 已記住權限不再跳對話框）")
    return False


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
    print(f"[0/4] 使用 Selenium 專用 profile：{PROFILE_DIR}")
    print(f"      路徑：{USER_DATA_DIR}")
    profile_path = os.path.join(USER_DATA_DIR, PROFILE_DIR)
    if not os.path.isdir(profile_path):
        print(f"      首次執行 — Chrome 將自動建立此目錄")
        os.makedirs(USER_DATA_DIR, exist_ok=True)
    else:
        mark_profile_clean_exit()

    options = Options()
    options.add_argument(f"--user-data-dir={USER_DATA_DIR}")
    options.add_argument(f"--profile-directory={PROFILE_DIR}")
    options.add_argument("--start-maximized")
    # 隱藏「Chrome 目前受到自動測試軟體控制」infobar
    options.add_argument("--disable-blink-features=AutomationControlled")
    # 跑完不要關閉瀏覽器，方便人工觀察 / 接手登入
    options.add_experimental_option("detach", True)
    # 抑制 USB / Bluetooth log + 移除 enable-automation 旗標（infobar 來源）
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)

    print("[1/5] 啟動 Chrome（Selenium Manager 自動下載對應 ChromeDriver）...")
    try:
        driver = webdriver.Chrome(options=options)
    except WebDriverException as e:
        msg = str(e)
        print(f"[FATAL] 無法啟動 Chrome。完整錯誤訊息：")
        print("─" * 60)
        print(msg)
        print("─" * 60)
        if "user data directory is already in use" in msg.lower():
            print("提示：請先關閉所有 1504@sssh.tp.edu.tw（Profile 2）的 Chrome 視窗再執行。")
        return

    try:
        print(f"[2/5] 開啟 {URL}")
        driver.get(URL)
        time.sleep(2)

        # Profile 2 可能還原多個 tab，先列印全部 window/tab 資訊以便除錯
        handles_before = list(driver.window_handles)
        print(f"      啟動後共 {len(handles_before)} 個 window/tab：")
        target = None
        for h in handles_before:
            driver.switch_to.window(h)
            cur_url = driver.current_url
            cur_title = driver.title
            print(f"        - [{h[:8]}...] title='{cur_title}' url={cur_url}")
            if "login.gov.taipei" in cur_url and target is None:
                target = h

        if target is None:
            print("      [警告] 沒有任何 tab 在 login.gov.taipei，於第一個 tab 重新導向...")
            driver.switch_to.window(handles_before[0])
            driver.get(URL)
            target = handles_before[0]
        else:
            extras = [h for h in handles_before if h != target]
            if extras:
                print(f"      偵測到 {len(extras)} 個額外 tab（session restore），關閉以保持單一視窗")
                for h in extras:
                    driver.switch_to.window(h)
                    driver.close()
                driver.switch_to.window(target)

        # 強制把目標 tab 視覺上拉到最前面
        try:
            driver.execute_script("window.focus();")
        except Exception:
            pass
        try:
            driver.maximize_window()
        except Exception:
            pass

        print(f"      切換後 URL：{driver.current_url}")
        print(f"      頁面標題：{driver.title}")

        print("[3/5] 點選『自然人憑證』分頁...")
        if not try_click(driver, CERT_TAB_XPATHS, "自然人憑證分頁"):
            dump_page_for_debug(driver)
            return
        time.sleep(1.5)

        print("[4/5] 點選『登入』按鈕...")
        if not try_click(driver, LOGIN_BTN_XPATHS, "登入按鈕"):
            dump_page_for_debug(driver)
            return
        time.sleep(2)

        print("[5/5] 偵測 Chrome 站台權限對話框並自動點『允許』...")
        click_chrome_allow_button(driver)
        time.sleep(1.5)

        # 存截圖供使用者檢查當下畫面
        screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "after_login_click.png")
        try:
            driver.save_screenshot(screenshot_path)
            print(f"\n[截圖] {screenshot_path}")
        except Exception as e:
            print(f"\n[截圖] 儲存失敗：{e}")

        print(f"      點擊後 URL：{driver.current_url}")
        print(f"      頁面標題：{driver.title}")
        print("      瀏覽器保持開啟，可接手人工完成或關閉。")

    except Exception as e:
        print(f"[ERROR] 流程中斷：{e}")
        dump_page_for_debug(driver)


if __name__ == "__main__":
    main()
