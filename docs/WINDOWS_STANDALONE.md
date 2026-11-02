# 單一 EXE 與本機啟動修正（2026-11-02）

`XRayReview-CPU-Standalone.exe` 是 Windows x64 自解開式應用程式。單一檔案內含原生啟動器、Python、CPU ONNX Runtime、OpenCV、C++ DLL、網頁資源、手冊及三張既有測試影像。首次執行不下載套件，不連到 Mac；所有網頁 API 都在執行 EXE 的 Windows 本機。

第一次執行會自動解開至 `%LOCALAPPDATA%\XRayReview\versions\<版本ID>\`。設定、模型與工作資料另外保存在 `%LOCALAPPDATA%\XRayReview\` 下的 config、models、workspace、logs。更新 EXE 不覆寫已存在的參考圖、照片或設定；第一次才補上不存在的測試影像。請使用一般使用者可寫入的本機帳號環境。

## 使用方式

1. 完整複製 `XRayReview-CPU-Standalone.exe` 到 Windows 本機，雙擊執行。
2. 第一次會顯示準備隨附環境；過程不需要網路。
3. 看到「本機服務網址」後，瀏覽器才會自動開啟。優先使用 8765，不可用時自動換到其他本機連接埠，請以啟動視窗實際網址為準。
4. 保持視窗開啟，在網頁選取來源、人工複判及匯出表單。只有來源本身是 SMB 分享時，才需要網路與該分享權限。
5. 關閉舊版啟動視窗後再換新版本。重啟同一版本會重用同工作區的服務。

## 本次修正

- 從固定埠改為 8765、8766、18765、OS 自動分配埠的順序嘗試，保存原始 errno／WinError。
- 健康檢查明確不走 HTTP 代理，避免依賴公司網路的代理行為；瀏覽器仍遵守自己的政策。
- 只重用相同工作區、支援新啟動協議的本機服務。
- 啟動資訊存於 `workspace\state\local-server.json`，錯誤存於 `logs\startup.log`。
- 自解開程式使用固定版本 miniz，檢查每個檔案 CRC，完成後才寫入完成標記；中途失敗可重試，不使用 PowerShell 解壓或外部下載。
- 執行 `XRayReview-CPU-Standalone.exe --self-test` 可產出 `logs\windows-selftest.json`，包括真正的 TCP bind／HTTP 檢查，以及 Windows 排除埠清單（唯讀查詢）。

這些修正不能代替確認現場的完整錯誤訊息。若 Windows 或企業策略禁止執行應用程式／隨附 Python，或禁止所有本機 TCP 連線，需要 IT 對應用程式放行；程式不變更防火牆、代理或權限政策。

## 建置與驗證

1. `packaging/build_single_exe.py` 依 `packaging/miniz-source.json` 下載並校驗 miniz 3.0.2，再用現有 Zig 工具鏈編譯 Windows x64 自解開器。
2. 先執行 `packaging/build_single_exe.py --prepare-only` 準備 miniz，再執行 `packaging/build_windows.py --variant cpu`。
3. 執行 `packaging/build_single_exe.py`，將最新 CPU ZIP 附加到啟動器，產生 EXE、SHA-256 與 build JSON。
4. `verify_startup.py` 驗證模擬 10013、真實本機 HTTP、代理隔離、啟動與工作區重用；既有 IPC／設定回歸繼續適用。
5. `packaging/verify_sfx_payload.c` 可在建置主機編譯，用同一 miniz 解壓邏輯檢查嵌入資料的所有 CRC。這是資料驗證，不等於已執行 Windows Win32 解開及啟動流程。

Windows 原生單檔啟動與現場權限仍需實機確認。原始 X 光影像包含在私人交付檔案中，因此單檔 EXE 不自動發佈到公開 GitHub。
