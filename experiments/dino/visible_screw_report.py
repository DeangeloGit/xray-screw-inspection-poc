"""Full corpus report for actual B-part detections, with semantic-control evidence."""
import sys,json,os,shutil,re
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote
from PIL import Image
import numpy as np
import answered_batch_report as full
ROOT=Path(__file__).resolve().parents[2];EXP=ROOT/'workspace/dino-4r-visible-screw-20261106/v3';OUT=EXP/'final';BASE=ROOT/'workspace/dino-4r-blackblock-20261106/final';RETIRED=ROOT/'workspace/dino-4r-hardnegative-20261106/manual-normal/final'
read=full.read;save=full.save
def main():
    prepare='--prepare-only' in sys.argv;reuse='--reuse-full' in sys.argv
    save(OUT/'manual-feedback.json',{'128-10':dict(label='screw',text='使用者確認新增／掉落物件。'),'135-88':dict(label='screw',text='使用者確認線材旁有掉落螺絲。'),'128-3':dict(label='normal',text='使用者確認正常結構變化。'),'128-5':dict(label='occluder',text='使用者確認要辨認右側B螺絲；此框主要是黑塊，不把黑塊本體當成螺絲命中。')})
    if reuse:
        v=read(OUT/'verification.json');assert v['status']=='passed';assert all(full.sha(OUT/p)==h for p,h in v['result_sha256'].items())
    else:sys.argv=[sys.argv[0],str(OUT)];full.main()
    if prepare:return
    report=OUT/'report';images=report/'images';summary=read(OUT/'summary.json');cases=read(OUT/'cases.json');ci={c['key']:c for c in cases};answers=read(OUT/'answers.json');marks=read(OUT/'answer-matches.json')
    assert summary['totals']['pilot']==dict(kept=128,answer_hits=69,unmatched=50)
    oldhits={(m['photo'],m['id']) for m in read(BASE/'answer-matches.json') if m['methods']['pilot']};hits={(m['photo'],m['id']) for m in marks if m['methods']['pilot']};assert oldhits<=hits and len(oldhits)==59
    assert ci['128-10']['keep']['pilot'] and ci['135-88']['keep']['pilot'] and not ci['128-3']['keep']['pilot'] and not ci['128-5']['keep']['pilot'] and ci['128-87']['keep']['pilot']
    new=[c for c in cases if c['keep']['pilot'] and not c['keep']['recovery']];assert len(new)==10 and all(c['answers']==[10] for c in new)
    assert all(r['metrics']['pilot']['unmatched']==r['metrics']['recovery']['unmatched'] for r in read(OUT/'rows.json'))
    raw={};unchanged=0;new_count=0;feature_checks=0;scores=read(EXP/'all-part-scores.json');scoreidx={(z['photo'],tuple(z['box'])):z for z in scores}
    for p in (OUT/'runs/pilot').glob('*/result.json'):
        r=read(p);old=read(BASE/'runs/pilot'/p.parent.name/'result.json');index={full.geom(c):c for c in r['candidates']+r['filtered_candidates']}
        for c in old['candidates']+old['filtered_candidates']:
            n=index[full.geom(c)];assert n['id']==c['id'] and n['classification']==c['classification'];unchanged+=1
        for c in r['candidates']+r['filtered_candidates']:
            raw[f'{p.parent.name}-{c["id"]}']=c
            if c.get('recovery')!='r4_visible_part':continue
            new_count+=1;z=scoreidx[(p.parent.name,full.geom(c))];pair=c['classification']['paired_evidence']
            for side in ('reference','target'):
                assert pair[side]['input_sha256']==z['pair'][side]['input_sha256'];assert abs(pair[side]['screw_margin']-z['pair'][side]['margin'])<1e-5;feature_checks+=1
    assert unchanged==1345 and new_count==987 and len(cases)==2332
    tests=read(EXP/'B-perturbation-results.json');controls=read(EXP/'B-counterfactual-results.json');proof=read(EXP/'actual-B-input-proof.json');assert tests['stable_tests']==tests['total_tests']==450 and len(controls['tests'])==40 and proof['occluder_pixels_in_inputs']==0
    assert all((not r['keep']) if r['kind']=='B_removed_occluder_retained' else r['model_inputs_identical'] for r in controls['tests'])
    for c in new:
        x,y,w,h=c['canonical_object']['box'];ox,oy,ow,oh=raw[c['key']]['visible_part']['occluder_box'];assert max(0,min(x+w,ox+ow)-max(x,ox))*max(0,min(y+h,oy+oh)-max(y,oy))==0
        for side in ('reference','target'):
            q=next(q for q in proof['rows'] if q['photo']==c['photo'] and q['side']==side);assert q['input_sha256']==c['paired_evidence'][side]['input_sha256']
    retired_cases=read(RETIRED/'cases.json');retired_kept=[c for c in retired_cases if c['keep']['pilot']];retired_hits={(c['photo'],i) for c in retired_kept for i in full.matches(c['native'],answers.get(c['photo'],{}).get('marks',[]))[0]};retired_outside=sum(not full.matches(c['native'],answers.get(c['photo'],{}).get('marks',[]))[0] for c in retired_kept)
    assert len(retired_hits)==59 and retired_outside==60
    audit=dict(historical_original_scoring=dict(hits=69,answers=101,unmatched=50),same_B_annotation_scoring=dict(hits=len(retired_hits),answers=101,unmatched=retired_outside),explanation='Historical black-block candidate boxes do not localize the user-confirmed exposed B screw. Historical outputs unchanged.')
    save(EXP/'retired-B-reassessment.json',audit)
    body='<p>使用者確認B為被遮擋螺絲露出的部位。本輪新增的是B局部候選；模型輸入不包含黑塊本體。原黑塊候選128-5仍排除、正常128-3仍排除，右側另一支已命中螺絲128-87維持保留。</p><p>全部原1,345候選重新推論，分類內容逐項相同；另產生987個可見部位候選，保留其中10個，皆對到B。合計69／101、框外警報50，各張照片都未增加。原55處、兩處人工確認及前輪59處全保住。</p>'
    body+='<p class="warn">本批仍為開發回歸，沒有一般良品圖或外部獨立測試。新增範例只用128、131、132；第136張已用來診斷邊緣細線，所以本輪不稱獨立驗收。128的B由使用者確認，精確框及其他9張B位置由助理逐張檢視，人工與助理標註分開記錄。合成移除測試不取代實拍驗證。</p>'
    body+='<h2>從黑塊框改成可見螺絲部位</h2><p>先從遮擋物邊緣找出新增的可見部分，去掉連續的黑塊邊緣細線；模型只取露出部位的矩形，以白色補成方形，保留比例，不取周圍黑塊。基礎47螺絲＋65正常雙圖維持；新增局部分類使用原範例加3個B局部與12個參照正常局部，合計50＋77。沒有整塊黑影正例。</p><p>待測局部分數≥0.05且同位置參照分數&lt;0才保留。查詢框位移或縮放時，依影像找出的同一遮擋物與同一側重新定位可見部位，再做新推論；不讀答案、不以照片編號決定結果。</p>'
    body+='<h2>用同一套B位置答案重新核對</h2>'+full.table(['版本','命中／101','答案框外警報','B定位'],[['原保留基準',59,50,'未補抓'],['已撤回的整塊黑影方案',59,60,'黑塊框沒有對到B'],['本輪B局部分類',69,50,'10處B皆命中']])
    body+='<p>已撤回方案先前69／101、框外警報50是舊位置口徑的歷史量測，不改寫原始紀錄。依使用者確認的B位置重新核對後，黑塊警報不能充當B命中。本輪與基準一律使用相同B答案，新增10處來自真正B候選，不是把舊黑塊框重新算成命中。</p>'
    body+='<h2>10張照片：實際B框與模型輸入</h2>'
    for c in sorted(new,key=lambda c:c['photo']):
        p=c['paired_evidence'];body+=f'<article><h3>{c["photo"]}／新增候選#{c["id"]}：B保留</h3><p><a href="photo-{c["photo"]}.html#case-{c["key"]}">完整照片／同類案例</a>；參照分數{p["reference"]["screw_margin"]:.4f}，待測分數{p["target"]["screw_margin"]:.4f}。</p><img class="pair" src="images/{c["key"]}.jpg"><details><summary>模型實際輸入：左參照、右B；黑塊像素為0</summary><img src="images/B-input-{c["photo"]}-reference.png" style="width:224px"> <img src="images/B-input-{c["photo"]}-target.png" style="width:224px"></details></article>'
    body+='<h2>保留黑塊、移除B的控制測試</h2><p>十張各做一次：只把B部位替換為同位置參照，保留黑塊及右側D螺絲，重新找局部候選與推論。十次都沒有B警報。另各改變黑塊內部三種深淺，共30次；B仍被定位，實際模型輸入與分數完全不變。以下為合成診斷：左原圖、右移除B；不宣稱是新實拍照片。</p>'
    for photo in map(str,range(128,138)):body+=f'<details><summary>{photo}：保留黑塊、移除B → 不保留B警報</summary><img src="images/B-removal-{photo}.png"></details>'
    body+='<h2>穩定性與前輪保護</h2><p>10處B，各做45種框位移／縮放，450次皆為新推論且結果一致。縮放0.75、0.9、1、1.1、1.25；x/y位移各−4、0、4像素。這是帶有影像遮擋物／側邊關聯的候選框擾動，不是影像旋轉或加雜訊測試。</p><p>原1,345候選的框、ID、完整分類內容皆與基準相同，原12組衝突及指定案例的既有判斷沒有改動；本輪沒有宣稱重跑前輪1,260／1,800次測試。只另驗證新B部位450次。</p>'
    body+='<h2>失敗嘗試也保留</h2><p>第一版B提取找回9處；136的B與細邊連在一起而過長。第二版先分離連續邊緣，找回10處，但未帶遮擋物關聯的細小查詢框在±4像素擾動時容易換物件。第三版加入影像物件關聯後450次皆一致。這些是本批開發歷程，不混稱全部未參與開發的驗證。</p>'
    body+='<h2>新增範例：只顯示部位，不含整塊黑影</h2>'
    for file in sorted((EXP.parent/'part-examples').glob('*.png')):
        shutil.copy2(file,images/file.name);body+=f'<details><summary>{full.esc(file.stem)}</summary><img src="images/{file.name}" style="width:224px"></details>'
    body+='<p><a href="../../B-annotation-changes.json">B位置標註修正及權限來源</a> · <a href="../../retired-B-reassessment.json">舊黑塊框依B位置重新核對</a> · <a href="../../B-perturbation-results.json">450次新推論</a> · <a href="../../B-counterfactual-results.json">40次合成控制測試</a> · <a href="../../actual-B-input-proof.json">20張實際輸入影像雜湊</a> · <a href="../../all-part-scores.json">全部987局部候選分數</a> · <a href="../../../part-bank-plan.json">局部範例來源</a></p>'
    (report/'visible-screw.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>B可見螺絲證據</title><style>'+full.STYLE+'</style><main>'+full.NAV+'<h1>B可見螺絲證據</h1>'+body+'</main></html>',encoding='utf-8')
    def add(match):
        key=match.group(1);c=raw[key];p=c['classification']
        if c.get('recovery')!='r4_visible_part':return match.group(0)
        ex=p['visible_part_experiment'];text='<details><summary>可見部位模型證據（不輸入黑塊）</summary><p>遮擋物框：'+full.esc(ex['geometry']['occluder_box'])+'；側邊：'+full.esc(ex['geometry']['side'])+'；實際部位框：'+full.esc(p['canonical_object']['box'])+'；模型輸入的遮擋物像素：0。待測門檻0.05，參照須小於0。</p></details>'
        return match.group(0).replace('</article>',text+'</article>')
    for p in report.glob('*.html'):
        text=p.read_text(encoding='utf-8').replace('</nav>','<a href="visible-screw.html">附加：B可見螺絲證據</a></nav>',1)
        text=text.replace('原始55／100與校正增加分開列於附加頁，校正不是模型新增命中。','本輪依使用者確認的B部位另存定位修正；所有版本用同一B答案比較。原基準59處保住，新增10處為實際B候選。原始答案不改。')
        text=re.sub(r'<article id="case-([^"]+)">[\s\S]*?</article>',add,text);p.write_text(text,encoding='utf-8')
    class Parser(HTMLParser):
        def __init__(self):super().__init__();self.ids=[];self.links=[]
        def handle_starttag(self,t,a):
            d=dict(a)
            if 'id' in d:self.ids.append(d['id'])
            self.links.extend(d[k] for k in ('href','src') if k in d)
    parsed={}
    for p in report.glob('*.html'):
        v=Parser();v.feed(p.read_text(encoding='utf-8'));assert len(v.ids)==len(set(v.ids));parsed[p.resolve()]=v
    links=0
    for p,v in parsed.items():
        for link in v.links:
            name,_,anchor=link.partition('#');dest=(p.parent/unquote(name)).resolve() if name else p;assert dest.exists(),(p,link)
            if anchor:assert anchor in parsed[dest].ids
            links+=1
    for pattern in ('photo-*.html','category-*.html'):assert sum(p.read_text(encoding='utf-8').count('可見部位模型證據（不輸入黑塊）') for p in report.glob(pattern))==987
    fs=[p for p in images.iterdir() if p.suffix in ('.jpg','.png')]
    for p in fs:
        with Image.open(p) as im:im.verify()
    plan=read(OUT/'plan.json')
    for group in ('hashes','experiment_hashes'):assert all(full.sha(p)==h for p,h in plan[group].items())
    bank=np.load(EXP.parent/'visible-part-bank.npz')['bank'];old=np.load(ROOT/'models/dino-paired-optimized-47-20261104-r3/paired-features.npz')['bank'];assert np.array_equal(bank[:47],old[:47]) and np.array_equal(bank[50:115],old[47:])
    v=read(OUT/'verification.json');v.update(html_pages=len(parsed),links_checked=links,images_checked=len(fs),original1345_classifications_exactly_preserved=True,new_part_candidates=987,part_feature_hashes_and_scores_checked=feature_checks,new_B_detections=10,original55_and_two_confirmed_preserved=True,all59_preserved=True,unmatched_unchanged_each_photo=True,normal128_3_excluded=True,black128_5_excluded=True,all987_part_evidence_covered=True,actual_B_model_inputs_verified=20,occluder_pixels_in_inputs=0,fresh_B_perturbation_tests=450,synthetic_B_removal_negative_tests=10,synthetic_black_interior_invariance_tests=30,original_47_and_65_preserved=True)
    save(OUT/'verification.json',v);print('FULL B REPORT VERIFIED',len(parsed),links,len(fs),'candidates',len(cases))
if __name__=='__main__':main()
