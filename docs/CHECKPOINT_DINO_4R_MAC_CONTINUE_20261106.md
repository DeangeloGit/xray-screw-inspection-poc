# 4r 整合參考庫：Mac 續作入口

本次續作分支是 `4r`，checkpoint 標籤是 `checkpoint-2026-11-06-dino-4r-mac-handoff`。目前實驗版本為 `curated_v5_review`；正式流程、模型預設、原始圖資及既有人工答案未改。

**私人移交包目前仍待加密、上傳、下載回比及隔離還原驗證。** 這份文件本身不是雲端移交成功證據。只有本次移交收據確認 `cloud_verified=true`，才能稱雲端驗證完成；GitHub checkpoint 是否已推送，也須核對實際遠端分支／標籤。

## 已完成的結果

同一批100張、8335候選已完成回歸：10張不良、89張一般良品、1張參照圖自比。這是同批開發回歸，沒有新的獨立不良批次。

- 相同 **79／101處**答案保住；兩處人工確認螺絲及10個被遮擋的B部位也保住。
- 不良圖未對答案警報 **34→25**，沒有新增位置；一般良品仍 **2處**，參照自比 **0處**。未對答案不等於全部已確認誤報。
- 128 #22、#40均判正常，在接點終端複核之前已排除。
- 主庫為 **51個螺絲例＋90個正常例**。原47個螺絲來源保留，整理S07／S20範圍，加入4個螺絲例及25個正常例；另外修正混合輪廓分數跳過既有副庫複核的實驗分支。
- 12組原衝突與兩個接點穩定性通過；全部框擾動1260／1260。
- **未解限制：135 #88放大125%時，原版及整合版都漏判。** 原尺寸與框擾動保留；額外影像縮放總計139／140，不能稱所有縮放測試通過。
- **128 #7人工回覆「目前無法判定」**，未納入螺絲例、正常例或新增答案。不得在Mac續作時自行把它當正常負例。

完整說明見 [本輪整合實驗紀錄](CHECKPOINT_DINO_4R_INTEGRATED_BANK_20261106.md)。報告110頁、全部照片／候選及左右結果欄已驗證；其中 `summary.json` 刻意保留 `stability_passed=false`，避免把原尺寸回歸通過誤讀為全部縮放通過。

## Git與私人資料分開接續

Git保存程式和公開說明；加密移交包保存模型、圖資、報告、實驗資料與人工紀錄。只取得Git不會取得私人圖資；只匯入資料包也不會自動取得本輪新程式。

在Mac使用新的Git checkout或先保護既有未提交工作，取得遠端 `4r` 和上述 checkpoint 標籤，核對兩者實際 commit。不要覆寫現有Mac工作區，也不要把Windows的 `.venv` 帶過去使用。

私人資料依 [Windows／Mac加密移交說明](STATION_HANDOFF.md) 匯入**全新的資料夾**。使用者已在Windows下載資料夾提供原本的 `backup.key`，本次使用這個32 bytes金鑰。Mac使用對應原金鑰；先前另建的 `XRay-4r-20261106.key` 未用於本次移交，請勿拿錯。金鑰不放入Git、私人包或Drive。先完成SHA-256回比、加密認證、檔案檢查及隔離還原，再使用匯入資料。

匯入預設CPU、關閉自動監看、不重跑檢測。核對 `IMPORT-RECEIPT.json` 的來源commit、來源包校驗碼與路徑對照。移交成功只代表檔案／還原驗證成功，不等於Mac已完成ONNX推論或準確率驗收。

## 匯入後的資料位置

移交工具的站台結構與開發checkout不同：

| 內容 | 原開發專案內 | 匯入站台內 |
| --- | --- | --- |
| 私人模型 | `models/` | `models/` |
| 本輪及前輪實驗 | `workspace/dino-*/` | `archives/workspace/dino-*/` |
| 目前站台資料 | `workspace/windows-check/` | `workspace/` |
| 設定的MPT10來源圖 | 外部來源資料夾 | `external/source/` |
| 額外Golden來源資料 | 額外原始圖資資料夾 | `extra/`下，實際名稱以manifest為準 |
| 額外checkpoint | `workspace/checkpoints/`下指定資料夾 | `extra/`下，實際名稱以manifest為準 |

`workspace/checkpoints` 預設不在私人包內，須由匯出時明確加入。Golden的原始來源也應明確加入，不能只因MPT10已收錄就假設Golden原檔齊全。以包內 `TRANSFER-MANIFEST.json` 核對實際清單。

實驗腳本目前固定以Git根目錄的 `workspace/dino-*` 及 `models` 查資料。若要從新的checkout繼續開發，可讓各實驗目錄及模型目錄連到匯入站台的對應位置；先確認目的路徑不存在，禁止覆蓋或合併既有Mac資料。不要把匯入站台整個 `workspace` 誤當成原開發專案的 `workspace`。連結方式與實際路徑應另記錄於Mac續作紀錄。

## 回家可以先做什麼

不必重跑檢測，就能從匯入站台開啟：

```text
archives/workspace/dino-4r-integrated-bank-20261106/final/report/index.html
archives/workspace/dino-4r-integrated-bank-20261106/final/report/attribution.html
archives/workspace/dino-4r-integrated-bank-20261106/final/report/comparison.html
```

首頁是完整100張結果；附頁包含範例歸因、未採用方案、實際改判候選及縮放限制。完整HTML主要使用相對圖片及連結，可在保留資料夾結構的情況下直接瀏覽。若只是整理或分析報告，不要重跑推論，也不要改原答案來配合結果。

後續優先分析135 #88放大125%的共同失敗；其他改進仍須保住相同79處、兩處人工確認及B部位，不增加警報。正式流程繼續保持不變。

## Mac推論與原證據的界線

Mac Python路徑為 `.venv/bin/python`，Windows紀錄中的 `.venv/Scripts/python` 不適用。建立Mac自己的環境，依專案需求安裝CPU版推論依賴。

`integrated_bank_replay.py` 支援 `--provider cpu`；但目前 `integrated_bank_proof.py`、`integrated_bank_scale_probe.py`、`integrated_bank_role_probe.py` 及 `integrated_bank_causes.py` 寫死GPU。不要直接照Windows指令執行，也不要把匯入預設CPU誤認為所有實驗腳本都已支援CPU。若要補上CPU選項，應另建Mac續作變更與驗證紀錄。

目前回放腳本遇到同名既有結果會跳過。因此再次執行相同命令，不代表已在Mac重新推論；要測Mac時，先建立新的實驗輸出與清楚版本，保留原結果。

匯入工具會重定位非模型JSON的路徑值，這會改變部分JSON位元組；而 `plan.hashes`、`source_hashes` 之類字典的Windows絕對路徑鍵不會一併重定位。因此舊的凍結hash驗證不能直接在Mac原樣執行，失敗也不能藉由重寫舊hash消除。

保留原加密包、原manifest及Windows驗收紀錄作證據。Mac使用重定位後的資料繼續分析／開發，另記錄路徑映射、來源包及新的執行驗證；不得把它包裝成原Windows驗收完全不變，或宣稱Mac推論已通過。
