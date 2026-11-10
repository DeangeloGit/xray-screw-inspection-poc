# KPH33 1006A 4r 實驗補充包（2026-11-10）

**接續前置條件：先從專用 Drive 取得並驗證還原 2026-11-09 Lean 包，執行 `tools/lean_4r_probe.py` 不加 `--infer`；退出碼必須是 0，`probe-result.json` 的 `status` 必須是 `passed`。**Lean 包提供 DINO 模型、原 47＋65 參考圖，以及 4r 的 51＋90 參考圖與副庫；本 KPH33 補充包沒有這些檔案。已驗證還原的 Lean 站台可沿用，但仍須先執行檔案核對。

缺少 Drive 權限、原金鑰、Lean 模型／參考圖／特徵、KPH33 補充資料，或任一核對失敗時，停止依賴該資料的分析與檢測，回報具體缺件。不要用替代模型、空庫或既有報告數字當成通過。檔案核對不等於新環境已重跑推論。

這是 KPH33 研究證據補充包，不是完整站台備份。先取得 `checkpoint-2026-11-09-dino-4r-lean-mac-verified` 及其已驗證的加密精簡站台；該包含必要 DINO 模型與參考範例，本補充包不重複上傳。

補充包涵蓋 10 張 KPH33 待測、10 張答案、1 張 Golden、完整 4r 報告及相依證據、r3／4r 保存的結果與對位影像。排除其他機種的原始測試圖、重複單候選中間裁圖、快取及環境。保留原報告的完整圖片，不重跑檢測。資料以原 backup.key 使用 XRAYENC1 加密，金鑰不放入 Git 或 Drive。

此批依答案計 48 個區域：4r 命中 2、漏失 46；27 個未對答案警報框按同照片及實際取圖合併為 5 組，不能直接視為 5 個已人工確認誤報。10 張是同序號相近位置的重複拍攝，沒有獨立良品，不能推論良品誤報率。原 r3 命中 4，4r 保住 1、失去 3、新增 1。影像與既有紀錄為歷史結果，不能稱為新環境重驗。

從 Drive 專用資料夾下載本補充包的所有 `.partNNN`、`.parts.json` 與 `.sha256`，放同一目錄，以新 checkout 中的工具在新資料夾重組並隔離還原：

```sh
python tools/transfer_parts.py join "$HOME/Downloads/KPH33-4r-20261110.xray.enc.parts.json" --output "$HOME/KPH33-download-20261110/KPH33-4r-20261110.xray.enc"
python tools/kph33_supplement.py restore "$HOME/KPH33-download-20261110/KPH33-4r-20261110.xray.enc" --key-file "$HOME/.config/xray-transfer/backup.key" --destination "$HOME/KPH33-evidence-20261110"
```

還原工具不覆寫既有目錄，AES-GCM 認證後逐檔核對 SHA-256，不匯入或覆寫站台。完整報告是 `evaluation/report/index.html`，逐處對帳是 `evaluation/report/decision.html`。原計畫與結果的 Windows 絕對路徑保留為歷史證據，在 Mac 或 Gemini 建立新實驗時應產生新的路徑及計畫，不要改寫舊 plan/hash 假裝原始驗證。此補充包不是針對 Mac 的推論驗收。

還原後核對 `source/待測` 有 10 張、`source/Answer` 有 10 張、`source/Golden` 有 1 張 TIFF，且上述兩個報告頁及 `SUPPLEMENT-MANIFEST.json` 存在。工具成功退出及清單逐檔 SHA 驗證是必要條件；資料夾存在或只看舊收據都不夠。若數量、檔案或驗證有誤，停止並回報。

後續：先釐清電池外緣遮罩與三處差分碎片，對比未對齊、既有對齊及新色調對齊；DINO 固定同一裁圖比較新舊庫。先做局部實驗，保護原有命中與誤報，完整回歸須另取全部必要原圖。正式流程未改。

## 2026-11-10 雲端驗收

補充包 227,641,504 bytes（約 217 MiB），三段；整包 SHA-256：`03f8f7d70816b360c0b8035eb9f528affd3cc07e2a44e26a3c02f1e908829c70`。三段、清單及校驗檔已從專用 Drive 實際下載，逐段及整包回比後，以原金鑰完成 1,756 檔隔離還原。驗收為補充包，不宣稱它本身是完整站台或 Mac 推論驗收。[驗收收據](checkpoints/kph33-20261110-cloud-verification.json)。
