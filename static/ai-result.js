window.aiResultText=function(c){
 if(!c||c.status==='disabled')return 'AI 尚未啟用；請人工確認。';
 if(c.status==='error')return 'AI 無法判讀：'+(c.error||'模型暫時不可用')+'；請人工確認。';
 const labels={screw:'疑似螺絲',cable:'偏向線材',structure:'偏向既有結構',circuit_board:'偏向電路板',metal_plate:'偏向金屬板',hole:'偏向孔洞',background:'偏向背景',uncertain:'無法確認螺絲'};
 let detail='';
 if(c.screw_example_evidence?.supported)return 'AI：螺絲外型範例支持保留 · 螺絲範例領先非螺絲 '+c.screw_example_evidence.margin.toFixed(4)+' · '+c.model_id;
 if(c.action==='discard')return 'AI 已排除：'+(labels[c.label]||c.label)+(c.shape_evidence?'（CLIP 線材外型再判讀）':'')+' · 領先螺絲分數 '+Math.abs(c.screw_margin).toFixed(4);
 if(c.filter_recommendation==='review')return 'AI 建議：不確定，保留複核 · 螺絲與'+(labels[c.raw_label]||c.raw_label).replace(/^偏向/,'')+'分數接近（差 '+Math.abs(c.screw_margin).toFixed(4)+'，保留範圍 '+c.review_margin+'） · '+c.model_id;
 if(c.score_kind==='cosine_similarity')detail=' · 螺絲相對分數 '+c.screw_margin.toFixed(3)+'（相似度差，非機率）';
 else if(c.score_kind==='detector_confidence')detail=' · 螺絲分數 '+c.screw_score.toFixed(3)+'／門檻 '+c.confidence_threshold;
 return 'AI 建議：'+(labels[c.label]||c.label)+detail+' · '+c.model_id+'（仍需人工確認）';
};
