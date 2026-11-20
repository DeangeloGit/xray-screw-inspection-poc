"""Explicit 5r enclosure/fragment-review service; prior entry remains available."""
import os
import json
import re
from pathlib import Path

from spatial5r_runtime import Engine

root = Path(__file__).resolve().parents[2]
home = Path(os.environ.get('XRAY_5R_HOME',root/'workspace/5r-spatial-home'))
engine = Engine(home,os.environ.get('XRAY_4R_PROVIDER','cpu'))
import library
import machine_tuning
from app import app, analysis_lock
from flask import jsonify, request
from folder_batch5r import register
from machine_profiles import selected_profile
from station_settings import detection_threshold

engine.banks.register(app,engine.manager)
engine.manager.snapshot = engine.snapshot
library.detect = machine_tuning.detect = engine.detect
register(app,home/'folder-batches',analysis_lock,engine.lock,engine.detect,
         engine.snapshot,selected_profile,detection_threshold)

def immutable_settings():
    return jsonify(error='此驗證站固定使用目前 DINO 流程與執行裝置。'),409
app.view_functions['settings_api.apply_model'] = immutable_settings
app.view_functions['settings_api.set_dino_execution'] = immutable_settings

@app.get('/api/5r/spatial-review')
def spatial_status():
    import spatial5r, enclosure_rescue5r, structure_shadow5r
    return jsonify(version=spatial5r.VERSION,rescue_version=enclosure_rescue5r.VERSION,policy_sha256=engine.policy_hash,
                   banks=engine.bundle.details(engine.banks.current),
                   structure_review=dict(version=structure_shadow5r.VERSION,mode='shadow_only'),
                   confirmed_local_review=engine.confirmed_local.status())

@app.get('/api/5r/confirmed-local-review')
def confirmed_local_status():
    return jsonify(engine.confirmed_local.status())

@app.get('/5r/confirmed-local-review')
def confirmed_local_page():
    from markupsafe import escape
    status=engine.confirmed_local.status()
    state='已就緒：只顯示建議，所有原警報照常保留' if status['ready'] else '目前不可複核，維持原判：'+status.get('reason','')
    return ('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>U1局部參照複核</title>'
            '<body><h1>U1局部參照複核</h1><p>'+str(escape(state))+'</p>'
            '<p>僅MPT10已確認U1；兩個局部參照都通過原條件才顯示排除建議。'
            '缺件、參照不符、越界或局部對位失敗，均保留原判。自動排除未啟用。</p>'
            '<p><a href="/5r/batch">開啟資料夾完整檢測</a> · <a href="/">返回檢測</a></p></body></html>')

@app.get('/api/5r/local-review')
def local_status():
    return jsonify(enabled=True,details=engine.bundle.details(engine.banks.current),
                   qualification=engine.bundle.meta['qualification'])

@app.before_request
def reject_stale_tuning():
    if request.method=='POST' and request.path.endswith('/tuning/apply'):
        body=request.get_json(silent=True) or {}
        token=body.get('preview_id','') if isinstance(body,dict) else ''
        if not isinstance(token,str) or not re.fullmatch('[a-f0-9]{32}',token):
            return jsonify(error='請先完成目前版本的調校試算'),400
        path=engine.home/'station/state/tuning-previews'/token/'result.json'
        try:
            result=json.loads(path.read_text(encoding='utf8'))
            if not result.get('spatial5r') or result.get('model',{}).get('fingerprint')!=engine.snapshot().identity:
                return jsonify(error='流程或範例庫已變更，請重新試算後再套用'),409
        except (OSError,ValueError):
            return jsonify(error='找不到目前版本的完整試算結果'),409

@app.after_request
def banner(response):
    if not response.direct_passthrough and response.content_type and response.content_type.startswith('text/html'):
        text=response.get_data(as_text=True)
        if '<body' in text:
            i=text.find('>',text.find('<body'))+1
            text=text[:i]+'<p style="padding:12px;text-align:center;background:#e5f0ff">5r 外殼範圍＋完整物件複核＋穩定物件補救｜<a href="/5r/batch">資料夾完整檢測報告</a>｜<a href="/5r/confirmed-local-review">U1局部參照：僅建議、保留警報</a></p>'+text[i:]
            response.set_data(text)
    return response

if __name__ == '__main__':
    import launch
    port=int(os.environ.get('XRAY_5R_PORT','18771'))
    if not 1024<=port<=65535:raise ValueError('無效的連接埠')
    launch.URL='http://127.0.0.1:'+str(port)
    launch.main(ports=(port,0))
