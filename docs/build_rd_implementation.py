"""Build a standalone RD implementation specification from the actual r3 source."""
import ast
import hashlib
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/XRAY_R3_RD_IMPLEMENTATION_20261104.html'
MODEL=ROOT/'models/dino-paired-optimized-47-20261104-r3'
sections=[]
def esc(s):return html.escape(str(s))
def code(s):return '<pre class="code"><code>'+esc(s.strip())+'</code></pre>'
def table(headers,rows):return '<div class="table"><table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def section(key,title,body):sections.append((key,title,body))
def p(text):return '<p>'+text+'</p>'

def main():
    m=json.loads((MODEL/'manifest.json').read_text(encoding='utf-8'))
    section('contract','01｜範圍、版本與重做所需材料',p('目標是讓 RD 能用其他語言或另一套程式，重建目前 r3 的差分與 DINO 判斷。前半部是可依序實作的規格，後半部附上本次正式來源程式的完整唯讀快照。文件本身不會執行檢測。')+
        table(['識別','本文件對應'],[['流程','<code>dino-combined-20261104-r3</code>；DETECTOR_VERSION = 13'],['預設模型目錄','<code>dino-paired-optimized-47-20261104-r3</code>'],['判斷','47 張螺絲＋65 張正常；參照圖與待測圖分別判斷；整體／局部各 50%'],['基準與版本','2026-11-04；Git 基準 66f17bb；r3 是基準之後的工作目錄實作，不能把基準 commit 本身當作已含 r3。'],['必須另有的資料','相同 ONNX 權重、manifest、paired-features.npz，或原始 112 張範例及其順序。HTML 不含模型權重、範例圖片或全部特徵值。'],['重作邊界','可重寫處理邏輯；無法只靠文字重建已訓練的 DINO 權重。換模型、前處理或範例就屬另一版本，須重新驗證。']])+p('附錄原始碼是程式快照，可直接複製比對；演算法說明中的「簡化流程」不能取代附錄的邊界判斷、資料型別和運算順序。'))
    nodes=[('讀圖與快取','灰階、百分位明暗正規化；參照圖縮到長邊 1536，保留其遮罩與 ORB 特徵。'),('整張圖對齊','四個旋轉方向 → 評估；普通方向支援不足才測四個鏡像方向。'),('覆蓋檢查／局部微調','覆蓋機體至少 95%；3×3 區域僅允許小幅平移，建立平滑位移場。'),('明暗補償與差分','三輪局部明暗擬合；7×7 容忍版本找主候選，3×3 版本補查小物件。'),('整理／結構解釋','雜點、尺寸、相似既有輪廓篩選；能由位移及明暗解釋的變化另列。'),('候選編號與座標','依優先度／分數排序；保存對齊座標，並映射回原始待測圖。'),('DINO 雙圖判斷','同座標各截一張；調整為 224×224；用相同 47＋65 範例獨立計分。'),('受限補看','僅初判兩圖都像螺絲，且幾何條件可靠時，固定規則再截同座標一對，最多一次。'),('結果與紀錄','只有待測像螺絲、參照不像才保留；其餘排除但保存紀錄，保留項目供人工複判。')]
    section('flow','02｜完整資料流與模組分工','<div class="flow">'+''.join('<div class="step"><b>'+str(i)+'. '+a+'</b><span>'+b+'</span></div>'+('<div class="arrow">↓</div>' if i<len(nodes) else '') for i,(a,b) in enumerate(nodes,1))+'</div>'+p('舊版 <code>legacy_proposals</code> 另在「整張對齊後、局部修正前」計算，僅供候選核對及保存圖片；不把其結果直接合併進本次 DINO 候選。')+table(['模組','職責'],[['detector.py','讀圖、對齊、候選整理、座標回推、輸出'],['registration_candidate.py / detection_runtime.py','普通／鏡像選擇；快取、並行與 OpenCV 全域狀態保護'],['brightness_fit.py','與原數學運算一致的明暗擬合加速'],['single_reference_evidence.py / wire_review.py','既有結構解釋；線材提示（提示本身不刪候選）'],['dino_paired_optimized.py / paired_geometry.py','r3 特徵比分、雙圖分類、一次受限幾何補看'],['model_manager.py / gpu_*.py','固定每張圖的模型快照；CPU／GPU 選擇及隔離工作程序']]))
    section('coordinates','03｜座標、影像型別與取整規則',table(['資料','定義／不可混用處'],[['raw','待測原始方向影像；大小 Hraw×Wraw；灰階值 0～1。'],['r','參照預覽座標；參照影像長邊 1536，比例 s_ref = 1536/max(Href,Wref)，也可能放大小圖。'],['aligned / corrected','先全域對齊到 r，再以位移場局部修正的待測影像；尺寸與 r 相同。'],['候選 x,y,w,h','全部是 r／corrected 座標，矩形使用左閉右開 [x,x+w)、[y,y+h)。不是原始待測座標。'],['flow[y,x]','從 corrected 座標映回 aligned 的位移，單位是預覽像素。'],['source_polygon / source_bbox','原始待測圖座標；顯示預覽另乘 preview_scale。'],['round / cast','Python round、np.rint 為 ties-to-even；astype(uint8) 對非負值截斷。兩者不能互換。'],['精度','不要統一強制 float32。原 read 表達式的 NumPy 百分位型別提升可能使影像為 float64；局部匹配、DINO 正規化明確使用 float32。若改語言／套件，先比較中間陣列。']])+p('所有此文件的像素門檻，除原始影像尺寸與 source 座標外，均指長邊 1536 的預覽空間。OpenCV 尺寸參數是 (width,height)，NumPy 陣列順序是 [y,x]。'))
    section('read','04｜讀圖、參照資料與遮罩',code('''a = imdecode(file_bytes, IMREAD_UNCHANGED)
if a is color: a = cvtColor(a, BGR2GRAY)
require min(a.shape) >= 128 and max(a.shape) <= 16000
lo, hi = percentile(a, [1, 99])
require hi > lo
image = clip((a.astype(float32)-lo)/float(hi-lo), 0, 1)
r = resize(reference, scale=1536/max(reference.shape))''')+p('每張圖各自計算百分位；不是把待測圖套用參照圖的 lo/hi。OpenCV resize 未指定插值時採其預設線性插值。')+table(['遮罩','步驟'],[['structure_mask','r &lt; 0.65 → uint8 → 31×31 全 1 核閉運算 → 保留最大非背景連通區 → 11×11 全 1 核侵蝕 → bool。無主體則報錯。'],['machine_mask','structure_mask 外輪廓 RETR_EXTERNAL / CHAIN_APPROX_SIMPLE → 取最大面積輪廓 → 凸包 → 填滿。檢查機體外包絡，包含亮孔及側邊凹區。'],['有效檢測範圍','machine_mask(r) AND reg.valid。coverage = 有效範圍像素數 / max(machine_mask像素數,1)。coverage &lt; 0.95 停止該張，不能當作正常。'],['快取','鍵為參照絕對路徑＋原始檔案 bytes 的 SHA-256；最多兩份。保存 full、small、structure、machine、ORB 特徵，陣列設為唯讀。換內容即重建，不只看 mtime。']]))
    section('registration','05｜全域對齊：方向選擇與變換矩陣',p('每次 register_one 先設 OpenCV RNG seed=7。參照 ORB 可從快取取用。每個方向獨立做特徵與匹配，但 RANSAC 擬合與最佳方向選擇仍依 0、1、2、3 的順序執行。')+table(['項目','實際規則'],[['方向','np.rot90(raw,k).copy()，k=0,1,2,3（逆時針）；各自縮放長邊到 1536。'],['特徵與配對','ORB_create(nfeatures=7000)；輸入 (image*255).astype(uint8)；BFMatcher(NORM_HAMMING).knnMatch(target_desc,ref_desc,k=2)。'],['配對篩選','每對必須有 2 個鄰居，且 m.distance &lt; 0.72*n.distance；至少 10 個 good matches。'],['擬合','estimateAffinePartial2D(src=target點,dst=reference點, method=RANSAC, ransacReprojThreshold=2)。其他參數沿用已驗證 OpenCV 版本預設。'],['最佳方向','選 inliers 最多者；相等保留先出現方向。最佳 inliers 至少 25；sqrt(M00²+M01²) 必須嚴格介於 0.5 與 2。'],['產生 aligned','warpAffine(target,M,(Wr,Hr),borderValue=1)。valid 用全 1 uint8 圖同樣 warp，再 >0。'],['普通方向直接接受','inliers ≥100 AND 全機體有效範圍的相關係數 ≥0.90 AND coverage ≥0.95。成立就不測鏡像。'],['鏡像選擇','普通方向不足時，對 np.fliplr(raw).copy() 再做四方向。鏡像需 inliers ≥max(50,2×普通inliers)、coverage ≥0.95、相關 ≥0.65，且比普通相關至少高 0.05。普通失敗時其 inliers=0、相關=-1。'],['失敗／退回','鏡像無法支援則退回可用普通結果；普通也失敗才拋出對齊錯誤。']])+p('correlation 僅在 mask 像素 ≥100、兩圖標準差各 ≥0.01 時計算 Pearson correlation，否則回傳 0。<b>不是每張都固定試滿八方向，也不是用 DINO 分數挑方向。</b>'))
    section('refine','06｜3×3 局部位置修正',p('以 structure_mask(r) AND reg.valid 的有效 bounding box，用 linspace(...,4).astype(int) 切成 3×3。每格使用 ECC，只估計平移，不做任意變形。')+table(['階段','參數／條件'],[['估平移','findTransformECC(a,b,I2×3,MOTION_TRANSLATION, EPS|COUNT,50,0.0001, roi_mask×255,gaussFiltSize=5)。'],['接受一格平移','ECC cc &gt;0.82、max(abs(dx),abs(dy)) ≤6；在以 15×15 侵蝕的格內 mask 上，相關性比原來增加至少 0.0001。ECC 失敗不接受該格平移。'],['整張位移場','每格內填其 dx,dy；未接受格填 0；GaussianBlur(flow,(0,0),sigma=12) 平滑接縫。'],['套用','mapx=x+flow_x；mapy=y+flow_y；remap(aligned,mapx,mapy,INTER_LINEAR,borderValue=1)。'],['可靠性紀錄','用實際 remap 結果重新計算各格相關；after ≥0.82 且 after ≥before−0.01 才標 reliable。有不可靠格會顯示警告，並非直接丟掉全部候選。']]))
    section('brightness','07｜明暗補償公式：三輪局部穩健擬合',p('令 R 為參照 r、T 為 corrected；B(X) 為 101×101 boxFilter 平均，borderType=BORDER_REFLECT。目的是預測正常參照在這張待測曝光下應有的灰階 P，不是用 AI 生成參照圖。')+code('''W = ones_like(R, dtype=float32)
repeat 3 rounds:
    mass = max(B(W), 0.01)                       # elementwise
    muR = B(W*R) / mass
    muT = B(W*T) / mass
    varR = max(B(W*R*R)/mass - muR*muR, 0)
    covRT = B(W*R*T)/mass - muR*muT
    gain = clip((covRT+0.002)/(varR+0.002), 0.6, 1.6)
    offset = clip(muT-gain*muR, -0.25, 0.25)
    P = clip(gain*R+offset, 0, 1)
    W = min(1, 0.04/max(abs(P-T), 0.0001))**2
return P''')+p('強差異像素在下一輪的權重降低，以免新增物件把自己的差異「校正掉」。正式加速實作重用暫存陣列、以 64 列為區段運算，最後一輪省略不再使用的 W；運算順序與精度依附錄 brightness_fit.py。'))
    section('difference','08｜差分、連通區與候選特徵',code('''D7 = erode(P, ones((7,7),uint8)) - T
D3 = erode(P, ones((3,3),uint8)) - T
binary = ((D > threshold) & machine_valid_mask).astype(uint8)
binary = morphologyEx(binary, MORPH_OPEN, ellipse(3,3))
# 對 area>1800 或 max(w,h)>110 的大連通區：
# 在其局部範圍使用 ellipse(7,7) 開運算，嘗試分離小物件。
# 完成後重新做 connectedComponentsWithStats。''')+p('D&gt;0 表示待測比正常預測更深；只取正向超門檻差異，不是 abs(R−T)。全 1 的 7×7／3×3 侵蝕核是方形；3×3／7×7 開運算核是橢圓形，不能混用。預設 threshold=0.13，每機種可調，允許 0.03～0.40。')+table(['特徵／篩選','精確定義'],[['基本大小','12 ≤連通區像素面積≤1800；4 ≤max(w,h)≤110。'],['area / fill','area 是連通區有效像素數；fill=area/(w*h)。'],['aspect','對連通區點集做 minAreaRect，aspect=(max(a,b)+1)/(min(a,b)+1)。'],['score','連通區內 D 的第 90 百分位，儲存時 round(...,4)。'],['bipolar','候選外擴 5 像素，取 S=P−T；sum(max(−S,0))/max(sum(max(S,0)),1e−6)，儲存 3 位小數。'],['contrast','連通區內 P−T 的中位數，儲存 4 位。'],['normal_support','N=erode(P,15×15 方形核)；連通區內 N≤T+0.06 的比例，儲存 3 位。'],['shape_similarity','取待測候選外擴 6 像素，參照附近搜尋±12；TM_CCOEFF_NORMED 最大值。patch標準差&lt;0.015 或範圍無效時為0。'],['直接篩掉','shape_similarity ≥0.85；或 area&lt;40 且 (shape_similarity&gt;0.55 或 normal_support&gt;0.5)。注意篩選時使用未 round 的值。']])+p('3×3 補查不是全部合併。補查候選須同時滿足：25≤area≤600、max(w,h)≤50、aspect≤4、fill≥0.25、score≥threshold+0.05、bipolar≤0.5、shape_similarity≤0.55。這一關使用已儲存／round 的候選欄位。若與既有框交集面積 / 較小框面積 &gt;0.25 就視為重複；否則加入，框內 residual 取 D7 與 D3 的逐像素最大值。'))
    section('explain','09｜AI 前的結構排除與線材提示',p('這一段確實可能在送 AI 之前排除候選，重寫時不能省略或誤寫成「全部交給 AI」。有兩個依序嘗試的解釋方法；未被解釋者才送 DINO。')+table(['方法','規則'],[['A：structure_change_evidence','候選外擴12、搜尋±12，TM_CCOEFF_NORMED找位移。候選核心不可參與明暗擬合。context correlation≥0.6，且位移≤2 或 context 比原位置提高≥0.03 才支援。用周邊做四輪 gain∈[0.6,1.6]、offset∈[−0.25,0.25] 穩健擬合。'],['A 的排除條件','context_supported AND 模板 sim≥0.65 AND 修正後正差分總量/原始正差分總量≤0.2 AND 修正後 >threshold 的最大連通區 area&lt;12。分母最小0.001。'],['B：single_reference_evidence.explain','A不成立時：外擴20、搜尋±24；候選及外擴3像素不參與匹配／擬合。周邊≥400像素、std≥0.025；masked相關≥0.85，排除最佳點附近±3後的次佳差距≥0.025。位移&gt;2時相關需提升≥0.08；搜尋邊界最佳點拒絕。'],['B 的排除條件','同樣四輪周邊明暗擬合；正差分量比例≤0.2、最大殘留面積&lt;12、核心abs差異P95≤0.10才接受。'],['結果','A 或 B 支援 → change_type=existing_structure_change，放 structure_changes，保存對照圖，不送 DINO。'],['線材提示','兩方法均不能解釋才執行 wire_review：檢查細長連續線、兩側參照支撐、原位置消失等。只新增 wire_review／排序理由，不直接排除候選。完整門檻見附錄 wire_review.py。']])+p('候選優先排序只影響顏色與先後：有 wire 提示、shape_similarity&gt;0.65、normal_support&gt;0.5、aspect&gt;8、contrast&lt;0.12、bipolar&gt;0.7、area&lt;35 或 fill&lt;0.18 任一理由即 review；否則 high。先 high，再 score 由大到小，最後依序編號。'))
    section('crop','10｜AI 小圖：量化、中心裁切及對比順序',p('同一張檢測先把 r、corrected 各量化一次並快取。這個順序是實作重點；若從原始高解析待測圖另截，便不再是同一份 DINO 輸入。')+code('''# 一張照片做一次：截斷量化，對整張已對齊的兩圖操作
Rq = (clip(r,0,1)*255).astype(uint8).astype(float32)/255
Tq = (clip(corrected,0,1)*255).astype(uint8).astype(float32)/255

# 對每個候選；兩張圖嚴格使用相同 slice，超出右／下邊界由切片裁掉
region = [max(0,y-12):y+h+12, max(0,x-12):x+w+12]
reference_crop, target_crop = Rq[region], Tq[region]

# 各自處理：先 resize/中心 crop，再做對比，不可交換次序
im = RGB_image(rint(clip(crop,0,1)*255).astype(uint8))
resize shortest side to 224 with PIL BICUBIC
# 長邊 int(...) 截斷；中心原點用 (dimension-224)//2
im = center_crop(im,224,224)
a = grayscale(im).astype(float32)
low, high = percentile(a,[1,99])
if high-low >= 1:
    im = RGB_image(rint(clip((a-low)/(high-low),0,1)*255).astype(uint8))
# 否則使用前一階段 RGB im，不強制拉對比
X = float32(im)/255
X = (X - [0.485,0.456,0.406]) / [0.229,0.224,0.225]
X = transpose_HWC_to_CHW(X)[None]  # float32 [1,3,224,224]''')+p('目前 resize_shortest=224，非正方形候選的長邊會在中心裁切時被切掉；外加12不代表保證所有螺絲完整入圖。「局部特徵」也不是另外裁一張更小圖片，而是同一次模型輸出的區域特徵彙整。'))
    section('bank','11｜模型與範例庫如何準備',table(['材料','契約'],[['ONNX','輸入 float32 [1,3,224,224]；輸出 [1,257,384]。輸出須為有限值。'],['輸出解讀','第0個 token為整體特徵；其餘256個區域 token先求平均，再L2正規化。不是256次分類或256次額外推論。'],['特徵','v_global=normalize(output[0,0])；v_local=normalize(mean(output[0,1:],axis=0))。兩個各384維。norm&lt;1e−8視為錯誤。'],['範例順序','先manifest.example_bank.screw.ids的47張，再normal.ids的65張。NPZ第0軸必須嚴格依此順序。'],['八種範例視角','每張原始範例先做第10節的resize、中心裁切、對比處理，之後先不翻／再左右翻，各rotate(0,90,180,270)。每個視角各算global和local。'],['NPZ','paired-features.npz，鍵 bank；形狀[112,8,2,384]。第1軸view0=未翻未轉；第2軸0=global、1=local。全部向量範數≈1，允許驗證誤差0.001。'],['建立成本','112×8個視角特徵事先建立，可重用重複影像特徵。每個查詢小圖只推論一次；不把112張範例每次重跑。'],['manifest','仍保留原CLS example_bank.embeddings供舊版契約驗證；r3實際比分使用外部NPZ。不能只有新增NPZ卻沒有合法manifest。']])+p('模型 SHA-256：<code>'+esc(m['sha256'])+'</code><br>範例特徵 SHA-256：<code>'+esc(m['feature_sha256'])+'</code>。同時檢查檔案 bytes、ID順序與形狀。新增／取消範例要另存新模型目錄並同步重建該版特徵；不能直接改112張的標籤而沿用舊矩陣。'))
    section('scores','12｜DINO 比分公式與雙圖真值表',code('''# qg, ql：查詢小圖的兩個單位向量；bank i = 一張原始範例
whole[i] = max(dot(bank[i, view, 0], qg) for view in range(8))
local[i] = dot(bank[i, 0, 1], ql)   # local只取原始視角，不做8視角max

def margin(scores):
    screw = mean(top3(scores[0:47]))
    normal = mean(top3(scores[47:112]))
    return float(screw-normal)

whole_margin = margin(whole)
local_margin = margin(local)
final_margin = (whole_margin+local_margin)/2
is_screw = final_margin >= 0      # 等於0也算像螺絲

# 參照、待測各獨立算一次，不直接相減兩圖的embedding
keep = target_is_screw and not reference_is_screw''')+table(['參照圖判斷','待測圖判斷','結果'],[['不像','像','保留候選，供人工複判'],['不像','不像','排除'],['像','不像','排除'],['像','像','先檢查第13節一次補看；不符合條件就依初判排除']])+p('示意數字（不是實測案例）：整體螺絲均值0.62、正常0.58 → +0.04；局部螺絲0.55、正常0.57 → −0.02；合併為+0.01，該張像螺絲。若參照圖合併分數−0.03、待測+0.01，就保留。分數是相似度差，不是「有幾成正確」。每種特徵、每一類各選最像3張，可能選到不同的範例，不是固定六張一直用。'))
    section('recheck','13｜一次局部補看的完整規則',code('''first = classify_pair(target_crop, reference_crop)
if first.status != active: return first
if not (first.reference_is_screw and first.target_is_screw):
    return first

ex = extract_local_component(Rq,Tq,candidate)
if not eligible(ex): return first
box = square_around_component(ex) + padding_2_each_side
return classify_pair(Tq[box], Rq[box])  # 僅一次，不遞迴、不投票挑高分''')+table(['步驟','確切做法'],[['周邊對位','外擴52、搜尋±12；候選外擴12的核心不參與masked TM_CCOEFF_NORMED。非有限相關值設−1。correlation≥0.75且abs(dx),abs(dy)&lt;12才稱context_reliable。'],['周邊明暗','用上述周邊mask做四輪穩健 gain/offset 擬合，界限同前。所得dx,dy,gain,offset只用於找差異輪廓，不套用到最後DINO小圖。'],['找輪廓','另在候選外擴32的窗口，將參照依dx,dy移動、明暗擬合；delta=GaussianBlur(fitted_reference-target,(3,3),0.6)；delta&gt;0.08的連通區。'],['選哪一個','在與原候選重疊的非背景連通區中，選重疊像素數最多者；並列依 max((count,label)) 選 label較大者。非按DINO分數挑選。'],['產生方框','物件bbox=(bx,by,bw,bh)，side=max(bw,bh)；左上角=(round(bx+bw/2−side/2),round(by+bh/2−side/2))；side不變，再四側各加2。'],['必要條件','context_reliable；物件area≥12；物件bbox不得碰到或跨過外擴32搜尋窗口的任一邊；補看方框完整在影像內。邊界判斷使用≤或≥，不是只判越界。'],['最終判斷','從原本 Rq/Tq 相同座標取圖，依第10～12節重算。新結果直接取代初判，不取兩次較高分、不做OR合併。若新推論失敗，Snapshot回傳error/manual_review，不當作成功排除。'],['不使用的診斷欄位','paired_geometry.compare中的outcome、dark_share等目前不是補看資格或最終螺絲判斷條件；重寫時勿自行加上。']])+p('補看只改AI收到的小圖，不修改差分候選x/y/w/h、編號或畫面檢測框。範圍過小／切片為空等幾何異常並非都有統一保護；詳見第16節現有錯誤邊界。'))
    section('mapping','14｜原圖顯示框與座標回推',p('初始顯示框以候選外擴5個預覽像素的四角，透過下面映射回原始待測圖。AI初判則外擴12，兩者用途不同。')+code('''p = [x,y] in corrected frame
idx = clip(rint(p), valid_preview_index_range)
global_p = p + flow[idx.y,idx.x]
q = invertAffineTransform(M) * global_p
q = (q+0.5)/target_scale - 0.5   # OpenCV resize像素中心慣例

# 逆轉np.rot90，H/W是原始raw大小
k=0: original = (qx, qy)
k=1: original = (Wraw-1-qy, qx)
k=2: original = (Wraw-1-qx, Hraw-1-qy)
k=3: original = (qy, Hraw-1-qx)
if mirrored: original.x = Wraw-1-original.x
clip original to [0,Wraw-1] × [0,Hraw-1]

source_polygon = round(mapped_4_corners, 2)
source_bbox = floor(min_corners), ceil(max_corners)
preview_scale = 1536/max(raw.shape)
display_polygon = rint(source_polygon*preview_scale)''')+p('保存供人工看的 crop_i：原始待測 source_bbox 外擴 pad=max(45,框寬//2,框高//2)，裁至原圖邊界。這張較寬的人工小圖不是 DINO 實際輸入。AI排除後仍保留原候選ID及相關圖片。'))
    section('runtime','15｜CPU／GPU與三項加速如何實作',table(['位置','正式r3做法'],[['方向計算','ThreadPoolExecutor(max_workers=2)準備4個旋轉方向的resize、ORB與配對；OpenCV內部threads=16；結果依原順序收集，RANSAC擬合依序做。鏡像是否啟用仍由品質決定。'],['差分','亮度擬合重用暫存陣列、64列區段、最後不計未使用權重；候選兩次掃描共用15×15 erode(P)及P−T。'],['候選核對','兩個worker平行做同一條check_candidate鏈，OpenCV內部threads=1；以map維持原順序。結構分類與排序規則不變。'],['全域狀態','整張detect持有RLock；每次暫時改OpenCV threads後finally恢復。CURRENT ContextVar保存本張參照與量化影像；不是跨照片共用可變target。'],['CPU模型','onnxruntime CPUExecutionProvider；intra_op_num_threads=4；模型session長駐。'],['GPU模型','Windows獨立DirectML工作程序，DXGI挑vendor 0x10de的NVIDIA adapter；不是直接使用第0張顯示卡，也不是CUDA版比較。'],['GPU session','固定[1,3,224,224]的自由維度；enable_mem_pattern=False；ORT_SEQUENTIAL；intra_op_num_threads=4；providers=[指定裝置DmlExecutionProvider,CPUExecutionProvider]，停用session fallback。'],['GPU限制','檢查第一provider為DML只證明DML後端成功建立；因仍列CPU provider，不能據此宣稱每一個ONNX算子都100%在GPU上。'],['程序傳輸','stdin/stdout二進位：4-byte little-endian JSON header長度 → UTF-8 JSON（含bytes）→ payload。request float32 little-endian NCHW；response float32 little-endian [1,257,384]。普通回應timeout=30s，初始metadata=90s。stdout不可混入log。'],['切換','設定套用先建候選session，驗證成功才儲存選擇；已開始照片保有原模型快照。GPU切換失敗保留原設定，不冒充GPU。'],['版本核對環境','NumPy 2.5.4；OpenCV headless 5.0.0.93；Pillow 13.0.0；CPU ORT 1.31.1；GPU ORT DirectML 1.24.4。依實際交付環境與requirements再核對；換版本須重驗。']]))
    section('errors','16｜錯誤、輸出與紀錄的契約',table(['情況','目前行為'],[['讀圖、尺寸、全域對齊、覆蓋失敗','拋出整張檢測錯誤，由外層記錄analysis_error；不能輸出「正常」。'],['局部ECC失敗','該格不接受平移，流程繼續，保存局部可靠性警告。'],['Snapshot.classify推論／前處理失敗','回傳status=error、label=uncertain、action=manual_review；不列為成功discard。'],['模型載入或切換失敗','manager可回傳之前已驗證的session及明確error/requested資訊；一張圖固定一份Snapshot。不可省略錯誤狀態假裝新模型成功載入。'],['補看幾何計算異常','extract呼叫在Snapshot.classify外，未統一catch；OpenCV／切片幾何錯誤可能中止整張。重寫若新增保護，是需另驗證的行為改動，文件不把它描述成已全面保護。'],['保留','action=manual_review、分類通常label=screw；表示AI保留候選供人看，不是人工確認的掉落螺絲。'],['排除','action=discard；移至filtered_candidates並保留classification、ID與圖片。'],['結構變化','structure_changes獨立保存；不要與filtered_candidates的AI排除混為同一統計。']])+code('''result = {
  "pipeline": "dino-combined-20261104-r3", "version": 13,
  "model": {"fingerprint": "...", "execution": "cpu|gpu", ...},
  "matrix": [[...],[...]], "rotation_ccw": 0, "mirrored_input": False,
  "local_alignment": [...], "coverage": 1.0,
  "baseline_candidates": [...], "structure_changes": [...],
  "pre_ai_count": N, "proposal_count": K, "filtered_count": N-K,
  "candidates": [...], "filtered_candidates": [...],
  # 每個candidate：id,x,y,w,h,area,score,features,priority,
  # source_polygon,source_bbox,crop_box,classification
}
# classification.paired_evidence.reference / target保存各自label及margin
# r3保存input_sha256；補看另有paired_recheck.initial與box
# baseline框數、結構變化框數、AI候選框數，都不是螺絲顆數。''')+p('儲存 reference.png、aligned.png、difference.png、source.png、overlay.png、all_overlay.png、各候選人工crop/reference_crop，以及結構與舊法核對圖片。可重建的判斷稽核還應保存模型／範例SHA、原圖SHA、實際AI輸入hash、框及兩圖分數。'))
    section('io','17｜取圖、快取與最小呼叫範例',p('外層取圖預設每3秒掃描，大小／mtime穩定至少15秒後，分塊複製並算SHA-256，完整解碼驗證，再原子改名提交本機快照。來源檔不修改。待處理事件進佇列，完成後記done；analysis_error可重試。來源改變時只顯示當前來源且present的快照，不刪舊圖與人工紀錄。重作核心可先使用已完整寫好的單張本機檔，之後才接佇列。')+code('''# 可在專案根目錄執行；需要既有模型資料，輸出請用新的測試目錄。
from model_manager import ModelManager
from detector import detect

snapshot = ModelManager(allow_cpu=True, execution_override="cpu").snapshot(
    "dino-paired-optimized-47-20261104-r3")
if snapshot.error:
    raise RuntimeError(snapshot.error)
result = detect("reference.tiff", "target.tiff", "rd-single-photo",
                threshold=0.13, model_snapshot=snapshot,
                output_directory="rd-output/new-run")
# 改成 execution_override="gpu" 使用已安裝的隔離GPU工作程序。
# 不呼叫整批介面、不覆寫原outputs，也不更新正式人工紀錄。''')+p('library.analyze_file的分析快取鍵包含引擎指紋、參照SHA＋機種ID、待測SHA、threshold、模型identity及error/requested。只依檔名快取會在換模型／機種後誤用舊結果。更新版本不應主動重跑舊done事件；人工紀錄應與AI新舊版本分開保存。'))
    section('verify','18｜RD重作的驗收方式與已知界限',p('先逐階段比對，不要只看最後螺絲分數或總候選數。此文件沒有重跑檢測；下面是既有r3整合驗證紀錄。')+table(['順序','比對項目'],[['1','鎖定同一ONNX／範例NPZ SHA、ID順序、套件版本、輸入檔SHA與threshold。'],['2','比normalized影像、遮罩、方向、matrix、valid、coverage、flow與corrected；數值不同就先停下查。'],['3','比亮度P、差分D7/D3、連通區、所有候選座標／屬性／編號、結構變化；不是只比候選總數。'],['4','對照每個候選真正送DINO的224×224 RGB bytes SHA，包含base與recheck的reference/target；不能拿人工放大圖代替。'],['5','比模型輸出global/local單位向量、whole/local margins、兩張圖label、是否補看與補看box、最終keep/discard。浮點小差可另定容差，但label／action必須一致。'],['6','比source_polygon／bbox及輸出圖bytes；換不同編碼器可比解碼像素，另說明不再要求PNG壓縮bytes一致。'],['7','CPU與GPU分別核對；切換失敗、無GPU、來源換資料夾、斷線掃描、重新啟動、重複照片及人工紀錄保留也要驗證。'],['8','效能只在結果一致後測：交錯原方法／新方法，分開資料夾等待、冷啟動、模型載入、開始檢測到DINO完成、儲存收尾；記錄GPU時脈／功率／限制標記。']])+p('既有固定單圖：137個候選、276次推論（274次初判＋2次補看）、368張輸出圖；來源程式與實際可攜EXE，CPU／GPU判斷及影像均相同。137不是每張必有的數量，276也不是固定上限；一般為2N＋2R，R為符合資格的補看候選數。')+p('既有59個固定案例：原本兩顆螺絲、另2個已確認位置維持判對；5個目視疑似位置判出2個、仍漏3個（疑似不是完整人工標準答案）；50個正常對照無誤報。不是獨立完整準確率測試。任何「差分沒提候選」的物件，後段DINO不會自行全圖找回。')+p('既有GPU八次交錯平均：原方法11.98秒、新方法10.82秒（開始檢測到DINO判完；已暖機，排除資料夾等待）。不能把這個單圖結果保證為所有照片／硬體的時限。'))
    # Keep control-flow pseudocode alongside the visual overview.
    key,title,body=sections[1]
    sections[1]=(key,title,body+p('<b>主控偽程式碼（函式內細節依後續章節與附錄）</b>')+code('''snapshot = freeze_model_for_this_photo()
R, cached_masks, reference_features = prepare_reference(reference_file)
T = read_and_normalize(target_file)
reg = choose_registration(R, T)       # 普通4方向；必要時才加鏡像4方向
if coverage(reg) < 0.95: raise InspectionError
legacy = legacy_proposals(R, reg.aligned)  # 只供核對，不加進AI候選
corrected, flow, regions = local_refine(R, reg.aligned)
P = compensate_brightness(R, corrected)
raw_candidates = find_D7_candidates_and_recover_D3(P, corrected)
candidates, structure_changes = explain_existing_structure(raw_candidates)
candidates = assign_priority_sort_and_number(candidates)
Rq, Tq = quantize_frames_once(R, corrected)

for c in candidates:
    first = independent_pair_classification(Rq, Tq, padded12(c))
    final = first
    if first.active and first.reference_screw and first.target_screw:
        local_object = extract_difference_component(Rq, Tq, c)
        if eligible_for_one_recheck(local_object):
            final = independent_pair_classification(
                Rq, Tq, component_square_plus2(local_object))
    if final.status != active:
        retain_for_manual_review(c, final)  # 不冒充成功排除
    elif final.target_screw and not final.reference_screw:
        retain_for_manual_review(c, final)
    else:
        discard_but_keep_audit_record(c, final)

map_display_boxes_back_to_original(flow, reg)
save_all_results_images_and_error_metadata()'''))
    sources=['detector.py','detection_runtime.py','brightness_fit.py','registration_candidate.py','single_reference_evidence.py','wire_review.py','dino_adapter.py','dino_paired_optimized.py','paired_geometry.py','model_manager.py','model_adapters.py','gpu_runtime.py','gpu_worker.py','gpu_devices.py','gpu_protocol.py','runtime_paths.py','station_settings.py','dino_examples.py','acquisition.py','library.py','release_validation.py','verify_optimized_cases.py']
    appendix='';hashes={}
    for filename in sources:
        payload=(ROOT/filename).read_bytes();source=(ROOT/filename).read_text(encoding='utf-8');ast.parse(source);digest=hashlib.sha256(payload).hexdigest();hashes[filename]=digest
        appendix+='<details class="source" id="src-'+filename.replace('.','-')+'"><summary>'+esc(filename)+' <small>'+str(len(source.splitlines()))+' 行</small></summary><div class="sourcebar"><span>SHA-256 '+digest+'</span><button class="copy" type="button">複製原始碼</button></div><pre><code data-file="'+filename+'">'+esc(source)+'</code></pre></details>'
    section('source','19｜完整原始碼快照：重作與逐行對照',p('以下為產生文件當下的正式r3相關原始碼，不是縮短過的範例。HTML內統一採LF換行；SHA-256標示原始檔案bytes的值。所有Python程式碼已做語法解析；本次只讀取並嵌入，沒有執行檢測或修改正式程式。核心模組需依依賴關係放在同一專案，並提供前述模型材料；不是每個檔案都能單獨執行。')+'<button id="expand" type="button">展開全部原始碼</button> <button id="collapse" type="button">收合全部原始碼</button>'+appendix)
    css='''*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}body{margin:0;color:#183948;background:#f3f6f8;font:16px/1.85 "Microsoft JhengHei",system-ui,sans-serif}aside{position:fixed;inset:0 auto 0 0;width:260px;background:#102e3c;color:#e5f1f5;padding:26px 20px;overflow:auto}aside strong{font-size:20px}aside p{color:#a7c5d2;font-size:13px}nav a{display:block;color:#d5e7ef;text-decoration:none;font-size:14px;line-height:1.55;padding:7px 8px;border-radius:5px}nav a:hover{background:#245167}main{margin-left:260px;max-width:1390px;padding:40px 42px 70px}header{border-top:6px solid #07868d;background:white;padding:30px 34px;margin-bottom:26px}h1{font-size:34px;line-height:1.4;margin:12px 0}header p{margin:8px 0}.tag{font-size:13px;color:#00767e;font-weight:bold;letter-spacing:1px}section{background:white;padding:26px 32px;margin:20px 0;border:1px solid #dde6eb;border-radius:8px;overflow:hidden}h2{font-size:23px;line-height:1.5;margin:0 0 18px;color:#103b4d}p{margin:12px 0}code{font-family:Consolas,"Microsoft JhengHei",monospace;font-size:.9em;overflow-wrap:anywhere}p code,td code{background:#edf3f5;padding:2px 4px}pre{background:#112b38;color:#e0f1f6;border-radius:7px;padding:20px;overflow:auto;tab-size:4;line-height:1.65;font-size:14px;max-height:800px}pre code{white-space:pre;overflow-wrap:normal;font-size:inherit}.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:15px;margin:14px 0}th,td{text-align:left;vertical-align:top;border:1px solid #d7e3e9;padding:12px 15px}th{background:#e8f2f4;color:#164c5b}td:first-child{min-width:145px;width:22%;font-weight:600}.flow{max-width:770px;margin:18px auto}.step{border:1px solid #b5d1dc;border-left:5px solid #07868d;background:#f0f7f8;padding:12px 18px;border-radius:6px}.step b{display:block}.step span{font-size:15px;display:block;color:#405d6b}.arrow{text-align:center;color:#278a92;font-size:22px;line-height:30px}button{background:#057c84;color:white;border:0;border-radius:5px;padding:9px 13px;cursor:pointer;font:inherit;font-size:14px}button:hover{background:#075965}.source{border:1px solid #cbdce5;margin:14px 0;border-radius:6px}.source summary{cursor:pointer;background:#edf4f6;padding:12px 16px;font-weight:600}.source small{font-weight:400;color:#567583}.source pre{border-radius:0;margin:0;max-height:680px}.sourcebar{display:flex;align-items:center;gap:12px;justify-content:space-between;padding:12px;font:11px/1.6 Consolas,monospace;overflow-wrap:anywhere}.sourcebar button{flex-shrink:0}footer{font-size:13px;color:#577382}a{color:#087983}input{width:100%;padding:9px;margin:15px 0;color:#142f3e;border-radius:5px;border:0}.tools{display:flex;gap:10px;margin-top:15px}.notice{background:#fff7e6;border-left:4px solid #d9952d;padding:12px 16px}section:target{border-color:#07868d}@media(max-width:1050px){aside{position:static;width:auto;padding:18px}nav{columns:2}main{margin:0;padding:20px}header,section{padding:22px}h1{font-size:27px}}@media print{aside,.tools,button,.sourcebar{display:none!important}main{margin:0;max-width:none;padding:0}body{background:white;font-size:11pt}header,section{border:0;padding:10px 0;margin:10px 0}h1{font-size:22pt}h2{font-size:16pt;break-after:avoid}table{font-size:9pt}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:none!important;font-size:8pt;background:#f1f4f5;color:black}pre code{white-space:pre-wrap}#source{display:none}tr,.step{break-inside:avoid}a{color:inherit;text-decoration:none}}'''
    nav=''.join('<a href="#'+key+'">'+esc(title)+'</a>' for key,title,_ in sections)
    body=''.join('<section id="'+key+'"><h2>'+esc(title)+'</h2>'+content+'</section>' for key,title,content in sections)
    js='''document.querySelector('#expand').onclick=()=>document.querySelectorAll('.source').forEach(x=>x.open=true);document.querySelector('#collapse').onclick=()=>document.querySelectorAll('.source').forEach(x=>x.open=false);document.querySelector('#print').onclick=()=>window.print();document.querySelector('#filter').oninput=e=>{const q=e.target.value.toLowerCase();document.querySelectorAll('nav a').forEach(a=>a.hidden=!a.textContent.toLowerCase().includes(q));};document.querySelectorAll('.copy').forEach(b=>b.onclick=async()=>{const code=b.closest('.source').querySelector('code');try{await navigator.clipboard.writeText(code.textContent);b.textContent='已複製';}catch(e){const r=document.createRange();r.selectNodeContents(code);const s=window.getSelection();s.removeAllRanges();s.addRange(r);b.textContent='已選取，請按 Ctrl+C';}});'''
    document='<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>X-RAY r3｜RD核心流程實作規格</title><style>'+css+'</style></head><body><aside><strong>X-RAY · RD 實作規格</strong><p>r3 / 2026-11-04<br>差分 → DINO 雙圖 → 結果</p><input id="filter" aria-label="篩選目錄" placeholder="搜尋目錄關鍵字"><nav>'+nav+'</nav></aside><main><header><span class="tag">ENGINEERING IMPLEMENTATION SPECIFICATION</span><h1>差分與 DINO 雙圖檢測<br>可依此重建的 RD 技術說明</h1><p>先掌握資料流，再依公式、參數和原始碼重作。所有流程圖、說明及 '+str(len(sources))+' 份程式快照都在這個 HTML，離線可開啟。</p><div class="notice">本文件描述目前正式 r3 的實際行為，含限制及例外；不是新一輪圖資檢測報告。未更動模型、設定、圖資、人工紀錄或可攜版。</div><div class="tools"><button id="print" type="button">列印／存成 PDF（規格本文）</button><a href="#source">直接看原始碼附錄 ↓</a></div></header>'+body+'<footer>以工作目錄原始碼與目前r3 manifest核對產生；附錄每份程式列SHA-256。文件無外部CDN、字型、網路API或追蹤程式。</footer></main><script>'+js+'</script></body></html>'
    OUT.write_text(document,encoding='utf-8',newline='\n')
    qa=ROOT/'workspace/rd-implementation-html-20261104';qa.mkdir(parents=True,exist_ok=True)
    (qa/'source-snapshot-sha256.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(html=str(OUT),sections=len(sections),source_files=len(hashes),bytes=OUT.stat().st_size),ensure_ascii=False))

if __name__=='__main__':main()
