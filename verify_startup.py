"""No Mac connection: real local HTTP, proxy isolation, port recovery and reuse."""
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
import urllib.request


def run():
    import launch
    from flask import Flask, jsonify
    from werkzeug.serving import make_server
    app=Flask('startup-test')
    @app.get('/api/health')
    def health():return jsonify(service='xray-poc',startup_protocol=2,workspace_id='test-workspace')
    def factory(host,port,app,**kwargs):
        if port==8765:
            e=PermissionError(13,'simulated Windows port denial');e.winerror=10013;raise e
        return make_server(host,port,app,**kwargs)
    server,failed=launch.bind_server(app,ports=(8765,0),factory=factory)
    assert failed[0]['winerror']==10013 and server.port>0
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    original={k:os.environ.get(k) for k in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','no_proxy')}
    try:
        for key in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY'):os.environ[key]='http://127.0.0.1:1'
        os.environ['NO_PROXY']='';os.environ['no_proxy']=''
        url='http://127.0.0.1:'+str(server.port)
        assert launch.ready(url,'test-workspace')
        assert not launch.ready(url,'different-workspace')
    finally:
        server.shutdown();server.server_close()
        for key,value in original.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
    with TemporaryDirectory() as temp:
        root=Path(temp).resolve()
        config=root/'station.json';config.write_text(json.dumps(dict(workspace=str(root/'workspace'),model_root=str(root/'models'))))
        env=dict(os.environ,XRAY_CONFIG=str(config),XRAY_WORKSPACE=str(root/'workspace'),XRAY_NO_BROWSER='1',HTTP_PROXY='http://127.0.0.1:1',HTTPS_PROXY='http://127.0.0.1:1',NO_PROXY='')
        with (root/'process.log').open('w') as log:
            process=subprocess.Popen([sys.executable,'-u','launch.py'],env=env,stdout=log,stderr=log)
            try:
                deadline=time.monotonic()+20
                record=root/'workspace/state/local-server.json'
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                while time.monotonic()<deadline:
                    if process.poll() is not None:raise AssertionError((root/'process.log').read_text())
                    try:
                        data=json.loads(record.read_text())
                        with opener.open(data['url']+'/api/health',timeout=1) as r:value=json.load(r)
                        assert value['workspace_id']==data['workspace_id']
                        with opener.open(data['url']+'/settings',timeout=1) as r:assert r.status==200
                        break
                    except (OSError,ValueError):time.sleep(.1)
                else:raise AssertionError('launcher did not become ready')
                assert data['local_only'] and data['url'].startswith('http://127.0.0.1:')
                reused=subprocess.run([sys.executable,'launch.py'],env=env,capture_output=True,text=True,timeout=10)
                assert reused.returncode==0,reused.stderr
                assert data['url'] in reused.stdout
            finally:
                process.terminate();process.wait(timeout=5)
    with TemporaryDirectory() as temp:
        root=Path(temp).resolve();version=root/'version';entry=version/'_app/portable_entry.py';entry.parent.mkdir(parents=True)
        import shutil
        shutil.copyfile('packaging/portable_entry.py',entry)
        fixtures=version/'workspace/data';fixtures.mkdir(parents=True)
        for name in ('ok_0.png','ng_5.png','ng_9.png'):(fixtures/name).write_bytes(b'test-only-seed')
        base=root/'user-data';(base/'workspace/data').mkdir(parents=True)
        (base/'workspace/data/ok_0.png').write_bytes(b'operator-reference')
        code="""
import importlib.util,sys,json,os
from pathlib import Path
spec=importlib.util.spec_from_file_location('portable_entry',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.initialize_user_storage()
base=Path(os.environ['XRAY_USER_ROOT']);config=base/'config/station.json'
value=json.loads(config.read_text());assert value['model_root']==str(base/'models')
value['operator_setting']='preserve';config.write_text(json.dumps(value))
m.initialize_user_storage()
assert json.loads(config.read_text())['operator_setting']=='preserve'
assert (base/'workspace/data/ok_0.png').read_bytes()==b'operator-reference'
assert (base/'workspace/data/ng_5.png').read_bytes()==b'test-only-seed'
"""
        subprocess.run([sys.executable,'-c',code,str(entry)],env=dict(os.environ,XRAY_USER_ROOT=str(base)),check=True)
    print('PASS: user storage seeds missing examples, preserves operator reference/settings and uses persistent models')
    print('PASS: simulated WinError 10013 recovery, actual loopback HTTP without proxy, workspace identity, full launcher and same-instance reuse')

if __name__=='__main__':run()
