# 两阶段结论契约（v2.2优先）

先读取book-evidence.json，依据model-catalog.json的27个讲义模型族，完成book-judgment.json，再读取完整行情指标中的BBI。第一阶段包含direction、target_date、reference_close、confidence、support、opposition、resolution、invalidation，以及model_review（27个模型族逐项status/reason）和evidence_rule_ids（真正参与方向判断的讲义规则ID）。此文件不含BBI、Q36/Q37/Q40或个人多空指标经验。

第二阶段写narrative.json：conclusion保留上述八个方向字段原值，coverage_review中的27个框架审阅也保持一致；补齐全部41条工程规则，加入actions及顶层timing_review。BBI只出现在timing_review、actions、Q36模型注释以及Q36/Q37/Q40审阅中，不进入summary、scenarios或其他模型方向说明。render_report使用--book-judgment读取独立文件。正式报告缺少第一阶段文件/对象、模型漏评、方向字段变化或已知BBI引用会拒绝生成。

报告顺序：讲义方向摘要→数据与模型证据→逐项审阅→讲义独立走势结论→最后的BBI与买卖节奏。程序校验确保字段分离与一致，不证明推理绝对不受其他信息影响；必须遵守先读分离证据、先保存判断的操作顺序。不得在第二阶段为了让BBI结论看起来一致而重写第一阶段文件。若行情更新或讲义证据出错，另开有记录的新分析版本。

# 次日判断与交易时序

理论依次使用A1-A15的趋势、位置、结构、量价与动量，以及B1-B21蜡烛的前趋势、形态、位置、确认和失效。BBI连续背景来自用户补充，仅用于最后的交易节奏。不要用模型票数、同源指标叠加或任意权重替代解释。

有效数据下，正式报告必须明确看涨或看跌：目标为最新完成交易日之后的第一个交易日，比较目标收盘与基准收盘。收平独立记录为FLAT，不算看涨或看跌命中。数据失效时只能输出草稿并说明原因，不能为二选一而编造方向。

逐步综合：先查数据和旧结构是否已被当前价格破坏，再解释周线背景、日线结构、支撑阻力和形态状态，最后使用量价与动量确认。超买、背离、触线及未确认形态只作辅助。每个相反模型须说明为何影响或未改变主判断。此顺序源于讲义A15、B11、B19；数值阈值和自动分类是未校准的工程规则。

render_report正式模式需要narrative.conclusion，缺项直接报错。--draft仅生成证据审阅稿，不作为次日预测交付。conclusion字段：

- direction：BULLISH或BEARISH；target_date；reference_close；price_basis（如qfq）；confidence（文字强弱，不是概率）。
- support、opposition、resolution、invalidation：支持、反证、取舍、失效条件，不允许空白。
- coverage_review：Q01到Q41每条对应status和reason；status为APPLIES、NO_SIGNAL、INSUFFICIENT、NOT_APPLICABLE之一。必须结合当轮数据逐项填写，不用一个通用理由批量填充。不能把“没有检测到”写成“没有评估”。
- actions：action为BUY/SELL/HOLD/WAIT；condition；price_source；confirmation_timing为INTRADAY/CLOSE/NONE；execution。BUY/SELL还须price_range=[下限,上限]、price_basis=RESEARCH_ADJUSTED或VERIFIED_RAW。

凡以收盘作为确认依据，execution必须为NEXT_SESSION。不能使用当天更早的回调价格作为事后确认后的成交价。目标区未到就不成交，跳空超出价格区须重评。A股T+1、涨跌停、停牌、费用与滑点必须单列，日线OHLC无法证明同根内成交顺序。未核验复权映射时只给研究参考区。

首页与讲义独立走势结论页使用同一份冻结方向；最后附BBI择时，两个部分均加入目录和书签。预测复盘用evaluate_forecast.py，对冻结判断和明确同口径目标日收盘比较；它不等于交易策略回测。事件研究另给1/3/5/10/20根收益，1根是下一开盘到该收盘，与收盘到收盘预测分开。
