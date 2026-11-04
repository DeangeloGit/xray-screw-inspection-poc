# Windows／Mac 加密資料移交

## Windows 同步核對：2026-11-05

已同步 Mac 的 `3a2adde` 規劃並保留本機 r3 修改。Windows 工具已建置於 `dist/XRayTransfer/XRayTransfer.exe`，原生介面缺件檢查通過；合成資料的加密、解密、路徑重定位、人工紀錄保留與拒絕覆寫測試通過。本機模型及原有 22 份 r3 核心程式快照核對一致，沒有執行圖資檢測。

已補上本機 `workspace/windows-check` 的自動辨識，以及 r3 `feature_file` 的存在／SHA-256 檢查。正式移交除了 ONNX、47＋65 範例，也必須包含 r3 的 `paired-features.npz`。

**尚未完成正式雲端移交。** Windows 預設位置未找到 Mac 的同一把外部金鑰，沒有另建替代金鑰，也沒有匯出或上傳正式私人資料。Mac 規劃已在 Git；本機後續 r3 修改以 `checkpoint-2026-11-05-dino-r3-rd-handoff` 保存並推送；Mac 必須取用這個 checkpoint 或更新的分支，不能只匯入資料包就假設程式也是 r3。現有 r3 可攜 EXE 在此啟動契約加入前已打包；匯入工作區目前可用更新後的原始碼 `launch.py` 啟動，舊包保持原樣。

核對紀錄：`docs/checkpoints/windows-handoff-sync-20261105.json`。

沿用 TCOOL 學習題庫專案的方式：**本機一致性備份 → 加密 → Google Drive 專用資料夾 → 下載比對 → 解密及隔離還原**。程式透過 Git 更新，私人模型、圖資與人工紀錄透過加密資料包移交。

## 已設定的位置

- Drive 專用資料夾：<https://drive.google.com/drive/folders/1QBfJNjDh9RpPe6bNr3HpC7ZBrCDkDzi2>。
- 非機密連接設定：`config/handoff-drive.json`。不更動題庫專案的檔案或分享權限。
- Mac 工具：`~/Applications/XRayTransfer.app`。
- Mac 移交暫存：`~/.local/share/xray-transfer/outbox`。
- Mac 獨立金鑰：`~/.config/xray-transfer/backup.key`，32 bytes，建立時權限 600。**不在 Git、資料包或 Drive 中。**

第一次在公司使用前，將這把金鑰透過另外的安全方式帶到公司電腦，例如隨身碟或既有的密碼管理工具，並保留離線復原副本。兩台的金鑰路徑可以不同，內容須相同。不需提供 Google 帳號密碼，也不從 Connector 抽取 token。

## 日常操作

1. 等檢測、人工複判和範例建立完成，儲存並關閉來源站台的檢測服務。匯出檢查本機健康端點，拒絕仍在執行的站台；仍須確保沒有其他程式在寫資料。
2. 開啟移交工具，選「本機專案／站台資料夾」。開發版選 Git 專案根目錄；Windows 可攜版選包含 `config`、`models`、`workspace` 的資料夾。站台設定一般留空；自訂配置可另選 `config/station.json`。
3. 選本機移交暫存資料夾、這台的外部金鑰檔，以及本機檢測程式。按「檢查本機缺件」。完整交付必須同時有 DINO 權重、47 張螺絲＋65 張正常範例與特徵庫、雙圖規則、已登錄機種參照圖及可讀的來源圖資。
4. 按「匯出完整移交包」。本機認證解密與 ZIP 完整性驗證通過後，會產生 `.xray.enc` 和 `.xray.enc.sha256`。工具不會在此時宣稱已上傳。
5. 在 Codex 說：**「把這次 X-RAY 移交包上傳到專案的 Google Drive 資料夾，下載回來校驗並隔離還原。」** Codex 讀取 `config/handoff-drive.json`，以已連接 Google Drive 上傳兩個檔案，再下載回比並執行 `tools/transfer_cloud.py`，成功後留下移交驗收紀錄。
6. 到另一台，在 Codex 說：**「從 X-RAY 的 Google Drive 專用資料夾下載最新完整移交包，驗證後匯入新的本機資料夾。」** 使用 `.enc` 與 `.sha256`，金鑰取自該台本機；不把金鑰上傳。
7. 匯入工具建立全新的本機資料夾，不覆寫、不合併舊人工紀錄。匯入後預設 CPU、自動監看關閉，不重跑檢測。核對照片、機種、模型、人工紀錄，才決定是否接回公司共享來源並開啟監看。
8. 介面匯入成功會把「目前站台」切換到新資料夾，下一次從這份資料接續匯出。兩台不要同時各自編輯後期待自動合併；指定一份資料作為接續來源，另一份仍保留。

不需要安裝 Google Drive 桌面同步。若已使用桌面版，也可以同步已完成的加密包與校驗碼；不要直接同步工作中的 SQLite 或 `.venv`。

## 公司 Windows 第一次建置工具

公司原有專案有 `.venv` 時：

```bat
.venv\Scripts\python.exe -m pip install -r packaging\requirements-transfer-build.txt
.venv\Scripts\python.exe packaging\build_transfer.py
```

建置後雙擊 `dist\XRayTransfer\XRayTransfer.exe`。搬到別台 Windows 要複製整個 `XRayTransfer` 資料夾，不只 EXE。也可直接執行 `.venv\Scripts\python.exe tools\station_transfer_ui.py`。工具不需要重新執行圖資檢測。

Mac 若需重建：

```sh
.venv/bin/python -m pip install -r packaging/requirements-transfer-build.txt
.venv/bin/python packaging/build_transfer.py
```

使用 Python 3.11 以上且含 tkinter。Mac Homebrew 需安裝與 Python 相符的 `python-tk`；建置腳本會先檢查，不再產出缺少元件的工具。

**舊 Windows r2 檢測 EXE 會固定使用程式旁的 workspace。** 要以本次更新的 `packaging/frozen_entry.py` 重建檢測程式，才能從工具啟動任意匯入工作區；也可直接用更新後的原始碼及 `.venv` 執行 `launch.py`。Mac 重建版已支援指定匯入工作區。Windows 原生執行仍須回公司實機驗收，本次只完成路徑與啟動契約測試。

## 移交包的內容

預設收錄實際工作區的 `data`、`outputs`、`state`、`reports`、`review`；全部本機模型版本與啟用指標；已登錄外部參照圖；目前設定的外部來源資料夾；專案 `workspace` 內的報告／實驗資料夾。已匯入工作區的 archives、extra、移交歷史也會接續保留。SQLite 以備份 API 產生一致性快照，WAL/SHM、服務狀態、日誌與暫存檔不收錄。

歷史 checkpoints、執行環境、wheel 快取、程式和執行檔不包含在私人資料包；額外原始圖資或報告可用 CLI `--extra` 加入。工具不會搜尋沒有登錄的歷史外部硬碟。報告自帶圖片與相對連結一併保留；歷史 HTML 的原機絕對網址不自動重寫。匯出內容清單與排除項都在加密包內的 manifest。

模型 manifest 原始內容和照片檔案時間保留。資料庫與結果中的已知路徑可重定位；來源識別及上傳照片目錄一起處理；人工標籤、時間戳和判斷不改動。匯入收據 `IMPORT-RECEIPT.json` 留下來源包校驗碼、commit 與路徑對照。來源程式有未提交修改時，manifest 會標示 `source_dirty`；移交資料不會代替移交這些程式修改，必須另以 Git 保存。

缺件檢查是檔案、SHA-256、SQLite 與 DINO 契約驗證，不等於 ONNX 實際推論或辨識準確率驗收。此 Mac 目前沒有正式 DINO 私人模型，所以正式匯出會拒絕；第一份正式移交必須回公司資料完整的站台產生。

## 加密與雲端驗證

`XRAYENC1` 格式採用每包隨機 salt、nonce、scrypt 與串流 AES-256-GCM。標頭一起認證，先完成認證才發布解密 ZIP。錯誤金鑰或資料被修改時，刪除解密暫存；檔案校驗、路徑安全及模型契約另驗一次。不覆寫既有目的資料夾。

與題庫一致，**Connector 的人工上傳和無人值守 rclone 是兩種授權**。目前使用已連接 Google Drive；沒有設定 rclone OAuth，也沒有建立背景排程。若日後需要無人值守，另在本機完成官方 rclone OAuth，再指定專用 remote；工具不會從連接器取得 token。

## 命令列

核心未加密功能只用 Python 標準函式庫；加密需安裝 `cryptography`（建置需求已包含）。

```sh
python tools/station_transfer.py check --root "/path/to/station"
python tools/station_transfer.py export --root "/path/to/station" --output "/local/outbox/XRay-20261104.xray.enc" --key-file "/external/backup.key"
python tools/station_transfer.py verify "/local/outbox/XRay-20261104.xray.enc" --key-file "/external/backup.key"
python tools/station_transfer.py import "/local/outbox/XRay-20261104.xray.enc" --destination "/new/local/station" --key-file "/external/backup.key"
```

第一次建立獨立金鑰可用 `python tools/station_transfer.py init-key "/external/backup.key"`，檔案已存在就拒絕，不會覆蓋。已有 Mac 金鑰時，請使用同一份副本而不是在公司產生另一把。

`check`／`export` 可加 `--config`；`export` 可重複加 `--extra`。不指定 `--key-file` 時保留本機 ZIP 救援模式，正式雲端移交使用加密包。CLI `--allow-incomplete` 可製作明確標示的缺件備份，正常匯入會拒絕，不能稱為正式雙圖版本。退出碼 0 成功，2 缺件或失敗。

下載回比與隔離還原：

```sh
python tools/transfer_cloud.py "/local/outbox/XRay.xray.enc" --downloaded "/local/download/XRay.xray.enc" --key-file "/external/backup.key" --receipt "/local/cloud-verification.json"
```

只有原檔與雲端下載 SHA-256 相同、加密認證通過、每個 ZIP 檔校驗及隔離匯入均成功，才設定 `cloud_verified=true`。下載時請一併保留同名 `.sha256`。

已獨立授權 rclone 時可用 `--rclone-remote remote:專用資料夾` 代替 `--downloaded`，工具會上傳並重新下載驗證，失敗不寫成功紀錄。

手動啟動已匯入工作區：

```sh
XRAY_CONFIG="/import/config/station.json" XRAY_WORKSPACE="/import/workspace" .venv/bin/python launch.py
```

Windows 命令提示字元：

```bat
set "XRAY_CONFIG=D:\XRay-Imported\config\station.json"
set "XRAY_WORKSPACE=D:\XRay-Imported\workspace"
.venv\Scripts\python.exe launch.py
```
