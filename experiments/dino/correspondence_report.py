"""Complete batch report plus correspondence, full contour and stability evidence."""
import argparse,json,sys
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote
from PIL import Image
import answered_batch_report as full
from correspondence_stability_probe import fingerprint

def main():
    p=argparse.ArgumentParser();p.add_argument('experiment',type=Path);p.add_argument('--reuse-full',action='store_true');a=p.parse_args();exp=a.experiment.resolve();out=exp/'final';read=full.read;save=full.save
    if a.reuse_full:
        v=read(out/'verification.json');assert v['status']=='passed' and len(v['result_sha256'])==33
        assert all(full.sha(out/p)==h for p,h in v['result_sha256'].items())
    else:
        sys.argv=[sys.argv[0],str(out)];full.main()
    report=out/'report';summary=read(out/'summary.json');tests=read(exp/'perturbation-results.json');cases=read(out/'cases.json');idx={c['key']:c for c in cases}
    assert len(tests['pairs'])==16 and tests['total_tests']==1260
    assert tests['stable_object_tests']==tests['stable_prediction_tests']==1260
    assert summary['totals']['pilot']['answer_hits']>=55 and not summary['lost_recovery_answers']
    assert summary['totals']['pilot']['unmatched']<=58
    assert all(r['metrics']['pilot']['unmatched']<=r['metrics']['recovery']['unmatched'] for r in read(out/'rows.json'))
    plan=read(out/'plan.json');assert all(full.sha(p)==h for p,h in plan['experiment_hashes'].items())
    manifest=read(exp/'evidence-manifest.json');assert all(full.sha(p)==h for p,h in manifest['files'].items())
    old=read(exp.parent/'dino-4r-stability-20261106/perturbation-results.json');oldpairs={r['pair']['kept']:r for r in old['pairs']}
    for rec in tests['pairs']:
        if not rec['pair'].get('user_flagged'):assert rec['expected']['verdict']==oldpairs[rec['pair']['kept']]['expected']['verdict']
        for key in set(rec['pair'][k] for k in ('kept','excluded')):
            photo,cid=key.split('-');result=read(out/'runs/pilot'/photo/'result.json')
            c=next(c for c in result['candidates']+result['filtered_candidates'] if c['id']==int(cid))
            assert fingerprint(c['classification'])==rec['expected'],key
    groups={}
    for c in cases:groups.setdefault((c['photo'],c['canonical_object']['object_id']),[]).append(c)
    assert all(len({c['keep']['pilot'] for c in group})==1 for group in groups.values())
    objects={m:dict(alarms=sum(any(c['keep'][m] for c in g) for g in groups.values()),unmatched=sum(any(c['keep'][m] for c in g) and not any(c['keep'][m] and c['method_matches'][m][0] for c in g) for g in groups.values())) for m in ('recovery','pilot')}
    assert objects['pilot']['unmatched']<=objects['recovery']['unmatched']
    changed=[c for c in cases if c['keep']['recovery']!=c['keep']['pilot']]
    families=[]
    def iou(a,b):
        x,y,w,h=a;X,Y,W,H=b;inter=max(0,min(x+w,X+W)-max(x,X))*max(0,min(y+h,Y+H)-max(y,Y));return inter/max(1,w*h+W*H-inter)
    for photo in map(str,range(128,138)):
        row=dict(photo=photo)
        for n in (10,80):
            c=max((c for c in cases if c['photo']==photo),key=lambda c:iou(c['box'],idx[f'128-{n}']['box']))
            assert iou(c['box'],idx[f'128-{n}']['box'])>=.5
            assert c['keep']['pilot']==(n==10),(photo,n,c['key'])
            row[str(n)]=c['key']
        families.append(row)
    stats=dict(pairs=16,original_conflicts=12,new_cases=4,tests=1260,stable=1260,old_12_decisions_preserved=True,all_55_hits_preserved=True,unmatched_no_increase_per_photo=True,object_metrics=objects,changed_candidates=[c['key'] for c in changed],human_labels_added=1,additional_manual_hit=bool(idx["128-10"]["keep"]["pilot"]))
    assert idx['128-10']['keep']['pilot'] and not idx['128-10']['answers']
    save(exp/'correspondence-verification.json',stats)
    save(exp/'similar-position-family.json',families)
    body='<p>本頁附加於全圖資結果。實際改動的是模型前參照物件配對與完整輪廓取圖，全部照片重新偵測、重新推論。正式流程、模型、來源影像與人工答案均未修改。</p>'
    body+=full.table(['檢查','結果'],[['原有答案命中',f"55 → {summary['totals']['pilot']['answer_hits']}／100；逐一保住"],['答案框外疑似誤報候選',f"58 → {summary['totals']['pilot']['unmatched']}"],['同物件去重後框外警報',f"{objects['recovery']['unmatched']} → {objects['pilot']['unmatched']}"],['原有 12 組衝突','全部維持前輪判斷，1,080 次通過'],['本輪 4 處','每處 45 次，180 次通過'],['全圖資','11 張照片、1,345 個候選、100 處答案']])
    body+='<p class="warn">未對到答案仍計疑似誤報。#10 已由使用者確認為新增／掉落物件；新增人工真值獨立記錄，為維持比較口徑仍列入原答案框外計數；#82、#103 的「重看後仍自動排除」不等於人工已確認正常。模型分數是相似度差，不是機率。本批已用於開發，沒有獨立新影像或一般良品。</p>'
    body+='<h2>四處實際處置與證據</h2>'
    explanations={10:'使用者已確認有新增／掉落物件。原參照空白區被單獨拉伸對比，微小紋理被放大；現在兩圖共用待測明暗尺度，以外圍 4／8／12 像素重看。參照取中位分數、待測取最低分數，符合雙圖規則才保留。這不是三個單獨視窗都同意：其中一個參照視窗仍略偏像螺絲，故明列各次分數；最終採預先固定的中位數／最低分數規則。原先僅擴大背景的方案在其他相近照片仍會翻轉，未採用。',80:'外圍 4／8／16 像素都找到約向左 24、向下 2 像素的參照物件。改用配對位置實際重跑雙圖，兩邊皆像螺絲，依雙圖規則排除；不是僅憑單次外形相似度刪除。',82:'以形態開運算分離細邊框與局部黑塊，取得完整輪廓；外圍 4／8／12 像素三次雙圖推論，待測皆仍不像螺絲。維持自動排除，但保留使用者提出的複核疑點，未新增人工正常標籤。',103:'原框只截到物件下緣。先分離細線、找完整輪廓，再跑三種取圖；移動小框離開原框時，可透過影像輪廓找回物件。三種推論仍判待測不像螺絲，維持自動排除，人工疑點仍待確認。'}
    results={}
    for n in (10,80,82,103):
        key=f'128-{n}';c=idx[key];r=read(out/'runs/pilot/128/result.json');raw=next(c for c in r['candidates']+r['filtered_candidates'] if c['id']==n);pred=raw['classification'];meta=pred['correspondence_experiment'];results[key]=dict(classification=pred,user_feedback='做得不好' if n in (10,80) else '可以再猶豫一下',human_ground_truth='screw' if n==10 else None)
        body+=f'<article id="focus-{n}"><h3>#{n}：'+('保留人工複核警報' if c['keep']['pilot'] else '自動排除；仍可人工複核')+f'</h3><p>{explanations[n]}</p><p><a href="photo-128.html#case-{key}">查看整張照片與同類案例</a></p><img class="pair" src="images/{key}.jpg"><p>左：實際參照取圖；右：待測。紅框：原候選；藍框：本輪判斷物件。</p>'
        if meta.get('matches'):body+=full.table(['外圍像素','相似度','水平位移','垂直位移'],[[z['pad'],round(z['score'],4),z['dx'],z['dy']] for z in meta['matches']])
        for kind,title in [('shared_views','共用明暗尺度實際推論'),('contour_views','完整輪廓實際推論')]:
            if kind in meta:body+='<h4>'+title+'</h4>'+full.table(['外圍像素','參照分數','待測分數','雙圖結果'],[[p,round(v['paired_evidence']['reference']['screw_margin'],5),round(v['paired_evidence']['target']['screw_margin'],5),'保留' if v['filter_recommendation']=='keep' else '排除'] for p,v in meta[kind].items()])
        body+='<details><summary>查看真正送入模型的影像（已逐張核對 SHA-256）</summary>'
        for pad in ((4,8,12) if n!=80 else (12,)):
            body+=f'<p>外圍 {pad} 像素；左：參照，右：待測</p><img src="images/input-128-{n}-pad{pad}-reference.png" alt="模型參照輸入"><img src="images/input-128-{n}-pad{pad}-target.png" alt="模型待測輸入">'
        body+='</details>'
        body+='</article>'
    save(exp/'four-case-evidence.json',results)
    body+='<h2>全部 16 組擾動驗證</h2><p>比例 75%、90%、100%、110%、125%；水平及垂直各 −4／0／＋4 個檢測縮圖像素。原 12 組每組兩個起始框、90 次；新 4 處每處一個起始框、45 次，不重複計算。每次重新推論，核對物件、判斷、分數及輸入雜湊。固定影像物件庫，不代表亮度、旋轉或新影像也已驗證。</p>'
    body+='<h3>#10、#80 相近位置跨照片核對</h3><p>依原候選框重疊選出其他照片的對應候選，僅用於事後驗證，不送入模型規則。#10 同位置 10／10 保留，#80 同位置 10／10 排除；其餘照片未新增人工真值。</p>'+full.table(['照片','#10 同位置：保留','#80 同位置：排除'],[[r['photo'],*[f'<a href="photo-{r["photo"]}.html#case-{r[k]}">{r[k]}</a>' for k in ('10','80')]] for r in families])
    for rec in tests['pairs']:
        pair=rec['pair'];name=pair['kept']+'__'+pair['excluded'];body+=f'<details><summary>{pair["kept"]} ／ {pair["excluded"]}：{rec["stable_prediction_tests"]}／{rec["total_tests"]} 次相同</summary>'
        for key in dict.fromkeys(pair[k] for k in ('kept','excluded')):
            photo=key.split('-')[0];body+=f'<p><a href="photo-{photo}.html#case-{key}">{key} 完整照片與同類案例</a></p><img class="pair" src="images/{key}.jpg">'
        body+=f'<p><a href="../../perturbations/{name}.json">逐次完整推論證據</a></p>'+full.table(['起始框','比例','水平','垂直','同物件','同推論'],[[z['seed_id'],z['scale'],z['dx'],z['dy'],'是' if z['same_object'] else '否','是' if z['same_prediction'] else '否'] for z in rec['tests']])+'</details>'
    body+='<h2>全部判斷變更</h2>'+full.table(['候選','前輪','本輪','本輪答案'],[[f'<a href="photo-{c["photo"]}.html#case-{c["key"]}">{c["key"]}</a>','保留' if c['keep']['recovery'] else '排除','保留' if c['keep']['pilot'] else '排除',str(c['answers'])] for c in changed])
    body+='<p><a href="../../four-case-evidence.json">四處完整模型證據與使用者回饋</a> · <a href="../../correspondence-verification.json">全批回歸核對</a> · <a href="../../evidence-manifest.json">實驗程式及輸入雜湊</a></p>'
    (report/'correspondence.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>參照配對與完整輪廓複核</title><style>'+full.STYLE+'</style><main>'+full.NAV+'<h1>參照配對、完整輪廓與穩定性</h1>'+body+'</main></html>',encoding='utf-8')
    for f in report.glob('*.html'):f.write_text(f.read_text(encoding='utf-8').replace('</nav>','<a href="correspondence.html">附加：四處複核與穩定性</a></nav>',1),encoding='utf-8')
    class Parser(HTMLParser):
        def __init__(self):super().__init__();self.ids=[];self.links=[]
        def handle_starttag(self,tag,attrs):
            d=dict(attrs)
            if 'id' in d:self.ids.append(d['id'])
            self.links += [d[k] for k in ('src','href') if k in d]
    parsed={}
    for f in report.glob('*.html'):
        v=Parser();v.feed(f.read_text(encoding='utf-8'));assert len(v.ids)==len(set(v.ids));parsed[f.resolve()]=v
    count=0
    for f,v in parsed.items():
        for link in v.links:
            name,_,anchor=link.partition('#');dest=(f.parent/unquote(name)).resolve() if name else f;assert dest.exists(),(f,link)
            if anchor:assert anchor in parsed[dest].ids,(f,link)
            count+=1
    images=[f for f in (report/'images').iterdir() if f.suffix in ('.jpg','.png')]
    for f in images:
        with Image.open(f) as im:im.verify()
    assert read(exp/'actual-input-proof.json')['all_input_hashes_match']
    v=read(out/'verification.json');v.update(html_pages=len(parsed),links_checked=count,images_checked=len(images),actual_model_inputs_verified=20,correspondence=stats);save(out/'verification.json',v)
    print(json.dumps(stats,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
