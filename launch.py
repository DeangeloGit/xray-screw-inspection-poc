"""Start or reuse this local app; open the browser only after it is ready."""
from pathlib import Path
import json
import subprocess
import sys
import time
import urllib.request
import webbrowser

url = 'http://127.0.0.1:8765'

def ready():
    try:
        with urllib.request.urlopen(url+'/api/health', timeout=1) as response:
            data = json.load(response)
        return data.get('service') == 'xray-poc' and data.get('version') == 3
    except Exception:
        return False

if ready():
    webbrowser.open(url)
else:
    process = subprocess.Popen([sys.executable, 'app.py'], cwd=Path(__file__).resolve().parent)
    try:
        for _ in range(80):
            if process.poll() is not None:
                raise RuntimeError('無法啟動服務，請查看上方錯誤；8765 埠可能已被使用。')
            if ready():
                webbrowser.open(url)
                break
            time.sleep(.25)
        else:
            raise RuntimeError('啟動逾時，請查看上方錯誤。')
        process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if process.poll() is None:
            process.terminate()
