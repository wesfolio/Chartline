# 合成回归数据

所有价格与成交量均为人工合成，不是真实证券历史。

设行号 i 从 0 开始，股票缩放 s=1，其他序列 s=400：
close=round((20+0.015*i+1.2*sin(0.19*i))*s,2)；open=round(close*(1+0.003*sin(0.7*i)),2)；high=round(max(open,close)*1.01,2)；low=round(min(open,close)*0.99,2)；volume=1000000+100*i；amount=round(close*volume,2)。

保留交易日、接口格式和历史代码以验证解析与日历；这些标识不表明数据来自供应商，也不构成行业倾向。bundle 的 SHA256 用于核验文件完整性。
