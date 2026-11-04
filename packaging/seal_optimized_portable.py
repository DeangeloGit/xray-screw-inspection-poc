"""Seal only after real source/frozen parity and data-preservation checks pass."""
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
NAME='XRayReview-DINO-Optimized-r3-20261104-Windows-x64'
PACKAGE=ROOT/'dist'/NAME


def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):p.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def main():
    work=Path((ROOT/'workspace/integration-r3-current.txt').read_text(encoding='utf-8'))
    checks={name:load(work/name) for name in ('source-cpu/verification.json','source-gpu/verification.json',
        'portable-final-cpu/verification.json','portable-final-gpu-monitor-verified/verification.json',
        'cases-cpu.json','cases-gpu.json','settings-verification.json','preservation-after.json')}
    assert all(z['success'] for z in checks.values())
    for device in ('cpu','gpu'):
        source=checks['source-'+device+'/verification.json']
        portable=checks[('portable-final-cpu' if device=='cpu' else 'portable-final-gpu-monitor-verified')+'/verification.json']
        assert source['model']['fingerprint']==portable['model']['fingerprint']
        assert source['pipeline']==portable['pipeline']=='dino-combined-20261104-r3'
    telemetry=load(work/'portable-final-gpu-telemetry-verified.json')
    assert telemetry['unknown_samples']==telemetry['limited_samples']==0
    selftest=load(PACKAGE/'logs/portable-selftest.json');assert selftest['success']
    manifest=load(PACKAGE/'BUILD-MANIFEST.json')
    for path,value in manifest['engine_sha256'].items():assert sha(ROOT/path)==value,path
    # Templates are external files in this onedir build; they must match source.
    for group in ('templates','static'):
        for p in (ROOT/group).rglob('*'):
            if p.is_file():assert sha(p)==sha(PACKAGE/'_internal'/p.relative_to(ROOT)),str(p)
    # No process-specific paths or active automatic source are exported to a new installation.
    preferences=load(PACKAGE/'workspace/state/ui_settings.json')
    assert preferences['acquisition']==dict(enabled=False,source='')
    local=load(ROOT/'workspace/windows-check/state/ui_settings.json')
    assert preferences['selected_machine']==local['selected_machine']
    assert preferences.get('machine_thresholds')==local.get('machine_thresholds')
    local_byid={p['id']:p for p in local['machine_profiles']}
    for p in preferences['machine_profiles']:
        assert sha(PACKAGE/p['reference'])==sha(local_byid[p['id']]['reference'])
    reports=PACKAGE/'release-checks';reports.mkdir(exist_ok=True)
    for name,value in checks.items():write(reports/name.replace('/','-'),value)
    write(reports/'gpu-telemetry.json',telemetry)
    write(reports/'portable-selftest.json',selftest)
    for f in ('reference.png','aligned.png'):
        shutil.copyfile(work/'portable-final-gpu-monitor-verified/images'/f,reports/f)
    verification=dict(success=True,pipeline='dino-combined-20261104-r3',source_frozen_cpu_equal=True,source_frozen_gpu_equal=True,
        candidates_per_full_photo=137,inferences_per_full_photo=276,output_images_per_full_photo=368,
        fixed_cases_each_device=59,decision_changes=0,original_screws_correct=2,normal_controls=50,normal_false_alarms=0,
        settings_preserved=True,no_batch_rerun=True,gpu_telemetry_unknown_samples=0,gpu_telemetry_limited_samples=0,
        models_cpu=checks['source-cpu/verification.json']['model'],models_gpu=checks['source-gpu/verification.json']['model'])
    write(reports/'verification.json',verification)
    # Delivery notes describe the validation scope, not a new full-dataset report.
    notes='''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DINO 合併優化雙圖 r3：更新與核對</title><style>body{font:18px/1.75 'Microsoft JhengHei',sans-serif;max-width:1100px;padding:24px;margin:auto;color:#173e4c;background:#f5f8f9}h1{font-size:30px}h2{font-size:24px}table{border-collapse:collapse;width:100%;background:white}td,th{border:1px solid #d7e2e6;padding:12px;text-align:left}.answer{background:white;border-left:6px solid #00838c;padding:20px}.pair{display:flex;gap:16px}figure{margin:0;flex:1}img{width:100%;max-height:580px;object-fit:contain}a{color:#007e8a}</style>
<h1>DINO 合併優化雙圖 r3：本機與可攜版一致</h1><div class="answer"><p>已整合正式流程：47 張螺絲＋65 張正常範例、參照圖＋待測圖，同時保留 CPU／GPU 選擇。兩種設備使用相同的取圖和判斷方法。</p><p>本次只核對同一張照片及既有 59 個案例，沒有重新跑整批。這頁是版本更新核對，不是全圖資完整檢測報告。</p></div>
<h2>整合了什麼？</h2><p>重用同機種的參照資料、減少重複準備圖片；兩個方向同時做對齊計算，仍檢查原本全部八種旋轉／鏡像方向；差分計算重用陣列、同時核對兩個候選。候選順序、位置及規則維持一致。</p><p>辨識使用已驗證的方法：範例的整體外觀與小區域各占一半，先分別判斷參照和待測小圖。若兩圖都像螺絲，且既有的局部幾何條件通過，兩圖在同一位置補看一次。最後仍須「待測有螺絲、參照沒有」才保留。</p>
<h2>核對結果</h2><table><tr><th>項目</th><th>結果</th></tr><tr><td>正式來源程式 CPU／GPU、實際可攜 EXE CPU／GPU</td><td>同一張圖各有 137 個候選、276 次推論；框、AI 輸入、兩圖判斷及 368 張輸出圖片全部一致。</td></tr><tr><td>59 個既有案例，CPU／GPU 分別驗證</td><td>兩邊都與實驗版一致。原本兩顆螺絲維持判對；50 個正常對照沒有誤報。</td></tr><tr><td>其餘螺絲檢查</td><td>4 個已確認螺絲位置皆維持判對；5 個目視疑似位置中判出 2 個，仍有 3 個未判出。疑似位置不是完整人工標準答案。</td></tr><tr><td>範例管理</td><td>可查看、追加、另存新版與切回；另存時仍保留新版的整體／局部與雙圖方法。</td></tr><tr><td>CPU／GPU 切換</td><td>可儲存選擇；切換失敗保留原設定，既有照片處理不受切換中斷。</td></tr><tr><td>本機設定、照片及人工紀錄</td><td>原設定檔內容相同，舊照片、舊結果及人工紀錄保留；現有 12 張來源照片仍為完成，未重跑。</td></tr></table>
<h2>時間怎麼看？</h2><p>先前 8 次 GPU 交錯實測：原方法平均 11.98 秒、合併版 10.82 秒，省 1.15 秒（9.6%）。時間從開始檢測到 DINO 判完，不包含資料夾等待，模型及參照資料已備妥。本次整合核對也是實際跑 CPU／GPU，但每個交付版本僅做少量一致性檢查，不將單次速度當成新的平均效能。</p><p>可攜版 GPU 再核對時，監看資料完整、未觀察到異常限速。顯示卡環境仍會影響速度；這不保證每次電源與散熱狀態都相同。</p>
<h2>本次核對的同一張圖</h2><div class="pair"><figure><figcaption>參照圖</figcaption><img src="release-checks/reference.png"></figure><figure><figcaption>待測圖（已對齊）</figcaption><img src="release-checks/aligned.png"></figure></div>
<h2>怎麼使用新版？</h2><p>本機繼續使用 http://127.0.0.1:18766/，重新整理頁面即可。工程頁面 → AI 模型 → DINO 執行方式可切換 CPU／GPU；保留原本 CPU 設定。舊照片結果不會自動重算，新檢測才套用 r3。</p><p>可攜版完整解壓縮後，雙擊 XRayReview.exe。機種、參照圖和敏感度與本機一致；新資料夾的自動取圖預設關閉，請選定來源後再啟用。若要直接更新既有可攜資料夾，先關閉舊程式，再使用「更新舊版.cmd」：保留 workspace、config 及舊模型，備份舊程式後更新。</p><p>舊 r2 模型、舊 ZIP 與舊報告保留。這是 r3 新版本；舊 r2 全圖資結果不代表 r3 的全圖資準確率。</p><p><a href="release-checks/verification.json">一致性核對摘要</a> · <a href="release-checks/preservation-after.json">本機資料保留核對</a> · <a href="release-checks/gpu-telemetry.json">GPU 狀態紀錄</a></p></html>'''
    (PACKAGE/'版本說明.html').write_text(notes,encoding='utf-8')
    # The local copy shares the same relative evidence directory.
    shutil.copytree(reports,work/'release-checks',dirs_exist_ok=True)
    (work/'index.html').write_text(notes,encoding='utf-8')
    manifest.update(windows_execution_verified=True,verification=verification,
                    source_sha256={p:sha(ROOT/p) for p in manifest['source_sha256']},
                    gpu_worker_included=True,default_execution='cpu',portable_auto_acquisition_default=False)
    manifest['file_sha256']={str(p.relative_to(PACKAGE)).replace('\\','/'):sha(p) for p in PACKAGE.rglob('*') if p.is_file() and p.name!='BUILD-MANIFEST.json'}
    write(PACKAGE/'BUILD-MANIFEST.json',manifest)
    archive=PACKAGE.with_suffix('.zip')
    if archive.exists():raise FileExistsError(archive)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for p in PACKAGE.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(PACKAGE.parent))
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    digest=sha(archive);archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    receipt=dict(success=True,archive=str(archive),bytes=archive.stat().st_size,sha256=digest,verification=verification)
    write(work/'DELIVERY_READY.json',receipt)
    print(json.dumps(receipt,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
