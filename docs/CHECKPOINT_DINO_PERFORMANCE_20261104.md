# 2026-11-04 Checkpoint：DINO辨識與效能研究

- Tag：`checkpoint-2026-11-04-dino-performance-research`
- 分支：`codex/next-development-20261103`；上一版：`e154c35` / r2雙圖checkpoint。
- 本機私人備份：`workspace/checkpoints/2026-11-04-dino-performance-research`。
- [機器可讀紀錄](checkpoints/dino-performance-research-20261104.json)。

## 目前正式站台與實驗必須分清楚

18766仍使用r2雙圖：47張螺絲＋65張正常範例，參照圖與待測圖皆判斷，執行方式CPU。待測像螺絲且參照不像才保留。不要因風險自行停用雙圖。

本次保存的正式程式修改包含：更新來源資料夾時立即清空舊清單、忽略過期回應；只顯示來源仍存在的最新照片版本，保留歷史快照與人工紀錄；工程頁CPU/GPU可選擇與保存、隔離DirectML工作程序、GPU失敗可恢復CPU。GPU環境依 `requirements-dino-gpu.txt` 另建，不覆寫原CPU環境。

磁碟程式另包含「GPU啟動失敗後仍可切回CPU」補強，隔離測試通過；先前該補強後的服務重啟未執行，本輪也沒有重啟18766。不能把磁碟程式的每項後續修改都當成現有程序已載入。

最新辨識方法（明暗處理、整體與小區域各半、受限制的二次取圖）以及三項CPU加速仍是離線實驗，**沒有套入正式檢測流程**。固定59案例：已判出的6處維持，原本兩顆及救回長螺絲維持；50個正常位置零誤報；3處助手目視疑似螺絲仍未判出，不能冒充已確認標籤或量產準確率。

## 最新可採信的時間結果

同一張MPT12照片，CPU原方法與合併版各4次交錯，模型與參照已載入，排除資料夾等待。開始檢測到DINO判完：58.06 → 56.77秒，平均省1.29秒／約2.2%。四組皆較快，省0.82～1.61秒；137個候選、兩圖DINO輸入及判斷、368張輸出圖片逐次相同。

先前另一個可攜版PID3244持續重試對齊失敗舊圖並使用CPU。按使用者要求，等它返回錯誤等待、資料庫無處理中／待處理、連續三次低CPU才關閉；11完成＋1錯誤及設定保留。本機18766未停止。不要照抄歷史PID終止新程序；`close_idle_portable.py` 是該次操作紀錄，不能當成通用重啟工具。

GPU在本輪7次檢查及短測均受限於300MHz／10W，要求仍80W，功率及溫度限制標記持續作用。只完成一組螺絲兩圖GPU短測；**未完成正常GPU的8次交錯或137候選全圖核對**，不可宣稱已完成。`gpu_paired_timing.py` 備妥檢查與監控，GPU正常後才可執行有效比較；不得把CPU回退當GPU實測。

正常GPU約13～15秒、2026高功率RTX5080電競筆電約6～8秒都是分段假設推估；包含存好結果、不含資料夾等待，不是新GPU或新筆電實測。廠商規格與假設見換機報告，不能用AI TOPS／遊戲FPS倍數直接除整個流程。

## 報告入口（私人本機）

- 最新CPU交錯實測：`workspace/dino-after-portable-close-20261104/index.html`
- CPU分段與三項優化：`workspace/dino-three-speed-20261104/index.html`
- AI變慢原因與另一可攜版：`workspace/dino-ai-contention-20261104/index.html`
- GPU受限狀態與短測：`workspace/dino-gpu-paired-timing-20261104/index.html`
- 正常GPU時間估算：`workspace/dino-gpu-optimized-estimate-20261104/index.html`
- 2026電競筆電換機估算：`workspace/dino-2026-laptop-estimate-20261104/index.html`
- 固定案例辨識實驗：`workspace/dino-four-remaining-20261103/index.html`

備份snapshot.zip保留原本相對目錄，包含報告、圖片、實驗資料、模型、設定、SQLite一致性快照及r2歷史交付ZIP。原始Pictures/X-Ray外部圖資不搬動；工作區中的來源快照及參照圖一併保存。模型、圖資、完整報告及人工紀錄不推送公開Git。

## 可攜版對應與恢復

本次**未重新打包可攜版**。`dist/XRayReview-DINO-Paired-20261103-r2-Windows-x64.zip` 及相應完整報告仍是上個r2交付，校驗碼見JSON；它們沒有本checkpoint新增的CPU/GPU選項與來源清單後續修正，更沒有啟用最新離線辨識或加速。不要把此checkpoint稱成新的r3執行版。

另台電腦先checkout本tag，再私下移交snapshot.zip並解壓；保留目錄結構恢復需要的models、workspace和設定。外部來源及報告JSON含原機絕對路徑，換機須調整；單靠公開Git無法還原私人模型或圖資。CPU環境與隔離GPU環境依原requirements重建；未備份venv、wheel快取與瀏覽器預覽profile。

## 本次檢查與後續

來源庫存隔離測試、來源切換／CSV／人工紀錄隔離測試、CPU恢復測試、兩份UI競態測試通過。來源切換測試初次因根目錄缺少舊影像fixture失敗，後以固定亂數生成的合成控制圖、XRAY_TEST_FIXTURES覆驗通過；不把這項稱為辨識準確率測試。紀錄存本機checkpoint的checks.json。

未重跑全圖資檢測；未重測受限GPU的59案例。下一步依使用者要求：GPU恢復正常再做同圖交錯；辨識研究與效能優化是否接入正式流程，需另依明確需求處理。圖資報告仍遵守AGENTS.md的全圖資、機種→類型→相近位置規範；本輪明確要求的小實驗保留其範圍說明。
