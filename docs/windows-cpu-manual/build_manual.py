"""Create the print-ready Windows CPU operator guide from verified UI captures."""
from pathlib import Path
from xml.sax.saxutils import escape
from PIL import Image as PILImage
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader

ROOT=Path(__file__).resolve().parents[2]
ASSETS=Path(__file__).parent/'assets'
OUT=ROOT/'output/pdf/Windows-CPU-操作手冊.pdf'
OUT.parent.mkdir(parents=True,exist_ok=True)
pdfmetrics.registerFont(TTFont('CJK','/System/Library/Fonts/STHeiti Light.ttc',subfontIndex=0))
pdfmetrics.registerFont(TTFont('CJKB','/System/Library/Fonts/STHeiti Medium.ttc',subfontIndex=0))
PAGE_W,PAGE_H=A4
M=42; W=PAGE_W-2*M
INK=colors.HexColor('#193944'); TEAL=colors.HexColor('#087e80'); MUTED=colors.HexColor('#637782')
PALE=colors.HexColor('#eef6f5'); LINE=colors.HexColor('#dce6e8'); AMBER=colors.HexColor('#fff5df')
C=canvas.Canvas(str(OUT),pagesize=A4,pageCompression=1)
C.setTitle('Windows CPU 版 - 圖文操作與現場測試手冊')
C.setAuthor('X-Ray 螺絲複判專案')
C.setSubject('啟動、UI 取圖、人工複判、CSV 匯出與測試勾選表')


def para(text,width,size=11,leading=17,color=INK,bold=False):
    style=ParagraphStyle('p',fontName='CJKB' if bold else 'CJK',fontSize=size,leading=leading,textColor=color,wordWrap='CJK',spaceAfter=0)
    return Paragraph(escape(text).replace('\n','<br/>'),style)


def drawtext(text,x,y,width,size=11,leading=17,color=INK,bold=False):
    p=para(text,width,size,leading,color,bold);_,h=p.wrap(width,1000);p.drawOn(C,x,y-h)
    return h


class Page:
    def __init__(self,n,title,subtitle):
        self.n=n; self.y=PAGE_H-115
        C.setFillColor(TEAL);C.rect(0,PAGE_H-7,PAGE_W,7,fill=1,stroke=0)
        C.setFont('CJKB',9);C.setFillColor(TEAL);C.drawString(M,PAGE_H-34,'X-RAY / WINDOWS CPU / 現場操作手冊')
        C.setFont('CJK',8);C.setFillColor(MUTED);C.drawRightString(PAGE_W-M,PAGE_H-34,'2026.11.01  |  手冊 v1.0')
        C.setFillColor(INK);C.setFont('CJKB',23);C.drawString(M,PAGE_H-73,title)
        drawtext(subtitle,M,PAGE_H-85,W,10,15,MUTED)
        C.setStrokeColor(LINE);C.line(M,48,PAGE_W-M,48)
        C.setFont('CJK',8);C.setFillColor(MUTED);C.drawString(M,33,'所有照片均需人工確認  |  SN 暫留白')
        C.drawRightString(PAGE_W-M,33,f'{n:02d} / 09')
        C.bookmarkPage('p'+str(n));C.addOutlineEntry(title,'p'+str(n),level=0)
    def text(self,text,size=11,leading=17,color=INK,bold=False,gap=9):
        self.y-=drawtext(text,M,self.y,W,size,leading,color,bold)+gap
    def h2(self,text):
        self.text(text,14,20,TEAL,True,8)
    def step(self,n,title,body):
        C.setFillColor(TEAL);C.circle(M+10,self.y-11,10,fill=1,stroke=0)
        C.setFillColor(colors.white);C.setFont('CJKB',10);C.drawCentredString(M+10,self.y-15,str(n))
        h=drawtext(title,M+29,self.y,W-29,12,18,INK,True)
        h+=drawtext(body,M+29,self.y-h-5,W-29,11,17)+5
        self.y-=max(26,h)+12
    def box(self,title,body,bg=PALE):
        h1=para(title,W-28,11,17,TEAL,True).wrap(W-28,1000)[1]
        h2=para(body,W-28,10.5,16,INK).wrap(W-28,1000)[1]
        h=h1+h2+30
        C.setFillColor(bg);C.roundRect(M,self.y-h,W,h,7,fill=1,stroke=0)
        drawtext(title,M+14,self.y-11,W-28,11,17,TEAL,True)
        drawtext(body,M+14,self.y-16-h1,W-28,10.5,16)
        self.y-=h+12
    def image(self,name,maxheight=350,crop=None,caption=None,badges=()):
        image=PILImage.open(ASSETS/name)
        if crop:image=image.crop((max(0,crop[0]),max(0,crop[1]),min(image.width,crop[2]),min(image.height,crop[3])))
        iw,ih=image.size
        scale=min(W/iw,maxheight/ih);dw,dh=iw*scale,ih*scale
        x=M+(W-dw)/2;top=self.y
        C.setStrokeColor(LINE);C.rect(x-1,top-dh-1,dw+2,dh+2,fill=0,stroke=1)
        C.drawImage(ImageReader(image),x,top-dh,width=dw,height=dh)
        for n,bx,by in badges:
            C.setFillColor(TEAL);C.circle(x+bx*scale,top-by*scale,8,fill=1,stroke=0)
            C.setFillColor(colors.white);C.setFont('CJKB',9);C.drawCentredString(x+bx*scale,top-by*scale-3,str(n))
        self.y-=dh+8
        if caption:self.text(caption,8.5,13,MUTED,gap=10)
    def table(self,rows,widths,header=True,size=10,leading=15):
        data=[[para(str(cell),widths[i]-16,size,leading,colors.white if header and ri==0 else INK,header and ri==0) for i,cell in enumerate(row)] for ri,row in enumerate(rows)]
        table=Table(data,colWidths=widths,hAlign='LEFT')
        commands=[('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),('LINEBELOW',(0,0),(-1,-1),.5,LINE)]
        if header:commands+=[('BACKGROUND',(0,0),(-1,0),TEAL),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE])]
        table.setStyle(TableStyle(commands));_,h=table.wrap(W,1000);table.drawOn(C,M,self.y-h);self.y-=h+12
    def end(self):
        assert self.y>=64,(self.n,self.y)
        C.showPage()


p=Page(1,'Windows CPU 版圖文操作手冊','從首次啟動到批次螺絲清單，適用於 Windows 測試與現場交接。')
p.box('先記住這三件事','保持啟動視窗開啟；完成整張照片人工複判；SN 欄位目前一律留白。')
p.image('01-review.png',maxheight=270,crop=(210,80,1430,1040),caption='同版程式的瀏覽器介面示意。圖中使用既有測試照片，並非正式設備的判定紀錄。')
p.h2('照著這個順序操作')
p.table([['步驟','操作與頁碼'],['01 啟動','解壓整包，雙擊 EXE，確認瀏覽器開啟。第 2 頁'],['02 取圖','指定來源資料夾，啟用自動取圖。第 3 頁'],['03 複判','逐位置判定，再確認整張照片。第 4-5 頁'],['04 匯出','勾選批次，下載 CSV，再依檔名回查。第 6-7 頁']],[100,W-100])
p.text('版本：Windows x64 CPU 測試包，程式基準 5c3d7a5。介面圖由同版 Mac 瀏覽器擷取；Windows 路徑以教學範例表示。Windows 實機結果待確認，流程測試通過不等於螺絲偵測準確率已驗收。',9,14,MUTED,gap=0)
p.end()

p=Page(2,'01 / 解壓與啟動','首次測試先用內附兩張照片，確認畫面與操作能正常使用。')
p.step(1,'解壓整個測試包','在 Windows 對 CPU 版 ZIP 按右鍵，選「解壓縮全部」。建議放到可寫入的資料夾，例如 C:\\XRayReview。')
p.box('資料夾結構示意','XRayReview.exe      啟動程式\nruntime、_app        隨附執行環境與程式，請一起保留\nworkspace           照片、人工結果、來源紀錄與表單\nmodels、config       模型與站台設定\nDIAGNOSTICS.bat      啟動失敗時的診斷工具')
p.step(2,'雙擊 XRayReview.exe','不用另外安裝 Python，也不需要 NVIDIA 顯示卡。不要在 ZIP 預覽中執行，也不要只複製 EXE。')
p.step(3,'確認瀏覽器開啟','正常情況會自動開啟下方網址。若未開啟，可自行輸入；啟動視窗必須持續開著。')
p.box('本機操作網址','http://127.0.0.1:8765\n這是目前 Windows 電腦上的服務；關閉啟動視窗後，網址就無法繼續操作。')
p.step(4,'確認內附測試資料','清單應有 ng_5.png、ng_9.png。正常參考 ok_0.png 不列入待測清單。點照片可分析，也可按「全部檢查」預先分析所有照片。')
p.text('預期結果：看得到照片、疑似位置框與局部放大圖。分析完成只是「待人工確認」，不能直接當作正常或異常結論。',11,17,TEAL,bold=True)
p.end()

p=Page(3,'02 / 指定自動取圖資料夾','點選頁面上方「取圖與模型設定」，設定可直接從 UI 完成。')
# Source card at a readable scale, with numbered callouts aligned to the captured controls.
image=PILImage.open(ASSETS/'02-settings.png').crop((184,182,708,900))
x=M;top=p.y;dw=225;dh=image.height*dw/image.width
C.drawImage(ImageReader(image),x,top-dh,width=dw,height=dh)
for n,bx,by in [(1,45,180),(2,450,265),(3,125,410),(4,160,510)]:
 s=dw/image.width;C.setFillColor(TEAL);C.circle(x+bx*s,top-by*s,8,fill=1,stroke=0);C.setFillColor(colors.white);C.setFont('CJKB',9);C.drawCentredString(x+bx*s,top-by*s-3,str(n))
x2=M+245;w2=W-245;y2=top
for title,body in [('1 先勾選啟用','勾選「啟用自動取圖」。'),('2 選擇資料夾','先在 Windows 建立 C:\\XRayIncoming。按「選擇資料夾…」，也可貼上完整路徑。'),('3 保留等待時間','首次先用 15 秒，避免讀到還沒寫完的照片。'),('4 儲存','按「儲存取圖設定」。下一次掃描自動生效，不用重啟。')]:
 y2-=drawtext(title,x2,y2,w2,12,18,TEAL,True)+5;y2-=drawtext(body,x2,y2,w2,11,17)+16
p.y=min(top-dh,y2)-12
p.text('圖為儲存前示意，因此目前狀態仍顯示關閉。請在 Windows 上儲存後，再確認狀態已連線。',9,14,MUTED)
p.table([['來源類型','Windows 路徑範例'],['本機資料夾','C:\\XRayIncoming'],['設備共享資料夾','\\\\XRAY-PC\\Images']],[110,W-110])
p.text('儲存後，把一張新的 PNG、JPEG 或 TIFF 照片放入來源，返回複判頁。需等待 15 秒穩定時間，加上輪詢與分析；清單會自動更新，必要時按「重新掃描」。',10.5,16)
p.box('取圖位置與模型選擇','來源需有讀取權限，且不能選到 workspace、models 或包含它們的上層。這次 CPU 流程測試不需選模型，保持「未啟用 AI」即可。')
p.end()

p=Page(4,'03 / 逐一確認疑似位置','每個框都要查看；沒有候選框的照片，也必須人工檢查全圖。')
p.image('01-review.png',maxheight=350,caption='1 選照片；2 看全圖與框的位置；3 看局部並選判定；4 追蹤剩餘位置。',badges=[(1,180,363),(2,885,280),(3,1388,575),(4,1380,760)])
p.table([['按鈕','何時選擇'],['是螺絲','人工確認這個局部為掉落螺絲。'],['不是螺絲','確認是線材、固定零件或其他正常結構。'],['不確定','看不清楚或目前無法判定，保留待確認。']],[105,W-105])
p.text('選擇後會儲存，並移至下一個位置。用下方圓點可回看；綠色框或圓點表示「已確認」，不代表「沒有螺絲」。',11,17)
p.box('不要漏掉全圖','差分框只是提示。請確認機器其他位置，特別留意線材重疊、邊緣或對齊不足的區域；無框不代表正常。',AMBER)
p.end()

p=Page(5,'04 / 完成整張照片複判','逐位置完成後，再看一次整張照片，才能完成這張的作業。')
image=PILImage.open(ASSETS/'04-complete.png').crop((945,740,1420,1010))
dw=W;dh=image.height*dw/image.width;C.drawImage(ImageReader(image),M,p.y-dh,width=dw,height=dh);p.y-=dh+10
p.text('整張結果已儲存的示範。螺絲照片必須選「有螺絲」；局部按「是螺絲」還不等於整張完成。',9,14,MUTED)
p.table([['整張照片選項','判定條件與後續'],['有螺絲','人工確認整張照片有掉落螺絲，會列入螺絲表單。'],['人工未見螺絲','已完整檢查全圖，且全部候選都選「不是螺絲」。'],['需再確認','仍無法確定。可先儲存，但這張會阻擋所屬批次匯出。']],[125,W-125])
p.step(1,'確認已儲存','看得到「已儲存」或左側照片狀態更新，再查看下一張。')
p.step(2,'需要修改時，重新完成整張','改動任一候選判定後，原本整張結果會被撤銷；請再選一次整張結果。')
p.box('按鈕不能按時','有位置尚未確認：先完成所有候選。\n「人工未見螺絲」不能選：仍有候選標為螺絲或不確定，請回看。',AMBER)
p.end()

p=Page(6,'05 / 勾選批次並匯出','先明確選好這批要交付的照片，避免新進照片被一起選入。')
image=PILImage.open(ASSETS/'05-export.png').crop((0,78,206,545))
dw=154;dh=image.height*dw/image.width;top=p.y
C.drawImage(ImageReader(image),M,top-dh,width=dw,height=dh)
x2=M+174;w2=W-174;y2=top
for title,body in [('1 清除預設全選','按「清除選取」，再逐一勾選本批次照片。'),('2 確認全批完成','選到的每張都要完成整張複判，不能仍是「需再確認」。'),('3 按匯出按鈕','按「匯出本批螺絲表單」，瀏覽器會下載 CSV。'),('4 核對匯出筆數','成功後左側會顯示匯出筆數；示範只選 ng_5.png，所以匯出 1 筆。')]:
 y2-=drawtext(title,x2,y2,w2,12,18,TEAL,True)+5;y2-=drawtext(body,x2,y2,w2,11,17)+15
p.y=min(top-dh,y2)-12
p.text('示範：ng_9.png 尚未完成，未被選入本批次。畫面中的判定只用於教學展示。',9,14,MUTED)
p.box('匯出規則','CSV 只列「人工整張確認有螺絲」的照片。已確認未見螺絲的照片不列入；全批皆未見螺絲時，仍會匯出只有表頭的 CSV。')
p.table([['畫面情況','處理方式'],['提示有未完成或需再確認的照片','依提示檔名回去完成複判，或先從本批次取消勾選。'],['自動取圖期間又有新照片','使用「清除選取」後明確勾選，避免預設全選把新照片納入。']],[180,W-180])
p.end()

p=Page(7,'06 / 開啟表單與回查照片','用 Excel 開啟 CSV；保留原始檔名、來源路徑與複判時間。')
p.text('下載後在瀏覽器「下載項目」找到 CSV，以 Excel 開啟。SN 尚無對應資料，請保持空白，不要由檔名推測或自行填入機器序號。')
p.h2('表單核心欄位示例（非現場真實紀錄）')
p.table([['序號','SN','照片檔名','來源完整路徑'],['1','','LineA_0001.png','C:\\XRayIncoming\\LineA_0001.png'],['2','','LineA_0002.png','\\\\XRAY-PC\\Images\\LineA_0002.png']],[40,45,135,W-220],size=9,leading=14)
p.text('SN 欄位刻意留白。無 SN 對應時，表單只能協助依檔名與來源回查，不能自動確定是哪一台實體機器。',10.5,16,TEAL,bold=True)
p.table([['其他欄位','現場用途'],['本機影像路徑','在 IPC 本機找到已取得的影像快照。'],['人工判定、台北複判時間','確認由人工完成，及是哪一次複判結果。'],['分析紀錄、模型版本','後續追查當時使用的分析版本。未啟用 AI 不影響人工表單。'],['取得時間','系統取得照片的時間，不是設備曝光時間；手動照片可能空白。']],[145,W-145])
p.box('檔名重複或筆數不同時','一起比對來源完整路徑與取得時間。完全相同的影像會共用分析項目，但表單可列出各來源事件或別名，因此筆數可能比照片清單項目多。')
p.text('系統另外保留：workspace\\reports\\<報表ID>.csv 與同 ID 的 JSON。JSON 記錄批次範圍、匯出時間及分析紀錄，方便追溯。',10,16,MUTED)
p.end()

p=Page(8,'07 / 結束、備份與問題排查','先看畫面提示；需要協助時，保留診斷紀錄與原始照片。')
p.table([['情況','先做這件事'],['瀏覽器沒有自動開啟','手動輸入 http://127.0.0.1:8765，確認 EXE 的啟動視窗仍開著。'],['無法啟動、提示檔案或 DLL 缺失','確認已解壓整包；執行 DIAGNOSTICS.bat。若明確缺少 C++ Runtime，可使用 prerequisites\\VC_redist.x64.exe。'],['8765 已被占用','關閉舊版 X-Ray 程式的啟動視窗，再執行本版 EXE。'],['取圖離線或一直沒照片','檢查來源路徑、讀取權限、網路連線與啟用勾選。等待檔案穩定後，再按照片清單的重新掃描。'],['放入照片卻沒有新增一列','若內容與清單既有照片完全相同，會合併項目；這不一定表示沒有取圖。新的不同照片才會形成新項目。'],['照片分析失敗或對齊不足','保留原圖，依提示人工補看；不要當作未見螺絲。參考圖不同型號時，需工程人員檢查。'],['無法匯出表單','檢查選定照片是否全部完成整張複判；「需再確認」仍會阻擋匯出。']],[125,W-125],size=10,leading=15)
p.box('需要回報時','雙擊 DIAGNOSTICS.bat。帶回 logs\\windows-selftest.json、logs\\startup.log（若有）或錯誤畫面。診斷不會修改現有照片、人工判定或啟用模型。')
p.text('結束作業：在啟動視窗按 Ctrl+C 或關閉該視窗。下次再雙擊 EXE。搬移或更新前，保留 workspace、models、config；現場備份建議保留整個程式資料夾。',10.5,16)
p.end()

p=Page(9,'現場測試與交接勾選表','建議列印本頁；本表確認操作流程，不作為量產偵測準確率的驗收。')
p.text('測試日期：________________  電腦／站台：________________\n操作人員：________________  程式／包版號：_______________',11,24,gap=16)
items=[('啟動','解壓整包，雙擊 EXE，瀏覽器可開啟。'),('內附照片','ng_5.png、ng_9.png 可分析，局部圖正常顯示。'),('取圖設定','可在 UI 選擇來源，儲存後顯示已連線。'),('自動取圖','新的不同照片可取得並分析；原始來源未被修改。'),('逐位置複判','每個候選均能儲存判定，剩餘數量正確。'),('整張複判','完成全圖檢查後，能儲存整張結果。'),('修改保護','改候選判定後，整張需要重新確認。'),('批次範圍','可清除全選，明確勾選本批次。'),('阻擋未完成','未完成或需再確認的選定照片無法匯出。'),('表單內容','CSV 可在 Excel 開啟，只列人工確認有螺絲。'),('SN 與回查','SN 留白，檔名與來源路徑可讀且可回查。'),('重新啟動','重啟後，設定與人工判定仍可讀取。'),('紀錄保存','知道 workspace、reports 及 logs 的位置。')]
rows=[['檢查項目','預期結果','通過','待處理']]+[[a,b,'',''] for a,b in items]
p.table(rows,[80,W-170,45,45],size=9.5,leading=14)
p.text('本次結果：  可繼續測試 ________   需修正後重測 ________\n問題／照片檔名：________________________________________\n_______________________________________________________',10.5,24,gap=12)
p.text('人工結果與原始照片請依現場規範保存。尚無 SN 對應、尚未訓練螺絲分類模型，不能把本次測試視為自動放行依據。',9.5,15,MUTED)
p.end()

C.save()
print(str(OUT))
