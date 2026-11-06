"""Part-B diagnostic only, using the unchanged 47+65 bank."""
import os,sys,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));OUT=ROOT/'workspace/dino-4r-visible-screw-20261106';OUT.mkdir(exist_ok=True)
os.environ['XRAY_WORKSPACE']=str(OUT/'runtime');os.environ['XRAY_CONFIG']=str(OUT/'isolated-settings.json')
from model_manager import ModelManager
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
def main():
    snap=ModelManager(ROOT/'models',allow_cpu=True,execution_override='gpu').snapshot('dino-paired-optimized-47-20261104-r3');assert not snap.error
    arr=np.load(ROOT/'workspace/dino-4r-improvement-20261106/arrays/128.npz');ref,tar=[(np.clip(arr[k],0,1)*255).astype('uint8').astype('float32')/255 for k in ('ref','target')]
    rows=[];panels=[]
    for name,b in [('B-tight',[728,442,12,18]),('B-visible',[728,440,13,23]),('B-edge',[726,440,16,23]),('normal-block-right',[728,1388,13,23]),('black-block',[705,437,23,36])]:
        x,y,w,h=b
        for pad in (0,2,4,8,12):
            crops=[a[y-pad:y+h+pad,x-pad:x+w+pad] for a in (ref,tar)];pred=snap.classify(crops[1],reference_crop=crops[0]);r=dict(name=name,box=b,pad=pad,prediction=pred);rows.append(r)
            print(name,pad,[(s,round(pred['paired_evidence'][s]['screw_margin'],4)) for s in ('reference','target')],pred['filter_recommendation'],flush=True)
            if pad in (0,4):
                im=Image.new('RGB',(480,270),'white');d=ImageDraw.Draw(im);d.text((4,4),f'{name} pad{pad}  Ref / Target',fill='black')
                for i,a in enumerate(crops):
                    p=Image.fromarray(np.uint8(a*255)).resize((230,230),Image.Resampling.NEAREST).convert('RGB');im.paste(p,(i*240,30))
                panels.append(im)
    canvas=Image.new('RGB',(960,270*((len(panels)+1)//2)),'white')
    for i,im in enumerate(panels):canvas.paste(im,((i%2)*480,(i//2)*270))
    canvas.save(OUT/'B-crop-diagnostic.jpg');(OUT/'crop-probe.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'user-feedback.json').write_text(json.dumps({'128-answer10':{'confirmed_part':'B','description':'黑塊右側半圓為被遮擋螺絲露出部位','authority':'使用者回覆B','pixel_box':[728,442,12,18],'pixel_box_authority':'助理依使用者部位定位，非使用者逐像素框選'},'scope':'只確認128案例B；其他照片另列對照，不冒稱人工逐點確認'},ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
