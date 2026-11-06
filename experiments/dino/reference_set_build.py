"""Build a source-traceable object-level reference collection from NG128/Golden."""
from reference_set_prepare import ROOT,OUT,PRIOR,read,save,flow_for
import copy,hashlib
from collections import Counter
import numpy as np
from PIL import Image,ImageDraw
from detector import source_points

POS_FAMILY={1:'線材旁圓頭',2:'側面頭桿／板邊',3:'斜向頭桿／板上',4:'板上重疊螺絲',5:'圓頭／明暗邊界',6:'側面頭桿／深色板邊',7:'側面頭桿／立邊',10:'遮擋物外露B部位',11:'獨立大圓頭'}
GOLDEN={
 '接點':[[1115,780,40,60],[1135,465,31,24],[1226,505,70,24],[1155,762,88,30],[1357,1028,23,80],[1164,1267,77,24]],
 '線材':[[778,532,13,52],[890,421,65,22],[1384,1040,30,65],[811,674,35,45],[792,1169,35,37]],
 '板邊':[[1085,949,20,70],[960,785,90,25],[1245,1380,90,25],[714,711,32,42]],
 '元件與黑塊':[[1292,816,50,58],[1195,828,30,30],[1065,760,22,19],[1229,1412,50,50],[1301,400,37,30]],
 'U形結構':[[976,896,51,135],[974,789,51,34],[970,1086,59,45]]}
ROUND_CONTROLS=[[1093,495,23,23],[1091,541,23,24],[712,660,29,29],[783,661,29,27],[1370,430,25,28],[1361,478,24,26],[1360,523,30,29],[1136,848,25,25],[1240,973,28,27],[1095,1326,22,26]]

def square_view(a,b,pad=0,part=False):
    x,y,w,h=b
    if part:
        c=a[y:y+h,x:x+w];s=max(w,h)+4;z=np.ones((s,s),np.float32);xx=(s-w)//2;yy=(s-h)//2;z[yy:yy+h,xx:xx+w]=c;return z
    s=max(w,h)+2*pad;x0=round(x+w/2-s/2);y0=round(y+h/2-s/2);z=np.ones((s,s),np.float32)
    X0,Y0=max(0,x0),max(0,y0);X,Y=min(a.shape[1],x0+s),min(a.shape[0],y0+s)
    z[Y0-y0:Y-y0,X0-x0:X-x0]=a[Y0:Y,X0:X];return z

def main():
    dest=OUT/'collection';dest.mkdir(parents=True,exist_ok=True);(dest/'images').mkdir(exist_ok=True)
    folder=PRIOR/'runs/ng-128';ref,tar=[np.asarray(Image.open(folder/f'{n}.png').convert('L'),np.float32)/255 for n in ('reference','aligned')];r=read(folder/'result.json');flow=flow_for(r,ref.shape);plan=read(PRIOR/'plan.json');item=next(x for x in plan['items'] if x['key']=='ng-128');reg=dict(matrix=np.asarray(r['matrix']),rotation=r['rotation_ccw']//90,mirrored=r['mirrored_input'],target_scale=r['preview_scale']);records=[]
    def add(key,label,family,b,side,role,authority,pair=None,answer=None):
        source_path=folder/('reference.png' if side=='reference' else 'aligned.png');a=ref if side=='reference' else tar;x,y,w,h=b
        pts=np.float32([[x,y],[x+w,y],[x+w,y+h],[x,y+h]])
        native=source_points(pts,reg,flow,r['source_shape']).tolist() if side=='target' else ((pts+.5)*2-.5).tolist()
        z=dict(id=key,label=label,family=family,box=b,side=side,role=role,authority=authority,paired_example=pair,answer=answer,aligned_source=str(source_path),aligned_source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),raw_source=item['path'] if side=='target' else item['reference'],native_polygon=native,views={})
        # Export actual source rectangle and two alternative views. Each source
        # object is ONE example, never count its scales/rotations as new examples.
        raw=Image.fromarray(np.uint8(a[y:y+h,x:x+w]*255));raw.save(dest/'images'/f'{key}-source.png')
        for mode,pad in [('core',0),('context',4)]:
            v=square_view(a,b,pad,role=='part_reference');p=dest/'images'/f'{key}-{mode}.png';Image.fromarray(np.uint8(v*255)).save(p);z['views'][mode]=dict(file=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),shape=list(v.shape),synthetic_object_pixels=False,white_padding_only=role=='part_reference')
        if side=='target' and label=='screw' and role!='part_reference':
            marks=[m for m in read(OUT/'aligned-answers.json') if m['photo']=='ng-128' and m['answer']==answer];assert len(marks)==1
        records.append(z)
    for p in read(OUT/'positive-core-draft.json'):
        n=p['answer'];role='part_reference' if n==10 else 'main_reference';family=POS_FAMILY[n]
        add(f'P{n:02}','screw',family,p['box'],'target',role,'existing answer label; object ROI assistant visually reviewed',f'G{n:02}',n)
        add(f'G{n:02}','non_screw','同位置背景：'+family,p['box'],'reference',role,'known-good Golden, paired same position; visually checked no visible loose-screw shape',f'P{n:02}',n)
    serial=1
    for family,boxes in GOLDEN.items():
        for b in boxes:
            # Review of the exported square views found fixed round structures
            # in these five backgrounds. Good-scene status is not appearance.
            ambiguous=serial in (8,11,15,17,19)
            add(f'N{serial:02}','ambiguous' if ambiguous else 'non_screw',family,b,'reference','pair_control_only' if ambiguous else 'main_reference','assistant visual review: fixed round structure in view; not a negative' if ambiguous else 'known-good Golden; assistant reviewed object type')
            serial+=1
    add('N22-confirmed','non_screw','接點',[1400,941,22,58],'target','main_reference','user explicitly confirmed normal structure / exclude')
    for i,b in enumerate(ROUND_CONTROLS,1):add(f'R{i:02}','ambiguous','板上接點／混合背景' if i==9 else '固定圓形／孔環',b,'reference','pair_control_only','good scene does not imply non-screw appearance; not put into either class')
    add('H40','non_screw','細密接點',[1400,842,22,73],'target','heldout_normal','user confirmed normal; not used as reference')
    add('H03','non_screw','大黑塊結構',[707,1386,21,36],'target','heldout_normal','user confirmed normal; not used as reference')
    add('H-block','ambiguous','黑塊本體、不含B',[707,439,18,32],'target','pair_control_only','no visible B evidence in crop; diagnostic only, not relabeled whole occluded object')
    main_rows=[r for r in records if r['role']=='main_reference'];parts=[r for r in records if r['role']=='part_reference'];assert sum(r['label']=='screw' for r in main_rows)==8 and sum(r['label']=='non_screw' for r in main_rows)==27
    split=dict(construction_photos=['ng-128','Golden'],validation_photos=[f'ng-{n}' for n in range(129,138)],normal_validation='89 ordinary OK images; no crops from them included',source_separation=True,external_independent_batch=False,explanation='Other NG images are development holdouts for this collection, not unseen external scans. #40/#3 are previously inspected diagnostic holdouts.')
    marks=read(OUT/'aligned-answers.json');held=[m for m in marks if m['photo']!='ng-128' and not m['deferred']];assert len(held)==70
    manifest=dict(version='4r-paired-object-reference-collection-v1',status='candidate_collection_not_production',examples=records,counts=dict(main_positive=8,main_negative=27,part_positive=1,part_negative=1,pair_control_only=16,heldout_normal=2,unique_examples=len(records)),split=split,validation_positive_answers=held,deferred_answers=[m for m in marks if m['deferred']],view_policy='core and context are alternative banks, never duplicate an object in top3; 8 rotations/flips remain within each example',label_policy='Train appearance, not scene defect labels. Fixed circular structures are ambiguity controls. Opaque black blocks are never positive screw evidence.')
    save(dest/'manifest.json',manifest)
    # Human-review contact sheets cover every proposed object, with ID and role.
    for prefix,rs in [('main',main_rows),('part',parts),('controls',[r for r in records if r['role'] not in ('main_reference','part_reference')])]:
        for start in range(0,len(rs),12):
            subset=rs[start:start+12];canvas=Image.new('RGB',(1000,220*((len(subset)+4)//5)),'white');d=ImageDraw.Draw(canvas)
            for i,z in enumerate(subset):
                x=i%5*200;y=i//5*220;im=Image.open(z['views']['context']['file']);im=im.resize((180,180),Image.Resampling.NEAREST);canvas.paste(im,(x+10,y+30));d.text((x+5,y+5),f'{z["id"]} {z["label"]}',fill='black')
            canvas.save(OUT/'discovery'/f'{prefix}-set-{start}.png')
    print('COLLECTION',manifest['counts'],'held positive answers',len(held))
if __name__=='__main__':main()
