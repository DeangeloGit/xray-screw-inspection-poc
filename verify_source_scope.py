"""Changing acquisition sources scopes lists, retries, uploads and report events."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


def checks(root):
    root=root.resolve()
    from app import app
    from library import importer, catalog
    from runtime_paths import DATA, RESOURCE_ROOT
    from station_settings import source_scope
    from acquisition import Importer
    shutil.copyfile(RESOURCE_ROOT/'data/ok_0.png', DATA/'ok_0.png')
    shutil.copyfile(RESOURCE_ROOT/'data/ng_5.png', DATA/'demo.png')
    a=root/'source-A'; b=root/'source-B'; sibling=root/'source-A-extra'
    for folder in (a,b,sibling):folder.mkdir()
    shutil.copyfile(RESOURCE_ROOT/'data/ng_5.png',a/'A.png')
    shutil.copyfile(RESOURCE_ROOT/'data/ng_9.png',b/'B.png')
    shutil.copyfile(RESOURCE_ROOT/'data/ng_5.png',b/'shared.png')
    shutil.copyfile(RESOURCE_ROOT/'data/ng_9.png',sibling/'other.png')
    def activate(client, folder, enabled=True):
        response=client.post('/api/settings/acquisition',json=dict(enabled=enabled,source=str(folder),stable_seconds=0))
        assert response.status_code==200,response.json
        importer.config=dict(enabled=enabled,source=str(folder),stable_seconds=0)
    def scan():
        importer.scan_once(now=0);importer.scan_once(now=1)
    with app.test_client() as client:
        assert any(x['filename']=='demo.png' for x in catalog())
        activate(client,a)
        token_a=source_scope()['id']
        assert client.get('/api/samples').json['items']==[],'old demo files must disappear before first scan'
        scan()
        listing=client.get('/api/samples').json
        assert [x['display_name'] for x in listing['items']]==['A.png']
        aid=listing['items'][0]['id']
        first=client.post('/api/analyze',data={'sample':aid}).json
        for candidate in first['candidates']:
            assert client.post('/api/review/'+first['name'],json=dict(id=candidate['id'],label='normal')).status_code==200
        assert client.post('/api/image-review/'+first['name'],json=dict(decision='screw')).status_code==200
        report=client.post('/api/reports/screws',json=dict(sample_ids=[aid]))
        assert report.status_code==200 and str(a) in report.data.decode('utf-8-sig')
        with importer.connect() as db:db.execute("UPDATE events SET state='analysis_error'")
        activate(client,b)
        assert client.get('/api/samples').json['items']==[]
        assert importer.info()['event_counts']=={}
        calls=[];importer.analyze=lambda path,name:calls.append(name)
        importer.process_pending()
        assert calls==[],'must not retry errors belonging to previous source'
        assert client.post('/api/batch',headers={'X-Inspection-Source':token_a}).status_code==400
        scan()
        listing=client.get('/api/samples').json
        assert set(x['display_name'] for x in listing['items'])=={'B.png','shared.png'}
        shared=next(x for x in listing['items'] if x['id']==aid)
        assert all(str(b) in x['source_path'] for x in shared['events'])
        report=client.post('/api/reports/screws',json=dict(sample_ids=[aid]))
        assert report.status_code==200
        assert str(b) in report.data.decode('utf-8-sig') and str(a) not in report.data.decode('utf-8-sig')
        importer.process_pending();assert set(calls)=={'B.png','shared.png'}
        uploaded=client.post('/api/analyze',data=dict(image=(io.BytesIO((RESOURCE_ROOT/'data/ng_5.png').read_bytes()),'manual.png')))
        assert uploaded.status_code==200,uploaded.json
        assert any('manual.png' in x['aliases'][-1] or any('manual.png' in alias for alias in x['aliases']) for x in catalog())
        activate(client,sibling);scan()
        assert [x['display_name'] for x in client.get('/api/samples').json['items']]==['other.png']
        activate(client,a,False)
        listing=client.get('/api/samples').json
        assert [x['display_name'] for x in listing['items']]==['A.png']
        assert listing['items'][0]['analysis']['image_review']['decision']=='screw'
        assert len(importer.metadata())==4,'source switching must retain snapshots/history'
        # The saved setting, rather than a stale in-memory scanner config, controls the list after restart.
        subprocess.run([sys.executable,'-c',"from library import public_catalog; x=public_catalog(); assert [p['display_name'] for p in x['items']]==['A.png']"],check=True,env=os.environ)
    print('PASS: A/B/sibling source filtering, immediate empty state, scoped uploads/retries/counts/CSV, stale request rejection, preserved review and restart')


if __name__=='__main__':
    if len(sys.argv)>1:checks(Path(sys.argv[1]))
    else:
        with TemporaryDirectory() as directory:
            root=Path(directory)
            config=root/'station.json'
            config.write_text(json.dumps(dict(workspace=str(root/'workspace'),model_root=str(root/'models'))))
            subprocess.run([sys.executable,__file__,str(root)],check=True,env=dict(os.environ,XRAY_CONFIG=str(config),XRAY_WORKSPACE=str(root/'workspace')))
