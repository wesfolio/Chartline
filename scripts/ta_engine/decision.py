"""Validate analyst synthesis and execution chronology; never invent a forecast."""
import math
import pandas as pd
from ta_data.core import schedule
from ta_engine.book_stage import validate_book_stage

def next_session(market, date):
    start=(pd.Timestamp(date)+pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    end=(pd.Timestamp(date)+pd.Timedelta(days=40)).strftime('%Y-%m-%d')
    return schedule(market,start,end).session_date.iloc[0]

def validate_decision(a,n,frames):
    c=n.get('conclusion')
    if not isinstance(c,dict):raise ValueError('Formal report requires conclusion; use --draft for an evidence-only report')
    required=['direction','target_date','reference_close','confidence','support','opposition','resolution','invalidation','actions','coverage_review']
    if any(k not in c for k in required):raise ValueError('Incomplete conclusion: '+','.join(k for k in required if k not in c))
    last=frames['equity_daily'][-1]
    if c['direction'] not in ['BULLISH','BEARISH']:raise ValueError('Choose BULLISH or BEARISH; no fabricated direction on insufficient data')
    if c['target_date']!=a['target_date'] or c['target_date']!=next_session(a['market'],last['session_date']):raise ValueError('Conclusion must target the next trading session after reference close')
    if a.get('audits',{}).get('equity',{}).get('stale_sessions',0):raise ValueError('Stale equity data cannot produce a formal next-session report')
    if not math.isclose(float(c['reference_close']),float(last['close']),abs_tol=1e-8):raise ValueError('Reference close mismatch')
    if not c['support'] or not c['opposition'] or not c['resolution'] or not c['invalidation']:raise ValueError('Explain supporting evidence, opposition, resolution and invalidation')
    expected={'Q'+str(i).zfill(2) for i in range(1,42)}
    reviews=c['coverage_review']
    if set(reviews)!=expected:raise ValueError('Review every Q01-Q41 rule without omission')
    for v in reviews.values():
        if v.get('status') not in ['APPLIES','NO_SIGNAL','INSUFFICIENT','NOT_APPLICABLE'] or not v.get('reason'):raise ValueError('Each rule review requires status and reason')
    if not c['actions']:raise ValueError('Explicit buy/sell/wait plan required')
    for x in c['actions']:
        if x.get('action') not in ['BUY','SELL','HOLD','WAIT']:raise ValueError('Invalid action')
        if not x.get('condition') or not x.get('price_source'):raise ValueError('Action requires condition and price provenance')
        timing=x.get('confirmation_timing')
        if timing not in ['INTRADAY','CLOSE','NONE']:raise ValueError('Declare confirmation timing')
        if timing=='CLOSE' and x.get('execution')!='NEXT_SESSION':raise ValueError('Close confirmation cannot execute at an earlier intraday price')
        if x['action'] in ['BUY','SELL']:
            band=x.get('price_range',[])
            if len(band)!=2 or not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in band) or band[0]>band[1]:raise ValueError('Valid positive price range required')
            if x.get('price_basis') not in ['RESEARCH_ADJUSTED','VERIFIED_RAW']:raise ValueError('Declare adjusted or verified raw pricing')
    validate_book_stage(n,c)
    return c

def forecast_outcome(reference_close,next_close,direction):
    """Separate close-to-close forecast outcome from executable trade returns."""
    if reference_close<=0 or next_close<=0:raise ValueError('Positive closes required')
    outcome='FLAT' if next_close==reference_close else 'BULLISH' if next_close>reference_close else 'BEARISH'
    return dict(realized_direction=outcome,correct=direction==outcome,return_close_to_close=next_close/reference_close-1)
