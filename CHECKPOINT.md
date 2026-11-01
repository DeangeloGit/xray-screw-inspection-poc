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
