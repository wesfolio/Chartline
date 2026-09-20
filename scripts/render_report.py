"""Render evidence with paired synthetic/observed vector charts, TOC and index."""
import argparse, json, re
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.graphics import renderSVG
from ta_engine.charts import paired,pattern_paired
from ta_engine.decision import validate_decision
from ta_engine.book_stage import book_view

BODY=ParagraphStyle('Body',fontName='Song',fontSize=10,leading=16,spaceAfter=7,wordWrap='CJK')
HEAD=ParagraphStyle('Head',fontName='Hei',fontSize=19,leading=25,spaceAfter=16,keepWithNext=True)
SMALL=ParagraphStyle('Small',parent=BODY,fontSize=8,leading=12)
def mixed(text):return ''.join('<font name="'+('Song' if t.isascii() else 'Song')+'">'+escape(t)+'</font>' for t in re.findall(r'[\x00-\x7f]+|[^\x00-\x7f]+',str(text)))
def para(t,style=BODY):return Paragraph(mixed(t),style)
def heading(t,toc=True,index=False):
    p=Paragraph(escape(t),HEAD);p._toc=toc;p._index=index;return p
class ModelIndex(TableOfContents):
    def notify(self,kind,stuff):
        if kind=='ModelIndexEntry':super().notify('TOCEntry',stuff)
class Report(SimpleDocTemplate):
    def afterFlowable(self,flowable):
        if getattr(flowable,'_toc',False):
            text=flowable.getPlainText();key='section-'+str(self.page);self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text,key,0,False)
            self.notify('TOCEntry',(0,mixed(text),self.page,key))
            if getattr(flowable,'_index',False):self.notify('ModelIndexEntry',(0,mixed(text),self.page,key))
def footer(c,d):
    c.setFont('Song',8);c.drawRightString(554,25,str(d.page))
    c.setFont('Song',8);c.drawString(42,25,'技术证据研究｜合成理论图与实际行情分开展示')

def run(path,out,narrative=None,draft=False,book_judgment=None):
    path=Path(path);out=Path(out);a=json.loads(path.read_text(encoding='utf8'));out.mkdir(parents=True,exist_ok=False)
    n=json.loads(Path(narrative).read_text(encoding='utf8')) if narrative else {}
    if book_judgment:n['book_judgment']=json.loads(Path(book_judgment).read_text(encoding='utf8'))
    models=a['models'];frames={k:json.loads((path.parent/v).read_text(encoding='utf8')) for k,v in a['frames'].items()}
    conclusion=None if draft else validate_decision(a,n,frames)
    if conclusion:
        label='看涨' if conclusion['direction']=='BULLISH' else '看跌'
        n['headline']=f"明确结论：{conclusion['target_date']} {label}；基准收盘 {conclusion['reference_close']:.2f}"
    else:n['headline']='草稿：技术证据审阅，未形成正式次日方向结论'
    story=[heading(a['name']+'技术分析'),para('代码：'+a['symbol']+'｜市场：'+a['market']),para('行情观察时点：'+a['as_of']),para('目标日：'+str(a['target_date'] or '本轮未指定')),
           para('数据模式：'+a.get('mode','OBSERVED_SNAPSHOT')),para(n.get('headline','技术证据报告：尚未完成综合方向判断')),para(n.get('summary','请依据后续各模型、反证和来源审计完成综合判断；脚本不自动输出买入指令。')),
           para('已排除基本面' if a['technical_only'] else '基本面状态：未核验；不得默认成立。'),para('走势结论先由两套讲义模型独立形成；个人择时经验在报告最后单独评估，不改变方向结论。'),para('研究模拟尚未完成独立样本外策略验证；不连接券商或执行真实交易。'),PageBreak()]
    tocstyle=ParagraphStyle('TOC',parent=SMALL,fontName='Song',leading=11,spaceBefore=1,spaceAfter=2)
    toc=TableOfContents();toc.levelStyles=[tocstyle]
    story += [heading('目录',toc=False),toc,PageBreak(),heading('讲义判断情景与数据审计')]
    for s in n.get('scenarios',[]):story.append(para(s.get('condition','')+' → '+s.get('interpretation','')+'；'+str(s.get('levels','')),SMALL))
    story.append(para('观察带不是挂单价格；前复权价格必须完成当日原始报价映射后才能讨论可执行价格。',SMALL))
    for k,audit in a['audits'].items():
        story.append(para(f'{k}：最新完成有效日 {audit.get("last_final_usable")}；'+str(audit.get('calendar_scope',''))+'；失效行 '+str(audit.get('rejected_rows',sum(audit.get('flags',{}).values()))),SMALL))
    story += [PageBreak(),heading('相关市场联动、形态与模型分歧')]
    for c in a['conflicts']:
        if 'bullish' in c:
            c=dict(c,bullish=[r for r in c['bullish'] if r!='Q36'],bearish=[r for r in c['bearish'] if r!='Q36'])
            if not c['bullish'] or not c['bearish']:continue
        if c.get('type')=='CROSS_TIMEFRAME_DIFFERENCE':story.append(para(f'跨周期差异：日线结构 {c.get("daily")}，完整周线结构 {c.get("weekly")}。不同期限可以并存，不能由周线直接推断明日方向。',SMALL))
        else:story.append(para(c['series']+'：偏多模型 '+', '.join(c['bullish'])+'；偏空模型 '+', '.join(c['bearish'])+'。'+c['resolution'],SMALL))
    for c in a['correlations']:
        value='不足' if c['pearson'] is None else f'{c["pearson"]:.3f}'
        story.append(para(f'{c["series"]} · {c["window_sessions"]}交易日 · 相关序列领先{c["lag_sessions"]}期：r={value}，有效样本{c["samples"]}，窗口完整={c["complete"]}',SMALL))
    story.append(para('相关性按各自连续交易段的收益计算，不代表因果或已知预测胜率。同源序列不能重复投票；指数权重、连续合约换月或供应商构造必须另行核验。',SMALL))
    for series,events in ((k,v) for k,v in a.get('latest_patterns',{}).items() if k in ['equity_daily','equity_weekly']):
        story.append(para(series+'最近形态与边界事件',HEAD))
        if not events:story.append(para('没有处于展示状态的自动识别事件。',SMALL))
        for e in events[-15:]:story.append(para(f'{e["known_date"]}｜{e["rule_id"]} {e["pattern"]}｜{e["direction"]}｜{e["state"]}｜定义={e["definition_kind"]}',SMALL))
    for setup in a.get('fusion_setups',[]):story.append(para('融合候选：'+setup['setup']+'｜'+setup['state']+'｜证据 '+', '.join(setup['evidence'])+'｜无数值打分',SMALL))
    for w in a['warnings']:story.append(para(w,SMALL))
    for i,m in enumerate(book_view(a,{})['models'],5):
        story += [PageBreak(),heading(m['series_name']+' '+m['timeframe']+' · '+m['rule_id']+' '+m['name'],index=True),para(m['timeframe']+'｜'+m['direction']+'｜适用='+str(m['applicable'])+'｜截至 '+m['bar_end'],SMALL)]
        chart=paired(frames[m['series']],m);renderSVG.drawToFile(chart,str(out/(m['series']+'-'+m['rule_id']+'.svg')));story.append(chart)
        for label,key in [('实际观察','observations'),('模型解释','reasoning'),('反证','counter_evidence'),('确认','confirmation'),('失效','invalidation')]:story.append(para(label+'：'+m[key],SMALL))
        note=n.get('model_notes',{}).get(m['series']+':'+m['rule_id'])
        if note:story.append(para('本轮研判：'+note,SMALL))
    equity_events=a.get('latest_patterns',{}).get('equity_daily',[])
    visual_events=[e for e in equity_events if e['state'] in ['CONFIRMED','RETEST_CONFIRMED','FAILED_BREAKOUT','CREATED','ACTIVE']][-8:]
    if n.get('featured_pattern_ids'):
        selected=set(n['featured_pattern_ids'])
        visual_events=[e for e in equity_events if e['id'] in selected]
        if {e['id'] for e in visual_events}!=selected:raise ValueError('Featured pattern ID missing from current events')
    for e in visual_events:
        story += [PageBreak(),heading('形态对照 · '+e['rule_id']+' '+e['pattern'],index=True),para(f'{e["known_date"]}｜{e["direction"]}｜{e["state"]}｜定义={e["definition_kind"]}',SMALL),pattern_paired(frames['equity_daily'],e,'价格轴：前复权 '+{'CN':'CNY','HK':'HKD','US':'USD'}.get(a['market'],'来源单位')),para('锚点与阈值：'+json.dumps(e['values'],ensure_ascii=False),SMALL)]
        if n.get('pattern_notes',{}).get(e['id']):story.append(para('本轮解释：'+n['pattern_notes'][e['id']],SMALL))
    if n.get('sources'):
        story += [PageBreak(),heading('本轮数据来源与核验')]
        for source in n['sources']:story.append(para(source,SMALL))
    story += [PageBreak(),heading('关键名词与索引')]
    glossary={'ATR':'真实波幅的Wilder平滑，用于波动尺度，不给出方向。','MACD':'EMA12减EMA26得到DIF；DEA为DIF的9期EMA。本版柱体为DIF减DEA。','RSI':'14期上涨与下跌幅度的Wilder平滑相对强弱；超买超卖不等于反转。','RVOL':'当根成交量除以前20根均量；须先核验成交单位。','枢轴':'经后续两根K线确认的局部高低点，存在确认延迟。','主连':'供应商按主力合约拼接的序列，换月可影响技术指标。','加权':'多个期货合约按供应商规则合成的序列，不能替代现货价格。','前复权':'调整历史股票价格以处理公司行为；不是严格逐时点可得历史。'}
    for k,v in glossary.items():story.append(para(k+'：'+v))
    story += [PageBreak(),heading('模型索引（页码）')]
    index=ModelIndex();index.levelStyles=[tocstyle];story.append(index)
    if conclusion:
        story += [PageBreak(),heading('原讲义规则逐项审阅')]
        for key,v in sorted(conclusion['coverage_review'].items()):
            if key in {'Q36','Q37','Q40'}:continue
            story.append(para(key+'：'+v['status']+'；'+v['reason'],SMALL))
        story += [PageBreak(),heading('两套讲义的独立走势结论'),heading(n['headline'],toc=False)]
        comparison='高于' if conclusion['direction']=='BULLISH' else '低于'
        story.append(para(f"判断定义：预计目标日收盘{comparison}基准收盘{conclusion['reference_close']:.2f}；证据强度：{conclusion['confidence']}。"))
        for key,label in [('support','支持证据'),('opposition','主要反证'),('resolution','分歧取舍'),('invalidation','判断失效条件')]:story.append(para(label+'：'+str(conclusion[key])))
    story += [PageBreak(),heading('最后评估：BBI与买卖节奏')]
    story.append(para('BBI=(SMA3+SMA6+SMA12+SMA24)/4。这里只评估买卖节奏，不参与或改写前面的讲义方向判断。'))
    for card in a['price_cards']:
        tf='日线' if card['timeframe']=='daily' else '完整周线'
        if card.get('state')=='INSUFFICIENT':story.append(para(tf+'：数据不足，不能判断触线支持。',SMALL));continue
        yn=lambda key:'是' if card.get(key) else '否'
        val=lambda key:'缺失' if card.get(key) is None else f'{card[key]:.4f}'
        band=' 至 '.join('缺失' if x is None else f'{x:.4f}' for x in card.get('observation_band',[]))
        story += [para(f'{tf}｜截至 {card["bar_end"]}｜BBI {val("bbi")}｜前一期参考 {val("reference_bbi")}',SMALL),para(f'此前连续在线上 {card["prior_above_run"]} 根，研究门槛 {card["required_bars"]} 根；上升背景满足：{yn("prior_uptrend")}；实际触线：{yn("exact_touch")}；收盘守住参考：{yn("close_holds_reference")}。',SMALL),para(f'本周期触线支持：{yn("support_present")}。单凭此项不能买入。波动观察带：{band}，不是可执行委托价格。',SMALL)]
    for m in [m for m in models if m['rule_id']=='Q36']:
        story += [heading(m['timeframe']+' BBI理论与实际',toc=False),paired(frames[m['series']],m)]
        note=n.get('model_notes',{}).get(m['series']+':Q36')
        if note:story.append(para(note,SMALL))
    if conclusion:
        story.append(para('讲义方向保持：'+('看涨' if conclusion['direction']=='BULLISH' else '看跌')+'；以下只评估交易是否合适。'))
        story.append(para(n['timing_review']))
        for key in ['Q36','Q37','Q40']:
            v=conclusion['coverage_review'][key];story.append(para(key+'：'+v['status']+'；'+v['reason'],SMALL))
        for x in conclusion['actions']:
            story.append(para(x['action']+'：'+x['condition']+'；价格 '+str(x.get('price_range','不适用'))+'；来源 '+x['price_source']+'；确认 '+x['confirmation_timing']+'；执行 '+x.get('execution','NONE')+'；价格口径 '+x.get('price_basis','不适用')))
        story.append(para('收盘确认后最早在下一交易日执行，若开盘跳过候选价格区则重新评估；前复权参考价未经映射不能当作可成交报价。',SMALL))
    doc=Report(str(out/'technical-analysis.pdf'),pagesize=(595,842),leftMargin=42,rightMargin=42,topMargin=36,bottomMargin=40)
    doc.multiBuild(story,onFirstPage=footer,onLaterPages=footer)
    print(out/'technical-analysis.pdf')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--analysis',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--narrative',type=Path);p.add_argument('--draft',action='store_true');p.add_argument('--book-judgment',type=Path);a=p.parse_args();run(a.analysis,a.out,a.narrative,a.draft,a.book_judgment)
