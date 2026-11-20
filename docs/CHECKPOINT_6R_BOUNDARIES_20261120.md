# 6R 第一輪：責任盤點與完整邊界離線實驗

本輪已完成實際呼叫鏈盤點，以及185張既存對位圖、38,403個既有差異區塊的輪廓實驗。**3129完整物件邊界仍未知，不能稱已修好；沒有接入正式服務。** 5R正式程式及185份結果JSON的SHA均未改。沒有重跑差分或DINO，也沒有新版本推論驗收。

## 必要資料核對

本機沿用同一Lean包還原站台，重新執行：

```powershell
python tools/lean_4r_probe.py --station workspace/handoffs/20261109-lean/station --output workspace/handoffs/probe-6r-start-20261120
```

退出0，`probe-result.json`為`passed`，沒有`--infer`。參考圖補充294檔與KPH33補充1756檔逐檔SHA通過。每張原TIFF、Golden、正式結果SHA另核對；新證據保存輸入對位PNG與既有差異JSON的SHA。沒有下載或另建金鑰，沒有更動站台、圖庫、人工紀錄或設定。

## 實際呼叫鏈（包含執行時替換）

1. `live5r_spatial_service.py`建立`spatial5r_runtime.Engine`，把`library.detect`、`machine_tuning.detect`及資料夾批次綁到`engine.detect`。
2. `Engine.detect`在`new_model_run.four_r`範圍內呼叫`detector.detect`。**只讀detector.py會漏掉實際執行時的proposals、check_candidate、classify替換。** 退出範圍會還原函式。
3. `detector._detect`：全圖對位 → `refine`局部對位 → 機器範圍 → proposals → 候選優先序 → DINO分類 → 寫出保留／排除結果。
4. 實際proposals：明暗校正 → 原差分3px主通道及1px補提 → `improvement_policy.supplemental` → 相似結構補救檢查 → `policy.geometry.proposals`可見部位補提 → 建立同照片Objects。可見部位走獨立check，不再走一般結構排除。
5. 實際分類：`integrated_bank_policy.classify` → `example_audit_policy`及既有分類鏈；完整輪廓可能再次裁圖、雙圖複核；之後`connector_policy.apply`。原pilot.apply在外層被替成直通，因凍結政策內部已呼叫pilot，不能誤計為外層又跑一次。
6. 首次detector結果後依序：`ReviewBundle.apply`警報局部複核 → `spatial5r.apply`外殼補提／碎片複核 → `fragment_core_guard5r` → `enclosure_guard5r` → `enclosure_rescue5r` → `structure_shadow5r` → 已確認U1局部參照建議。最後兩者不自動刪警報；前面的guard／rescue可能改保留／排除，不能統稱只做觀察。

## 責任重複與6R應放的位置

| 現有位置 | 現在做什麼 | 6R最小分工 |
|---|---|---|
| register／refine／compensate_brightness | 對位、明暗可比性 | 保留，記錄可靠度；與物件判定分開 |
| 3px／1px位置容忍 | 在產生候選前消去鄰近結構差異 | 先保留原始差異核心及容忍後證據；移交候選整理判讀，尚不刪正式規則 |
| 3×3開運算、超大區塊7×7開運算 | 去雜點、切開黏連，也可能失去小差異 | 同時保存運算前後連通關係；不要把被消去當正常答案 |
| matching_structure／normal_support／bipolar | 用相似結構、暗區鄰近與正負差分提前篩掉 | 改為候選證據欄位；必須有可靠對應才解釋為結構變動 |
| check_candidate／single_reference_evidence | 再做局部位移及明暗解釋 | 集中到候選整理的一次對應核對，避免每條補提各自決定 |
| tight補提／similarity recovery／supplemental／visible part／外殼補提 | 用不同規則追回前面刪掉或範圍外的部分 | 新流程先保留來源ID與差異核心；驗證涵蓋能力後逐條取代，不能直接全關 |
| 分類鏈、spatial fragment、兩個guard、rescue | 多次尋輪廓、改裁圖、再送DINO | 候選整理先提供共用輪廓假設與不確定性；DINO接收可追溯雙圖裁圖，不在不同階段各自重造物件 |

這是責任盤點與取代順序，不是刪規則清單。本輪只新增離線程式`experiments/dino/boundary_shadow6r.py`，沒有改上述正式檔案。

## 可驗證的最小方案與本輪實作

先固定輸入：沿用前輪185張對位PNG及38,403差異種子。這是8-bit存檔影像上的幾何敏感度實驗，不是從原圖重新產生6R候選；對位及差分重建的驗收仍屬前輪。

三份資料分開：`seed`差異核心；`levels/stable_pairs`輪廓假設；舊`views/state`周邊對應可靠度。完整物件`object_box`本輪一律留空，避免把閉合的板件當完整異物。

固定灰階32、64、96、128、160、192、224，不用檔名、答案或DINO分數選門檻。對整張圖做連通區分析，檢查覆蓋至少半個差異核心，且整個連通區嚴格落在12／20／32周圍範圍內。兩相鄰灰階都支持且框IoU≥0.8才記「閉合輪廓假設」。這些研究條件尚未驗收，不能宣稱為正式判定門檻。

碎片只有在兩個相鄰灰階**都指向同一連通區**才記共同輪廓合併假設；不是距離近就合併，也不做A近B、B近C的傳遞合併。保留全部種子及成員ID，不實際合併、刪除或改警報。不同灰階同成員組去重後計數，但不同組仍可能交疊，不是物件顆數。

## 看圖與實測

| 範圍 | 照片 | 差異核心 | 有閉合假設的核心 | 有閉合假設的照片 | 不同共同輪廓成員組 |
|---|---:|---:|---:|---:|---:|
| 全部 | 185 | 38,403 | 2,003 | 142 | 70 |
| OK（不含自比） | 146 | 23,054 | 1,173 | 104 | 36 |
| NG | 38 | 15,349 | 830 | 38 | 34 |
| 參照自比 | 1 | 0 | 0 | 0 | 0 |

3129中央#158：差異核心仍9×8；灰階32的連通區12×20，已連到下方原有結構，不能把上下兩段合成一顆新物件。灰階64擴到243×251，之後更大，沒有穩定獨立輪廓。新產生的切面圖已實際看過。

另看NG第一個共同輪廓案例（3129非中央#95）及OK第一個案例（history/OK-000002 #2）：NG局部橫向結構和OK既有圓形結構都可能產生閉合輪廓。這只是目視觀察，不新增人工標籤；也說明共同輪廓不能證明是同一個新增異物。

**本輪沒有證明完整邊界改善，也沒有證明候選負擔降到可接受。** 上表2,003不是新增螺絲數，70不是已確認成功去重數，104張也不是新增誤報照片數。沒有把新框送DINO，因完整邊界尚未通過；DINO雙圖規則、門檻和範例不變。

本批24張22/24、2300 #173及原79命中仍是5R既有驗收結果。本輪逐份確認正式JSON不變，**不以此冒稱6R新候選已保住79命中**。3129、3094未確認位置不當人工答案。

## 驗證及完整報告

- `tests/test_boundary_shadow6r.py`四項合成測試：同輪廓、鄰近但分開、板件黏連、僅單一灰階支持；全部通過。合成測試不是私人圖資驗收。
- 私人執行目錄：`workspace/6r-boundaries-20261120`，含`run.py`、`visuals.py`、`report.py`、逐張JSON、`progress.json`、`summary.json`及圖。
- `report/index.html`先列185張完整正式結果，連回全部22,387保留／排除候選及未配對標註圖。比較只在附頁；MPT10／KPH33分開，五種類型列出，未人工分類者為待確認。零候選及自比保留。每個差異核心可返回機種、相近位置及全部證據。
- 新報告檢查圖片、頁面與錨點，收據為`report-verification.json`。前輪統計只作沿用背景，不當本輪重測。
- 沿用的正式完整報告亦重新核對185張、22,387候選、22,405張候選／證據圖片；全部通過，收據`baseline-report-verification.json`。公開摘要見[本輪驗證收據](checkpoints/6r-boundaries-20261120-validation.json)。

## 後續最小實驗

下一步應研究「參照已有結構」與「待測新增輪廓」的聯合分割，保留遮擋／無法分離的未知狀態；不要改成更寬灰階或更大搜尋框來假裝完整。用相同NG／OK全批檢查輪廓及候選負擔，先取得可解釋的物件範圍，再評估合併前後的雙圖DINO裁圖。任何取代正式規則的方案，都還須重新產生候選、重跑DINO並核對2300、本批24張與歷史101標記中的原79命中，不能用這輪不變的JSON代替驗收。

本輪未推送Git、未更新Drive；私人證據與圖不入Git。
