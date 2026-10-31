# V2 IPC 複判系統設計

日期：2026-11-01；分支：codex/v2-portable-flex-cable。
狀態：原始設計規格。路徑分離、noop／ONNX adapter、版本切換、共享取圖與 CSV 已實作，操作方式見 IPC_SETUP.md；Windows 打包與實機 GPU／SMB 驗收尚未完成。

## 平台與交付方式

正式產品建議定位為 Windows x64 IPC GPU 版。作業系統選用 IPC 與 X 光設備供應商共同支援的 Windows 11／Windows IoT Enterprise 版本，實際版本需依 IPC 型號確認。現場不必安裝 Python，以整個發行資料夾交付，另附與 GPU 驅動相容的推論依賴與安裝檢查工具。可攜不代表免裝 NVIDIA 驅動，也不代表可跨 OS 直接執行。

Ubuntu x86_64 可作第二部署目標：設備端只需提供 SMB 分享，不必因設備本身使用 Windows 就選 Windows IPC；若工廠已有 Linux 維運與 IPC 驅動支援，Ubuntu 同樣合理。但須另做 CIFS 掛載、帳號權限、自動啟動與 GPU 驗收。首版先驗收一個平台，避免同時維護兩套部署。

macOS 保留為開發、展示、CPU 空模型驗證環境，不作此 NVIDIA IPC 正式部署目標。

推薦第一階段為登入後自動啟動的桌面啟動器＋本機服務＋瀏覽器；無人登入運作需求確認後，再交付 Windows Service。共享資料夾採 UNC 路徑，不依賴登入使用者的磁碟機代號。SMB 帳密由 Windows 認證與執行帳號管理，不放進 JSON 或 Git。

發行結構：

```text
XRayReview/
  XRayReview.exe
  _internal/                # 封裝的程式、網頁、手冊及依賴
  config/station.json      # 站台、共享資料夾與工作路徑
  models/active.json       # 指向啟用版本
  models/resnet-001/
    manifest.json
    model.onnx
```

可寫工作資料獨立配置於 IPC 本機磁碟，例如 C:/XRayReviewData，含 inbox、outputs、state、logs、quarantine 及正常參考。更新程式不覆蓋人工判定、資料庫或模型。模型目錄也可改設在固定外部位置，避免更換發行資料夾時遺失。

## 資料流與設備串接

X 光設備共享資料夾 → 輪詢發現 → 等待檔案完成 → 複製到 IPC 本機 → 驗證與去重 → 持久佇列 → 差分候選 → ResNet 分類 → 人工複判 → 本機結果保存。

1. 預設只讀設備分享，不更名、不刪除、不寫結果到設備資料夾。網路直連仍需設定 IP、SMB 帳號與分享權限；無須讓設備呼叫本機 API。
2. 優先與設備約定「暫存檔寫入後重新命名」或完成旗標。若設備不支援，採跨多次輪詢的大小與修改時間穩定檢查；穩定只是啟發式，還需在複製前後比較來源資訊、驗證完整影像可解碼，失敗退回等待／重試。
3. 先複製為本機 .partial，完成後原子改名再排程，分析不得直接讀取仍在寫入的共享檔。影像採不可變本機快照，保存來源路徑、取得時間、來源大小與 SHA-256。
4. 輪詢優先於單靠遠端檔案事件；斷網記錄離線狀態，退避重試，復線後補掃。SMB 呼叫使用獨立取檔工作程序，避免阻塞 UI 或推論工作者。
5. SQLite 保存發現、待穩定、已取得、待分析、分析中、待複判、完成、重試與隔離狀態；重啟後恢復工作，不只使用記憶體 jobs。失敗檔案與磁碟不足不得被當作正常。
6. 區分「拍攝事件」與「影像內容」：不同檔名的相同內容可以共用分析快取，但保留各自事件追溯。沒有產品序號時不能推測兩張照片一定是同一台產品。
7. 限制單一 GPU 推論工作者，先用持久佇列避免爆量。UI 顯示來源連線、待處理數、最後收圖時間、推論狀態與失敗原因；沒有新照片不等於設備離線。

## ResNet 插件與資料契約

建議訓練使用 PyTorch，正式推論使用匯出的 ONNX ResNet。單獨的 .pth 檔往往只有權重，沒有網路結構與前處理契約，不能保證丟進資料夾就能執行。約定 ONNX＋manifest 後，後續更新不用改應用程式碼。

v1 分類契約：一個 float32 NCHW 輸入 [N,3,224,224]，一個 float32 輸出 [N,4] logits。類別順序固定為 screw、cable、structure、uncertain。初版 N=1 逐候選推論；未來才擴大批次。

前處理固定為 detector.read 的百分位灰階正規化結果；使用現行 source_bbox 與 padding 規則所產生的原始方向 crop_box，resize 至 224×224（OpenCV INTER_LINEAR），灰階複製成三通道，像素保持 [0,1]，再以 manifest 的三通道 mean/std 正規化。訓練資料匯出器必須使用相同流程。這是工程契約，不能假定 ImageNet 權重可直接辨識 X-ray。

若改成待測／參考／差分三路輸入，需新增契約版本；不能只換模型而沿用舊前處理版本。

模型資料夾 manifest 至少包含 schema_version、model_id、backend、file、sha256、preprocessing、classes、input_size、mean、std、output 與 provider_policy。模型 ID 不作檔案路徑；file 僅允許版本資料夾內的單一 ONNX 檔，拒絕外部路徑及未列出的外部權重。

空模型使用 backend=noop，不需要安裝 ONNX Runtime。每個候選輸出狀態 disabled、label=uncertain、probabilities=null、action=manual_review，不產生假的分數、不刪除候選。整張仍待人工複判。

真模型在 shadow 模式輸出分類、softmax 分數與建議排序，但不自動完成候選或整張照片。分數不是已校準正確率。驗證足夠後，才允許經核准的策略省略高可信線材候選；低分、uncertain、對齊不足及模型錯誤必須保留複判。螺絲在線材上必須列為驗收案例。

## 更新、切換與回滾

1. 將完整新版本先放入 models/resnet-002 等新資料夾，不覆寫正在使用的版本。
2. 最後以原子取代方式更新 active.json；只把模型放進任意資料夾不會自動選成最新，避免誤啟用半套檔案。
3. 程式每張照片開始前檢查啟用設定；驗證 JSON schema、路徑、SHA-256、前處理版本、輸入輸出名稱／型別／形狀、類別、有限數值，並執行測試輸入。模型包另附已知輸入及預期輸出的測試案例以檢查訓練匯出一致性。
4. 新模型驗證成功後於下一張照片原子切換；同張照片的全部候選綁定同一 session 與 manifest 快照，禁止中途混用模型。
5. 更新失敗時保留前一個已驗證版本並明示 requested_model、effective_model 及錯誤；首次載入失敗則使用 noop。GPU 推論執行失敗時，該張標記模型錯誤並保留所有候選人工處理，不以失敗冒充線材或正常。
6. 回滾只需把 active.json 指回前版。既有照片結果不偷偷重算或覆寫人工判定；可另建分析紀錄比較新舊模型。
7. 記錄模型檔與 manifest 雜湊、實際 provider、前處理版本、分類策略版本、差分版本、正常參考雜湊。完整分析快取納入上述指紋，避免模型更新後沿用舊分類。可分開保存差分快取與分類快取以減少重算。

Windows GPU 版預設 require_cuda：載入 ONNX Runtime GPU 後需檢查實際 session provider 並以 GPU 測試輸入確認。不得靜默把 CPU 當作 GPU 運作；允許 CPU 降級時必須由站台設定開啟且 UI 顯示。noop 在開發環境不要求 GPU。

## 模組邊界與實作順序

- runtime_paths：分開封裝資源、站台設定與可寫工作資料；替換目前 ROOT 混用。
- acquisition：SMB 取圖、完成判斷、本機快照、重試與隔離。
- job_store：SQLite 事件、狀態與重新啟動恢復。
- detector：保留差分與座標映射，輸出候選和一致的 crop。
- model_manager：noop／ONNX adapter、契約驗證、GPU session、版本切換。
- review_policy：分類建議與是否需人工的策略，與模型分離。
- app：來源／模型狀態、照片清單、人工複判與結果追溯。
- launcher／build：直接啟動服務，替換凍結後不適用的 sys.executable app.py；打包 templates/static，產生建置指紋，提供 Windows 本機建置與乾淨 IPC 驗收流程。

第一里程碑：路徑分離、noop 真正接入候選流程、模型狀態、快取指紋與現有回歸。
第二里程碑：共享資料夾取圖與 SQLite 佇列、斷線／半檔／重啟驗證。
第三里程碑：ONNX adapter、版本切換、錯誤回退、GPU 現場驗證及 Windows 發行包。
第四里程碑：真模型 shadow 測試、獨立資料評估，再決定減少人工複判策略。

## 驗收與待確認資訊

在未安裝 Python 的目標 IPC 測試啟動、GPU、斷網復線、長時間寫入、重複檔、同檔名內容更新、中文路徑、損壞圖、磁碟滿、服務重啟與結果保存。模型測試涵蓋 noop、合法版本、錯誤 hash、不支援契約、GPU 不可用、推論失敗、更新中半檔、分析中切版、回滾與人工判定保留。

降低誤報須用依實體機／配置分組的獨立測試資料，比較螺絲召回、每張誤報、人工複判時間及端到端延遲；尚無證據可承諾誤報改善比例。

採購／現場整合前確認：IPC 作業系統與 CPU、GPU 型號／顯存／驅動、設備 SMB 版本與權限、照片完成訊號、檔名與產品序號規則、影像格式／大小、出圖間隔、資料保留量，以及是否要求無登入持續運作。這些不阻擋先做 noop 與程式架構。

## 官方參考

- CUDA provider 與 CUDA/cuDNN 相容要求：https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html
- PyTorch 部署平台：https://pytorch.org/get-started/locally/
- Windows Service 不應依賴映射磁碟機：https://learn.microsoft.com/en-us/windows/win32/services/services-and-redirected-drives
- PyInstaller 平台與打包限制：https://pyinstaller.org/en/stable/operating-mode.html
