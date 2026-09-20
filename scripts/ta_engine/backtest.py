"""Gross event study and explicitly configured long-only execution simulation."""
import numpy as np

def event_study(d,events,horizons=(1,3,5,10,20)):
    out=[]
    for e in events:
        pos=e.get('confirmation_pos')
        if e.get('direction') not in ['BULLISH','BEARISH'] or pos is None or pos+1>=len(d):continue
        if 'engine_segment' in d and d.iloc[pos].engine_segment!=d.iloc[pos+1].engine_segment:continue
        entry_pos=pos+1;entry=float(d.iloc[entry_pos].open);direction=e['direction'];row=dict(event_id=e['id'],rule_id=e['rule_id'],pattern=e['pattern'],direction=direction,signal_date=str(d.iloc[pos].session_date),entry_pos=entry_pos,entry_date=d.iloc[entry_pos].session_date,entry_open=entry,horizons={})
        for h in horizons:
            end=entry_pos+h-1
            if end>=len(d):row['horizons'][str(h)]=dict(status='CENSORED');continue
            q=d.iloc[entry_pos:end+1]
            if 'engine_segment' in q and q.engine_segment.nunique()!=1:row['horizons'][str(h)]=dict(status='GAP');continue
            raw=float(q.iloc[-1].close/entry-1);signed=raw if direction=='BULLISH' else -raw
            adverse=float(q.low.min()/entry-1) if direction=='BULLISH' else float(1-q.high.max()/entry)
            favorable=float(q.high.max()/entry-1) if direction=='BULLISH' else float(1-q.low.min()/entry)
            row['horizons'][str(h)]=dict(status='AVAILABLE',raw_return=raw,direction_adjusted_return=signed,mae=adverse,mfe=favorable,end_date=q.iloc[-1].session_date)
        out.append(row)
    return out

def walk_forward_summary(d,study,horizons=(1,3,5,10,20)):
    """Chronological 60/20/20 report with a max-horizon embargo at boundaries."""
    n=len(d);a=int(n*.6);b=int(n*.8);out={}
    for name,lo,hi in [('train',0,a),('validation',a,b),('test',b,n)]:
        rows=[]
        for r in study:
            p=r['entry_pos']
            if name=='train' and p+max(horizons)<hi:rows.append(r)
            elif name=='validation' and p>=lo+max(horizons) and p+max(horizons)<hi:rows.append(r)
            elif name=='test' and p>=lo+max(horizons):rows.append(r)
        metrics={}
        for h in horizons:
            vals=[r['horizons'][str(h)]['direction_adjusted_return'] for r in rows if r['horizons'][str(h)]['status']=='AVAILABLE']
            metrics[str(h)]=dict(n=len(vals),mean=float(np.mean(vals)) if vals else None,median=float(np.median(vals)) if vals else None,win_rate=float(np.mean(np.asarray(vals)>0)) if vals else None)
        out[name]=dict(date_start=d.iloc[lo].session_date if lo<n else None,date_end=d.iloc[hi-1].session_date if hi else None,events=len(rows),metrics=metrics)
    return dict(method='chronological_60_20_20_with_20_bar_embargo',selection_warning='No parameter search is performed here; repeated use of the test split contaminates it.',splits=out)

def simulate_long(d,events,profile):
    required={'initial_cash','fee_bps','slippage_bps','max_holding_bars','lot_size','max_chase_atr'}
    missing=required-set(profile)
    if missing:return dict(status='EXECUTION_PROFILE_REQUIRED',missing=sorted(missing),trades=[])
    cash=float(profile['initial_cash']);trades=[];active_until=-1
    for e in events:
        pos=e.get('confirmation_pos')
        if e.get('state') not in ['CONFIRMED','RETEST_CONFIRMED','FAILED_BREAKOUT'] or e.get('direction')!='BULLISH' or pos is None or pos+1>=len(d) or pos+1<=active_until:continue
        j=pos+1;open_=float(d.iloc[j].open);atr=float(d.iloc[pos].atr);signal=float(e.get('confirmation_price',d.iloc[pos].close))
        if np.isfinite(atr) and open_-signal>profile['max_chase_atr']*atr:continue
        entry=open_*(1+profile['slippage_bps']/10000);lot=int(profile['lot_size']);qty=int(cash/(entry*(1+profile['fee_bps']/10000))//lot*lot)
        if qty<=0:continue
        end=min(len(d)-1,j+int(profile['max_holding_bars'])-1);exit_=float(d.iloc[end].close)*(1-profile['slippage_bps']/10000);fees=(entry+exit_)*qty*profile['fee_bps']/10000;pnl=(exit_-entry)*qty-fees;cash+=pnl;active_until=end
        trades.append(dict(event_id=e['id'],entry_date=d.iloc[j].session_date,exit_date=d.iloc[end].session_date,qty=qty,entry=entry,exit=exit_,fees=fees,pnl=pnl,cash_after=cash))
    return dict(status='RESEARCH_SIMULATION_ONLY',final_cash=cash,trades=trades,profile=profile)
