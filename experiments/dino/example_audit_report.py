"""Full corpus delivery plus all-47 example review and all-32 miss diagnosis."""
import sys,shutil,re
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote
import numpy as np
from PIL import Image
import answered_batch_report as full
ROOT=Path(__file__).resolve().parents[2];EXP=ROOT/'workspace/dino-4r-example-audit-20261106';OUT=EXP/'final';BASE=ROOT/'workspace/dino-4r-visible-screw-20261106/v3/final'
read=full.read;save=full.save;esc=full.esc
def main():
    if '--reuse-full' not in sys.argv:
        sys.argv=[sys.argv[0],str(OUT)];full.main()
    report=OUT/'report';images=report/'images';summary=read(OUT/'summary.json');cases=read(OUT/'cases.json');ci={c['key']:c for c in cases};old=read(BASE/'cases.json');oldci={c['key']:c for c in old}
    assert summary['totals']['pilot']==dict(kept=138,answer_hits=79,unmatched=50)
    assert len(cases)==2332 and summary['photos']==11 and summary['answer_marks']==101
    oldhits={(m['photo'],m['id']) for m in read(BASE/'answer-matches.json') if m['methods']['pilot']};hits={(m['photo'],m['id']) for m in read(OUT/'answer-matches.json') if m['methods']['pilot']};assert len(oldhits)==69 and oldhits<=hits
    new=[c for c in cases if c['keep']['pilot'] and not oldci[c['key']]['keep']['pilot']];assert len(new)==10 and all(c['answers']==[4] for c in new)
    assert all(r['metrics']['pilot']['unmatched']==r['metrics']['recovery']['unmatched'] for r in read(OUT/'rows.json'))
    assert full.sha(OUT/'answers.json')==full.sha(BASE/'answers.json')
    unchanged=0;raw={};proof=read(EXP/'board-proof.json');assert proof['total_tests']==proof['stable_tests']==450 and proof['synthetic_control_failures']==0 and len(proof['controls'])==40 and len(proof['actual_inputs'])==80
    features={f'{z["photo"]}-{z["id"]}':z for z in read(EXP/'all-crop-bank-scores.json')};assert len(features)==1345
    for p in (OUT/'runs/pilot').glob('*/result.json'):
        r=read(p);oldr=read(BASE/'runs/pilot'/p.parent.name/'result.json');idx={c['id']:c for c in oldr['candidates']+oldr['filtered_candidates']}
        for c in r['candidates']+r['filtered_candidates']:
            key=f'{p.parent.name}-{c["id"]}';raw[key]=c;previous=idx[c['id']];assert full.geom(c)==full.geom(previous)
            if c['classification']==previous['classification']:unchanged+=1
            else:
                assert c['classification']['example_crop_review']['previous']==previous['classification']
                for v in c['classification']['example_crop_review']['views']:
                    for side in ('reference','target'):
                        expected=features[key]['variants'][f'letterbox-{v["pad"]}-allbank'][side];assert v[side]['input_sha256']==expected['input_sha256'];assert abs(v[side]['screw_margin']-expected['margin'])<1e-5
    assert unchanged==2322
    assert ci['128-10']['keep']['pilot'] and ci['135-88']['keep']['pilot'] and not ci['128-3']['keep']['pilot'] and not ci['128-5']['keep']['pilot']
    inv=read(EXP/'positive-review.json');miss=read(EXP/'remaining32-diagnosis.json');assert len(inv)==47 and len(miss)==32
    for p in (EXP/'bank-review').glob('S*.png'):shutil.copy2(p,images/p.name)
    for p in (EXP/'proof-images').glob('*.png'):shutil.copy2(p,images/p.name)
    for name in ('board-input-diagnostic.jpg','positives-01-16.jpg','positives-17-32.jpg','positives-33-47.jpg','misses-01-16.jpg','misses-17-32.jpg'):shutil.copy2(EXP/name,images/name)
    ablation=[]
    basekeep={c['key'] for c in old if c['keep']['pilot']}
    for mode in ('center','letterbox'):
        for bank in ('old','allbank'):
            added=[]
            for key,z in features.items():
                c=oldci[key];meta=c.get('correspondence_experiment') or {}
                if z['baseline_keep'] or c['rules'] or meta.get('recheck')!='complete_contour' or c['paired_evidence']['target']['label']!='non_screw':continue
                views=[z['variants'][f'{mode}-{pad}-{bank}'] for pad in (2,4,8,12)]
                if np.mean([v['target']['margin'] for v in views])>=0 and all(v['reference']['margin']<0 for v in views):added.append(key)
            hs={(oldci[k]['photo'],a) for k in basekeep|set(added) for a in oldci[k]['answers']};outside=[k for k in added if not oldci[k]['answers']];ablation.append(dict(crop=mode,bank=bank,hits=len(hs),unmatched=50+len(outside),added=added))
    save(EXP/'controlled-2x2.json',ablation)
    body='<p>本輪實際全批重新檢測為 <b>79／101</b>；原69處全部保住，新增10處為各張答案4。答案框外警報仍50，各張皆未增加；這50是待人工核對警報，不宣稱全部已確認為誤報。保留138個候選框不等於138顆螺絲。</p><p>所有2332候選與11張圖均收錄。2322個候選的完整分類內容完全相同；只改10個候選的實際判斷。原55處、兩處人工確認、10處B均保住；128正常黑塊#3及遮擋物本體#5仍排除。答案位置、配對算法、正式程式、模型與設定均未修改。</p>'
    body+='<p class="warn">本批是已參與開發的10張不良品及1張參照自比，沒有一般良品或獨立新拍圖。這是同批回歸，不代表已證明跨批次誤報不增加。候選框位移測試也不等於重新拍攝、旋轉或雜訊測試。</p>'
    body+='<h2>1．參考螺絲例需要修正什麼</h2><p>47張均逐張審視來源圖與模型實際輸入；目前沒有證據把任何一張螺絲正例直接改標成正常。問題首先在呈現方式：S19的中央裁切已切掉右側桿端；S21、S26的桿端／頭部靠近輸入邊緣；S23等長方形來源丟失部分上下文。S16、S18、S23、S39、S40帶明顯線材或板邊；S37、S38、S41與深色結構混在一起，需乾淨螺絲輪廓與相同背景正常圖作對照。</p><p>本輪修正是把來源補成方形後再抽特徵，保留完整長寬比例；47張螺絲與65張正常例一律同樣處理，沒有新增正例、沒有改標籤、沒有重訓ONNX權重。原庫及B局部50＋77分支保留；新的47＋65庫只用於完整輪廓補救。白邊可能改變相似度，因此正常例也必須同步處理並做控制測試。</p><p>23張偏圓頭／正面或斜面，24張偏側面／頭桿輪廓；這是助理目視分類，不是「圓頭例太多所以刪掉」的依據。現有47張沒有足夠明確的B半圓部位代表，前輪已另建3張B局部例，不能用整塊黑影取代。</p>'
    body+='<h2>2．取圖與範例分開比較</h2><p>以下四組使用同一批候選、同一完整輪廓範圍、相同四範圍平均及既有排除規則；只改取圖與範例預處理。這不是只改報告分類。</p>'
    body+=full.table(['待測／參照取圖','47＋65範例處理','命中／101','答案框外警報'],[['中央裁切' if z['crop']=='center' else '保留比例補方形','原處理' if z['bank']=='old' else '兩類都保留比例',z['hits'],z['unmatched']] for z in ablation])
    body+='<p>只改範例沒有補回；只改取圖會多2個框外警報；兩者一起改，配合既有結構／參照配對排除，才在本批做到79／101、框外50。不能把分數上升直接說成學會螺絲，也不能把相似度分數稱作機率。</p><p>補救僅適用於已做完整輪廓複核、待測仍判不像螺絲且無結構排除規則的候選。每次對2、4、8、12像素背景範圍各跑參照／待測DINO；待測四分數平均≥0，且四個參照分數皆&lt;0才保留。原有警報與參照物件移位排除不被這條規則覆蓋。執行判斷不讀照片編號或答案。</p>'
    body+='<h2>3．剩下32處的逐處診斷</h2><p>10處板上案例已補回；20處深色喇叭區、2處小圓頭混合背景依指示暫緩。32處之中，10處沒有能對到答案中心的候選，全部在暫緩的喇叭區；其餘22處已有候選。判斷「有框」仍不代表框內清楚露出螺絲。</p><p>板上10處的舊差分框只包到局部，完整輪廓複核已把它擴到約20×15像素，仍然漏抓。參照是板上既有黑色元件，待測多出的螺絲與它們接在一起；直接用小碎片、或中央裁掉兩側／頭桿，會讓DINO更像在比板上元件。不能再只用「碎裂」解釋，也不能把整片黑色都當螺絲。</p><details><summary>參照、待測、差值與新增像素診斷（差值不是模型輸入）</summary><img src="images/board-input-diagnostic.jpg"></details>'
    for m in miss:
        recovered=(m['photo'],m['answer']) in hits;links='、'.join(f'<a href="photo-{m["photo"]}.html#case-{c["key"]}">#{c["key"]}</a>' for c in m['candidates']) or '無符合中心配對的候選'
        body+=f'<details id="miss-{m["photo"]}-{m["answer"]}"><summary>{m["photo"]}／答案{m["answer"]}：'+('本輪補回' if recovered else '暫緩')+f'</summary><p>{esc(m["diagnosis"])}。候選數{m["candidate_count"]}；{links}。</p><img src="images/{m["photo"]}-mark-{m["answer"]}.jpg"><p><a href="photo-{m["photo"]}.html">返回完整照片與同類案例</a></p></details>'
    body+='<h2>4．新補回10處的真正模型輸入</h2>'
    for c in new:
        ex=raw[c['key']]['classification']['example_crop_review'];p=c['paired_evidence'];body+=f'<article><h3>{c["photo"]}／候選#{c["id"]}：答案4</h3><p>參照平均{p["reference"]["screw_margin"]:.4f}；待測平均{p["target"]["screw_margin"]:.4f}。<a href="photo-{c["photo"]}.html#case-{c["key"]}">完整照片／同類案例</a></p><img class="pair" src="images/{c["key"]}.jpg">'
        body+=full.table(['背景範圍','參照分數','待測分數'],[[v['pad'],f'{v["reference"]["screw_margin"]:.4f}',f'{v["target"]["screw_margin"]:.4f}'] for v in ex['views']])
        for v in ex['views']:body+=f'<details><summary>範圍{v["pad"]}，真正輸入：左參照、右待測</summary><img width="224" src="images/board-{c["photo"]}-pad{v["pad"]}-reference.png"> <img width="224" src="images/board-{c["photo"]}-pad{v["pad"]}-target.png"></details>'
        body+='</article>'
    body+='<h2>5．穩定性與黑塊控制</h2><p>新10處，各做5種縮放（0.75、0.9、1、1.1、1.25）×水平／垂直各−4、0、4像素，共450次。每次由影像物件重新對應，再跑DINO，450次判斷與實際輸入雜湊一致。這驗證候選框變動，不代表影像本身縮放後也已驗證。</p><p>另40次合成診斷：每張把實際物件範圍還原成參照一次，再各用0、0.08、0.14三種深度的純色矩形取代。新的四範圍分類器40次皆不保留。這檢查只剩黑塊是否也被當螺絲；不是新拍圖，也不是重新跑整張候選生成。</p>'
    for photo in map(str,range(128,138)):
        body+=f'<details><summary>{photo}：左原圖，右還原參照／純黑矩形；兩種皆不保留</summary><img src="images/board-{photo}-restore_reference.png"><img src="images/board-{photo}-solid_dark_rectangle.png"></details>'
    body+='<p>原12組衝突與B局部分支本輪沒有改寫判斷，2322個完整分類紀錄逐項一致；不把前輪測試冒充本輪重跑。<a href="../../../dino-4r-visible-screw-20261106/v3/final/report/visible-screw.html">前輪B局部、移除B與黑塊變化證據</a>另列。</p>'
    body+='<h2>6．47張逐例審視</h2><p>每例依序為來源、原實際輸入、保留比例的新輸入。下面的風險與外觀分類均由助理審視，未冒稱人工重新標籤。原始檔與原特徵庫不覆寫。</p>'
    for e in inv:
        n=e['index'];body+=f'<details id="example-{n}"><summary>S{n:02d}：{esc(e["appearance"])}／{e["width"]}×{e["height"]}</summary><p>{esc(e["id"])}。{esc(e["label_review"])}；{esc(e["action"])}。</p><p>'+esc('；'.join(e['concerns']))+f'</p><p>中央裁切保留來源面積約{e["center_crop_area_fraction"]:.0%}，不等於螺絲本體保留率。</p><div style="display:flex;gap:12px;flex-wrap:wrap"><img style="width:224px;object-fit:contain" src="images/S{n:02d}-source.png"><img width="224" src="images/S{n:02d}-input.png"><img width="224" src="images/S{n:02d}-letterbox.png"></div></details>'
    body+='<h2>7．後續範例修正建議</h2><p>先保留原標籤，修正完整輪廓與比例；下一批收集「螺絲清楚部位＋同位置無螺絲」配對，分開整支、遮擋露出部位與圓頭。帶線材／大元件的正例要有相同背景正常反例，不能直接把背景當成螺絲。用不同拍攝批次與一般良品驗收後，才考慮正式替換；本輪仍只在4r。</p>'
    body+='<p><a href="../../positive-review.json">47例審視紀錄</a> · <a href="../../remaining32-diagnosis.json">32處診斷與原分數</a> · <a href="../../controlled-2x2.json">控制實驗</a> · <a href="../../gated-ablation-summary.json">全部範圍整合試驗</a> · <a href="../../board-proof.json">450次與40次控制證據</a> · <a href="../verification.json">全圖資完整性核對</a></p>'
    (report/'example-audit.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>範例與32處漏抓診斷</title><style>'+full.STYLE+'</style><main>'+full.NAV+'<h1>附加：範例與32處漏抓診斷</h1>'+body+'</main></html>',encoding='utf8')
    for p in report.glob('*.html'):
        text=p.read_text(encoding='utf8')
        if 'href="example-audit.html"' not in text:text=text.replace('</nav>','<a href="example-audit.html">附加：47範例／32處診斷</a></nav>',1)
        text=text.replace('原始55／100與校正增加分開列於附加頁，校正不是模型新增命中。','本輪沿用前輪101處答案及B部位定位，答案與評分規則未變；原69處全保住，新增10處來自實際重新推論。')
        if p.name=='index.html':
            text=re.sub(r'<p class="box">本頁採校正後[\s\S]*?</p>','<p class="box">本次使用101處答案，包括使用者確認的兩處螺絲；線材案例已在原答案中，不重複計數。答案位置與評分規則未更改，人工與助理核對來源詳見附加頁。</p>',text)
        p.write_text(text,encoding='utf8')
    class Parser(HTMLParser):
        def __init__(self):super().__init__();self.ids=[];self.links=[]
        def handle_starttag(self,t,a):
            d=dict(a)
            if 'id' in d:self.ids.append(d['id'])
            self.links.extend(d[k] for k in ('href','src') if k in d)
    parsed={}
    for p in report.glob('*.html'):
        parser=Parser();parser.feed(p.read_text(encoding='utf8'));assert len(parser.ids)==len(set(parser.ids));parsed[p.resolve()]=parser
    links=0
    for p,parser in parsed.items():
        for link in parser.links:
            name,_,anchor=link.partition('#');dest=(p.parent/unquote(name)).resolve() if name else p;assert dest.exists(),(p,link)
            if anchor:assert anchor in parsed[dest].ids,(p,link)
            links+=1
    fs=list(images.glob('*.jpg'))+list(images.glob('*.png'))
    for p in fs:
        with Image.open(p) as im:im.verify()
    plan=read(OUT/'plan.json')
    for group in ('hashes','experiment_hashes'):assert all(full.sha(p)==h for p,h in plan[group].items())
    v=read(OUT/'verification.json');v.update(html_pages=len(parsed),links_checked=links,images_checked=len(fs),all69_preserved=True,original55_and_two_confirmed_preserved=True,all10_B_preserved=True,unmatched_unchanged_each_photo=True,unchanged_classification_count=unchanged,actual_changed_classifications=10,example_audit_count=47,miss_diagnosis_count=32,remaining_deferred=22,unchanged_answers=True,new_candidate_window_tests=450,new_synthetic_controls=40,synthetic_control_failures=0,actual_input_hashes_verified=80,normal_black128_3_excluded=True,opaque_black128_5_excluded=True,independent_validation=False)
    save(OUT/'verification.json',v);print('FULL REPORT VERIFIED',len(parsed),'pages',links,'links',len(fs),'images')
if __name__=='__main__':main()
