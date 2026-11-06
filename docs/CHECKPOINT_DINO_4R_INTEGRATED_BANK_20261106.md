# 4r：原庫與新參考案例整合

狀態：100張原尺寸回歸與全報告檢查完成；原要求12組衝突及兩接點穩定性通過，額外135 #88放大125%仍有原／新共通失敗。分支 `4r`，正式流程未修改。

## 實際結果

100張／8335候選：10張不良、89張一般良品、1張參照自比。相同79／101處保住，兩處人工確認與10個B部位保住，B判斷範圍未改且黑塊輸入像素仍為0。NG未對答案警報34→25，未新增位置；良品仍為ok-070 #31及ok-087 #31兩處，自比0。#22與#40在接點終端複核之前已判正常，待測分數−0.2423／−0.0516。

原版100張重建與上輪全部相符。報告110頁、68392個引用、8335候選完整覆蓋，左右欄105頁／16670次候選出現核對通過；首頁、範例附頁與照片左右欄已截圖目視檢查。`final/summary.json`刻意保留`stability_passed=false`，不能把原尺寸回歸通過誤讀為所有縮放通過。

- [100張完整報告](../workspace/dino-4r-integrated-bank-20261106/final/report/index.html)
- [新增警報原因與參考圖](../workspace/dino-4r-integrated-bank-20261106/final/report/attribution.html)
- [整合主庫ZIP](../workspace/dino-4r-integrated-bank-20261106/integrated-reference-collection.zip)

## 使用者要求與人工紀錄

整合原庫與答案圖／Golden的新例，追查新增警報是哪些範例造成。128 #22、#40都應正常；相同79處與128 #10、135 #88兩處人工確認掉落物件要保住；不得新增未對答案警報或良品警報。全圖資報告維持機種→五種類型→相近位置，全部照片與候選、左排除／右保留。

128 #7人工回覆「目前無法判定」，另存於實驗 `human-unconfirmed-128-7.json`。未作正例、正常例或新增答案；保護條件仍要求不新增該未確認警報。

## 固定版本

實驗名稱 `curated_v5_review`，位於 `workspace/dino-4r-integrated-bank-20261106`。

- 主庫51螺絲＋90正常：原47螺絲來源保留，S07／S20使用先前審查的螺絲本體範圍；S05維持原圖。加入P02、P03、P06、P07。原65正常保留，加入25正常例。
- P06及相同位置Golden G06成對使用本體版本；其他新例用context版本。同一來源的core/context沒有當成兩個獨立物件加票。
- P01、P04、P05、P11暫不參與主庫投票，標籤仍為螺絲。正常例G01、N12的視野帶到圓形結構，移至對照用途，未改原標籤。
- 遮擋B局部庫、完整比例47＋65副庫、接點副庫沿用。模型權重、主庫top3及雙圖門檻保持不變。
- 實驗另有分類分支修正：完整輪廓三範圍意見混合時，只要沒有實際結構排除規則，繼續使用既有四範圍副庫複核。不是僅換庫，也不是報告文字修正。

`integrated_bank_build.py`根據配方重建向量並逐元素核對，與實際使用庫完全相同。新例來源仍只有128答案圖與Golden；其餘圖曾用於選版本，不能宣稱盲測。

## 新增警報原因與淘汰方案

固定1345個候選的相同待測輸入，整合全部新例後出現26個單步新增未對答案候選；其中6個在上輪完整流程早已保留，因此相對目前版本真正新出現的是20個單步候選。單步結果不能冒充完整分類成績，也不能把那6個壓掉來湊降低誤報。

逐例移除證據在 `attribution.json`，完整分類對照在 `reference-role-counterfactuals*.json`。

- 原#40最相似舊S07、S05、S20，參考圖背景混入接點紋理。只整理全部三例仍會引出其他邊界警報；最終保留S05原圖，整理S07／S20並補正常例。
- P05／P11的圓頭及周邊背景會增加未確認小圓形、邊界的正例支持；P04能拉高板上元件的單步分數，但是否形成最終警報還要看結構規則。
- G01／N12視野內圓形結構會壓低真螺絲分數；移出後仍要實測其他正常結構，不能直接刪光同位置Golden例。
- P06背景影響板邊小元件；改成P06／G06成對本體，加上保留原S05，才同時保住131答案6及排除邊界／未確認小圓物件。
- P05本體曾通過局部對照，但完整130回放新增#9，因此v4未採用。
- v5在136答案4漏判：一個完整輪廓分數略轉正（+0.00014567）後變成「意見不一致」，反而跳過本來可以命中的既有副庫複核。`integrated_bank_policy.py`修正此銜接，沒有照片ID、答案ID或特定座標條件，實際結構排除仍保留。

## 穩定性測試及未解限制

`stability-curated_v5_review.json`：1260／1260框擾動通過；±4像素，75／90／100／110／125%框大小。12組原衝突共1080／1080，#22／#40共90／90，兩個人工確認螺絲共90／90。

對位後影像同比例縮放，沿用縮放後候選，未重新產生候選：12組原衝突120／120、接點10／10、兩個人工螺絲9／10，合計139／140。

**未解限制：135 #88放大125%時，原版及本版都排除，待測分數完全相同−0.0055936；最相似正／正常例皆來自原庫。** 原尺寸與其他4種影像尺寸保留。長條候選15×89放大為19×111，兩版均未進入完整輪廓複核。原／新完整分類證據在 `human88-scale-diagnosis.json`。不得把整體穩定性寫成全部通過；未標答案衝突只驗證一致性，不增造人工真值。

## 重現與交付

以專案 `.venv/Scripts/python` 執行，`PYTHONIOENCODING=utf-8`；一次一個GPU推論程序。

```text
experiments/dino/integrated_bank_build.py --arm curated_v5_review
experiments/dino/integrated_bank_proof.py --arm curated_v5_review
experiments/dino/integrated_bank_scale_probe.py
experiments/dino/integrated_bank_replay.py --arms original,curated_v5_review --stop-on-regression
experiments/dino/integrated_bank_report.py --arm curated_v5_review
experiments/dino/verify_result_columns.py workspace/dino-4r-integrated-bank-20261106/final
```

回放使用相同100張的凍結對位影像及8335候選，重新執行全部分類分支；相同模型輸入允許重用精確特徵／tensor，不重用舊判斷。原版重建必須對到上輪決策，答案以本輪實際物件範圍重新配對。這不是重新跑對位與候選生成，也不是新批驗收。

最終交付位置：`final/report/index.html`（全100張）、`final/report/attribution.html`（附頁）、`integrated-reference-collection.zip`（實際啟用主庫來源圖與特徵）。完整性檢查在`final/verification.json`，左右欄檢查在`final/column-verification.json`。正式模型、設定、原始圖資與既有人工紀錄不變。
