# 4r 精簡 Mac 續作包（2026-11-09）

**先取得並核對此包，才能接續依賴 DINO 的檢測與分析。**GitHub 不含私人模型、參考圖及特徵，KPH33 補充包也不包含這些資料。新站台先從本文件的 Drive 資料夾下載六段、清單及 SHA-256，以原金鑰解密還原到新目錄，再執行下方 `lean_4r_probe.py` 的檔案核對模式（不加 `--infer`）。已經由此包驗證還原的本機站台可重用，但仍須先執行該核對；退出碼必須是 0，`probe-result.json` 的 `status` 必須是 `passed`。

缺少 Drive 權限、原金鑰、模型、參考圖或特徵，或分段、整包、解密、逐檔／probe 核對失敗時，停止依賴該資料的工作並回報明確缺件／錯誤。不能用替代模型、空庫或先前收據當成這台機器已通過；為取得或排查缺件的唯讀工作可以繼續。不要上傳金鑰或將其貼到對話。

分支 `4r`；checkpoint `checkpoint-2026-11-09-dino-4r-lean-mac-verified`。這是使用者要求的必要資料續作包，**不是原站台完整備份，也不含全批原始測試圖資**。正式站台與47＋65雙圖設定未改。

清單核對：9,403個來源檔案，未壓縮536.03 MiB，較原15.45 GiB減少96.6%；其中完整報告與連結證據398.83 MiB。Windows已用新CPU入口實際重判四例並通過；這不代表Mac實機驗收。

## 雲端移交已完成

已從Drive實際下載六段、重組成515.1 MiB原加密包，整包SHA-256、解密認證、9,406個檔案校驗及隔離還原均通過。[驗收收據](checkpoints/lean-4r-20261109-cloud-verification.json)。資料包來源commit為 `28370db245e21d9bbea0d4ffdf7effa7ed8c6ba7`，包內原始checkpoint／清單及歷史證據保持不變；最新交付標籤另包含切片重組工具與驗證紀錄。

整包SHA-256：`47fa703ef38efdb169e7177a3d576b28f01c065ee1c49531ff1e624f25c99227`。

## 保留什麼

- 唯一啟用的正式DINO r3版本：ONNX權重、特徵、原始47螺絲＋65正常參考PNG及各自SHA。
- `curated_v5_review` 的51＋90主庫與全部141張來源圖；B部位副庫及15張額外參考PNG、完整輪廓副庫、接點副庫與正常#22圖。新參考集的core/context小圖和原標籤一併保存，供續作選例。
- 最新100張、8335候選完整HTML報告及所有必要圖片／連結證據。這些是已產生的報告預覽，沒有附帶100份原始推論圖資。
- 原始影像僅Golden、128、135；兩張案例的完整候選支援及對位影像，不能縮成僅幾個答案框。
- 原答案、人工確認、B部位修正紀錄、#7無法判定、穩定性及失敗範例證據。

排除未選用的原始測試照片、所有歷史模型、舊報告、重複候選裁圖、中間特徵快取、瀏覽器資料、Python環境、安裝包及原站台照片索引DB。原始來源均保留在公司，不刪除。

具體檔案及SHA在資料包的 `archives/LEAN-SCOPE.json`，大小摘要在本次移交收據。工具的 `complete=true` 僅表示這個選擇性研究站台滿足模型／還原契約，不代表原站台全部資料都已備份。

GitHub是公開儲存庫，只存程式、說明與清單。私人DINO參考圖、向量、模型權重與照片位於加密包，受 `.gitignore` 保護。使用下載資料夾中使用者提供的原 `backup.key`；先前新建但未使用的 `XRay-4r-20261106.key` 不適用。任何金鑰均不入Git或Drive。

## 已有成果與限制

同批回歸79／101處、兩處人工確認及10個B部位保住；未對答案34→25，良品2、自比0。#22、#40正常。135 #88影像放大125%時原版與新版都漏判，仍未解決；#7未能人工判定，不能當訓練例。

此包可看完整報告及對128／135進行新實驗，**不能重新跑全部100張或宣稱Mac重驗79處**。若後續改模型，要回公司取用完整驗證集做保護檢查。原Windows驗收是歷史證據，勿改舊hash來冒充Mac驗收。

## Mac操作

先取得本checkpoint或更新的 `4r`，使用新的checkout／資料夾；保護Mac既有未提交工作，不覆寫舊資料。

需要 **Python 3.12以上**（固定的NumPy版本要求）；不要直接沿用舊的系統Python或3.11環境。以下以Python 3.12為例，若已安裝較新版本，可換成該執行檔。

```sh
python3.12 --version
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-cpu.txt cryptography==50.0.2
```

加密包為540,115,114 bytes（515.1 MiB）。Drive連接工具前端單檔上限512 MiB，內部傳輸上限100 MiB，因此保留原加密內容，分成六段、每段最多96 MiB傳送，沒有增減圖資或重新加密。從[專用Drive資料夾](https://drive.google.com/drive/folders/1QBfJNjDh9RpPe6bNr3HpC7ZBrCDkDzi2)下載以下八個檔案，放在同一個資料夾（以下假設為Downloads）：

- `XRay-4r-Lean-20261109.xray.enc.part001`
- `XRay-4r-Lean-20261109.xray.enc.part002`
- `XRay-4r-Lean-20261109.xray.enc.part003`
- `XRay-4r-Lean-20261109.xray.enc.part004`
- `XRay-4r-Lean-20261109.xray.enc.part005`
- `XRay-4r-Lean-20261109.xray.enc.part006`
- `XRay-4r-Lean-20261109.xray.enc.parts.json`
- `XRay-4r-Lean-20261109.xray.enc.sha256`

若連接器把下載檔名額外加上 `.bin` 或 `.txt`，先還原成上面列出的原檔名；檔案內容不用轉換。

另外核對 `XRay-4r-Lean-20261109-cloud-verification.json` 是否明列本包SHA、`cloud_verified=true` 和 `isolated_restore_verified=true`。只有README不代表上傳完成。先用新工具逐段驗證與重組至新的資料夾，再匯入：

```sh
.venv/bin/python tools/transfer_parts.py join "$HOME/Downloads/XRay-4r-Lean-20261109.xray.enc.parts.json" --output "$HOME/XRay-4r-download-20261109/XRay-4r-Lean-20261109.xray.enc"
.venv/bin/python tools/station_transfer.py import "$HOME/XRay-4r-download-20261109/XRay-4r-Lean-20261109.xray.enc" --destination "$HOME/XRay-4r-20261109" --key-file "$HOME/.config/xray-transfer/backup.key"
.venv/bin/python tools/lean_4r_probe.py --station "$HOME/XRay-4r-20261109" --output "$HOME/XRay-4r-file-check-20261109"
```

匯入預設CPU、關閉監看，外部取圖來源空白，不會自動掃全批照片。報告位於：

```text
archives/workspace/dino-4r-integrated-bank-20261106/final/report/index.html
```

要實際重判四個選定案例，再執行下列命令。輸出必須用不存在的新資料夾；此工具不修改站台或原證據，也不依賴Windows絕對路徑與舊推論快取。

```sh
.venv/bin/python tools/lean_4r_probe.py --station "$HOME/XRay-4r-20261109" --output "$HOME/XRay-4r-cpu-check-20261109" --infer
```

這四例是128 #10保留、#22排除、#40排除、135 #88保留；只驗證原尺寸及分類，不重做候選生成。Windows測過同一CPU入口不代表Mac實機已通過，請看Mac新產生的 `probe-result.json`。

舊的 `integrated_bank_replay.py/proof.py` 仍依賴完整原工作區或GPU，不直接拿精簡包執行。Mac接續先用新probe或另外建立實驗輸出；保留原加密包、SHA與manifest。

## 建置／驗證

`tools/prepare_lean_4r_handoff.py` 使用明確清單建立隔離副本，核對每檔SHA；保留最新報告全部相對連結目的地。`tools/station_transfer.py`、`tools/transfer_crypto.py`、`tools/transfer_cloud.py` 繼續負責加密、下載回比與隔離還原。

本次雲端狀態以實際移交收據為準，不以本說明單獨宣稱成功。11月6日舊整站匯出因缺少cryptography失敗，沒有私人資料包上傳；本次已補齊加密依賴，改用精簡清單。
