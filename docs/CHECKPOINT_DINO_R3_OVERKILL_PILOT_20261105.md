# X-RAY r3 過殺改善試驗版交接

- Git 分支 `codex/next-development-20261103`
- Checkpoint `checkpoint-2026-11-05-dino-r3-overkill-pilot`
- 上一版 `checkpoint-2026-11-05-dino-r3-rd-handoff`
- 本機續作清單 `workspace/checkpoints/2026-11-05-dino-r3-overkill-pilot/START-HERE.md`
- Windows 可攜包 `XRayReview-DINO-r3-Overkill-Pilot-20261105-Windows-x64.zip`

## 這版在做什麼

1. 原 r3 保留的候選沿用原判定。差分找到緊湊黑影，周圍雖與正常圖相像，補償後仍有新增黑影時，補送候選給 DINO。
2. 待測圖原本判不像螺絲時，只對符合尺寸的候選重看兩張小圖。縮小取圖，增加新增黑影位置的權重，再核對側面螺絲範例。正常圖沒有、待測圖有螺絲才新增報出。
3. 只對前兩項新增的警報檢查原有接頭、板件和孔位。三項規則沿用上一輪小實驗。範例庫有變動時，應用程式使用該模型原有判斷。

可攜包預設開啟這套試驗規則，使用 47 張螺絲、65 張正常範例與雙圖。CPU 為預設，也可以在工程頁切換 GPU。Git 原始碼啟動時需明確設定 `XRAY_OVERKILL_PILOT=1`。Windows 包內的啟用標記由啟動程式讀取。本機 18766 設定與既有檢測紀錄保留。

## 已核對的結果

同批已知的 40 個過殺擋下 39 個。線材／接頭 11／11、板件／元件 17／18、孔位 11／11。剩下 MPT10 134.tiff 的板角 #61。MPT11 10.png 候選 #4 經使用者看圖確認，原 r3 漏抓、這版命中。MPT10 Golden 補測救回的六處與原有命中維持，主圖資的 1,468 個原 r3 保留框也都沿用。

上一輪合併版全圖資驗證涵蓋 254 張，另有三張 Golden 補測／自比。這一輪在已有結果上核對 201 個新增警報，並用代表圖驗證執行版。同批資料同時用於調整及核對。續作時用獨立圖資驗證這組條件。

## 本機檔案

- 過殺小實驗與對照圖 `workspace/dino-overkill-pilot-20261105/index.html`
- 先前合併版全圖資報告 `workspace/dino-combined-full-validation-20261105/report/index.html`
- 有答案的 MPT10 補測 `workspace/dino-combined-full-validation-20261105/report/answers.html`
- 本版建置程式 `packaging/build_overkill_portable.py`
- 本版執行一致性核對 `overkill_release_validation.py`

GitHub 上傳程式、交接說明與封包校驗碼。Windows 下載包和驗證圖資留在本機工作區；跨機移交沿用既有加密流程。

## 建置與核對方式

執行 `.venv/Scripts/python.exe packaging/build_overkill_portable.py`。建置使用本機 PyInstaller、既有 r3 可攜包的 GPU 工作者與參照圖，以及本機模型目錄。代表圖清單保存在本機 checkpoint，封裝後以 `XRayReview.exe --verify-overkill-pilot <清單>` 比對每個保留框、排除框和試驗規則。封包校驗碼見同目錄的交付清單。

[版本、校驗碼與核對範圍](checkpoints/dino-r3-overkill-pilot-20261105.json)。來源程式用 GPU 核對 7 張，可攜版 CPU 核對 7 張、GPU 核對 4 張，全部與離線預期一致。可攜版工程頁與 112 張範例自檢通過。
