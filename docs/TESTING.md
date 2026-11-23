# 統一合成測試入口

Windows 與 Mac 都在專案根目錄、啟用專案 Python 虛擬環境後執行：

```console
python -B run_tests.py
```

若 Mac 的 Python 指令名為 `python3`，使用 `python3 -B run_tests.py`。入口會沿用目前的 Python 執行每組測試，並將子程序工作目錄設為專案根目錄；也可從其他目錄以引號包住 `run_tests.py` 的完整路徑執行。路徑可包含空白與中文，無須 Bash 或 PowerShell 專用腳本。

## 環境與範圍

需要 Python 3，以及專案使用的 NumPy、OpenCV、Pillow（套件名稱 `numpy`、`opencv-python-headless`、`pillow`）。Pillow 由局部物件測試間接載入的模組使用。已有專案環境可直接執行；新環境依根目錄 `requirements.txt` 安裝：

```console
python -m pip install -r requirements.txt
```

入口本身只使用 Python 標準庫。這組測試不需要 DINO 模型、私人圖資或金鑰，不會啟動正式服務、下載模型或產生私人檢測報告。

| 執行範圍 | 目前案例數 |
| --- | ---: |
| `tests/test_*6r.py` | 17 |
| `tools/test_local_object5r.py` | 4 |
| `tools/test_lost_difference_shadow5r.py` | 4 |
| `tools/test_structure_cause_shadow5r.py` | 3 |
| `tools/test_ok_reference_shadow5r.py` | 4 |
| 合計 | 32 |

這是既有 32 項合成回歸測試的共同入口，**不是專案全部測試，也不是正式圖資推論驗收**。其他 5R 測試、服務整合測試及根目錄 `verify*.py` 不會自動執行；其中部分驗證會讀寫私人資料或啟動服務，須依各自文件及 `AGENTS.md` 的前置要求操作。正式 5R 判斷與 6R 離線研究的邊界不變。

## 如何判讀結果

每組在獨立子程序以 unittest 載入，顯示實際命令參數、測試數與退出碼。五組均成功時，最後顯示 `PASS: all 5 selected synthetic suites passed.`，入口退出碼為 `0`；任一組失敗、找不到測試或無法啟動則顯示 `FAILED`，入口退出碼為 `1`。入口明確檢查測試數，避免舊版 Python 把零項測試當成功。失敗後仍執行其餘組別，方便一次看完整結果；不會自動重試。

不要以根目錄的 `python -m unittest discover` 代替此入口：既有測試分散在不同目錄，預設 discovery 無法涵蓋上述組別。新增其他測試組時，先確認其資料依賴與副作用，再更新 `run_tests.py` 的 `SUITES` 和本表。
