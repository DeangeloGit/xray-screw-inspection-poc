"""Full actual results for a validated integrated bank, with attribution appendix."""
from integrated_bank_probe import ROOT,OUT as EXP,PRIOR,CURRENT,NEW,OLD,read,save
import argparse,copy,hashlib,shutil
from collections import Counter
import numpy as np,cv2
from PIL import Image,ImageDraw
import answered_batch_report as common
import connector_report as verifier
from result_columns import columns
TYPES=common.TYPES;esc=common.esc;table=common.table
NAV='<nav><a href="index.html">完整結果</a><a href="machine-MPT10.html">MPT10</a><a href="answers.html">全部答案</a><a href="comparison.html">版本比較</a><a href="attribution.html">新增警報與範例原因</a></nav>'

def page(report,name,title,body):
    (report/name).write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>'+common.STYLE+'</style><main>'+NAV+'<h1>'+esc(title)+'</h1>'+body+'</main></html>',encoding='utf8')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--arm',required=True);a=ap.parse_args();OUT=EXP/'final';report=OUT/'report';images=report/'images';images.mkdir(parents=True,exist_ok=True)
    plan=copy.deepcopy(read(CURRENT/'plan.json'));answers=read(CURRENT/'answers.json');oldcases={c['key']:c for c in read(CURRENT/'cases.json')};oldrows={r['key']:r for r in read(CURRENT/'rows.json')};proof=read(EXP/f'stability-{a.arm}.json')
    assert proof['query_passed'],'Proposal stability failed'
    required=[g for g in proof['groups'] if g['kind'] in ('original_conflict','normal_connector')]
    assert all(g['expected']=='keep' for g in required if g.get('answers')),'Annotated conflict must remain a screw'
    assert len(required)==14 and all(g['image_pass']==g['image_total'] for g in required),'Required conflict/connector stability failed'
    scale_diagnosis=read(EXP/'human88-scale-diagnosis.json');extra_failures=[t for t in proof['image_resample_tests'] if not t['pass_test']]
    for t in extra_failures:
        old=next(r for r in scale_diagnosis if r['arm']=='original' and r['photo']==t['photo'] and r['id']==t['seed'] and r['scale']==t['scale'])
        assert old['final']['filter_recommendation']==t['verdict']!=t['expected']
        assert old['final']['paired_evidence']['target']==t['paired_evidence']['target'],'Extra scale failure differs from baseline'
    assert all(g['query_pass']==g['query_total'] for g in proof['groups'])
    plan['integrated_bank_arm']=a.arm;plan['scope']='All100 frozen proposals and registered images; complete classification branches re-executed with integrated MAIN bank, fixed B/secondary-review criteria/terminal policies, with experimental mixed-contour branch repair. Development regression, not unseen scans.'
    for p in [EXP/f'{a.arm}-bank.npz',EXP/f'stability-{a.arm}.json']+[ROOT/'experiments/dino'/f for f in ('integrated_bank_build.py','integrated_bank_probe.py','integrated_bank_replay.py','integrated_bank_policy.py','integrated_bank_proof.py','integrated_bank_scale_probe.py','integrated_bank_report.py','integrated_bank_export.py')]:plan['hashes'][str(p)]=common.sha(p)
    build=read(EXP/'bank-build-verification.json');assert build['status']=='passed' and build['arm']==a.arm
    plan['hashes'].update(build['source_hashes'])
    for p in (EXP/f'{a.arm}-recipe.json',EXP/'bank-build-verification.json',EXP/'human-unconfirmed-128-7.json',EXP/'human88-scale-diagnosis.json',NEW/'collection/manifest.json'):plan['hashes'][str(p)]=common.sha(p)
    shutil.copytree(CURRENT/'report/images',images,dirs_exist_ok=True);cases=[];rows=[];markrows=[];part_checks=[]
    for item in plan['items']:
        key=item['key'];rr=read(EXP/'replay'/key/f'{a.arm}.json');assert rr['main_bank_sha256']==common.sha(EXP/f'{a.arm}-bank.npz');base=read(PRIOR/'runs'/key/'result.json');cs=sorted(base['candidates']+base['filtered_candidates'],key=lambda c:c['id']);ref,tar=[Image.open(PRIOR/'runs'/key/f'{n}.png').convert('RGB') for n in ('reference','aligned')];flow=np.zeros((ref.height,ref.width,2),np.float32)
        for z in base['local_alignment']:
            x,y,X,Y=z['bbox'];flow[y:Y,x:X]=[z['dx'],z['dy']]
        flow=cv2.GaussianBlur(flow,(0,0),12);cc=[]
        for c in cs:
            p=rr['predictions'][str(c['id'])];c['classification']=p;poly=common.native(c,base,flow);yes,edge=common.matches(poly,answers.get(key,{}).get('marks',[]));assert yes==rr['answer_matches'][str(c['id'])]
            old=oldcases[f'{key}-{c["id"]}'];rules=p.get('overkill_pilot',{}).get('rules',[])+p.get('r4_experiment',{}).get('rules',[]);keep=p['filter_recommendation']=='keep';pair=p['paired_evidence'];assert keep==(pair['target']['label']=='screw' and pair['reference']['label']!='screw' and not rules)
            cat=next((cat for rule,cat in [('wire','wire'),('r4_wire_motion','wire'),('border','edge'),('corner','edge'),('component','component'),('r4_part_boundary','edge' if max(c['w'],c['h'])<=9 else 'component'),('r4_weak_object_extent','component')] if rule in rules),'unknown')
            z=dict(key=old['key'],photo=key,id=c['id'],box=list(common.geom(c)),canonical_box=p['canonical_object']['box'],machine='MPT10',label=item['label'],is_reference=item['is_reference'],keep=keep,baseline_keep=old['keep'],answers=yes,baseline_answers=old['answers'],edge_answers=edge,category=cat,rules=rules,paired_evidence=pair,reason=p['decision_reason'],source_polygon=poly.tolist());cc.append(z)
            # Re-render all paired images, so changed reference offsets/boxes are real.
            x,y,w,h=z['box'];side=max(120,w+48,h+48);x0=int(max(0,min(ref.width-side,x+w/2-side/2)));y0=int(max(0,min(ref.height-side,y+h/2-side/2)));canvas=Image.new('RGB',(800,400))
            for j,im in enumerate((ref,tar)):
                dx,dy=p.get('correspondence_experiment',{}).get('reference_offset',[0,0]) if j==0 else (0,0);v=im.crop((x0+dx,y0+dy,x0+dx+side,y0+dy+side));d=ImageDraw.Draw(v);d.rectangle((x-x0-dx,y-y0-dy,x+w-x0-dx,y+h-y0-dy),outline='#eb2346');cx,cy,cw,ch=z['canonical_box'];d.rectangle((cx-x0,cy-y0,cx+cw-x0,cy+ch-y0),outline='#00a5dd');canvas.paste(v.resize((400,400)),(j*400,0))
            canvas.save(images/f'{z["key"]}.jpg',quality=88)
        if item['label']=='NG':
            previous=read(CURRENT/'runs'/key/'result.json')
            for c in previous['candidates']:
                if 'visible_part_experiment' not in c['classification']:continue
                p=rr['predictions'][str(c['id'])];part_checks.append(dict(photo=key,id=c['id'],passed=p['filter_recommendation']=='keep' and p['canonical_object']['box']==c['classification']['canonical_object']['box'] and p.get('visible_part_experiment',{}).get('occluder_pixels_in_input')==0))
        hits=sorted({x for c in cc if c['keep'] for x in c['answers']});assert hits==rr['hits'];old=oldrows[key];row=dict(**item,candidates=len(cc),kept=sum(c['keep'] for c in cc),excluded=sum(not c['keep'] for c in cc),hits=hits,baseline_hits=old['hits'],baseline_kept=old['kept'],answer_count=len(answers.get(key,{}).get('marks',[])),unmatched=rr['unmatched'],baseline_unmatched=old['unmatched'],new_unmatched=rr['new_unmatched'],new_alerts=rr['new_alerts'],alignment_warning=base['alignment_warning'],structure_changes=base['structure_changes']);rows.append(row);cases+=cc
        base['candidates']=[c for c in cs if c['classification']['filter_recommendation']=='keep'];base['filtered_candidates']=[c for c in cs if c['classification']['filter_recommendation']!='keep'];base.update(proposal_count=row['kept'],filtered_count=row['excluded'],high_count=sum(c['priority']=='high' for c in base['candidates']),wire_review_count=sum(bool(c.get('wire_review')) for c in base['candidates']),experimental_policy='4r-integrated-main-bank-'+a.arm);base['review_count']=row['kept']-base['high_count'];save(OUT/'runs'/key/'result.json',base)
        overlay=Image.open(PRIOR/'runs'/key/'source.png').convert('RGB');d=ImageDraw.Draw(overlay)
        for c in cc:
            if c['keep']:
                pts=[tuple(q) for q in (np.asarray(c['source_polygon'])*base['preview_scale']).tolist()];d.line(pts+[pts[0]],fill='#ed3030',width=2);d.text(pts[0],str(c['id']),fill='#ed3030')
        overlay.thumbnail((1400,1400));overlay.save(images/f'{key}-overlay.jpg',quality=90)
        for m in answers.get(key,{}).get('marks',[]):markrows.append(dict(photo=key,id=m['id'],polygon=m['polygon'],hit=m['id'] in hits,candidates=[c['key'] for c in cc if c['keep'] and m['id'] in c['answers']]))
        print('REPORT',key,row['kept'],len(hits),flush=True)
    bad=[r for r in rows if r['label']=='NG'];good=[r for r in rows if r['label']=='OK' and not r['is_reference']];refs=[r for r in rows if r['is_reference']];original={(r['key'],i) for r in oldrows.values() for i in r['hits']};actual={(m['photo'],m['id']) for m in markrows if m['hit']};lost=sorted(original-actual)
    summary=dict(photos=len(rows),candidates=len(cases),good_photos=len(good),bad_photos=len(bad),reference_self_photos=len(refs),answers=len(markrows),answer_hits=len(actual),original79_preserved=not lost,lost_original_answers=lost,good_alarms=sum(r['kept'] for r in good),NG_unmatched=sum(r['unmatched'] for r in bad),self_alarms=sum(r['kept'] for r in refs),new_NG_unmatched=[f'{r["key"]}-{i}' for r in bad for i in r['new_unmatched']],new_good_alerts=[f'{r["key"]}-{i}' for r in good for i in r['new_alerts']],baseline_NG_unmatched=sum(r['unmatched'] for r in oldrows.values() if r['label']=='NG'),baseline_good_alarms=sum(r['kept'] for r in oldrows.values() if r['label']=='OK' and not r['is_reference']),arm=a.arm,stability_passed=proof['query_passed'] and proof['image_resample_passed'],required_conflict_connector_stability_passed=True,proposal_tests_passed=proof['query_passed'],extra_image_scale_failures=[dict(photo=t['photo'],id=t['seed'],scale=t['scale'],original_also_failed=True) for t in extra_failures],production_changed=False,independent_new_defect_images=0)
    summary['acceptance_scope']='Original-size full100 regression and required12 conflict/connector stability. Extra human135#88 125% image scale fails identically in original and new; overall stability_passed remains false.'
    summary['human_confirmed_screws_preserved']=all(next(c for c in cases if c['key']==k)['keep'] for k in ('ng-128-10','ng-135-88'));summary['pair22_40_normal']=all(not next(c for c in cases if c['key']==f'ng-128-{i}')['keep'] for i in (22,40));summary['acceptance_passed']=not lost and not summary['new_NG_unmatched'] and not summary['new_good_alerts'] and summary['self_alarms']==0 and summary['human_confirmed_screws_preserved'] and summary['pair22_40_normal'];assert summary['acceptance_passed'],summary
    summary['original_visible_B_parts_preserved']=len(part_checks)==10 and all(z['passed'] for z in part_checks);assert summary['original_visible_B_parts_preserved'];save(OUT/'visible-part-protection.json',part_checks)
    for n,v in [('cases',cases),('rows',rows),('answers',answers),('answer-matches',markrows),('summary',summary),('plan',plan)]:save(OUT/f'{n}.json',v)
    import integrated_bank_export
    integrated_bank_export.main()
    def card(c):
        human={'ng-128-7':'人工回覆：目前無法判定；未作正例或正常例。','ng-128-22':'人工已確認：正常結構，應排除。','ng-128-40':'人工已確認：正常結構，應排除。','ng-128-10':'人工已確認：新增／掉落物件，應保留。','ng-135-88':'人工已確認：掉落螺絲，應保留。'}.get(c['key'],'')
        p=c['paired_evidence'];label='保留警報' if c['keep'] else '排除';ans='答案'+','.join(map(str,c['answers'])) if c['answers'] else '未對到答案' if c['label']=='NG' else '來源標為良品；警報待核對'
        return f'<article id="case-{c["key"]}"><h3>{c["photo"]}／候選#{c["id"]}：{label}</h3><p>{TYPES[c["category"]]} · '+('待確認（未人工分類）' if c['category']=='unknown' else '規則自動推測')+f' · {ans}</p><p>{human}</p><p><a href="photo-{c["photo"]}.html#case-{c["key"]}">查看照片</a> · <a href="category-{c["category"]}.html#case-{c["key"]}">查看同類案例</a> · <a href="machine-MPT10.html">返回機種</a></p><p>左：參照圖　右：待測圖</p><img loading="lazy" class="pair" src="images/{c["key"]}.jpg" alt="參照與待測"><p>參照：'+('像螺絲' if p['reference']['label']=='screw' else '不像螺絲')+'；待測：'+('像螺絲' if p['target']['label']=='screw' else '不像螺絲')+f'。{esc(c["reason"])}</p><details><summary>判斷依據與實際範圍</summary><p>原候選紅框{c["box"]}，實際物件藍框{c["canonical_box"]}；參照{p["reference"]["screw_margin"]:+.4f}，待測{p["target"]["screw_margin"]:+.4f}。分數不是機率。規則：{esc(", ".join(c["rules"]) or "無")}。</p></details></article>'
    def photos(rs):return table(['照片','分類','保留／排除候選','答案命中','警報核對'],[[f'<a href="photo-{r["key"]}.html">{esc(r["name"])}</a>','參照自比' if r['is_reference'] else '良品' if r['label']=='OK' else '不良品',f'{r["kept"]}／{r["excluded"]}',f'{len(r["hits"])}/{r["answer_count"]}' if r['label']=='NG' else '不適用',f'未對答案{r["unmatched"]}' if r['label']=='NG' else f'警報{r["kept"]}'] for r in rs])
    note='<p class="warn">本次是同批開發回歸，沒有新的獨立不良圖，部分良品也與既有正常例來源重疊。沿用對位與全部候選，重新執行完整分類分支；相同輸入可重用DINO特徵，沒有套用舊判斷。正式流程未變。未對答案警報不等同全部已確認誤報，候選框數不等於螺絲顆數。</p>'
    page(report,'index.html','4r｜整合參考庫・100張全圖資結果',note+f'<p>100張、{len(cases)}候選；答案命中{len(actual)}／101，原79處與兩處人工確認皆保住。一般良品警報{summary["good_alarms"]}，NG未對答案{summary["NG_unmatched"]}，參照自比{summary["self_alarms"]}。</p><p class="warn">已知限制：135 #88放大125%時原版與本版都漏判；原尺寸與框擾動保留。12組衝突與#22／#40測試通過，不能宣稱所有影像縮放皆穩定。<a href="attribution.html#scale-limit">查看完整測試</a></p><p><a href="machine-MPT10.html">依機種 → 誤報類型 → 相近位置查看</a></p><h2 id="good">良品完整結果</h2>'+photos(good)+'<h2 id="bad">不良品完整結果</h2>'+photos(bad)+'<h2>參照圖自比</h2>'+photos(refs))
    counts=Counter(c['category'] for c in cases);page(report,'machine-MPT10.html','MPT10 → 誤報類型',table(['類型','候選數','人工確認分類'],[[f'<a href="category-{k}.html">{v}</a>',counts[k],0] for k,v in TYPES.items()])+'<p>本批實際只有MPT10，其他機種未混入。自動外觀分類不是人工判定。</p>'+photos(rows))
    for kind,label in TYPES.items():
        selected=[c for c in cases if c['category']==kind];body='<p><a href="machine-MPT10.html">返回MPT10</a></p>'
        for i,g in enumerate(common.grouped(selected),1):body+=f'<section><h2>相近位置{i}／{len(g)}候選</h2>'+columns(g,card,lambda c:c['keep'],True)+'</section>'
        page(report,f'category-{kind}.html','MPT10 → '+label+' → 相近位置',body if selected else body+'<p>0 個案例。</p>')
    for r in rows:
        key=r['key'];cc=[c for c in cases if c['photo']==key];ct=Counter(c['category'] for c in cc);body=f'<p><a href="machine-MPT10.html">返回此機種</a> · <a href="category-unknown.html">查看同類案例</a></p><p>分類：'+esc('、'.join(f'{TYPES[k]} {ct[k]}' for k in TYPES))+f'。保留{r["kept"]}、排除{r["excluded"]}。</p><div class="grid"><div>參照圖<img src="images/{key}-reference.jpg"></div><div>待測與保留框<img src="images/{key}-overlay.jpg"></div></div><details><summary>原始照片</summary><img src="images/{key}-source.jpg"></details>'
        if r['label']=='NG':body+=f'<p><a href="answers.html#answer-{key}">查看本張答案</a></p>'
        body+='<h2>全部保留與排除候選</h2>'+columns(cc,card,lambda c:c['keep']);page(report,f'photo-{key}.html','MPT10／'+r['name'],body)
    body='<p>沿用101處既有答案與中心重疊規則，以本輪實際判斷物件範圍重新配對；未新增或移動標籤。</p>'
    for r in bad:
        key=r['key'];body+=f'<section id="answer-{key}"><h2>{key}</h2><p><a href="photo-{key}.html">返回照片</a></p><img src="images/{key}-answers.jpg">'+table(['答案','結果','候選'],[[m['id'],'命中' if m['hit'] else '未命中','、'.join(f'<a href="photo-{key}.html#case-{k}">{k}</a>' for k in m['candidates']) or '無'] for m in markrows if m['photo']==key])+'</section>'
    page(report,'answers.html','全部101處答案',body)
    body=note+table(['指標','上輪保留版本','本輪整合庫'],[['答案命中',79,len(actual)],['NG未對答案',summary['baseline_NG_unmatched'],summary['NG_unmatched']],['一般良品警報',summary['baseline_good_alarms'],summary['good_alarms']],['參照自比',0,summary['self_alarms']]])+'<p>逐處保護原79處，逐照片檢查警報；沒有新增未對答案警報或新增良品警報，兩處人工確認與#22／#40均符合。B局部辨識、完整輪廓複核的判準與接點複核均沿用；另修正整合分支，讓完整輪廓意見不一致時仍能進入既有複核。主參考庫實際已更換，正式流程未動。</p>'
    changed=[c for c in cases if c['keep']!=c['baseline_keep']];body+='<h2>實際改判的全部候選</h2>'+table(['案例','上輪','本輪','答案','實際理由'],[[f'<a href="photo-{c["photo"]}.html#case-{c["key"]}">{c["key"]}</a>','保留' if c['baseline_keep'] else '排除','保留' if c['keep'] else '排除',str(c['answers']) or '無',esc(c['reason'])] for c in changed])
    body+=table(['照片','原保留','本輪保留','原未對答案','本輪未對答案'],[[f'<a href="photo-{r["key"]}.html">{r["key"]}</a>',r['baseline_kept'],r['kept'],r['baseline_unmatched'],r['unmatched']] for r in rows])+'<p><a href="../summary.json">實際統計</a> · <a href="../plan.json">凍結來源與程式雜湊</a> · <a href="../verification.json">完整性檢查</a></p>';page(report,'comparison.html','附加：版本比較與實際測試範圍',body)
    attribution(report,cases,proof,a.arm)
    verifier.OUT=OUT;verifier.verify(report,images,cases,rows,plan,summary)
    print('VALIDATED INTEGRATED REPORT',summary,flush=True)

def attribution(report,cases,proof,arm):
    manifest=read(NEW/'collection/manifest.json');new={r['id']:r for r in manifest['examples']};body='<p>主參考範例已整理，模型權重與門檻不變；另修正混合輪廓分數會跳過既有複核的整合分支。逐一移除單個參考例並對相同輸入重算，用來分清相似鄰居與實際造成翻判的例子。</p>'
    body+='<h2>哪些參考例造成新增警報</h2><p>#40最接近舊S07、S05、S20，其背景混入接點紋理。P05與P11均是圓頭正例，全部加入周邊背景版本會讓邊界及未確認小圓物件得到更多正例支持。P04也會拉高板上元件的單步分數，但完整流程仍須通過結構複核，不能看到分數變高就認定它造成最終誤報。</p><p>正常例G01、N12的視野實際帶到圓形結構，會壓低真螺絲分數；它們移到對照用途。P06的板邊背景會影響小元件判斷，改用本體版本。只改P05本體雖能救回131答案6，整張回放仍在130新增小圓形警報，因此該方案不採用。後續改為P06與同位置G06成對使用本體範圍，並保留原S05；特定完整分類對照可同時保住原螺絲及排除未確認小圓形／邊界。這些是參考影像內容的修正，模型權重與待測取圖不變。</p><p>使用者對128#7回覆「目前無法判定」，因此不把它當正常負例或新螺絲答案。驗收仍要求不新增此未確認警報。</p>'
    for ident in ('P05','P11','P04'):
        name=f'{ident}-reference.png';shutil.copy2(new[ident]['views']['context']['file'],report/name);body+=f'<article><h3>{ident}｜{esc(new[ident]["family"])}</h3><img style="width:220px;image-rendering:pixelated" src="{name}"></article>'
    arms=read(EXP/'fixed-query-summary.json');body+='<h2>固定同一待測輸入的初步比較</h2><p>此表是1345候選的單步診斷，不是完整79流程成績；26個單步新增未對答案警報中，6個原本已被上輪完整流程保留，真正相對上輪新出現的是20個單步候選。不能把前6個當成新增誤報壓掉。</p>'+table(['方案','單步命中','未對答案','新增單步未對答案','#40分數'],[[s['arm'],s['raw_hits'],s['unmatched'],len(s['new_unmatched']),f'{s["pair40"]:+.4f}'] for s in arms])
    recipe_path=EXP/f'{arm}-recipe.json'
    if recipe_path.exists():
        recipe=read(recipe_path);body+='<h2>本輪實際採用的實驗庫</h2><p>'+f'{recipe["positive"]}個螺絲正例＋{recipe["normal"]}個正常例。原47個螺絲來源保留；實際整理範圍的來源依本輪配方紀錄。原65正常例保留，加入經審查的新案例。主庫暫不使用的正例：'+esc('、'.join(recipe['inactive_new_positive_ids']))+'；移到對照用途的正常例：'+esc('、'.join(recipe['inactive_new_normal_ids']))+'。本體版本：'+esc('、'.join(recipe['view_overrides']))+'。沒有把移出的螺絲改標成正常，原有答案與人工紀錄保持不變。</p>'
    elif arm=='clean3_selective':
        body+='<h2>本輪實際採用的實驗庫</h2><p>保留原47個螺絲來源，其中S05／S07／S20改用已審查的螺絲範圍；新增P02／P03／P06／P07四個側面螺絲，合計51正例。正常庫保留原65個再加27個，合計92個。P01／P04／P05／P11仍是正例，保留於案例集與驗證資料，但不參與主庫相似度投票；沒有改標成正常。原圓頭姿態仍保留，使用者確認的#10大圓頭必須實際辨識成功。</p>'
    else:body+='<h2>本輪實際採用的實驗庫</h2><p>方案：'+esc(arm)+'。移出主庫的P11仍是螺絲正例，保留在案例集與驗證資料；不是改標成正常。原有姿態及其他新案例保留，#10大圓頭仍必須實際辨識成功。</p>'
    model=ROOT/'models/dino-paired-optimized-47-20261104-r3';old_manifest=read(model/'manifest.json');old_examples=read(model/'examples.json');body+='<h3>原庫實際整理的兩例</h3><p>每組左邊是原參考圖，右邊是本輪啟用範圍；S05維持原圖。這裡整理的是參考範例，不是搬動待測答案框。</p><div class="grid">'
    for ident in ('S07','S20'):
        oid=old_manifest['example_bank']['screw']['ids'][int(ident[1:])-1];src=model/'examples'/old_examples[oid]['file'];name=f'{ident}-original.png';Image.open(src).save(report/name);active_name=f'{ident}-active.png';shutil.copy2(EXP/'active-reference-collection/images'/f'{ident}.png',report/active_name);body+=f'<article><h4>{ident}</h4><img style="width:160px;image-rendering:pixelated" src="{name}"> → <img style="width:160px;image-rendering:pixelated" src="{active_name}"></article>'
    body+='</div><h2>完整流程失敗方案與修正</h2>'
    records=[]
    for photo in ('ng-128','ng-129','ng-130','ng-131','ng-132','ng-133','ng-134','ng-135','ng-136','ng-137'):
        for name in ('clean3_integrated','clean3_selective','clean2_dedup','curated_v3','curated_v4','curated_v5','curated_v5_review'):
            p=EXP/'replay'/photo/f'{name}.json'
            if p.exists():
                r=read(p);records.append([photo,name,len(r['hits']),r['lost_original_answers'],r['unmatched'],r['new_unmatched']])
    body+=table(['照片','方案','命中','遺失原答案','未對答案','新增未對答案'],records)
    if (EXP/'reference-role-counterfactuals.json').exists():
        role=read(EXP/'reference-role-counterfactuals.json');body+='<h2>逐項修正對照</h2><p>固定實際候選與完整分類規則，分別測原候選庫、移除全部同位置背景例、G06改本體，以及補回P05或P01本體。移除更多正常例雖能救回131答案6，也會讓132邊界再報警；P05本體只通過這組局部對照，後續整張130新增警報，因此沒有採用。</p>'+table(['案例','方案','接點複核前','完整結果'],[[f'{r["photo"]} #{r["id"]}',r['arm'],r['upstream_verdict'],r['final_verdict']] for r in role])
    if (EXP/'reference-role-counterfactuals-v5.json').exists():
        role=read(EXP/'reference-role-counterfactuals-v5.json');body+='<h3>後續成對範例與原S05保留的對照</h3>'+table(['案例','方案','接點複核前','完整結果'],[[f'{r["photo"]} #{r["id"]}',r['arm'],r['upstream_verdict'],r['final_verdict']] for r in role])
    body+='<details><summary>參考例本體／背景範圍與移出的正常例</summary><div class="grid">'
    for ident in ('P05','P06','G06','G01','N12'):
        for mode in ('core','context'):
            name=f'{ident}-{mode}.png';shutil.copy2(new[ident]['views'][mode]['file'],report/name);body+=f'<article><h3>{ident}｜{mode}</h3><img style="width:200px;image-rendering:pixelated" src="{name}"></article>'
    body+='</div></details>'
    body+='<h2>修正分數變好卻漏掉的分支</h2><p>136答案4原本靠既有完整輪廓複核命中。新庫使其中一個輪廓範圍略微轉正（約+0.00015），三範圍意見不一致，原流程反而保留小碎片的未達共識標記並跳過後續複核。4r整合修正讓這類混合結果仍進入相同四範圍複核，使用同一47＋65副庫及原門檻；線材／元件等實際結構排除條件仍保留。這是分類流程修正，不是報告改字或答案位置特判。</p><h2>擾動與影像縮放</h2><p>框位移±4像素、大小75／90／100／110／125%；另對對位後影像做同比例縮放，沿用縮放後候選支援，沒有重新產生候選。未標答案的衝突組只驗證一致性，不宣稱新增人工標籤。</p>'+table(['組別','框擾動通過／總數','影像縮放通過／總數'],[[str(g['photo'])+' '+str(g['seeds']),f'{g["query_pass"]}/{g["query_total"]}',f'{g["image_pass"]}/{g["image_total"]}'] for g in proof['groups']])
    body+='<h3 id="scale-limit">額外縮放檢查仍有1項失敗</h3><p>135 #88是人工確認掉落螺絲。原尺寸、45次候選框擾動、75／90／100／110%影像尺寸均保留；放大125%時原版和本版都排除，待測分數同為−0.0055936，最相似的正例與正常例也完全相同，皆來自原庫。該長條候選由15×89變為19×111像素；兩版皆沒有進入完整輪廓複核。這是尚未解決的既有限制，不能稱全部縮放通過。12組原衝突及兩接點則全部通過；全部框擾動1260／1260，額外影像縮放總計139／140。</p><p><a href="../../human88-scale-diagnosis.json">原版與本版完整分類證據</a></p>'
    checks=read(EXP/'replay/ng-128'/f'{arm}.json')['upstream_pair_checks'];body+='<h2>#22／#40實際主流程判斷</h2><p>兩個案例在既有接點終端複核之前，已由本輪分類流程判為排除。</p>'+table(['候選','終端複核前','待測分數','參照分數'],[[r['id'],r['verdict'],f'{r["paired_evidence"]["target"]["screw_margin"]:+.4f}',f'{r["paired_evidence"]["reference"]["screw_margin"]:+.4f}'] for r in checks])
    body+='<h2>26個單步新增候選與#22／#40逐一追溯</h2>'
    for z in read(EXP/'attribution.json'):
        key=z['key'];photo='-'.join(key.split('-')[:2]);top=sorted(z['leave_one_out'],key=lambda v:v['target_delta'])[:3];body+=f'<details><summary>{key}｜'+('上輪已保留' if z['current_keep'] else '上輪排除')+f'</summary><p><a href="photo-{photo}.html#case-{key}">本輪實際完整結果</a></p><img src="images/{key}.jpg" alt="實際圖對">'+table(['移除哪個例','待測分數變化','移除後單步判斷'],[[r['id'],f'{r["target_delta"]:+.4f}','保留' if r['keep'] else '排除'] for r in top])+'</details>'
    active=read(EXP/'active-reference-collection/manifest.json');body+='<details><summary>展開全部實際啟用的參考例</summary><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px">'
    for r in active['examples']:
        name=f'active-ref-{r["id"]}.png';shutil.copy2(EXP/'active-reference-collection'/r['file'],report/name);body+=f'<article><h3>{r["id"]}｜'+('螺絲' if r['label']=='screw' else '正常')+f'</h3><img style="width:160px;height:160px;object-fit:contain;image-rendering:pixelated" src="{name}" alt="實際參考來源圖"></article>'
    body+='</div></details>'
    body+=f'<p><a href="../../attribution.json">全部逐例移除證據</a> · <a href="../../{arm}-bank.npz">主庫特徵</a> · <a href="../../stability-{arm}.json">完整穩定性紀錄</a> · <a href="../../active-reference-collection/manifest.json">全部參考來源與範圍</a> · <a href="../../integrated-reference-collection.zip">整合案例集ZIP</a></p>';page(report,'attribution.html','附加：新增警報的參考例原因與修正',body)
if __name__=='__main__':main()
