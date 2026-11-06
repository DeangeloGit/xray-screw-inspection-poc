"""Add every missed answer and every added alarm to the full experiment report."""
import argparse
from collections import Counter
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import sys
from urllib.parse import unquote
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
esc=lambda x:html.escape(str(x))


def main():
    p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('experiment',type=Path);a=p.parse_args();base=a.baseline.resolve();exp=a.experiment.resolve();out=exp/'final'
    sys.path.insert(0,str(ROOT))
    import answered_batch_report as full
    sys.argv=[sys.argv[0],str(out)];full.main()
    report=out/'report';images=report/'images'
    initial=read(exp/'diagnosis-initial.json');detail={(r['photo'],r['id']):r for r in read(exp/'diagnosis-detailed.json')}
    oldmarks=read(base/'answer-matches.json');newmarks={(m['photo'],m['id']):m for m in read(out/'answer-matches.json')}
    newcases=read(out/'cases.json');index={(c['photo'],tuple(c['box'])):c for c in newcases}
    summary=read(out/'summary.json');rules=read(out/'plan.json')['rules'];oldcases=read(base/'cases.json')
    misses=[]
    for m in initial['misses']:
        photo,mid=m['photo'],m['id'];d=detail[(photo,mid)];final=newmarks[(photo,mid)]
        if mid==4:
            category='板上螺絲的差分碎裂'
            text='寬容差分只剩少量像素；縮小容差後仍拆成小塊，受到小面積／鄰近既有結構門檻限制。合併碎片可補出候選，但 DINO 隨取圖範圍改變，尚未達穩定雙圖共識。'
        elif mid in (8,9):
            category='深色喇叭區訊號不足'
            text='答案位於深色喇叭區。參照與待測都很暗，主要差分幾乎沒有完整物件；窄容差多為細碎邊緣。不能只靠降低門檻把正常喇叭輪廓當螺絲。'
        elif mid==10:
            category='大元件遮住或混入螺絲取圖'
            text='答案區域主要候選是大塊矩形／支架，螺絲與其重疊或位在旁邊；DINO 取圖受到大元件主導而判不像螺絲。需要先把小物件分離，直接放寬分數會引入板件警報。'
        elif (photo,mid) in (('133',3),('137',6)):
            category='答案框位置待確認'
            text='附近已有保留警報，目視疑似螺絲，但與提供的紅框只擦邊或有位移。配準整體檢查通過，仍需人工確認這個局部答案框；本輪不改答案、不放寬匹配，也不將疑似螺絲刪掉來降低誤報。'
        elif (photo,mid)==('135',1):
            category='螺絲與線材候選混在一起'
            text='附近有長條線材／邊界候選，但沒有對上答案的獨立螺絲框。需要局部分離與重新定位；本次保守條件尚未可靠救回。'
        else:
            category='小圓頭或混合背景判斷不穩'
            text='部分候選被鄰近相似結構門檻擋住，部分已送進 DINO 卻判成正常物件。雙尺寸重看可救回其中幾處，但參照也像螺絲的情況仍須依雙圖規則排除。'
        misses.append(dict(**m,category=category,explanation=text,current_hit=bool(final['methods']['pilot']),current_candidates=final['methods']['pilot'],trace=d))
    alarmrows=[]
    for z in initial['added_false_alarms']:
        c=index[(z['photo'],tuple(z['box']))]
        if z['key'] in ('133-9','137-28'):
            reason='目視疑似螺絲，答案框位置待確認；保留警報，原答案框外統計也保留。';category='待確認'
        elif z['key']=='132-49':
            reason='細長結構與線材相連；附近參照可找到位移後相似外形，兩種取圖的整體／局部分數不支持螺絲。';category='線材（自動推測）'
        elif z['key']=='130-78':
            reason='小黑塊擴大輪廓後連到大元件；補抓分數對取圖範圍不穩，結構複核排除。';category='元件外觀（自動推測）'
        else:
            reason='板角的小黑點在較亮輪廓下連到大板件；原小裁圖像螺絲，擴大後缺乏穩定支持。';category='板件邊界（自動推測）'
        alarmrows.append(dict(previous_key=z['key'],current_key=c['key'],current_keep=c['keep']['pilot'],category=category,explanation=reason))
    metrics=dict(initial_misses=48,initial_stage_counts=dict(Counter(m['reason'] for m in initial['misses'])),diagnostic_groups=dict(Counter(m['category'] for m in misses)),rescued=[f'{m["photo"]}-{m["id"]}' for m in misses if m['current_hit']],remaining=sum(not m['current_hit'] for m in misses),previous_hits_lost=summary['lost_recovery_answers'],initial_added_alarms=7,removed_added_alarms=sum(not z['current_keep'] for z in alarmrows),preserved_ambiguous_alarms=[z['previous_key'] for z in alarmrows if z['current_keep']])
    assert metrics['previous_hits_lost']==[]
    assert metrics['rescued']==['130-2','130-5','131-6'],metrics
    assert metrics['removed_added_alarms']==5,metrics
    assert summary['totals']['pilot']['answer_hits']==55 and summary['totals']['pilot']['unmatched']==61,summary
    save(exp/'diagnosis-final.json',dict(metrics=metrics,misses=misses,added_alarms=alarmrows))
    body='<p>本頁是完整結果的附加分析。固定原有 100 處答案和原匹配規則；候選框外警報仍列為疑似誤報。未修改人工答案或正式流程。本批已用於規則選擇，不能當作獨立驗收。</p>'
    body+=full.table(['比較','上輪','本輪'],[['答案命中','52/100','55/100'],['未命中答案',48,45],['答案框外警報',66,61],['相較原 r3 多出的框外警報',7,2],['原有 52 處命中損失',0,0]])
    body+='<h2>48 處原始漏抓：原因分組</h2>'+full.table(['原因','處數'],[[k,v] for k,v in metrics['diagnostic_groups'].items()])
    body+='<p>依原流水線位置分流：33 處沒有對上候選、15 處待測被判不像螺絲；0 處直接由上輪過殺過濾刪掉。本輪救回 130 的答案 2／5 與 131 的答案 6，其餘 45 處保留未命中狀態。</p>'
    body+='<h2>本輪採用與未採用的做法</h2><ul><li>原 r3 保留判斷直接沿用，另核對目前 52 處命中全部保住。</li><li>合併鄰近窄容差碎片，補足前段沒有送出的候選；所有補提候選及排除結果均收錄在完整報告。</li><li>參照／待測各用 4、8 像素外圍取圖；整體、局部及新增黑影特徵平均，兩種取圖都須待測分數至少 0.04、參照小於 0，並保有足夠物件範圍。</li><li>只對上輪補抓新增的警報檢查板件連接與線材位移；沒有用答案位置決定保留或排除。</li><li>更小取圖或放寬分數能救回更多，但會增加框外警報，未採用。分數 0.03 與 0.04 的保守方案結果相同，固定用 0.04。</li></ul>'
    body+='<p>後續方向：板上螺絲先改善物件分離與取圖一致性；喇叭深色區需檢查原始曝光與可見訊號；大元件旁螺絲需局部分割。兩個答案框疑點應另行人工確認。現在沒有足夠證據支持直接放寬正式門檻。</p>'
    timing=[]
    for method in ('recovery','pilot'):
        seconds=[read(out/'runs'/method/key/'complete.json')['seconds'] for key in [str(i) for i in range(128,138)]]
        timing.append([full.METHODS[method],round(sum(seconds)/len(seconds),2),round(min(seconds),2),round(max(seconds),2)])
    body+='<h2>本次執行時間紀錄</h2><p>同機 GPU 單次批次紀錄，包含輸出圖片；不是交錯重複的效能基準。本輪增加補提與雙尺寸重看，耗時較高，尚未做速度優化。</p>'+full.table(['版本','每張平均秒數','最快','最慢'],timing)
    body+='<h2>原有 7 個新增警報：逐一去向</h2>'
    for z in alarmrows:
        name='diagnostic-alarm-'+z['previous_key']+'.jpg';shutil.copy2(base/'report'/'images'/(z['previous_key']+'.jpg'),images/name)
        key=z['current_key'];photo=key.split('-')[0]
        body+=f'<article id="alarm-{z["previous_key"]}"><h3>{z["previous_key"]}：'+('保留／待確認' if z['current_keep'] else '本輪排除')+f'</h3><p>{esc(z["category"])}。{esc(z["explanation"])}</p><p><a href="photo-{photo}.html#case-{key}">查看完整照片與同類案例</a></p><img src="images/{name}" alt="參照與待測對照"></article>'
    body+='<h2>48 處原始漏抓：全部逐處證據</h2>'
    for m in misses:
        photo,mid=m['photo'],m['id'];k=f'{photo}-{mid}';d=m['trace'];name='diagnostic-answer-'+k+'.jpg';shutil.copy2(exp/'diagnostic-pairs'/(k+'.jpg'),images/name)
        body+=f'<article id="miss-{k}"><h3>{k}：{esc(m["category"])}／'+('本輪救回' if m['current_hit'] else '仍未命中')+f'</h3><p>{esc(m["explanation"])}</p><p><a href="answers.html#answer-{photo}">查看本張全部答案</a> · <a href="photo-{photo}.html">返回完整照片</a></p><p>左：參照　右：待測；紅框為提供答案對回的位置。</p><img src="images/{name}" alt="答案 {k} 的雙圖診斷">'
        gate_names={'size':'面積或尺寸未達條件','small_near_existing_structure':'小碎片靠近既有結構而被擋下','similarity_rejected':'與參照過於相似，補提條件不足','passed_initial_filters':'通過初步篩選，仍須後續核對','similarity_recovery':'符合相似結構補提條件'}
        body+=full.table(['前段差分','答案區超過門檻像素','對上的原始連通區'],[[('主差分（容許 3 像素位移）' if s=='7' else '窄容差（容許 1 像素位移）'),v['above_threshold_pixels'],'；'.join(f'面積 {c["area"]}，{gate_names[c["gate"]]}' for c in v['components']) or '無'] for s,v in d['stages'].items()])
        body+='<p>本輪命中候選：'+('、'.join(f'<a href="photo-{photo}.html#case-{c}">{c}</a>' for c in m['current_candidates']) or '無')+'</p></article>'
    variants=read(exp/'bounded-variants.json')
    body+='<details><summary>全部 36 組取圖／分數比較（同批開發試驗）</summary>'+full.table(['外圍取圖','分數組合','門檻','新增命中答案','新增框外警報'],[[','.join(v['pads']),v['kind'],v['threshold'],v['new_count'],len(v['added_unmatched'])] for v in variants])+'</details>'
    nav=full.NAV+'<a href="diagnosis.html">附加：漏抓與新增警報分析</a>'
    (report/'diagnosis.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>48 處漏抓與 7 個新增警報分析</title><style>'+full.STYLE+'</style><main>'+nav+'<h1>48 處漏抓與 7 個新增警報分析</h1>'+body+'</main></html>',encoding='utf-8')
    for f in report.glob('*.html'):
        if f.name=='diagnosis.html':continue
        txt=f.read_text(encoding='utf-8').replace('</nav>','<a href="diagnosis.html">附加：漏抓與新增警報分析</a></nav>',1);f.write_text(txt,encoding='utf-8')
    class Parser(HTMLParser):
        def __init__(self):super().__init__();self.ids=[];self.links=[]
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if 'id' in a:self.ids.append(a['id'])
            for k in ('src','href'):
                if k in a:self.links.append(a[k])
    parsed={}
    for f in report.glob('*.html'):
        parser=Parser();parser.feed(f.read_text(encoding='utf-8'));assert len(parser.ids)==len(set(parser.ids));parsed[f.resolve()]=parser
    links=0
    for f,parser in parsed.items():
        for link in parser.links:
            name,_,anchor=link.partition('#');dest=(f.parent/unquote(name)).resolve() if name else f
            assert dest.exists(),(f,link)
            if anchor:assert anchor in parsed[dest].ids,(f,link)
            links+=1
    for image in images.glob('*.jpg'):
        with Image.open(image) as im:im.verify()
    verify=read(out/'verification.json');verify.update(html_pages=len(parsed),links_checked=links,images_checked=len(list(images.glob('*.jpg'))),all_48_previous_misses_documented=True,all_7_added_alarms_documented=True,all_52_previous_hits_preserved=True,diagnostic_metrics=metrics)
    save(out/'verification.json',verify);print(json.dumps(metrics,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
