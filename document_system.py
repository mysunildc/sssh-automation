"""
document_system.py
公文系統內的後續處理流程 — 假設 driver 已導航到 edoc.gov.taipei 公文首頁（已登入）。

呼叫方式：
1) 從 main.py 串接：click_document_card 回 True 後 main() 直接呼叫
     process_document_system(driver)
2) 單獨執行（測試用，跳過登入流程）：
     C:\\Python314\\python.exe document_system.py
   會用同一個 Selenium profile 開 Chrome、直接導航到 edoc 首頁；session 過期就
   提示去跑 main.py 重登。

第一版只做：點選 edoc 首頁右上方的「催辦訊息」badge。後續擴充寫進對應的
helper（_open_first_document、_handle_document_list 等）。
"""

import re
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

sys.stdout.reconfigure(encoding='utf-8')

# edoc 公文首頁。standalone 模式會直接 driver.get 這個 URL。
EDOC_HOME_URL = "https://edoc.gov.taipei/tcqb/home/default.jsp?inLine=Y"

# 「催辦訊息」badge 的 XPath 候選。實測 DOM 結構未明，由窄到寬列幾個 fallback，
# 邏輯同 click_document.py 的 DOCUMENT_XPATHS。
URGENT_MSG_XPATHS = [
    "//a[contains(normalize-space(), '催辦訊息')]",
    "//*[normalize-space()='催辦訊息']/ancestor::a[1]",
    "//*[normalize-space()='催辦訊息']/ancestor::*[@role='link' or @role='button'][1]",
    "//*[normalize-space()='催辦訊息']/ancestor::div[contains(@class, 'badge') or contains(@class, 'btn') or contains(@class, 'tag') or contains(@class, 'pill')][1]",
    "//*[normalize-space()='催辦訊息']",
    "//*[contains(normalize-space(), '催辦訊息')]",
]


def _get_urgent_message_count(driver, timeout=10):
    """讀「催辦訊息」badge 後面的數字。

    DOM 不確定是「催辦訊息」與「N」分在兩個 span 還是同一個 text node，所以雙策略：
    1. 找含「催辦訊息」的最內層元素 → 用 regex 抓自身 text 裡「催辦訊息」後面的數字
       （能 cover「催辦訊息0」同 text node 與 a/span 包子 span 的兩種情況）
    2. 策略 1 抓不到 → 學 click_document._get_document_count 在 label 周邊找純數字元素

    回傳：
        int >= 0 → 判讀成功
        -1       → 找不到 label / 無法 parse（呼叫端保守不點）
    """
    wait = WebDriverWait(driver, timeout)
    label_xpath = "//*[contains(normalize-space(), '催辦訊息')]"
    try:
        candidates = wait.until(EC.presence_of_all_elements_located((By.XPATH, label_xpath)))
    except TimeoutException:
        print("[WARN] 找不到「催辦訊息」label，無法判讀數字")
        return -1

    # 取最內層元素：自身含「催辦訊息」字串、但沒有後代元素也含此字串。
    # 用 contains(normalize-space()) 抓會把所有外層 ancestor 也抓進來，要過濾。
    label_el = None
    for el in candidates:
        try:
            if not el.is_displayed():
                continue
            inner = el.find_elements(By.XPATH, ".//*[contains(normalize-space(), '催辦訊息')]")
            if not inner:
                label_el = el
                break
        except Exception:
            continue
    if label_el is None:
        # 沒找到「葉子」元素，退一步用第一個 candidate
        label_el = candidates[0] if candidates else None
    if label_el is None:
        print("[WARN] 找不到可用的「催辦訊息」label 元素")
        return -1

    # 策略 1：label 自身 text 內 regex 抓「催辦訊息」後面的數字（容許千分位逗號）
    try:
        txt = (label_el.text or "").strip()
        m = re.search(r'催辦訊息\s*([\d,]+)', txt)
        if m:
            n = int(m.group(1).replace(",", ""))
            print(f"      OK：讀到催辦訊息數 = {n}（來源文字「{txt}」）")
            return n
    except Exception:
        pass

    # 策略 2：label 周邊找純數字元素（同 click_document._get_document_count 邏輯）
    relative_xpaths = [
        "./following-sibling::*[1]",
        "./parent::*/*[self::span or self::div or self::strong or self::b or self::p]",
        "./parent::*/parent::*//*[self::span or self::div or self::strong or self::b or self::p]",
    ]
    seen_ids = set()
    for rel_xp in relative_xpaths:
        try:
            els = label_el.find_elements(By.XPATH, rel_xp)
        except Exception:
            continue
        for el in els:
            try:
                el_id = el.id if hasattr(el, "id") else id(el)
                if el_id in seen_ids:
                    continue
                seen_ids.add(el_id)
                if not el.is_displayed():
                    continue
                txt = (el.text or "").strip()
                if not txt or txt == "催辦訊息":
                    continue
                m = re.fullmatch(r"[\d,]+", txt)
                if m:
                    n = int(txt.replace(",", ""))
                    print(f"      OK：讀到催辦訊息數 = {n}（來源文字「{txt}」）")
                    return n
            except Exception:
                continue

    print("[WARN] 找到「催辦訊息」label 但無法 parse 數字")
    return -1


def _click_urgent_message(driver, timeout=10):
    """點選 edoc 公文首頁的「催辦訊息」badge。

    回傳 True 表示點到，False 表示所有 XPath 都失敗。用 JS click 繞遮罩，與
    click_document._click_document_card 同套路；不抓 href 同分頁導航，因為催辦
    可能是 modal / 同頁切換而不是新分頁，目前先讓它走元素的原生行為觀察結果。
    """
    wait = WebDriverWait(driver, timeout)
    for xp in URGENT_MSG_XPATHS:
        try:
            el = wait.until(EC.presence_of_element_located((By.XPATH, xp)))
            if not el.is_displayed():
                continue
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)
            print(f"      OK：點到「催辦訊息」（XPath: {xp}）")
            return True
        except TimeoutException:
            continue
        except Exception as e:
            print(f"      x  「催辦訊息」XPath {xp} 例外：{type(e).__name__}: {e}")
            continue
    print("[ERROR] 「催辦訊息」全部 XPath 都失敗")
    return False


def process_document_system(driver):
    """公文系統處理主入口。driver 必須已導航到 edoc 公文首頁。

    流程：
        1. 確認 current_url 在 edoc.gov.taipei
        2. 讀「催辦訊息」待辦數
           - = 0：無待辦，跳過點擊，回 True（流程正常完成）
           - > 0：點進催辦頁，sleep 2 印 URL/title 觀察
           - 判讀失敗 (-1)：保守不點，回 False（同 click_document_card 策略）
    回傳 True 表示流程跑完；False 表示前置檢查失敗或判讀失敗或點擊失敗。
    """
    print("[document_system] 開始處理公文系統...")

    try:
        current = driver.current_url
    except Exception as e:
        print(f"[ERROR] 讀 current_url 失敗：{type(e).__name__}: {e}")
        return False

    if "edoc.gov.taipei" not in current:
        print(f"[ERROR] 當前 URL 不在 edoc：{current}")
        return False

    print("[document_system] 讀「催辦訊息」待辦數...")
    count = _get_urgent_message_count(driver)

    if count == 0:
        print("[document_system] 催辦訊息 = 0，無待辦催辦，跳過點擊。")
        print("[完成] 公文系統處理流程結束。")
        return True
    if count < 0:
        print("[document_system] 無法判讀催辦訊息數，保守不點，請手動處理。")
        return False

    print(f"[document_system] 催辦訊息 = {count}，點選進入催辦頁...")
    if not _click_urgent_message(driver):
        return False

    # 等頁面反應，觀察點完去到哪
    time.sleep(2)
    try:
        print(f"[document_system] 點完後 URL：{driver.current_url}")
        print(f"[document_system] 點完後標題：{driver.title}")
    except Exception as e:
        print(f"[document_system] 讀狀態失敗：{type(e).__name__}: {e}")

    # TODO: 後續工作（讀催辦清單、逐筆點進公文等）在此擴充
    print("[完成] 公文系統處理流程結束。")
    return True


def _standalone_open_chrome_at_edoc():
    """單獨執行時開 Chrome 並導航到 edoc 公文首頁。

    流程：
    1. 預清理 Selenium Chrome（避免 profile 被前一次 detach 的 Chrome 鎖住）
    2. 用 _build_chrome_options() 建 options，與 main.py 完全一致
    3. driver.get(EDOC_HOME_URL)，sleep 2 後檢查 current_url
    4. 若被導去 login.gov.taipei / sso → session 過期，印提示後回 None
    回傳 driver 或 None。

    注意：失敗路徑 return None 時故意不呼叫 driver.quit() — options 帶 detach=True，
    Chrome 會留著；下次跑時 _close_selenium_chrome_only 會清掉。與
    login_taipeion_selenium 的 lifecycle 模式一致。
    """
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException

    from taipeion_login_selenium import _build_chrome_options, _close_selenium_chrome_only

    print("[standalone] 預清理上一次 Selenium Chrome (若有)...")
    _close_selenium_chrome_only()

    print("[standalone 1/2] 啟動 Chrome（用 Selenium profile）...")
    options = _build_chrome_options()
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(15)
        driver.set_script_timeout(10)
    except WebDriverException as e:
        print(f"[FATAL] 無法啟動 Chrome：{str(e)[:300]}")
        return None

    print(f"[standalone 2/2] 導航到 {EDOC_HOME_URL}")
    try:
        driver.get(EDOC_HOME_URL)
    except TimeoutException:
        print("      [警告] 頁面載入超時，繼續執行")

    # 給 redirect 一點時間（session 過期會被導去 login.gov.taipei 或 sso）
    time.sleep(2)
    try:
        current = driver.current_url
    except Exception as e:
        print(f"[FATAL] 讀 current_url 失敗：{type(e).__name__}: {e}")
        return None

    if "edoc.gov.taipei" not in current:
        print(f"[ERROR] 沒進到 edoc，被導向：{current}")
        print("        session 可能過期，請先執行 main.py 重新登入")
        return None

    print(f"      OK：已在 edoc — {current}")
    return driver


if __name__ == "__main__":
    driver = _standalone_open_chrome_at_edoc()
    if driver is None:
        sys.exit(1)
    ok = process_document_system(driver)
    sys.exit(0 if ok else 1)
