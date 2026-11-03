"""Plain-language report with explicit assistant visual audit, separate from model labels."""
import os,json,math
from collections import Counter
from PIL import Image,ImageOps
from experiments.dino.two_directions import ROOT,BASE,OUT,PRIOR,read,pairs,digest
from experiments.current_dataset_review import report as R

def view(im):
    w,h=im.size;im=im.resize((224,int(224*h/w)) if w<=h else (int(224*w/h),224),Image.Resampling.BICUBIC)
    x,y=(im.width-224)//2,(im.height-224)//2;return im.crop((x,y,x+224,y+224))
def groups(items):
    gs=[]
    for z in items:
        c=z['c'];cx,cy=c['x']+c['w']/2,c['y']+c['h']/2
        g=next((g for g in gs if math.hypot(cx-g[0]['c']['x']-g[0]['c']['w']/2,cy-g[0]['c']['y']-g[0]['c']['h']/2)<=45),None)
        if g:g.append(z)
        else:gs.append([z])
    return sorted(gs,key=lambda g:-len(g))
def main():
    R.OUT=OUT;(OUT/'images').mkdir(exist_ok=True)
    a=read(OUT/'a-cases.json');changed=[z for z in a if z['would_discard']];b=read(OUT/'b-cases.json')
    risk={4,25,29,33,35,36,43,50,64};uncertain={1,2,9,24,61,67,74}
    for n,z in enumerate(changed,1):
        z['audit_number']=n;z['visual_status']='疑似新增螺絲會被誤刪' if n in risk else '暫時無法確定' if n in uncertain else '原有物件／線材變化'
    btypes={'輪廓偏淡的圓形物件':[1,4,6,18,19,25,30], '頭和桿可見，仍判錯':[2,3,10,12,20], '與其他物件重疊／取圖不完整':[5,31,35,38]}
    reasons={
        '輪廓偏淡的圓形物件':'小圖仍看得到圓形主體；對照的螺絲範例大多邊緣很強、背景花紋很重。目前只能說外觀落差值得測試，不能宣稱已證明明暗就是唯一原因。',
        '頭和桿可見，仍判錯':'這幾例的小圖仍看得到頭和桿，不能一律歸因於沒有截到。DINO 仍把它們排在正常範例那邊；有些甚至拿圓頭範例與側面螺絲比較。應先改善實際 X 光螺絲範例的涵蓋範圍。',
        '與其他物件重疊／取圖不完整':'部分螺絲與線材、固定物件混在一起。第 31 例在小圖裡已不完整，第 38 例縮成正方形後長物件右端被裁掉。這一組才值得另外測試完整取圖，不能套用成所有誤刪的原因。'}
    chosen=[]
    for cat,nums in btypes.items():
        for n in nums:
            z=b[n-1];z['audit_number']=n;z['visual_status']=cat;chosen.append(z)
    annotations=dict(basis='assistant visual review of saved paired images and AI inputs; not complete user-confirmed ground truth',
        a=[dict(key=z['key'],number=z['audit_number'],status=z['visual_status']) for z in changed],
        b=[dict(key=z['key'],number=z['audit_number'],status=z['visual_status'],known=z['known']) for z in chosen],
        b_not_selected=[dict(key=z['key'],status='本次縮圖核對未列為明顯螺絲，不能視為已證明正常') for z in b if z not in chosen])
    (OUT/'visual-audit.json').write_text(json.dumps(annotations,ensure_ascii=False,indent=2),encoding='utf-8')
    nav='<nav id="top"><a href="index.html">先看結論</a><a href="a.html">圖一：減少誤報與誤刪風險</a><a href="b.html">圖二：誤刪原因</a></nav>'
    def card(z,kind):
        key=z['key'];c=z['c'];x,y,w,h=(c[k] for k in ('x','y','w','h'))
        canvas=Image.new('RGB',(800,400),'white')
        for j,im in enumerate(pairs(z)):canvas.paste(im.resize((400,400)),(400*j,0))
        canvas.save(OUT/'images'/f'{key}-pair.jpg',quality=92)
        link=os.path.relpath(BASE/'photos'/z['sha']/'report.html',OUT).replace('\\','/')+('#candidate-' if kind=='a' else '#removed-')+str(z['id'])
        body=f'<article id="case-{key}"><h3>{R.esc(z["name"])} · 位置 {z["id"]}</h3><p><b>{z["visual_status"]}</b> · 本頁核對編號 {z["audit_number"]}</p><p>左：參照圖　／　右：待測圖。紅框是原本的差分框。</p><img loading="lazy" style="width:100%;max-width:1000px" src="images/{key}-pair.jpg">'
        if kind=='b':
            mark='既有目視標記' if z['known'] else '助手目視疑似，仍待使用者確認'
            body+=f'<p>{mark}；原本 DINO 已排除。</p>'
            with Image.open(BASE/'photos'/z['sha']/'aligned.png') as im:crop=im.convert('RGB').crop((x-12,y-12,x+w+12,y+h+12))
            bank=ROOT/'workspace/windows-check/diagnostics/clip-screw-examples';e=c['classification']['dino_evidence']
            tiles=[('小圖完整範圍',ImageOps.pad(crop,(224,224))),('DINO 實際看到',view(crop))]
            for lab,txt in [('screw','最像的一張螺絲範例'),('normal','最像的一張正常範例')]:
                name=e[lab]['neighbors'][0];tiles.append((txt,view(Image.open(bank/(name if name.endswith('.png') else name+'.png')).convert('RGB'))))
            body+='<div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px">'
            for j,(title,im) in enumerate(tiles):
                f=f'{key}-input-{j}.png';im.save(OUT/'images'/f);body+=f'<figure><b>{title}</b><img loading="lazy" style="width:100%" src="images/{f}"></figure>'
            body+='</div><p>上面範例只展示最像的一張；實際判斷是各類最像三張的平均。左一黑邊只為方便展示完整範圍，並未送入 DINO。</p>'
        else:body+='<p>原方法保留；參照 DINO 也判成螺絲，所以簡單雙圖規則會改成排除。上面的核對結論由助手看圖判讀，不是另一個 DINO 分數。</p>'
        return body+f'<p><a href="{link}">完整照片與原始位置 →</a> · <a href="#top">返回本頁總覽</a></p></article>'
    def gallery(items,kind):
        body=''
        for gi,g in enumerate(groups(items),1):
            body+=f'<section><h3>MPT11 / 相近位置第 {gi} 組 · {len(g)} 個框／{len({z["sha"] for z in g})} 張照片</h3>'+card(g[0],kind)
            if len(g)>1:body+=f'<details><summary>展開其餘 {len(g)-1} 個同位置案例</summary>'+''.join(card(z,kind) for z in g[1:])+'</details>'
            body+='</section>'
        return body
    body=nav+'<h1>圖一：加看參照圖，能不能減少誤報？</h1><div class="answer"><b>有幫助，但不能用「兩邊都像螺絲就刪」作正式規則。</b><p>原本保留的 330 個框，這條規則會刪掉 74 個、剩 256 個。逐一看過這 74 個位置：58 個目視屬原有物件／線材變化；9 個有新增疑似螺絲、會有誤刪風險；7 個暫時不能確定。</p><p>你的圖一（96.tiff 位置 80）屬於可減少的誤報。但不能把刪掉的 74 框全部當作改善。</p></div><p>範圍：本批全部 330 個原本保留框，都在 MPT11 不良品照片內；良品原本已無保留框，所以本項沒有額外可刪的良品框。這是框數，不是螺絲顆數；58／9／7 為助手逐框目視核對，尚非完整人工標準答案或準確率。</p><h2>為什麼會誤刪？</h2><p>參照小圖可能包含旁邊原有的螺絲；也可能只是圓形板件圖案被 DINO 看成螺絲。因此「兩張都被叫作螺絲」，不等於「同一顆早就存在」。必須核對物件的位置、範圍是否對得上，並確認旁邊沒有新增物。</p>'
    for status in ['疑似新增螺絲會被誤刪','原有物件／線材變化','暫時無法確定']:
        zs=[z for z in changed if z['visual_status']==status];body+=f'<h2>{status}：{len(zs)} 框</h2>'+gallery(zs,'a')
    body+='<h2>下一步，僅建議，尚未實作</h2><p>把這 9 個風險案例固定為不可誤刪的檢查題。測試「同一物件是否對得上」而非只比兩邊分類，並檢查是否仍能排除那 58 個原有結構框。不可只把這批照片座標寫成排除清單。</p>'
    R.save('a.html','圖一：誤報減少與誤刪風險',body)
    body=nav+'<h1>圖二：先找誤刪，再分析原因</h1><div class="answer"><b>本次看過 40 個已排除的代表候選，整理出 16 個值得追查的位置。</b><p>其中 2 個已有目視螺絲標記；14 個是助手看圖後列為疑似誤刪（含你提出的圖二）。它們出現在 '+str(len({z['sha'] for z in chosen}))+' 張照片，不等於 16 顆獨立螺絲，也不是整批漏檢總數。</p><p>重點：有些螺絲明明完整出現在 AI 小圖裡，還是被排除。不能全部怪裁圖，也不能全部靠加看參照圖解決。</p></div><p>343 個只是先前自動挑出的候選；這次從分組代表與既有標記中看了 40 個。另 24 個未列為明顯螺絲，不代表已確認正常；其他未檢查的位置仍可能漏掉。此頁不測新排除規則、不宣稱已救回。</p>'
    for cat in btypes:
        zs=[z for z in chosen if z['visual_status']==cat];body+=f'<h2>{cat}：{len(zs)} 個位置</h2><p>{reasons[cat]}</p>'+gallery(zs,'b')
    body+='<h2>後續應分開測，不一起改</h2><ol><li>完整可見但被判錯：補入其他照片的實際 X 光螺絲範例，涵蓋淡圓形、側面頭與桿；本頁案例留作測試，避免拿答案教完又考同一張。</li><li>取圖不完整：只針對這類另測完整取圖；同時帶入線材對照，查看誤報代價。</li><li>重疊：另列一組，檢查 AI 是否被旁邊元件影響，不與單獨完整螺絲混算。</li></ol><p>以上是根據圖像提出的原因假設與下一步測法，目前未證明修改後會改善。</p><details><summary>查看全部 40 個抽查候選（含未列為明顯螺絲者）</summary>'
    for i in range(1,5):body+=f'<a href="b-review-{i}.jpg"><img loading="lazy" style="max-width:100%;width:700px" src="b-review-{i}.jpg"></a>'
    R.save('b.html','圖二：誤刪案例與原因',body+'</details>')
    body=nav+'<h1>兩個問題，分開看結果</h1><div class="answer"><h2>圖一：原本就有，卻被誤報</h2><p><b>加看參照圖有幫助，但直接拿來刪框會誤傷新增物。</b></p><p>330 個保留框中，預計刪掉 74 個。逐一看圖：58 個原有結構誤報、9 個新增疑似螺絲風險、7 個待確認。這是助手目視核對，不是完整人工驗收。</p><a href="a.html">看圖一的證據：哪些可刪、哪些不能刪 →</a></div><div class="answer"><h2>圖二：多了螺絲，卻被 DINO 排除</h2><p><b>先找到案例，這次不改判斷規則。</b></p><p>抽查 40 個代表候選，整理出 16 個追查位置：2 個已有目視標記、14 個疑似誤刪。分成「偏淡的圓形」「看得到頭和桿仍判錯」「重疊或取圖不完整」三組。</p><a href="b.html">看圖二的案例與可能原因 →</a></div><p><b>正式流程、模型和設定未修改，未重跑整批差分。</b> 本次只讀取保存的圖片，對原本保留框補做參照圖 DINO 推論，再看圖核對。</p><p>報告沿用機種 → 問題類型 → 相近位置分組；每組先看代表圖，其餘可展開。相近位置只為方便瀏覽，不代表必定同一物件。</p><details><summary>核對資料與重現方式</summary><a href="plan.json">圖一固定測試規則</a> · <a href="visual-audit.json">逐框目視記錄</a> · <a href="summary.json">統計</a><p>圖一檢查全部 74 個會改變決策的框；圖二逐看 40 個代表候選，並還原 16 個追查位置的實際 AI 輸入。未將助手判讀寫入正式標註。</p></details>'
    R.save('index.html','圖一與圖二：分開驗證',body)
    summary=dict(a=dict(original_kept=330,would_discard=74,remaining=256,visual_existing=58,visual_new_risk=9,uncertain=7),b=dict(reviewed=40,flagged=16,known=2,suspected=14,photos=len({z['sha'] for z in chosen}),groups={k:len(v) for k,v in btypes.items()}),formal_changes=False)
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    assert Counter(z['visual_status'] for z in changed)==Counter({'原有物件／線材變化':58,'疑似新增螺絲會被誤刪':9,'暫時無法確定':7})
    assert all(digest(__import__('pathlib').Path(p))==v for p,v in read(OUT/'plan.json')['hashes'].items())
    print(json.dumps(summary,ensure_ascii=False))
    from experiments.dino.simple_readout import main as simplify
    simplify()
if __name__=='__main__':main()
