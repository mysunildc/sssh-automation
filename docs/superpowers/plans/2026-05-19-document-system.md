# document_system 公文系統處理模組 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `document_system.py` 處理 edoc.gov.taipei 公文系統內的後續操作，第一版只點選右上「催辦訊息」badge，並提供 standalone 入口可單獨測試免重跑登入。

**Architecture:** 在現有 `main.py → login → click_document_card`（已導航到 edoc）之後串接 `document_system.process_document_system(driver)`。`document_system.py` 同時有 `__main__`，獨立執行時用同一個 Selenium profile 開 Chrome、直接 `driver.get(EDOC_HOME_URL)` 賭 session 還在；被導去 login 就提示退出。共享 Chrome options 與預清理函式抽到 `taipeion_login_selenium.py`。

**Tech Stack:** Python 3.14、Selenium 4.x、Windows 10、PowerShell（預清理腳本）、既有專案 import 模式（`from <module> import <func>`）。

**Spec:** [docs/superpowers/specs/2026-05-19-document-system-design.md](../specs/2026-05-19-document-system-design.md)

---

## 檔案藍圖

| 檔案 | 動作 | 責任 |
|---|---|---|
| `taipeion_login_selenium.py` | 修改 | 抽出 `_build_chrome_options()`；新增 `_close_selenium_chrome_only()`（從 main.py 搬過來） |
| `main.py` | 修改 | 移除本地 `_close_selenium_chrome_only` 改 import；`main()` 內 `click_document_card` 後接 `process_document_system` |
| `document_system.py` | 新增 | `process_document_system`、`_click_urgent_message`、`_standalone_open_chrome_at_edoc`、`__main__` |

---

## Task 1：重構 `taipeion_login_selenium.py` — 抽 `_build_chrome_options()` + 接管 `_close_selenium_chrome_only`

**Files:**
- Modify: `taipeion_login_selenium.py`（新增兩個函式、`login_taipeion_selenium` 改用 `_build_chrome_options()`）
- Modify: `main.py:20-44`（移除 `_close_selenium_chrome_only` 與模組層呼叫，改 `from taipeion_login_selenium import _close_selenium_chrome_only`）

- [ ] **Step 1.1：在 `taipeion_login_selenium.py` 加 `_close_selenium_chrome_only()` 函式（從 main.py 搬，內容不變）**

加在 `_read_pin()` 上方（檔案前段、import 區之後）：

```python
def _close_selenium_chrome_only():
    """只關閉 Selenium 相關的 chrome.exe + chromedriver.exe，不動使用者個人 Chrome。

    委派給 scripts/close-profile2-chrome.ps1：該腳本用 Get-CimInstance 過濾 command line，
    只殺帶 --user-data-dir=*Chrome-Selenium*、--remote-debugging-port 或 --test-type=webdriver
    的程序，並先 CloseMainWindow 優雅關閉再強制終止，順帶清 profile lockfile。
    這樣個人 Chrome 不會被強殺，下次手動打開不會跳「未正確關閉，要還原網頁嗎？」對話框。
    """
    import subprocess
    script_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "scripts", "close-profile2-chrome.ps1",
    )
    if not os.path.isfile(script_path):
        print(f"[WARN] 找不到 {script_path}，跳過 Chrome 預清理")
        return
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
            capture_output=True, timeout=30,
        )
    except Exception as e:
        print(f"[WARN] Chrome 預清理失敗：{e}")
```

- [ ] **Step 1.2：在 `taipeion_login_selenium.py` 加 `_build_chrome_options()` — 把 `login_taipeion_selenium` 內所有 `options.add_argument/...` 內容搬進來**

加在 `_close_selenium_chrome_only` 下方：

```python
def _build_chrome_options():
    """建構 Selenium Chrome 的 Options。

    所有 entry-point（main.py 走的 login 流程、document_system.py standalone 流程）
    共用同一份 options，避免兩邊飄移後出現「main.py OK 但 document_system 連 PNA 都
    沒關」這種詭異 bug。

    各旗標的詳細理由見對應的 inline 註解。
    """
    options = Options()
    options.page_load_strategy = "eager"
    options.add_argument(f"--user-data-dir={USER_DATA_DIR}")
    options.add_argument(f"--profile-directory={PROFILE_DIR}")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-session-crashed-bubble")
    options.add_argument("--hide-crash-restore-bubble")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--restore-last-session=false")
    options.add_argument(
        "--disable-features=LocalNetworkAccessChecks,"
        "BlockInsecurePrivateNetworkRequests,"
        "PrivateNetworkAccessRespectPreflightResults,"
        "PrivateNetworkAccessSendPreflights"
    )
    options.add_argument("--allow-running-insecure-content")
    options.add_experimental_option("detach", True)
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)
    options.set_capability("unhandledPromptBehavior", "accept")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    return options
```

- [ ] **Step 1.3：`login_taipeion_selenium()` 用新的 `_build_chrome_options()`**

把 `taipeion_login_selenium.py:441-485`（從 `options = Options()` 到 `options.set_capability("goog:loggingPrefs", ...)`）全部刪掉，只留：

```python
    options = _build_chrome_options()
```

並把原本散在這幾十行的 inline 註解整段刪掉（同樣的註解已搬到 `_build_chrome_options()` 內了，不要重複）。

- [ ] **Step 1.4：`main.py` 移除本地 `_close_selenium_chrome_only` 改 import**

把 `main.py:20-44`（`def _close_selenium_chrome_only():` 到 `_close_selenium_chrome_only()` 那一行）全部刪掉。

緊接著的 import block（原本是 `from taipeion_login import ...`）改成：

```python
from taipeion_login_selenium import login_taipeion_selenium, _close_selenium_chrome_only
from taipeion_login import login_taipeion
from click_document import click_document_card

_close_selenium_chrome_only()
```

也刪掉 `import subprocess`（main.py 不再直接用 subprocess）。檔案上方保留 `import os`、`import sys`、`sys.stdout.reconfigure(...)`。

- [ ] **Step 1.5：語法檢查**

```powershell
& "C:\Python314\python.exe" -m py_compile taipeion_login_selenium.py main.py
```

預期：無輸出（成功）。

- [ ] **Step 1.6：smoke import 驗證**

```powershell
& "C:\Python314\python.exe" -c "from taipeion_login_selenium import _build_chrome_options, _close_selenium_chrome_only; opts = _build_chrome_options(); args = opts.arguments; assert any('LocalNetworkAccessChecks' in a for a in args), 'LNA disable missing'; assert any('Chrome-Selenium' in a for a in args), 'user-data-dir missing'; print('OK args=', len(args))"
```

預期輸出：`OK args= 12`（或類似數量）— 確認 LNA disable 與 user-data-dir 都還在新函式的回傳。

- [ ] **Step 1.7：commit + push**

```powershell
git add taipeion_login_selenium.py main.py
git commit -m "重構：抽 _build_chrome_options 與 _close_selenium_chrome_only 到 taipeion_login_selenium

為 document_system.py 鋪路 — 兩個 entry point (main.py 與未來的
document_system.py standalone) 共用同一份 Chrome options 與預清理函式，
避免兩邊飄移。純重構，行為不變。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push
```

---

## Task 2：新增 `document_system.py` 核心函式（不含 standalone 入口）

**Files:**
- Create: `document_system.py`

- [ ] **Step 2.1：建立 `document_system.py`，加 module docstring + import + 常數**

```python
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

import os
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
```

- [ ] **Step 2.2：加 `_click_urgent_message(driver, timeout=10)`**

接在上面常數區之後：

```python
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
```

- [ ] **Step 2.3：加 `process_document_system(driver)`**

接在 `_click_urgent_message` 之後：

```python
def process_document_system(driver):
    """公文系統處理主入口。driver 必須已導航到 edoc 公文首頁。

    流程（第一版）：
        1. 確認 current_url 在 edoc.gov.taipei
        2. 點「催辦訊息」
        3. sleep 2 等頁面反應，印當前 URL/title 觀察
    回傳 True 表示流程跑完；False 表示前置檢查或點擊失敗。
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

    print("[document_system] 點選「催辦訊息」...")
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
```

- [ ] **Step 2.4：暫時補一個最小 `__main__` 區塊，讓 Task 2 commit 時 import 不會崩**

檔案最後加（Task 4 會替換成正式版）：

```python
if __name__ == "__main__":
    print("[ERROR] standalone 入口尚未實作（Task 4 才加）")
    sys.exit(1)
```

- [ ] **Step 2.5：語法 + import 驗證**

```powershell
& "C:\Python314\python.exe" -m py_compile document_system.py
& "C:\Python314\python.exe" -c "from document_system import process_document_system, _click_urgent_message, EDOC_HOME_URL, URGENT_MSG_XPATHS; print('OK', len(URGENT_MSG_XPATHS), 'xpaths')"
```

預期輸出：`OK 6 xpaths`

- [ ] **Step 2.6：commit + push**

```powershell
git add document_system.py
git commit -m "新增 document_system.py：公文系統處理模組（第一版只點催辦訊息）

提供 process_document_system(driver) 給 main.py 串接呼叫；driver 必須
已在 edoc 公文首頁。第一版只做：
- 確認 current_url 在 edoc.gov.taipei
- 點選右上「催辦訊息」badge（六個 fallback XPath，JS click 繞遮罩）
- sleep 2 印 URL/title 觀察點完去到哪

standalone __main__ 還沒接，下個 commit 補。

Spec: docs/superpowers/specs/2026-05-19-document-system-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push
```

---

## Task 3：`main.py` 串接 `process_document_system`

**Files:**
- Modify: `main.py:66-89`（`main()` 函式內 post_login 分支）

- [ ] **Step 3.1：修改 `main()`，`click_document_card` 回 True 後呼叫 `process_document_system`**

把 `main.py` 內現有的：

```python
    if post_login is None:
        func()
    else:
        driver = func(return_driver=True)
        if driver is None:
            print("[ERROR] 登入未完成，跳過後續動作。")
        else:
            post_login(driver)
```

改成：

```python
    if post_login is None:
        func()
    else:
        driver = func(return_driver=True)
        if driver is None:
            print("[ERROR] 登入未完成，跳過後續動作。")
        else:
            # post_login (click_document_card) 回 True 表示已點進公文系統 (edoc)；
            # 串接 document_system 進去做後續處理。
            if post_login(driver):
                from document_system import process_document_system
                process_document_system(driver)
```

- [ ] **Step 3.2：語法檢查**

```powershell
& "C:\Python314\python.exe" -m py_compile main.py
```

預期：無輸出。

- [ ] **Step 3.3：commit + push（端到端驗證留到使用者實機測試）**

```powershell
git add main.py
git commit -m "main.py：click_document_card 回 True 後接 process_document_system

於 main() 內顯式呼叫 document_system.process_document_system(driver)；
依賴 click_document_card 既有的 True/False 回傳值（待辦=0 / 判讀失敗 /
點擊失敗 → False → 不接續）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push
```

- [ ] **Step 3.4：使用者實機驗證（人工）**

請使用者跑 `C:\Python314\python.exe main.py`，預期：
- 登入流程一切如舊
- 公文(學校) 待辦 > 0 時，導航到 edoc 後印 `[document_system] 開始處理公文系統...`
- 印 `OK：點到「催辦訊息」（XPath: ...）`
- 印「點完後 URL / 標題」觀察跳到哪
- 印 `[完成] 公文系統處理流程結束。`

若「催辦訊息」XPath 全失敗 → 使用者打開 DevTools 確認 DOM，回報實際結構，再回頭補 XPath。

---

## Task 4：document_system.py standalone 入口

**Files:**
- Modify: `document_system.py`（替換 Task 2.4 那個臨時 `__main__`）

- [ ] **Step 4.1：加 `_standalone_open_chrome_at_edoc()`**

把 Task 2.4 的臨時 `if __name__ == "__main__":` 區塊整個刪掉，改成：

```python
def _standalone_open_chrome_at_edoc():
    """單獨執行時開 Chrome 並導航到 edoc 公文首頁。

    流程：
    1. 預清理 Selenium Chrome（避免 profile 被前一次 detach 的 Chrome 鎖住）
    2. 用 _build_chrome_options() 建 options，與 main.py 完全一致
    3. driver.get(EDOC_HOME_URL)，sleep 2 後檢查 current_url
    4. 若被導去 login.gov.taipei / sso → session 過期，印提示後回 None
    回傳 driver 或 None。
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
        print("        session 可能過期，請先跑 C:\\Python314\\python.exe main.py 重新登入")
        return None

    print(f"      OK：已在 edoc — {current}")
    return driver
```

- [ ] **Step 4.2：加正式 `__main__`**

接在 `_standalone_open_chrome_at_edoc()` 之後：

```python
if __name__ == "__main__":
    driver = _standalone_open_chrome_at_edoc()
    if driver is None:
        sys.exit(1)
    ok = process_document_system(driver)
    sys.exit(0 if ok else 1)
```

- [ ] **Step 4.3：語法 + import 驗證**

```powershell
& "C:\Python314\python.exe" -m py_compile document_system.py
& "C:\Python314\python.exe" -c "from document_system import _standalone_open_chrome_at_edoc, process_document_system; print('OK')"
```

預期輸出：`OK`

- [ ] **Step 4.4：commit + push**

```powershell
git add document_system.py
git commit -m "document_system.py：加 standalone __main__ 入口

跑 'python document_system.py' 時：
- _close_selenium_chrome_only 預清理
- 用 _build_chrome_options() 開 Chrome (與 main.py 共用同一份 options)
- driver.get(EDOC_HOME_URL) → 賭 session 還在
- 被導回 login.gov.taipei 就提示「請先跑 main.py 重登」並 exit(1)
- 成功進到 edoc 才呼叫 process_document_system(driver)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push
```

- [ ] **Step 4.5：使用者實機驗證（人工）**

兩種情境：

**(a) session 還新鮮**：剛跑完 main.py（Chrome 已 detach 留著），馬上跑：
```powershell
& "C:\Python314\python.exe" document_system.py
```
預期：預清理 → 開 Chrome → 進 edoc → 點催辦訊息 → 印 URL/標題 → 結束。

**(b) session 過期**：等久一點（隔幾小時 / 隔天）再跑同指令。
預期：開 Chrome → 導向 login 之類 → 印「session 可能過期，請先跑 main.py 重新登入」→ exit(1)，不要卡死。

---

## Self-Review（writer 已執行）

**Spec 覆蓋率**：
- 「點選催辦訊息」 → Task 2.2 `_click_urgent_message` + Task 2.3 流程
- 「main.py 顯式串接」 → Task 3.1
- 「standalone 開同 profile 賭 session」 → Task 4.1
- 「Chrome options 共用」 → Task 1.2 / 1.3
- 「session 過期提示退出」 → Task 4.1 末段
- 「重用 _close_selenium_chrome_only」 → Task 1.1 + Task 4.1 預清理

**Placeholder 掃描**：所有 `TODO:` 都是程式內預留給未來迭代擴充的位置（spec 已列入「後續迭代候選」），不是 plan 本身的待辦。無 "TBD / fill in details / implement later" 等坑。

**型別 / 命名一致性**：
- `process_document_system(driver) -> bool`（Task 2.3、3.1、4.2 一致）
- `_click_urgent_message(driver, timeout=10) -> bool`（Task 2.2 唯一定義）
- `_standalone_open_chrome_at_edoc() -> WebDriver | None`（Task 4.1、4.2 一致）
- `_build_chrome_options() -> Options`（Task 1.2、1.3、4.1 一致）
- `_close_selenium_chrome_only()` 無回傳值（Task 1.1、1.4、4.1 一致）
- `EDOC_HOME_URL`、`URGENT_MSG_XPATHS` 名稱於 Task 2.1、4.1 一致
