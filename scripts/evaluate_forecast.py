"""Score an archived forecast against an explicitly supplied later observation."""
import argparse,json
from pathlib import Path
from ta_engine.decision import forecast_outcome

def evaluate(n,rows):
    c=n['conclusion'];matches=[r for r in rows if str(r.get('session_date',r.get('date')))[:10]==c['target_date']]
    if len(matches)!=1:raise ValueError('Exactly one target-date observation required')
    r=matches[0]
    if r.get('price_basis')!=c.get('price_basis'):raise ValueError('Matching explicit price basis required')
    return dict(target_date=c['target_date'],**forecast_outcome(c['reference_close'],float(r['close']),c['direction']),trade_profitability_inferred=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--narrative',type=Path,required=True);p.add_argument('--observed',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=evaluate(json.loads(a.narrative.read_text(encoding='utf8')),json.loads(a.observed.read_text(encoding='utf8')))
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
