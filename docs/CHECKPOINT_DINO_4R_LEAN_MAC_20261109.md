# 4r 精簡 Mac 續作包（2026-11-09）

分支 `4r`；checkpoint `checkpoint-2026-11-09-dino-4r-lean-mac`。這是使用者要求的必要資料續作包，**不是原站台完整備份，也不含全批原始測試圖資**。正式站台與47＋65雙圖設定未改。

清單核對：9,403個來源檔案，未壓縮536.03 MiB，較原15.45 GiB減少96.6%；其中完整報告與連結證據398.83 MiB。Windows已用新CPU入口實際重判四例並通過；這不代表Mac實機驗收。

## 保留什麼

- 唯一啟用的正式DINO r3版本：ONNX權重、特徵、原始47螺絲＋65正常參考PNG及各自SHA。
- `curated_v5_review` 的51＋90主庫與全部141張來源圖；B部位副庫及15張額外參考PNG、完整輪廓副庫、接點副庫與正常#22圖。新參考集的core/context小圖和原標籤一併保存，供續作選例。
- 最新100張、8335候選完整HTML報告及所有必要圖片／連結證據。這些是已產生的報告預覽，沒有附帶100份原始推論圖資。
- 原始影像僅Golden、128、135；兩張案例的完整候選支援及對位影像，不能縮成僅幾個答案框。
- 原答案、人工確認、B部位修正紀錄、#7無法判定、穩定性及失敗範例證據。

排除其他98張原始測試照片、所有歷史模型、舊報告、重複候選裁圖、中間特徵快取、瀏覽器資料、Python環境、安裝包及原站台照片索引DB。原始來源均保留在公司，不刪除。

具體檔案及SHA在資料包的 `archives/LEAN-SCOPE.json`，大小摘要在本次移交收據。工具的 `complete=true` 僅表示這個選擇性研究站台滿足模型／還原契約，不代表原站台全部資料都已備份。

GitHub是公開儲存庫，只存程式、說明與清單。私人DINO參考圖、向量、模型權重與照片位於加密包，受 `.gitignore` 保護。使用下載資料夾中使用者提供的原 `backup.key`；先前新建但未使用的 `XRay-4r-20261106.key` 不適用。任何金鑰均不入Git或Drive。

## 已有成果與限制

同批回歸79／101處、兩處人工確認及10個B部位保住；未對答案34→25，良品2、自比0。#22、#40正常。135 #88影像放大125%時原版與新版都漏判，仍未解決；#7未能人工判定，不能當訓練例。

此包可看完整報告及對128／135進行新實驗，**不能重新跑全部100張或宣稱Mac重驗79處**。若後續改模型，要回公司取用完整驗證集做保護檢查。原Windows驗收是歷史證據，勿改舊hash來冒充Mac驗收。

## Mac操作

先取得本checkpoint或更新的 `4r`，使用新的checkout／資料夾；保護Mac既有未提交工作，不覆寫舊資料。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-cpu.txt cryptography==50.0.2
```

從專用Drive資料夾下載 `XRay-4r-Lean-20261109.xray.enc` 及同名 `.sha256`；核對 `XRay-4r-Lean-20261109-cloud-verification.json` 是否明列本包SHA、`cloud_verified=true` 和 `isolated_restore_verified=true`。只有README不代表上傳完成。

```sh
.venv/bin/python tools/station_transfer.py import "$HOME/Downloads/XRay-4r-Lean-20261109.xray.enc" --destination "$HOME/XRay-4r-20261109" --key-file "$HOME/.config/xray-transfer/backup.key"
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
