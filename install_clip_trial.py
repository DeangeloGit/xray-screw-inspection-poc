"""Install the evaluated CLIP vision model and fixed text vectors; select via the UI afterwards."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import numpy as np
import onnxruntime as ort


def install(source, runtime):
    sys.path.insert(0,str(Path(runtime).resolve()))
    from tokenizers import Tokenizer
    from runtime_paths import MODEL_ROOT
    from model_manager import ModelManager
    from trial_clip_candidates import LABELS, DESCRIPTIONS, TEMPLATES
    source=Path(source)
    provenance=json.loads((source/'provenance.json').read_text())
    for item in provenance['files']:
        if hashlib.sha256((source/item['file']).read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('Downloaded model checksum mismatch: '+item['file'])
    tokenizer=Tokenizer.from_file(str(source/'tokenizer.json'))
    tokenizer.enable_padding(pad_id=49407,pad_token='<|endoftext|>')
    tokenizer.enable_truncation(max_length=77)
    prompts=[t.format(d) for d in DESCRIPTIONS for t in TEMPLATES]
    tokens=tokenizer.encode_batch(prompts)
    options=ort.SessionOptions();options.intra_op_num_threads=4
    session=ort.InferenceSession(str(source/'text_model_quantized.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
    feed={x.name:np.asarray([t.ids if x.name=='input_ids' else t.attention_mask for t in tokens],np.int64) for x in session.get_inputs()}
    text=session.run(None,feed)[0];text/=np.linalg.norm(text,axis=1,keepdims=True)
    text=text.reshape(len(LABELS),len(TEMPLATES),-1).mean(axis=1);text/=np.linalg.norm(text,axis=1,keepdims=True)
    processor=json.loads((source/'preprocessor_config.json').read_text())
    payload=(source/'vision_model_quantized.onnx').read_bytes()
    manifest=dict(schema_version=1,model_id='CLIP ViT-B/32 較緊裁圖試用版',backend='clip_onnx',
                  preprocessing='aligned-gray-tight12-v1',classes=LABELS,input_size=[224,224],
                  file='model.onnx',sha256=hashlib.sha256(payload).hexdigest(),provider_policy='cpu',
                  mean=processor['image_mean'],std=processor['image_std'],text_embeddings=text.tolist(),
                  prompts=prompts,source=provenance,license='MIT (upstream model card)',output='image_embeddings')
    version='clip-tight-'+hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()[:12]
    directory=MODEL_ROOT/version
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'model.onnx').write_bytes(payload)
    (directory/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    snapshot=ModelManager(MODEL_ROOT,allow_cpu=True).snapshot(version)
    if snapshot.error:raise ValueError(snapshot.error)
    print(json.dumps(dict(directory=version,model=snapshot.info()),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir',required=True);parser.add_argument('--runtime-directory',required=True)
    args=parser.parse_args();install(args.model_dir,args.runtime_directory)
