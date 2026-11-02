"""Offline CLIP trial on production candidate crops; never activates a model or filters candidates.

Usage: python trial_clip_candidates.py --cases cases.json --model-dir MODEL --output OUT
Optional --runtime-directory points to an isolated tokenizers installation.
"""
import argparse
import hashlib
import importlib.metadata
import html
import json
from pathlib import Path
import sys
import time

import numpy as np
import onnxruntime as ort
from PIL import Image

LABELS = ['screw', 'cable', 'circuit_board', 'metal_plate', 'hole', 'background']
DESCRIPTIONS = ['a metal screw', 'an electrical cable', 'an electronic circuit board',
                'a metal plate', 'a circular hole', 'an image background']
TEMPLATES = ['a close up photo of {}.', 'a close up x ray image of {}.']


def run(args):
    if args.runtime_directory:
        sys.path.insert(0, str(Path(args.runtime_directory).resolve()))
    from tokenizers import Tokenizer
    from detector import detect
    model = Path(args.model_dir)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    provenance = json.loads((model/'provenance.json').read_text())
    for item in provenance['files']:
        assert hashlib.sha256((model/item['file']).read_bytes()).hexdigest() == item['sha256'], item['file']
    processor = json.loads((model/'preprocessor_config.json').read_text())
    tokenizer = Tokenizer.from_file(str(model/'tokenizer.json'))
    tokenizer.enable_padding(pad_id=49407, pad_token='<|endoftext|>')
    tokenizer.enable_truncation(max_length=77)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 1
    sessions = {kind: ort.InferenceSession(str(model/f'{kind}_model_quantized.onnx'),
                sess_options=options, providers=['CPUExecutionProvider']) for kind in ('vision','text')}
    prompts = [template.format(description) for description in DESCRIPTIONS for template in TEMPLATES]
    tokens = tokenizer.encode_batch(prompts)
    ids = np.asarray([x.ids for x in tokens], dtype=np.int64)
    masks = np.asarray([x.attention_mask for x in tokens], dtype=np.int64)
    feed = {x.name: ids if x.name=='input_ids' else masks for x in sessions['text'].get_inputs()}
    embeddings = sessions['text'].run(None, feed)[0]
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings.reshape(len(LABELS),len(TEMPLATES),-1).mean(axis=1)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    mean = np.asarray(processor['image_mean'], np.float32)
    std = np.asarray(processor['image_std'], np.float32)
    size = processor['crop_size']['height']
    def encode_image(path):
        image = Image.open(path).convert('RGB')
        # Official shortest-edge resize followed by centre crop.
        width, height = image.size
        shortest = processor['size']['shortest_edge']
        new_size = (shortest, int(shortest*height/width)) if width<=height else (int(shortest*width/height), shortest)
        image = image.resize(new_size, Image.Resampling.BICUBIC)
        left, top = (image.width-size)//2, (image.height-size)//2
        image = image.crop((left,top,left+size,top+size))
        values = (np.asarray(image,dtype=np.float32)/255-mean)/std
        values = values.transpose(2,0,1)[None]
        embedding = sessions['vision'].run(None, {'pixel_values':values})[0][0]
        return embedding/np.linalg.norm(embedding)
    report = dict(model=provenance, labels=LABELS, prompts=prompts,
                  runtime_versions={name:importlib.metadata.version(name) for name in ('onnxruntime','numpy','Pillow','tokenizers')},
                  mode='offline-only', crop_mode=args.crop_mode, score_semantics='cosine similarity and screw-minus-best-other margin; not probabilities',
                  limitation='Known regions are provisional positives only. Other candidates are unlabelled, not negatives. No accuracy or precision estimate.',
                  samples=[])
    panels=[]
    for case in json.loads(Path(args.cases).read_text(encoding='utf-8')):
        directory=output/case['name'];directory.mkdir(exist_ok=True)
        if args.cached_detection_root:
            import shutil
            cached=Path(args.cached_detection_root)/case['name']
            result=json.loads((cached/'result.json').read_text(encoding='utf-8'))
            for filename in ('aligned.png',):
                shutil.copy2(cached/filename,directory/filename)
            if args.crop_mode=='source':
                for c in result['candidates']:
                    filename=f"crop_{c['id']}.png"
                    shutil.copy2(cached/filename,directory/filename)
        else:
            result=detect(case['reference'],case['target'],case['name'],case['threshold'],output_directory=directory)
        if args.crop_mode=='aligned-tight':
            aligned=Image.open(directory/'aligned.png')
            for c in result['candidates']:
                x,y,w,h=(c[k] for k in ('x','y','w','h'))
                patch=aligned.crop((max(0,x-12),max(0,y-12),min(aligned.width,x+w+12),min(aligned.height,y+h+12)))
                patch.save(directory/f"crop_{c['id']}.png")
        start=time.monotonic(); rows=[]
        for c in result['candidates']:
            scores=encode_image(directory/f"crop_{c['id']}.png") @ embeddings.T
            known=[]
            for index,(x0,y0,x1,y1) in enumerate(case.get('known_regions',[]),1):
                if c['x']<x1 and c['y']<y1 and c['x']+c['w']>x0 and c['y']+c['h']>y0:
                    known.append(index)
            rows.append(dict(candidate_id=c['id'], label=LABELS[int(scores.argmax())],
                        scores=dict(zip(LABELS,map(float,scores))), screw_margin=float(scores[0]-max(scores[1:])),
                        known_regions=known, crop=f"{case['name']}/crop_{c['id']}.png"))
        rows.sort(key=lambda r:r['screw_margin'],reverse=True)
        for rank,row in enumerate(rows,1):row['rank']=rank
        hits=[]
        for index in range(1,len(case.get('known_regions',[]))+1):
            matched=[r for r in rows if index in r['known_regions']]
            hits.append(dict(region=index,candidate_ids=[r['candidate_id'] for r in matched],
                             best_rank=min((r['rank'] for r in matched),default=None),
                             predicted_screw=any(r['label']=='screw' for r in matched)))
        sample=dict(name=case['name'],threshold=case['threshold'],detector_version=result['version'],
                    count=len(rows),predicted_screw_count=sum(r['label']=='screw' for r in rows),
                    inference_seconds=round(time.monotonic()-start,2),known_regions=hits,candidates=rows)
        report['samples'].append(sample)
        print(json.dumps({k:v for k,v in sample.items() if k!='candidates'}),flush=True)
        cards=[]
        for row in rows:
            mark=' / KNOWN REGION '+','.join(map(str,row['known_regions'])) if row['known_regions'] else ' / unlabelled'
            cards.append(f"<article><b>Rank {row['rank']} / #{row['candidate_id']}{mark}</b><img loading='lazy' src='{html.escape(row['crop'])}'><p>{row['label']} / screw margin {row['screw_margin']:.4f}</p></article>")
        panels.append(f"<h2>{html.escape(case['name'])}: {sample['predicted_screw_count']} screw predictions / {len(rows)} candidates</h2><section>{''.join(cards)}</section>")
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'report.html').write_text("<!doctype html><meta charset='utf-8'><title>CLIP candidate trial</title><style>body{font:16px system-ui;margin:24px;background:#f2f5f7}section{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}article{background:white;padding:12px}img{display:block;width:100%;height:190px;object-fit:contain}</style><h1>Offline CLIP trial</h1><p>候選不刪除。分數為相似度，非螺絲機率；KNOWN REGION 為先前圈選位置，其他候選尚未標註。所有運算在本機進行。</p>"+''.join(panels),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for argument in ('cases','model-dir','output'):parser.add_argument('--'+argument,required=True)
    parser.add_argument('--runtime-directory')
    parser.add_argument('--crop-mode',choices=['source','aligned-tight'],default='source')
    parser.add_argument('--cached-detection-root')
    run(parser.parse_args())
