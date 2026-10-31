# IPC 版設定與操作（實作版）

本分支已實作路徑分離、空模型與 ONNX adapter、版本更新、共享資料夾輪詢及人工複判 CSV。尚未在 Windows IPC、真實 SMB 設備或 NVIDIA GPU 驗收；尚未交付 EXE。

## 本機啟動

沿用 `start.command` 或 `.venv/bin/python launch.py`；Windows 原始碼測試可使用虛擬環境的 `python launch.py`。介面仍在 http://127.0.0.1:8765。健康檢查介面版本為 4，差分演算法仍為 2。

未設定時沿用原本專案下的 data、outputs，讀取舊紀錄；不會搬移或刪除既有照片與人工判定。新程式／模型會使用新快取指紋；重新分析可能建立待複判的新紀錄，舊分析仍保留於原 outputs。一般使用者開圖優先讀取最新已保存結果；工程模式的分析按鈕可要求目前版本重算。

## 設定 IPC 與取圖

複製 config/station.example.json 為 config/station.json，或以環境變數 XRAY_CONFIG 指定外部設定檔。站台設定需重新啟動程式才生效；只有模型啟用設定支援動態更新。

- workspace：IPC 本機可寫資料夾，例如 C:/XRayReviewData。資料下含 data、outputs、state、reports。XRAY_WORKSPACE 可覆蓋 workspace，供測試／獨立環境使用。
- reference：可額外指定正常參考完整路徑；未設定使用 workspace/data/ok_0.png。參考圖需由現有資料備份提供，沒有隨 Git 交付。
- model_root：版本模型所在資料夾，例如 C:/XRayReview/models。
- acquisition.enabled：設為 true 才會自動取圖。
- acquisition.source：UNC 分享路徑，例如 JSON 字串 `"\\\\XRAY-PC\\Images"`。讀取帳號需先由 Windows 認證或服務執行帳號設定，不在此存密碼。
- poll_seconds：輪詢間隔，預設 3 秒；stable_seconds：來源大小／時間穩定等待，預設 15 秒。
- scan_timeout_seconds：每次取圖程序上限，預設 30 秒；超時終止工作程序，下輪重試，UI 仍可操作。
- max_bytes：單檔大小上限，預設 100 MiB。

目前只實作 stable_metadata 完成判斷，未實作設備完成旗標。設備應盡可能使用「暫存檔寫完後改成正式檔名」。大小穩定及可解碼不能保證生產者已永久停止寫入；須於現場確認最長寫入間隔並設定等待時間。

來源只讀，本機生成不可變快照。來源同名檔變更會形成新取得事件，保留前一份來源紀錄。同大小與相同修改時間的內容替換目前無法辨識，設備應更新修改時間或使用唯一檔名。每次輪詢的掃描範圍應控制在可於逾時內完成的設備輸出目錄。

state/acquisition.sqlite3 保存等待、取圖與分析工作。斷網復線會補掃；分析中重啟會回到待分析。分析錯誤及無法解碼的來源會定期重試，UI 顯示狀態，原始來源不會刪除。請將整個 workspace 一起備份，避免快照與來源對應資料分離。

## 空模型與更新模型

沒有 models/active.json 時使用內建 noop-v1。每個候選的 classification.status=disabled、probabilities=null，仍完整人工複判。可以把 models/active.example.json 複製成 active.json，啟用附帶的 noop-v1 資料夾。

真模型需使用 ONNX；參照 models/onnx-manifest.example.json 建立版本資料夾中的 manifest.json，放入單一 model.onnx，填入 SHA-256。mean/std 必須和訓練一致，範例值不是對 X-ray 已驗證的設定。GPU 站台另安裝相容的 ONNX Runtime GPU／CUDA／cuDNN，再鎖定實機驗證的依賴版本；空模型無需這些依賴。

固定輸入：float32 [1,3,224,224]，或第一維名為 N 的動態 batch；單一輸出 float32 [1,4] logits。順序 screw、cable、structure、uncertain。輸入使用 detector.read 正規化的原始方向 crop_box，INTER_LINEAR 縮放，灰階複製三通道，再依 manifest mean/std 正規化。訓練與匯出必須遵守相同契約。

更新步驟：

1. 建立新的版本資料夾，完整放妥 manifest 與 ONNX，勿覆寫已使用的版本。
2. 先寫 active.next.json，內容如 `{"schema_version":1,"version_directory":"resnet-002"}`，再原子取代 active.json。
3. 程式自動驗證並在下一張開始時使用新版本；同張所有候選維持同一模型。
4. 回滾時將 active.json 指回前版即可。新版本失敗會保留前版，介面顯示錯誤；首次失敗則維持空模型。

目前真模型只提供 shadow 分類，**不刪候選、不自動判定正常**。模型及分類結果可在分析 JSON 與工程模式查看。GPU session 會檢查 CUDA provider；實際 GPU 工作負載、速度與準確率仍需在 IPC 驗證。

## 現場批次表單

1. 在照片清單勾選本批次照片，可使用「全選／清除選取」。選取只在目前頁面保留；照片取得／複判結果則會保存。
2. 完成各候選與整張照片人工複判。
3. 按「匯出本批螺絲表單」。未分析、未完成或整張「需再確認」的照片會阻擋本批匯出並提示檔名。
4. 下載 UTF-8 BOM CSV，可直接由 Excel 開啟；只列人工整張判定「有螺絲」的照片。零筆時仍輸出表頭。

欄位：序號、SN（留白）、照片檔名、來源完整路徑、本機影像路徑、人工判定、台北複判時間、分析紀錄、取得時間、模型版本。SN 尚無對應關係，系統不會由檔名推測。

完全相同內容仍共用分析，但表單會列出每個來源事件／別名，避免漏掉不同來源照片。無 SN 時請用設備原始檔名與完整路徑回查機器；這不等於已建立機器身分對應。

匯出會在 workspace/reports 保存 CSV 與同 ID 的 JSON（批次照片 ID、分析紀錄、匯出時間與筆數），便於追溯。

## 驗證

- `.venv/bin/python verify_ipc.py`：隔離工作目錄、模型更新／回退、實際差分接入空模型、人工複判、CSV／SN、來源讀取穩定性、重啟、同名換圖、失敗重試及獨立掃描程序。
- `.venv/bin/python verify.py`：原始三張與旋轉座標等回歸。
- `.venv/bin/python verify_library.py`：照片管理、批次與人工複判完成條件。

verify_ipc 使用現有 data/ok_0.png 與 data/ng_5.png 作為測試輸入，其結果與取圖測試在臨時資料夾中，不寫入現場人工判定。
