# 最新 Checkpoint：2026-11-05 r3 正式流程、RD 交接與 Drive 移交

Tag：`checkpoint-2026-11-05-dino-r3-rd-handoff`；分支：`codex/next-development-20261103`。

[版本與交付校驗紀錄](docs/checkpoints/dino-r3-rd-handoff-20261105.json) · [RD 核心流程 HTML](docs/XRAY_R3_RD_IMPLEMENTATION_20261104.html) · [Windows／Mac 加密移交方式](docs/STATION_HANDOFF.md)。

目前正式程式為 r3，pipeline=`dino-combined-20261104-r3`、DETECTOR_VERSION=13。47 張螺絲＋65 張正常、參照圖＋待測圖、整體與局部特徵各半及一次受限補看已整合；CPU／GPU 保留選擇。對齊／明暗／候選核對合併加速與參照資料重用已啟用。不得把下方歷史 r2／僅離線實驗狀態當成目前版本。

本機私人交付：`dist/XRay-RD-r3-Reproduction-20261105.zip`、`dist/XRayReview-DINO-Optimized-r3-20261104-Windows-x64.zip`、`dist/XRayTransfer-Windows-20261105.zip`；名稱、大小及 SHA-256 見版本紀錄。公開 Git 只保存程式、HTML 與校驗／交接資訊，不包含私人權重、範例、圖資、完整檢測報告或 ZIP。

既有驗證：來源程式與可攜 EXE 在 CPU／GPU 的同一張圖 137 候選、276 推論、368 張輸出一致；59 固定案例一致，50 個正常對照無誤報。這不是獨立全圖資準確率，5 個目視疑似位置仍有 3 個未判出。本次 checkpoint 不重跑檢測。

Mac 的加密移交工具已同步，Windows 原生工具已建置及缺件檢查通過，合成加密往返與 r3 特徵完整性測試通過。現有 r3 可攜 EXE 在匯入啟動契約加入前建置，故啟動新匯入工作區先使用此 checkpoint 的原始碼 `launch.py`；未重建舊包，不能宣稱舊 EXE 已有此新功能。

金鑰由使用者之後從 Mac 另行帶入 Windows，不能新建替代、寫入 Git／移交包／Drive。正式私人資料尚未上傳，`cloud_verified=false`，也沒有設定無人值守 rclone。後續先停寫來源站台，使用同一把金鑰匯出，再上傳指定 Drive，下載回比 SHA-256 並隔離還原，才可稱跨機移交成功。

本機私人 checkpoint：`workspace/checkpoints/2026-11-05-dino-r3-rd-handoff`；保留歷史 checkpoint。外部 Pictures/X-Ray 原始圖留原處，內部模型、工作區、設定及紀錄備份獨立保存，不更改原資料。

---

# 歷史 Checkpoint：2026-11-04 DINO辨識與效能研究

Tag：`checkpoint-2026-11-04-dino-performance-research`；分支：`codex/next-development-20261103`。

[接續開發必讀](docs/CHECKPOINT_DINO_PERFORMANCE_20261104.md) · [報告／交付對照紀錄](docs/checkpoints/dino-performance-research-20261104.json)。

18766為r2雙圖、47＋65範例、CPU。來源清單修正及CPU/GPU選項已保存；最新辨識與三項加速仍僅離線實驗。移除另一個可攜版干擾後，同圖CPU到DINO答案58.06→56.77秒，137個候選及判斷不變。GPU目前300MHz／10W受限，正常GPU13～15秒及換機6～8秒均為估算，非新實測。

本機私人備份：`workspace/checkpoints/2026-11-04-dino-performance-research`。本次未重包EXE；r2 ZIP是歷史交付，不含本輪後續修改。公開Git保留程式、交接、校驗及實驗腳本，私人模型、圖資、報告、設定及人工紀錄留本機備份。

以下歷史checkpoint保留。

---

# 歷史 Checkpoint：r2 DINO 雙圖可攜版

日期：2026-11-03（Asia/Taipei）

標籤：`checkpoint-2026-11-03-dino-paired-r2`

分支：`codex/next-development-20261103`

**47 張螺絲＋65 張正常範例，以及參照圖＋待測圖判斷，已同時啟用於 r2 可攜版。** 工程頁面含範例管理；新增範例保留原版並繼承雙圖方式。既有 2,793 個候選逐框重播與完整報告一致：良品 0 框、不良品 386 框保留；另通過 4 例實際推論及 Windows EXE／搬移驗證。

- 接續開發必讀：[r2 完整交接](docs/CHECKPOINT_DINO_PAIRED_R2_20261103.md)。
- 對應交付與校驗碼：[r2 release record](docs/checkpoints/dino-paired-r2-20261103.json)。
- 私人資料備份：`workspace/checkpoints/2026-11-03-dino-paired-r2`。
- 正確交付：`XRayReview-DINO-Paired-20261103-r2-Windows-x64.zip` 及 `XRayReview-DINO-Paired-20261103-r2-完整報告.zip`。

公開 Git 保存原始碼與交接文件；私人模型、範例、完整報告、可攜包及現場設定留在本機 checkpoint。原開發站台的啟用指標仍保留舊模型，r2 包則預設雙圖；接手時請依交接文件確認，不混用舊服務與新版本。已知疑似誤刪風險保留說明，不能自行關閉使用者要求的雙圖功能。

以下歷史 checkpoint 保留。

---

# Checkpoint：V5，新增物體／既有結構判斷改版前

日期：2026-11-02（Asia/Taipei）
標籤：`checkpoint-2026-11-02-v5-before-structure-discrimination`

保存目前已在 Windows 本機啟用的 V5：各機型獨立上傳調校、敏感度保存、完整工程明細、同方向比較、機體內部與側槽範圍、局部亮度補償及小物件補查。

已驗證原有兩處暫定螺絲、使用者圈出的六處及兩個綠框案例，另通過同圖／亮度／位移控制、旋轉、上傳、人工紀錄及機型設定保存測試。仍有大量待人工複判候選；尚無完整標註集，不能據此宣稱量產準確率。

本 checkpoint 保存程式、文件與驗證腳本。原始照片、工作資料、機型設定、模型權重不納入 Git，仍保留於本機工作區。後續改動限定於「新增物體與原有結構變化的判斷」，不調整機型設定、檢測範圍、門檻或擷取流程。

---

# Checkpoint：Windows CPU 新版 UI 與異常匯出

日期：2026-11-02（Asia/Taipei）
標籤：`checkpoint-2026-11-02-ui-partial-export`
分支：`codex/v2-portable-flex-cable`；同步 main。

本次完成：

- 現場複判／工程設定新版 UI、資料夾選擇與表單預覽。
- 各機型正常參考圖與現場機型切換，參考圖版本與複判隔離。
- 照片清單、批次及匯出依目前來源，不混入其他來源或內附測試照。
- 逐位置人工判定完成後直接彙整照片結果，無需最後確認；零候選保留一次人工判定。
- 無法分析、未完成、需再確認不阻擋匯出，表單另列待處理異常及原因，SN 留白。
- 匯出預覽版本檢查、持久分析失敗原因與成功重試恢復。
- 可公開下載的 Windows CPU 單一 EXE ZIP，不含原始測試影像、現場紀錄或真模型。

驗證：隔離 UI／CSV、部分匯出、機型、來源、IPC、設定、啟動回歸；瀏覽器實測複判、參考圖上傳、預覽與 CSV、窄螢幕；原有 20 張批次相容性通過。封裝另做 Windows PE／依賴與嵌入 ZIP 完整性檢查。

限制：Windows 原生啟動、設備 SMB 與 NVIDIA GPU 仍需實機驗收；尚無量產辨識率結論。公開包首次須自行加入正常參考圖；既有使用者資料不會因更新 EXE 被覆寫。舊 PDF 截圖僅供判讀參考，當前操作以 `docs/UI_WORKFLOW.md` 為準。

前次：`checkpoint-2026-11-02-windows-single-exe`。以下歷史 checkpoint 保留。

---

# Checkpoint：Windows CPU 單一 EXE 離線版

日期：2026-11-02（Asia/Taipei）
標籤：`checkpoint-2026-11-02-windows-single-exe`
基準分支：`codex/v2-portable-flex-cable`；同步 main 供工程師預設下載。
功能實作 commit：`2f2e473`；本次 checkpoint 另更新交接文件。

本次完成：

- 單一 Windows x64 自解開 EXE，內含 CPU 執行環境，不需安裝 Python或連到 Mac。
- 固定版本 miniz、CRC 驗證、完成標記、失敗重試與版本快取。
- 設定、模型、工作照片與紀錄保存在 `%LOCALAPPDATA%\XRayReview`，更新程式保留既有資料。
- 本機連接埠自動回退、健康檢查略過代理、工作區識別，並保存啟動診斷。
- `--self-test` 產出 CPU 推論、資源與本機 TCP／HTTP 檢查報告。
- 已交付私人下載 ZIP（EXE 與啟動說明），原始碼與建置工具同步公開 GitHub。

驗證：Mac 啟動回歸（包含模擬 Windows 10013、實際連接埠占用與代理隔離）、IPC／設定回歸、實際 ONNX CPU 流程模型、Windows PE／依賴靜態檢查、嵌入 ZIP 全檔 CRC 與 SHA-256。這些檢查不等於 Windows 實機驗證。

尚待：乾淨 Windows 原生解開／啟動、現場權限、SMB 與 IPC GPU 驗收。未取得現場完整錯誤，不能斷言原先連線失敗的根因。尚無訓練完成的螺絲模型；模型建議不自動放行。

交接入口：[Windows 工程師接手開發](docs/WINDOWS_DEVELOPER.md)、[單一 EXE 使用與建置](docs/WINDOWS_STANDALONE.md)。

公開 Git 與 Release 不含原始照片、人工資料、真模型權重、共享帳密或完整執行檔。私人 EXE／ZIP 含三張原始測試照，請由專案擁有者另行交接。

前次 checkpoint：`checkpoint-2026-11-01-windows-cpu-manual`；V1：`checkpoint-2026-11-01-ui-manuals`，均保留。

---

# Checkpoint：Windows CPU 圖文手冊與 IPC 開發交接

日期：2026-11-01（Asia/Taipei）
標籤：`checkpoint-2026-11-01-windows-cpu-manual`
基準分支：`codex/v2-portable-flex-cable`；同步 main 供工程師預設下載。

已完成：

- 封裝資源與可寫工作路徑分離。
- noop／ONNX 分類介面、模型契約驗證、版本套用與失敗回退。
- UI 指定來源資料夾、直接選取 ONNX 模型檔；設定保存與動態生效。
- 來源只讀取圖、本機快照、SQLite 狀態、重啟恢復與重試。
- 保留逐候選與整張人工複判；批次 CSV 只列整張確認有螺絲，SN 留白。
- Windows x64 CPU／GPU 原生啟動器與可攜測試包、診斷工具。
- 9 頁圖文 PDF，含操作圖、問題排查與可列印現場勾選表；CPU 測試包已附 PDF。
- Windows 工程師接手文件：`docs/WINDOWS_DEVELOPER.md`。

已驗證：Mac 原始回歸、20 張既有批次、隔離 IPC／UI 整合、實際 ONNX CPU 載入與流程驗證模型推論；PDF 逐頁視覺檢查、字型嵌入；可攜包的 PE 架構、依賴、SHA-256、ZIP CRC 及手冊入包。

尚待：Windows 實機啟動、設備 SMB、IPC GPU；尚無訓練完成的螺絲分類模型，也未驗收量產召回與誤報率。noop 不產生假分數，分類建議不自動放行。

公開內容：程式碼、說明、既有介面／檢測示意圖與 PDF。公開 Git 與 Release 不含原始照片、人工執行資料、真模型權重或共享帳密。現有完整 CPU／GPU 測試包含三張原始影像，由專案擁有者私下交接。

前一個 V1 成果 checkpoint：`checkpoint-2026-11-01-ui-manuals`，保留作為原始基準。
