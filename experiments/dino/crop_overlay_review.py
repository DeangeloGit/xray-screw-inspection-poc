"""Read-only visual audit of four saved cases. No inference or detection runs."""
import hashlib
import html
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dino_adapter import input_image

OUT = ROOT / 'workspace/dino-crop-overlay-review-20261103'
BLUE, ORANGE, RED = '#006ac2', '#dd6500', '#db2340'
INK = '#173e4b'
FONT = 'C:/Windows/Fonts/msjh.ttc'


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def font(n):
    return ImageFont.truetype(FONT, n)


def rect(x, y, w, h):
    return [x, y, x + w, y + h]


def panel(im, region, box=None, color=BLUE, size=360):
    # All columns show the same source pixels, scale, and context. No contrast edits.
    view = im.crop(region).convert('RGB').resize((size, size), Image.Resampling.NEAREST)
    if box:
        k = size / (region[2] - region[0])
        points = [(box[0]-region[0])*k, (box[1]-region[1])*k,
                  (box[2]-region[0])*k, (box[3]-region[1])*k]
        ImageDraw.Draw(view).rectangle(points, outline=color, width=2)
    return view


def region_for(boxes, im):
    left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
    right, bottom = max(b[2] for b in boxes), max(b[3] for b in boxes)
    side = max(72, right-left+36, bottom-top+36)
    x = max(0, min(im.width-side, round((left+right-side)/2)))
    y = max(0, min(im.height-side, round((top+bottom-side)/2)))
    return [x, y, x+side, y+side]


def montage(title, ims, region, columns, filename):
    width = 30 + len(columns)*382
    canvas = Image.new('RGB', (width, 930), '#f5f8f9')
    d = ImageDraw.Draw(canvas)
    d.text((20, 14), title, font=font(28), fill=INK)
    d.text((20, 55), '同一位置、同一倍率；上排參照圖，下排待測圖。框內是取用範圍，框外保留背景供核對。', font=font(19), fill=INK)
    for col, (label, box, color) in enumerate(columns):
        x = 20 + col*382
        d.text((x, 91), label, font=font(21), fill=color or INK)
        for row, im in enumerate(ims):
            y = 142 + row*394
            d.text((x, y-25), '參照圖' if row == 0 else '待測圖', font=font(18), fill=INK)
            canvas.paste(panel(im, region, box, color), (x, y))
    canvas.save(OUT / filename)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plan_path = ROOT/'workspace/added-object-pilot-20261103/plan.json'
    new_path = ROOT/'workspace/dino-recenter-local-20261103/results.json'
    old_path = ROOT/'workspace/dino-recenter-pair-20261103/results.json'
    cases, rows, old = read(plan_path)['cases'], read(new_path), read(old_path)
    model_path = ROOT/'models/dino-paired-47-20261103/manifest.json'
    manifest = read(model_path)
    protect = [plan_path, new_path, old_path, ROOT/'models/active.json']
    protect += [p for p in (ROOT/'models/dino-paired-47-20261103').rglob('*') if p.is_file()]
    protect += [ROOT/p for p in ['detector.py','dino_adapter.py','acquisition.py','library.py','static/user.js']]
    for n in [1,2,4,12]:
        protect += [Path(cases[n-1]['source'])/f for f in ['reference.png','aligned.png','result.json']]
    before = {str(p):sha(p) for p in protect}
    titles = {1:'斜螺絲',2:'圓頭螺絲',4:'正常線材',12:'正常板件邊界'}
    records, body = [], []
    for n in [1,2,4,12]:
        z = cases[n-1]
        assert z['key'] == rows[n-1]['key'] == old[n-1]['key']
        src = Path(z['source'])
        ims = [Image.open(src/f).convert('L') for f in ['reference.png','aligned.png']]
        c = z['c']; x,y,w,h = [c[k] for k in ['x','y','w','h']]
        candidate = rect(x,y,w,h)
        formal = [max(0,x-12), max(0,y-12), min(ims[0].width,x+w+12), min(ims[0].height,y+h+12)]
        unshifted = next(t for t in rows[n-1]['trials'] if t['dx']==t['dy']==0)
        shifted = next(t for t in rows[n-1]['trials'] if (t['dx'],t['dy']) == ({1:(2,0),2:(2,0),4:(-2,-2),12:(0,-2)}[n]))
        baseline = next(t['before'] for t in old[n-1]['trials'] if (t['dx'],t['dy'])==(shifted['dx'],shifted['dy']))
        bx,by,bs = baseline['box']; old_shift = rect(bx,by,bs,bs)
        region = region_for([candidate,formal,unshifted['crop_box'],old_shift,shifted['crop_box']],ims[0])
        montage(f'{titles[n]}｜原正式取圖與重新定位比較（未加偏移）', ims, region,
                [('原圖：不畫框',None,None),('紅：差分候選框',candidate,RED),
                 ('藍：原正式取圖範圍',formal,BLUE),('橘：重新定位取圖',unshifted['crop_box'],ORANGE)],f'{n}-original.png')
        montage(f'{titles[n]}｜前輪偏移測試：左右 {shifted["dx"]}、上下 {shifted["dy"]} 像素',ims,region,
                [('原圖：不畫框',None,None),('藍：直接偏移的實驗框',old_shift,BLUE),
                 ('橘：偏移後重新定位',shifted['crop_box'],ORANGE)],f'{n}-shift.png')
        # Show source resolution faithfully and verify saved experimental inputs.
        for label, trial, box in [('unshifted',unshifted,unshifted['crop_box']),('shift-old',baseline,old_shift),('shift-new',shifted,shifted['crop_box'])]:
            for side, im in zip(['reference','target'],ims):
                inp = input_image(manifest,np.asarray(im.crop(box),dtype='float32')/255)
                assert hashlib.sha256(inp.tobytes()).hexdigest() == trial[side]['input_sha256']
                inp.save(OUT/f'{n}-{label}-{side}.png')
        full = Image.new('RGB',(1040,570),'#f5f8f9');d=ImageDraw.Draw(full)
        for i, im in enumerate(ims):
            thumb=im.convert('RGB');thumb.thumbnail((500,500))
            full.paste(thumb,(20+i*520,50));k=thumb.width/im.width
            d.rectangle([20+i*520+region[0]*k,50+region[1]*k,20+i*520+region[2]*k,50+region[3]*k],outline=ORANGE,width=3)
            d.text((20+i*520,15),'完整參照圖' if i==0 else '完整待測圖',font=font(22),fill=INK)
        full.save(OUT/f'{n}-location.png')
        rec=dict(number=n,key=z['key'],name=z['name'],machine=z['machine'],title=titles[n],source=str(src),
                 candidate=candidate,formal_crop=formal,recenter_unshifted=unshifted['crop_box'],display_region=region,
                 shift=[shifted['dx'],shifted['dy']],old_experiment_crop=old_shift,new_experiment_crop=shifted['crop_box'],
                 old_pair=baseline,new_pair=shifted)
        records.append(rec)
        body.append(f'<section id="case-{n}"><h2>{titles[n]} · {z["machine"]}／位置 {z["id"]}</h2>'
                    f'<p class="file">{html.escape(z["name"])}</p><p><b>先看未偏移的比較：</b>左邊原圖不畫框，方便檢查輪廓有沒有被線條遮住。</p>'
                    f'<a href="{n}-original.png"><img src="{n}-original.png"></a><div class="finding" id="finding-{n}">{{FINDING_{n}}}</div>'
                    f'<h3>實際偏移測試的前後框</h3><p>此處藍框是上一輪「已縮小的實驗框」直接偏移，不是正式版原取圖。兩者不能混稱原框。</p>'
                    f'<a href="{n}-shift.png"><img src="{n}-shift.png"></a><p>{{SHIFT_{n}}}</p>'
                    '<details><summary>看前輪保存的判斷與實際小圖（不是本輪重跑）</summary>'
                    f'<p>藍框：參照{label_word(baseline["reference"])}、待測{label_word(baseline["target"])}；'
                    f'橘框：參照{label_word(shifted["reference"])}、待測{label_word(shifted["target"])}。</p>'
                    + ''.join(f'<figure><figcaption>{caption}</figcaption><img class="small" src="{n}-{which}-{side}.png"></figure>' for which,side,caption in [('shift-old','reference','偏移前法：參照'),('shift-old','target','偏移前法：待測'),('shift-new','reference','重新定位：參照'),('shift-new','target','重新定位：待測')])
                    + '</details><details><summary>看完整照片中的位置與座標</summary>'
                    f'<img src="{n}-location.png"><pre>{html.escape(json.dumps({k:rec[k] for k in ["candidate","formal_crop","recenter_unshifted","shift","old_experiment_crop","new_experiment_crop"]},ensure_ascii=False,indent=2))}</pre>'
                    f'<p><a href="{(src/"reference.png").as_uri()}">完整參照原圖</a> · <a href="{(src/"aligned.png").as_uri()}">完整待測原圖（已對齊）</a></p></details><p><a href="#top">返回四例總覽</a></p></section>')
    # Findings were written after inspecting all four original and shifted overlays.
    template='''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>四個案例：原框與重新定位框</title><style>
    body{margin:0;background:#f4f7f8;color:#173e4b;font:19px/1.7 "Microsoft JhengHei",sans-serif}main{max-width:1550px;margin:auto;padding:24px}h1{font-size:32px}h2{font-size:27px}a{color:#007d8b}nav{display:flex;gap:24px;flex-wrap:wrap}section{background:white;margin:30px 0;padding:24px;border:1px solid #d6e0e5;border-radius:12px}img{width:100%;height:auto}figure{display:inline-block;margin:8px}.small{width:224px}.file{font-size:15px;overflow-wrap:anywhere}.finding,.answer{background:#edf5f6;padding:20px;border-left:5px solid #087d88}summary{cursor:pointer;padding:12px}pre{font-size:14px;white-space:pre-wrap}
    </style><main id="top"><h1>框的位置真的比較正確嗎？先看這四個案例</h1><nav><a href="#case-1">斜螺絲</a><a href="#case-2">圓頭螺絲</a><a href="#case-4">線材</a><a href="#case-12">板件邊界</a></nav>
    <p>本頁只把前輪已保存的座標畫回原圖。未重跑差分或 DINO，未更動正式流程、模型、設定與人工紀錄。</p>
    <div class="answer">{CONCLUSION}</div><p><b>紅框：</b>差分提出的候選位置。<b>藍框：</b>原正式版裁圖範圍（候選向外加 12 像素）。<b>橘框：</b>實驗重新定位後的取圖範圍。藍框內的長方形還會經 DINO 縮放、中央裁切；它不等於畫面紅框。</p>
    <p>每組使用同一份已對齊原圖、同一位置與倍率，未調整亮度或銳化；放大採原像素顯示。第二組偏移圖另有圖例，避免把實驗框當成正式框。</p>{BODY}
    <p>本頁為指定四例的取圖核對，不是全圖資準確率報告。類型沿用前輪分類；正常案例取自良品資料夾。<a href="coordinates.json">全部座標與前輪結果</a> · <a href="validation.json">完整性核對</a></p></main></html>'''.replace('{BODY}',''.join(body))
    findings = {
        1: '<b>看圖結論：原正式取圖已包含斜螺絲；新框主要是收緊背景。</b>紅色候選框只框住螺絲的一部分，但藍色 AI 取圖範圍原本已包住整顆。橘框由 41×39 縮成 28×28 像素，螺絲更占滿畫面，也更貼近框邊。因此不能把改善說成「補回原本沒截到的螺絲」。',
        2: '<b>看圖結論：原正式取圖已包含圓頭螺絲；新框較貼近外圈。</b>藍框 49×49，橘框 27×27 像素；主要排除了下方板件和較遠背景，沒有找回原先遺漏的另一部分螺絲。這支持「改變背景比例」，尚不能證明分類器真的理解了新增物件。',
        4: '<b>看圖結論：新框沒有只包住移動的線材，反而帶進更多周邊物件。</b>原正式框 39×30，未偏移的新框 52×52 像素。新框包括線材、左側深色結構及右上原有圓形結構的一部分。兩張都有原有結構，沒有看到本例新增螺絲的證據；不能把這個框稱為更正確的螺絲定位。',
        12: '<b>看圖結論：原候選是細長板邊，新框擴大到旁邊原有圓形結構。</b>原正式框 27×76，未偏移的新框 88×88 像素；它納入的黑色圓形結構，在參照圖和待測圖都存在。新框改變了關注的內容，不能因為包到圓形物件就稱為定位更正確。',
    }
    shifts = {
        1: '這裡用的是已經縮小過的實驗框：藍框向右 2 像素後，螺絲頭更靠近左邊界，部分外緣落到框外；橘框向左找回原取圖位置。這證明本例能補償小框偏移，不代表原正式大框原本沒有包含螺絲。',
        2: '這顆在前後實驗框都判對。重新定位只把向右移動的框移回較貼近圓形外圈的位置，沒有證明新增辨識能力。',
        4: '此處選的是「舊實驗法沒有誤報，新法有誤報」的一次：搜尋起點向左、向上各 2 像素。藍框 52×52，橘框 54×54，左上角相同，只往右、往下多取 2 像素。圖中看不出新增螺絲；小幅改框就改變判斷，顯示辨識仍不穩。',
        12: '此處選搜尋起點向上 2 像素的誤報。藍框 88×88，橘框 90×90；橘框往左、往下各多取 2 像素。兩張圖的圓形結構仍都存在。前輪結果卻從「兩圖都像螺絲」變成「只有待測像螺絲」；這是判斷翻轉，沒有圖像證據支持新增螺絲。',
    }
    conclusion = '<b>這次看圖後，應修正前面的說法：</b><ul><li>兩顆螺絲：原正式 AI 取圖已包含螺絲，新方法主要縮掉背景。</li><li>線材、板件：新方法擴大範圍，把原有的周邊結構也帶入。</li></ul><b>所以目前不能說它普遍定位更正確。</b>它改變了 DINO 看見的內容比例，部分案例受益，部分案例誤判。這是疊圖觀察，不是靠分數反推；確切造成分數翻轉的因素仍未證實。'
    template = template.replace('{CONCLUSION}', conclusion)
    for n in [1,2,4,12]:
        template = template.replace('{FINDING_'+str(n)+'}',findings[n]).replace('{SHIFT_'+str(n)+'}',shifts[n])
    assert not re.search(r'\{(?:FINDING|SHIFT|CONCLUSION|BODY)',template)
    (OUT/'index.html').write_text(template,encoding='utf-8')
    # A compact target-only overview for the chat; full paired images remain above.
    overview = Image.new('RGB',(1000,1600),'#f5f8f9');d=ImageDraw.Draw(overview)
    d.text((22,12),'原框和新框：直接看取圖範圍的改變',font=font(28),fill=INK)
    d.text((22,52),'以下為待測原圖局部；完整報告同時並排參照圖。',font=font(20),fill=INK)
    notes={1:'原框已包住螺絲，新框縮小背景',2:'原框已包住螺絲，新框貼近外圈',4:'新框放大，帶入周邊原有結構',12:'新框放大，帶入原有圓形結構'}
    for i,rec in enumerate(records):
        y=90+i*374;n=rec['number']
        im=Image.open(Path(rec['source'])/'aligned.png').convert('L')
        d.text((22,y),f'{rec["title"]}：{notes[n]}',font=font(22),fill=INK)
        for col,(caption,box,color) in enumerate([('藍：原正式 AI 取圖',rec['formal_crop'],BLUE),('橘：重新定位取圖',rec['recenter_unshifted'],ORANGE)]):
            x=70+col*480
            d.text((x,y+34),caption,font=font(20),fill=color)
            overview.paste(panel(im,rec['display_region'],box,color,size=290),(x,y+66))
    overview.save(OUT/'overview.png')
    (OUT/'coordinates.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(sha(Path(p))==h for p,h in before.items())
    (OUT/'preservation.json').write_text(json.dumps(dict(unchanged=True,files=before),ensure_ascii=False,indent=2),encoding='utf-8')
    missing=[];checked=0
    from urllib.parse import unquote, urlparse
    for link in re.findall(r'(?:src|href)="([^"]+)"',template):
        if link.startswith('#'):
            assert f'id="{link[1:]}"' in template
            continue
        if link=='validation.json':continue
        path=Path(unquote(urlparse(link).path).lstrip('/')) if link.startswith('file:') else OUT/link
        checked+=1
        if not path.is_file():missing.append(str(path))
    assert not missing,missing
    (OUT/'validation.json').write_text(json.dumps(dict(cases=4,original_overlays=4,shift_overlays=4,
        verified_input_images=24,links_checked=checked,missing=missing,protected_files=len(before),
        protected_unchanged=True,inference_runs=0,detection_runs=0,production_changes=False),indent=2),encoding='utf-8')
    print(json.dumps(dict(output=str(OUT),cases=len(records),verified_input_images=24,protected_files=len(before)),ensure_ascii=False))


def label_word(value):
    return '被判成螺絲' if value['screw'] else '被判成非螺絲'


if __name__=='__main__':
    main()
