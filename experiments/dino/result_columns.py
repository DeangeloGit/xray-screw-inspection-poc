"""Report-only outcome columns; candidate decisions are supplied, never changed."""
STYLE='''main{max-width:1680px}.decision-scroll{overflow-x:auto}.decision-columns{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px;align-items:start}.decision-column{min-width:0}.decision-column>h3{padding:12px 16px;margin:8px 0;background:#e6edf1;border-bottom:3px solid #8398a4}.decision-column[data-result="keep"]>h3{background:#fff0dd;border-color:#bd792c}.decision-column article{margin:14px 0;overflow-wrap:anywhere}.decision-column .pair{width:100%;max-width:800px}.decision-column details{margin:12px 0;padding:12px}.decision-column details article{padding:12px}.decision-empty{padding:16px;background:white}@media(max-width:900px){.decision-columns{min-width:1000px}}'''
def columns(items,card,keep,compact=False):
    result='<div class="decision-scroll"><div class="decision-columns">'
    for outcome,name,label in ((False,'exclude','排除'),(True,'keep','保留警報')):
        selected=[z for z in items if bool(keep(z))==outcome]
        result+=f'<section class="decision-column" data-result="{name}"><h3>{label}（{len(selected)}）</h3>'
        if not selected:result+='<p class="decision-empty">0 個候選</p>'
        elif compact:
            result+=card(selected[0])
            if len(selected)>1:result+=f'<details><summary>展開其餘{len(selected)-1}個相同結果候選</summary>'+''.join(card(z) for z in selected[1:])+'</details>'
        else:result+=''.join(card(z) for z in selected)
        result+='</section>'
    return result+'</div></div>'
