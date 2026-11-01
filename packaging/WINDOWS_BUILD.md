# Windows x64 可攜測試包

本版採 Windows 原生 C 啟動器、官方 CPython embeddable runtime 與 Windows x64 wheels，沒有使用 PyInstaller 跨平台建置。Mac 只負責交叉編譯啟動器與組裝檔案，不宣稱已執行 Windows 程式。

可交付的整包包含 XRayReview.exe、runtime、_app、config、models、workspace、手冊、診斷程式、官方 VC++ 備用安裝程式及套件授權。正常參考與兩張既有測試照片由本機 data 複製，不會上傳 GitHub，不包含既有人工判定。單獨複製 EXE 無法執行。

## 在本開發機重建

1. `.venv/bin/python packaging/prepare_windows_cache.py`：官方下載與 SHA-256 驗證、Windows wheels 下載、解出 app-local C++ DLL。此準備腳本固定使用 macOS ARM64 Zig 0.17.0；Microsoft latest 連結若未來換版，雜湊不符時會停止，需審查並更新釘選值。
2. `build/windows-cache/zig/zig-aarch64-macos-0.17.0/zig cc -target x86_64-windows-gnu -Os -s -municode packaging/windows_launcher.c -luser32 -o build/windows-cache/XRayReview.exe`
3. 先以 ReportLab 環境執行 `docs/windows-cpu-manual/build_manual.py` 產生 PDF，再執行 `.venv/bin/python packaging/build_windows.py --variant cpu`；CPU 包根目錄會包含圖文手冊。手冊字型目前使用 macOS STHeiti TTC，其他主機需替換為可嵌入的繁中字型。
4. `.venv/bin/python packaging/build_windows.py --variant gpu`
5. `.venv/bin/python packaging/verify_windows_bundle.py dist/XRayReview-Windows-x64-CPU`
6. `.venv/bin/python packaging/verify_windows_bundle.py dist/XRayReview-Windows-x64-GPU`

建置需要現有 Python 套件，以及 onnx（建立診斷測試模型）、pefile（PE 靜態檢查）、packaging。`requirements-model-test.txt` 提供前兩類模型測試依賴，pefile 本機驗證版本為 2024.8.26。

第三方輸入皆來自 Python.org、PyPI、Zig 官方及 Microsoft 官方；套件版本與 SHA-256 記錄在 BUILD-MANIFEST.json。Windows 條件依賴 colorama 明確加入，避免 Mac 上執行 pip --platform 時遺漏 sys_platform=win32 條件。C++ DLL 從已驗證的官方 VC_redist.x64.exe 解出，沒有執行安裝程式。

CPU 包內含 ONNX Runtime CPU 1.31.1，無 NVIDIA 需求。GPU 包內含 ONNX Runtime GPU 1.31.1（CUDA 13 版），未附 NVIDIA 驅動、CUDA 或 cuDNN；啟用 GPU 時需相容環境，程式會檢查實際 provider，失敗仍保留人工複判。

## 驗證的界線

靜態檢查包含套件相依版本、Windows x64 PE 架構、必要非系統 DLL、檔案 SHA-256 與 ZIP CRC。GPU 的 CUDA DLL 列為外部依賴；TensorRT provider 不使用，相關 DLL 也不要求現場安裝。

Mac 可執行組裝後 `_app/portable_entry.py --self-test` 來測試相同啟動路徑、資源與診斷程式，但使用的是 Mac Python 與 Mac 依賴，不等於 Windows 測試。

Windows 使用者雙擊 DIAGNOSTICS.bat 後會產生 logs/windows-selftest.json，記錄 Windows 平台、Python、ORT provider、介面資源、正常與兩張測試照片分析，以及真正 ONNX CPU 載入／推論結果。測試模型只產生固定分類以驗證介面，不是訓練完成的螺絲模型。

## 官方依據

- CPython embeddable runtime：https://docs.python.org/3.14/using/windows.html#the-embeddable-package
- Python 3.14.10 官方發行與校驗：https://www.python.org/downloads/release/python-31410/
- Zig 官方下載：https://ziglang.org/download/
- Microsoft VC++ runtime：https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist
- CUDA 相容要求：https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html
