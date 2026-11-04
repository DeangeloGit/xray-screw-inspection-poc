"""Readable timing breakdown and concrete proposals; no detection rerun."""
import html
import json
import os
import statistics
from pathlib import Path
from urllib.parse import quote,unquote,urlparse
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'workspace/dino-alignment-difference-profile-20261104'


def main():
    d=json.loads((OUT/'profile.json').read_text(encoding='utf-8'))
    runs=[r for r in d['runs'] if r['profiled']]
    controls=[r for r in d['runs'] if not r['profiled']]
    def value(key,field='inclusive'):
        return statistics.mean(r['details'].get(key,{}).get(field,0.) for r in runs)
    def stage(key):return statistics.mean(r['stages'][key] for r in runs)
    for r in runs:
        roots=sum(r['details'][k]['inclusive'] for k in ('register','refine','legacy_proposals','proposals'))
        assert abs(sum(v['exclusive'] for v in r['details'].values())-roots)<1e-5
    prep=value('orientation_image_preparation');features=value('_register_orientation / detectAndCompute')
    match=value('_register_orientation / knnMatch');pairprep=value('filter_feature_pairs')+value('matched_point_arrays')
    fit=value('_register_orientation / estimateAffinePartial2D');warp=value('_register_orientation / warpAffine')
    align=value('register');diff=value('proposals');local=value('refine');legacy=value('legacy_proposals')
    align_rows=[('把待測圖轉成各方向、複製與縮圖',prep,'8 組'),('找出定位用的圖案特徵',features,'8 組，每組 7,000 個'),
        ('逐一比對兩圖的定位特徵',match,'8 組，每組 7,000 × 7,000'),('篩選配對並整理座標',pairprep,'8 組'),
        ('算出圖片應如何移動與旋轉',fit,'8 次'),('依選定位置產生對齊圖及有效範圍',warp,'2 次影像轉換'),
        ('其他準備與對齊品質檢查',align-sum((prep,features,match,pairprep,fit,warp)),'包含覆蓋及相似程度檢查')]
    difference_rows=[('校正兩張圖的明暗差異',value('compensate_brightness'),'3 輪，避免原本亮度不同就出現大量差異'),
        ('把差異整理成候選區塊',value('candidates_from_residual'),'一般搜尋＋較細的補查，共 2 次'),
        ('檢查是否原有結構稍微位移',value('structure_change_evidence'),'142 個暫時候選'),
        ('再用周圍背景核對是否正常變動',value('context_explain'),'137 次'),
        ('檢查是否符合線材移動特徵',value('wire_review'),'137 次；目前僅作提示，不直接刪候選')]
    difference_rows.append(('合併候選與其他整理',diff-sum(v for _,v,_ in difference_rows),'包含細小物件補查結果合併'))
    def table(rows,total):
        text='<table><tr><th>步驟</th><th>耗時</th><th>這張圖做了多少工作</th></tr>'
        for title,seconds,note in rows:text+=f'<tr><td>{html.escape(title)}</td><td>{seconds:.3f} 秒</td><td>{html.escape(note)}</td></tr>'
        return text+f'<tr><th>合計</th><th>{total:.3f} 秒</th><td>各列互不重複計時</td></tr></table>'
    control_mean=statistics.mean(r['stages']['total'] for r in controls)
    profile_mean=stage('total')
    timingrows=''.join(f'<tr><td>第 {r["run"]} 次</td><td>{"細項計時" if r["profiled"] else "只計大階段（對照）"}</td><td>{r["stages"]["total"]:.3f} 秒</td><td>相同</td></tr>' for r in d['runs'])
    previous=json.loads((ROOT/'workspace/dino-cpu-reuse-20261104/runs.json').read_text(encoding='utf-8'))
    timing=json.loads(Path(next(r['path'] for r in previous if r['mode']=='warm')).read_text(encoding='utf-8'))
    saved=Path(timing['result_path']).parent
    def relative(path):return quote(Path(os.path.relpath(path,OUT)).as_posix())
    text=f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>對齊與差分：時間花在哪裡？</title><style>body{{font:18px/1.7 'Microsoft JhengHei',sans-serif;max-width:1180px;margin:32px auto;padding:0 24px;color:#173e4c;background:#f5f8f9}}h1{{font-size:32px}}h2{{font-size:25px;margin-top:35px}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{border:1px solid #d7e2e6;padding:12px;text-align:left;vertical-align:top}}th{{background:#e8f1f4}}.answer{{padding:22px;background:white;border-left:6px solid #00838c}}a{{color:#007e8a}}details{{padding:18px;background:white;border:1px solid #d7e2e6;margin:22px 0}}summary{{cursor:pointer}}.images{{display:flex;gap:20px}}figure{{flex:1;margin:0}}img{{width:100%;max-height:520px;object-fit:contain}}small{{color:#526b76}}</style>
<h1>最花時間：找出兩張圖的位置關係，以及校正明暗</h1>
<div class="answer"><p><strong>整張對齊約 {align:.2f} 秒，差分找候選約 {diff:.2f} 秒。</strong></p>
<p>對齊中，定位特徵互相比較約 <strong>{match:.2f} 秒</strong>；準備8個方向的圖片約 <strong>{prep:.2f} 秒</strong>；找定位特徵約 {features:.2f} 秒。</p>
<p>差分中，明暗校正約 <strong>{value('compensate_brightness'):.2f} 秒</strong>，是這部分最大的耗時。</p>
<p><strong>這輪只量時間，沒有實作下面的新加速方案，也沒有改正式流程。</strong>137 個候選的內容及座標與前次完整結果相同；加計時器前後的對齊影像、差異影像與候選資料也完全相同。</p></div>
<p>照片：{html.escape(Path(d['target']).name)}。使用前輪實驗的「參照圖重用＋減少重複大圖資料」，參照圖已備妥。這次只量對齊、局部修正與差分，合計約 {profile_mean:.2f} 秒；不包含取圖等待、DINO或圖片儲存，不能直接與全流程35秒／85秒相比。</p>
<h2>對齊：{align:.2f} 秒怎麼花？</h2>{table(align_rows,align)}
<p>程式對正向、鏡像各測四個旋轉方向，共8組。這張圖最後採用鏡像、旋轉 {d['output_signature']['rotation']*90}°，因此不能直接拿掉鏡像檢查。每組有7,000個定位特徵與參照的7,000個比較，比對規模為7,000 × 7,000 × 8，約3.92億組。這些是用來對齊的角點、紋路特徵。</p>
<h2>差分：{diff:.2f} 秒怎麼花？</h2>{table(difference_rows,diff)}
<p>這裡的142個暫時候選，經結構變化檢查後分出5處結構變化，留下137個供後續AI判斷；不代表142顆螺絲。</p>
<details><summary>明暗校正內部，以及線材檢查內部</summary>
<table><tr><th>明暗校正</th><th>三輪合計</th></tr><tr><td>計算附近區域的平均、變化程度與兩圖關係</td><td>{value('brightness_local_statistics'):.3f} 秒</td></tr><tr><td>計算並套用明暗調整</td><td>{value('brightness_correction'):.3f} 秒</td></tr><tr><td>找出差異大的位置，減少它們對下一輪的影響</td><td>{value('brightness_reweight'):.3f} 秒</td></tr><tr><td>其他準備</td><td>{value('compensate_brightness','exclusive'):.3f} 秒</td></tr></table>
<p>線材檢查的 {value('wire_review'):.3f} 秒中，反覆計算各小區塊與候選框重疊多少，就占 {value('wire_component_overlap'):.3f} 秒。</p></details>
<h2>另外兩段目前較小</h2><table><tr><th>步驟</th><th>耗時</th><th>判斷</th></tr><tr><td>局部對齊微調</td><td>{local:.3f} 秒</td><td>分9區微調，其中求局部移動量約 {value('refine / findTransformECC'):.3f} 秒，暫不列為第一優先。</td></tr><tr><td>舊版候選核對</td><td>{legacy:.3f} 秒</td><td>產生39個核對框。完整保留，沒有為了加速刪除。</td></tr></table>
<h2>接下來具體怎麼改善？</h2>
<table><tr><th>建議順序</th><th>具體做法</th><th>本次量到的相關耗時</th><th>怎麼確認沒改錯</th></tr>
<tr><td>1. 先改善圖片轉向的準備</td><td>目前每個方向都搬動3072×3072的大圖，再縮到1536。嘗試先縮成檢測尺寸，再準備各方向，減少搬運的大圖資料；仍保留全部8方向搜尋。</td><td>{prep:.2f} 秒</td><td>逐方向核對縮圖像素、對齊矩陣與候選框；奇數尺寸、不同方向也須測。若縮放順序造成差異，不能直接套用。</td></tr>
<tr><td>2. 明暗校正共用暫存計算空間</td><td>保留三輪校正及原有公式順序；每一輪內，重複用到的「權重×參照圖」只算一次，其他乘加結果寫入可重用的暫存空間，減少反覆建立整張圖大小的資料。</td><td>{value('compensate_brightness'):.2f} 秒</td><td>核對校正影像、差異影像及候選框；不減少校正輪數、不改門檻，也不讓螺絲被當成亮度差異消除。</td></tr>
<tr><td>3. 線材重疊量一次算完</td><td>改成一次統計候選框內各區塊有多少像素，取代每個區塊各掃一次小圖。</td><td>線材檢查中的 {value('wire_component_overlap'):.2f} 秒</td><td>所有區塊計數、線材提示及候選結果需相同；保留目前提示用途。</td></tr>
<tr><td>另開實驗：減少完整方向搜尋</td><td>先用較少的定位特徵判斷正反與方向，再對最可能方向做完整比對；若方向不明或對齊品質不足，回到原本全部方向搜尋。</td><td>特徵尋找＋比對約 {features+match:.2f} 秒</td><td>這會改變搜尋流程，不能保證與原方法等效。尤其本案例需要鏡像，必須另測正反、旋轉、位移等情況，不能先關掉某些方向。</td></tr></table>
<p><strong>表中的秒數是目前整個步驟花的時間，不是保證能全部省下。</strong>前3項先以結果不變為驗證目標；方向搜尋較有潛力，但影響範圍也較大，要獨立驗證。以上方案本輪均尚未實作。</p>
<details><summary>同一張圖的對照與計時核對</summary><div class="images"><figure><figcaption>參照圖（沿用前次輸出）</figcaption><img src="{relative(saved/'reference.png')}" alt="參照圖"></figure><figure><figcaption>同一張待測圖，對齊後（沿用前次輸出）</figcaption><img src="{relative(saved/'aligned.png')}" alt="對齊後的待測圖"></figure></div>
<p>兩次細項計時取平均；前後各做一次不加細項計時器的對照。</p><table><tr><th>次序</th><th>方式</th><th>對齊＋局部修正＋差分合計</th><th>影像、候選結果</th></tr>{timingrows}</table>
<p>未加細項計時器平均 {control_mean:.3f} 秒，加計時器平均 {profile_mean:.3f} 秒，差 {profile_mean-control_mean:+.3f} 秒。這個差包含量測開銷與當時負載波動，無法完全拆開；不能視為新方案加速或變慢。各表只加同一層步驟，沒有把子步驟再重複加進總數。</p>
<p>正常參照圖準備與讀取待測原圖另花 {d['reference_and_raw_setup_seconds']:.3f} 秒，未算進上述內部計時。OpenCV版本 {d['opencv_version']}，執行緒設定 {d['opencv_threads']}；此次未調整核心數、GPU或正式服務。</p>
<p><a href="profile.json">完整計時、呼叫次數與候選核對</a> · <a href="preservation-after.json">正式檔案未變更證據</a></p></details>
<details><summary>程式實作依據（技術補充）</summary><p>目前採逐一比較特徵距離的BFMatcher；其行為可核對 <a href="https://docs.opencv.org/4.10.0/dc/dc3/tutorial_py_matcher.html">OpenCV官方說明</a>。減少方向搜尋是基於本次程式與實測提出的方案，並非官方保證加速。</p><p>重用陣列輸出空間可使用 <a href="https://numpy.org/doc/stable/reference/ufuncs.html">NumPy的out參數</a>；區塊像素計數可用 <a href="https://numpy.org/doc/stable/reference/generated/numpy.bincount.html">NumPy bincount</a>。實際省時與結果一致性仍須實驗確認。</p></details></html>'''
    (OUT/'index.html').write_text(text,encoding='utf-8')
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.urls=[]
        def handle_starttag(self,tag,attrs):
            self.urls.extend(v for k,v in attrs if k in ('href','src'))
    parser=Links();parser.feed(text);checked=0
    for url in parser.urls:
        if urlparse(url).scheme:continue
        assert (OUT/unquote(url)).is_file(),url
        checked+=1
    summary=dict(alignment_seconds=align,difference_seconds=diff,local_alignment_seconds=local,
        legacy_audit_seconds=legacy,total_profiled_seconds=profile_mean,feature_matching_seconds=match,
        orientation_image_preparation_seconds=prep,feature_extraction_seconds=features,
        brightness_correction_seconds=value('compensate_brightness'),wire_overlap_seconds=value('wire_component_overlap'),
        directions_tested=8,features_per_image=7000,candidates_unchanged=137,formal_changes=False,
        proposed_optimizations_implemented=False,dino_rerun=False,checked_local_links=checked)
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
