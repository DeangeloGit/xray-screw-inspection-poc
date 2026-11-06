"""Complete corpus report and audited experiment appendix, without rerunning detection."""
import json,sys,re,shutil,os
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote
from PIL import Image
import numpy as np
import answered_batch_report as full
ROOT=Path(__file__).resolve().parents[2];EXP=ROOT/'workspace/dino-4r-hardnegative-20261106';RUN=EXP/'manual-normal';OUT=RUN/'final';PREV=ROOT/'workspace/dino-4r-blackblock-20261106/final'
read=full.read;save=full.save

def main():
    prepare_only='--prepare-only' in sys.argv;reuse='--reuse-full' in sys.argv
    meta=read(OUT/'report-meta.json');meta.update(answer_intro='<p>沿用前輪校正101處答案，沒有再移動或新增答案來替本輪加分。原55處及使用者確認的128-10、135-88逐一保護。使用者另確認128-3是正常結構變化，已另存人工紀錄，不改原始答案圖。</p>',comparison_description='原r3、前輪安全版與本輪皆使用相同校正101處答案。本輪重跑全部候選及雙圖推論；新增物件複核只救回原先排除的候選，既有保留與結構否決維持。基礎47＋65仍啟用；隔離補救庫為50螺絲＋73正常範例。')
    save(OUT/'report-meta.json',meta)
    save(OUT/'manual-feedback.json',{'128-10':dict(label='screw',text='使用者確認新增／掉落物件，應保留警報。'),'135-88':dict(label='screw',text='使用者確認線材旁有掉落螺絲。'),'128-3':dict(label='normal',text='使用者確認正常結構變化，應排除。')})
    if reuse:
        v=read(OUT/'verification.json');assert v['status']=='passed'
        assert all(full.sha(OUT/p)==h for p,h in v['result_sha256'].items())
    else:
        sys.argv=[sys.argv[0],str(OUT)];full.main()
    if prepare_only:return
    report=OUT/'report';images=report/'images';summary=read(OUT/'summary.json');cases=read(OUT/'cases.json');ci={c['key']:c for c in cases};scores=read(RUN/'all-scores.json');si={z['key']:z for z in scores};evaluation=read(RUN/'evaluation.json');e=evaluation['variants']['hardnegative_difference'];tests=read(RUN/'perturbation-results.json')
    assert summary['totals']['pilot']==dict(kept=128,answer_hits=69,unmatched=50)
    assert tests['total_tests']==1800 and tests['stable_object_tests']==tests['stable_prediction_tests']==1800
    previous_hits={(m['photo'],m['id']) for m in read(PREV/'answer-matches.json') if m['methods']['pilot']};hits={(m['photo'],m['id']) for m in read(OUT/'answer-matches.json') if m['methods']['pilot']};assert previous_hits<=hits
    assert ci['128-10']['keep']['pilot'] and ci['135-88']['keep']['pilot'] and not ci['128-3']['keep']['pilot']
    added={c['key'] for c in cases if c['keep']['pilot'] and not c['keep']['recovery']};assert added==set(e['added']) and len(added)==10
    assert all(r['metrics']['pilot']['unmatched']==r['metrics']['recovery']['unmatched'] for r in read(OUT/'rows.json'))
    fresh=0;score_checks=0
    for p in (OUT/'runs/pilot').glob('*/result.json'):
        result=read(p)
        for c in result['candidates']+result['filtered_candidates']:
            z=c['classification'];assert z['canonical_object']['fresh_inference'];fresh+=1
            ex=z.get('hardnegative_experiment')
            if ex:
                cached=si[f'{p.parent.name}-{c["id"]}'];assert ex['fresh_inference']
                for side in ('reference','target'):
                    assert ex['pair'][side]['input_sha256']==cached['pairs']['hardnegative'][side]['input_sha256']
                    assert abs(ex['pair'][side]['margin']-cached['pairs']['hardnegative'][side]['margin'])<1e-5
                assert ex['difference']==cached['difference'];score_checks+=1
    assert fresh==1345
    oldtests=read(ROOT/'workspace/dino-4r-correspondence-20261106/perturbation-results.json');oldmap={(z['pair']['kept'],z['pair']['excluded']):z for z in oldtests['pairs']}
    for t in tests['pairs']:
        key=(t['pair']['kept'],t['pair']['excluded'])
        if key in oldmap:assert t['expected']['verdict']==oldmap[key]['expected']['verdict']
    for p,h in read(RUN/'frozen-before-heldout.json').items():assert full.sha(p)==h
    plan=read(OUT/'plan.json')
    for group in ('hashes','experiment_hashes'):
        for p,h in plan[group].items():assert full.sha(p)==h
    bank=np.load(RUN/'experimental-bank.npz')['bank'];original=np.load(ROOT/'models/dino-paired-optimized-47-20261104-r3/paired-features.npz')['bank']
    assert np.array_equal(bank[:47],original[:47]) and np.array_equal(bank[50:115],original[47:])
    body='<p>本輪真正重跑全批偵測與雙圖推論，不是修改報告判斷。原55處、兩處使用者確認及前輪校正後全部59處逐一保住；新增10處大黑塊，69／101，答案框外警報維持50，各張照片均未增加。候選框數不等於螺絲顆數。</p>'
    body+='<p>評分沿革：原55／100經前輪定位修正及人工答案補齊，成為59／101；那4處是計分校正。本輪沿用同一101處答案，從59增加到69才是實際補抓的10處。原始圖資與標註不變，校正追溯連結列於本頁底部。</p>'
    body+='<p class="warn">仍是同批開發影像，沒有一般良品圖或外部獨立測試。新增範例及門檻只用128、131、132三張選定，再固定驗證其餘七張；不能宣稱新機種泛化。50個答案框外警報仍是疑似誤報口徑，不是逐一人工確認。</p>'
    body+='<h2>做了什麼</h2><p>基礎47螺絲＋65正常及既有雙圖流程維持。僅對原先「待測不像螺絲」、沒有結構否決的候選做補救。隔離補救庫為50螺絲＋73正常：保留全部原範例，加前輪3個大黑塊正例、7個良品參照既有結構，以及使用者確認正常的128-3。沒有使用七張驗證圖建立新範例。</p><p>補救條件：待測螺絲分數至少0.20、參照分數小於0；參照容許3像素位移，扣除周圍背景亮度差後，仍須有至少16像素連續新增深色區域，且占待測深色像素至少50%。判斷只讀影像與固定範例，不讀照片編號或答案。</p>'
    body+='<h2>固定條件下的對照</h2>'
    a=read(EXP/'evaluation.json')['variants'];v=evaluation['variants'];rows=[['前輪安全版',59,0,50,'基準'],['只加3個螺絲範例',a['positive_only']['all']['answer_hits'],a['positive_only']['all']['big_block_hits'],a['positive_only']['all']['unmatched'],'不採用'],['再加7個參照正常範例',a['hardnegative_only']['all']['answer_hits'],a['hardnegative_only']['all']['big_block_hits'],a['hardnegative_only']['all']['unmatched'],'不採用'],['再加人工確認128-3，尚未加門檻／差異複核',v['hardnegative_only']['all']['answer_hits'],v['hardnegative_only']['all']['big_block_hits'],v['hardnegative_only']['all']['unmatched'],'不採用'],['完整補救：範例＋信心＋差異複核',69,10,50,'僅4r實驗採用']]
    body+=full.table(['方案','命中／101','大黑塊／10','答案框外警報','用途'],rows)
    controls=read(RUN/'gate-controls.json')
    body+='<h2>改善原因不能混算</h2><p>七個參照正常範例將框外警報由75降至62；加人工正常128-3後，整批框外警報數仍是62，但它與大黑塊正例的分數拉開。僅做參照差異複核仍會放行12個新增框外警報；加入開發集選定的信心門檻後才維持50。本批單獨使用相同信心門檻也能得到相同10個補抓，因此沒有證據宣稱差異複核額外減少本批誤報；它是額外的新增物件限制，外部效果尚待驗證。</p>'
    body+='<p>凍結門檻後核對：10處大黑塊的待測分數最低0.279；其餘通過差異與參照條件、且原先未保留的候選最高0.162，固定門檻0.20位於兩者之間。這是本批分數間隔，不能當成未測影像雜訊或新機種的保證。</p>'
    body+='<h2>人工正常案例與需要抓回的大黑塊</h2>'
    for k in ('128-3','128-5'):
        z=si[k];prior=next(t for t in read(EXP/'all-scores.json') if t['key']==k)
        body+=f'<article><h3>{k}：'+('使用者確認正常，排除' if k=='128-3' else '答案中的大黑塊，保留')+f'</h3><a href="photo-128.html#case-{k}">完整照片／同類案例</a><img class="pair" src="images/{k}.jpg">'+full.table(['補救庫','參照分數','待測分數'],[['未加人工正常例',round(prior['pairs']['hardnegative']['reference']['margin'],4),round(prior['pairs']['hardnegative']['target']['margin'],4)],['加入人工正常例',round(z['pairs']['hardnegative']['reference']['margin'],4),round(z['pairs']['hardnegative']['target']['margin'],4)]])+'</article>'
    body+='<h2>全部新增正常範例</h2>'
    for item in read(RUN/'experiment-plan.json')['negative_examples']:
        k=item['key'];shutil.copy2(RUN/'negative-examples'/f'{k}.png',images/f'normal-{k}.png');body+=f'<article><h3>{k}／'+('待測' if item['side']=='target' else '參照')+f'</h3><p>{full.esc(item["authority"])}</p><img src="images/normal-{k}.png" style="width:224px"><p><a href="photo-{k.split("-")[0]}.html#case-{k}">完整參照／待測脈絡</a></p></article>'
    body+='<h2>全部10處大黑塊</h2>'
    for k in sorted(added):
        z=si[k];p=z['pairs']['hardnegative'];d=z['difference'];body+=f'<article><h3>{k}：保留（'+('開發' if z['photo'] in ('128','131','132') else '驗證')+f'）</h3><a href="photo-{z["photo"]}.html#case-{k}">完整照片／同類案例</a><img class="pair" src="images/{k}.jpg"><p>參照 {p["reference"]["margin"]:.4f}；待測 {p["target"]["margin"]:.4f}；新增連續區域 {d["area"]} 像素；新增深色占比 {d["share"]:.1%}。</p></article>'
    body+='<h2>框位移與縮放：全部1800次新推論</h2><p>原12組衝突、前輪4個使用者指定案例、10處新增補抓、135-88確認螺絲與128-3確認正常，共28組。縮放0.75／0.9／1／1.1／1.25，水平垂直位移各−4／0／4像素。1800／1800定位與判斷／分數／輸入雜湊一致；原12組及前輪4案例判斷維持。這是候選框擾動，不是對原始影像加入雜訊或重新拍攝。</p>'
    body+=full.table(['案例','定位一致','新推論一致','次數'],[[t['pair']['kept']+'／'+t['pair']['excluded'],t['stable_object_tests'],t['stable_prediction_tests'],t['total_tests']] for t in tests['pairs']])
    proof=read(RUN/'actual-input-proof.json');assert proof['all_input_hashes_match'] and len(proof['rows'])==22
    body+='<h2>模型實際看到的22張輸入圖</h2><p>以下重建輸入已逐張比對推論影像SHA-256；左參照、右待測，並非只展示較大的報告脈絡圖。</p>'
    for k in sorted(added|{'128-3'}):
        body+=f'<details><summary>{k}：實際模型輸入</summary><img src="images/actual-{k}-reference.png" style="width:224px"> <img src="images/actual-{k}-target.png" style="width:224px"></details>'
    body+='<p><a href="../../actual-input-proof.json">22張實際輸入影像核對</a></p>'
    correction=os.path.relpath(PREV/'report/blackblock.html',report).replace('\\','/')
    body+=f'<p><a href="{correction}">前輪101處評分校正與原始標註追溯</a> · <a href="../../evaluation.json">本輪全部評分</a> · <a href="../../training-selection.json">只用三張開發圖的門檻選擇</a> · <a href="../../frozen-before-heldout.json">驗證前固定檔案雜湊</a> · <a href="../../perturbation-results.json">1800次擾動明細</a> · <a href="../../all-scores.json">全部候選比較分數</a> · <a href="../../gate-controls.json">信心與差異分離對照</a> · <a href="../../../user-feedback.json">人工正常確認</a></p>'
    (report/'hardnegative.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>困難正常範例與參照差異複核</title><style>'+full.STYLE+'</style><main>'+full.NAV+'<h1>困難正常範例與參照差異複核</h1>'+body+'</main></html>',encoding='utf-8')
    def details(match):
        z=si[match.group(1)];p=z['pairs']['hardnegative'];d=z['difference'];text='<details><summary>本候選的困難正常範例與差異複核證據</summary>'
        text+='<p>既有保留優先維持；結構否決不繞過。以下是比較分數，實際是否補救以本候選完整判斷為準。</p>'+full.table(['比較庫','參照分數','待測分數'],[[name,round(v['reference']['margin'],4),round(v['target']['margin'],4)] for name,v in z['pairs'].items()])
        text+=f'<p>可進入補救：{z["eligible"]}；連續新增區域 {d["area"]} 像素；新增占比 {d["share"]:.1%}。完整條件：待測≥0.20、參照&lt;0、連續區域≥16、新增占比≥50%。</p></details>'
        return match.group(0).replace('</article>',text+'</article>')
    for p in report.glob('*.html'):
        text=p.read_text(encoding='utf-8').replace('</nav>','<a href="hardnegative.html">附加：困難正常範例與穩定性</a></nav>',1)
        text=text.replace('原始55／100與校正增加分開列於附加頁，校正不是模型新增命中。','前輪由55／100校正為59／101；本輪沿用同一101處答案，實際新增10處而達69／101。評分校正與本輪補抓分開列於附加頁。')
        text=re.sub(r'<article id="case-([^"]+)">[\s\S]*?</article>',details,text);p.write_text(text,encoding='utf-8')
    class Parser(HTMLParser):
        def __init__(self):super().__init__();self.ids=[];self.links=[]
        def handle_starttag(self,t,a):
            d=dict(a)
            if 'id' in d:self.ids.append(d['id'])
            self.links.extend(d[k] for k in ('href','src') if k in d)
    parsed={}
    for p in report.glob('*.html'):
        v=Parser();v.feed(p.read_text(encoding='utf-8'));assert len(v.ids)==len(set(v.ids));parsed[p.resolve()]=v
    n=0
    for p,v in parsed.items():
        for link in v.links:
            name,_,anchor=link.partition('#');dest=(p.parent/unquote(name)).resolve() if name else p;assert dest.exists(),(p,link)
            if anchor:assert anchor in parsed[dest].ids
            n+=1
    for pattern in ('photo-*.html','category-*.html'):assert sum(p.read_text(encoding='utf-8').count('本候選的困難正常範例與差異複核證據') for p in report.glob(pattern))==1345
    fs=[p for p in images.iterdir() if p.suffix in ('.jpg','.png')]
    for p in fs:
        with Image.open(p) as im:im.verify()
    verify=read(OUT/'verification.json');verify.update(html_pages=len(parsed),links_checked=n,images_checked=len(fs),fresh_candidates=fresh,fresh_rescue_pair_checks=score_checks,original55_preserved=True,both_confirmed_screws_preserved=True,all59_baseline_preserved=True,confirmed_normal128_3_excluded=True,unmatched_unchanged_per_photo=True,original_47_and_65_entries_identical=True,all_candidate_evidence_covered=True,stable_fresh_tests=1800,frozen_files_unchanged=True)
    verify['actual_model_input_images_verified']=22
    save(OUT/'verification.json',verify);print('FULL VERIFIED',len(parsed),n,len(fs),'fresh candidates',fresh,'rescue pairs',score_checks)
if __name__=='__main__':main()
