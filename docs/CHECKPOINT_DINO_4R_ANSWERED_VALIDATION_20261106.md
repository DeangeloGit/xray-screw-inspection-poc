# 4r 有答案圖資驗證｜2026-11-06

分支：`4r`。接續 `checkpoint-2026-11-05-dino-r3-overkill-pilot`。
本輪只增加隔離驗證與報告工具，沒有修改正式檢測流程、模型、設定、原始影像或人工紀錄。

## 結果

本批 MPT10 有 10 張待測圖、100 處 PNG 答案，另有 1 張 Golden 自比。
9 張待測圖與舊圖的 SHA-256 相同；第 128 張與舊圖逆時針旋轉 90 度後逐像素相同。
因此是補齊答案後的回歸驗證，不能稱為獨立新圖驗證。

| 固定版本 | 命中答案／100 | 保留候選框 | 未對到答案的警報 |
|---|---:|---:|---:|
| 原 r3 | 30 | 89 | 59 |
| 補抓版，略過結構過濾 | 52 | 121 | 69 |
| 過殺試驗版 | 52 | 118 | 66 |

原 r3 的 30 處答案命中及 89 個保留候選全部保住。過殺過濾移除 3 個答案框外警報，沒有減少過濾前的 52 處答案命中；仍漏掉 48 處答案。
相較原 r3，答案框外警報增加 7 個，不能宣稱整體誤報已較原 r3 更低。
答案框外警報是依提供答案計算的疑似誤報，不是新增人工確認標籤；候選框數不是螺絲顆數。
本批沒有一般良品，Golden 自比零候選不代表一般良品誤報率。

## 固定條件與核對

- 模型 `dino-paired-optimized-47-20261104-r3`，47 張螺絲＋65 張正常範例、DINO 雙圖、門檻 0.13，GPU 執行。
- 3 個版本各跑 11 張，共 33 次檢測。補抓對照只在隔離程序內略過 `structure_rules`，不修改正式模組檔案。
- PNG 紅框先以未標註像素配準至原圖，再沿用前輪的中心重疊匹配規則。兩張歷史 TIFF 答案各 9 處，本次採新 PNG 每張 10 處，不混用答案。
- 全圖資報告涵蓋 11 張照片、861 個保留／排除候選、100 處答案、五種類型（含 0），參照自比分開呈現。
- 已核對 21 個 HTML 頁面、5,566 個連結、1,006 張報告圖片；照片及分類頁候選覆蓋完整，受保護檔案 SHA-256 未變。首頁已實際渲染檢視。

## 本機交付

首頁：`workspace/dino-4r-validation-20261106/report/index.html`

同目錄的 `comparison.html` 為版本比較附加頁，`answers.html` 收錄全部答案及局部放大圖。
實驗目錄保存 `plan.json`、`provenance.json`、`answers.json`、`answer-matches.json`、`cases.json`、`rows.json`、`summary.json`、`verification.json` 及全部原始檢測輸出。
私人圖資與報告維持於忽略追蹤的 workspace，不推送公開 Git。

## 重現工具

1. `experiments/dino/answered_batch_run.py SOURCE OUTPUT`：固定模型與三版本隔離檢測，保存輸入雜湊與逐次完成憑據。
2. `experiments/dino/answered_batch_answers.py OUTPUT`：獨立讀取 PNG 答案、配準與答案局部核對圖。
3. `experiments/dino/answered_batch_provenance.py OUTPUT PRIOR_INVENTORY`：檔案雜湊與旋轉／鏡像後像素重複核對。
4. `experiments/dino/answered_batch_report.py OUTPUT`：沿用全圖資瀏覽格式產生完整報告，執行動態覆蓋、統計、圖片、連結與輸入一致性檢查。

舊的全圖資首頁與驗證器含固定批次數字（190 張、2,793 框等），本輪不更動它們；本輪工具依本批實際數量核對。
