"""Run causal event study and optional configured long-only simulation."""
import argparse,json
from pathlib import Path
import pandas as pd
from ta_engine.backtest import event_study,simulate_long,walk_forward_summary

def run(analysis,out,profile=None):
    analysis=Path(analysis);a=json.loads(analysis.read_text(encoding='utf8'));out=Path(out);out.mkdir(parents=True,exist_ok=False);results={}
    for key,frame_file in a['frames'].items():
        if not key.startswith('equity_'):continue
        d=pd.DataFrame(json.loads((analysis.parent/frame_file).read_text(encoding='utf8')));events=json.loads((analysis.parent/a['pattern_files'][key]).read_text(encoding='utf8'))
        study=event_study(d,events);result=dict(event_study=study,walk_forward=walk_forward_summary(d,study))
        if profile:result['simulation']=simulate_long(d,events,json.loads(Path(profile).read_text(encoding='utf8')))
        else:result['simulation']=dict(status='EXECUTION_PROFILE_REQUIRED',reason='No fees, slippage, lot size, cash or chase limit supplied')
        results[key]=result
    (out/'backtest.json').write_text(json.dumps(dict(schema_version=2,analysis_sha256=__import__('hashlib').sha256(analysis.read_bytes()).hexdigest(),research_only=True,causal_entry='next_bar_open_after_confirmation',costs_in_event_study=False,results=results),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    return out/'backtest.json'
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--analysis',required=True);p.add_argument('--out',required=True);p.add_argument('--execution-profile');a=p.parse_args();print(run(a.analysis,a.out,a.execution_profile))
