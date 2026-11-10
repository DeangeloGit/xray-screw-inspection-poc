"""Configure an isolated 4r reference service without modifying an existing station."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--asset-root',type=Path,required=True);p.add_argument('--model-root',type=Path,required=True);p.add_argument('--reference',type=Path)
a=p.parse_args();home=a.home.expanduser().resolve();assets=a.asset_root.expanduser().resolve();models=a.model_root.expanduser().resolve()
if not (home/'example-versions/active.json').is_file():raise SystemExit('缺少已還原的 4r 圖庫版本')
if not (models/'active.json').is_file():raise SystemExit('缺少已還原 Lean DINO 模型')
if not (assets/'workspace/dino-4r-integrated-bank-20261106/curated_v5_review-bank.npz').is_file():raise SystemExit('缺少已還原 4r 特徵庫')
if a.reference and not a.reference.expanduser().is_file():raise SystemExit('指定的正常參考圖不存在')
config=dict(schema_version=1,workspace=str(home/'station'),model_root=str(models),asset_root=str(assets),default_provider='cpu',allow_cpu_fallback=True,acquisition=dict(source='',enabled=False))
if a.reference:config['reference']=str(a.reference.expanduser().resolve())
path=home/'settings.json'
with path.open('x',encoding='utf8') as f:json.dump(config,f,ensure_ascii=False,indent=2)
print('已建立隔離設定：'+str(path))
