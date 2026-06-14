# doc_classifier

對公文做「處置動作」分類:依使用者累積標註的歷史範例,讓 LLM 推論新公文最合適的動作 (公告 / 存查 / 轉發 / ...)。

## 工作流程

1. **summarize_doc** 為每份新公文產出 `總結.md`
2. **使用者標註**:在 `總結.md` 頂部加一行 `# action: <動作>`
3. **collect_training.sync()** 把帶 `# action:` 的 .md 複製進 `training_data/` (永久家)
4. **classifier.classify_dir()** 對新公文組 prompt → LLM 推論 → 在原 .md 開頭加 `# suggested_action:`
5. 使用者採納建議 → 把 `# suggested_action:` 改成 `# action:` → 下次 sync 自動納入訓練資料

## 執行

```powershell
# 對單一公文目錄分類
py -m doc_classifier.classifier document_download\MW999

# 掃 document_download/MW*/(預設)
py -m doc_classifier.classifier

# 已分類過的也強制重跑
py -m doc_classifier.classifier --force

# 只跑 sync,不分類
py -m doc_classifier.collect_training
```

## 結構

```
doc_classifier/
├─ classifier.md         ← LLM 業務規格 (改規格只動這檔)
├─ actions.yaml          ← 動作清單 (隨時可加)
├─ classifier.py         ← 主入口 (classify_dir / run_one / main)
├─ collect_training.py   ← 訓練資料同步
├─ log_utils.py          ← runs.log 寫入 + rotate
├─ training_data/        ← (gitignored) 已標註資料永久家
├─ runs.log              ← (gitignored) 執行紀錄
├─ example_data/         ← 測試用假資料
└─ tests/                ← pytest
```

## 設計原則

- **規格全交 LLM 執行**:`classifier.md` 用 markdown 寫業務規則,LLM runtime 讀;Python 不重複規格條文。改規格只動 .md,程式不動。
- **LLM backend 重用**:`from summarize_doc import _llm_summarize_claude_code, _llm_summarize_anthropic`
- **訓練資料永久家**:`training_data/` 獨立於 `document_download/`,後者刪了也不影響
- **可獨立執行,亦可被主程式呼叫**:`from doc_classifier.classifier import classify_dir`

## 驗收標準

見 [spec §11](../docs/superpowers/specs/2026-05-24-doc-classifier-design.md#11-驗收標準-使用者肉眼驗收)。
