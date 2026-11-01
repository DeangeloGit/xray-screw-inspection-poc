# Windows 工程師接手開發

本文件對應 `checkpoint-2026-11-01-windows-cpu-manual`。此 checkpoint 包含 IPC 架構、取圖／模型 UI、人工複判、批次 CSV，以及 Windows CPU 圖文手冊。正式取圖與 GPU 功能仍需目標設備驗證。

## 1. 取得程式碼

```powershell
git clone https://github.com/DeangeloGit/xray-screw-inspection-poc.git
cd xray-screw-inspection-poc
git switch -c engineer/windows-integration
```

預設 main 提供本次 checkpoint 的最新程式。需要重現這次交接時，可另以以下方式切分支：

```powershell
git switch -c engineer/checkpoint-test checkpoint-2026-11-01-windows-cpu-manual
```

沒有 Git 的電腦可從 GitHub 的 Code > Download ZIP，或 Release 的 Source code ZIP 下載。

## 2. 建立 Windows 開發環境

建議 Windows 10/11 x64、Python 3.14 x64。此專案原始碼在 Mac 的 Python 3.14.5 驗證；可攜測試包內附 Windows Python 3.14.10，尚待 Windows 實機驗收。

在專案根目錄開 PowerShell：

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-model-test.txt
.\.venv\Scripts\python.exe launch.py
```

不必啟用虛擬環境，也不必變更 PowerShell 執行原則。`requirements-model-test.txt` 包含 CPU 推論與測試模型產生所需套件；只執行應用程式可安裝 `requirements-cpu.txt`。

啟動網址：http://127.0.0.1:8765

- `/`：逐位置與整張照片人工複判、批次 CSV。
- `/settings`：資料夾瀏覽、啟用自動取圖、選取並套用 ONNX 檔。
- `/engineer`：差分門檻、候選、對齊與分類建議。

保持啟動的 PowerShell 視窗開啟；Ctrl+C 結束服務。若 8765 已有另一版服務，先關閉該版啟動視窗。

## 3. 取得測試資料

公開 Git 歷史不含 `data/` 原始影像、`outputs/` 人工結果、共享資料夾憑證或模型權重。儲存庫的介面截圖、檢測圖與手冊包含影像示意，不能替代測試輸入。

請由專案擁有者另行交付 `ok_0.png`、`ng_5.png`、`ng_9.png`，放入專案根目錄的 `data/`。既有完整 Windows CPU 測試包也含這三張，可經私下交接後取用；該包不作公開 Release 附件。

沒有原始影像時仍可啟動與查看設定 UI；影像分析與依賴實拍的回歸測試，需要先備妥參考圖。不要把手冊擷圖當作完整原始參考圖。

## 4. 取圖與模型

從 UI 指定專案工作資料夾以外的來源，例如 `C:\XRayIncoming` 或 `\\XRAY-PC\Images`。SMB 帳號由 Windows 管理，先確認執行程式的帳號可以讀取分享，不把密碼寫入程式或 Git。

- UI 設定儲存在 `state/ui_settings.json`，會保留到下次啟動。
- 自動取圖預設等待 15 秒穩定，再複製本機快照並分析。
- 來源不會刪除或更名；取圖佇列存於 SQLite。
- 模型由 UI 選取單一 ONNX，再按套用。CPU 開發時明確選 CPU。
- 分類契約：float32 NCHW `[1,3,224,224]`；單一 `[1,4]` logits；類別順序 screw、cable、structure、uncertain。
- 前處理須與訓練一致；UI 支援 ImageNet mean/std 或 0-1 灰階。
- 目前分類只提供建議，沒有刪除候選或自動放行。沒有真模型時使用 noop，仍完整人工複判。

正式 IPC 可透過外部站台設定分離工作路徑，見 [IPC_SETUP.md](IPC_SETUP.md)。GPU 環境須另驗證 NVIDIA 驅動、CUDA/cuDNN 與 ONNX Runtime GPU 的相容版本；不要同時在同一環境裝 CPU 與 GPU 兩種 ONNX Runtime 套件。

## 5. 執行驗證

完成三張影像的私下交接後執行：

```powershell
.\.venv\Scripts\python.exe verify_settings.py
.\.venv\Scripts\python.exe verify_ipc.py
.\.venv\Scripts\python.exe verify.py
```

`verify_settings.py`、`verify_ipc.py` 將 UI 設定、模型與匯入工作放在隔離的臨時目錄中。測試的 ONNX 是固定輸出流程驗證模型，不是螺絲辨識模型。

`verify_library.py` 使用既有整批資料，需另取得完整測試資料集；不要只用兩張待測照就期待該測試通過。既有標註是暫定目視標註，不代表量產準確率。

Windows 還需實機確認：中文與空白路徑、沒有系統 Python 的可攜啟動、SMB 權限與斷線、照片未寫完、重啟恢復、人工紀錄與 CSV、GPU 錯誤處理。

## 6. 程式模組

| 模組 | 職責 |
| --- | --- |
| runtime_paths.py、station_settings.py | 資源／可寫路徑、站台與 UI 設定 |
| acquisition.py | 來源輪詢、快照、持久佇列、獨立掃描程序 |
| detector.py | 對齊、差分、候選與原圖座標 |
| model_manager.py、settings_api.py | noop／ONNX、模型驗證與 UI 套用 |
| library.py | 去重、分析快取、目前分析紀錄與人工結果 |
| app.py、reports.py | UI API、人工複判完成條件、CSV |
| packaging/ | 原生 Windows 啟動器、可攜封裝、診斷與靜態檢查 |

## 7. Windows 上接續打包

現有可攜包的可重現組裝流程見 [WINDOWS_BUILD.md](../packaging/WINDOWS_BUILD.md)，準備工具鏈的腳本目前固定於 Mac ARM64。它可以在 Mac 編譯 Windows 啟動器，但不代表 Windows 執行已通過。

若工程師在 Windows 改用 PyInstaller，現有 `launch.py`、資源路徑與掃描子命令已有凍結模式設計。以下為待 Windows 驗證的建置起點，請在獨立輸出目錄操作，不覆蓋現場 workspace：

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -c "import hashlib; from pathlib import Path; names=('detector.py','model_manager.py','library.py'); Path('build_fingerprint.txt').write_text(hashlib.sha256(b''.join(Path(n).read_bytes() for n in names)).hexdigest())"
$xrayProjectRoot = (Get-Location).Path
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --onedir --console --name XRayReview --distpath build/windows-native-dist --workpath build/windows-native-work --specpath build --add-data "$xrayProjectRoot\templates;templates" --add-data "$xrayProjectRoot\static;static" --add-data "$xrayProjectRoot\build_fingerprint.txt;." --collect-all onnxruntime launch.py
```

產物位於 `build/windows-native-dist/XRayReview/`。將正常參考放至該包的 `workspace/data/ok_0.png`，並另外交付手冊。沒有系統 Python 的乾淨 Windows 上通過啟動、取圖、CPU 模型、複判與匯出後，才視為該原生建置方式驗證完成。確認版本後鎖定工程師實機使用的 PyInstaller 與依賴版本。

## 8. 交接時保留的資料

- 保留原始來源路徑與照片檔名；目前未串接 SN，CSV 的 SN 留白。
- 不把 `data/`、`outputs/`、`state/`、`workspace/`、真模型及帳密提交到公開 Git。
- 原有 V1 checkpoint：`checkpoint-2026-11-01-ui-manuals`；本次 IPC 分支仍保留，main 會同步這次交接 checkpoint。
- 圖文手冊：[Windows CPU 操作手冊](../output/pdf/Windows-CPU-操作手冊.pdf)。可下載 PDF 離線閱讀或列印最後一頁的交接勾選表。
