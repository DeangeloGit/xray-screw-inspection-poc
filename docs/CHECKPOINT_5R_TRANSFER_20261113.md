# 5r 最小必要資料移交（2026-11-13）

本次為補充包，沿用原 `backup.key`，不是完整站台備份。程式在 GitHub `5r` 分支；私人資料在 `config/handoff-drive.json` 指定的 Drive 資料夾。金鑰須另外安全取得，不在 Git、Drive 或補充包中。

新電腦先取得 [GitHub 的最新 5r 分支](https://github.com/DeangeloGit/xray-screw-inspection-poc/tree/5r)，讀取 `START-HERE.md`，再依本頁還原。不要只使用先前下載的舊版程式；本次新增了 `prepare_5r_supplement_home.py` 與跨平台換行設定。

加密包為 `XRay-5r-Minimal-20261113.xray.enc`，675,470,809 bytes，分為 7 段。整包 SHA-256：`8d616398595955603d1d336c3cc25aba9b1990c7627b84bed3f9300eaf8701fb`。清單共 18,617 個檔案；下載 [分段清單](https://drive.google.com/file/d/1vNr4YhtW3trWprcfmUp5cnKYNr-YNbHV/view)及[整包校驗碼](https://drive.google.com/file/d/196a-PVY36tCSMnuHngnAUCnjXgVBj-Eu/view)，各分段 ID 見雲端收據。

## 先取得三份既有依賴

依 START-HERE 分別下載、核對、解密至新的隔離目錄：

1. 2026-11-09 Lean 包：模型、原 47＋65、整合庫及原副庫。
2. 2026-11-10 參考圖補充包：目前 52＋90 主庫。
3. 2026-11-10 KPH33 補充包：既有 KPH33 研究原圖與完整報告。

不要合併或覆寫既有站台。下方 `LEAN`、`REFERENCE`、`SUPPLEMENT`、`NEW_HOME` 表示自行選定的絕對路徑，不是固定目錄名稱。缺任何依賴、原金鑰或 SHA 不符時停止。

## 本次補充包內容

- 已驗證的局部正反例、特徵、資格清單及原始驗收收據。
- 三個機種的參照圖、門檻與設定；還原工具重設 CPU 並關閉監看。
- KPH33 全部 61 張原圖，包含四張問題圖、第五張未解決案例、訓練例子的來源及 NG；另保留 135 真螺絲控制圖與其參照圖。
- 161 張完整報告、17,759 候選結果、KPH33 基線結果、主要實驗及擾動／縮放驗證紀錄。
- 不重複收錄模型權重與現行主庫，不包含原 100 張整批原圖、執行環境、快取、試作失敗中間資料、服務程序狀態或金鑰。

歷史 JSON 中原機絕對路徑保留作證據；實際資料另以 `source/`、`evidence/`、`home/` 的相對結構收錄。不可直接把歷史路徑當成新機可用路徑。完整報告採相對圖片／連結。跨機種完整重跑仍需補齊未收錄的原 100 張原圖。

## 下載、還原與啟動

下載 `XRay-5r-Minimal-20261113.xray.enc.part*`、同名 `.parts.json` 及整包 `.sha256`。用 Python 3.12 以上；以下以 `python` 表示已安裝專案相依套件的 Python（Windows 常為 `.venv/Scripts/python.exe`，Mac 為 `.venv/bin/python`）。

```text
python tools/transfer_parts.py join DOWNLOAD/XRay-5r-Minimal-20261113.xray.enc.parts.json --output DOWNLOAD/XRay-5r-Minimal-20261113.xray.enc
python tools/kph33_supplement.py restore DOWNLOAD/XRay-5r-Minimal-20261113.xray.enc --key-file EXTERNAL/backup.key --destination SUPPLEMENT
python tools/prepare_5r_supplement_home.py --lean LEAN --reference-supplement REFERENCE --supplement SUPPLEMENT --destination NEW_HOME
```

重組會逐段與整包核對 SHA；另將下載的整包 `.sha256` 與重組結果比對。解密需通過 AES-GCM 認證及逐檔 SHA。建立站台前工具重新執行 Lean 檔案 probe、核對參考圖補充包、本次清單及受驗證程式雜湊；退出碼必須為 0。若失敗留下新建目錄，不要沿用該目錄啟動，改用新的目的地重試。

Windows PowerShell：

```powershell
$env:XRAY_5R_HOME = 'NEW_HOME'
.venv/Scripts/python.exe experiments/dino/live5r_local_service.py
```

Mac：

```sh
XRAY_5R_HOME="NEW_HOME" .venv/bin/python experiments/dino/live5r_local_service.py
```

使用終端顯示的實際網址。資料夾測試可指定 `SUPPLEMENT/source/KPH33/OK` 或 `NG`；完整歷史報告位於 `SUPPLEMENT/evidence/postreview-final/report/index.html`。新機先核對 `/api/5r/local-review` 的 `enabled` 與 `base_bank_matches_validation` 都為 true，再做自己的推論驗收。

Git 的 `.gitattributes` 固定六個已驗證程式檔的換行，保留驗證時的實際位元組。不要用編輯器任意轉換換行或直接修改私人 manifest 的 SHA 來繞過核對。

下載回比、隔離還原及站台建置不等於新機已重新做過辨識驗收；Mac 實機推論尚未測試。已知第五張誤報、第一張縮為 90% 的誤報，以及 NG 缺位置真值等限制仍見局部複核交接。

已完成 7 段實際下載、逐段與整包 SHA 回比、原金鑰解密認證，以及下載包的 18,617 檔隔離還原。成功收據與各分段連結見 [雲端驗證收據](checkpoints/5r-minimal-20261113-cloud-verification.json)。

另以同一加密包的本機認證還原資料建立全新站台，Lean probe 通過、294 個參考圖補充包檔案核對通過，CPU 啟動及三組圖庫版本核對成功。完整報告 161 張、17,759 候選、143,783 個圖片與連結引用核對通過。下載包與此本機包位元組相同，並已獨立解密還原；未把檔案／啟動驗證宣稱為新機推論重驗。
