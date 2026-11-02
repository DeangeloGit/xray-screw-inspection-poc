"""A failed photo must not block confirmed results or silently become a normal photo."""
import csv
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
    import cv2
    import numpy as np
    from app import app
    from runtime_paths import DATA, RESOURCE_ROOT, WORK_ROOT
    from library import select_sample, analyze_sample, save_result, analysis_failures
    shutil.copyfile(RESOURCE_ROOT/'data/ok_0.png',DATA/'ok_0.png')
    shutil.copyfile(RESOURCE_ROOT/'data/ng_5.png',DATA/'confirmed.png')
    # Valid image encoding, but no shared structure / usable contrast for analysis.
    cv2.imwrite(str(DATA/'=failed.png'),np.zeros((256,256),np.uint16))
    shutil.copyfile(RESOURCE_ROOT/'data/ng_9.png',DATA/'pending.png')
    confirmed=select_sample('confirmed.png');failed=select_sample('=failed.png');pending=select_sample('pending.png')
    with app.test_client() as client:
        result=client.post('/api/analyze',data={'sample':confirmed['id']}).json
        for index,candidate in enumerate(result['candidates']):
            response=client.post('/api/review/'+result['name'],json={'id':candidate['id'],'label':'screw' if index==0 else 'normal'})
            assert response.status_code==200
        failure=client.post('/api/analyze',data={'sample':failed['id']})
        assert failure.status_code==400
        assert failed['sha256'] in analysis_failures()
        listing=client.get('/api/samples').json
        failed_item=next(item for item in listing['items'] if item['id']==failed['id'])
        assert failed_item['analysis_error'] and failed_item['analysis'] is None
        ids=[confirmed['id'],failed['id'],pending['id']]
        before=set((WORK_ROOT/'reports').glob('*'))
        preview=client.post('/api/reports/screws/preview',json={'sample_ids':ids})
        assert preview.status_code==200,preview.json
        data=preview.json
        assert data['completed_count']==1 and data['screw_rows']==1 and data['unresolved_count']==2
        assert {row['status'] for row in data['rows']}=={'已複判','無法分析','尚未檢查'}
        assert set((WORK_ROOT/'reports').glob('*'))==before
        report=client.post('/api/reports/screws',json={'sample_ids':ids,'preview_token':data['preview_token']})
        assert report.status_code==200 and report.headers['X-Screw-Rows']=='1' and report.headers['X-Unresolved-Rows']=='2'
        rows=list(csv.DictReader(io.StringIO(report.data.decode('utf-8-sig'))))
        assert len(rows)==3 and all(row['SN']=='' for row in rows)
        error=next(row for row in rows if row['處理狀態']=='無法分析')
        assert error['照片檔名']=="'=failed.png" and error['人工判定']=='未判定' and error['未完成原因']
        assert error['來源完整路徑'] and error['資料類型']=='待處理異常'
        assert len([row for row in rows if row['人工判定']=='人工確認有掉落螺絲'])==1
        # All failures can still produce an explicit exception-only report.
        report=client.post('/api/reports/screws',json={'sample_ids':[failed['id']]})
        assert report.status_code==200 and report.headers['X-Screw-Rows']=='0' and report.headers['X-Unresolved-Rows']=='1'
        # Changed reviews cannot export a stale preview as if it were still current.
        client.post('/api/review/'+result['name'],json={'id':result['candidates'][0]['id'],'label':'uncertain'})
        stale=client.post('/api/reports/screws',json={'sample_ids':ids,'preview_token':data['preview_token']})
        assert stale.status_code==409
        fresh=client.post('/api/reports/screws/preview',json={'sample_ids':ids})
        assert fresh.json['screw_rows']==0 and fresh.json['unresolved_count']==3
        assert any(row['status']=='需再確認' for row in fresh.json['rows'])
        # A real successful retry clears a persisted failure for this machine/reference.
        from library import record_analysis_failure
        record_analysis_failure(pending['sha256'], __import__('machine_profiles').selected_profile(), 'transient failure')
        analyze_sample(pending)
        assert pending['sha256'] not in analysis_failures()
        subprocess.run([sys.executable,'-c',f"from library import analysis_failures; assert {failed['sha256']!r} in analysis_failures()"],check=True,env=os.environ)
    print('PASS: mixed completed/failed/unreviewed export, distinct exception reasons, SN blank, CSV formula protection, exception-only report, stale preview rejection, retry recovery and failure persistence')


if __name__=='__main__':
    if len(sys.argv)>1:checks(Path(sys.argv[1]))
    else:
        with TemporaryDirectory() as directory:
            root=Path(directory);config=root/'station.json'
            config.write_text(json.dumps(dict(workspace=str(root/'workspace'),model_root=str(root/'models'))))
            subprocess.run([sys.executable,__file__,str(root)],check=True,env=dict(os.environ,XRAY_CONFIG=str(config),XRAY_WORKSPACE=str(root/'workspace')))
