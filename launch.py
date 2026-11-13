"""Local-only launcher with proxy-free readiness and recoverable port selection."""
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import urllib.request
import webbrowser

URL = 'http://127.0.0.1:8765'
LOCAL_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def workspace_identity(path):
    return hashlib.sha256(os.path.normcase(str(Path(path).resolve())).encode()).hexdigest()[:16]


def ready(url=URL, identity=None):
    try:
        with LOCAL_HTTP.open(url+'/api/health', timeout=1) as response:
            data = json.load(response)
        return (data.get('service') == 'xray-poc' and data.get('startup_protocol') == 2
                and (identity is None or data.get('workspace_id') == identity))
    except Exception:
        return False


def bind_server(app, ports=(8765, 8766, 18765, 0), factory=None):
    from werkzeug.serving import make_server
    factory = factory or make_server
    failures = []
    for port in ports:
        try:
            # Werkzeug exits on socket errors. Keep the OS error in diagnostics and try
            # another local port, including an OS-assigned port as the final option.
            server = factory('127.0.0.1', port, app, threaded=True)
            return server, failures
        except (OSError, SystemExit) as exc:
            cause = exc.__context__ or exc
            failures.append(dict(port=port, error=str(cause), errno=getattr(cause,'errno',None),
                                 winerror=getattr(cause,'winerror',None)))
    raise RuntimeError('無法建立本機服務。所有候選連接埠均無法使用：'+json.dumps(failures,ensure_ascii=False))


def open_local(url):
    if os.environ.get('XRAY_NO_BROWSER') != '1':
        webbrowser.open(url)


def main(ports=(8765, 8766, 18765, 0)):
    from runtime_paths import STATE, WORK_ROOT
    identity = workspace_identity(WORK_ROOT)
    record = STATE/'local-server.json'
    candidates = [URL]
    if record.exists():
        try:
            last = json.loads(record.read_text(encoding='utf-8'))
            port = last['port']
            if type(port) is int and 1 <= port <= 65535:
                candidates.insert(0, 'http://127.0.0.1:'+str(port))
        except (ValueError,KeyError,OSError):
            pass
    for url in dict.fromkeys(candidates):
        if ready(url,identity):
            print('本機服務已啟動：'+url,flush=True)
            open_local(url)
            return
    from app import app, start_background
    server, failures = bind_server(app, ports=ports)
    url = 'http://127.0.0.1:'+str(server.port)
    info = dict(url=url,port=server.port,pid=os.getpid(),workspace_id=identity,
                bind_failures=failures,local_only=True,
                proxy_environment_present=[name for name in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY') if os.environ.get(name)])
    temp = record.with_suffix('.tmp')
    temp.write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(record)
    print('本機服務網址：'+url+' （不需要連線到 Mac）',flush=True)
    if failures: print('原連接埠無法使用，已自動改用其他本機連接埠。',flush=True)
    print('請保持此視窗開啟。若瀏覽器未自動開啟，請使用上述實際網址。',flush=True)
    start_background()
    def open_browser():
        for _ in range(100):
            if ready(url,identity):
                open_local(url)
                return
            time.sleep(.1)
        print('瀏覽器就緒檢查未通過，請查看本機服務紀錄。',flush=True)
    threading.Thread(target=open_browser,daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    if '--acquisition-scan' in sys.argv:
        from acquisition import scan_worker
        scan_worker()
    else:
        main()
