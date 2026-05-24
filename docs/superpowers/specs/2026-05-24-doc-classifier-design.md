# 公文處置分類器 (doc_classifier) 設計

- **日期**：2026-05-24
- **作者**：ldc (透過 brainstorming skill 與 Claude 對話產出)
- **狀態**：草稿,待使用者確認

## 1. 目標

讓 Claude Code 透過「累積使用者標註」逐步學會處置公文的方式 (公告 / 存查 / 轉發 / 會辦 / ...)。新公文進來時自動產出「建議處置 + 信心 + 引用範例」,供使用者決策。

## 2. 範圍 (Scope)

### 包含
- 收集使用者在 `總結.md` 內手動填寫的 `# action:` 欄位,複製進獨立 `training_data/` 永久保存
- 對單一公文目錄產出 `# suggested_action: <動作> (信心:高/中/低)` 並寫回該公文的 `總結.md`
- 動作清單以 `actions.yaml` 集中管理,可隨時新增
- 獨立資料夾 `doc_classifier/`,可獨立執行,未來可被 `main.py` 鏈式呼叫

### 不包含 (Non-goals)
- **不**自動執行任何處置 (不點 edoc 的「存查」「結案」按鈕、不自動發公告)
- **不**做 embedding 檢索 / 向量索引 (預留升級口,但本次不寫)
- **不**做 fine-tune / 訓練真模型 (與 Claude 訂閱架構不相容)
- **不**做 GUI 標註介面 (使用者以 VSCode 直接編輯 `總結.md`)
- **不**主動推測 `actions.yaml` 之外的動作

## 3. 關鍵決策紀錄

| 決策 | 選擇 | 為何 |
|------|------|------|
| 學習機制 | LLM few-shot (歷史標註當範例庫) | Claude 不開放 fine-tune;資料量小;可解釋;隨改隨生效 |
| 範例挑選 | 全部丟給 LLM (不檢索) | YAGNI;1 個月 ~50-100 封,半年 500 筆內 token 還夠;升級口已留 |
| 動作清單 | `actions.yaml` 動態 | spec 階段不固定;打標時遇到新動作隨手加 |
| 標註介面 | 在既有 `總結.md` 加 `# action:` 行 | 零新 UI,與 VSCode 工作流無縫 |
| 訓練資料儲存 | 獨立 `doc_classifier/training_data/`,複製進來 | 之後刪 `document_download/` 不傷訓練資料;集中管理已標清單 |
| 執行階段 | 本次只做分類器,不做執行器 | 先驗證分類效果,執行器是另一個獨立 spec |
| LLM backend | 重用 `summarize_doc.py` 的 `claude -p` / Anthropic SDK | 不維護兩份 backend |

## 4. 目錄結構

```
sssh-automation/
├─ doc_classifier/                    ← 新增,獨立模組
│  ├─ classifier.md                   ← 業務規格 (LLM runtime 讀)
│  ├─ classifier.py                   ← 入口:對單一 MW 目錄做分類
│  ├─ collect_training.py             ← I/O:同步 document_download → training_data
│  ├─ actions.yaml                    ← 動作清單 config
│  ├─ training_data/                  ← 已標註 .md 永久家 (空目錄,執行後填入)
│  ├─ runs.log                        ← 分類器執行紀錄 (ISO 8601 + rotate)
│  └─ README.md                       ← 模組說明
│
├─ document_download/<MWxxx>/         ← 既有結構,不動
│  └─ <主檔名>總結.<model>.md         ← 使用者在此加 `# action:`
│                                        分類器在此寫回 `# suggested_action:`
│
└─ main.py / summarize_doc.py / ...    ← 既有,不動
```

## 5. 模組分工

### classifier.py — 入口
- 介面:`python doc_classifier/classifier.py <MW目錄>` 或 `python doc_classifier/classifier.py` (掃 `document_download/MW*/`)
- 流程:
  1. 呼叫 `collect_training.sync()` 同步訓練資料
  2. 讀 `training_data/` 所有 .md,抽 `(主旨, 標記字詞, action)` 三元組
  3. 讀 `classifier.md` 規格全文、`actions.yaml` 動作清單
  4. 讀目標 MW 目錄的 `總結.md` (待分類公文)
  5. 組 prompt → 呼叫 LLM backend
  6. 解析回應 → 在目標 `總結.md` 開頭加 `# suggested_action:` 與 `# cited_examples:` 兩行 + reasoning
  7. `runs.log` 加一行
- 預設不覆蓋已分類過的 .md,加 `--force` 才覆蓋
- 提供 `classify_dir(mw_dir)` 給 `main.py` 鏈式呼叫

### collect_training.py — 訓練資料同步
- 介面:`python doc_classifier/collect_training.py` 或 import `sync()`
- 流程:掃 `document_download/MW*/總結*.md`,挑「有 `# action:` 欄位」的,複製進 `training_data/`,檔名直接用原檔名 (公文檔名含唯一公文號,不會撞名)
- 比對 mtime,`document_download/` 較新就覆蓋 `training_data/`
- 反向:`training_data/` 有、`document_download/` 已被使用者刪 → 保留不動 (這正是「永久家」的意義)
- 印 summary:「同步 N 筆;新增 X、更新 Y、保留孤兒 Z」

### classifier.md — 業務規格 (LLM 讀)

```markdown
# 公文處置分類規格

## 任務
依「歷史範例」推論新公文最合適的處置動作。

## 輸入
- 動作清單 (actions.yaml 的內容,本次允許值)
- 歷史範例 (training_data/ 內所有 .md,每份含主旨、發文機關、標記字詞、action)
- 待分類公文 (一份 .md,內含主旨、發文機關、標記字詞,無 action)

## 判斷依據優先順序
1. 主旨、說明的語意
2. 標記字詞 (# 資安 / # 汰換 / # 校務行政 ...)
3. 發文機關
4. 發文字號的字頭

## 信心分級
- 高:有 ≥2 個高度相似的歷史範例 (同標記、同類主旨) 全部都同一 action
- 中:歷史範例方向一致但相似度普通,或只有 1 個高度相似範例
- 低:無強範例,主要靠語意推測

## 輸出格式 (嚴格)
第一行: # suggested_action: <動作> (信心:高/中/低)
第二行: # cited_examples: <MW目錄名>, <MW目錄名>, ...    (最多 5 個,只列「真的被當依據」的範例)
第三行起: <reasoning,繁體中文,<100 字,寫「為何選這個動作」>

## 例外處理
- 若 training_data/ 為空 → 回 SKIP,不要硬猜
- 若所有歷史範例皆無與本公文相關之線索 → 信心:低,reasoning 註明「無強範例」
- 若主旨明顯落在 actions.yaml 外的動作 → 仍須從清單選最接近者,但 reasoning 標註「最接近清單動作」

## 不要做的事
- 不要附引言區塊、簽名、「輸出結束」標記等
- 不要解釋輸入內容、不要列訓練資料統計
- 不要創造 actions.yaml 之外的動作
```

### actions.yaml — 動作清單

初始空清單,使用者第一次標註時依需求加入。範例:

```yaml
actions:
  - 公告
  - 存查
  - 轉發
  - 會辦
  - 自辦
  - 簽呈
```

## 6. 資料流

### 6.1 標註階段 (使用者)

```
document_download/MW001/xxx總結.md   ← 使用者用 VSCode 開,頂部加 `# action: 公告`
document_download/MW002/yyy總結.md   ← 使用者加 `# action: 存查`
            │
            ▼
    python doc_classifier/collect_training.py
            │
            ▼
doc_classifier/training_data/
    xxx總結.<model>.md     (內含 `# action: 公告`)
    yyy總結.<model>.md     (內含 `# action: 存查`)
```

### 6.2 分類階段 (新公文進來)

```
MW999/總結.md (summarize_doc.py 剛產出,無 action)
            │
            ▼
    python doc_classifier/classifier.py document_download/MW999
            │
            ├─ 1. collect_training.sync() (拉新標註進 training_data)
            ├─ 2. 讀 training_data/ 抽 (主旨, 標記, action) list
            ├─ 3. 讀 classifier.md + actions.yaml
            ├─ 4. 讀 MW999/總結.md (待分類)
            ├─ 5. 組 prompt → claude -p (或 anthropic SDK fallback)
            ├─ 6. LLM 回 (suggested_action, confidence, cited_examples, reasoning)
            ├─ 7. 在 MW999/總結.md 開頭加 3 行:
            │     # suggested_action: 公告 (信心:高)
            │     # cited_examples: MW001, MW005
            │     <reasoning 一段>
            └─ 8. runs.log 加一行
```

### 6.3 Feedback loop

使用者看到 `# suggested_action: 公告 (信心:高)` 後,若採納,把它改成 `# action: 公告` (或新增 `# action:` 行,保留 `# suggested_action:` 也可,以 `# action:` 為準)。下次 `collect_training.sync()` 自動把這筆拉進 `training_data/`,後續分類器看得到。

## 7. LLM 互動約定

### 7.1 Prompt 結構

```
<開場宣告任務>
=== 規格 (classifier.md 全文) ===
<classifier.md 內容>

=== 動作清單 (actions.yaml) ===
- 公告
- 存查
- ...

=== 歷史範例 (training_data/ 全部) ===
#### MW001 / xxx總結.md
<該檔全文>
---
#### MW002 / yyy總結.md
<該檔全文>
---
...

=== 待分類公文 ===
#### MW999 / zzz總結.md
<該檔全文 (除掉 # action 與 # suggested_action 行)>

=== 輸出格式提醒 ===
僅按 classifier.md「輸出格式」段落產生輸出,無多餘文字。
```

### 7.2 Backend 重用

`classifier.py` 直接 `from summarize_doc import _llm_summarize_claude_code, _llm_summarize_anthropic`。

兩函式維持私有底線命名 (向後相容),分類器引入時不重命名;後續若需公開化,在 `summarize_doc.py` 加 public alias,不破壞既有匯入。

### 7.3 解析回應

正規表達式:
- `^#\s*suggested_action:\s*(\S+)\s*\(信心:(高|中|低)\)\s*$` → (action, confidence)
- `^#\s*cited_examples:\s*(.+)$` → comma-split list
- 之後所有內容 (含中間空行) → reasoning,頭尾 trim

格式不符 → 印 error、不寫回、`runs.log` 記「LLM 格式錯誤」。

### 7.4 Prompt 預處理

組 prompt 時,把 `training_data/` 內每份 `.md` 的 `# suggested_action:` 與 `# cited_examples:` 行 strip 掉,只保留 `# action:` 與公文內文 — 避免 LLM 把過去的「建議」當金標 (`# action:` 才是被使用者確認的真實標籤)。

## 8. Edge cases

| 情境 | 處理 |
|------|------|
| `training_data/` 完全沒檔 (冷啟動) | LLM 回 SKIP;`runs.log` 記「無訓練資料」;不寫 `# suggested_action:` |
| 待分類目錄沒 `總結.md` | 印 error「summarize_doc 沒跑過?」`exit 1` |
| `總結.md` 已含 `# suggested_action:` | 預設跳過、不覆蓋;`--force` 才強制重跑 |
| `actions.yaml` 缺檔或空 | 印 error,`exit 1` |
| LLM 回的動作不在 `actions.yaml` 內 | 印 warning、不寫回、`runs.log` 記「LLM 違反清單」 |
| `training_data/` 有但 `document_download/` 已刪 | 保留 `training_data/` 不動 (永久家原則) |
| `總結.md` 有 `# action:` 也有 `# suggested_action:` | sync 時兩個都帶走 (`# action:` 為訓練資料來源,`# suggested_action:` 只是歷史紀錄不影響) |
| LLM backend 全不可用 | 印 error、`runs.log` 記;`exit 1` |

## 9. 日誌規範

`doc_classifier/runs.log` 沿用全域規則:

- 每行 ISO 8601 開頭:`YYYY-MM-DDThh:mm:ss`
- 檔案 >10MB 時 rotate:`runs.log` → `runs.log.1` (最多保留 6 份,亦即 .1 ~ .6)
- 格式範例:

```
2026-05-24T14:30:01 MW999 suggested=公告 confidence=高 examples=MW001,MW005
2026-05-24T14:30:15 MW998 SKIP reason=無訓練資料
2026-05-24T14:30:42 MW997 ERROR reason=LLM格式錯誤 raw=...
```

## 10. 測試策略

### 單元測試 (`tests/` 或 `doc_classifier/tests/`)
- `collect_training.sync()`:準備假 `document_download/` 樹 → 跑 sync → 驗 `training_data/` 內容
- prompt 組裝:給定 fixtures (3 份假 training + 1 份待分類) → 驗 prompt 字串包含必要區塊
- 回應解析:餵 LLM 樣本回應 → 驗 (action, confidence, examples, reasoning) 拆解正確
- LLM 呼叫 monkeypatch:不打真 API

### 不寫的測試
- 「LLM 分類正確率」── 那是 prompt engineering 議題,看 `runs.log` 比寫 unit test 實際

### `doc_classifier/example_data/` 提供:
- 3-5 份做好的假 `總結.md` (含 `# action:`) 給單元測試使用
- 1 份待分類假 `總結.md`

### 提交前
- `python doc_classifier/classifier.py --help` 不爆
- `python doc_classifier/collect_training.py` 在空 `document_download/` 下不爆
- 跑 pytest 全綠 (沿用 [CLAUDE.md](../../../CLAUDE.md)「提交前必須執行測試」)

## 11. 驗收標準 (使用者肉眼驗收)

1. **冷啟動 SKIP**:`training_data/` 為空時跑 `classifier.py` → LLM 回 SKIP、不寫回、`runs.log` 記錄
2. **單筆訓練即可推論**:手動標 1 份,跑分類 → 出 `# suggested_action:` 但信心應 = 低
3. **5-10 筆後合理推論**:手動標 5-10 份,挑一份**已知答案**的新公文 → 看建議是否合理
4. **新類型公文低信心**:累積 20-30 份後,故意拿一份新類型公文 → LLM 應給「低信心」(證明 LLM 知道自己不知道,比給正確答案更重要)
5. **Feedback loop**:把建議改成 `# action:` → 跑 sync → `training_data/` 出現該筆

## 12. 未來擴充預留

設計上**留口、本次不做**:

- **embedding 檢索層**:只動 `_select_examples()` 函式,介面不變
- **GUI 自動執行**:分類器只輸出 `# suggested_action:`,不動 edoc。未來加 `executor.py` 讀此欄位、判斷低風險、再走 edoc selenium
- **準度回饋面板**:`runs.log` + 後來人工確定的 `# action:` 已能算 accuracy,未來補簡單 CLI 統計

## 13. 與既有專案的關係

- **不改** `main.py` / `summarize_doc.py` / `pending_doc_handler.py` / `document_system.py`
- 從 `summarize_doc.py` import 兩個 LLM backend 函式 (read-only 重用)
- `main.py` 未來可加一行 `from doc_classifier.classifier import classify_dir`,但本 spec 不要求此步驟

## 14. 部署與相容性註記

- `doc_classifier/training_data/` 內容因含校內公文資料,**加入 `.gitignore`**,不推 GitHub
- `doc_classifier/runs.log` 同理加入 `.gitignore`
- `doc_classifier/actions.yaml` **要** commit (是 config,跨環境共用)
- 程式啟動時自動 `mkdir -p training_data/` (因 git 不追蹤空目錄,clone 後不存在)
- 新增相依套件:`pyyaml` (讀 `actions.yaml`);在 `README.md` 的安裝指令加入

## 15. 已知未決問題

- (無) — 設計階段所有關鍵問題已釐清
