"""Entry point for an app-local Windows Python distribution; no global Python install."""
import os
from pathlib import Path
import sys
import json
import shutil
import uuid
import traceback

ROOT = Path(__file__).resolve().parent.parent
os.environ['PYTHONUTF8']='1'
os.environ['PYTHONIOENCODING']='utf-8'
# SFX supplies a persistent per-user work directory; folder editions use their local workspace.
os.environ.setdefault('XRAY_CONFIG',str(ROOT/'config/station.json'))
os.environ.setdefault('XRAY_WORKSPACE',str(ROOT/'workspace'))


def initialize_user_storage():
    if not os.environ.get('XRAY_USER_ROOT'):
        return
    base=Path(os.environ['XRAY_USER_ROOT'])
    for name in ('config','models','workspace/data','logs'):
        (base/name).mkdir(parents=True,exist_ok=True)
    config=base/'config/station.json'
    if not config.exists():
        value=dict(schema_version=1,station_id='WINDOWS-STANDALONE',
                   workspace=str(base/'workspace'),model_root=str(base/'models'),
                   default_provider='cpu',allow_cpu_fallback=True,
                   acquisition=dict(enabled=False,source='',poll_seconds=3,stable_seconds=15))
        temporary=config.with_name(uuid.uuid4().hex+'.tmp')
        try:
            temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
            if not config.exists():os.replace(temporary,config)
        finally:
            temporary.unlink(missing_ok=True)
    for name in ('ok_0.png','ng_5.png','ng_9.png'):
        source=ROOT/'workspace/data'/name; target=base/'workspace/data'/name
        if source.exists() and not target.exists():shutil.copyfile(source,target)
    os.environ['XRAY_CONFIG']=str(config)
    os.environ['XRAY_WORKSPACE']=str(base/'workspace')
    print('Data and logs: '+str(base),flush=True)


def main():
    if '--self-test' in sys.argv:
        from portable_selftest import run
        return run(ROOT)
    initialize_user_storage()
    print('Starting local service. No Mac connection or shared network is required.', flush=True)
    from launch import main as launch
    launch()
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except BaseException as exc:
        if isinstance(exc,SystemExit) and exc.code in (None,0):
            raise
        detail=traceback.format_exc()
        print(detail,file=sys.stderr)
        try:
            log_root=Path(os.environ.get('XRAY_USER_ROOT',str(ROOT)))
            (log_root/'logs').mkdir(parents=True,exist_ok=True)
            with (log_root/'logs/startup.log').open('a',encoding='utf-8') as file:
                file.write(detail+'\n')
        except OSError:
            pass
        raise SystemExit(1)
