"""Isolated API integration: original bank preservation, upload/preview/build/select/rollback."""
import sys,os,json,tempfile,subprocess,shutil,io,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
def child():
    from runtime_paths import MODEL_ROOT,RESOURCE_ROOT
    from flask import Flask
    from PIL import Image,ImageDraw
    import numpy as np
    from dino_examples import dino_examples
    from settings_api import settings_api
    from dino_adapter import embedding
    from model_manager import ModelManager
    version='dino-examples-a3b8c97aa539';source=ROOT/'models'/version;p=MODEL_ROOT/version
    shutil.copytree(source,p);(MODEL_ROOT/'active.json').write_text(json.dumps(dict(schema_version=1,version_directory=version)))
    active=(MODEL_ROOT/'active.json').read_bytes();original=(p/'manifest.json').read_bytes()
    app=Flask(__name__,template_folder=str(RESOURCE_ROOT/'templates'));app.register_blueprint(dino_examples);app.register_blueprint(settings_api)
    app.config['TESTING']=True
    im=Image.new('L',(60,80),160);ImageDraw.Draw(im).line((12,65,48,12),fill=25,width=8)
    buf=io.BytesIO();im.save(buf,format='PNG');image=buf.getvalue()
    with app.test_client() as client:
        listing=client.get('/api/dino/examples').json;assert len(listing['examples'])==96
        assert all(z['available'] for z in listing['examples']);ids=[z['id'] for z in listing['examples']]
        assert client.get('/engineer/dino-examples').status_code==200
        assert client.get('/api/dino/examples?model=../escape').status_code==400
        r=client.get('/api/dino/image',query_string=dict(model=version,id=ids[0],view='input'));assert Image.open(io.BytesIO(r.data)).size==(224,224)
        r=client.post('/api/dino/preview',data=dict(model=version,image=(io.BytesIO(image),'test.png')));assert r.status_code==200
        assert Image.open(io.BytesIO(r.data)).size==(224,224)
        assert client.post('/api/dino/preview',data=dict(model=version,image=(io.BytesIO(b'bad'),'bad.png'))).status_code==400
        assert client.post('/api/dino/build',data=dict(model=version,name='invalid',keep='[]')).status_code==400
        assert client.post('/api/dino/build',data=dict(model=version,name='invalid',keep=json.dumps(ids+['unknown']))).status_code==400
        # Invalid upload must not expose a partial version or touch the active model.
        r=client.post('/api/dino/build',data=dict(model=version,name='invalid',keep=json.dumps(ids),screw=(io.BytesIO(b'bad'),'bad.png')));assert r.status_code==400,r.json
        assert not list(MODEL_ROOT.glob('.build-*'))
        retained=ids[1:]
        r=client.post('/api/dino/build',data=dict(model=version,name='測試新版',keep=json.dumps(retained),screw=(io.BytesIO(image),'現場螺絲.png')))
        assert r.status_code==200,r.json;new=r.json['directory'];m=json.loads((MODEL_ROOT/new/'manifest.json').read_text(encoding='utf-8'))
        assert len(m['example_bank']['screw']['ids'])==31 and len(m['example_bank']['normal']['ids'])==65
        assert ids[0] not in m['example_bank']['screw']['ids']
        assert (MODEL_ROOT/'active.json').read_bytes()==active and (p/'manifest.json').read_bytes()==original
        snap=ModelManager(MODEL_ROOT,allow_cpu=True).snapshot(new);assert not snap.error,snap.error
        vec=embedding(m,snap.session,np.asarray(im,np.float32)/255)
        assert np.allclose(vec,m['example_bank']['screw']['embeddings'][-1],atol=1e-6)
        # Persistence and copied images do not depend on the uploaded temporary file.
        r=client.get('/api/dino/examples',query_string=dict(model=new));assert len(r.json['examples'])==96 and all(z['available'] for z in r.json['examples'])
        assert client.get('/api/dino/image',query_string=dict(model=new,id=m['example_bank']['screw']['ids'][-1])).status_code==200
        r=client.post('/api/settings/models/select',json=dict(directory=new));assert r.status_code==200,r.json
        assert ModelManager(MODEL_ROOT,allow_cpu=True).snapshot().requested==new
        assert client.post('/api/settings/models/select',json=dict(directory=version)).status_code==200
        assert ModelManager(MODEL_ROOT,allow_cpu=True).snapshot().requested==version
    print('PASS: 96 images; exact previews; invalid paths/images/counts; rollback on failed build; new bank vectors; persistence; explicit activation and switch-back',flush=True)
if __name__=='__main__':
    if '--child' in sys.argv:child()
    else:
        active=(ROOT/'models/active.json').read_bytes()
        with tempfile.TemporaryDirectory(prefix='xray-examples-') as tmp:
            root=Path(tmp);(root/'models').mkdir();config=root/'station.json';config.write_text(json.dumps(dict(workspace=str(root/'work'),model_root=str(root/'models'),allow_cpu_fallback=True,default_provider='cpu')))
            env=dict(os.environ,XRAY_CONFIG=str(config),XRAY_WORKSPACE=str(root/'work'));subprocess.run([sys.executable,__file__,'--child'],env=env,cwd=ROOT,check=True)
        assert (ROOT/'models/active.json').read_bytes()==active
