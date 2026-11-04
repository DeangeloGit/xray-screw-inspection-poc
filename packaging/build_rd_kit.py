"""Collect r3 source/runtime/fixtures; never execute detection while packaging."""
import ast,hashlib,json,shutil,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'dist/XRay-RD-r3-Reproduction-20261105'
MODEL='dino-paired-optimized-47-20261104-r3'
WORK=ROOT/'workspace/integration-r3-20261104-121817'
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def copy(a,b):b.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(a,b)

RUNNER=r'''"""Verify by default. Inference requires explicit --run-single or --run-cases."""
import argparse,hashlib,json,os,subprocess,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent
MODEL='dino-paired-optimized-47-20261104-r3'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def verify():
    m=read(ROOT/'KIT-MANIFEST.json')
    for name,digest in m['files'].items():
        p=ROOT/name
        assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==digest,name
    print('PASS: all kit SHA-256 checks; no inference performed',flush=True)
def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group()
    g.add_argument('--run-single',action='store_true');g.add_argument('--run-cases',action='store_true')
    p.add_argument('--backend',choices=['portable','source'],default='portable')
    p.add_argument('--execution',choices=['cpu','gpu'],default='cpu');p.add_argument('--verify',action='store_true');a=p.parse_args()
    verify()
    if not(a.run_single or a.run_cases):return
    out=ROOT/'reproductions'/uuid.uuid4().hex;out.mkdir(parents=True)
    env=dict(os.environ,XRAY_CONFIG=str(ROOT/'config/rd-station.json'),XRAY_WORKSPACE=str(out/'runtime'),PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
    if a.run_cases:
        if a.backend!='source':raise RuntimeError('Cropped-pair checks require --backend source and supplied dependencies')
        cmd=[sys.executable,str(ROOT/'rd_cases.py'),a.execution,str(out/'cases.json')]
    else:
        golden=read(ROOT/'fixtures/single/golden-timing.json');golden['result_path']=str(ROOT/'fixtures/single/images/result.json')
        gp=out/'golden.json';gp.write_text(json.dumps(golden),encoding='utf-8')
        cfg=dict(model=MODEL,execution=a.execution,reference=str(ROOT/'fixtures/single/reference.tiff'),target=str(ROOT/'fixtures/single/target.tiff'),golden=str(gp),output=str(out/'actual'))
        cp=out/'config.json';cp.write_text(json.dumps(cfg),encoding='utf-8')
        if a.backend=='portable':
            if sys.platform!='win32':raise RuntimeError('Bundled EXE requires Windows x64')
            cmd=[str(ROOT/'portable/XRayReview.exe'),'--verify-release',str(cp)]
        else:
            bootstrap='import sys;from pathlib import Path;sys.path.insert(0,sys.argv[2]);import gpu_runtime;gpu_runtime.INSTALL_ROOT=Path(sys.argv[3]);from release_validation import run;run(sys.argv[1])'
            cmd=[sys.executable,'-c',bootstrap,str(cp),str(ROOT/'src'),str(ROOT/'portable')]
    subprocess.run(cmd,cwd=ROOT,env=env,check=True);print('Results: '+str(out))
if __name__=='__main__':main()
'''
CASES=r'''import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
import gpu_runtime
gpu_runtime.INSTALL_ROOT=ROOT/'portable'
import numpy as np
from PIL import Image
from model_manager import ModelManager
from dino_paired_optimized import classify_candidate
def main(execution,output):
    cases=json.loads((ROOT/'fixtures/cases/plan.json').read_text(encoding='utf-8'))
    s=ModelManager(allow_cpu=True,execution_override=execution).snapshot('dino-paired-optimized-47-20261104-r3')
    assert not s.error,s.info()
    rows=[]
    for z in cases:
        ref,tar=[np.asarray(Image.open(ROOT/'fixtures/cases'/z['frames']/f).convert('L'),np.float32)/255 for f in ('reference.png','aligned.png')]
        p=classify_candidate(s,tar,ref,z['candidate']);pair=p.get('paired_evidence',{});e=z['expected']
        assert p['status']=='active' and (p['action']!='discard')==e['new']['keep'],z['number']
        for side in ('reference','target'):
            assert (pair[side]['label']=='screw')==e['new'][side]['screw'],(z['number'],side)
            assert pair[side]['input_sha256']==e['input_hashes'][side],(z['number'],side,'input')
        rows.append(dict(number=z['number'],group=z['group'],classification=p));print(str(z['number'])+'/59 unchanged',flush=True)
    Path(output).write_text(json.dumps(dict(success=True,cases=len(rows),decision_changes=0,model=s.info(),rows=rows),ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main(*sys.argv[1:])
'''
PS=r'''param([ValidateSet('cpu','gpu')][string]$Execution='cpu')
$ErrorActionPreference='Stop'
$kit=$PSScriptRoot
$run=Join-Path $kit ('reproductions\'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $run | Out-Null
$gold=Get-Content -LiteralPath (Join-Path $kit 'fixtures\single\golden-timing.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$gold.result_path=Join-Path $kit 'fixtures\single\images\result.json'
$gp=Join-Path $run 'golden.json'
[IO.File]::WriteAllText($gp,($gold | ConvertTo-Json -Depth 20),(New-Object Text.UTF8Encoding($false)))
$cfg=@{execution=$Execution;model='dino-paired-optimized-47-20261104-r3';reference=(Join-Path $kit 'fixtures\single\reference.tiff');target=(Join-Path $kit 'fixtures\single\target.tiff');golden=$gp;output=(Join-Path $run 'actual')}
$cp=Join-Path $run 'config.json'
[IO.File]::WriteAllText($cp,($cfg | ConvertTo-Json -Depth 10),(New-Object Text.UTF8Encoding($false)))
& (Join-Path $kit 'portable\XRayReview.exe') --verify-release $cp
if($LASTEXITCODE -ne 0){throw 'Parity diagnostic failed'}
Write-Host "Result: $run"
'''
def main():
    if OUT.exists():raise FileExistsError(OUT)
    snapshot=load(ROOT/'workspace/rd-implementation-html-20261104/source-snapshot-sha256.json')
    paths=[ROOT/p for p in snapshot]+[ROOT/'models/active.json',ROOT/'workspace/windows-check/state/ui_settings.json',ROOT/'docs/XRAY_R3_RD_IMPLEMENTATION_20261104.html']
    before={str(p):sha(p) for p in paths};OUT.mkdir(parents=True)
    for name,digest in snapshot.items():assert sha(ROOT/name)==digest,name;copy(ROOT/name,OUT/'src'/name)
    copy(ROOT/'docs/XRAY_R3_RD_IMPLEMENTATION_20261104.html',OUT/'RD核心流程實作規格.html')
    shutil.copytree(ROOT/'dist/XRayReview-DINO-Optimized-r3-20261104-Windows-x64',OUT/'portable')
    model=OUT/'portable/models'/MODEL;m=load(model/'manifest.json');meta=load(model/'examples.json')
    ids=m['example_bank']['screw']['ids']+m['example_bank']['normal']['ids'];assert len(ids)==112
    for key in ids:assert sha(model/'examples'/meta[key]['file'])==meta[key]['sha256']
    write(OUT/'examples-index.json',[dict(id=key,label='screw' if i<47 else 'normal',file='portable/models/'+MODEL+'/examples/'+meta[key]['file'],sha256=meta[key]['sha256']) for i,key in enumerate(ids)])
    cfg=load(WORK/'source-gpu.json')
    copy(Path(cfg['reference']),OUT/'fixtures/single/reference.tiff');copy(Path(cfg['target']),OUT/'fixtures/single/target.tiff')
    golden=load(cfg['golden']);gf=Path(golden['result_path']).parent
    for p in gf.iterdir():
        if p.is_file() and (p.suffix=='.png' or p.name=='result.json'):copy(p,OUT/'fixtures/single/images'/p.name)
    write(OUT/'fixtures/single/golden-timing.json',dict(candidate_timings=golden['candidate_timings'],result_path='images/result.json',candidates=137,scope='Historical expected data, not newly inferred'))
    plan=load(ROOT/'workspace/dino-learn-joint-20261103/results.json');expected=load(ROOT/'workspace/dino-four-remaining-20261103/restricted-results.json');cases=[];seen=set()
    for a,b in zip(plan,expected):
        assert a['key']==b['key'];source=Path(a['source']);key=hashlib.sha256(str(source).encode()).hexdigest()[:20]
        if key not in seen:
            for name in ('reference.png','aligned.png'):copy(source/name,OUT/'fixtures/cases/frames'/key/name)
            seen.add(key)
        cases.append(dict(number=a['number'],group=a['group'],candidate=a['c'],frames='frames/'+key,expected=b))
    assert len(cases)==59;write(OUT/'fixtures/cases/plan.json',cases)
    for name in ('requirements.txt','requirements-cpu.txt','requirements-dino-gpu.txt'):copy(ROOT/name,OUT/name)
    write(OUT/'config/rd-station.json',dict(schema_version=1,model_root='../portable/models',workspace='../reproductions/default-runtime',allow_cpu_fallback=True,acquisition=dict(enabled=False,source='')))
    for name,text in [('rd_reproduce.py',RUNNER),('rd_cases.py',CASES),('run-single.ps1',PS),('verify_kit.py','from rd_reproduce import verify\nverify()\n')]:
        (OUT/name).write_text(text,encoding='utf-8')
    (OUT/'RUN-SINGLE-CPU.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-single.ps1"\r\npause\r\n',encoding='ascii')
    readme=r'''X-RAY r3 RD 重現交接包｜2026-11-05

先看 RD核心流程實作規格.html（離線）。本包沒有自動檢測或來源監看。

A. Windows x64 不需安裝 Python：雙擊 RUN-SINGLE-CPU.cmd。
   只處理內附一張圖，核對137候選、276推論、368張輸出圖片及雙圖判斷。
   GPU命令：powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run-single.ps1 -Execution gpu
   需要可用NVIDIA驅動。CPU仍保留可用；不把受限GPU的速度當正常速度。

B. RD原始碼（已驗證Windows x64 Python 3.14.3；Mac未驗證）：
   py -3.14 -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements-cpu.txt
   .venv\Scripts\python.exe rd_reproduce.py --verify
   .venv\Scripts\python.exe rd_reproduce.py --run-single --backend source --execution cpu
   .venv\Scripts\python.exe rd_reproduce.py --run-single --backend source --execution gpu
   GPU來源程式可用內附portable/runtime-gpu，不需把DirectML裝進CPU環境。

C. 明確執行59個既有小圖案例（不是監看整個圖資）：
   .venv\Scripts\python.exe rd_reproduce.py --run-cases --backend source --execution cpu
   改execution gpu可核對GPU。只驗證檔案時用--verify，完全不跑AI。

src：22份核心與相關程式，與HTML快照逐檔核對。
portable/models/dino-paired-optimized-47-20261104-r3：精確r3模型、manifest、NPZ及範例。
examples-index.json：實際使用的47螺絲＋65正常；portable/models其他目錄是舊版。
fixtures/single：原始參照／待測TIFF、既有預期JSON、PNG與AI輸入hash。
fixtures/cases：59個候選框、預期兩圖判斷、AI輸入hash及去重參照／待測PNG。
reproductions：每次RD重現都寫新隨機目錄，不覆寫golden或正式工作區。
KIT-MANIFEST.json：逐檔SHA-256；ZIP旁.sha256核對整包。

設定為本包獨立RD設定，未帶入正式人工紀錄、監看資料庫或憑證。
已知界限：4個確認螺絲判對；5個目視疑似位置有3個仍漏判；50個正常對照無誤報。
這不是完整獨立準確率證明。Windows EXE不能在Mac直接執行。
本次只收集及移植路徑，沒有重跑檢測、改正式設定或上傳雲端。
'''
    (OUT/'先讀我.txt').write_text(readme,encoding='utf-8-sig')
    for p in [*OUT.glob('*.py'),*(OUT/'src').glob('*.py')]:ast.parse(p.read_text(encoding='utf-8'))
    write(OUT/'KIT-MANIFEST.json',dict(schema_version=1,pipeline='dino-combined-20261104-r3',model=MODEL,screw_examples=47,normal_examples=65,single_candidates=137,single_inferences=276,single_output_png=368,fixed_cases=59,case_source_frames=len(seen),detection_rerun=False,source_snapshot=snapshot,files={p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file()}))
    assert all(sha(Path(p))==h for p,h in before.items())
    archive=OUT.with_suffix('.zip')
    if archive.exists():raise FileExistsError(archive)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for p in OUT.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(OUT.parent))
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    digest=sha(archive);archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    receipt=dict(success=True,zip=str(archive),bytes=archive.stat().st_size,sha256=digest,examples=112,cases=59,formal_files_unchanged=True,detection_rerun=False)
    write(ROOT/'workspace/rd-kit-20261105-receipt.json',receipt);print(json.dumps(receipt,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
