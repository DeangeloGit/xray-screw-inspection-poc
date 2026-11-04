"""Plain-Chinese timing report from the completed single-photo run only."""
import sys,json,html
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 out=Path(sys.argv[1]);d=json.loads((out/'timing.json').read_text(encoding='utf-8'))
 total=d['total_seconds'];ai=d['ai_stage_seconds'];inference=sum(v for k,v in ai.items() if k.endswith('_inference'))
 d['hardware_observed']={'cpu':'Intel Xeon W-10885M','gpu':'NVIDIA Quadro RTX 3000','onnx_available_providers':['AzureExecutionProvider','CPUExecutionProvider']}
 d['ui_refresh_note']='static/user.js stationPoll schedules the next refresh5000ms after previous requests finish. Browser display latency was not measured; usually adds approximately0–5s plus request/render time when idle.'
 (out/'timing.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
 css='''body{margin:0;background:#f4f7f8;color:#173e4b;font:19px/1.7 "Microsoft JhengHei",sans-serif}main{max-width:1150px;margin:auto;padding:28px}h1{font-size:32px}h2{font-size:26px}a{color:#007d89}.answer{background:white;border-left:5px solid #007e88;padding:22px;margin:24px 0}table{border-collapse:collapse;width:100%;background:white}td,th{padding:11px;border:1px solid #d7e2e6;text-align:left}th{background:#e6eff2}.bar{height:12px;background:#00838b;min-width:1px}.number{white-space:nowrap}.note{font-size:16px;overflow-wrap:anywhere}summary{cursor:pointer;padding:12px}img{max-width:100%;height:auto}'''
 s=f'<h1>從資料夾取圖到出結果：{total:.2f}秒</h1><div class="answer"><b>這次把自動取圖等待也算進來。</b><p>照片完整進入資料夾 → 自動發現與確認寫入完成 → 複製檢查 → 對齊差分 → DINO雙圖與必要補查 → 結果存好並讀回。</p><p><b>本次實測 {total:.2f}秒，約{int(total//60)}分{total%60:.0f}秒。</b>其中開始檢測前{d["folder_to_analysis_seconds"]:.2f}秒，檢測與登記{d["analysis_seconds"]:.2f}秒。</p></div>'
 s+='<h2>每一段花多久？</h2><p>以下各列不重複計算，加總就是完整時間。AI各列是整張照片所有候選的累計，實際程式會逐候選交錯執行。</p><table><tr><th>段落</th><th>秒數</th><th>占整體</th><th style="width:24%">時間占比</th></tr>'
 for row in d['sections']:
  n,v=row['name'],row['seconds'];s+=f'<tr><td>{n}</td><td class="number">{v:.3f}</td><td>{v/total*100:.1f}%</td><td><div class="bar" style="width:{v/total*100:.2f}%"></div></td></tr>'
 s+=f'<tr><th>合計</th><th>{total:.3f}</th><th>100%</th><th></th></tr></table>'
 s+=f'<h2>最值得先加速哪裡？</h2><table><tr><th>優先順序</th><th>目前證據</th><th>具體下一步</th></tr><tr><td>1．DINO運算</td><td>純AI運算共{inference:.2f}秒，占整體{inference/total*100:.1f}%。目前用CPU，電腦另有RTX3000顯示卡。</td><td>另開離線環境測顯示卡運算。用相同小圖核對雙圖判斷與分數，再量速度；本輪未安裝或啟用GPU，不能先宣稱能快幾倍。</td></tr><tr><td>2．檔案穩定等待</td><td>現行設定等15秒確認檔案不再改變，再配合每3秒掃描。這不是AI慢。</td><td>確認X-RAY是否能在寫完後才改成正式檔名，或提供完成訊號。有可靠依據後再縮短等待，不直接取消檔案完整性檢查。</td></tr>'
 prep=ai.get('full_frame_quantization_per_candidate',0)
 s+=f'<tr><td>3．重複影像準備</td><td>每個候選都把兩張整圖轉成相同格式，合計{prep:.3f}秒。</td><td>改成每張照片只轉一次，供所有候選共用。先核對像素與結果完全一致；節省上限受這段實測時間限制。</td></tr><tr><td>4．畫面刷新</td><td>目前網頁每輪請求結束後再等5秒刷新。</td><td>檢測完成時通知畫面，或在檢測中縮短刷新間隔。這只讓結果更快顯示，不會縮短AI運算。</td></tr></table><p>本輪只量測，以上加速方式尚未套用或測出加速倍率。</p>'
 s+=f'<h2>這張照片實際做了多少工作？</h2><p>{html.escape(d["source_file"])}，{d["source_shape"][1]}×{d["source_shape"][0]}像素；差分提出{d["candidates"]}個候選，並非{d["candidates"]}顆螺絲。</p><p>DINO實際運算{d["counts"]["inferences"]}次：原本每候選看參照與待測各一次；{d["counts"]["geometry_attempts"]}處檢查補查範圍，{d["counts"]["rechecks"]}處通過條件，再各看一張參照與待測。</p><p>與前次同方案的137處保留／排除結果一致：<b>{"是" if d["same_decisions_as_previous"] else "否，需另外核對"}</b>。這只是確認計時沒有改變答案，不是新增準確率驗收。</p>'
 s+='<h2>資料夾掃描與等待的時間線</h2><table><tr><th>事件</th><th>照片進入後第幾秒</th></tr>'
 titles={'completed_file_available':'照片已完整放入資料夾','analysis_start':'開始讀圖檢測','result_saved':'檢測結果與紀錄存好','saved_result_retrieved':'讀回結果成功'}
 for e in d['events']:
  title=titles.get(e['event'],e['event'].replace('scan_','第').replace('_complete','次資料夾掃描完成'))
  s+=f'<tr><td>{title}</td><td>{e["seconds"]:.3f}</td></tr>'
 s+='</table><details><summary>展開掃描程序內部耗時</summary><p>每次掃描會啟動獨立程序。以下子項已包含在上方「資料夾掃描、取圖與匯入」，不要再加一次。</p><table><tr><th>子項</th><th>累計秒數</th></tr>'
 sub={}
 for scan in d['scans']:
  for k,v in scan['sections_seconds'].items():sub[k]=sub.get(k,0)+v
 names={'folder_enumeration_and_stat':'列出資料夾照片、讀取檔案狀態','copy_and_sha256':'複製照片與計算內容校驗值','image_integrity_and_decode':'核對檔案穩定、解碼檢查照片','import_commit':'完成匯入與登記','inventory_database_and_checks':'清單資料庫及其他檢查'}
 for k,v in sub.items():s+=f'<tr><td>{names[k]}</td><td>{v:.4f}</td></tr>'
 overhead=sum(z['parent_wall_seconds'] for z in d['scans'])-sum(sub.values());s+=f'<tr><td>程序啟動、匯入程式與其他程序開銷</td><td>{overhead:.4f}</td></tr></table></details>'
 s+=f'<h2>計時邊界，避免誤解</h2><p>模型與112張範例的比對資料已載入；它們不會每張重新建立。本輪測試啟動準備另花{d["setup_seconds"]:.2f}秒，不列入照片到達後時間。</p><p>使用同一原始照片的副本，放入獨立的本機測試資料夾，執行實際自動匯入、檢測及結果登記程式。用獨立資料庫，沒有修改18766正式流程、設定、圖資或人工紀錄。沒有排隊、沒有重跑整批，也沒有沿用已算好的測試小圖特徵。</p><p>從「檔案已完整進入資料夾」開始計時；X-RAY拍攝、檔案傳到資料夾之前的時間不在內。本次是本機資料夾，不是網路分享資料夾速度測試。</p><p><b>終點是檢測結果存好且可讀取，未實測瀏覽器畫面出現的時間。</b>現行畫面每輪請求後等5秒刷新，通常可能另等約0–5秒，加上請求和圖片載入時間；不能把它說成已量到的顯示時間。</p><p>只測一張、一次，不是平均值或最慢值。掃描有少量計時工具開銷，已包含在數字裡。</p>'
 s+=f'<p><a href="timing.json">全部原始時間紀錄（含逐候選耗時）</a> · <a href="{Path(d["result_path"]).as_uri()}">本次完整檢測結果</a> · <a href="{(Path(d["result_path"]).parent/"all_overlay.png").as_uri()}">本次標示圖</a></p>'
 (out/'index.html').write_text(f'<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>資料夾到檢測結果：逐段計時</title><style>{css}</style><main>{s}</main></html>',encoding='utf-8')
 assert abs(sum(r['seconds'] for r in d['sections'])-total)<1e-5
 assert d['protected_unchanged'] and d['same_decisions_as_previous']
 print(json.dumps(dict(report=str(out/'index.html'),total=total,inference_seconds=inference,prepare_full_images_seconds=prep,folder_to_analysis=d['folder_to_analysis_seconds']),ensure_ascii=False))
if __name__=='__main__':main()
