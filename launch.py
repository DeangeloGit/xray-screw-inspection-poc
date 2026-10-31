"""Source and frozen entry point: run the server directly, without recursive subprocesses."""
import json
import sys
import threading
import time
import urllib.request
import webbrowser

URL = 'http://127.0.0.1:8765'

def ready():
    try:
        with urllib.request.urlopen(URL+'/api/health', timeout=1) as response:
            data = json.load(response)
        return data.get('service') == 'xray-poc' and data.get('version') == 4
    except Exception:
        return False

def main():
    if ready():
        webbrowser.open(URL)
        return
    from app import app, start_background
    from werkzeug.serving import make_server
    # Bind before starting ingestion; a busy port must never start a second importer.
    server = make_server('127.0.0.1',8765,app,threaded=True)
    start_background()
    def open_browser():
        for _ in range(80):
            if ready():
                webbrowser.open(URL); return
            time.sleep(.25)
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
