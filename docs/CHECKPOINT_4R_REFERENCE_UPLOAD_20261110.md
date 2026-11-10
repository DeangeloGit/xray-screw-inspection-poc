# 4r 參考圖上傳版本（2026-11-10）

此版本可在工程師頁面的「AI」新增螺絲或正常參考圖片，按「上傳並啟用」後，新的範例會加入目前圖庫並保留至重啟後。原有範例保留，已啟用版本是 52 張螺絲及 90 張正常案例。這是 4r 服務；舊版啟動入口沒有被替換。

GitHub 只有程式，不包含私人模型、圖片與特徵。先依 [Lean 包說明](CHECKPOINT_DINO_4R_LEAN_MAC_20261109.md) 取得並核對原模型和圖庫，接著取得 [4r 新參考圖加密補充包](https://drive.google.com/file/d/1ItPwGDlrRycFDAbegrJZdMrDdKKplNQP/view) 及其 [SHA-256 檔](https://drive.google.com/file/d/1DCurO8CZMoksNfTrl3nTVEEF54n1MGBd/view)。原金鑰 `backup.key` 須另外安全取得，不得上傳。補充包 12,413,689 bytes，SHA-256 `2675ef33438623c4f07cb663cc79a479be6849708a4692ee9e440b3e176d0db9`。已從 Drive 實際下載回比、使用原金鑰解密並隔離還原 294 個檔案，詳見 [驗收收據](checkpoints/4r-reference-20261110-cloud-verification.json)。它不含整批測試圖或模型權重，須搭配 Lean 包。

以下以 Mac、新目錄、已還原的 Lean 站台 `$HOME/XRay-4r-20261109` 為例。先遵循 Lean 文件核對並安裝相依套件。將補充包下載到 Downloads，確定 SHA-256 與上方一致，再還原：

```sh
shasum -a 256 "$HOME/Downloads/4r-reference-20261110.xray.enc"
.venv/bin/python tools/kph33_supplement.py restore "$HOME/Downloads/4r-reference-20261110.xray.enc" --key-file "$HOME/.config/xray-transfer/backup.key" --destination "$HOME/XRay-4r-reference-20261110"
.venv/bin/python tools/configure_4r_home.py --home "$HOME/XRay-4r-reference-20261110/example-home" --asset-root "$HOME/XRay-4r-reference-20261110" --model-root "$HOME/XRay-4r-20261109/models"
XRAY_4R_HOME="$HOME/XRay-4r-reference-20261110/example-home" XRAY_4R_PROVIDER=cpu .venv/bin/python experiments/dino/live4r_service.py
```

以服務顯示的網址開啟工程師頁面。還原及設定拒絕覆寫既有目錄或設定；缺少模型、圖庫、金鑰或核對失敗時停止，不能以空庫代替。Mac 使用 CPU，尚未在 Mac 實機驗證。此版本依使用者要求未執行完整回歸，先前部分檢查出現一個新增未對答案警報，尚未人工確認，不可宣稱誤報未增加。原有 79 處是舊版本歷史結果，不代表新版已重新驗收。
