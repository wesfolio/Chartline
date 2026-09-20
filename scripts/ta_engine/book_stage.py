"""Separate textbook evidence and frozen directional judgment from entry timing."""
import json
import re
from pathlib import Path

CATALOG=json.loads((Path(__file__).resolve().parents[2]/'references/model-catalog.json').read_text(encoding='utf8'))
MODEL_IDS={m['id'] for m in CATALOG['models']}
FROZEN_FIELDS=['direction','target_date','reference_close','confidence','support','opposition','resolution','invalidation']
FORBIDDEN=re.compile(r'BBI|多空指标|Q(?:36|37|40)',re.I)

def book_view(analysis,frames):
    """Whitelist ordinary price/volume evidence, omitting personal timing fields."""
    keys=['name','symbol','market','as_of','target_date','audits','correlations','latest_patterns','fusion_setups','warnings']
    out={k:analysis[k] for k in keys if k in analysis}
    out['models']=[m for m in analysis['models'] if m['rule_id'] in MODEL_IDS]
    columns=['session_date','open','high','low','close','volume','atr','scale','rsi','dif','dea','hist','macd_cross','obv','rvol','structure','rsi_divergence','appearance16','body','upper_shadow','lower_shadow']+[kind+str(n) for kind in ['sma','ema'] for n in [5,10,20,50,200]]
    out['series']={key:[{k:row[k] for k in columns if k in row} for row in rows] for key,rows in frames.items()}
    out['model_catalog']=CATALOG
    # Existing generic wording may name the excluded user rule; omit those sentences.
    def clean(x):
        if isinstance(x,dict):return {k:clean(v) for k,v in x.items() if not FORBIDDEN.search(k)}
        if isinstance(x,list):return [clean(v) for v in x]
        if isinstance(x,str):return '。'.join(s for s in x.split('。') if not FORBIDDEN.search(s))
        return x
    return clean(out)

def validate_book_stage(n,c):
    book=n.get('book_judgment')
    if not isinstance(book,dict):raise ValueError('Formal report requires frozen book_judgment before timing review')
    if FORBIDDEN.search(json.dumps(book,ensure_ascii=False)):raise ValueError('Book judgment must exclude BBI evidence')
    if any(book.get(k)!=c.get(k) for k in FROZEN_FIELDS):raise ValueError('Timing review cannot change frozen book judgment')
    reviews=book.get('model_review',{})
    if set(reviews)!=MODEL_IDS:raise ValueError('Book stage must review all 27 model families')
    for key,value in reviews.items():
        if value.get('status') not in ['APPLIES','NO_SIGNAL','INSUFFICIENT','NOT_APPLICABLE'] or not value.get('reason'):raise ValueError('Each book model requires status and reason')
        if c.get('coverage_review',{}).get(key)!=value:raise ValueError('Final review differs from frozen book model review')
    evidence=book.get('evidence_rule_ids',[])
    if not evidence or not set(evidence)<=MODEL_IDS:raise ValueError('Direction evidence must cite book model families')
    for key in ['summary','scenarios','pattern_notes']:
        if FORBIDDEN.search(json.dumps(n.get(key,''),ensure_ascii=False)):raise ValueError('Put BBI commentary in final timing section only')
    for key,value in n.get('model_notes',{}).items():
        if not key.endswith(':Q36') and FORBIDDEN.search(str(value)):raise ValueError('Book model commentary must exclude BBI')
    for key,value in c.get('coverage_review',{}).items():
        if key not in {'Q36','Q37','Q40'} and FORBIDDEN.search(json.dumps(value,ensure_ascii=False)):raise ValueError('Keep BBI in final timing rule review')
    if not n.get('timing_review'):raise ValueError('Separate final timing_review required')
    return book
