# KPH33 1006A 4r 實驗補充包（2026-11-10）

這是 KPH33 研究證據補充包，不是完整站台備份。先取得 `checkpoint-2026-11-09-dino-4r-lean-mac-verified` 及其已驗證的加密精簡站台；該包含必要 DINO 模型與參考範例，本補充包不重複上傳。

補充包涵蓋 10 張 KPH33 待測、10 張答案、1 張 Golden、完整 4r 報告及相依證據、r3／4r 保存的結果與對位影像。排除其他機種的原始測試圖、重複單候選中間裁圖、快取及環境。保留原報告的完整圖片，不重跑檢測。資料以原 backup.key 使用 XRAYENC1 加密，金鑰不放入 Git 或 Drive。

此批依答案計 48 個區域：4r 命中 2、漏失 46；27 個未對答案警報框按同照片及實際取圖合併為 5 組，不能直接視為 5 個已人工確認誤報。10 張是同序號相近位置的重複拍攝，沒有獨立良品，不能推論良品誤報率。原 r3 命中 4，4r 保住 1、失去 3、新增 1。影像與既有紀錄為歷史結果，不能稱為新環境重驗。

從 Drive 專用資料夾下載本補充包的所有 `.partNNN`、`.parts.json` 與 `.sha256`，放同一目錄，以新 checkout 中的工具在新資料夾重組並隔離還原：

```sh
python tools/transfer_parts.py join "$HOME/Downloads/KPH33-4r-20261110.xray.enc.parts.json" --output "$HOME/KPH33-download-20261110/KPH33-4r-20261110.xray.enc"
python tools/kph33_supplement.py restore "$HOME/KPH33-download-20261110/KPH33-4r-20261110.xray.enc" --key-file "$HOME/.config/xray-transfer/backup.key" --destination "$HOME/KPH33-evidence-20261110"
```

還原工具不覆寫既有目錄，AES-GCM 認證後逐檔核對 SHA-256，不匯入或覆寫站台。完整報告是 `evaluation/report/index.html`，逐處對帳是 `evaluation/report/decision.html`。原計畫與結果的 Windows 絕對路徑保留為歷史證據，在 Mac 或 Gemini 建立新實驗時應產生新的路徑及計畫，不要改寫舊 plan/hash 假裝原始驗證。此補充包不是針對 Mac 的推論驗收。

後續：先釐清電池外緣遮罩與三處差分碎片，對比未對齊、既有對齊及新色調對齊；DINO 固定同一裁圖比較新舊庫。先做局部實驗，保護原有命中與誤報，完整回歸須另取全部必要原圖。正式流程未改。
