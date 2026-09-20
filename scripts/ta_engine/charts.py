"""Deterministic vector charts: real OHLC stays separate from synthetic theory."""
import math,re,os
from reportlab.graphics.shapes import Drawing,Line,Rect,String,Circle,PolyLine
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path

def fonts():
    for name,file in [('Song','simsun.ttc'),('Hei','simhei.ttf')]:
        if name not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(name,str(Path(os.environ.get('TA_FONT_DIR','C:/Windows/Fonts'))/file)))
fonts()
INK=colors.HexColor('#19374c');UP=colors.HexColor('#0072B2');DOWN=colors.HexColor('#D55E00');BBI=colors.HexColor('#754AA6');GRID=colors.HexColor('#dce2e7')
def finite(v):return isinstance(v,(int,float)) and math.isfinite(v)
def label(g,x,y,text,size=8,font='Song',color=INK):
    if font!='Song':g.add(String(x,y,str(text),fontName=font,fontSize=size,fillColor=color));return
    for part in re.findall(r'[\x00-\x7f]+|[^\x00-\x7f]+',str(text)):
        face='Song' if part.isascii() else 'Song'
        g.add(String(x,y,part,fontName=face,fontSize=size,fillColor=color));x+=pdfmetrics.stringWidth(part,face,size)
def line(g,x1,y1,x2,y2,color=INK,width=.8,dash=None):g.add(Line(x1,y1,x2,y2,strokeColor=color,strokeWidth=width,strokeDashArray=dash))
def axes(g,x,y,w,h,values,dates=None,bounds=None):
    vals=[v for v in values if finite(v)];lo,hi=bounds or ((min(vals),max(vals)) if vals else (0,1))
    span=max(hi-lo,.01);lo-=span*.1;hi+=span*.1
    if bounds:lo,hi=bounds
    def sy(v):return y+(v-lo)/(hi-lo)*h
    for i in range(4):
        v=lo+(hi-lo)*i/3;yy=sy(v);line(g,x,yy,x+w,yy,GRID,.5);label(g,x-30,yy-3,f'{v:.1f}',7,'Song')
    line(g,x,y,x,y+h,INK,.6);line(g,x,y,x+w,y,INK,.6)
    if dates:
        for f,anchor in [(0,'start'),(.5,'middle'),(1,'end')]:
            idx=round((len(dates)-1)*f);s=dates[idx];xx=x+f*w
            g.add(String(xx,y-12,s,fontName='Song',fontSize=6.5,textAnchor=anchor,fillColor=INK))
    return sy
def series(g,values,x,y,w,h,sy,color,stroke=1.1):
    n=len(values);prev=None
    for i,v in enumerate(values):
        if not finite(v):prev=None;continue
        cur=(x+(i+.5)/n*w,sy(v))
        if prev:line(g,*prev,*cur,color,stroke)
        prev=cur
def candles(g,rows,x,y,w,h,sy):
    n=len(rows);cw=min(5,w/n*.65)
    for i,r in enumerate(rows):
        xx=x+(i+.5)/n*w;col=UP if r['close']>=r['open'] else DOWN
        line(g,xx,sy(r['low']),xx,sy(r['high']),col,.65)
        yy=min(sy(r['open']),sy(r['close']));height=abs(sy(r['close'])-sy(r['open']))
        if height<.7:line(g,xx-cw/2,yy,xx+cw/2,yy,col,1)
        else:g.add(Rect(xx-cw/2,yy,cw,height,fillColor=col,strokeColor=col,strokeWidth=.4))
def actual_panel(g,rows,model,x,y,w,h,events=(),context=False):
    family=model['rule_id'];rows=rows[-(160 if context else 8 if family=='Q17' else 80):]
    px=x+33;pw=w-39;bottom=y+23;ph=h-58
    has_sub=family in ['Q06','Q30','Q07'];price_y=bottom+ph*.45 if has_sub else bottom;price_h=ph*.55 if has_sub else ph
    prices=[r[k] for r in rows for k in ['high','low']]+([r.get('bbi') for r in rows] if family=='Q36' else [])
    dates=[r['session_date'][2:] for r in rows]
    sy=axes(g,px,price_y,pw,price_h,prices,dates if not has_sub else None)
    candles(g,rows,px,price_y,pw,price_h,sy)
    if family=='Q36':series(g,[r.get('bbi') for r in rows],px,price_y,pw,price_h,sy,BBI,1)
    if family in ['Q09','Q30']:
        anchors=model.get('values',{}).get('highs',[])+model.get('values',{}).get('lows',[])
        for i,e in enumerate(anchors,1):
            ix=next((i for i,r in enumerate(rows) if r['session_date']==e['pivot_date']),None)
            if ix is not None:
                xx=px+(ix+.5)/len(rows)*pw;yy=sy(e['price']);g.add(Circle(xx,yy,2.5,fillColor=None,strokeColor=INK));label(g,xx+3,yy+(5 if e['kind']=='HIGH' else -10),('H' if e['kind']=='HIGH' else 'L')+str(1 if i in [1,3] else 2),6.5,'Song')
    if family=='Q36':
        last=rows[-1]
        for key in ['bbi_band_lo','bbi_band_hi']:
            if finite(last.get(key)):
                yy=sy(last[key]);line(g,px+pw*.72,yy,px+pw,yy,BBI,.7,[2,2])
    if has_sub:
        sh=ph*.31
        if family=='Q06':
            vals=[r.get(k) for r in rows for k in ['dif','dea','hist']]+[0];ss=axes(g,px,bottom,pw,sh,vals,dates)
            line(g,px,ss(0),px+pw,ss(0),INK,.6)
            for i,r in enumerate(rows):
                v=r.get('hist')
                if finite(v):line(g,px+(i+.5)/len(rows)*pw,ss(0),px+(i+.5)/len(rows)*pw,ss(v),UP if v>=0 else DOWN,1.4)
            series(g,[r.get('dif') for r in rows],px,bottom,pw,sh,ss,UP);series(g,[r.get('dea') for r in rows],px,bottom,pw,sh,ss,DOWN)
            label(g,px,bottom+sh+6,'DIF蓝 / DEA橙 / 柱体=DIF-DEA',6.8)
        elif family=='Q30':
            ss=axes(g,px,bottom,pw,sh,[],dates,bounds=(0,100));series(g,[r.get('rsi') for r in rows],px,bottom,pw,sh,ss,BBI)
            for prefix,key in [('H','highs'),('L','lows')]:
                for j,e in enumerate(model.get('values',{}).get(key,[]),1):
                    ix=next((i for i,r in enumerate(rows) if r['session_date']==e['pivot_date']),None)
                    if ix is not None and finite(e.get('rsi')):
                        xx=px+(ix+.5)/len(rows)*pw;yy=ss(e['rsi']);g.add(Circle(xx,yy,2.3,fillColor=None,strokeColor=INK));label(g,xx+3,yy+5,prefix+str(j),6.2,'Song')
            for v in [30,70]:line(g,px,ss(v),px+pw,ss(v),INK,.5,[2,2])
            label(g,px,bottom+sh+6,'RSI(14) / 阈值30与70',6.8)
        else:
            vv=[r['volume']/1e6 if r.get('volume_usable') and finite(r.get('volume')) else None for r in rows];ss=axes(g,px,bottom,pw,sh,[0]+vv,dates,bounds=(0,max([v for v in vv if finite(v)]+[1])*1.1))
            for i,v in enumerate(vv):
                if finite(v):line(g,px+(i+.5)/len(rows)*pw,ss(0),px+(i+.5)/len(rows)*pw,ss(v),UP,1.5)
            series(g,[r.get('volume_baseline')/1e6 if finite(r.get('volume_baseline')) else None for r in rows],px,bottom,pw,sh,ss,DOWN)
            label(g,px,bottom+sh+6,model.get('volume_label','成交量：百万原始单位')+' / 橙线：前20根均量',6.1)
    label(g,x+3,y+h-15,'实际：截至 '+rows[-1]['session_date'],8)
    label(g,x+3,y+h-28,model.get('axis_label','价格轴：见来源口径')+'；蓝涨／橙跌',6.5)
    line(g,px+pw,price_y,px+pw,price_y+price_h,INK,.6,[2,2])
    return rows

def theory_panel(g,model,x,y,w,h):
    family=model['rule_id'];label(g,x+3,y+h-15,'理论：按规则重绘的合成示意',8)
    label(g,x+3,y+h-28,'横轴：相对bar；纵轴：示意单位',7)
    px=x+31;pw=w-40;by=y+25;hh=h-65
    vals=[10,11,13,11,12,15,13,14,17,15,16]
    if family in ['Q09','Q06','Q07'] and model['direction']=='BEARISH':vals=[30-v for v in vals]
    if family=='Q36':vals=[10,11,12,13,14,16,15,14,13.6,13.4,14.5]
    if family=='Q17':
        rr=[dict(open=14,close=12,high=15,low=11),dict(open=11.5,close=14.5,high=15,low=11)]
        bear=model['direction']=='BEARISH'
        if bear:rr=[dict(open=r['close'],close=r['open'],high=r['high'],low=r['low']) for r in rr]
        ss=axes(g,px,by,pw,hh,[10,16]);candles(g,rr,px,by,pw,hh,ss);label(g,px,by+hh-12,'前置：上升趋势' if bear else '前置：下降趋势',8);label(g,px,by+hh-26,'阴实体覆盖前阳实体' if bear else '阳实体覆盖前阴实体',8);label(g,px,by-13,'A                  B',7,'Song');return
    sub=family in ['Q06','Q30','Q07'];py=by+hh*.48 if sub else by;ph=hh*.5 if sub else hh
    if family=='Q30':vals=[10,11,14,11,12,15,12] if model['direction']!='BULLISH' else [15,14,11,14,13,10,13]
    ss=axes(g,px,py,pw,ph,vals);series(g,vals,px,py,pw,ph,ss,INK,1.6)
    if family=='Q36':
        b=[9.5,10,10.5,11,11.5,12,12.5,13,13.2,13.4,13.5];series(g,b,px,py,pw,ph,ss,BBI,1.4)
        label(g,px+pw*.40,py+ph*.82,'持续在线上后回调',8);label(g,px+pw*.5,py+ph*.2,'触线仅作支持证据',8,color=BBI)
    if family=='Q09':
        label(g,px+5,py+ph*.8,'LH + LL' if model['direction']=='BEARISH' else 'HH + HL',9,'Song')
        label(g,px+5,py+ph*.65,'拐点需等后续两根确认',7)
    if sub:
        sh=hh*.3
        if family=='Q06':
            vv=[-1,-.8,-.6,-.3,.1,.4,.8,1.1];sig=[-.9,-.9,-.8,-.6,-.4,-.1,.2,.5]
            if model['direction']=='BEARISH':vv=[-v for v in vv];sig=[-v for v in sig]
            ss=axes(g,px,by,pw,sh,vv+sig+[0]);series(g,vv,px,by,pw,sh,ss,UP);series(g,sig,px,by,pw,sh,ss,DOWN);line(g,px,ss(0),px+pw,ss(0),INK,.5,[2,2]);label(g,px,by+sh+5,'DIF与DEA及零轴条件',7)
        elif family=='Q30':
            vv=[50,60,78,50,58,65,50] if model['direction']!='BULLISH' else [50,40,22,50,42,35,50]
            ss=axes(g,px,by,pw,sh,[],bounds=(0,100));series(g,vv,px,by,pw,sh,ss,BBI);label(g,px,by+sh+5,'价格与RSI相反的枢轴推进',7)
        else:
            vv=[1,1,1.2,.9,1.1,1.7,2];ss=axes(g,px,by,pw,sh,[0]+vv,bounds=(0,2.2))
            for i,v in enumerate(vv):line(g,px+(i+.5)/len(vv)*pw,ss(0),px+(i+.5)/len(vv)*pw,ss(v),UP,9)
            line(g,px,ss(1),px+pw,ss(1),DOWN,.8);label(g,px,by+sh+5,'放量与价格方向同时观察',7)
    label(g,px,by-13,'1          相对bar          N',7,'Song')

def paired(rows,model):
    g=Drawing(480,250);theory_panel(g,model,0,0,224,250);line(g,235,10,235,244,GRID,1)
    actual_panel(g,rows,model,245,0,235,250)
    return g

def context_chart(rows,tf):
    g=Drawing(480,235);m=dict(rule_id='Q09',values={})
    actual_panel(g,rows[-(160 if tf=='daily' else 100):],m,0,0,480,235,context=True)
    return g

def pattern_paired(rows,event,axis_label='价格轴：见来源口径'):
    """Generic source-labelled schematic plus the causal actual anchor window."""
    g=Drawing(480,250);name=event['pattern'];direction=event['direction']
    label(g,3,235,'理论：'+name+' 合成几何示意',8);label(g,3,222,'阈值以事件JSON为准；非收益承诺',6.5)
    x,y,w,h=30,45,180,150
    mirror=direction=='BULLISH'
    shapes={
      'HEAD_AND_SHOULDERS_TOP':[2,5,3,8,3.2,5.2,2], 'INVERSE_HEAD_AND_SHOULDERS':[8,5,7,2,6.8,4.8,8],
      'DOUBLE_TOP':[2,7,4,7,2], 'DOUBLE_BOTTOM':[8,3,6,3,8], 'TRIPLE_TOP':[2,7,3,7,3,7,2], 'TRIPLE_BOTTOM':[8,3,7,3,7,3,8],
      'RECTANGLE':[5,8,5,8,5,8,5], 'SYMMETRICAL_TRIANGLE':[2,8,3,7,4,6,5],
      'ASCENDING_TRIANGLE':[3,8,5,8,6.5,8], 'DESCENDING_TRIANGLE':[8,3,8,5,8,6.5],
      'RISING_WEDGE':[2,4,3,5,4,5.6,5], 'FALLING_WEDGE':[8,6,7,5,6,4.5,5],
      'BROADENING_FORMATION':[5,4,6,3,7,2,8], 'DIAMOND_FORMATION':[5,4,2,5,8,6,5],
      'ROUNDING_TOP':[2,5,7,8,7,5,2], 'ROUNDING_BOTTOM':[8,5,3,2,3,5,8],
      'BULL_FLAG':[2,8,7,6.5,7.5,6,8.5], 'BEAR_FLAG':[8,2,3,3.5,2.5,4,1.5],
      'BULL_PENNANT':[2,8,7,6,7.5,6.5,8.5], 'BEAR_PENNANT':[8,2,3,4,2.5,3.5,1.5]
      ,'SUPPORT':[7,4,6,4,7], 'RESISTANCE':[3,6,4,6,3], 'UP_TRENDLINE':[2,4,3,6,5,8], 'DOWN_TRENDLINE':[8,6,7,4,5,2]
    }
    vals=shapes.get(name)
    if vals:
        lo=min(vals);hi=max(vals);pts=[]
        for i,v in enumerate(vals):pts += [x+i*w/(len(vals)-1),y+(v-lo)/(max(hi-lo,.1))*h]
        g.add(PolyLine(pts,strokeColor=INK,strokeWidth=2));line(g,x,y,x+w,y,GRID,.5);label(g,x,y-15,'相对bar',7,'Song')
    else:
        bull=direction!='BEARISH';rr=[dict(open=13,close=11,high=14,low=10),dict(open=10.5,close=13.5,high=14,low=10)] if bull else [dict(open=11,close=13,high=14,low=10),dict(open=13.5,close=10.5,high=14,low=10)]
        if name in ['DOJI','GRAVESTONE_DOJI','DRAGONFLY_DOJI','SPINNING_TOP']:
            rr=[dict(open=12,close=12.05,high=14,low=10)] if name=='DOJI' else [dict(open=12,close=12.05,high=14,low=12)] if name=='GRAVESTONE_DOJI' else [dict(open=12,close=12.05,high=12.1,low=10)] if name=='DRAGONFLY_DOJI' else [dict(open=11.8,close=12.2,high=14,low=10)]
        if 'STAR' in name or 'BABY' in name:rr.insert(1,dict(open=9,close=9.1,high=9.3,low=8.8))
        if name=='STAR_UP':rr=[dict(open=10,close=13,high=13.5,low=9.7),dict(open=13.7,close=13.9,high=14.6,low=13.4)]
        if name=='DOJI_STAR_UP':rr=[dict(open=10,close=13,high=13.5,low=9.7),dict(open=13.8,close=13.8,high=14.6,low=13.4)]
        ss=axes(g,x,y,w,h,[8,15]);candles(g,rr,x,y,w,h,ss)
    label(g,3,18,'来源页：'+','.join(event.get('source_pages',[])),7)
    known=int(event['known_pos']);lookback=12 if event['rule_id'] in {'Q14','Q15','Q16','Q17','Q18','Q19','Q20','Q21','Q22'} else 60
    actual=rows[max(0,known-lookback):min(len(rows),known+6)]
    model=dict(rule_id='GENERIC',values={},axis_label=axis_label,volume_label='成交量：来源单位')
    actual_panel(g,actual,model,245,0,235,250)
    label(g,248,207,'事件：'+event['state']+' / '+event['definition_kind'],6.2)
    return g
