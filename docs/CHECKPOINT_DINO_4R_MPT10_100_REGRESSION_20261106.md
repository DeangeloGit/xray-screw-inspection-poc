# 4r MPT10 100張回歸與左右排版｜2026-11-06

分支為 `4r`。使用者指定 `C:\Users\Deangelo_Hu\Pictures\X-Ray\MPT10`；核對後10張不良圖全部與原開發批重複。使用者已明確回覆「目前沒有，先完成這100張回歸」，本輪不再聲稱要取得或已完成獨立新批驗收。

## 交付

- [100張全圖資報告](../workspace/dino-4r-crossbatch-20261106/report/index.html)
- [版本與資料來源核對](../workspace/dino-4r-crossbatch-20261106/report/comparison.html)
- [完整性核對](../workspace/dino-4r-crossbatch-20261106/verification.json)
- [左右欄逐候選核對](../workspace/dino-4r-crossbatch-20261106/column-verification.json)
- [原79處全圖資報告，亦已更新左右排版](../workspace/dino-4r-example-audit-20261106/final/report/index.html)

## 實際結果

凍結目前79處版本的規則、模型、範例庫與門檻，從指定來源完整重跑100張；沒有依這批調參，正式流程、正式模型與原圖未變。

| 組別 | 照片 | 結果 |
|---|---:|---|
| 不良品回歸 | 10 | 原79／101處完全保住；答案框外警報50，逐張不增加 |
| 一般良品 | 89 | 2張各1個警報；前輪69版與目前79版皆為2，沒有新增或移除的良品警報 |
| 參照自比 | 1 | 0警報，獨立列出、不算一般良品績效 |

兩個良品警報為 `ok-070-31`、`ok-087-31`，來源分別為 `CND6440BQ3_2026_11_02_16_42_19_70.tiff` 與 `CND6440BQ3_2026_11_02_16_55_50_87.tiff`。保留供核對，不因報表好看而刪除；依OK來源視為良品警報，未冒稱新增人工逐框正常標籤。

全批8335候選：保留140、排除8195。候選框數不等於螺絲顆數。109個報告頁、68269個連結／圖片引用、8645張圖片均核對通過。105個照片／類型頁共16670個候選呈現，恰為8335候選各在照片及類型頁各一次；左右結果完全正確。首頁、實際候選欄與比較頁已渲染檢視。

## 不能稱獨立驗收的原因

9張NG檔案SHA與原批完全相同；128是同影像旋轉90度後逐像素相同。答案沿用原101處；128只用已核實的像素旋轉做座標轉換 `x_new=W-1-y_old, y_new=x_old`，沒有依預測移動或新增答案。新舊命中集合逐處一致，不只比總數。

31個正常範例ID中的來源SHA對到24張本資料夾良品，這24張的警報前後都是2；其餘65張在此ID命名查不到來源匹配，警報前後都是0，但不宣稱這65張從未參與先前開發。獨立新不良圖為0。

參照沿用79處版本的 `Downloads/XRay_Screw_20261106/XRay_Screw/Golden.tiff`，其位元組等同本次OK資料夾的74號影像。不要與更早r3全圖資使用95號參照的成績混比。

## 執行及比較證據

`experiments/dino/crossbatch_run.py` 在新的隔離runtime執行相同 `example_audit_policy.py`，沒有改判斷規則。前輪69版分類另存 `baseline69-classifications.json`；若新保留輪廓影響B重複框排除，會使用前輪保留輪廓集合獨立重算前輪B判斷。原10張NG的2332個前輪完整分類紀錄，已與既有69版逐項核對完全相同。

資料在 `workspace/dino-4r-crossbatch-20261106/`：

- `source-inventory.json`：100張來源雜湊及原批重複證據。
- `plan.json`：固定模型、來源、規則及程式雜湊。
- `runs/<key>/result.json`、`complete.json`：逐張完整新檢測與完成憑據。
- `original79-regression.json`：相同79處與框外50核對。
- `baseline-reconstruction-check.json`：2332個完整前輪分類一致。
- `example-source-overlap.json`：31個正常範例ID與24張來源的命名雜湊匹配。
- `answer-coordinate-transforms.json`：128的純旋轉座標換算。
- `summary.json`、`cases.json`、`rows.json`、`answer-matches.json`：全量結果。

`crossbatch_report.py` 產生完整100張報告；`verify_result_columns.py` 核對所有候選所在結果欄。報告重整不重跑檢測。`crossbatch_run.py` 的完成檔有快取；未來改規則或來源必須另開輸出目錄，不能沿用本輪結果宣稱新推論。

## 固定排版

候選區左側「排除」、右側「保留警報」，同側只放相同結果；每張照片及各類型的相近位置群組都遵守。同類群組每側先顯示代表案例，再展開其餘相同結果。每個候選內部仍是左參照、右待測，追溯連結不變。

共用報告樣式與分欄在 `experiments/dino/result_columns.py`，已套用 `answered_batch_report.py` 與本輪100張報告。原79處報告只重整排版，實際檢測結果未改。小螢幕採左右滑動保持兩欄，不把排除與保留混排。

下一輪仍保護79／101及NG框外50；本資料夾89張良品的2個既有警報亦可作回歸基準。深色喇叭20處及小圓頭混合背景2處的暫緩指示未撤銷。獨立新批驗收仍待使用者提供不同拍攝且附答案的資料。
