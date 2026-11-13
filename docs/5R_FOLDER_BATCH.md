# 5r 資料夾批次檢測

在 5r 頁面選擇「NG／OK 資料夾批次檢測與完整報表」，指定本批機種及資料夾後開始。
資料夾名稱須為 `NG`、`OK`、`[NG]` 或 `[OK]`（大小寫皆可）。包含子資料夾的 PNG、JPEG、TIFF、BMP；每個檔名各計一張，重複影像不合併。一批使用同一機種及正常參照圖。

不跟隨檔案／資料夾的符號連結及 Windows junction；無法讀取的子資料夾會回報錯誤，不會將不完整清單冒充完整檢測。

- NG：沒有任何保留警報的照片計為「未檢出掉落螺絲」。有警報不保證命中真正螺絲，位置仍待確認。
- OK：有任何保留警報的照片計為「誤報有掉落螺絲」。這項統計以使用者保證 OK 為正常照片為前提。
- 讀取／檢測失敗不算無警報；與參照圖位元完全相同的照片列為自比，不計入上述兩類。
- 紅／黃保留框均計為警報；框數不是螺絲顆數。對位警告另列。

完成後自動產出完整 HTML、逐張 CSV、原始結果 JSON 和圖片，核對全部照片、保留／排除候選及圖片連結後才標記完成。首頁呈現照片統計，依機種 → 五種類型 → 相近位置瀏覽；未人工分類的候選全列待確認。零候選及失敗照片也有獨立頁面。

每批固定模型快照、機種門檻與正常參照圖副本，逐張重新檢測，結果存於 5r 工作區 `folder-batches/<批次ID>`。來源圖檔與人工紀錄不改寫。重新整理頁面可繼續查看進度；服務程序中斷的批次須重新執行，不會冒充完成。

## 建立獨立站台

先依 START-HERE 核對 Lean、最新參考圖補充包；KPH33 工作另核對 KPH33 包。以下參數指向已驗證還原的資料夾；目的地必須不存在。

```powershell
.venv/Scripts/python.exe tools/prepare_5r_home.py --lean workspace/handoffs/20261109-lean/station --reference-supplement workspace/handoffs/5r-reference-check-20261113 --source-home workspace/4r-live-20261110 --destination workspace/5r-live
.venv/Scripts/python.exe experiments/dino/live5r_service.py
```

使用終端顯示的實際本機網址，再點選 5r 資料夾驗證入口。`XRAY_5R_HOME` 可指定其他隔離工作區。預設 CPU、關閉監看，沿用 52＋90 範例與 4r 雙圖分類，不更動偵測演算法。檔案核對及功能測試不代表全圖資辨識效果已通過驗收。

合成流程測試：`.venv/Scripts/python.exe tools/test_folder_batch5r.py`。

## 2026-11-13 功能驗證

合成 NG／OK 流程已檢查重複檔名逐張計數、子資料夾、無警報、誤報、損壞圖檔、自比分開統計、CSV、全部候選與圖片／錨點連結。

本機另以 20261111 KPH33 圖資的 NG、OK 各一張副本重新執行 CPU 檢測：NG 一張未檢出，OK 一張無警報，處理失敗皆為 0。完整報告分別含 172、147 個候選，完整性核對通過；這是兩張功能測試，不是 61 張回歸或辨識準確率驗收。

本機測試批次：`35603a9c12904412b2078080dbee7ff2`（NG）、`12a99b9a77054a68ba89ea591caf425f`（OK），位於 `workspace/5r-live/folder-batches/`。私人結果不在 Git；跨電腦接續仍須依移交規則處理。
