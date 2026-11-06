"""Export every active reference with order, provenance, ROI and feature hashes."""
from integrated_bank_probe import ROOT,OUT,NEW,read,save
import argparse,hashlib,shutil,zipfile
import numpy as np
from PIL import Image

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--arm',required=True);a=ap.parse_args();summary=read(OUT/'final/summary.json');assert summary['acceptance_passed'] and summary['arm']==a.arm
    folder=OUT/'active-reference-collection';(folder/'images').mkdir(parents=True,exist_ok=True);model=ROOT/'models/dino-paired-optimized-47-20261104-r3';m=read(model/'manifest.json');ex=read(model/'examples.json');new={r['id']:r for r in read(NEW/'collection/manifest.json')['examples']};b=np.load(OUT/f'{a.arm}-bank.npz');ids=b['ids'].tolist();n=int(b['n']);rows=[];rects={'S07':[9,13,37,46],'S20':[13,15,42,49]}
    recipe=read(OUT/f'{a.arm}-recipe.json') if (OUT/f'{a.arm}-recipe.json').exists() else {}
    if a.arm.startswith('clean3') or 'S05' in recipe.get('original_positive_crop_ids',[]):rects['S05']=[11,11,43,41]
    for i,ident in enumerate(ids):
        rec=dict(id=ident,bank_index=i,label='screw' if i<n else 'non_screw',feature_sha256=hashlib.sha256(b['bank'][i].tobytes()).hexdigest(),file=f'images/{ident}.png')
        if ident.startswith('S') or ident.startswith('O-N'):
            orig_id=m['example_bank']['screw']['ids'][int(ident[1:])-1] if ident.startswith('S') else m['example_bank']['normal']['ids'][int(ident[3:])-1];source=model/'examples'/ex[orig_id]['file'];im=Image.open(source)
            if ident in rects:im=im.crop(rects[ident])
            im.save(folder/rec['file']);rec.update(original_id=orig_id,source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_rectangle=rects.get(ident),label_authority='original library label unchanged')
        else:
            z=new[ident];view=recipe.get('view_overrides',{}).get(ident,'context');source=__import__('pathlib').Path(z['views'][view]['file']);shutil.copy2(source,folder/rec['file']);rec.update(source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_rectangle=z['box'],raw_source=z['raw_source'],native_polygon=z['native_polygon'],family=z['family'],label_authority=z['authority'],view=view)
        rec['image_sha256']=hashlib.sha256((folder/rec['file']).read_bytes()).hexdigest();rows.append(rec)
    shutil.copy2(OUT/f'{a.arm}-bank.npz',folder/'main-bank.npz');manifest=dict(status='validated_4r_regression_with_known_scale_failure_not_production',arm=a.arm,positive=n,normal=len(ids)-n,examples=rows,inactive_positive_reference_ids=recipe.get('inactive_new_positive_ids',['P01','P04','P05','P11'] if a.arm=='clean3_selective' else ['P11'] if a.arm=='clean2_dedup' else []),inactive_normal_reference_ids=recipe.get('inactive_new_normal_ids',[]),inactive_label_unchanged=True,source_model=str(model),other_banks_unchanged=True,classification_integration_fix=recipe.get('classification_integration_fix'),validation_summary=summary,independent_new_scans=False);save(folder/'manifest.json',manifest)
    (folder/'README.txt').write_text('4r 整合參考例實驗包\n\n主庫例的順序、原始來源、實際範圍與SHA在manifest.json。原螺絲來源整理範圍仍保留螺絲標籤；移出主庫的正例仍保留於原案例集。\nmain-bank.npz供既有DINO雙圖分類實驗使用。其他B部位、完整輪廓及正常接點複核沿用既有副庫與判準；混合輪廓結果的整合修正依manifest記錄。\n本輪原尺寸回歸使用同批100張及固定候選，沒有新外部不良批次；正式設定與模型未啟用此實驗。額外影像縮放139/140，135 #88放大125%時原版及本版皆漏判，尚未解決，不能稱全部穩定性通過。\n',encoding='utf8')
    dest=OUT/'integrated-reference-collection.zip'
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
        for p in folder.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(folder))
    with zipfile.ZipFile(dest) as z:assert z.testzip() is None
    sha=hashlib.sha256(dest.read_bytes()).hexdigest();(OUT/'integrated-reference-collection.zip.sha256').write_text(sha+'  integrated-reference-collection.zip\n',encoding='ascii');save(OUT/'export-verification.json',dict(status='passed',positive=n,normal=len(ids)-n,source_images=len(rows),zip_sha256=sha,production_enabled=False));print('EXPORTED',n,len(ids)-n,sha,flush=True)
if __name__=='__main__':main()
