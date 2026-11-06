"""Full corpus report plus all perturbation evidence, never relabels inference."""
import argparse,json,sys
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote
from PIL import Image
import answered_batch_report as full
from stability_probe import fingerprint

def main():
    p=argparse.ArgumentParser();p.add_argument('experiment',type=Path);a=p.parse_args();exp=a.experiment.resolve();out=exp/'final';read=full.read;save=full.save
    sys.argv=[sys.argv[0],str(out)];full.main()
    report=out/'report';summary=read(out/'summary.json');tests=read(exp/'perturbation-results.json');cases=read(out/'cases.json');idx={c['key']:c for c in cases}
    manifest=read(exp/'evidence-manifest.json')
    assert all(full.sha(p)==h for p,h in manifest['policy_and_test_inputs'].items())
    assert all(full.sha(p)==h for p,h in read(out/'plan.json')['experiment_hashes'].items())
    assert len(tests['pairs'])==12 and tests['total_tests']==1080
    assert tests['stable_object_tests']==tests['stable_prediction_tests']==1080
    assert sum(r['expected']['verdict']=='keep' for r in tests['pairs'])==8
    assert all(r['expected']['verdict']=='keep' for r in tests['pairs'] if r['pair']['same_answer_ids'])
    assert summary['totals']['pilot']['answer_hits']>=55 and not summary['lost_recovery_answers']
    assert summary['totals']['pilot']['unmatched']<=61
    # Compare raw inference output against every tested pair, independent of HTML.
    for rec in tests['pairs']:
        for key in ('kept','excluded'):
            name=rec['pair'][key];photo,cid=name.split('-');result=read(out/'runs/pilot'/photo/'result.json')
            c=next(c for c in result['candidates']+result['filtered_candidates'] if c['id']==int(cid))
            assert fingerprint(c['classification'])==rec['expected'],name
            assert c['classification']['canonical_object']['box']==rec['canonical_box']
    objects={}
    for c in cases:
        obj=c['canonical_object'];objects.setdefault((c['photo'],obj['object_id']),[]).append(c)
    assert all(len({c['keep']['pilot'] for c in group})==1 for group in objects.values())
    object_metrics={m:dict(alarms=sum(any(c['keep'][m] for c in group) for group in objects.values()),unmatched=sum(any(c['keep'][m] for c in group) and not any(c['keep'][m] and c['method_matches'][m][0] for c in group) for group in objects.values())) for m in ('recovery','pilot')}
    assert object_metrics['pilot']['unmatched']<=object_metrics['recovery']['unmatched']
    changed=[c for c in cases if c['keep']['recovery']!=c['keep']['pilot']]
    stats=dict(pairs=12,tests=1080,stable=1080,pair_final_outputs_match_tests=True,old_hits_lost=summary['lost_recovery_answers'],object_metrics=object_metrics,changed_candidates=[c['key'] for c in changed],notes='固定影像物件庫下的候選框擾動；不是影像旋轉、亮度或重新配準測試。')
    save(exp/'stability-verification.json',stats)
    body='<p>本頁附加於全圖資結果。實際修改模型前的影像取圖，重新跑完 11 張照片、全部 1,345 個候選；不是修改報告標籤。模型仍為 47＋65 範例與參照／待測雙圖，正式流程沒有變更。</p>'
    body+=full.table(['檢查','結果'],[['衝突組數','12／12 組消除相反判斷'],['框位移／縮放','1,080／1,080 次物件、判斷、分數及輸入影像雜湊相同'],['前輪 55 處命中損失',len(summary['lost_recovery_answers'])],['答案框外警報（候選框）',f"61 → {summary['totals']['pilot']['unmatched']}"],['答案框外警報（同一物件去重）',f"{object_metrics['recovery']['unmatched']} → {object_metrics['pilot']['unmatched']}"],['答案命中',f"{summary['totals']['pilot']['answer_hits']}／100"]])
    body+='<h2>實際改善與測試範圍</h2><p>原本大小框可能截到不同的物件部位，且走不同補抓規則，造成同一螺絲一留一刪。現在先從影像差分候選與暗色輪廓建立物件範圍：緊實物件採用完整小輪廓，連到板件的碎片採用周圍結構。大型群組不合併，以免混入另一個物件。定位不讀答案、照片編號或舊判斷；每次均以定位後影像重新推論。</p><p>每組兩個原始框，各測 5 種比例（75%、90%、100%、110%、125%）× 水平位移 −4／0／＋4 × 垂直位移 −4／0／＋4，共 90 次。位移單位是檢測縮圖像素。測試固定同一張影像建立的物件庫，只擾動輸入候選框；不表示模型本身對任意裁圖都穩定，也未驗證影像旋轉、亮度變化或重新配準。</p><p class="warn">這批圖已用於開發。8 組螺絲樣物件保留（其中 1 組未對到提供答案，仍計入疑似誤報）；4 組板件／接頭樣結構排除，屬自動判斷、尚非新增人工真值。測試證明指定範圍內一致及原有答案保住，不等於所有未標記物件均已證實判對。</p>'
    body+='<h2>12 組完整驗證</h2>'
    for n,rec in enumerate(tests['pairs'],1):
        pair=rec['pair'];keep=rec['expected']['verdict']=='keep';name=pair['kept']+'__'+pair['excluded']
        body+=f'<article><h3>{n}．{pair["kept"]} ／ {pair["excluded"]} → '+('兩者保留' if keep else '兩者排除')+'</h3>'
        for k in ('kept','excluded'):
            key=pair[k];c=idx[key]
            body+=f'<p><a href="photo-{c["photo"]}.html#case-{key}">{key}：查看完整照片與同類案例</a></p><img class="pair" src="images/{key}.jpg">'
        body+=f'<p>紅框：原候選；藍框：實際判斷物件。原本一留一刪，本輪 90／90 次相同。實際取圖框 {rec["canonical_box"]}。</p><p><a href="../../perturbations/{name}.json">90 次完整分數、輸入雜湊與位移紀錄</a></p>'
        body+='<details><summary>展開全部 90 次測試</summary>'+full.table(['起始候選','比例','水平位移','垂直位移','同物件','相同推論'],[[z['seed_id'],z['scale'],z['dx'],z['dy'],'是' if z['same_object'] else '否','是' if z['same_prediction'] else '否'] for z in rec['tests']])+'</details></article>'
    body+='<h2>全部判斷變更</h2>'+full.table(['候選','前輪','本輪','本輪答案'],[[f'<a href="photo-{c["photo"]}.html#case-{c["key"]}">{c["key"]}</a>','保留' if c['keep']['recovery'] else '排除','保留' if c['keep']['pilot'] else '排除',str(c['answers'])] for c in changed])
    body+='<p><a href="../../stability-verification.json">穩定性與去重統計核對</a> · <a href="../../perturbation-results.json">全部測試證據</a> · <a href="../../evidence-manifest.json">推論程式與測試輸入雜湊</a></p>'
    (report/'stability.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>12 組穩定性驗證</title><style>'+full.STYLE+'</style><main>'+full.NAV+'<h1>12 組衝突與框位移／縮放驗證</h1>'+body+'</main></html>',encoding='utf-8')
    for f in report.glob('*.html'):
        f.write_text(f.read_text(encoding='utf-8').replace('</nav>','<a href="stability.html">附加：12 組穩定性驗證</a></nav>',1),encoding='utf-8')
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
    for f in (report/'images').glob('*.jpg'):
        with Image.open(f) as im:im.verify()
    v=read(out/'verification.json');v.update(html_pages=len(parsed),links_checked=count,stability=stats);save(out/'verification.json',v)
    print(json.dumps(stats,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
