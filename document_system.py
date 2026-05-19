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

# 左側 sidebar「待簽收(N)」menu item 的 XPath 候選。文字格式為「待簽收(1)」，
# 不像催辦訊息的「催辦訊息0」，數字外有括號。
PENDING_SIGNOFF_XPATHS = [
    "//a[contains(normalize-space(), '待簽收')]",
    "//*[contains(normalize-space(), '待簽收')]/ancestor::a[1]",
    "//*[contains(normalize-space(), '待簽收')]/ancestor::*[@role='link' or @role='menuitem' or @role='button'][1]",
    "//*[contains(normalize-space(), '待簽收')]/ancestor::li[1]",
    "//*[contains(normalize-space(), '待簽收')]",
]

# 待簽收清單表頭的「全選 checkbox」XPath 候選（緊鄰「序號」欄位的 input）。
SELECT_ALL_CHECKBOX_XPATHS = [
    "//tr[.//th[contains(normalize-space(), '序號')]]//input[@type='checkbox']",
    "//th[contains(normalize-space(), '序號')]/preceding-sibling::th[1]//input[@type='checkbox']",
    "//th[contains(normalize-space(), '序號')]//input[@type='checkbox']",
    "//thead//input[@type='checkbox']",
    # 最後 fallback：頁面上第一個 checkbox（風險較高，最後才試）
    "(//input[@type='checkbox'])[1]",
]

# 表格上方亮青色「簽收」按鈕 XPath 候選。需精確匹配「簽收」避免誤點旁邊的「退文」。
SIGNOFF_BUTTON_XPATHS = [
    "//button[normalize-space()='簽收']",
    "//a[normalize-space()='簽收']",
    "//input[@type='button' and @value='簽收']",
    "//*[normalize-space()='簽收' and (self::button or @role='button')]",
    "//*[normalize-space()='簽收']/ancestor::button[1]",
    "//*[normalize-space()='簽收']/ancestor::a[1]",
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


def _get_pending_signoff_count(driver, timeout=10):
    """讀左側 sidebar「待簽收(N)」的 N。格式有括號，例如「待簽收(1)」。

    策略與 _get_urgent_message_count 同：先找含「待簽收」字串的最內層元素，再
    1. regex 抓「待簽收\\s*(\\s*([\\d,]+)\\s*)」
    2. fallback 在 sibling / parent 找純數字元素（少見，因為待簽收的數字幾乎
       一定跟著 label 在同一個 text node）

    回傳：
        int >= 0 → 判讀成功
        -1       → 找不到 label / 無法 parse（呼叫端保守不點）
    """
    wait = WebDriverWait(driver, timeout)
    label_xpath = "//*[contains(normalize-space(), '待簽收')]"
    try:
        candidates = wait.until(EC.presence_of_all_elements_located((By.XPATH, label_xpath)))
    except TimeoutException:
        print("[WARN] 找不到「待簽收」label，無法判讀數字")
        return -1

    label_el = None
    for el in candidates:
        try:
            if not el.is_displayed():
                continue
            inner = el.find_elements(By.XPATH, ".//*[contains(normalize-space(), '待簽收')]")
            if not inner:
                label_el = el
                break
        except Exception:
            continue
    if label_el is None:
        label_el = candidates[0] if candidates else None
    if label_el is None:
        print("[WARN] 找不到可用的「待簽收」label 元素")
        return -1

    # 策略 1：regex 抓「待簽收(N)」括號內數字
    try:
        txt = (label_el.text or "").strip()
        m = re.search(r'待簽收\s*\(\s*([\d,]+)\s*\)', txt)
        if m:
            n = int(m.group(1).replace(",", ""))
            print(f"      OK：讀到待簽收數 = {n}（來源文字「{txt}」）")
            return n
    except Exception:
        pass

    # 策略 2：fallback 找鄰近純數字元素
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
                if not txt or txt == "待簽收":
                    continue
                # 容許 "(1)" 或純 "1"
                m = re.fullmatch(r"\(?\s*([\d,]+)\s*\)?", txt)
                if m:
                    n = int(m.group(1).replace(",", ""))
                    print(f"      OK：讀到待簽收數 = {n}（來源文字「{txt}」）")
                    return n
            except Exception:
                continue

    print("[WARN] 找到「待簽收」label 但無法 parse 數字")
    return -1


def _click_pending_signoff(driver, timeout=10):
    """點選左側 sidebar「待簽收」menu item。

    回傳 True 表示點到，False 表示所有 XPath 都失敗。同 _click_urgent_message
    套路，JS click 繞遮罩。
    """
    wait = WebDriverWait(driver, timeout)
    for xp in PENDING_SIGNOFF_XPATHS:
        try:
            el = wait.until(EC.presence_of_element_located((By.XPATH, xp)))
            if not el.is_displayed():
                continue
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)
            print(f"      OK：點到「待簽收」（XPath: {xp}）")
            return True
        except TimeoutException:
            continue
        except Exception as e:
            print(f"      x  「待簽收」XPath {xp} 例外：{type(e).__name__}: {e}")
            continue
    print("[ERROR] 「待簽收」全部 XPath 都失敗")
    return False


def _try_check_checkbox(driver, el):
    """確保單一 checkbox 為勾選狀態，回傳是否成功（是否被真實 click event 勾起來）。

    為何不直接 JS 設 `el.checked = true`：實測會說謊。Vue / React / Ant Design 等
    客製 checkbox 的點擊 handler 綁在 wrapper（label / 外層 span / 外層 div），
    不在隱藏的 <input> 上。直接設 input.checked 只更新 DOM property，框架的內部
    state 完全沒變，畫面 ✓ 不出現，下一步點「簽收」會被當「沒選任何 row」拒絕。
    is_selected() 仍然回 True 因為它讀的是 DOM .checked — 報告也跟著說謊。

    本函式只用「真實 click event」策略，依序試六種點擊目標：
      1. input 元素 — Selenium 原生 click
      2. input 元素 — JS click（繞 opacity:0 / 遮罩）
      3. 最近的 <label> ancestor — JS click（HTML 規定 label click 會 forward 到 input）
      4. parent[1] — JS click（cover wrapper 綁在直接父元素的客製 checkbox）
      5. parent[2] — JS click
      6. parent[3] — JS click

    任一策略後 is_selected() 為 True 就回 True。全部失敗回 False（不再嘗試 JS 設
    checked = true 蒙混過關）。
    """
    try:
        if el.is_selected():
            return True
    except Exception:
        return False

    targets = [("input native", el, "native"), ("input JS", el, "js")]
    try:
        label = el.find_element(By.XPATH, "./ancestor::label[1]")
        targets.append(("label", label, "js"))
    except Exception:
        pass
    for level in range(1, 4):
        try:
            anc = el.find_element(By.XPATH, "/".join([".."] * level))
            targets.append((f"parent[{level}]", anc, "js"))
        except Exception:
            break

    for name, target, method in targets:
        try:
            if method == "native":
                target.click()
            else:
                driver.execute_script("arguments[0].click();", target)
            time.sleep(0.2)
            if el.is_selected():
                print(f"        勾選成功 (策略: {name})")
                return True
        except Exception:
            continue
    return False


def _check_select_all(driver, timeout=10):
    """確保「待簽收」清單上所有 checkbox 都呈勾選狀態。

    策略：蒐集頁面上所有相關的 input[type=checkbox]（先 SELECT_ALL_CHECKBOX_XPATHS
    精確定位，找不到再退讓到「table 內所有」與「頁面所有」），對每個未勾的呼叫
    _try_check_checkbox 試三種 click strategy。

    為何不只點 header「全選」：實測 header checkbox 行為不確定（custom CSS 把 input
    設 opacity:0、framework binding 不 cascade、單一 XPath 命不中）。把每個 row 都
    勾起來是最 robust 的做法，end state 一致為「全部已勾」，不受 header 行為影響。

    回傳 True 表示最終至少一個 checkbox 為勾選狀態。
    """
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, "//input[@type='checkbox']"))
        )
    except TimeoutException:
        print("[ERROR] 頁面上找不到任何 input[type=checkbox]")
        return False

    # 蒐集候選：精確 XPaths 優先，再 table 內，再全頁
    candidate_xpaths = SELECT_ALL_CHECKBOX_XPATHS + [
        "//table//input[@type='checkbox']",
        "//input[@type='checkbox']",
    ]
    seen_ids = set()
    targets = []
    for xp in candidate_xpaths:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                el_id = id(el)
                if el_id not in seen_ids:
                    seen_ids.add(el_id)
                    targets.append(el)
        except Exception:
            continue

    print(f"      蒐集到 {len(targets)} 個 checkbox 候選，逐個確認/勾選...")
    successful = 0
    for el in targets:
        if _try_check_checkbox(driver, el):
            successful += 1

    if successful == 0:
        print("[ERROR] 沒有任何 checkbox 能被勾選。診斷前 5 個元素 + parent wrapper：")
        for i, el in enumerate(targets[:5]):
            try:
                info = driver.execute_script("""
                    var el = arguments[0];
                    var p1 = el.parentElement;
                    var p2 = p1 ? p1.parentElement : null;
                    return {
                        input: el.outerHTML,
                        parent1: p1 ? p1.outerHTML : null,
                        parent2: p2 ? p2.outerHTML : null,
                    };
                """, el) or {}
                print(f"      [{i+1}] input  : {(info.get('input') or '')[:200]}")
                print(f"           parent1: {(info.get('parent1') or '')[:300]}")
                print(f"           parent2: {(info.get('parent2') or '')[:400]}")
            except Exception as e:
                print(f"      [{i+1}] dump 失敗：{type(e).__name__}: {e}")
        return False

    print(f"      OK：{successful}/{len(targets)} 個 checkbox 已為勾選狀態")
    return True


def _click_signoff_button(driver, timeout=10):
    """點選表格上方亮青色的「簽收」按鈕。

    **重要**：這個動作會改變公文狀態（待簽收 → 承辦中），沒有 admin 介入無法復原。
    呼叫端應於本函式呼叫前印明顯警告。

    回傳 True 表示點到，False 表示所有 XPath 都失敗。
    """
    wait = WebDriverWait(driver, timeout)
    for xp in SIGNOFF_BUTTON_XPATHS:
        try:
            el = wait.until(EC.presence_of_element_located((By.XPATH, xp)))
            if not el.is_displayed():
                continue
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)
            print(f"      OK：點到「簽收」按鈕（XPath: {xp}）")
            return True
        except TimeoutException:
            continue
        except Exception as e:
            print(f"      x  「簽收」XPath {xp} 例外：{type(e).__name__}: {e}")
            continue
    print("[ERROR] 「簽收」按鈕全部 XPath 都失敗")
    return False


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
        2. 讀右上「催辦訊息N」數字
           - > 0：點進催辦頁，sleep 2 印 URL/title 觀察
           - = 0：跳過
           - 判讀失敗 (-1)：保守不點，印警告繼續
        3. 讀左側 sidebar「待簽收(N)」數字（不管催辦結果如何都檢查 — sidebar
           是常駐元件，導航到催辦頁之後仍然看得到）
           - > 0：點進待簽收清單
           - = 0：跳過
           - 判讀失敗 (-1)：保守不點，印警告繼續
    回傳 True 表示流程跑完（即使部分項目跳過或保守不點）；False 表示前置檢查失敗
    或任一點擊行動失敗。
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

    # ── 催辦訊息 ────────────────────────────────────────────────────────────
    print("[document_system] 讀「催辦訊息」待辦數...")
    urgent_count = _get_urgent_message_count(driver)
    if urgent_count < 0:
        print("[document_system] 無法判讀催辦訊息數，保守不點，繼續下一步。")
    elif urgent_count == 0:
        print("[document_system] 催辦訊息 = 0，無待辦催辦，跳過點擊。")
    else:
        print(f"[document_system] 催辦訊息 = {urgent_count}，點選進入催辦頁...")
        if not _click_urgent_message(driver):
            return False
        time.sleep(2)
        try:
            print(f"[document_system] 催辦頁 URL：{driver.current_url}")
            print(f"[document_system] 催辦頁標題：{driver.title}")
        except Exception as e:
            print(f"[document_system] 讀狀態失敗：{type(e).__name__}: {e}")

    # ── 待簽收 ─────────────────────────────────────────────────────────────
    print("[document_system] 讀左側 sidebar「待簽收」數...")
    signoff_count = _get_pending_signoff_count(driver)
    if signoff_count < 0:
        print("[document_system] 無法判讀待簽收數，保守不點，繼續下一步。")
    elif signoff_count == 0:
        print("[document_system] 待簽收 = 0，無待簽收公文，跳過點擊。")
    else:
        print(f"[document_system] 待簽收 = {signoff_count}，點選進入待簽收清單...")
        if not _click_pending_signoff(driver):
            return False
        time.sleep(2)
        try:
            print(f"[document_system] 待簽收頁 URL：{driver.current_url}")
            print(f"[document_system] 待簽收頁標題：{driver.title}")
        except Exception as e:
            print(f"[document_system] 讀狀態失敗：{type(e).__name__}: {e}")

        # 待簽收清單載入後：勾全選 → 點簽收按鈕
        # **警告**：簽收會改變公文狀態（待簽收 → 承辦中），無 admin 介入無法復原
        print(f"[WARN] 即將自動執行：勾選 {signoff_count} 筆待簽收 + 點「簽收」按鈕")
        print(f"[WARN] 簽收會把公文從「待簽收」狀態改為「承辦中」，無法復原")
        if not _check_select_all(driver):
            print("[document_system] 全選 checkbox 失敗，不執行簽收。請手動處理。")
        else:
            if not _click_signoff_button(driver):
                print("[document_system] 找不到「簽收」按鈕，請手動處理。")
            else:
                # 簽收後等系統回應（可能跳 JS confirm 由 unhandledPromptBehavior=accept
                # 自動接受、或跳轉到下一頁、或就地刷新清單）
                time.sleep(3)
                try:
                    print(f"[document_system] 簽收後 URL：{driver.current_url}")
                    print(f"[document_system] 簽收後標題：{driver.title}")
                except Exception as e:
                    print(f"[document_system] 讀狀態失敗：{type(e).__name__}: {e}")

    # TODO: 後續工作（逐筆點進公文做承辦動作、退文判斷等）在此擴充
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
    # 把 stdout/stderr 同步落地到 run.log — entry point 開頭就 setup，確保 Chrome
    # 預清理 / 啟動 / 導航等每行 print 都進 log
    from taipeion_login_selenium import _setup_stdout_logging
    _setup_stdout_logging()
    driver = _standalone_open_chrome_at_edoc()
    if driver is None:
        sys.exit(1)
    ok = process_document_system(driver)
    sys.exit(0 if ok else 1)
