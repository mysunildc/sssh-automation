# sssh-automation 交接手冊（給接手者的 Claude Code 讀）

> **讀者**：在新主機上協助同事部署、執行、維護本系統的 Claude Code。
> **來源**：原作者主機上的實機紀錄（2026-05 ～ 2026-10，223 個 commit、多次實機事故）。
> **公開 repo**：<https://github.com/mysunildc/sssh-automation>（`git log` 的 commit 訊息是繁中、寫得很細，查某個坑的來龍去脈時直接搜 commit 訊息）。
> 本檔重點在「README 沒寫、但換一台機器一定會撞到」的事。程式架構與基本跑法以 `README.md` 為準；本檔與 README 衝突時，以本檔與實際程式碼為準（README 有少數過時段落，見 §10）。

---

## 0. Claude Code 請先做的事

1. 讀完本檔，再讀 `README.md`、`CLAUDE.md`（專案硬性規則）、`flowchart.md`（Mermaid 全流程圖）。
2. **把 §2 的硬性規則寫進你自己的專案記憶**（每次對話都要遵守，特別是「陳會不可復原」）。
3. 依 §3 逐項確認同事主機與原作者主機的差異，**能用指令驗證的就自己驗**，不要假設。
4. 依 §5 的「漸進試運轉」順序上線，不要第一次就讓 `main.py` 跑完整流程。

---

## 1. 系統在做什麼

執行一次 `py main.py`，依序：

1. **登入**：自然人憑證（讀卡機 + PIN）→ 臺北市單一身分驗證 → TAIPEION → 點「公文(學校)」方塊 → edoc 公文系統（edoc 會**再要一次 PIN**，即「二次憑證登入」）。
2. **簽收**：催辦訊息、待簽收公文自動全選簽收。
3. **承辦中**（迴圈到 0）：開公文 → 下載 zip（KdApp 對話框）→ 解壓 → LLM 依 `summarize_doc.md` 產出「內容.txt + 總結.md」→ 依總結填擬辦文字並**儲存** → 總結判定「陳會」就**送陳會 + PIN 簽章**。任何一份動作是 `none`（公文沒離開承辦中）就印 STOP、停止承辦中迴圈，留給人接手；**但整體流程不會停**，會繼續往下做受會案件與待結案。
4. **受會案件**：沿用承辦中流程。
5. **待結案**（迴圈到 0）：確認核決區有「如擬」→ 下載歸檔 → 附件歸檔 → 填存查表單（檔號/案次號）→ 確定存檔 → PIN 簽章 → 寫存查標記檔。
6. **上網公告**：總結承辦文字含「於官網公告」→ 用帳密登入校網 → 發佈到圖書館公告（置頂、附件、同步分類）。

`py main.py 3` 只跑「登入 + 結案存查」。`py main.py 2` 是舊的像素點擊版登入（備援，只到登入）。

---

## 2. 硬性規則（必須寫進記憶）

| 動作 | 可否復原 | Claude Code 該怎麼做 |
|---|---|---|
| **陳會**（`fill_in_draft` 點「陳會」+ PIN 簽章） | **不可復原**：公文真的送到下一關主管 | 程式修改、單元測試、乾跑、讀 log 可自己做；**實機會觸發陳會的執行，一定先問使用者**。 |
| 催辦/待簽收**簽收** | 例行收件確認 | 原作者已授權自動簽，不必逐次問（同事是否同意，第一次先問他）。 |
| 結案**存查** | 可由管理者復原 | 不必逐次確認。 |
| **上網公告** | 公開發佈到學校官網 | 第一次實機前先問；之後依同事意願。 |

**原作者踩過的事故（2026-09-14）**：為了驗證「登入修正」在背景跑完整 `main.py`，結果它一路跑進承辦中 → 擬辦 → **真的陳會送出一份公文**，使用者事前不知道。
**教訓：`main.py` 不是驗證工具。** 只是要驗證登入/導航，就盯著 `run.log`，看到能證明修正成立的那行（例如 `edoc 登入成功`、sidebar 讀到數字）就立刻停掉程序。

**程式裡沒有「不要陳會」的開關**：`fill_in_draft` 只看總結檔 `###` 那行是不是 `陳會`，是就送出。想要保證不送出，只能讓總結檔的動作不是 `陳會`（見 §5 第 3 步），或另外加一個程式開關。

**帳密**：PIN、校網帳密只放 `env.env`（已在 `.gitignore`）。絕不印進對話、命令列參數、log，也絕不 commit。`env_example.env` 是範本，裡面只能放假值。

---

## 3. 換主機一定要檢查/修改的項目

> 原作者主機：Windows 10 Enterprise、Python 3.14（`py` 啟動器）、Chrome 142+、讀卡機 **EZ100PU**、HiCOS 跨平台元件、TCGServiSign 簽章元件裝在預設路徑、常用 RDP 遠端操作。

### 3.1 會直接讓程式 STOP 或失敗的

| # | 項目 | 位置 | 原作者的值 | 同事主機要做的事 |
|---|---|---|---|---|
| 1 | **讀卡機型號寫死** | `main.py` 的 `ensure_servisign(expect_reader_substr="EZ100PU")` | `EZ100PU` | 讀卡機不是 EZ100PU 的話，console 語境會 STOP 並印「看得到 [...] 但沒有 'EZ100PU'」。查出實際名稱後改掉，或改成 `None`（只要求「有讀卡機」）。查法：跑 `py -c "from servisign_utils import list_smartcard_readers as f; print(f())"`（**要在主機 console 跑，RDP 下必為空**）。 |
| 2 | **簽章元件路徑寫死** | `servisign_utils.py` 的 `SERVISIGN_DIR`、`scripts/servisign_session0*.ps1` 的 `$exe`/`$dir` | `C:\Program Files (x86)\TCG\TCGServiSign` | 用 `Test-Path` 確認同事主機的安裝路徑，不同就三處一起改。 |
| 3 | **`env.env` 不存在** | repo 根目錄 | — | 從 `env_example.env` 複製改名為 `env.env`，填 `pin`、`sssh_account`、`sssh_password`、`sssh_publisher`、`sssh_publish_unit`、LLM 設定。 |
| 4 | **Python 版本** | — | 3.14.4 | **至少 3.12**（結案存查刪目錄用了 `shutil.rmtree(onexc=...)`，3.11 會丟 TypeError），建議跟原作者一樣用 3.14。統一用 `py` 啟動器。 |
| 5 | **相依套件** | — | 見 §4 | README 的安裝指令**漏了 `pypdf`、`psutil`**（總結讀 PDF 需要 `pypdf`；`psutil` 選用，用來找鎖住目錄的程序）。 |
| 6 | **LLM 後端** | `env.env` 的 `summarize_llm_order` 等 | `claude,antigravity,aistudio,anthropic`，`summarize_claude_model=opus` | 依同事有的帳號調整順序。沒有任何可用後端時，下載仍會成功，但沒有總結 → 擬辦走 default、存查讀不到檔號。見 §7.5。 |

### 3.2 業務規則：依同事的職務改

| 項目 | 位置 | 說明 |
|---|---|---|
| **公文分類 → 檔號 → 承辦文字 → 承辦方式（陳會/none）→ 校網同步分類** | `summarize_doc.md` 的對應表 | 這張表是**原作者（資訊組）的業務規則**，檔號 `03750401~04` 是資訊組的。同事職務不同就一定要改，否則存查會歸錯檔號、陳會會送錯。**這張表直接決定哪些公文會被自動陳會、哪些會被公告到官網。** |
| 擬辦文字模板 | `fill_in_draft.yaml` | `template` 與 `default`（總結缺欄位時的 fallback，預設動作 `none`）。 |
| 上網公告 | `env.env` 的 `sssh_*`、`document_closure/document_closure_post_web.py` | 存查成功後，總結的承辦文字（`##` 行）含「於官網公告」就會用校網帳號發佈到「圖書館公告」模組。「發布單位」可選項由校網後台帳號群組決定，**會變動**；填錯不會發佈，run.log 會印「站上可選=[...]」，照清單改 `sssh_publish_unit`。**要確實關掉公告：把 `env.env` 的 `sssh_publish_unit` 留空**，程式會在登入校網之前就印 STOP 並略過，不會發佈（改對應表的「於官網公告」字樣不保險：舊總結不會重產，LLM 輸出也不固定）。 |
| 存查表單「檔號」第一格 | `document_closure.py` 的 `'0115'` | 程式靠「值為 `0115` 的那一格」定位檔號欄，再填它的下一格。推測是民國年度代碼（未驗證），**換年度或同事表單不同就會填不到檔號**。 |
| TAIPEION 方塊名稱 | `click_document.py` 的 XPath（`公文(學校)`） | 同事的 TAIPEION 儀表板方塊名稱不同就要改。 |

### 3.3 依主機狀況可能要調的

| 項目 | 說明 |
|---|---|
| **Chrome「允許」按鈕座標 (322,197)** | `taipeion_login_selenium._click_chrome_allow_button` 用固定螢幕座標 + 藍色像素判斷。**解析度/DPI 縮放不同就會對不到**（程式只會印「非允許按鈕藍底色，跳過點擊」）。這個對話框授權一次後 Chrome profile 就會記住，所以**第一次執行時請同事手動按「允許」**（看到 Chrome 跳「要開啟/存取…」的對話框就按），之後就不會再出現。 |
| Selenium 專用 Chrome profile | `%LOCALAPPDATA%\Chrome-Selenium\User Data`（全新主機會自動建立）。**不要在這個 profile 裡登入 Google 帳號**，否則會同步下來大量已存密碼、autofill 會蓋掉登入欄位（見 §7.8 第 1 點）。 |
| UAC | RDP 語境下，程式會提權把簽章元件切到 session 0。原作者主機的 UAC 設成「提權不提示」所以全自動；**同事主機會跳 UAC，要按「是」**。 |
| 常駐守護排程 | 要在 RDP 下也能讀主機讀卡機，請以系統管理員身分執行一次 `scripts\install_servisign_watchdog.ps1`。**repo 搬位置後要重跑**（排程記的是絕對路徑）。只在 console 前操作、不用 RDP 的話可以不裝。 |
| 讀卡機接在哪 | 讀卡機接在主機、人用 RDP 連進來，跟人直接坐在主機前，行為不同。詳見 README「遠端桌面(RDP)與讀卡機」與本檔 §7.2。 |
| KdApp 本地元件 | 公文系統元件（javaw，監聽 `http://127.0.0.1:16888`），隨 edoc 安裝。下載公文、陳會/存查簽章都靠它。 |

---

## 4. 安裝與環境驗證（Claude Code 可自己跑的部分）

```powershell
py --version                                   # 需 >= 3.12
py -m pip install selenium pillow pyautogui pywin32 pyyaml pywinpty pypdf psutil
py -m pip install pytest                       # 跑單元測試
# 選用：anthropic（anthropic 後端）、claude CLI（claude 後端）、agy CLI（antigravity 後端）

# 本地元件是否在監聽（56420=TCGServiSign 簽章元件、16888=KdApp）
Get-NetTCPConnection -State Listen -LocalPort 56420,16888 -ErrorAction SilentlyContinue |
  Select-Object LocalPort, OwningProcess

# 簽章元件安裝路徑
Test-Path "C:\Program Files (x86)\TCG\TCGServiSign\TCGServiSign.exe"

# 單元測試（不碰網路、不碰真實系統）
py -m pytest -q
```

- ChromeDriver 由 Selenium Manager 自動下載，不用手動裝。
- `claude` 後端是呼叫 `claude -p`（吃本機 claude.ai 訂閱）。**一定要在 `env.env` 釘住 `summarize_claude_model`**，否則會跟著 Claude Code 全域預設模型（例如換成較慢、較耗額度的模型）。
- `antigravity` 後端要先裝 `agy` 並登入 Google 帳號；裝完若終端機是之前就開的，PATH 會是舊的 → 程式會退回 `%LOCALAPPDATA%\agy\bin\agy.exe`，或用環境變數 `AGY_EXE` 指定。

---

## 5. 漸進試運轉（第一次上線請照這個順序）

1. **`py -m pytest -q` 全綠。**
2. **關掉公告**：試運轉期間把 `env.env` 的 `sssh_publish_unit` 留空（§3.2），存查後不會發佈到官網。
3. **降低陳會風險**：程式沒有陳會開關（§2）。試運轉期間把 `summarize_doc.md` 對應表的「承辦方式」欄全部改成 `none`，並把規則段的範例「如:###陳會」改成「如:###none」。**這只能降低、不能保證**：總結是 LLM 讀這張表產生的，輸出不固定；而且目錄裡已經有 `*內容.txt` + `*總結.*.md` 的公文不會重產總結（要先刪掉）。總結一產出就立刻擬辦，中間沒有空檔讓人檢查。要百分之百保證不送出，請先加一個程式開關（例如 `env.env` 設定為真時，`fill_in_draft` 遇到 `陳會` 只儲存不送出）並經使用者同意。
4. **只驗登入**：執行 `py main.py`，同時盯 `run.log`。看到 `edoc 登入成功`（或 `edoc 未要求二次憑證登入（已在系統內）`）以及 sidebar 讀到「承辦中 = N」就停掉（`Ctrl+C` 或結束 python 程序）。這一步會順便驗證 §3.1 第 1～3 項與「允許」對話框。**注意：讀到承辦中之前，程式已經先自動簽收了催辦與待簽收**，第一次跑前要先徵得同事同意（§2）。
5. **驗下載 + 總結**：讓它跑一份承辦中公文，確認 `document_download\<文號>\` 有解壓內容、`*內容.txt`、`*總結.<模型>.md`，且總結第 1～4 行格式正確（`#存查分類:` / `##承辦文字` / `###承辦方式` / `####校網同步`）。**注意：承辦中停下後，程式會繼續處理受會案件與待結案（含存查；公告依第 2 步設定），只想驗承辦中就要在這時人工停掉程序。**
6. **驗結案存查**：`py main.py 3`（存查可復原）。**新主機的第一次存查幾乎一定會停在「讀不到分類檔號」**：存查讀的檔號來自承辦中那一輪產生的總結，結案下載本身不跑總結；部署前就已在待結案的公文從沒在這台跑過承辦中，所以沒有總結。處理：`py summarize_doc.py document_download_closure\<文號>` 產出總結後重跑。
7. 都 OK 後才恢復「陳會」與公告設定，並在同事同意下跑一次完整 `py main.py`。

各階段也可以單獨跑，但要知道它們的行為：
- `py document_system.py`、`py pending_doc_handler.py`、`py document_closure\document_closure.py`：**不是接手既有 Chrome**，而是先關掉自動化 Chrome、重開一個直接到 edoc 首頁，靠 profile 裡殘留的登入狀態。不跑 edoc 二次 PIN 登入、不做簽章元件與桌面狀態檢查；edoc 要求二次 PIN 時，前兩個會誤判成「無公文待處理」，`document_closure.py` 會印「無法判讀待結案數」後結束。前兩個一樣會跑進擬辦/陳會。
- `py fill_in_draft.py`：attach 到既有 Chrome 的 `:9222`，對停在閱覽器分頁的公文跑擬辦（**會陳會**）。`py fill_in_draft.py dump`：只列出擬辦面板的元素候選。
- `py summarize_doc.py <公文目錄>`：只產總結。

---

## 6. 執行時的環境限制（最常被忽略）

### 6.1 一定要滿足

- **螢幕不能鎖定**：Windows 鎖屏會擋 Smart Card API，HiCOS 讀不到卡。這是 OS 機制，軟體繞不過（原作者實測過，早期看似成功都是時序假象）。
- **桌面要是 Active**：用 RDP 時**不能斷線**。RDP 一斷，Selenium 照常跑，但到「匯出公文資料」對話框要模擬鍵盤時會全部被拒（`SendInput` 回 0、`GetLastError=5`）。`main.py` 起手會偵測並 STOP。

### 6.2 執行中不要動鍵盤滑鼠（尤其是以下兩段）

大部分網頁操作走 Selenium/CDP，不受人同時操作影響。但有兩段是**作業系統層級的鍵盤滑鼠模擬**：

| 時機 | 程式在做什麼 | 人同時操作會怎樣 |
|---|---|---|
| **每份公文下載時**（log 出現 `等「匯出公文資料」對話框出現`），承辦中與待結案都會發生，時間點不可預測（前一份的 LLM 總結可能跑好幾分鐘） | 把 KdApp 對話框拉到前景，`SendInput` 送 **Ctrl+A → Backspace → 打路徑 → Enter**（約 3 秒） | 程式**沒有確認對話框真的在前景**。人在 200 秒內有操作過，Windows 會拒絕背景程序搶前景（`ForegroundLockTimeout` 預設 200000ms），這串按鍵就會打進**人正在用的視窗**：全選刪光文件內容、在聊天視窗送出一串路徑。人同時打字也會讓按鍵混進路徑。 |
| 登入初期兩次（登入頁、進 edoc 時） | 按一下全域 Alt 鍵，把 Selenium Chrome 拉到前景，檢查 (322,197) 是否為藍色「允許」按鈕，是才點 | Alt 會落在人當下的視窗（Office 進入選單快捷鍵模式；人正按著 Shift 時，Alt+Shift 會切換輸入語言）。之後 Chrome 在最上層，人以為在自己視窗打的字會打進 edoc 網頁。 |

其他：
- **不要在 Selenium 開的那個 Chrome 視窗裡點擊、打字、關分頁。** 最危險的時機是擬辦文字填完、讀回驗證之後，到「儲存/陳會」之間（不到 1 秒）：這時打進去的字會被一起儲存甚至送出。
- Chrome 視窗被其他視窗完全蓋住或最小化，Chrome 可能把頁面當成隱藏並降低計時器頻率（隱藏超過 5 分鐘時，部分計時器降到每分鐘一次）。程式沒有加關閉節流的參數。**此點依 Chrome 機制推論、未實機驗證**；遇到不明的逾時可以先往這個方向查。
- 系統剪貼簿是共用的：Selenium Chrome 授權所有網站讀寫剪貼簿（edoc 閱覽器會用到）。
- 啟動時會把**當下前景視窗**的輸入法切成英文；若 Windows 設定為全部視窗共用輸入法，人的注音會被切掉。
- 人若同時在自己的瀏覽器用自然人憑證，會跟程式搶同一個簽章元件與同一張卡。

> 已知改進方向（尚未實作）：送鍵前比對 `GetForegroundWindow()` 是否為對話框、不是就重試或停下；「允許」按鈕改成先判斷有沒有對話框，沒有就完全不按 Alt、不搶前景；Chrome 加 `--disable-backgrounding-occluded-windows` 等參數。

### 6.3 Claude Code 自己實測時的特殊坑

在 Claude Code 的 Bash/PowerShell 工具內直接跑 python，`SendInput` 會被拒（err 5）、`GetForegroundWindow()=0`，**即使桌面沒鎖**。此時 log 印的「RDP 已斷線或工作站鎖定」是誤判。要實測含「下載公文」的流程，請用**互動式排程工作**啟動：

```powershell
# run_test.bat 內容：set PYTHONIOENCODING=utf-8 / cd 到 repo / py main.py > out.txt 2>&1
$act = New-ScheduledTaskAction -Execute "<完整路徑>\run_test.bat"
$pr  = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
Register-ScheduledTask -TaskName claude_test -Action $act -Principal $pr -Force
Start-ScheduledTask claude_test
# 盯 run.log；跑完 Unregister-ScheduledTask claude_test -Confirm:$false
```

Action 直接寫 `cmd.exe /c "..."` 帶引號會失敗（Result=1），要包成 `.bat`。**再次提醒：會跑到陳會的流程要先問使用者。**

---

## 7. 各階段的坑（原作者實機踩過、程式已處理，改程式時別改壞）

### 7.1 Chrome / Selenium 啟動

1. **Chrome 136+ 不准對預設 User Data 開 DevTools port** → `DevToolsActivePort file doesn't exist`。所以用獨立 profile `%LOCALAPPDATA%\Chrome-Selenium\User Data`。
2. **強制結束後殘留 lock 檔** → `Chrome instance exited`。`scripts/close-profile2-chrome.ps1` 會清 `lockfile`、`Default\LOCK`、`Singleton*`。`main.py` 啟動時會自動跑它。它只關命令列帶 `Chrome-Selenium`、`--remote-debugging-port`、`--test-type=webdriver` 的 Chrome，**但也會關命令列含 `Profile 2` 的 Chrome**：同事的個人 Chrome 若用「Profile 2」捷徑開，會被一起關掉。另外它會強制結束**所有** `chromedriver.exe`（不過濾），以及其他正在跑的 `sssh-automation\main.py`；同事若有別的 Selenium 工作在跑，會被一起殺掉。它會保護呼叫者的父程序鏈（否則會把正在啟動的 `main.py` 自己殺掉、毫無輸出就結束）。
3. **`variations_crash_streak` 累積到 5+，Chrome 會拒絕啟動**：每次強制結束 +1，`_reset_crash_streak()` 啟動前歸零。
4. 「Chrome 未正確關閉」泡泡：啟動前把 profile 的 `exit_type` 設 `Normal`。
5. 「受自動測試軟體控制」資訊列：三件套（`excludeSwitches`、`useAutomationExtension=False`、`--disable-blink-features=AutomationControlled`）。
6. **`page_load_strategy="eager"` 不能改回 normal**：edoc 新分頁會跳站台權限對話框，`onload` 永遠不觸發，normal 模式下所有 driver 指令會卡死。
7. **`unhandledPromptBehavior=accept`**：公文系統會跳 JS confirm，不處理的話 driver 會一直卡住。
8. Chrome 142+ 的 Local Network Access 會擋 edoc（公開網站）去 fetch `127.0.0.1` 的本地元件 → 用 `--disable-features=LocalNetworkAccessChecks,...` 加 `--allow-running-insecure-content`（KdApp 是 HTTP）。
9. 剪貼簿權限對話框：prefs 加上 CDP `Browser.grantPermissions` 雙保險。
10. `--remote-debugging-port=9222`：讓 `fill_in_draft.py` 能 attach 到已開著的 Chrome 接手。
11. `driver.save_screenshot` 只截網頁內容，看不到 Chrome 本身的對話框；要整個桌面得用 `PIL.ImageGrab.grab()`。
12. 用 Bash 工具重導輸出時，`print` 會被緩衝。`run.log` 由 `_setup_stdout_logging()` 即時寫入（每行帶 ISO 8601 時間戳），**除錯一律先讀 `run.log`**。但它**每次執行都會覆寫**（只有超過 10MB 才輪替成 `.1`～`.6`）：每跑一次 `main.py`、`document_system.py`、`pending_doc_handler.py`、`fill_in_draft.py`（含 `dump`）、`document_closure\document_closure.py`、`document_closure\document_closure_post_web.py`，上一次的 log 就沒了，要保留就先複製。`summarize_doc.py` 單獨跑時不寫 run.log，輸出只在 console。`chrome_browser.log` 只是 edoc 登入當下的 Chrome console 快照，同樣每次覆寫。

### 7.2 登入、簽章元件、讀卡機、RDP

1. **「重試 2 輪後仍未看到『登入』按鈕」/ 登入頁一直「重新檢測」，先查 56420 有沒有在監聽，不要先怪卡片。** `TCGServiSign.exe` 主程式偶爾會自己掉（只剩 Monitor/Worker）。`main.py` 起手式 `ensure_servisign` 會自動重啟。
2. **RDP 與讀卡機（微軟設計）**：`winscard.dll` 在**被載入的那一刻**決定讀卡要不要重導。在 RDP session 內載入 → 永遠看不到主機讀卡機；在 console 或 session 0 載入 → 讀主機。所以：
   - RDP 下，程式會把 `TCGServiSign.exe 0` 以 SYSTEM 身分啟動到 **session 0**（排程工作 + `scripts/servisign_session0.ps1`）。**只能啟動主程式**，Monitor 在 session 0 沒有桌面會立刻退出。
   - RDP 下本程序自己的 WinSCard 也會被重導，`list_smartcard_readers()` 必為空，**不能拿來判斷讀卡機在不在**（曾因此誤 STOP）。
   - 判斷是不是 RDP 要用 `GetSystemMetrics(SM_REMOTESESSION)`，**不要看 `SESSIONNAME` 環境變數**（console 被 RDP 接管後仍是 `Console`）。
   - 讀卡機廠商的自我檢測程式、HiCOS 卡片管理工具在 RDP 視窗內一律顯示「讀卡機未安裝」，這是正常的，不代表網頁簽章不能用。
3. **提權用的 `.ps1` 必須是純 ASCII**：Windows PowerShell 5.1 讀無 BOM 的 UTF-8 中文會解析失敗、**靜默不執行**。`schtasks /TR` 帶「含空白路徑 + 參數」時引號會被吃掉，所以改用 ScheduledTasks cmdlet。
4. **edoc 不吃 TAIPEION 的登入狀態**，進站會停在 `index.jsp` 再要一次 PIN（`click_document.edoc_pin_login`）。沒處理的話，下游會在登入頁上空轉並誤判成「無公文待處理」。
5. PIN 填入有兩處，行為不同：
   - edoc 二次登入（`click_document.edoc_pin_login`）：填完讀回比對，不符就**不送出**（避免 autofill 蓋掉造成錯誤 PIN 鎖卡）。
   - TAIPEION 第一次登入（`taipeion_login_selenium._fill_pin`）：用 `element_to_be_clickable` 找欄位、**不讀回**，填失敗仍會按登入。
   - TAIPEION 登入頁的按鈕用 `presence_of_element_located` + JS click（`_js_click`）繞過遮罩；edoc 二次登入的「登入」鈕則是先用原生 click，失敗才退回 JS。
6. 二次登入轉址會把「操作時間逾時警告」（`sessionTimeout.jsp`）開成新分頁，出現就要關掉。
7. 頁面跳 Chrome 站台權限對話框時，若 `page_load_strategy` 是 normal，`window_handles` 等 driver 指令會卡到 120 秒逾時，這就是 §7.1 第 6 點用 eager 的原因。

### 7.3 edoc 公文系統頁面

1. **承辦中的「公文已離開」以 sidebar 數字為準**。陳會後會短暫多開「請選擇對象」視窗（window 數 2→3→1），用 window 數判斷會誤判。陳會送出後 server 處理約需 5～6 秒，每秒輪詢 sidebar、最多 10 次。（存查的成功驗證另有邏輯，最長等 30 秒，見 §7.7。）
2. 催辦 badge 是 `<button class="urge">`，文字「催辦訊息1」後面黏著數字 → 用 `contains`。催辦清單的簽收鈕 value 是「簽　   收」（字間夾空白）→ 用 `contains(簽)+contains(收)`。
3. **Frame focus**：大部分內容在 `dTreeContent` iframe。`switch_to.window` 會把 frame focus 重置回 top，**每次切分頁後都要重新切回 frame**。找按鈕時不要依賴呼叫端留下的 frame，要自己掃 top + 所有 iframe（`_click_button_in_any_frame` 的作法）。
4. **只切到 `doSno` 對應的閱覽器分頁**（2026-10-13 曾卡在舊分頁）。閱覽器 URL 格式：`https://edoc.gov.taipei/tcqb/oa/index.html?app=editor&doSno=<10碼>`。
5. **公文閱覽器是 Sencha Touch/ExtJS**：按鈕不能用 `el.click()`，要 `Ext.getCmp(id).fireAction('tap', ...)`（`_sencha_tap_element`）。ExtJS 的 `ext-button-XX` id 是動態的，不要寫死。
6. 選擇器一律以實機 dump 鎖定（`py fill_in_draft.py dump`），**不能只寫好就 commit**，pytest 的 monkeypatch 測不到真實點擊。

### 7.4 下載公文 zip（`pending_doc_handler.py`）

1. **toolbar 下載鈕（`#packageBtn`）不會走 Chrome 下載**，而是讓 KdApp（javaw）開一個 Java Swing JFileChooser「匯出公文資料」對話框。CDP 的 `setDownloadBehavior` 對它無效。
2. 點完後 Chrome 會多開一個列印預覽視窗（`app=genpages&package=Y`），**不要切過去**，會搶走焦點、干擾對話框。
3. 對話框是 top-level 視窗，要用 `EnumWindows` 依標題「匯出公文資料」找。
4. **Java AWT 不接受 `SendInput` 的 `KEYEVENTF_UNICODE`**（會變全大寫、符號錯亂、中段截斷），要用 `VkKeyScanW` 拆成 vk + shift 模擬實體按鍵。**所以下載路徑（repo 路徑）必須是純英文**，中文路徑打不進去。
5. 打字前要把對話框的輸入法切成英文（`ensure_english_ime(hwnd)`），否則會被注音攔截。
6. KdApp 先寫一個沒有副檔名的暫存檔，寫完才改名成 `.zip`。等檔案完成時要排除「無副檔名/.tmp/.part/.crdownload」，且大小穩定 1 秒以上。
7. **zip 內檔名是 cp950（Big5）**，用 `ZipFile(..., metadata_encoding='cp950')`（需 Python 3.11+）。
8. 解壓後若頂層只有一層殼資料夾（「公文」/「來文」）會攤平；遇到新的殼資料夾名就加進 `_FLATTEN_CANDIDATE_NAMES`。
9. KdApp 剛打包完可能還握著 zip，刪除要重試。「來文」可能是唯讀檔，刪目錄前要先去唯讀屬性。
10. 存檔後會自動開檔案總管指向下載目錄，程式只會把**位於下載目錄**的檔案總管視窗最小化/關閉。清空殼目錄時，只會對工作目錄卡在那裡的 Notepad 類程式送 `WM_CLOSE`（白名單，絕不碰 VSCode/瀏覽器）。

### 7.5 公文總結 LLM（`summarize_doc.py`）

規格全寫在 `summarize_doc.md`（LLM 讀這份執行），Python 只做 I/O。改業務規則只改 `.md`。

1. **舊的 gemini CLI 已停用**（Google 2026-06-18 停掉消費者免費 OAuth），改成四個後端依 `summarize_llm_order` 輪流試。
2. **`claude -p` 會載入使用者層級的 `~/.claude/CLAUDE.md`**，若裡面規定了回覆結尾格式，會被寫進公文總結檔。`--bare` 能關掉，但會連 OAuth 訂閱認證一起關掉，所以不能用。現行解法：`--append-system-prompt` 加上 `_strip_claude_md_footer()` 砍掉結尾的引言區塊。**同事的全域 CLAUDE.md 若有其他結尾格式，要確認這個去除邏輯仍然有效。**
3. `claude -p` 的 `modelUsage` 常有多個 key（會順帶用小模型做輔助），取 token 用量最大者當總結模型（決定輸出檔名）。
4. `agy` 被當子程序（非 TTY）呼叫時會把回應丟掉 → 必須用 `pywinpty` 包進 ConPTY。`agy -p` 的 prompt 只能走命令列參數（Windows 約 32767 字元上限）。拿不到實際 model id，檔名用 `antigravity`。單篇約需 4 分鐘，慢。
5. AI Studio 免費層偶發 HTTP 503，對 429/5xx 做 backoff 重試。
6. 已有 `內容.txt` 或 `總結.*.md` 就會略過對應工作。要重產就先刪掉舊檔。

### 7.6 擬辦與陳會（`fill_in_draft.py`）

1. 承辦文字與動作取自 `*總結*.md` 的 `##`（承辦文字）與 `###`（動作：`陳會`/`none`）。欄位缺少就用 `fill_in_draft.yaml` 的 default。
2. 「我的意見」textarea：`textarea.x-input-el.x-form-field`，同一個 selector 有可見與隱藏兩個，要取可見的那個。
3. **填完一定要按左上 toolbar 的磁碟片鈕儲存**（`.fa-floppy-o`），否則文字只存在前端，重新整理就不見。儲存會讓 URL 的 `gbDocflowId` 重新分配。
4. **儲存後 ExtJS 會重繪 + 蓋一層 loading mask** → 舊的元素參照會 stale、點擊會被攔截。陳會鈕每輪都要重新 find 再 click，重試到逾時。
5. **陳會後 KdApp 會跳 `localhost:16888/doPostMsg` pinCode 視窗**，要再簽一次章。沒處理的話公文**不會真的送出**、卻不會報錯。另外，若 KdApp 勾過「記住 PIN」就不會出現輸入框（但換解析度後可能失效）。

### 7.7 結案存查（`document_closure/document_closure.py`）

1. 核決區沒有「如擬」就**保守跳過**（可能還在簽核中、或意見有異）。
2. **存查表單載入後、填檔號之前，必須先按「附件歸檔」**（會另開分頁，不用輸入任何東西，直接關掉）。少了這步，「確定存檔」後 pinCode 視窗不會出現，存查其實沒有完成。
3. 「檔號」第二格（以值為 `0115` 的第一格定位，見 §3.2）、「案次號」選第一個 option、保存年限只記 log 不驗證。
4. **pinCode 視窗的完成態判斷**：視窗內一開始就有「初始化完成」字樣，**不能只比對「完成」**（會把還在等輸入的視窗關掉）。要認「更新SI檔完成/簽章完成」這類結尾詞，而且輸入框可見時一律不算完成。「進行中」也不算完成態（2026-10-07 修）。
5. PIN 自動填入失敗時不中止，給 30 秒讓人手動完成，驗證到後仍會寫標記檔。
6. 存查成功的判準已在 2026-10-07 改成認表單/清單狀態。
7. **檔號來源**：存查只從結案目錄（`document_download_closure\<文號>\`）的 `*總結*.md` 讀檔號。結案下載不跑總結（`summarize=False`），總結是從承辦中目錄（`document_download\<文號>\`）複製過來的。沒在這台跑過承辦中的公文就沒有總結，會停在「讀不到分類檔號」，要用 `py summarize_doc.py document_download_closure\<文號>` 補產（見 §5 第 6 步）。
8. 標記檔：`<公文主檔名>已存查.txt`，已公告則有 `<公文主檔名>已公告.txt`，另外有持久的公告清冊 CSV 防止重複發佈。

### 7.8 上網公告（`document_closure_post_web.py`）

1. **Selenium profile 若存有瀏覽器密碼，autofill 會在欄位 focus 時蓋掉帳密**（晚於程式的 `clear()`），導致送出混合帳密、登入失敗。三層防護：
   - Chrome prefs 關掉密碼管理員。
   - 登入啟動前由 `taipeion_login_selenium._purge_saved_passwords` 用 sqlite 刪除 `Login Data*` 裡的已存密碼（保留「永不儲存」黑名單；sqlite 失敗才退回整檔刪除）。
   - 公告登入送出前讀回兩個欄位，不對就用 JS 改回，改 3 次仍不對就 STOP。
2. 「發布單位」不是 `<select>`，是自訂下拉（`ul.select-menu > li.select-item`）。點選後 input 的值是**非同步更新**，要用 Python 輪詢讀回確認。
3. 總結裡的主旨/條列行先做 Markdown 正規化再解析，解析失敗不能靜默跳過（2026-10-12 修）。
4. 內文是 CKEditor 5；附件抓公文目錄內的 `*ATTCH*` 檔案。

---

## 8. 故障排除速查

| 症狀 | 先查什麼 |
|---|---|
| 一啟動就 `[STOP] 桌面狀態 = Disconnected` | 主要是 RDP 斷線（看的是 WTS 連線狀態）。本機鎖屏時這個狀態推測仍是 Active，起手式不一定擋得下，但讀卡會失敗（未實測）。 |
| `[STOP] WinSCard 看不到讀卡機 ... 沒有 'EZ100PU'` | §3.1 第 1 項，改讀卡機名稱。 |
| `[STOP] RDP 語境下無法把簽章元件切到 session 0` | UAC 被拒或沒按：重跑並按「是」，或以系統管理員身分執行 `scripts\servisign_session0.ps1`（log 在 `%TEMP%\servisign_session0.log`）。 |
| 登入頁一直「重新檢測」、PIN 欄位不出現 | 56420 有沒有在監聽 → 簽章元件是否在正確的 session → 螢幕是否鎖定 → 最後才懷疑卡片。 |
| `session not created: Chrome instance exited` | 跑 `scripts\close-profile2-chrome.ps1`。 |
| 「無公文待處理」但其實有 | 是否卡在 edoc 二次 PIN 登入頁（看 run.log 有沒有 `edoc 登入成功`）。 |
| 下載卡在「匯出公文資料」對話框 | `SendInput` 被拒（看 log 是否有 `ERROR_ACCESS_DENIED`）、對話框沒拿到前景、路徑含中文、輸入法、有人同時在操作。**Claude Code 在工具內直接跑時**，起手式會顯示 Active、不會 STOP，但到這一步必定被拒，log 會誤報「RDP 已斷線或工作站鎖定」，見 §6.3。 |
| 解壓後中文檔名亂碼 | Python 版本（程式對舊版有 cp437→cp950 的退路，但整體需要 3.12+，見 §3.1）。 |
| 沒有總結檔 | LLM 後端都失敗（看 run.log 各後端的錯誤）、`pypdf` 沒裝。 |
| 擬辦沒填字/找不到按鈕 | `py fill_in_draft.py dump` 重新鎖定 selector；閱覽器分頁是否已載入。 |
| 陳會後公文還在承辦中 | pinCode 視窗沒處理（看 Chrome 是否還開著 `localhost:16888` 視窗）。 |
| 存查讀不到檔號 | `document_download_closure\<文號>\` 內有沒有 `*總結*.md`（新主機第一次存查幾乎必定如此，見 §7.7 第 7 項）。 |
| 存查填不到檔號 | 表單檔號第一格不是 `0115`（§3.2）。 |
| 公告沒發佈 | run.log 搜「站上可選=」（發布單位不符）、「自動填入」（autofill 干擾）、「缺 sssh_publish_unit」（刻意留空時的正常訊息）。 |

---

## 9. 給 Claude Code 的工作守則（原作者的偏好，建議同事也採用）

- **能自己跑的就自己跑**：測試、讀 log、乾跑都自己做，不要叫使用者跑完再回報。只有實體動作（插卡、解鎖、UAC 按「是」）與**陳會**這類不可逆動作才停下來問。
- **回報前先用工具驗證**：狀態、路徑、設定值都要實際查過，不憑印象。
- **修好 = 改程式碼 + 重跑會過**，不是手動幫它補過這一次。
- 改 selector 一定要實機驗證，pytest 測不到真實點擊。
- 驗證前段修正時，**盯 run.log、達成目的就停**，不要放任 `main.py` 跑進承辦中處理迴圈（§2）。
- 自然人憑證卡在原作者主機上永遠插著，所以程式不把「插卡」當前提；同事主機若不是如此，第一次先跟他確認。
- 截圖等暫存檔用完即刪；`run.log`、`chrome_browser.log`、`document_download*\` 都在 `.gitignore`，不要 commit。

---

## 10. 文件與現況的落差（已知）

- README「執行方式」寫「執行前會 `taskkill /F /IM chrome.exe` 清掉所有 Chrome（含使用者個人 Chrome）」**已過時**：現行程式只關自動化用的 Chrome（`_close_selenium_chrome_only`），但含 `Profile 2` 的例外（見 §7.1 第 2 點）。
- README「階段測試入口」寫「在 Chrome 已就位的狀態下從中段開始」，實際上這些入口會重開 Chrome（見 §5 末段）。
- README 的安裝指令漏了 `pypdf`、`psutil`。
- README 開頭寫的 LLM 順序（antigravity 第一）是程式內建預設 `DEFAULT_LLM_ORDER`；`env_example.env` 的範本值是 claude 第一。`env.env` 有設 `summarize_llm_order` 就以它為準。
- `docs/superpowers/specs/2026-05-27-fill-in-draft-design.md` 與 `fill_in_draft.py` 開頭的模組說明仍是舊的「yaml rules 查表」架構；現行是直接讀總結檔的 `##`/`###`。
- `doc_classifier/` 目前不使用（以 `summarize_doc` 取代）。

---

## 11. 檔案索引

| 檔案 | 用途 |
|---|---|
| `main.py` | 入口；起手式：輸入法切英文 → 桌面狀態檢查 → 簽章元件健康檢查 → 跑 FEATURES |
| `taipeion_login_selenium.py` | 登入 + Chrome options + run.log 設定等共用工具 |
| `click_document.py` | 點「公文(學校)」方塊、edoc 二次 PIN 登入（全 repo 只有這裡會做二次登入） |
| `document_system.py` | 催辦/待簽收簽收、承辦中→受會案件→待結案 cascade |
| `pending_doc_handler.py` | 閱覽器分頁、下載（KdApp 對話框 + SendInput）、解壓、清理 |
| `summarize_doc.py` / `summarize_doc.md` | LLM 總結程式 / **業務規則（同事要改）** |
| `fill_in_draft.py` / `fill_in_draft.yaml` | 擬辦填字、儲存、陳會 / 模板 |
| `document_closure/document_closure.py` | 結案存查迴圈 |
| `document_closure/document_closure_post_web.py` | 校網公告 |
| `servisign_utils.py`、`scripts/servisign_session0*.ps1`、`scripts/install_servisign_watchdog.ps1` | 簽章元件健康檢查、session 0、守護排程 |
| `ime_utils.py` | 輸入法切換、桌面狀態偵測 |
| `scripts/close-profile2-chrome.ps1` | 清自動化 Chrome 與 lock 檔 |
| `tests/` | pytest（不碰真實系統） |
| `docs/superpowers/specs`、`plans` | 各功能的設計文件與實作計畫 |
| `run.log`、`chrome_browser.log` | 主 log / Chrome console log |
