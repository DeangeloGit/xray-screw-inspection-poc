"""Evidence inventory, explicitly separating assistant review from human labels."""
import json,sys
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'workspace/dino-4r-example-audit-20261106';BASE=ROOT/'workspace/dino-4r-visible-screw-20261106/v3/final'
read=lambda p:json.loads(p.read_text(encoding='utf8'))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    inv=read(OUT/'positive-inventory.json');roundheads=set(range(1,19))|{33,34,43,44,46}
    for e in inv:
        n=e['index'];e.update(review_authority='助理逐張檢視原圖及模型實際輸入，非使用者重新標註',appearance='圓頭／正面或斜面' if n in roundheads else '側面／頭桿輪廓',label_review='有螺絲外觀；目前沒有證據把此例改成正常',action='保留來源；用補成方形的輸入做隔離比較',concerns=[])
        if n<=31:e['concerns'].append('低解析且含板上背景；須保留完整頭桿並以相同背景正常例對照')
        if n==19:e['concerns'].append('實際中央裁切已切掉右側桿端；優先修正預處理')
        elif n in (21,26):e['concerns'].append('中央裁切使桿端／頭部靠近輸入邊緣；不宣稱全部都已被裁斷')
        elif e['center_crop_area_fraction']<.75:e['concerns'].append('中央裁切刪去超過四分之一來源面積；面積比例不等於螺絲被切除比例')
        if n in (16,18,23,39,40):e['concerns'].append('有明顯線材／板邊背景，可能混入相似度；不能把背景視為螺絲證據')
        if n in (37,38,41):e['concerns'].append('與其他深色結構重疊或邊緣截斷；應補乾淨輪廓對照，不能直接加整塊黑影正例')
        if n in roundheads:e['concerns'].append('圓形頭部有用，但不能代替被遮擋螺絲的可見頭桿／半圓部位')
    save(OUT/'positive-review.json',inv)
    marks=read(BASE/'answer-matches.json');cases=read(BASE/'cases.json');miss=[]
    for m in marks:
        if m['methods']['pilot']:continue
        cs=[c for c in cases if c['photo']==m['photo'] and m['id'] in c['answers']]
        deferred=m['id'] in (8,9) or (m['photo'],m['id']) in [('129',6),('137',5)]
        reason='深色喇叭區，依使用者指示暫緩' if m['id'] in (8,9) else '小圓頭與混合背景，依使用者指示暫緩' if deferred else '板上新增螺絲與既有元件黑影接在一起；已有候選及完整輪廓複核，待測仍被判不像螺絲'
        miss.append(dict(photo=m['photo'],answer=m['id'],deferred=deferred,diagnosis=reason,diagnosis_authority='助理影像與推論紀錄審核',candidate_count=len(cs),candidates=[dict(key=c['key'],query_box=c['box'],model_box=c['canonical_object']['box'],target_margin=c['paired_evidence']['target']['screw_margin'],reference_margin=c['paired_evidence']['reference']['screw_margin'],rules=c['rules'],complete_contour=c.get('correspondence_experiment')) for c in cs]))
    assert len(miss)==32 and sum(m['deferred'] for m in miss)==22;save(OUT/'remaining32-diagnosis.json',miss)
    for start in (0,16):
        subset=miss[start:start+16];canvas=Image.new('RGB',(1200,340*((len(subset)+3)//4)),'white');d=ImageDraw.Draw(canvas)
        for j,m in enumerate(subset):
            x=(j%4)*300;y=(j//4)*340;d.text((x+4,y+3),f'{m["photo"]} answer {m["answer"]}  candidates {m["candidate_count"]}',fill='black');d.text((x+4,y+20),'DEFERRED' if m['deferred'] else 'BOARD REVIEW',fill='black');canvas.paste(Image.open(BASE/'report/images'/f'{m["photo"]}-mark-{m["answer"]}.jpg'),(x,y+40))
        canvas.save(OUT/f'misses-{start+1:02d}-{start+len(subset):02d}.jpg')
    print('AUDITED',len(inv),'positive examples;',len(miss),'misses;',sum(not z['candidate_count'] for z in miss),'without matching candidates')
if __name__=='__main__':main()
