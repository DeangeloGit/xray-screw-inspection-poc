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
