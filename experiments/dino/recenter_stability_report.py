"""Explain the crop recentering improvement and its normal-case cost honestly."""
import sys,json,hashlib,html
from pathlib import Path
from collections import Counter
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.dino.recenter_local_pilot import OUT,PRIOR,OFFSETS,read,save,digest
from experiments.dino.local_added_object_report import CSS
from experiments.dino.local_added_object_pilot import font
BEFORE=ROOT/'workspace/dino-recenter-pair-20261103'
def main():
    plan=read(PRIOR/'plan.json');cases=plan['cases'];rows=read(OUT/'results.json');old=read(BEFORE/'results.json');pose=read(ROOT/'workspace/dino-recenter-pose-20261103/results.json');consensus=read(ROOT/'workspace/dino-recenter-consensus-20261103/results.json')
    assert len(rows)==len(old)==len(pose)==len(consensus)==17
    for i,z in enumerate(cases):
        assert all(r[i]['key']==z['key'] for r in [rows,old,pose,consensus])
        for r in [rows,old,pose,consensus]:assert [(t['dx'],t['dy']) for t in r[i]['trials']]==OFFSETS
    def success(t):return t['target']['screw'] and not t['reference']['screw']
    for r in rows:
        for t in r['trials']:assert t['paired_keep']==success(t)
    positives=[sum(t['paired_keep'] for t in r['trials']) for r in rows[:2]];assert positives==[13,13]
    normal=[dict(number=r['number'],category=r['category'],alerts=sum(t['paired_keep'] for t in r['trials'])) for r in rows[2:]]
    normal_alerts=sum(z['alerts'] for z in normal);old_alerts=sum(t['before']['paired_keep'] for r in old[2:] for t in r['trials'])
    summary=dict(cases=17,screw_positions=2,normal_positions=15,wire_positions=8,positions_per_case=13,total_pair_evaluations=221,
        strict_pair_success_before=[sum(t['before']['paired_keep'] for t in r['trials']) for r in old[:2]],strict_pair_success_after=positives,
        old_normal_alert_trials=old_alerts,new_normal_alert_trials=normal_alerts,normal_cases_with_alert=[z for z in normal if z['alerts']],
        identical_positive_crop_boxes=[len({tuple(t['crop_box']) for t in r['trials']}) for r in rows[:2]],
        formal_changes=False,limitation='Same development images; shifted search positions are not independent images; no claim of model-level translation invariance.')
    save(OUT/'summary.json',summary)
    # Re-audit production model, detection/list code and source images at completion.
    protected=read(BEFORE/'preservation-before.json');changed=[p for p,h in protected.items() if digest(Path(p))!=h];assert not changed,changed
    save(OUT/'preservation.json',dict(protected_files=len(protected),unchanged=True,formal_changes=False))
    nav='<nav><a href="index.html">先看改善與代價</a><a href="normal.html">正常案例對照</a><a href="details.html">13 種位置與完整數據</a></nav>'
    def write(name,title,body):
        (OUT/name).write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><style>'+CSS+'</style><main>'+nav+body+'</main></html>',encoding='utf-8')
    def pair_text(t):return f'參照：{"螺絲" if t["reference"]["screw"] else "非螺絲"}／待測：{"螺絲" if t["target"]["screw"] else "非螺絲"}'
    def make_trial_images(n,t):
        # Scripts persist all positive inputs and normal unshifted inputs. Materialize
        # remaining views directly from the recorded boxes, verifying input hashes.
        from dino_adapter import input_image
        import numpy as np
        m=read(ROOT/'models/dino-paired-47-20261103/manifest.json');z=cases[n-1]
        for side,f in [('reference','reference.png'),('target','aligned.png')]:
            im=Image.open(Path(z['source'])/f).convert('L').crop(tuple(t['crop_box']));inp=input_image(m,np.asarray(im,dtype='float32')/255)
            assert hashlib.sha256(inp.tobytes()).hexdigest()==t[side]['input_sha256']
            inp.save(OUT/'images'/f'{n}-{t["dx"]}-{t["dy"]}-{side}.png')
    def card(n):
        z=cases[n-1];r=rows[n-1];alerts=[t for t in r['trials'] if t['paired_keep']];shown=next((t for t in r['trials'] if n>2 and t['paired_keep']),r['trials'][0]);make_trial_images(n,shown);dx,dy=shown['dx'],shown['dy']
        label=f'指定雙圖判斷正確 {len(alerts)}／13' if n<=2 else f'正常案例誤報 {len(alerts)}／13'
        body=f'<article id="case-{n}"><h3>{n}. {html.escape(z["title"])} · {z["machine"]}／位置 {z["id"]}</h3><p><b>{label}</b></p>'
        if n<=2:body+='<p>13 種搜尋位置重新取圖後，都找回同一個近照範圍。DINO 每次收到相同內容，所以維持相同判斷；這不是 DINO 自己學會忽略偏移。</p>'
        elif alerts:body+=f'<p class="bad">以下展示失敗位置：左右偏移 {dx}、上下偏移 {dy} 像素。線材或板邊的差分輪廓隨取樣位置改變，仍可能被裁成像螺絲的外觀。</p>'
        else:body+='<p>這個正常案例的 13 種位置都沒有產生螺絲保留框；以下展示原位置。</p>'
        body+='<div class="tiles">'
        for side,title in [('reference','DINO 實際看到的參照圖'),('target','DINO 實際看到的待測圖')]:body+=f'<figure><figcaption>{title}</figcaption><img style="width:330px" src="images/{n}-{dx}-{dy}-{side}.png"></figure>'
        body+=f'</div><p><b>{pair_text(shown)}</b></p><details><summary>展開此案例全部 13 種位置</summary><table><tr><th>左右／上下偏移（像素）</th><th>舊方式</th><th>重新找中心後</th><th>結果</th></tr>'
        for j,t in enumerate(r['trials']):
            make_trial_images(n,t);before=old[n-1]['trials'][j]['before'];goal=t['paired_keep'] if n<=2 else not t['paired_keep']
            body+=f'<tr><td>{t["dx"]}／{t["dy"]}</td><td>{pair_text(before)}</td><td>{pair_text(t)}<br><a href="images/{n}-{t["dx"]}-{t["dy"]}-reference.png">參照小圖</a> · <a href="images/{n}-{t["dx"]}-{t["dy"]}-target.png">待測小圖</a></td><td>{"符合本例預期" if goal else "不符合"}</td></tr>'
        body+=f'</table></details><details><summary>看原始較大範圍與候選框</summary><img class="pair" src="../{PRIOR.name}/images/{n}-pair.jpg"></details><p class="note">{html.escape(z["name"])}；{html.escape(z["basis"])}</p>'
        source=Path(z['source']);links=f'<a href="normal.html#machine-{z["machine"]}">返回此機種</a> · <a href="normal.html#category-{z["machine"]}-{z["category"]}">查看同類案例</a>' if n>2 else '<a href="index.html">返回兩顆總覽</a>'
        return body+f'<p><a href="{(source/"reference.png").as_uri()}">完整參照圖</a> · <a href="{(source/"aligned.png").as_uri()}">完整待測圖</a> · {links}</p></article>'
    body='''<h1>重新找中心：兩顆螺絲不再因這批偏移測試而判錯</h1><div class="answer"><h2>斜螺絲 4／13 → 13／13；圓頭螺絲維持 13／13。</h2><p>成功條件都是 <b>「參照圖非螺絲、待測圖螺絲」</b>，沒有用待確認代替。</p><p><b>代價：</b>15 個正常對照中，1 個線材與 1 個板邊各有 3 次誤報。這輪改善了兩顆的定位穩定性，但正常誤報仍需解決，未套用正式流程。</p></div><h2>上次到底改了什麼？</h2><p>上次只改 DINO 收到的小圖：從差分找出相連的深色區域，依該範圍取貼近物件的正方形近照，減少周圍板件；參照取同位置、同大小。DINO 模型、47＋65 範例與分類門檻都沒換。</p><h2>這次多做哪一步？</h2><p><b>把不準的位置當作搜尋起點，重新找輪廓中心後才裁圖。</b></p><ol><li>取圖位置偏移時，回到完整的已對齊原圖，重新計算附近的差異。</li><li>找與候選重疊最多的相連差異範圍，再以這個範圍的中心取近照。</li><li>參照與待測使用完全相同的取圖位置，各自交給原 DINO 分類。</li></ol><p>這次兩顆在 13 個搜尋位置都找回同一個近照範圍，因此 DINO 的輸入穩定了。沒有手寫螺絲座標，也沒有挑選 DINO 分數最高的一張來算成功。</p><h2>同一批案例的結果</h2><table><tr><th>案例</th><th>近照框直接跟著偏移</th><th>偏移後重新找中心</th></tr><tr><td>斜螺絲</td><td>4／13 判對</td><td>13／13 判對</td></tr><tr><td>圓頭螺絲</td><td>13／13 判對</td><td>13／13 判對</td></tr><tr><td>15 個正常對照</td><td>1 個案例出現誤報，共 2 次</td><td>2 個案例出現誤報，共 6 次</td></tr></table><p>每個案例測原位置、上下左右與斜角偏移 2 像素、上下左右偏移 4 像素，共 13 種位置。這是同一張圖片的重複測試，不是 13 張獨立照片；兩顆螺絲也來自同一張原照片。</p>'''
    body+=card(1)+card(2)+'''<h2>正常線材有沒有一起比較？</h2><p>有。原來的 8 個線材＋7 個原有物件／板件都保留。13 個正常案例全程排除；第 4 例線材和第 12 例板邊，各在 3 個偏移位置被誤報。</p><p>原位置不偏移時，15 個正常對照仍全數排除。新增的問題是在位置偏移後出現，不能用原位置的結果掩蓋。</p><p><a href="normal.html">查看全部正常對照及兩個誤報案例 →</a></p><h2>哪些做法沒成功？</h2><p>試過直接用整張差異圖重新置中、去掉細線連接、把長條物件轉正，都未讓斜螺絲達成指定雙圖判斷。另試附近 9 個輪廓取中間結果，沒有進一步減少正常誤報，所以沒有採用。</p><h2>目前能下的結論</h2><p>在這一批、這 13 種位置變動下，重新找中心確實穩住兩顆螺絲的雙圖分類。下一個問題是避免線材與板邊在偏移後被裁成螺絲外觀；還不能把這個方案直接定為正式版本。</p><p class="note">模型與正式程式未修改；未重跑整批檢測。這是原有 17 個固定開發案例的實驗，不能當成整批準確率或獨立驗證。</p>'''
    write('index.html','取圖偏移改善：同批案例驗證',body)
    body='<h1>正常案例：全部 15 個與偏移結果</h1><p>依機種 → 類型 → 位置檢視。每個位置都有全部 13 種偏移結果；沒有只展示成功例。</p>'
    for machine in ['MPT10','MPT11','MPT12','KPH33']:
        nums=[n for n,z in enumerate(cases,1) if n>2 and z['machine']==machine];body+=f'<section id="machine-{machine}"><h2>{machine} · {len(nums)} 個位置</h2>'
        for category in ['線材','板件邊界','元件外觀','U 形結構','待確認']:
            sub=[n for n in nums if cases[n-1]['category']==category];body+=f'<div id="category-{machine}-{category}"><h3>{category} · {len(sub)} 個位置</h3>'
            if sub:
                body+=card(sub[0])
                if len(sub)>1:body+=f'<details><summary>展開其餘 {len(sub)-1} 個同類位置</summary>'+''.join(card(n) for n in sub[1:])+'</details>'
            else:body+='<p>本次固定小樣本未選入，數量為 0。</p>'
            body+='</div>'
        body+='</section>'
    body+='<script>function show(){const n=document.getElementById(decodeURIComponent(location.hash.slice(1)));for(let p=n;p;p=p.parentElement)if(p.tagName==="DETAILS")p.open=true;if(n)n.scrollIntoView()}show();addEventListener("hashchange",show);</script>'
    write('normal.html','正常案例：偏移誤報核對',body)
    body='''<h1>實驗方法與資料</h1><p>前後比較同一批 17 個案例、相同 13 組偏移量。舊方式移動已求出的近照框；新方式把同樣的偏移加到原候選位置，重新執行輪廓擷取，再裁近照。這測的是取圖前重新定位的補償能力，不是在宣稱 DINO 對真正被截斷、旋轉或變形的螺絲都能辨認。</p><p>輪廓計算沿用前輪：只用候選外圍估計局部平移與明暗差，再找差值超過 0.08 的相連區域，選與候選重疊最多者。每一種偏移都重新計算，沒有從先前成功記錄讀取固定裁框。DINO 取圖仍來自原始已對齊圖的相同座標，沒有把參照另外平移、壓背景或畫上待測輪廓。</p><p>若找不到相連區域，退回原候選外加 12 像素的雙圖分類；不強制排除、不列待確認。本次要追蹤的兩顆在全部 13 種位置皆成功找到輪廓，沒有走退回流程。</p><h2>比較過的其他方法</h2><table><tr><th>方法</th><th>斜螺絲達成指定雙圖判斷</th><th>圓頭螺絲</th><th>正常誤報次數</th></tr>'''
    variants=[('近照框直接偏移',[sum(t['before']['paired_keep'] for t in r['trials']) for r in old],0),('整圖差異重新置中',[sum(t['modes']['local_brightness_removed'].get('paired_keep',False) for t in r['trials']) for r in old],sum(not t['modes']['local_brightness_removed']['valid'] for r in old for t in r['trials'])),('去細線後置中',[sum(t['modes']['opened_center']['paired_keep'] for t in r['trials']) for r in pose],0),('去細線並轉正',[sum(t['modes']['opened_upright']['paired_keep'] for t in r['trials']) for r in pose],0),('局部輪廓重新置中',[sum(t['paired_keep'] for t in r['trials']) for r in rows],0),('附近九個輪廓取中間值',[sum(t['paired_keep'] for t in r['trials']) for r in consensus],0)]
    for label,values,invalid in variants:body+=f'<tr><td>{label}</td><td>{values[0]}／13</td><td>{values[1]}／13</td><td>{sum(values[2:])}／195'+(f'；另有 {invalid} 次無有效裁圖，不算成功排除' if invalid else '')+'</td></tr>'
    body+='</table><p>另外的原始整圖差異法，把斜螺絲連進大塊背景，13 次都沒有有效裁圖，已排除該方案。整圖差異法中沒有裁圖的案例，沒有被算作正確排除。</p><h2>限制</h2><ul><li>只有兩顆新增螺絲，且同一張照片；偏移測試不是獨立新樣本。</li><li>正常對照中有 7 個案例原本就在正常範例庫，本輪沿用原 47＋65 範例；所以不宣稱獨立準確率。</li><li>測試候選位置偏移，未涵蓋對齊錯誤、螺絲實際移動、亮度或姿態改變。</li><li>兩顆最終裁圖在 13 次皆相同，改善來源是定位穩定，不是 DINO 本身對不同輸入更有韌性。</li></ul><p><a href="plan.json">固定案例</a> · <a href="rules.json">本輪規則</a> · <a href="results.json">全部 221 組結果</a> · <a href="summary.json">統計</a> · <a href="preservation.json">正式模型與資料未變核對</a></p>'
    write('details.html','實驗規則與限制',body)
    # Key example: rightward 2px shift, old target fails; relocated pair is correct.
    canvas=Image.new('RGB',(1140,500),'#f4f7f8');draw=ImageDraw.Draw(canvas)
    draw.text((20,15),'斜螺絲：搜尋位置向右偏 2 像素',font=font(29),fill='#173d4b')
    for col,(title,file) in enumerate([('舊待測小圖：判非螺絲',BEFORE/'images/1-before-2-0-target.png'),('重新置中後參照：非螺絲',OUT/'images/1-2-0-reference.png'),('重新置中後待測：螺絲',OUT/'images/1-2-0-target.png')]):
        draw.text((20+col*375,65),title,font=font(23),fill='#173d4b');canvas.paste(Image.open(file).resize((350,350)),(20+col*375,105))
    draw.text((20,465),'模型和範例沒換；重新找回輪廓中心後，兩張圖分別判對。',font=font(22),fill='#173d4b');canvas.save(OUT/'summary.png')
    print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
