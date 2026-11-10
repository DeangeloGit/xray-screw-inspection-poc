# X-RAY 續作入口

**最新 4r 參考圖上傳功能版本：**先讀 [2026-11-10 圖庫版本與啟動說明](docs/CHECKPOINT_4R_REFERENCE_UPLOAD_20261110.md)。除了下方 Lean 包，還必須下載並核對新參考圖補充包，缺件就停止；GitHub 不含私人圖庫。此版本未完成完整回歸。

KPH33 SKU=1006A 最新研究接續：先讀 [KPH33 補充包說明](docs/CHECKPOINT_KPH33_20261110.md)。它需要下述已驗證的精簡站台與另外加密的 KPH33 證據補充包；不可把歷史結果稱為新環境重驗。

目前續作分支：`4r`。
入口更新 checkpoint：`checkpoint-2026-11-10-dino-handoff-required`。
KPH33 資料與雲端驗收 checkpoint：`checkpoint-2026-11-10-kph33-4r-cloud-verified`。

## 接續前必做：取得並核對 DINO 圖庫

**GitHub 只有程式與文件，不包含私人 DINO 模型、參考圖或特徵。下載程式不會自動取得 Google Drive 資料。**不要直接開始檢測、比較模型或判讀 DINO 範例。

1. 到 [X-RAY 專用 Google Drive 資料夾](https://drive.google.com/drive/folders/1QBfJNjDh9RpPe6bNr3HpC7ZBrCDkDzi2) 下載 **2026-11-09 Lean 加密包**：六段、分段清單及 SHA-256。此包才有 DINO 模型、原 47＋65 範例、4r 的 51＋90 整合範例及副庫。已從同一包驗證還原的本機站台可重用，但仍須重新核對檔案。
2. 使用另行安全取得的原 `backup.key`，依 [Lean 包操作步驟](docs/CHECKPOINT_DINO_4R_LEAN_MAC_20261109.md#mac操作) 驗證、重組及還原到新站台，再執行 `tools/lean_4r_probe.py` 的檔案核對模式；必須退出碼 0 且 `probe-result.json` 的 `status` 為 `passed`。這不是推論驗收。
3. 接續 KPH33 時，再取得並還原 **2026-11-10 KPH33 補充包**：三段、分段清單及 SHA-256；核對完整報告及 10 張待測、10 張答案和 Golden。步驟見 [KPH33 補充包說明](docs/CHECKPOINT_KPH33_20261110.md)。補充包不含模型與 DINO 圖庫，不能替代 Lean 包。
4. Drive 無法存取、原金鑰不存在、任一必要檔案缺失或驗證失敗時，**停止依賴這些資料的工作，明確告知缺件／錯誤**。不能假設 GitHub 已有圖庫，不能使用空庫、替代模型或舊結果冒充驗證通過。不要把金鑰貼到對話或上傳。

先讀 [精簡Mac續作與資料匯入](docs/CHECKPOINT_DINO_4R_LEAN_MAC_20261109.md)，再讀 [本輪整合與驗證](docs/CHECKPOINT_DINO_4R_INTEGRATED_BANK_20261106.md)。11月9日改為必要資料包：只帶128／135／Golden原圖，保留最新完整報告與所有必要DINO參考圖，不帶整批原始測試資料。

100張回歸保住相同79處；未對答案警報34→25，良品2，自比0。135 #88放大125%仍有原/新版共同失敗，未宣稱全部穩定性通過。正式流程保持不變。

私人模型、圖資與報告在另行加密移交包；Git不含這些資料。六段加密包已實際下載回比與隔離還原通過，驗證紀錄見 [移交收據](docs/checkpoints/lean-4r-20261109-cloud-verification.json)。
