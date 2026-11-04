"""Small desktop front end for the offline handoff tool; Drive sync stays local."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
import uuid

import station_transfer as transfer
import transfer_crypto as crypto

PREFS = Path.home() / '.xray-transfer/preferences.json'


def main():
    window=tk.Tk();window.title('X-RAY 資料移交｜Windows ↔ Mac');window.geometry('860x650')
    def callback_error(kind,value,tb):
        import traceback
        detail=''.join(traceback.format_exception(kind,value,tb))
        path=Path.home()/'.xray-transfer/ui-error.log';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(detail,encoding='utf-8')
        messagebox.showerror('操作未完成',str(value)+'\n紀錄：'+str(path))
    window.report_callback_exception=callback_error
    self_test_report=None
    if '--self-test-report' in sys.argv:
        self_test_report=Path(sys.argv[sys.argv.index('--self-test-report')+1])
    saved=transfer.read(PREFS) if PREFS.exists() else {}
    defaults=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'transfer-defaults.json'
    initial=transfer.read(defaults) if defaults.exists() else {}
    initial.update(drive=str(Path.home()/'.local/share/xray-transfer/outbox'),key=str(Path.home()/'.config/xray-transfer/backup.key'))
    fields={key:tk.StringVar(value=saved.get(key,initial.get(key,''))) for key in ('root','config','drive','program','key')}
    top=ttk.Frame(window,padding=14);top.pack(fill='both',expand=True)
    ttk.Label(top,text='仿題庫專案：本機加密 → Codex／Google Drive 移交 → 下載校驗與隔離匯入。',wraplength=810).pack(anchor='w')
    ttk.Label(top,text='完整匯出前請關閉檢測程式。匯入會建立新資料夾，並關閉自動監看。').pack(anchor='w',pady=(3,12))
    names={'root':'本機專案／站台資料夾','config':'站台設定（可留空自動尋找）','drive':'本機移交暫存資料夾','program':'本機檢測程式（匯入後啟動用）','key':'外部加密金鑰（不放進雲端包）'}
    def persist():transfer.write(PREFS,{k:v.get() for k,v in fields.items()})
    for key,label in names.items():
        row=ttk.Frame(top);row.pack(fill='x',pady=3)
        ttk.Label(row,text=label,width=29).pack(side='left')
        ttk.Entry(row,textvariable=fields[key]).pack(side='left',fill='x',expand=True)
        def browse(k=key):
            if k in ('root','drive'):value=filedialog.askdirectory(parent=window)
            else:value=filedialog.askopenfilename(parent=window)
            if value:fields[k].set(value);persist()
        ttk.Button(row,text='選擇',command=browse).pack(side='left',padx=(6,0))
    ttk.Label(top,text='匯出完成後可請 Codex 上傳到已連接的 X-RAY Drive 專用資料夾；不需要桌面同步或提供帳號密碼。',wraplength=810).pack(anchor='w',pady=9)
    buttons=ttk.Frame(top);buttons.pack(fill='x')
    log=tk.Text(top,wrap='word',height=20);log.pack(fill='both',expand=True,pady=12)
    log.insert('end','第一次使用：選取本機站台、暫存資料夾及外部金鑰，再按「檢查本機缺件」。\n匯出後請 Codex 上傳；另一台請 Codex 下載並校驗。金鑰只需另行安全移交一次。\n')
    events=queue.Queue();busy=False
    def record(value):log.insert('end',value+'\n');log.see('end')
    def run(task):
        nonlocal busy
        if busy:return
        persist();busy=True
        for b in controls:b.configure(state='disabled')
        record('正在處理；大型圖資需要時間，完成前請勿關閉視窗。')
        def worker():
            try:events.put(('result',task()))
            except Exception as e:events.put(('error',str(e)))
        threading.Thread(target=worker,daemon=False).start()
    def poll():
        nonlocal busy
        try:
            kind,value=events.get_nowait();busy=False
            for b in controls:b.configure(state='normal')
            if self_test_report is not None:
                transfer.write(self_test_report,dict(kind=kind,result=value));window.destroy();return
            if kind=='error':record('未完成：'+value)
            else:
                if value.get('destination'):
                    fields['root'].set(value['destination']);fields['config'].set(value['config']);persist()
                    record('匯入完成：已將目前站台切換至新資料夾，後續匯出會使用這份資料。')
                record(json.dumps(value,ensure_ascii=False,indent=2))
        except queue.Empty:pass
        window.after(100,poll)
    def root_and_config():
        root=fields['root'].get().strip()
        if not root:raise ValueError('請先選取本機站台資料夾')
        return root,fields['config'].get().strip() or None
    def check():
        root,config=root_and_config();return transfer.check_station(root,config)
    def export():
        root,config=root_and_config();drive=Path(fields['drive'].get().strip())
        if not fields['drive'].get().strip():raise ValueError('請選取本機移交暫存資料夾')
        drive.mkdir(parents=True,exist_ok=True)
        name='XRay-Handoff-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.xray.enc'
        return crypto.export_encrypted(root,drive/name,fields['key'].get(),config)
    def choose_archive():
        return filedialog.askopenfilename(parent=window,initialdir=fields['drive'].get() or None,filetypes=[('移交包','*.enc *.zip')])
    def verify():
        archive=choose_archive()
        if archive:
            def task():
                with crypto.open_bundle(archive,fields['key'].get()) as plain:
                    result=transfer.verify_archive(plain)
                return dict(ok=True,**{k:v for k,v in result.items() if k in ('complete','source_commit','validation')})
            run(task)
    def import_data():
        archive=choose_archive()
        if not archive:return
        parent=filedialog.askdirectory(parent=window,title='選擇本機匯入位置；請選在 Drive 以外')
        if not parent:return
        drive=fields['drive'].get().strip()
        if drive and Path(parent).resolve().is_relative_to(Path(drive).resolve()):
            messagebox.showerror('請選本機位置','工作資料不能放在設定的 Drive 移交資料夾內。');return
        destination=Path(parent)/('XRay-Imported-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
        def task():
            result=crypto.import_encrypted(archive,destination,fields['key'].get()) if archive.endswith('.enc') else transfer.import_bundle(archive,destination)
            return dict(result,launch_config=result['config'])
        run(task)
    def launch_imported():
        config=filedialog.askopenfilename(parent=window,title='選擇已匯入資料夾內的 config/station.json',filetypes=[('站台設定','*.json')])
        if not config:return
        receipt=Path(config).resolve().parent.parent/'IMPORT-RECEIPT.json'
        if not receipt.is_file():messagebox.showerror('無匯入紀錄','請選擇本工具已匯入的站台設定。');return
        program=Path(fields['program'].get()).expanduser()
        if program.suffix=='.app':program=program/'Contents/MacOS'/program.stem
        if not program.is_file():messagebox.showerror('缺少程式','請先設定這台電腦的檢測程式完整路徑。');return
        env=dict(os.environ,XRAY_HANDOFF_CONFIG=str(Path(config).resolve()),XRAY_CONFIG=str(Path(config).resolve()),XRAY_WORKSPACE=str(receipt.parent/'workspace'))
        command=[str(program)]
        if program.suffix=='.py':
            repo=program.parent
            python=repo/('.venv/Scripts/python.exe' if os.name=='nt' else '.venv/bin/python')
            if not python.is_file():messagebox.showerror('缺少環境','此原始碼專案尚未建立 .venv，請先安裝執行環境。');return
            command=[str(python),str(program)]
        persist()
        process=subprocess.Popen(command,env=env,cwd=program.parent)
        record('已發出啟動要求，程序 '+str(process.pid)+'；請核對瀏覽器的模型與機種。舊 Windows EXE 需重新建置後才支援匯入設定。')
    controls=[]
    for title,callback in [('檢查本機缺件',lambda:run(check)),('匯出完整移交包',lambda:run(export)),('驗證雲端資料包',verify),('匯入到本機',import_data),('啟動已匯入資料',launch_imported)]:
        b=ttk.Button(buttons,text=title,command=callback);b.pack(side='left',padx=(0,5));controls.append(b)
    def close():
        if busy:messagebox.showinfo('正在移交','請等待工作完成後再關閉。');return
        persist();window.destroy()
    window.protocol('WM_DELETE_WINDOW',close);poll()
    if self_test_report is not None:window.after(200,lambda:run(check))
    window.mainloop()


if __name__=='__main__':main()
