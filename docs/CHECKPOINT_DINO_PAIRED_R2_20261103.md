# r2 雙圖版開發交接

- Checkpoint：`checkpoint-2026-11-03-dino-paired-r2`
- 分支：`codex/next-development-20261103`
- 前一 checkpoint：`checkpoint-2026-11-03-clip-yolo`，基準 commit `fb4706a`。
- 工作目錄：`C:\Users\Deangelo_Hu\Documents\ChatGPT\X-RAY檢測`。
- 本機備份：`workspace/checkpoints/2026-11-03-dino-paired-r2`。
- 可機器讀取的交付清單：[r2 檔案與校驗碼](checkpoints/dino-paired-r2-20261103.json)。

## 這次保存的版本

**47 張螺絲＋65 張正常範例，以及參照圖＋待測圖判斷，兩個條件都已接入程式並於 r2 可攜版預設啟用。** 不可再自行將雙圖判斷停用或只保留在報告裡。

差分找出候選 → 同位置分別取待測及參照小圖 → 每張圖各比較最像的 3 張螺絲、3 張正常範例 → 待測像螺絲且參照不像螺絲才保留。兩張都像螺絲，或待測不像螺絲，則排除。參照小圖缺失／推論失敗會保留人工確認，不默默退回單圖。

- 模型目錄：`dino-paired-47-20261103`。
- 模型名稱：`DINO 雙圖：47 張螺絲＋65 張正常（參照圖＋待測圖）`。
- 判斷規則：`dino-top3-target-and-reference-v1`。
- 模型識別：`3602fd9633f11606bed811ac2d7d1762401524f8fb81b1406a571d45cbd8434e`。
- 47 張螺絲＝原有 31 張＋使用者確認的現場 16 張；新增，並非替換。65 張正常範例維持。
- 工程頁面整合 DINO 範例管理。存成新版保留原版；從雙圖版本新增範例會繼承雙圖規則。
- 原版 DINO、47＋65 單圖版、CLIP 仍可切換；YOLO ONNX 上傳功能保留。
- 未套用 upper-green 補完整框方法；未改差分找框位置或畫面框範圍。

## 正確交付檔，請勿混用前一個單圖包

| 用途 | 本機檔案 |
| --- | --- |
| 可攜版 | `dist/XRayReview-DINO-Paired-20261103-r2-Windows-x64.zip` |
| 完整報告 | `dist/XRayReview-DINO-Paired-20261103-r2-完整報告.zip` |
| 版本總結 | `docs/DINO_PAIRED_RELEASE_20261103.html` |
| 原報告資料 | `workspace/windows-check/diagnostics/dino-47-paired-full-20261103` |
| 程式／報告一致性驗證 | `workspace/dino-paired-release-20261103/verification.json` |

兩份 ZIP 也完整複製到 checkpoint 的 `artifacts/`，附 SHA-256。前次不含 `Paired`、`r2` 的可攜包只有單圖，已由 r2 取代，不能用來對應雙圖報告。

解壓後執行 `XRayReview.exe`；保留整個資料夾，不需另裝 Python。包內保存設定、模型與工作資料。預載四機種參照，差分門檻 0.13；自動取圖預設關閉。使用 OS 指派的本機連接埠，避免開到其他既有服務。

注意：已交付的 EXE 建置於本次 Git commit 之前，其包內 `source_commit` 仍為 `fb4706a`，並明列包含未提交修改。交付清單已用逐檔原始碼雜湊核對 checkpoint 對應程式；不要僅以建置時的舊 HEAD 誤認為缺少 r2 修改。本次不為了改 commit 字樣重新建置已驗證的 ZIP。

## 數據與驗證界線

全圖資 190 張＝139 張良品＋47 張不良品＋4 張參照圖；2,793 個既有差分候選。

| 圖資 | 原候選 | r2 保留 | r2 排除 |
| --- | ---: | ---: | ---: |
| 良品 139 張 | 128 | 0 | 128 |
| 不良品 47 張 | 2,665 | 386 | 2,279 |

驗證為正式取圖／模型介面／雙圖決策逐框重播，沿用保存的 DINO 特徵；2,793 框的取圖雜湊、分數與決策均與原報告一致。另有 4 個案例實際執行 ONNX。沒有重跑整批差分。Windows EXE 實測雙圖推論、缺參照保留、工程頁面、112 張範例、新版保存與模型切換、中文與空白路徑搬移及沒有外部 Python PATH 的啟動。

框數不是真螺絲數，沒有完整人工標註或獨立測試集，不宣稱量產準確率。

## 已知問題與後續方向

- 已標記 2 處螺絲都保留。
- 58 個目視原有結構框排除；9 個疑似新增螺絲風險框也排除。
- 前次 14 處疑似誤刪只保留 3 處，尚需確認。
- 「兩張都像螺絲」尚不能確認是同一顆；風險照實列出，但依使用者要求保持啟用。
- 後續改善範例品質、分析被誤刪外觀與取圖範圍、區分原有物件和新增加的物件，使用未拿來當範例的照片驗證。
- 報告繼續遵守 `AGENTS.md` 的全圖資、「機種 → 類型 → 相近位置」方式，不能只交付差異頁。

## 本機資料與恢復

公開 GitHub 僅保存原始碼、文件、驗證／報告腳本與不含圖片的校驗清單。模型權重、範例圖片與向量、原始照片、完整報告、EXE 及現場設定保留本機，未上傳公開 GitHub。

Checkpoint 目錄包含：

- `models/`：所有現有模型與範例的完整複本，包括 r2 雙圖與舊版。
- `station/`：開發站台當時設定、參照圖與既有 SQLite 紀錄的一致性備份。
- `diagnostics/`：原完整差分資料及雙圖實驗資料，供接續分析與重播。
- `field-examples/`：使用者新增 16 張範例的來源及裁切記錄。
- `artifacts/`：兩份正式 r2 ZIP、SHA-256、建置與驗證紀錄。
- `private-inventory.json`：上述備份逐檔校驗碼；`commit.txt` 記錄本次 checkpoint commit。

**開發站台的 `models/active.json` 在建立 checkpoint 時仍指向舊版 `dino-examples-a3b8c97aa539`，因先前明確保留現有服務狀態。它不是 r2 的預設。** r2 可攜包的 `models/active.json` 明確指向 `dino-paired-47-20261103`。接續開發若使用原始碼服務，先啟動此 checkpoint 的程式，再到工程頁面選擇 r2 雙圖模型；不要把舊版服務當成已載入新程式。

新電腦先取此 Git tag，再私下移交 checkpoint。將模型、所需 diagnostics 複製回對應目錄；路徑不同時調整站台參照與來源，不照搬舊機絕對路徑。單靠公開 Git clone 不會取得私人模型和圖資。

## 重要程式與指令

- `detector.classify_dino_candidate`：同位置、±12 像素、與報告一致的灰階量化。
- `dino_adapter.py`：範例比較與雙圖規則；`model_manager.py`：模型識別、雙圖參照傳遞、缺圖保留。
- `dino_examples.py`：範例管理 API；`templates/dino_examples_panel.html` 與 `static/dino-examples.js`：工程頁面元件。
- `.venv/Scripts/python.exe experiments/dino/verify_paired_runtime.py`：沿用特徵的逐框核對與 4 例實際推論。
- `packaging/build_dino_portable.ps1`：Windows 建置、封裝、EXE 自測與 ZIP；需要本機 `.venv`、模型、正常參照及保存的驗證資料。
- `packaging/assemble_dino_portable.py --report`：封裝既有完整報告，非重新檢測。

建置腳本會拒絕覆寫已有的正式交付目錄。後續開發應先改新版本名稱／輸出路徑，不刪掉 r2 交付來重用名稱。歷史 `full_paired_run.py` 與 `verify_full_paired_report.py` 釘選了當時原始碼和模型狀態，r2 修改後其舊雜湊檢查可能拒絕；不要改寫凍結紀錄來繞過，應用 r2 重播驗證或另開新的實驗目錄。
