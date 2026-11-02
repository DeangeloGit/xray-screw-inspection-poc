X-Ray 螺絲複判 Windows x64 可攜測試版 — {VARIANT}

使用方式
1. 將整個 ZIP 解壓縮到可寫入的資料夾，例如 C:\XRayReview。
2. 雙擊 XRayReview.exe。不要只複製 EXE；runtime 與 _app 也必須一起保留。
3. 啟動後自動開啟本機網址（優先 http://127.0.0.1:8765；若該埠不可用，會自動換埠）。使用期間請保持啟動視窗開啟。
4. 頁面上的「取圖與模型設定」可選取照片來源及 ONNX 模型檔。
5. 使用完畢，在啟動視窗按 Ctrl+C 或關閉該視窗。

不用另外安裝 Python，也不需連網下載套件。建議先在 Windows 10/11 的 64 位元電腦測試。
本版在 Mac 上製作，已檢查 Windows x64 二進位格式、依賴與檔案完整性，尚未在 Windows 實際啟動驗證。

CPU 與 GPU 包
CPU：先用這一包確認啟動、差分、複判與 CSV。模型設定選 CPU；不需 NVIDIA GPU。
GPU：包含 ONNX Runtime GPU 1.31.1；差分與人工複判本身不需 GPU。
     啟用 NVIDIA 模型前，IPC 需有相容 NVIDIA 驅動、CUDA 13 與 cuDNN 9。
     GPU 包也可在設定中選 CPU。沒有符合條件的 GPU 時不會假裝使用 GPU。
     GPU 驅動、CUDA、cuDNN 未包含在本壓縮包；GPU 尚未實機驗收。
     官方相容要求：https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html

內附資料
workspace\data\ok_0.png：正常參考
workspace\data\ng_5.png、ng_9.png：既有兩張測試照片
未附帶既有人工複判結果，也沒有訓練完成的螺絲分類模型。
所有候選與整張照片仍需人工確認。
_app\selftest.onnx 僅供診斷程式驗證載入流程，不是螺絲模型，也不會自動啟用。

現場作業
1. 完成逐候選與整張照片複判。
2. 在照片清單勾選本批次，按「匯出本批螺絲表單」。
3. CSV 只列人工確認有螺絲的照片，SN 留白，保留照片來源路徑。
4. workspace 保存照片、來源紀錄、人工結果與表單，請整個保留／備份。

無法啟動時
先確認已解壓整包，不是在 ZIP 預覽中執行。
雙擊 DIAGNOSTICS.bat，將 logs\windows-selftest.json 或 logs\startup.log 的內容帶回檢查。
診斷使用獨立臨時資料，不修改現有照片、人工判定或啟用模型。
若 Windows 明確提示缺少 Microsoft C++ Runtime，隨包附有官方 prerequisites\VC_redist.x64.exe。
程式已附帶 app-local C++ DLL；通常不需要安裝該套件。
若 8765 已被舊版 X-Ray 程式占用，先關閉舊版的啟動視窗，再啟動本版。

2026-11-02 啟動修正
不需要與 Mac 位於同網域或同一個網路；127.0.0.1 永遠指本機。
新版會在 8765 無法使用時自動改用其他本機埠，請使用啟動視窗實際顯示的網址。
健康檢查不經電腦代理；這不會更改 Windows 防火牆、代理或企業安全政策。
單檔版 XRayReview-CPU-Standalone.exe 已包含本包內容，第一次會解開到本機 LocalAppData，無需網路下載。
若公司策略禁止執行隨附 Python 或禁止所有本機連線，仍需 IT 允許應用程式運作。
