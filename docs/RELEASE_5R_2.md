# X-RAY 5r.2

- 5r 局部複核的側面小螺絲補救先判待測圖。待測的側面特徵或整體分數不符合原條件時，略過參照推論。
- 在工程設定加入「影像逐步追蹤」。可選擇兩張圖，在獨立工作目錄執行並下載 27 步的單檔 HTML。報告包含實際中間圖、候選裁切、DINO 輸入、逐框判斷與階段耗時。見[操作說明](ENGINEERING_IMAGE_TRACE.md)。
- Mac 實測 KPH33 NG-000004 的 ONNX 呼叫從 258 次降至 250 次，203 個候選座標、判定與分類證據一致。工程入口已用同圖產出報告。Windows 實機待驗證。

## Windows 接續測試

```powershell
git fetch origin --tags
git switch 5r
git pull --ff-only origin 5r
```

延續已核對的 5r 局部複核站台。資料還原及入口見 [5r 移交說明](CHECKPOINT_5R_TRANSFER_20261113.md)與 [5r 局部複核說明](CHECKPOINT_5R_LOCAL_REVIEW_20261113.md)。啟動後開啟「工程設定 → 影像逐步追蹤」，選擇同機種的正常參照及待測圖。工程報告的耗時包含取證寫圖。
