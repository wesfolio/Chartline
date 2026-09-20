from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
from .indicators import features,next_close_intersection

def num(v):return None if v is None or not np.isfinite(v) else float(v)
def fmt(v):return '缺失' if num(v) is None else f'{v:.4f}'
def read_input(root,entry,tf):
    p=root/'inputs'/entry['files'][tf]['path']
    if hashlib.sha256(p.read_bytes()).hexdigest()!=entry['files'][tf]['sha256']:raise ValueError('Input hash mismatch')
    return pd.DataFrame(json.loads(p.read_text(encoding='utf8')))

def model_rows(d,events,tf):
    if d.empty:return []
    r=d.iloc[-1];date=r.session_date;segment=int(r.engine_segment)
    events=[e for e in events if e['segment']==segment and pd.Timestamp(e['known_date'])<=pd.Timestamp(date)]
    # Age must be measured in bars in the current segment, not calendar days.
    pos=len(d.loc[d.engine_segment==segment])-1
    recent=[e for e in events if pos-e['pivot_pos']<=60]
    hs=[e for e in recent if e['kind']=='HIGH'][-2:];ls=[e for e in recent if e['kind']=='LOW'][-2:]
    def row(id,name,direction,obs,why,counter,confirm,invalidate,values,app=True):
        return dict(id=id+'-'+tf,rule_id=id,name=name,timeframe=tf,forecast_horizon='1至10个交易日' if tf=='daily' else '3至12个月背景观察',direction=direction,applicable=bool(app),observations=obs,reasoning=why,counter_evidence=counter,confirmation=confirm,invalidation=invalidate,values=values,bar_end=date,as_of=str(r.available_at),chart_id=id+'-'+tf,empirically_validated=False)
    structure_direction={'UP':'BULLISH','DOWN':'BEARISH','MIXED':'MIXED','UNKNOWN':'INSUFFICIENT'}[r.structure]
    anchors='；'.join(f"{e['kind']} {e['pivot_date']}={e['price']:.4f}，{e['known_date']}确认" for e in hs+ls) or '没有足够的已确认高低点'
    result=[row('Q09','已确认高低点结构',structure_direction,anchors,
        f'最近两组高低点按0.1倍前一期ATR容差判断，状态为{r.structure}。UP须高点和低点都抬高，DOWN须两者都降低。',
        '枢轴有两根bar确认延迟；最新尚未确认的波动可能改变后续结构。MIXED不等于已证实震荡区间。',
        '后续已确认高低点继续推进，且主支撑不破。','出现相反方向的新确认结构；结构证据超过60根bar时降级。',dict(state=r.structure,highs=hs,lows=ls),r.structure!='UNKNOWN')]
    bbi_ready=np.isfinite(r.bbi) and np.isfinite(r.atr)
    direction=('BULLISH' if r.close>r.bbi and r.bbi_slope>0 else 'BEARISH' if r.close<r.bbi and r.bbi_slope<0 else 'MIXED') if bbi_ready else 'INSUFFICIENT'
    result.append(row('Q36','BBI位置与斜率',direction,f'收盘{r.close:.4f}；BBI {fmt(r.bbi)}；本期变化{fmt(r.bbi_slope)}；距BBI {fmt((r.close/r.bbi-1)*100)}%。',
        '价格在上且线抬升，支持该周期均线趋势；价格在下且线下行，支持偏弱状态。其他组合保留分歧。同周期先连续在线上再触线，只作加分证据，不能形成独立买入或确认买入信号。',
        'BBI为滞后均线，触线不单独触发买入；结构、动量和基本面可以反对这项证据。',
        '触线加分须满足本周期此前连续运行门槛；接近观察带不等于实际触线，收回也不等于确认买入。','跌破相关结构支撑或均线方向持续转弱，重新评估。',dict(bbi=num(r.bbi),slope=num(r.bbi_slope),close=num(r.close),atr=num(r.atr),lo=num(r.bbi_band_lo),hi=num(r.bbi_band_hi)),bbi_ready))
    macd_ready=np.isfinite(r.dea)
    direction=('BULLISH' if r.dif>0 and r["hist"]>0 else 'BEARISH' if r.dif<0 and r["hist"]<0 else 'MIXED') if macd_ready else 'INSUFFICIENT'
    result.append(row('Q06','MACD动量',direction,f'DIF={fmt(r.dif)}；DEA={fmt(r.dea)}；柱体={fmt(r["hist"])}；当根交叉={r.macd_cross}。',
        '零轴表示快慢均线相对位置，柱体表示DIF相对DEA。零轴与柱体同向才标为本模型方向一致，异向表示长期均线差与近期动量存在分歧。',
        '负柱缩短并不等于金叉；金叉也不保证价格趋势反转。它与BBI同源于价格，不能作为独立胜率投票。',
        '记录真实交叉时间，并由价格结构或关键价位进一步确认。','柱体或零轴方向反向，或价格破坏原支撑／突破条件。',dict(dif=num(r.dif),dea=num(r.dea),hist=num(r["hist"]),cross=r.macd_cross),macd_ready))
    div=r.rsi_divergence
    rdir='MIXED' if div=='BOTH' else div if div in ['BULLISH','BEARISH'] else 'NEUTRAL' if np.isfinite(r.rsi) else 'INSUFFICIENT'
    zone='超买状态' if r.rsi>=70 else '超卖状态' if r.rsi<=30 else '非极值区' if np.isfinite(r.rsi) else '预热不足'
    result.append(row('Q30','RSI状态与确认枢轴背离',rdir,f'RSI(14)={fmt(r.rsi)}，{zone}；最近有效价格枢轴对的背离状态={div}。',
        '背离比较同一价格枢轴日期的RSI；价格推进超过0.1倍前ATR且RSI反向至少3点才成立。极值单独作为状态，背离作为风险／改善候选。',
        '强趋势可维持极值。背离并未证明反转，且旧枢轴背离可能在趋势延续中被覆盖。',
        '等待价格结构破坏或反向突破确认，不把RSI极值直接作为买卖指令。','新的价格与RSI同向推进使背离条件消失，或锚点过期。',dict(rsi=num(r.rsi),zone=zone,divergence=div,highs=hs,lows=ls),np.isfinite(r.rsi)))
    rv=num(r.rvol);vdir=('BULLISH' if r.price_change>0 else 'BEARISH' if r.price_change<0 else 'NEUTRAL') if rv is not None and rv>=1.5 else 'NEUTRAL' if rv is not None else 'INSUFFICIENT'
    result.append(row('Q07','量价与相对成交量',vdir,f'RVOL={fmt(r.rvol)}；价格变动={fmt(r.price_change)}；成交量={fmt(r.volume)}。',
        'RVOL使用本根之前20根有效成交量均值；达到1.5才记为研究版放量。本根涨跌决定放量证据方向，缩量仅降低量能确认程度。',
        '回调缩量不保证止跌；除权、停牌、成交单位和来源处理均可能干扰量价。未独立核验公司行为。',
        '将量能放在具体突破／回调和价格位置中判断；OBV已计算，作为同源量价辅助，不独立投票。','新量价反向或数据质量不通过，不能延用旧放量证据。',dict(rvol=rv,volume=num(r.volume),baseline=num(r.volume_baseline),price_change=num(r.price_change)),rv is not None))
    direction=r.engulfing if r.engulfing!='NONE' else 'NEUTRAL'
    result.append(row('Q17','实体吞没候选',direction,f'最新完成K线吞没候选={r.engulfing}；实体={fmt(r.body)}；上影={fmt(r.upper)}；下影={fmt(r.lower)}。',
        '检查两根阴阳、实体包含且至少一端扩大，并要求第一根之前已有反向确认趋势。实体几何与影线覆盖分开判断。',
        '本页显示吞没候选，其他蜡烛组合及完整生命周期见形态事件文件；未配置交易所报价档位，边界按数值容差处理。未形成形态不代表缺乏其他交易机会。',
        '候选出现后还需未来价格突破形态边界或其他规则确认；完整Q13生命周期见同轮patterns.json。','反向突破组合极值或前置趋势不满足时，候选失效／不适用。',dict(pattern=r.engulfing,body=num(r.body),upper=num(r.upper),lower=num(r.lower)),r.engulfing!='NONE'))
    return result

def price_card(d,weekly_state,entry,tf):
    if d.empty or not np.isfinite(d.iloc[-1].bbi):return dict(timeframe=tf,state='BLOCKED',reason='预热不足',tradeable_price_band=None,sufficient_to_buy=False)
    r=d.iloc[-1];fund=entry['fundamental_status']
    if fund not in ['VERIFIED_SUPPORT','USER_ASSUMED','UNKNOWN','CONTRADICTED']:raise ValueError('Unknown fundamental status')
    support=bool(r.bbi_support_present)
    technical='SUPPORTING_EVIDENCE' if support else 'TREND_NOT_ESTABLISHED' if not r.bbi_prior_uptrend else 'SUPPORT_WITHDRAWN' if r.bbi_exact_touch and not r.bbi_close_holds_reference else 'NO_TOUCH_SUPPORT'
    blockers=[]
    if fund=='UNKNOWN':blockers.append('基本面未核验；技术证据仅条件展示')
    if fund=='CONTRADICTED':blockers.append('基本面存在反证，不可据此支持买入')
    if fund=='VERIFIED_SUPPORT' and not entry.get('fundamental_evidence'):blockers.append('声称已核验但未提供基本面证据')
    if not entry.get('corporate_action_verified'):blockers.append('公司行为与复权连续性未独立核验')
    if not entry.get('tick_grid_verified'):blockers.append('报价档位未核验')
    if entry['price_basis']!='raw' and not entry.get('tradeable_mapping_verified'):blockers.append('复权到可交易价格映射未核验')
    if entry['mode']=='FROZEN_DEMONSTRATION':blockers.append('冻结历史演示，不是当前行情')
    return dict(timeframe=tf,state='BLOCKED' if blockers else 'EVIDENCE_ONLY',technical_state=technical,evidence_role='SUPPORT_ONLY',sufficient_to_buy=False,buy_action=None,numeric_score_weight=None,support_present=support,usable_buy_support=bool(support and not blockers),prior_above_bbi_run=int(r.bbi_prior_above_run),required_prior_bars=int(r.bbi_required_run),prior_uptrend=bool(r.bbi_prior_uptrend),exact_touch=bool(r.bbi_exact_touch),close_holds_reference=bool(r.bbi_close_holds_reference),primary_weekly_structure=weekly_state,weekly_structure_role='Separate model evidence; not a substitute for same-timeframe BBI continuity',fundamental_status=fund,bar_end=r.session_date,price_basis=entry['price_basis'],bbi=num(r.bbi),technical_band=[num(r.bbi_band_lo),num(r.bbi_band_hi)],band_formula='BBI +/- 0.2 * ATR(14); near-line observation only, no touch credit',static_prior_plan=[num(r.plan_lo),num(r.plan_hi)],touched_prior_plan=bool(r.touch_prior_plan),distance_percent=num((r.close/r.bbi-1)*100),distance_atr=num((r.close-r.bbi)/r.atr) if r.atr else None,tradeable_price_band=None,blockers=blockers,valid_until='仅描述本bar证据；下一bar重评，不逐日累计加分',confirmation='先连续收盘在对应BBI线上方，再回调触及此前BBI且收盘未跌破参考线，仅增加一项支持证据。收回或收阳也不升级为确认买入。',invalidation='此前连续运行前提不成立，或触线后收盘跌破参考BBI，不给触线支持；其他模型与基本面仍可否定买入。',next_close_intersection_scenario=next_close_intersection(d.loc[d.engine_segment==r.engine_segment,'close']),scenario_note='代数条件值，不是价格预测或买入信号',live_enabled=False)

def analyze(root,entry):
    fs={};ev={};models=[]
    for tf in ['daily','weekly']:
        fs[tf],ev[tf]=features(read_input(root,entry,tf),entry['as_of']);models+=model_rows(fs[tf],ev[tf],tf)
    wk=fs['weekly'].iloc[-1].structure if len(fs['weekly']) else 'UNKNOWN'
    cards=[price_card(fs[tf],wk,entry,tf) for tf in ['daily','weekly']]
    conflicts=[]
    for tf in ['daily','weekly']:
        group=[m for m in models if m['timeframe']==tf and m['applicable']]
        bull=[m['id'] for m in group if m['direction']=='BULLISH'];bear=[m['id'] for m in group if m['direction']=='BEARISH']
        if bull and bear:conflicts.append(dict(type='SAME_TIMEFRAME_DISAGREEMENT',timeframe=tf,bullish=bull,bearish=bear,resolution='价格结构优先描述方向，动量与量能提供确认／反证；等待各模型已列确认条件，不用票数给胜率。',effect='保留回调观察，确认前不把分歧升级为一致买入信号。'))
    daily=fs['daily'].iloc[-1].structure if len(fs['daily']) else 'UNKNOWN'
    if daily!=wk:conflicts.append(dict(type='CROSS_TIMEFRAME_DIFFERENCE',daily=daily,weekly=wk,resolution='不同期限状态可以并存，不自动称为逻辑矛盾。'))
    return dict(engine_version='0.2.0',entry=entry,decision='EVIDENCE_INSUFFICIENT_FOR_PURCHASE',decision_reason='冻结样本且基本面、执行价格、公司行为等前提未完成核验；仅报告技术状态。',short_term_structure=daily,long_term_structure=wk,models=models,price_cards=cards,conflicts=conflicts,unimplemented=['Q13完整突破/确认生命周期','Q14-Q16及Q18-Q29其他蜡烛和图形识别','OBV','组合策略与样本外回测','交易执行/费用/报价映射','完整skill安装'],events=ev,live_enabled=False,empirically_validated=False),fs

def run(root):
    root=Path(root);entries=json.loads((root/'inputs/manifest.json').read_text(encoding='utf8'))['entries'];summaries=[]
    for entry in entries:
        r,frames=analyze(root,entry);out=root/'results'/entry['id'];out.mkdir(parents=True,exist_ok=True)
        (out/'analysis.json').write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
        for tf,df in frames.items():df.to_json(out/f'{tf}.features.json',orient='records',date_format='iso',force_ascii=False,double_precision=15)
        summaries.append(dict(id=entry['id'],name=entry['name'],daily=r['short_term_structure'],weekly=r['long_term_structure'],decision=r['decision'],model_count=len(r['models']),conflicts=len(r['conflicts'])))
    (root/'results/summary.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(summaries,ensure_ascii=False))

if __name__=='__main__':run(Path(__file__).resolve().parents[1])


