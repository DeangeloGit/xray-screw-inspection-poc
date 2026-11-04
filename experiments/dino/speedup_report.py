"""Compare recorded full folder-to-result runs and unchanged-case checks."""
import sys,json,html,re
from pathlib import Path
from urllib.parse import urlparse,unquote
ROOT=Path(__file__).resolve().parents[2]
def main():
 paths=[Path(p).resolve() for p in sys.argv[1:]];assert len(paths)==3
 runs=[json.loads((p/'timing.json').read_text(encoding='utf-8')) for p in paths]
 out=ROOT/'workspace/dino-speedup-20261103';out.mkdir(exist_ok=True)
 verify=ROOT/'workspace/dino-speed-verification-20261103';v=json.loads((verify/'gpu-summary.json').read_text(encoding='utf-8'))
 assert all(r['stable_seconds']==15 and r['poll_seconds']==3 and r['candidates']==137 and r['counts']['inferences']==276 for r in runs)
 assert all(r['same_decisions_as_previous'] and r['protected_unchanged'] for r in runs)
 assert all(not r.get('reference_target_decision_changes') for r in runs)
 assert not v['decision_changes'] and not v['input_differences'] and v['normal_false_alarms']==0
 assert all(v['protected_screws'].values())
 assert v['gpu_kernel_events'].get(runs[2]['provider'],0)>0
 old,cpu,gpu=runs;best=cpu if cpu['total_seconds']<=gpu['total_seconds'] else gpu;gain=old['total_seconds']-best['total_seconds'];percent=gain/old['total_seconds']*100
 names=['修改前：CPU','整張圖只準備一次：CPU','只準備一次＋GPU']
 css='''body{margin:0;background:#f4f7f8;color:#173e4b;font:19px/1.7 "Microsoft JhengHei",sans-serif}main{max-width:1200px;margin:auto;padding:28px}h1{font-size:32px}h2{font-size:26px}a{color:#007d89}.answer{background:white;border-left:5px solid #007e88;padding:22px;margin:24px 0}table{border-collapse:collapse;width:100%;background:white}td,th{padding:11px;border:1px solid #d7e2e6;text-align:left}th{background:#e6eff2}.number{white-space:nowrap}.note{font-size:16px;overflow-wrap:anywhere}summary{cursor:pointer;padding:12px}img{max-width:100%;height:auto}pre{white-space:pre-wrap;font-size:15px}'''
 title='第一項有效；GPU目前較慢，暫不採用' if best is cpu else '影像準備與GPU加速有效'
 s=f'<h1>{title}</h1><div class="answer"><b>同一張照片，修改前{old["total_seconds"]:.2f}秒；CPU優化版{cpu["total_seconds"]:.2f}秒；GPU版{gpu["total_seconds"]:.2f}秒。</b><p>目前較快方案比修改前少{gain:.2f}秒（約{percent:.1f}%）。這是單次實測差距，包含電腦負載波動。</p><p>15秒檔案穩定等待、每3秒掃描均維持原樣。模型、完整47＋65範例、雙圖判斷及補查條件不變。</p><p>目前完成的是獨立離線版本；尚未替換18766正式版，也沒有重打包可攜版。</p></div>'
 s+='<h2>三次完整流程實測</h2><table><tr><th>版本</th><th>取圖到開始檢測</th><th>檢測與登記</th><th>完整時間</th></tr>'
 for name,r in zip(names,runs):s+=f'<tr><td>{name}</td><td>{r["folder_to_analysis_seconds"]:.2f}秒</td><td>{r["analysis_seconds"]:.2f}秒</td><td><b>{r["total_seconds"]:.2f}秒</b></td></tr>'
 s+='</table><p>完整時間包括取圖收尾及讀回結果，所以前兩欄相加可能略少。每個版本各跑同一張一次，電腦負載會波動，不把全部時間差都歸因於單一修改。</p><h2>每一段的前後時間</h2><table><tr><th>段落</th>'+''.join(f'<th>{n}</th>' for n in names)+'</tr>'
 for i,row in enumerate(old['sections']):
  assert all(r['sections'][i]['name']==row['name'] for r in runs)
  s+=f'<tr><td>{row["name"]}</td>'+''.join(f'<td>{r["sections"][i]["seconds"]:.3f}秒</td>' for r in runs)+'</tr>'
 s+='<tr><th>合計</th>'+''.join(f'<th>{r["total_seconds"]:.3f}秒</th>' for r in runs)+'</tr></table>'
 prep=[r['ai_stage_seconds']['full_frame_quantization_per_candidate'] for r in runs]
 infer=[sum(t for k,t in r['ai_stage_seconds'].items() if k.endswith('_inference')) for r in runs]
 s+=f'<h2>一：把重複整圖轉換消掉</h2><p>原本137個候選，每個都重轉參照與待測整圖，共274次。現在每張照片只各轉一次，共2次，其餘候選共用。換新照片時會清空，避免沿用上一張內容。</p><p>這段由{prep[0]:.3f}秒降到CPU版{prep[1]:.3f}秒、GPU版{prep[2]:.3f}秒。同批59處的實際輸入圖片像素完全一致；整張137處CPU分數差異為0。</p>'
 s+=f'<h2>二：讓RTX3000執行AI運算</h2><p>使用Windows DirectML介面，選到的顯示卡是{html.escape(gpu["gpu_adapter"]["name"])}。已查看執行紀錄，確認有{v["gpu_kernel_events"][gpu["provider"]]}筆運算事件由GPU執行，沒有只看套件名稱就當成加速成功。</p><p>純DINO運算時間：修改前{infer[0]:.2f}秒，只準備一次的CPU版{infer[1]:.2f}秒，GPU版{infer[2]:.2f}秒。GPU與CPU都各看參照和待測圖，合計276次推論，沒有靠少判幾張小圖縮短時間。</p>'
 if best is cpu:s+='<div class="answer"><b>GPU答案核對通過，但速度未達成，因此暫不採用。</b><p>測試進行時，NVIDIA驅動回報P8低時脈狀態、300MHz、目前功率上限10W（預設與要求值80W），且功率與軟體溫度限制都啟動。這是本次查到的實際效能限制，不能把本次速度當作RTX3000正常運作時的效能；也不能只憑這項資料斷定所有慢速原因。</p><p>沒有調高功率、超頻、關閉保護或修改系統電源設定。後續應先確認顯示卡為何持續限速，再重測GPU；目前保留CPU優化方案。</p><p><a href="gpu-state-during-test.txt">測試中顯示卡狀態完整紀錄</a> · <a href="gpu-state-summary.txt">時脈與使用率紀錄</a></p></div>'
 s+='<p>GPU執行時明確指定每次1張、224×224、3色彩通道，讓它預先準備完整運算配置。這就是原本DINO實際收到的尺寸，並未重新裁圖或縮小圖片。</p><details><summary>為什麼不是直接換GPU就好？</summary><p>先試只換GPU、保留可變輸入尺寸時，速度反而較慢，該次完整計時已中止，沒有拿未完成的數字當成果。確認輸入尺寸固定後，GPU可以合併整段運算；本頁GPU數字是重新跑完137個候選的實測。</p></details>'
 s+='<h2>有沒有改變答案？</h2><table><tr><th>核對項目</th><th>結果</th></tr><tr><td>整張照片137處：參照／待測各自判斷</td><td>全部與加速前一致</td></tr><tr><td>整張照片137處：最終保留／排除</td><td>全部一致</td></tr><tr><td>原本兩顆問題螺絲</td><td>維持參照沒有、待測有</td></tr><tr><td>上輪救回的長螺絲</td><td>維持判對</td></tr><tr><td>這輪救回的8.png／位置5</td><td>維持判對</td></tr><tr><td>另外兩處已有螺絲標記</td><td>維持判對</td></tr><tr><td>同批50個正常位置</td><td>0個新增誤報</td></tr><tr><td>之前仍錯的1.png、2.png、5.png</td><td>仍錯；這次加速不宣稱改善準確率</td></tr></table>'
 s+=f'<p>GPU與CPU的小數分數並非逐位相同。同批59處最大差異{v["max_margin_delta"]:.8f}；整張137處最大差異{gpu["max_margin_delta"]:.8f}，本次都沒有跨過判斷門檻。其他未測照片仍需另外核對。</p>'
 s+='<h2>這次沒有動第三項</h2><p>檔案穩定仍等15秒，掃描間隔仍3秒；來源照片、人工紀錄、正式模型與112張範例都保留。沒有修改判斷門檻、沒有降低模型精度、沒有用少做參照圖判斷換速度。</p><h2>時間的起點與終點</h2><p>起點：完整照片出現在獨立本機資料夾。終點：結果已存好並成功讀回。實際執行原有取圖、匯入、檢測、結果登記程式；使用獨立資料庫，無其他照片排隊。</p><p>模型已載入、範例比對資料已準備，不包含首次啟動／建立範例特徵時間。不含X-RAY拍攝、傳送檔案之前的時間，也沒有量網路共享資料夾或瀏覽器刷新。網頁目前每輪請求後等5秒刷新，畫面可能另外等約0–5秒及載入時間。</p>'
 s+='<details><summary>環境與可重現紀錄</summary><p>CPU主環境ONNX Runtime 1.31.1；獨立GPU環境使用onnxruntime-directml 1.24.4。其他影像與數值套件固定為原專案版本。同一ONNX模型檔，未轉成低精度模型。CUDA大型套件下載已停止，實際測試採DirectML，沒有安裝或替換顯示卡驅動。</p><p><a href="https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html">ONNX Runtime官方DirectML設定文件</a></p>'
 for name,p in zip(names,paths):s+=f'<p><a href="{(p/"timing.json").as_uri()}">{name}：完整時間與逐候選紀錄</a></p>'
 s+=f'<p><a href="{(verify/"pixel-verification.json").as_uri()}">影像像素與換圖快取檢查</a> · <a href="{(verify/"gpu-summary.json").as_uri()}">59處GPU核對與運算證據</a> · <a href="{(verify/"gpu-results.json").as_uri()}">59處逐例GPU結果</a> · <a href="environment.txt">GPU環境版本</a></p></details>'
 (out/'index.html').write_text(f'<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>影像準備與GPU加速結果</title><style>{css}</style><main>{s}</main></html>',encoding='utf-8')
 summary=dict(runs=[dict(name=n,path=str(p),total_seconds=r['total_seconds'],ai_inference_seconds=t) for n,p,r,t in zip(names,paths,runs,infer)],recommended='cpu_prepared_once' if best is cpu else 'gpu_prepared_once',saved_seconds=gain,saved_percent=percent,full_image_decisions_unchanged=True,case59_decisions_unchanged=True,stable_seconds=15,production_changed=False)
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
