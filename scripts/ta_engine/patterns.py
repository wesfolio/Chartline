"""Causal, parameterised recognition for the formations catalogued in the notes.

Every event records when it became knowable.  Heuristic geometry is labelled as
such; recognition is evidence, never an order or a calibrated probability.
"""
from __future__ import annotations
import hashlib, json, math
from pathlib import Path
import numpy as np
import pandas as pd

_SPEC=json.loads((Path(__file__).resolve().parents[2]/'references/rules.v0.4.json').read_text(encoding='utf8'))
P={k:v['research_default'] for k,v in _SPEC['parameters'].items()}
SOURCE={r['id']:r.get('source',[]) for r in _SPEC['rules']}

def f(v): return None if v is None or not np.isfinite(v) else float(v)
def eid(rule,pattern,*parts):
    raw='|'.join(map(str,(rule,pattern)+parts))
    return rule+'-'+hashlib.sha1(raw.encode()).hexdigest()[:12]
def event(rule,pattern,direction,state,known_pos,d,**values):
    known_pos=int(known_pos);r=d.iloc[known_pos]
    return dict(id=eid(rule,pattern,r.session_date,values.get('anchor_dates','')),rule_id=rule,
        pattern=pattern,direction=direction,state=state,known_pos=known_pos,known_date=r.session_date,
        known_at=str(r.available_at),source_pages=SOURCE.get(rule,[]),definition_kind='HEURISTIC' if rule in {'Q24','Q25','Q26','Q27','Q28','Q29'} else 'DETERMINISTIC_FROM_DECLARED_THRESHOLDS',
        values={k:v for k,v in values.items()})

def geometry(d):
    x=d.copy();o=x.open.astype(float);c=x.close.astype(float);h=x.high.astype(float);l=x.low.astype(float)
    x['body']=(c-o).abs();x['upper_shadow']=h-np.maximum(o,c);x['lower_shadow']=np.minimum(o,c)-l;x['candle_range']=h-l
    x['body_low']=np.minimum(o,c);x['body_high']=np.maximum(o,c)
    x['epsilon']=1e-10*np.maximum(x[['open','high','low','close']].abs().max(axis=1),1)
    x['candle_color']=np.where(c-o>x.epsilon,'BULL',np.where(o-c>x.epsilon,'BEAR','NEUTRAL'))
    nz=x.candle_range>x.epsilon
    x['near_four_price']=~nz;x['doji']=nz&(x.body/x.candle_range<=P['doji_ratio'])
    x['small_body']=nz&~x.doji&(x.body/x.candle_range<=P['small_body_ratio'])
    x['large_body']=np.isfinite(x.scale)&(x.body>=P['large_body_atr']*x.scale)
    x['spinning_top']=x.small_body&(x.upper_shadow/x.candle_range>=P['long_shadow_ratio'])&(x.lower_shadow/x.candle_range>=P['long_shadow_ratio'])
    x['dragonfly_doji']=x.doji&(x.upper_shadow/x.candle_range<=P['short_shadow_ratio'])&(x.lower_shadow/x.candle_range>=P['long_shadow_ratio'])
    x['gravestone_doji']=x.doji&(x.lower_shadow/x.candle_range<=P['short_shadow_ratio'])&(x.upper_shadow/x.candle_range>=P['long_shadow_ratio'])
    x['umbrella_shape']=x.small_body&(x.lower_shadow>=P['hammer_lower_multiple']*x.body)&(x.upper_shadow/x.candle_range<=P['short_shadow_ratio'])
    x['long_upper_shape']=x.small_body&(x.upper_shadow>=P['shooting_upper_multiple']*x.body)&(x.lower_shadow/x.candle_range<=P['short_shadow_ratio'])
    labels=[]
    for _,r in x.iterrows():
        q=[]
        if r.near_four_price:q.append('NEAR_FOUR_PRICE')
        elif r.doji:q+=['DOJI']+(['DRAGONFLY_DOJI'] if r.dragonfly_doji else [])+(['GRAVESTONE_DOJI'] if r.gravestone_doji else [])
        else:
            if r.small_body:q.append('SMALL_BODY')
            if r.spinning_top:q.append('SPINNING_TOP')
            if r.large_body:q.append('LARGE_BODY')
            if r.umbrella_shape:q.append('UMBRELLA_SHAPE')
            if r.long_upper_shape:q.append('LONG_UPPER_SHAPE')
        labels.append(q)
    x['candle_labels']=labels
    # B1: six directional appearances per colour plus four cross appearances.
    # Shadow/body tolerances are declared engineering definitions, not source laws.
    x['appearance16']=None
    for idx,r in x.iterrows():
        eps=float(r.epsilon); upper=r.upper_shadow>eps; lower=r.lower_shadow>eps
        if r.near_four_price: name='FOUR_PRICE'
        elif r.doji: name='T_DOJI' if not upper else 'INVERTED_T_DOJI' if not lower else 'CROSS_DOJI'
        else:
            color='BULL' if r.candle_color=='BULL' else 'BEAR'
            shape='LOWER_SHADOW_ONLY' if not upper and lower else 'UPPER_SHADOW_ONLY' if upper and not lower else 'LONG_LOWER' if r.lower_shadow>=2*r.body else 'LONG_UPPER' if r.upper_shadow>=2*r.body else 'SMALL_BODY' if r.small_body else 'LARGE_BODY' if r.large_body else 'OTHER_BODY'
            name=color+'_'+shape
        x.loc[idx,'appearance16']=name
    return x

def lifecycle(e,d,created,direction,hi,lo,scale,window=None):
    """Q13 candidate lifecycle. Invalidation wins when a bar hits both sides."""
    window=P['confirm_window'] if window is None else window;e['values'].update(signal_high=f(hi),signal_low=f(lo),frozen_scale=f(scale),confirm_window=int(window))
    if not np.isfinite(scale):e['state']='DATA_INSUFFICIENT';return e
    last=min(len(d)-1,created+window);buf=P['break_buffer_atr']*scale
    for j in range(created+1,last+1):
        r=d.iloc[j];invalid=r.close<lo-buf if direction=='BULLISH' else r.close>hi+buf
        confirmed=r.close>hi+buf if direction=='BULLISH' else r.close<lo-buf
        if invalid:e.update(state='INVALIDATED',terminal_date=r.session_date);return e
        if confirmed:e.update(state='CONFIRMED',terminal_date=r.session_date,confirmation_pos=j,confirmation_price=float(r.close));return e
    if len(d)-1>=created+window:e['state']='EXPIRED';e['terminal_date']=d.iloc[created+window].session_date
    else:e['state']='CREATED'
    return e

def _post_breakout(e,d,direction,boundary,scale):
    """Track Q13 retest/failure after a confirmed close without erasing it."""
    pos=e.get('confirmation_pos');e['values']['breakout_lifecycle']='BREAKOUT'
    if pos is None:return e
    band=P['zone_width_atr']*scale;buf=P['break_buffer_atr']*scale
    for j in range(pos+1,min(len(d),pos+1+P['confirm_window'])):
        r=d.iloc[j];b=float(boundary(j))
        failed=r.close<b-buf if direction=='BULLISH' else r.close>b+buf
        touched=(r.low<=b+band and r.close>=b) if direction=='BULLISH' else (r.high>=b-band and r.close<=b)
        if failed:e['state']='FAILED_BREAKOUT';e['values']['breakout_lifecycle']='FAILED_BREAKOUT';e['values']['post_breakout_date']=r.session_date;return e
        if touched:e['state']='RETEST_CONFIRMED';e['values']['breakout_lifecycle']='RETEST_CONFIRMED';e['values']['post_breakout_date']=r.session_date;return e
    return e

def _trend(d,pos):
    if pos<1:return 'UNKNOWN'
    return str(d.iloc[pos-1].structure)
def _candle(evs,rule,name,direction,i,d,lo,hi,scale,**vals):
    e=event(rule,name,direction,'CREATED',i,d,anchor_dates=vals.pop('anchor_dates',d.iloc[i].session_date),**vals)
    evs.append(lifecycle(e,d,i,direction,hi,lo,scale))

def candle_events(d):
    ev=[]
    for i,r in d.iterrows():
        if r.near_four_price:ev.append(event('Q14','NEAR_FOUR_PRICE','NEUTRAL','OBSERVED',i,d,ratio=None))
        elif r.doji:ev.append(event('Q14','DRAGONFLY_DOJI' if r.dragonfly_doji else 'GRAVESTONE_DOJI' if r.gravestone_doji else 'DOJI','NEUTRAL','OBSERVED',i,d,body_ratio=f(r.body/r.candle_range)))
        elif r.spinning_top:ev.append(event('Q14','SPINNING_TOP','NEUTRAL','OBSERVED',i,d,body_ratio=f(r.body/r.candle_range)))
        tr=_trend(d,i);scale=r.scale
        if r.umbrella_shape:
            name,di=('HAMMER','BULLISH') if tr=='DOWN' else ('HANGING_MAN','BEARISH') if tr=='UP' else ('UMBRELLA_SHAPE','NEUTRAL')
            if di=='NEUTRAL':ev.append(event('Q15',name,di,'OBSERVED',i,d,trend=tr))
            else:_candle(ev,'Q15',name,di,i,d,r.low,r.high,scale,trend=tr)
        if r.long_upper_shape:
            name,di=('SHOOTING_STAR','BEARISH') if tr=='UP' else ('INVERTED_HAMMER','BULLISH') if tr=='DOWN' else ('LONG_UPPER_SHAPE','NEUTRAL')
            if di=='NEUTRAL':ev.append(event('Q16',name,di,'OBSERVED',i,d,trend=tr))
            else:_candle(ev,'Q16',name,di,i,d,r.low,r.high,scale,trend=tr)
        if i<1:continue
        a=d.iloc[i-1];eps=max(a.epsilon,r.epsilon);lo=min(a.low,r.low);hi=max(a.high,r.high);tr0=_trend(d,i-1);anchors=[a.session_date,r.session_date]
        contains=r.body_low<=a.body_low+eps and r.body_high>=a.body_high-eps and (r.body_low<a.body_low-eps or r.body_high>a.body_high+eps)
        if a.candle_color=='BEAR' and r.candle_color=='BULL' and contains and tr0=='DOWN':_candle(ev,'Q17','BULLISH_ENGULFING','BULLISH',i,d,lo,hi,a.scale,anchor_dates=anchors,expansion=f(r.body/a.body) if a.body else None)
        if a.candle_color=='BULL' and r.candle_color=='BEAR' and contains and tr0=='UP':_candle(ev,'Q17','BEARISH_ENGULFING','BEARISH',i,d,lo,hi,a.scale,anchor_dates=anchors,expansion=f(r.body/a.body) if a.body else None)
        if tr0=='UP' and a.candle_color=='BULL' and a.large_body and r.candle_color=='BEAR' and r.open>a.high+eps:
            if a.open+eps<r.close<(a.open+a.close)/2-eps:_candle(ev,'Q18','DARK_CLOUD_COVER','BEARISH',i,d,lo,hi,a.scale,anchor_dates=anchors,version='STRICT')
            elif abs(r.close-(a.open+a.close)/2)<=eps:ev.append(event('Q18','DARK_CLOUD_MIDPOINT_TOUCH','NEUTRAL','OBSERVED',i,d,anchor_dates=anchors))
        if tr0=='DOWN' and a.candle_color=='BEAR' and a.large_body and r.candle_color=='BULL' and r.open<a.close-eps:
            if (a.open+a.close)/2+eps<r.close<a.open-eps:_candle(ev,'Q18','PIERCING_LINE','BULLISH',i,d,lo,hi,a.scale,anchor_dates=anchors,version='STRICT_GAP_LOW' if r.open<a.low-eps else 'BODY_GAP')
            elif abs(r.close-(a.open+a.close)/2)<=eps:ev.append(event('Q18','PIERCING_MIDPOINT_TOUCH','NEUTRAL','OBSERVED',i,d,anchor_dates=anchors))
        if a.candle_color=='BEAR' and r.candle_color=='BULL' and a.body>eps:
            rec=(r.close-a.close)/(a.open-a.close)
            if rec<=.5:
                subtype='NO_RECOVERY' if rec<=0 else 'ON_NECK_HEURISTIC' if rec<=.15 else 'IN_NECK_HEURISTIC' if rec<=.35 else 'THRUSTING_HEURISTIC'
                ev.append(event('Q19',subtype,'NEUTRAL','OBSERVED',i,d,anchor_dates=anchors,recovery=f(rec),subtype_origin='ENGINEERING_BANDS_BECAUSE_SOURCE_THUMBNAIL_LACKS_EXACT_THRESHOLDS'))
        if a.large_body and r.body<=P['star_body_fraction']*a.body:
            gap='DOWN' if r.body_high<a.body_low-eps else 'UP' if r.body_low>a.body_high+eps else None
            if gap:ev.append(event('Q20',('DOJI_' if r.doji else '')+'STAR_'+gap,'NEUTRAL','CREATED',i,d,anchor_dates=anchors,gap=gap))
        # Harami uses bodies; shadows may protrude.
        inside=r.body_low>=a.body_low-eps and r.body_high<=a.body_high+eps and r.body<=P['harami_fraction']*a.body
        if a.large_body and inside and tr0 in ['UP','DOWN']:
            di='BEARISH' if tr0=='UP' else 'BULLISH';_candle(ev,'Q22','HARAMI_CROSS' if r.doji else 'HARAMI',di,i,d,lo,hi,a.scale,anchor_dates=anchors,trend=tr0)
        # Full-range windows, then maintain entry/fill/close-failure state.
        if r.low>a.high+eps or r.high<a.low-eps:
            up=r.low>a.high+eps;lower=float(a.high if up else r.high);upper=float(r.low if up else a.low)
            state='OPEN';entered=filled=failed=None
            for j in range(i+1,min(len(d),i+1+P['zone_expiry'])):
                z=d.iloc[j]
                if entered is None and ((up and z.low<=upper) or (not up and z.high>=lower)):entered=z.session_date
                if filled is None and ((up and z.low<=lower) or (not up and z.high>=upper)):filled=z.session_date
                if (up and z.close<lower-eps) or ((not up) and z.close>upper+eps):failed=z.session_date;state='CLOSE_FAILED';break
            if state=='OPEN' and filled:state='FILLED'
            elif state=='OPEN' and entered:state='ENTERED'
            ev.append(event('Q23','RISING_WINDOW' if up else 'FALLING_WINDOW','BULLISH' if up else 'BEARISH',state,i,d,anchor_dates=anchors,lower=lower,upper=upper,entered_at=entered,filled_at=filled,failed_at=failed))
        if i<2:continue
        b=d.iloc[i-1];aa=d.iloc[i-2];tr2=_trend(d,i-2);eps3=max(aa.epsilon,b.epsilon,r.epsilon);lo3=min(aa.low,b.low,r.low);hi3=max(aa.high,b.high,r.high);anchors3=[aa.session_date,b.session_date,r.session_date]
        if aa.large_body and b.body<=P['star_body_fraction']*aa.body:
            morning=tr2=='DOWN' and aa.candle_color=='BEAR' and b.body_high<aa.body_low-eps3 and r.candle_color=='BULL' and (r.close-aa.close)/aa.body>=P['star_penetration']
            evening=tr2=='UP' and aa.candle_color=='BULL' and b.body_low>aa.body_high+eps3 and r.candle_color=='BEAR' and (aa.close-r.close)/aa.body>=P['star_penetration']
            if morning or evening:
                di='BULLISH' if morning else 'BEARISH';name=('MORNING' if morning else 'EVENING')+('_DOJI_STAR' if b.doji else '_STAR')
                _candle(ev,'Q20',name,di,i,d,lo3,hi3,aa.scale,anchor_dates=anchors3,penetration=f((r.close-aa.close)/aa.body if morning else (aa.close-r.close)/aa.body))
                isolated=b.high<min(aa.low,r.low)-eps3 if morning else b.low>max(aa.high,r.high)+eps3
                if b.doji and isolated:_candle(ev,'Q21','ABANDONED_BABY_BOTTOM' if morning else 'ABANDONED_BABY_TOP',di,i,d,lo3,hi3,aa.scale,anchor_dates=anchors3)
    for i,r in d.iterrows():
        divergence=getattr(r,'rsi_divergence','NONE')
        if divergence in ['BULLISH','BEARISH','BOTH']:
            ev.append(event('Q30','PRICE_PIVOT_ALIGNED_RSI_DIVERGENCE',divergence,'OBSERVED',i,d,divergence=divergence,rsi=f(getattr(r,'rsi',None))))
    return ev

def _pivots(d,events):
    pos={v:i for i,v in enumerate(d.session_date)};out=[]
    for e in events:
        if e['pivot_date'] in pos and e['known_date'] in pos:
            q=dict(e);q['pivot_pos']=pos[e['pivot_date']];q['known_pos']=pos[e['known_date']];out.append(q)
    return sorted(out,key=lambda x:(x['known_pos'],x['pivot_pos']))
def _line(a,b,x):return a['price']+(b['price']-a['price'])*(x-a['pivot_pos'])/(b['pivot_pos']-a['pivot_pos'])

def zones_and_lines(d,piv):
    ev=[]
    for p in piv:
        s=d.iloc[max(0,p['pivot_pos']-1)].atr
        if not np.isfinite(s):continue
        half=P['zone_width_atr']*s;low=p['price']-half;high=p['price']+half;direction='SUPPORT' if p['kind']=='LOW' else 'RESISTANCE';state='ACTIVE';touch=[];invalid=None
        for j in range(p['known_pos']+1,min(len(d),p['known_pos']+P['zone_expiry']+1)):
            r=d.iloc[j]
            if r.low<=high and r.high>=low:touch.append(r.session_date)
            if (direction=='SUPPORT' and r.close<low-P['break_buffer_atr']*s) or (direction=='RESISTANCE' and r.close>high+P['break_buffer_atr']*s):state='INVALIDATED';invalid=r.session_date;break
        if state=='ACTIVE' and len(d)-1>=p['known_pos']+P['zone_expiry']:state='EXPIRED'
        ev.append(event('Q11',direction,direction,state,p['known_pos'],d,anchor_dates=[p['pivot_date']],center=f(p['price']),lower=f(low),upper=f(high),touches=touch,invalidated_at=invalid,frozen_scale=f(s)))
    for kind,di in [('LOW','BULLISH'),('HIGH','BEARISH')]:
        ps=[p for p in piv if p['kind']==kind]
        for a,b in zip(ps,ps[1:]):
            if b['pivot_pos']==a['pivot_pos']:continue
            rising=b['price']>a['price'] if kind=='LOW' else b['price']<a['price']
            if not rising:continue
            s=d.iloc[max(0,b['pivot_pos']-1)].atr
            if not np.isfinite(s):continue
            accepted=True
            for j in range(a['known_pos'],b['known_pos']+1):
                bad=d.iloc[j].close<_line(a,b,j)-P['line_breach_atr']*s if kind=='LOW' else d.iloc[j].close>_line(a,b,j)+P['line_breach_atr']*s
                if bad:accepted=False;break
            if not accepted:continue
            state='ACTIVE';cross=None;prev=d.iloc[b['known_pos']].close-_line(a,b,b['known_pos'])
            for j in range(b['known_pos']+1,len(d)):
                delta=d.iloc[j].close-_line(a,b,j)
                if (kind=='LOW' and prev>=0 and delta<-P['line_breach_atr']*s) or (kind=='HIGH' and prev<=0 and delta>P['line_breach_atr']*s):state='CROSSED';cross=d.iloc[j].session_date;break
                prev=delta
            ev.append(event('Q12','UP_TRENDLINE' if kind=='LOW' else 'DOWN_TRENDLINE',di,state,b['known_pos'],d,anchor_dates=[a['pivot_date'],b['pivot_date']],slope=f((b['price']-a['price'])/(b['pivot_pos']-a['pivot_pos'])),crossed_at=cross,frozen_scale=f(s)))
    return ev

def _dynamic_break(e,d,start,direction,boundary,scale,window=None):
    window=P['confirm_window'] if window is None else window;buf=P['break_buffer_atr']*scale
    for j in range(start+1,min(len(d),start+window+1)):
        bound=boundary(j);r=d.iloc[j]
        probe=(direction=='BULLISH' and r.high>bound+buf and r.close<=bound+buf) or (direction=='BEARISH' and r.low<bound-buf and r.close>=bound-buf)
        if probe:e['values'].setdefault('intrabar_probes',[]).append(r.session_date)
        if (direction=='BULLISH' and r.close>bound+buf) or (direction=='BEARISH' and r.close<bound-buf):
            e.update(state='CONFIRMED',terminal_date=r.session_date,confirmation_pos=j,confirmation_price=float(r.close),values={**e['values'],'breakout_boundary':f(bound)})
            return _post_breakout(e,d,direction,boundary,scale)
    e['state']='EXPIRED' if len(d)-1>=start+window else 'CREATED';return e

def reversal_patterns(d,piv):
    ev=[]
    # Double top/bottom and head-and-shoulders use consecutive alternating confirmed pivots.
    for k in range(2,len(piv)):
        a,b,c=piv[k-2:k+1]
        if [a['kind'],b['kind'],c['kind']] not in [['HIGH','LOW','HIGH'],['LOW','HIGH','LOW']]:continue
        top=a['kind']=='HIGH';s=d.iloc[max(0,a['pivot_pos']-1)].atr;span=c['pivot_pos']-a['pivot_pos']
        if not np.isfinite(s) or not P['pattern_span_min']<=span<=P['pattern_span_max']:continue
        near=abs(a['price']-c['price'])<=P['double_tol_atr']*s;depth=(min(a['price'],c['price'])-b['price'] if top else b['price']-max(a['price'],c['price']))>=P['pattern_depth_atr']*s
        if near and depth:
            created=c['known_pos'];di='BEARISH' if top else 'BULLISH';name='DOUBLE_TOP' if top else 'DOUBLE_BOTTOM';neck=b['price']
            e=event('Q25',name,di,'CREATED',created,d,anchor_dates=[a['pivot_date'],b['pivot_date'],c['pivot_date']],neckline=f(neck),height=f((a['price']+c['price'])/2-neck if top else neck-(a['price']+c['price'])/2),frozen_scale=f(s))
            e=_dynamic_break(e,d,created,di,lambda _:neck,s)
            if e['state'] in ['CONFIRMED','RETEST_CONFIRMED','FAILED_BREAKOUT']:e['values']['reference_target']=f(neck-e['values']['height'] if top else neck+e['values']['height']);e['values']['target_rule']='Q31'
            ev.append(e)
    for k in range(4,len(piv)):
        q=piv[k-4:k+1];types=[x['kind'] for x in q]
        if types not in [['HIGH','LOW','HIGH','LOW','HIGH'],['LOW','HIGH','LOW','HIGH','LOW']]:continue
        top=types[0]=='HIGH';a,b,h,c,e3=q;s=d.iloc[max(0,a['pivot_pos']-1)].atr;span=e3['pivot_pos']-a['pivot_pos']
        if not np.isfinite(s) or not P['pattern_span_min']<=span<=P['pattern_span_max']:continue
        shoulders=abs(a['price']-e3['price'])<=P['shoulder_tol_atr']*s;prom=(h['price']-max(a['price'],e3['price']) if top else min(a['price'],e3['price'])-h['price'])>=P['head_prominence_atr']*s
        if not shoulders or not prom:continue
        created=e3['known_pos'];di='BEARISH' if top else 'BULLISH';name='HEAD_AND_SHOULDERS_TOP' if top else 'INVERSE_HEAD_AND_SHOULDERS'
        line=lambda x:_line(b,c,x)
        z=event('Q24',name,di,'CREATED',created,d,anchor_dates=[v['pivot_date'] for v in q],neckline_points=[[b['pivot_date'],f(b['price'])],[c['pivot_date'],f(c['price'])]],frozen_scale=f(s))
        ev.append(_dynamic_break(z,d,created,di,line,s))
    return ev

def consolidation_patterns(d,piv):
    ev=[];seen=set();n=P['rectangle_n']
    for end in range(n-1,len(d)):
        start=end-n+1;s=d.iloc[start].atr
        if not np.isfinite(s):continue
        q=d.iloc[start:end+1];upper=float(q.high.max());lower=float(q.low.min());width=upper-lower
        if not P['rectangle_min_atr']<=width/s<=P['rectangle_max_atr']:continue
        hp=[p for p in piv if p['kind']=='HIGH' and p['known_pos']<=end and start<=p['pivot_pos']<=end and abs(p['price']-upper)<=P['zone_width_atr']*s]
        lp=[p for p in piv if p['kind']=='LOW' and p['known_pos']<=end and start<=p['pivot_pos']<=end and abs(p['price']-lower)<=P['zone_width_atr']*s]
        spaced=lambda ps:len(ps)>=2 and any(b['pivot_pos']-a['pivot_pos']>=P['min_touch_spacing'] for a,b in zip(ps,ps[1:]))
        if not spaced(hp) or not spaced(lp):continue
        if any(x['state']=='CREATED' for x in ev if x['rule_id']=='Q26'):continue
        key=(round(upper/s,1),round(lower/s,1));
        if key in seen:continue
        seen.add(key);e=event('Q26','RECTANGLE','NEUTRAL','CREATED',end,d,anchor_dates=[d.iloc[start].session_date,d.iloc[end].session_date],upper=upper,lower=lower,height=width,frozen_scale=f(s))
        for j in range(end+1,min(len(d),end+1+P['zone_expiry'])):
            if d.iloc[j].close>upper+P['break_buffer_atr']*s:e.update(state='CONFIRMED',direction='BULLISH',terminal_date=d.iloc[j].session_date,confirmation_pos=j,confirmation_price=float(d.iloc[j].close));e['values']['reference_target']=upper+width;e['values']['target_rule']='Q31';e=_post_breakout(e,d,'BULLISH',lambda _:upper,s);break
            if d.iloc[j].close<lower-P['break_buffer_atr']*s:e.update(state='CONFIRMED',direction='BEARISH',terminal_date=d.iloc[j].session_date,confirmation_pos=j,confirmation_price=float(d.iloc[j].close));e['values']['reference_target']=lower-width;e['values']['target_rule']='Q31';e=_post_breakout(e,d,'BEARISH',lambda _:lower,s);break
        if e['state']=='CREATED' and len(d)-1>=end+P['zone_expiry']:e['state']='EXPIRED'
        ev.append(e)
    # Boundaries from two latest highs and lows: wedges, triangles and broadening.
    for end in range(10,len(d)):
        ps=[p for p in piv if p['known_pos']<=end and end-p['pivot_pos']<=P['pattern_span_max']]
        hs=[p for p in ps if p['kind']=='HIGH'][-3:];ls=[p for p in ps if p['kind']=='LOW'][-3:]
        if len(hs)<2 or len(ls)<2:continue
        hu=(hs[-1]['price']-hs[-2]['price'])/(hs[-1]['pivot_pos']-hs[-2]['pivot_pos']);ll=(ls[-1]['price']-ls[-2]['price'])/(ls[-1]['pivot_pos']-ls[-2]['pivot_pos']);s=d.iloc[max(0,min(hs[-2]['pivot_pos'],ls[-2]['pivot_pos'])-1)].atr
        if not np.isfinite(s):continue
        width0=_line(hs[-2],hs[-1],end)-_line(ls[-2],ls[-1],end);width1=_line(hs[-2],hs[-1],end+5)-_line(ls[-2],ls[-1],end+5)
        if width0<=0:continue
        name=rule=None
        flat=.03*s
        if hu>0 and ll>hu and 0<width1<width0:name,rule='RISING_WEDGE','Q28'
        elif ll<0 and hu<ll and 0<width1<width0:name,rule='FALLING_WEDGE','Q28'
        elif hu<0<ll and 0<width1<width0:name,rule='SYMMETRICAL_TRIANGLE','Q29'
        elif abs(hu)<=flat and ll>flat and 0<width1<width0:name,rule='ASCENDING_TRIANGLE','Q29'
        elif abs(ll)<=flat and hu<-flat and 0<width1<width0:name,rule='DESCENDING_TRIANGLE','Q29'
        elif hu>0>ll and width1>width0:name,rule='BROADENING_FORMATION','Q29'
        if not name:continue
        anchors=[hs[-2]['pivot_date'],hs[-1]['pivot_date'],ls[-2]['pivot_date'],ls[-1]['pivot_date']];key=(rule,name,tuple(anchors))
        if key in seen:continue
        seen.add(key);e=event(rule,name,'NEUTRAL','CREATED',end,d,anchor_dates=anchors,upper_slope=f(hu),lower_slope=f(ll),width=f(width0),frozen_scale=f(s))
        for j in range(end+1,min(len(d),end+1+P['confirm_window'])):
            up=_line(hs[-2],hs[-1],j);low=_line(ls[-2],ls[-1],j);r=d.iloc[j]
            if r.close>up+P['break_buffer_atr']*s:e.update(state='CONFIRMED',direction='BULLISH',terminal_date=r.session_date,confirmation_pos=j);break
            if r.close<low-P['break_buffer_atr']*s:e.update(state='CONFIRMED',direction='BEARISH',terminal_date=r.session_date,confirmation_pos=j);break
        if e['state']=='CREATED' and len(d)-1>=end+P['confirm_window']:e['state']='EXPIRED'
        ev.append(e)
    return ev

def flags_and_rounding(d):
    ev=[];seen=set()
    for start in range(5,len(d)-5):
        s=d.iloc[start-1].atr
        if not np.isfinite(s):continue
        pole=d.iloc[start].close-d.iloc[start-5].close
        if abs(pole)<3*s:continue
        di='BULLISH' if pole>0 else 'BEARISH'
        for length in range(5,min(16,len(d)-start)):
            q=d.iloc[start:start+length];x=np.arange(length);uh=np.polyfit(x,q.high,1)[0];ll=np.polyfit(x,q.low,1)[0];retr=(q.low.min()-d.iloc[start].close)/pole if pole>0 else (q.high.max()-d.iloc[start].close)/pole
            conv=(q.high.iloc[0]-q.low.iloc[0])>(q.high.iloc[-1]-q.low.iloc[-1]);parallel=abs(uh-ll)<=.08*s
            counter=(pole>0 and uh<=.08*s and ll<=.08*s) or (pole<0 and uh>=-.08*s and ll>=-.08*s)
            if abs(retr)>.65 or not counter:continue
            name='BULL_FLAG' if pole>0 else 'BEAR_FLAG'
            if conv:name='BULL_PENNANT' if pole>0 else 'BEAR_PENNANT'
            elif not parallel:continue
            end=start+length-1;key=(name,start,end)
            if key in seen:continue
            seen.add(key);e=event('Q27',name,di,'CREATED',end,d,anchor_dates=[d.iloc[start-5].session_date,d.iloc[start].session_date,d.iloc[end].session_date],pole_move_atr=f(pole/s),duration=length,retracement=f(retr),upper_slope=f(uh),lower_slope=f(ll),frozen_scale=f(s))
            high=float(q.high.max());low=float(q.low.min());ev.append(lifecycle(e,d,end,di,high,low,s));break
    # Rounding formations use a declared quadratic heuristic, not a visual assertion.
    for end in range(19,len(d)):
        q=d.iloc[end-19:end+1];y=q.close.to_numpy(float);x=np.linspace(-1,1,20);coef=np.polyfit(x,y,2);pred=np.polyval(coef,x);ss=((y-y.mean())**2).sum();r2=1-((y-pred)**2).sum()/ss if ss else 0;s=q.iloc[0].atr
        if np.isfinite(s) and r2>=.8 and abs(coef[0])>=s:
            name='ROUNDING_BOTTOM' if coef[0]>0 else 'ROUNDING_TOP';di='BULLISH' if coef[0]>0 else 'BEARISH';ev.append(event('Q29',name,di,'OBSERVED',end,d,anchor_dates=[q.iloc[0].session_date,q.iloc[-1].session_date],quadratic=f(coef[0]),r_squared=f(r2),window=20))
    return ev

def triple_and_diamond(d,piv):
    ev=[]
    for k in range(4,len(piv)):
        q=piv[k-4:k+1];types=[x['kind'] for x in q]
        if types not in [['HIGH','LOW','HIGH','LOW','HIGH'],['LOW','HIGH','LOW','HIGH','LOW']]:continue
        top=types[0]=='HIGH';same=q[::2];other=q[1::2];s=d.iloc[max(0,q[0]['pivot_pos']-1)].atr
        if not np.isfinite(s):continue
        if max(x['price'] for x in same)-min(x['price'] for x in same)<=P['double_tol_atr']*s:
            deep=(min(x['price'] for x in same)-max(x['price'] for x in other) if top else min(x['price'] for x in other)-max(x['price'] for x in same))>=P['pattern_depth_atr']*s
            if deep:ev.append(event('Q29','TRIPLE_TOP' if top else 'TRIPLE_BOTTOM','BEARISH' if top else 'BULLISH','CREATED',q[-1]['known_pos'],d,anchor_dates=[x['pivot_date'] for x in q],frozen_scale=f(s)))
    # Diamond: pivot envelope expands then contracts across six alternating pivots.
    for k in range(5,len(piv)):
        q=piv[k-5:k+1]
        if any(q[j]['kind']==q[j-1]['kind'] for j in range(1,6)):continue
        widths=[]
        for j in range(1,5):widths.append(abs(q[j+1]['price']-q[j]['price']))
        if widths[0]<widths[1] and widths[1]>widths[2]>widths[3]:ev.append(event('Q29','DIAMOND_FORMATION','NEUTRAL','CREATED',q[-1]['known_pos'],d,anchor_dates=[x['pivot_date'] for x in q],swing_widths=[f(x) for x in widths]))
    return ev

def scan_patterns(d,pivot_events):
    """Return augmented bars and all causal pattern/zone/lifecycle records."""
    if d.empty:return d,[]
    if 'engine_segment' in d and d.engine_segment.nunique()>1:
        chunks=[];events=[];offset=0
        for segment,g in d.groupby('engine_segment',sort=False):
            part,ev=scan_patterns(g.reset_index(drop=True),[p for p in pivot_events if p.get('segment')==segment])
            for e in ev:
                for key in ['known_pos','confirmation_pos']:
                    if key in e:e[key]+=offset
            chunks.append(part);events.extend(ev);offset+=len(g)
        return pd.concat(chunks,ignore_index=True),events
    x=geometry(d);piv=_pivots(x,pivot_events)
    all_events=candle_events(x)+zones_and_lines(x,piv)+reversal_patterns(x,piv)+consolidation_patterns(x,piv)+flags_and_rounding(x)+triple_and_diamond(x,piv)
    all_events=sorted(all_events,key=lambda e:(e['known_pos'],e['rule_id'],e['id']))
    # Exact duplicate IDs can arise from overlapping scans; retain first causal instance.
    unique={}
    for e in all_events:unique.setdefault(e['id'],e)
    return x,list(unique.values())

def latest_summary(events,limit=40):
    terminal={'CONFIRMED','RETEST_CONFIRMED','FAILED_BREAKOUT','CREATED','ACTIVE','CROSSED','ENTERED','FILLED','CLOSE_FAILED','OBSERVED'}
    return sorted([e for e in events if e['state'] in terminal],key=lambda e:(e['known_pos'],e['rule_id']))[-limit:]

def fuse_setups(daily,weekly,events):
    """Q32 transparent conjunctions; no vote count or score."""
    out=[];weekly_state=str(weekly.iloc[-1].structure) if weekly is not None and len(weekly) else 'UNKNOWN';last=len(daily)-1
    events=[e for e in events if e.get('confirmation_pos',e['known_pos'])>=last-20]
    active_support=[e for e in events if e['rule_id']=='Q11' and e['pattern']=='SUPPORT' and e['state']=='ACTIVE' and e['known_pos']<=last]
    bullish=[e for e in events if e['rule_id'] in ['Q15','Q17'] and e['direction']=='BULLISH' and e['state'] in ['CONFIRMED','RETEST_CONFIRMED']]
    for e in bullish[-10:]:
        touched=[z['id'] for z in active_support if z['values'].get('touches') and any(x<=e['known_date'] for x in z['values']['touches'])]
        if weekly_state=='UP' and touched:out.append(dict(id='F1-'+e['id'],rule_id='Q32',setup='F1_TREND_PULLBACK',state='CONFIRMED',known_date=e.get('terminal_date'),evidence=[e['id']]+touched,weekly_structure=weekly_state,score=None))
    for e in events:
        if e['rule_id']=='Q26' and e['direction']=='BULLISH' and e['state'] in ['CONFIRMED','RETEST_CONFIRMED'] and weekly_state!='DOWN':
            pos=e.get('confirmation_pos');rvol=f(daily.iloc[pos].rvol) if pos is not None else None
            out.append(dict(id='F2-'+e['id'],rule_id='Q32',setup='F2_RANGE_BREAKOUT',state=e['state'],known_date=e.get('terminal_date'),evidence=[e['id']],weekly_structure=weekly_state,rvol=rvol,volume_variant=bool(rvol is not None and rvol>=P['volume_ratio']),score=None))
    for e in events:
        if e['direction']=='BEARISH' and e['rule_id'] in ['Q15','Q16','Q17','Q18','Q20','Q21','Q22','Q30'] and e['known_pos']>=last-20:
            out.append(dict(id='F3-'+e['id'],rule_id='Q32',setup='F3_HIGH_LEVEL_RISK_REVIEW',state='REVIEW',known_date=e['known_date'],evidence=[e['id']],not_a_short_signal=True,score=None))
    return out
