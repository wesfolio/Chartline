import numpy as np
import pandas as pd
import json
from pathlib import Path
BBI_CONFIG=json.loads((Path(__file__).resolve().parents[1]/'inputs/bbi-evidence-config.json').read_text(encoding='utf8'))

def bbi_support(x,min_prior):
    """Binary supporting evidence only. Evaluate each bar using its preceding run."""
    if not isinstance(min_prior,int) or isinstance(min_prior,bool) or min_prior<1:raise ValueError('Positive integer duration required')
    run=0;out=[]
    for _,r in x.iterrows():
        valid=np.isfinite(r.bbi);ref=r.bbi_prior
        eligible=run>=min_prior
        touch=bool(np.isfinite(ref) and r.low<=ref<=r.high)
        held=bool(np.isfinite(ref) and r.close>=ref)
        out.append(dict(bbi_prior_above_run=run,bbi_required_run=min_prior,bbi_prior_uptrend=eligible,bbi_exact_touch=touch,bbi_close_holds_reference=held,bbi_support_present=bool(eligible and touch and held)))
        run=run+1 if valid and r.close>r.bbi else 0
    return pd.DataFrame(out,index=x.index)

def smooth(series,n,alpha):
    """SMA seed after n consecutive finite values; reset on every gap."""
    values=np.asarray(series,dtype=float);out=np.full(len(values),np.nan);seed=[];prev=np.nan
    for i,v in enumerate(values):
        if not np.isfinite(v):seed=[];prev=np.nan;continue
        if np.isnan(prev):
            seed.append(v)
            if len(seed)==n:prev=float(np.mean(seed));out[i]=prev
        else:prev=alpha*v+(1-alpha)*prev;out[i]=prev
    return pd.Series(out,index=series.index)

def features(frame,as_of):
    """Filter observed time first. Compute within unbroken valid price segments only."""
    d=frame.copy();ts=pd.Timestamp(as_of)
    if ts.tzinfo is None:raise ValueError('as_of must be timezone-aware')
    for col in ['available_at','bar_final_after']:
        if d[col].map(lambda v:pd.Timestamp(v).tzinfo is None).any():raise ValueError('Input timestamps must carry timezone')
        d[col]=pd.to_datetime(d[col],utc=True,format='ISO8601')
    d=d.loc[(d.available_at<=ts)&(d.bar_final_after<=ts)&d.is_final].copy()
    if d.empty:return d,[]
    if not d.session_date.is_monotonic_increasing or d.session_date.duplicated().any():raise ValueError('Unsorted or duplicate dates')
    for k in ['market','symbol','price_basis','source_api','timeframe']:
        if d[k].nunique()!=1:raise ValueError('Mixed '+k)
    d=d.reset_index(drop=True)
    # Input daily segment IDs survive, weekly IDs inherit their constituent daily segment.
    valid=d.price_usable.astype(bool)
    d['engine_segment']=(d.segment_id.ne(d.segment_id.shift())|~valid|~valid.shift(fill_value=False)).cumsum()
    chunks=[];events=[]
    for _,g in d.groupby('engine_segment',sort=False):
        if not g.price_usable.all():continue
        x=g.copy();c=x.close.astype(float);h=x.high.astype(float);l=x.low.astype(float);o=x.open.astype(float)
        if not np.isfinite(x[['open','high','low','close']].to_numpy(dtype=float)).all():raise ValueError('Nonfinite usable OHLC')
        if ((l>np.minimum(o,c)+1e-6)|(h<np.maximum(o,c)-1e-6)|(l<=0)).any():raise ValueError('Bad usable OHLC')
        prev=c.shift();tr=pd.concat([h-l,(h-prev).abs(),(l-prev).abs()],axis=1).max(axis=1);tr.iloc[0]=np.nan
        x['tr']=tr;x['atr']=smooth(tr,14,1/14);x['scale']=x.atr.shift()
        x['bbi']=sum(c.rolling(n,min_periods=n).mean() for n in [3,6,12,24])/4
        x['bbi_slope']=x.bbi.diff();x['bbi_prior']=x.bbi.shift();x['bbi_band_lo']=x.bbi-.2*x.atr;x['bbi_band_hi']=x.bbi+.2*x.atr
        x['plan_lo']=x.bbi_prior-.2*x.atr.shift();x['plan_hi']=x.bbi_prior+.2*x.atr.shift()
        x['touch_prior_plan']=(l<=x.plan_hi)&(h>=x.plan_lo)
        x['above_bbi']=c>x.bbi
        support=bbi_support(x,BBI_CONFIG['min_prior_above_bars'][x.timeframe.iloc[0]])
        for col in support:x[col]=support[col]
        for n in [5,10,20,50,200]:
            x['sma'+str(n)]=c.rolling(n,min_periods=n).mean()
            x['ema'+str(n)]=smooth(c,n,2/(n+1))
        x['ema12']=smooth(c,12,2/13);x['ema26']=smooth(c,26,2/27);x['dif']=x.ema12-x.ema26;x['dea']=smooth(x.dif,9,2/10);x['hist']=x.dif-x.dea
        x['macd_cross']=np.where((x.dif.shift()<=x.dea.shift())&(x.dif>x.dea),'GOLDEN',np.where((x.dif.shift()>=x.dea.shift())&(x.dif<x.dea),'DEAD','NONE'))
        delta=c.diff();gain=smooth(delta.clip(lower=0),14,1/14);loss=smooth((-delta).clip(lower=0),14,1/14)
        x['rsi']=100-100/(1+gain/loss.replace(0,np.nan));x.loc[(loss==0)&(gain>0),'rsi']=100;x.loc[(gain==0)&(loss>0),'rsi']=0;x.loc[(gain==0)&(loss==0),'rsi']=50
        v=x.volume.where(x.volume_usable);vb=v.shift().rolling(20,min_periods=20).mean();x['volume_baseline']=vb;x['rvol']=v/vb.replace(0,np.nan)
        x['obv']=(np.sign(c.diff()).fillna(0)*v).cumsum(skipna=False).where(v.notna())
        x['price_change']=c.diff();x['volume_change']=v.diff();x['body']=(c-o).abs();x['upper']=h-np.maximum(c,o);x['lower']=np.minimum(c,o)-l;x['range']=h-l
        x['structure']='UNKNOWN';x['rsi_divergence']='NONE';local_events=[]
        for pos in range(len(x)):
            if pos>=4:
                center=pos-2;block=x.iloc[center-2:center+3];r=x.iloc[center];other=block.drop(index=x.index[center])
                hi=r.high>other.high.max();lo=r.low<other.low.min()
                if hi!=lo:
                    e=dict(kind='HIGH' if hi else 'LOW',pivot_pos=center,known_pos=pos,pivot_date=r.session_date,known_date=x.iloc[pos].session_date,price=float(r.high if hi else r.low),rsi=None if pd.isna(r.rsi) else float(r.rsi),known_at=str(x.iloc[pos].available_at),segment=int(x.engine_segment.iloc[0]))
                    local_events.append(e);events.append(e)
            recent=[e for e in local_events if pos-e['pivot_pos']<=60]
            hs=[e for e in recent if e['kind']=='HIGH'][-2:];ls=[e for e in recent if e['kind']=='LOW'][-2:];scale=x.iloc[pos].scale
            if len(hs)==len(ls)==2 and np.isfinite(scale):
                dh=hs[-1]['price']-hs[-2]['price'];dl=ls[-1]['price']-ls[-2]['price'];tol=.1*scale
                x.loc[x.index[pos],'structure']='UP' if dh>tol and dl>tol else 'DOWN' if dh<-tol and dl<-tol else 'MIXED'
            div=[]
            if np.isfinite(scale):
                for kind,pair in [('BEARISH',hs),('BULLISH',ls)]:
                    if len(pair)==2 and all(e['rsi'] is not None for e in pair):
                        a,b=pair;pdiff=b['price']-a['price'];rdiff=b['rsi']-a['rsi']
                        if (kind=='BEARISH' and pdiff>.1*scale and rdiff<=-3) or (kind=='BULLISH' and pdiff<-.1*scale and rdiff>=3):div.append(kind)
            x.loc[x.index[pos],'rsi_divergence']='BOTH' if len(div)==2 else div[0] if div else 'NONE'
        eps=1e-10*np.maximum(x[['open','high','low','close']].abs().max(axis=1),1)
        a_o=o.shift();a_c=c.shift();lo_a=np.minimum(a_o,a_c);hi_a=np.maximum(a_o,a_c);lo_b=np.minimum(o,c);hi_b=np.maximum(o,c)
        contains=(lo_b<=lo_a+eps)&(hi_b>=hi_a-eps)&((lo_b<lo_a-eps)|(hi_b>hi_a+eps))
        bull=(a_c<a_o-eps)&(c>o+eps)&contains&(x.structure.shift(2)=='DOWN')
        bear=(a_c>a_o+eps)&(c<o-eps)&contains&(x.structure.shift(2)=='UP')
        x['engulfing']=np.where(bull,'BULLISH',np.where(bear,'BEARISH','NONE'))
        # Tick-size-dependent near-equality patterns are deliberately not classified here.
        chunks.append(x)
    return pd.concat(chunks).reset_index(drop=True) if chunks else d.iloc[:0],events

def next_close_intersection(closes):
    c=np.asarray(closes,dtype=float)
    if len(c)<23 or not np.isfinite(c[-23:]).all():return None
    a=np.mean([1/n for n in [3,6,12,24]]);b=np.mean([c[-(n-1):].sum()/n for n in [3,6,12,24]])
    return float(b/(1-a))
