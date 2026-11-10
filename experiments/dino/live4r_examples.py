"""Additive reference-bank editing for the isolated 4r experimental service."""
import copy,hashlib,io,json,os,re,shutil,tempfile,threading,uuid
from dataclasses import replace
from pathlib import Path
import numpy as np
from PIL import Image
from flask import jsonify,request,send_file
from datetime import datetime
from dino_examples import upload_image,png,actual_input
from dino_paired_optimized import example_features,validate_bank

BASE_ID='4r-curated-v5-review'
def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def save(p,obj):
 p=Path(p);tmp=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8');os.replace(tmp,p)
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
class LiveBanks:
 def __init__(self,base,original,snapshot,details,lock):
  self.root=Path(base)/'example-versions';self.root.mkdir(parents=True,exist_ok=True)
  self.pointer=self.root/'active.json';self.original=original;self.frozen=snapshot;self.details=details;self.lock=lock;self.loaded={}
  source=Path(os.environ.get('XRAY_4R_ASSET_ROOT',Path(__file__).resolve().parents[2])).expanduser().resolve()/'workspace/dino-4r-integrated-bank-20261106/active-reference-collection'
  self.base_source=source;data=read(source/'manifest.json');self.base_examples=[]
  ids=snapshot.manifest['example_bank']['screw']['ids']+snapshot.manifest['example_bank']['normal']['ids']
  assert len(data['examples'])==141 and len(ids)==141
  for i,row in enumerate(data['examples']):
   assert row['id']==ids[i] and digest(source/row['file'])==row['image_sha256']
   assert hashlib.sha256(snapshot.feature_bank[i].tobytes()).hexdigest()==row['feature_sha256']
   self.base_examples.append(dict(id=row['id'],label='screw' if i<51 else 'normal',name=row['id'],file=row['file'],sha256=row['image_sha256']))
  self.active=read(self.pointer)['version'] if self.pointer.exists() else BASE_ID
  self.current=self.load(self.active)[0]
 def version_dir(self,name):
  if not isinstance(name,str) or not re.fullmatch(r'4r-example-[a-f0-9]{32}',name):raise ValueError('範例版本不存在')
  p=(self.root/name).resolve()
  if p.parent!=self.root.resolve():raise ValueError('範例路徑錯誤')
  return p
 def load(self,name):
  if name==BASE_ID:
   snap=replace(self.frozen,requested=BASE_ID)
   return snap,dict(id=BASE_ID,name='4r 原始整合庫（51 螺絲＋90 正常）',examples=self.base_examples),self.base_source
  if name in self.loaded:return self.loaded[name]
  directory=self.version_dir(name);meta=read(directory/'version.json')
  if meta['id']!=name or digest(directory/'bank.npz')!=meta['bank_sha256']:raise ValueError('範例庫驗證失敗')
  examples=meta['examples'];ids=[x['id'] for x in examples];labels=[x['label'] for x in examples]
  if len(ids)!=len(set(ids)) or labels!=sorted(labels,key=lambda x:0 if x=='screw' else 1):raise ValueError('範例標籤或順序錯誤')
  old={r['id']:r['sha256'] for r in self.base_examples}
  if not all(any(x['id']==k and x['sha256']==h for x in examples) for k,h in old.items()):raise ValueError('原 4r 範例缺失')
  for row in examples:
   path=(directory/row['file']).resolve()
   if path.parent!=(directory/'images').resolve() or not path.is_file() or digest(path)!=row['sha256']:raise ValueError('範例圖片缺失或校驗失敗')
  with np.load(directory/'bank.npz',allow_pickle=False) as data:bank=data['bank'].copy()
  m=copy.deepcopy(self.frozen.manifest);screw=[x['id'] for x in examples if x['label']=='screw'];normal=[x['id'] for x in examples if x['label']=='normal']
  if len(screw)<51 or len(normal)<90:raise ValueError('原 4r 範例不足')
  m['example_bank']['screw']['ids']=screw;m['example_bank']['normal']['ids']=normal;m['model_id']=meta['name']+'（4r 實驗範例庫，未回歸驗證）';m['experimental_main_bank_sha256']=meta['bank_sha256']
  validate_bank(m,bank)
  fingerprint=hashlib.sha256((self.frozen.identity+'|'+meta['bank_sha256']).encode()).hexdigest()
  snap=replace(self.frozen,manifest=m,feature_bank=bank,identity=fingerprint,requested=name)
  self.loaded[name]=(snap,meta,directory)
  return self.loaded[name]
 def listing(self):
  result=[dict(directory=BASE_ID,name='4r 原始整合庫（51 螺絲＋90 正常）')]
  for p in sorted(self.root.glob('4r-example-*')):
   if not p.is_dir():continue
   try:_,m,_=self.load(p.name);result.append(dict(directory=p.name,name=m['name']+'（實驗）'))
   except (OSError,ValueError,KeyError):continue
  return result
 def select(self,name):
  with self.lock:
   self.loaded.pop(name,None)  # Revalidate every image and vector before activation.
   snap,meta,_=self.load(name)
   save(self.pointer,dict(version=name));self.current=snap;self.active=name
  return snap
 def build(self,parent,keep,title,files):
  if not isinstance(title,str) or not title.strip() or len(title)>80:raise ValueError('請填寫 1～80 字的新版名稱')
  if not isinstance(keep,list) or any(not isinstance(x,str) for x in keep) or len(set(keep))!=len(keep):raise ValueError('範例選擇不正確')
  additions=files['screw']+files['normal']
  if not 1<=len(additions)<=100:raise ValueError('請新增 1～100 張範例')
  with self.lock:
   parent_snap,meta,src=self.load(parent);existing=meta['examples']
   if set(keep)!={x['id'] for x in existing}:raise ValueError('本實驗只接受新增，請保留全部原有範例')
   used={r['sha256'] for r in existing};new=[]
   for label in ('screw','normal'):
    for upload in files[label]:
     im=upload_image(upload);data=png(im).getvalue();h=hashlib.sha256(data).hexdigest()
     if h in used:raise ValueError('新增圖片與現有範例重複')
     used.add(h);vector=example_features(parent_snap.manifest,parent_snap.session,np.asarray(im,np.float32)/255)
     new.append(dict(id='upload-'+h,label=label,name=Path(upload.filename.replace('\\','/')).name,sha256=h,data=data,vector=vector))
   n=sum(x['label']=='screw' for x in existing);b=parent_snap.feature_bank
   pos=[x for x in new if x['label']=='screw'];neg=[x for x in new if x['label']=='normal']
   def stack(rows):return np.stack([x['vector'] for x in rows]) if rows else np.empty((0,8,2,384),dtype=b.dtype)
   bank=np.concatenate((b[:n],stack(pos),b[n:],stack(neg)))
   vid='4r-example-'+uuid.uuid4().hex;stage=Path(tempfile.mkdtemp(prefix='.build-',dir=self.root));dest=self.root/vid
   try:
    (stage/'images').mkdir();rows=[]
    for row in existing:
     source=src/row['file'];filename=row['sha256']+'.png';shutil.copyfile(source,stage/'images'/filename)
     if digest(stage/'images'/filename)!=row['sha256']:raise ValueError('來源範例已變動')
     rows.append(dict(row,file='images/'+filename))
    newrows=[]
    for row in new:
     filename=row['sha256']+'.png';(stage/'images'/filename).write_bytes(row['data']);newrows.append({k:row[k] for k in ('id','label','name','sha256')}|{'file':'images/'+filename})
    rows=([x for x in rows if x['label']=='screw']+[x for x in newrows if x['label']=='screw']+[x for x in rows if x['label']=='normal']+[x for x in newrows if x['label']=='normal'])
    np.savez_compressed(stage/'bank.npz',bank=bank)
    save(stage/'version.json',dict(id=vid,name=title.strip(),parent=parent,examples=rows,bank_sha256=digest(stage/'bank.npz'),regression_verified=False))
    os.rename(stage,dest);self.load(vid)
   finally:
    if stage.exists():shutil.rmtree(stage)
  return vid,len(pos),len(neg)
 def register(self,app,manager):
  def listing():
   try:
    name=request.args.get('model') or self.active;_,m,_=self.load(name)
    return jsonify(versions=self.listing(),selected=name,active=self.active,examples=[dict(id=x['id'],label=x['label'],name=x['name'],available=True) for x in m['examples']],name=m['name'])
   except (ValueError,OSError,KeyError) as e:return jsonify(error=str(e)),400
  def image():
   try:
    _,m,src=self.load(request.args.get('model'));item=next((x for x in m['examples'] if x['id']==request.args.get('id')),None)
    if item is None:raise ValueError('範例不存在')
    image_path=src/item['file']
    if digest(image_path)!=item['sha256']:raise ValueError('範例圖片已變動')
    with Image.open(image_path) as im:
     im=im.convert('RGB')
     if request.args.get('view')=='input':im=actual_input(self.frozen.manifest,np.asarray(im.convert('L'),np.float32)/255)
     else:im.thumbnail((800,800))
     return send_file(png(im),mimetype='image/png',max_age=0)
   except (ValueError,OSError,KeyError) as e:return jsonify(error=str(e)),400
  def preview():
   try:
    self.load(request.form.get('model'));im=upload_image(request.files['image']);return send_file(png(actual_input(self.frozen.manifest,np.asarray(im,np.float32)/255)),mimetype='image/png')
   except (ValueError,OSError,KeyError) as e:return jsonify(error=str(e)),400
  def build():
   try:
    vid,p,n=self.build(request.form.get('model'),json.loads(request.form.get('keep','null')),request.form.get('name',''),{k:request.files.getlist(k) for k in ('screw','normal')})
    return jsonify(directory=vid,message=f'已建立 4r 實驗庫（新增螺絲 {p}、正常 {n}）；尚未啟用，也尚未回歸驗證。請檢視後按切換。')
   except (ValueError,OSError,KeyError,TypeError) as e:return jsonify(error=str(e)),400
  def select():
   try:
    body=request.get_json(silent=True) or {};snap=self.select(body.get('directory'))
    return jsonify(applied=True,model=snap.info(),message='已切換 4r 實驗庫；重新試算才會使用。新增版本尚未驗證原有命中與誤報。')
   except (ValueError,OSError,KeyError,TypeError) as e:return jsonify(error='未切換：'+str(e)),400
  def models():return jsonify(models=[dict(directory=x['directory'],model_id=x['name'],backend='dino_onnx') for x in self.listing()])
  def quick_status():
   current=self.current
   return jsonify(active=self.active,name=current.manifest['model_id'],screw=len(current.manifest['example_bank']['screw']['ids']),normal=len(current.manifest['example_bank']['normal']['ids']),regression_verified=self.active==BASE_ID)
  def quick_add():
   try:
    kind=request.form.get('kind')
    if kind not in ('screw','normal'):raise ValueError('請選擇螺絲或正常範例')
    uploads=request.files.getlist('images')
    if not uploads or any(not f.filename for f in uploads):raise ValueError('請選擇至少一張圖片')
    with self.lock:
     parent=self.active;_,meta,_=self.load(parent)
     title='4r 新增'+('螺絲' if kind=='screw' else '正常')+'範例 '+datetime.now().strftime('%Y-%m-%d %H:%M:%S')
     files={'screw':uploads if kind=='screw' else [],'normal':uploads if kind=='normal' else []}
     vid,p,n=self.build(parent,[x['id'] for x in meta['examples']],title,files)
     snap=self.select(vid)
    return jsonify(applied=True,version=vid,name=snap.manifest['model_id'],screw=len(snap.manifest['example_bank']['screw']['ids']),normal=len(snap.manifest['example_bank']['normal']['ids']),fingerprint=snap.identity,regression_verified=False,message='已新增並啟用，之後檢測與重啟會使用此版本；既有照片需重新試算。尚未完成命中與誤報回歸。')
   except (ValueError,OSError,KeyError,TypeError) as e:return jsonify(error='未啟用：'+str(e)),400
  def quick_script():
   return send_file(Path(__file__).with_name('live4r_quick_add.js'),mimetype='application/javascript',max_age=0)
  app.add_url_rule('/api/4r/examples/status','live4r_quick_status',quick_status,methods=['GET'])
  app.add_url_rule('/api/4r/examples/add-and-activate','live4r_quick_add',quick_add,methods=['POST'])
  app.add_url_rule('/4r/quick-add.js','live4r_quick_script',quick_script,methods=['GET'])
  app.view_functions['dino_examples.listing']=listing;app.view_functions['dino_examples.image']=image;app.view_functions['dino_examples.preview']=preview;app.view_functions['dino_examples.build']=build
  app.view_functions['settings_api.select_installed_model']=select;app.view_functions['settings_api.installed_models']=models
  manager.snapshot=lambda version_directory=None:self.load(version_directory)[0] if version_directory else self.current
