"""Versioned DINO example editing. Building never selects or edits the source model."""
import copy,hashlib,io,json,os,shutil,threading,uuid
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps,UnidentifiedImageError
from flask import Blueprint,jsonify,request,send_file,render_template
from runtime_paths import MODEL_ROOT,RESOURCE_ROOT
from model_manager import ModelManager,manager
from dino_adapter import embedding,input_image

dino_examples=Blueprint('dino_examples',__name__)
build_lock=threading.Lock()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def model(name):
    if not isinstance(name,str) or not name or name.startswith('.') or '/' in name or '\\' in name or ':' in name:raise ValueError('模型名稱不正確')
    p=(MODEL_ROOT/name).resolve()
    if p.parent!=MODEL_ROOT.resolve():raise ValueError('模型路徑不正確')
    m=read(p/'manifest.json')
    if m.get('backend')!='dino_onnx':raise ValueError('請選擇 DINO 模型')
    return p,m
def entries(p,m):
    meta=read(p/'examples.json') if (p/'examples.json').exists() else {}
    result=[]
    for label in ('screw','normal'):
        for name in m['example_bank'][label]['ids']:
            z=meta.get(name)
            result.append(dict(id=name,label=label,available=bool(z),name=z.get('name',name) if z else name))
    return result
def source(p,name):
    meta=read(p/'examples.json');z=meta.get(name)
    if not z:raise ValueError('這個舊版沒有保存範例圖片，不能重建此範例')
    file=(p/'examples'/z['file']).resolve()
    if file.parent!=(p/'examples').resolve():raise ValueError('範例路徑不正確')
    if hashlib.sha256(file.read_bytes()).hexdigest()!=z['sha256']:raise ValueError('範例圖片已變動，請重新檢查')
    return file,z
def upload_image(file):
    data=file.read(8*1024*1024+1)
    if len(data)>8*1024*1024:raise ValueError('每張範例最大 8 MB')
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.width*im.height>16_000_000 or min(im.size)<8:raise ValueError('請使用至少 8×8、最多 1600 萬像素的裁圖')
            if getattr(im,'n_frames',1)!=1:raise ValueError('請上傳單張圖片')
            return ImageOps.exif_transpose(im).convert('L').copy()
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as e:raise ValueError('無法讀取圖片，請使用 PNG、JPG 或單頁 TIFF') from e
def png(im):
    b=io.BytesIO();im.save(b,format='PNG');b.seek(0);return b
@dino_examples.get('/engineer/dino-examples')
def page():return render_template('dino_examples.html')
@dino_examples.get('/api/dino/examples')
def listing():
    try:
        versions=[]
        for p in sorted(MODEL_ROOT.iterdir()):
            if p.name.startswith('.') or not p.is_dir():continue
            try:
                _,m=model(p.name);versions.append(dict(directory=p.name,name=m['model_id']))
            except (ValueError,OSError,KeyError):continue
        active=manager.snapshot().requested
        name=request.args.get('model') or (active if any(v['directory']==active for v in versions) else versions[0]['directory'] if versions else '')
        p,m=model(name)
        return jsonify(versions=versions,selected=name,active=active,examples=entries(p,m),name=m['model_id'])
    except (ValueError,OSError,KeyError) as e:return jsonify(error=str(e)),400
@dino_examples.get('/api/dino/image')
def image():
    try:
        p,m=model(request.args.get('model'));name=request.args.get('id')
        if name not in {z['id'] for z in entries(p,m)}:raise ValueError('範例不存在')
        file,_=source(p,name)
        with Image.open(file) as im:
            im=im.convert('RGB')
            if request.args.get('view')=='input':im=input_image(m,np.asarray(im,np.float32)/255)
            else:im.thumbnail((800,800))
            return send_file(png(im),mimetype='image/png',max_age=0)
    except (ValueError,OSError,KeyError) as e:return jsonify(error=str(e)),400
@dino_examples.post('/api/dino/preview')
def preview():
    try:
        _,m=model(request.form.get('model'));im=upload_image(request.files['image'])
        return send_file(png(input_image(m,np.asarray(im,np.float32)/255)),mimetype='image/png')
    except (ValueError,OSError,KeyError) as e:return jsonify(error=str(e)),400
@dino_examples.post('/api/dino/build')
def build():
    if not build_lock.acquire(blocking=False):return jsonify(error='正在建立範例庫，請稍候'),409
    staging=None
    try:
        p,m=model(request.form.get('model'));keep=json.loads(request.form.get('keep','null'));title=request.form.get('name','').strip()
        if not title or len(title)>80:raise ValueError('請填寫 1～80 字的新版名稱')
        if not isinstance(keep,list) or not all(isinstance(x,str) for x in keep) or len(keep)!=len(set(keep)):raise ValueError('範例選擇不正確')
        allids={z['id'] for z in entries(p,m)}
        if not set(keep)<=allids:raise ValueError('選取了不存在的範例')
        files={label:request.files.getlist(label) for label in ('screw','normal')}
        if sum(map(len,files.values()))>100:raise ValueError('每次最多新增 100 張')
        for label in files:
            count=sum(n in keep for n in m['example_bank'][label]['ids'])+len(files[label])
            if not 3<=count<=500:raise ValueError('螺絲與非螺絲各需保留 3～500 張範例')
        snapshot=ModelManager(MODEL_ROOT,allow_cpu=True).snapshot(p.name)
        if snapshot.error:raise ValueError(snapshot.error)
        token='dino-examples-'+uuid.uuid4().hex[:16];staging=MODEL_ROOT/('.build-'+token);staging.mkdir();(staging/'examples').mkdir()
        new=copy.deepcopy(m);new['model_id']=title;new['example_bank']={};meta={};seen={}
        for label in ('screw','normal'):
            ids=[];vectors=[];bank=m['example_bank'][label]
            for n,v in zip(bank['ids'],bank['embeddings']):
                if n not in keep:continue
                file,z=source(p,n);sha=z['sha256']
                if sha in seen:raise ValueError('範例內容重複，請取消重複圖片（也不可在兩類同時使用）')
                seen[sha]=label;dest=hashlib.sha256(n.encode()).hexdigest()+'.png';shutil.copyfile(file,staging/'examples'/dest)
                meta[n]=dict(z,file=dest);ids.append(n);vectors.append(v)
            for file in files[label]:
                im=upload_image(file);data=png(im).getvalue();sha=hashlib.sha256(data).hexdigest()
                if sha in seen:raise ValueError('新增圖片重複，或與現有範例重複，請移除重複圖片')
                seen[sha]=label;n='upload-'+sha;dest=n+'.png';(staging/'examples'/dest).write_bytes(data)
                vector=embedding(m,snapshot.session,np.asarray(im,np.float32)/255)
                meta[n]=dict(file=dest,sha256=sha,name=Path(file.filename.replace('\\','/')).name)
                ids.append(n);vectors.append(vector.tolist())
            new['example_bank'][label]=dict(ids=ids,embeddings=vectors)
        new['provenance']=dict(parent=p.name,method='user-edited-examples',note='Not evaluated on independent test images; not automatically activated')
        new['file']='model.onnx';shutil.copyfile(p/m['file'],staging/'model.onnx')
        (staging/'manifest.json').write_text(json.dumps(new,ensure_ascii=False),encoding='utf-8');(staging/'examples.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf-8')
        # Validate under a private parent before making the new version visible.
        checkparent=staging/'validation';checkparent.mkdir();os.rename(staging/'manifest.json',checkparent/'manifest.json');os.rename(staging/'model.onnx',checkparent/'model.onnx')
        candidate=ModelManager(staging,allow_cpu=True).snapshot('validation')
        if candidate.error:raise ValueError(candidate.error)
        os.rename(checkparent/'manifest.json',staging/'manifest.json');os.rename(checkparent/'model.onnx',staging/'model.onnx');checkparent.rmdir()
        os.rename(staging,MODEL_ROOT/token);staging=None
        return jsonify(directory=token,message='新版已建立，尚未啟用。可先檢查圖片，再選擇使用；舊版仍可切回。')
    except (ValueError,OSError,KeyError,TypeError) as e:return jsonify(error=str(e)),400
    finally:
        if staging is not None and staging.exists():shutil.rmtree(staging)
        build_lock.release()

if __name__=='__main__':
    from flask import Flask
    from settings_api import settings_api
    app=Flask(__name__,template_folder=str(RESOURCE_ROOT/'templates'),static_folder=str(RESOURCE_ROOT/'static'))
    app.config['MAX_CONTENT_LENGTH']=40*1024*1024
    app.register_blueprint(dino_examples);app.register_blueprint(settings_api)
    app.run(host='127.0.0.1',port=18767,threaded=True,use_reloader=False)
