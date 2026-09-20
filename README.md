# Chartline 

Chartline 是面向 AI 编程助手的股票技术分析 Skill，结合 Python 与 AKShare 获取行情、计算日周线指标、识别形态、展示模型分歧并生成中文 PDF。它是研究工具，不是训练完成的预测模型或自动交易系统。

首次公开版：**0.1.0 · 研究预览**，由内部 technical-analysis-akshare 2.2.0 整理。

## 核心流程

行情与日期核验 → 独立技术证据 → 27 个框架逐项审阅 → 保存方向判断 → 最后评估 BBI 与交易节奏 → 理论/实际图表对照 → PDF → 后续复盘。

1. 第一阶段仅使用 `book-evidence.json`，完成 `book-judgment.json`，不读取 BBI。
2. 第二阶段读取完整分析结果。BBI 仅补充交易节奏，不能改变第一阶段的方向、强弱与理由。
3. 正式报告明确给出目标交易日看涨或看跌，含义为目标收盘相对参考收盘；列出反证、失效条件及有依据的条件价位。数据不足时生成草稿，不编造结论。
4. 支持、反对模型都要解释；不按指标票数投票，也不把主观置信描述当成统计胜率。

## 包含多少模型

| 框架分类 | 数量 |
|---|---:|
| 趋势与位置 | 6 |
| 指标与量价 | 4 |
| 蜡烛形态 | 10 |
| 价格形态 | 6 |
| 量度目标 | 1 |
| 合计 | **27** |

另有 Q01—Q41 工程规则与 36 页/46 张图的来源定位索引。这些数量不能相加为模型数量，也不代表完整覆盖两本教材或所有模型都已成熟。详见 [模型目录](references/model-catalog.md) 与 [实现清单](references/implementation-coverage.csv)。

## 快速开始

需要 Python 3.12（当前验证版本）和能使用本地 Skill 的 AI 助手。仓库根目录本身就是完整 Skill；仅运行 Python 不会自动生成最终综合判断。

下载仓库后，在仓库根目录建立环境：

```sh
python -m venv .venv
# Windows PowerShell
.venv\Scripts\python.exe -m pip install -r requirements.txt
# macOS / Linux
.venv/bin/python -m pip install -r requirements.txt
```

以下命令中的 `python` 应替换成上述虚拟环境 Python，或先激活环境。

```sh
python -m pytest scripts/tests -q
python scripts/audit_sources.py
python scripts/analyze_market.py --bundle scripts/tests/fixtures/bundle.json --out output/offline-demo --target-date 2026-09-18 --technical-only
```

离线样本是合成数据，日期固定用于回归；不能用其分析真实股票。输出目录须为新目录。

将完整 `chartline` 文件夹放入你的助手支持的 Skill 目录。当前工程采用 Codex 的 `~/.codex/skills/chartline`（配置 CODEX_HOME 时为其 skills 子目录）；其他宿主按其安装规则设置。重新打开任务后调用：

> 使用 $chartline 分析指定股票下一交易日的走势。先冻结不含 BBI 的判断，再讨论交易节奏，并输出图表对照和 PDF。

真实行情示例：

```sh
python scripts/fetch_market.py --market CN --symbol 000001 --name 示例股票 --out output/snapshot
```

随后按 [运行说明](references/runtime.md) 与 [结论契约](references/decision-contract.md) 生成分析、由助手填写独立判断及报告叙述，再运行报告脚本。不是一条抓取命令即可形成投资结论。

## PDF 与字体

正文、英文及数字采用宋体，标题采用黑体。Windows 默认读取 `C:/Windows/Fonts/simsun.ttc` 和 `simhei.ttf`；其他环境设置 `TA_FONT_DIR` 指向合法安装且含同名文件的字体目录。仓库不分发字体。缺字体会导致报告模块加载失败；纯计算与回归测试无需字体。版面检查另需 Poppler 等 PDF 渲染工具。

## 目录

```text
SKILL.md                 助手入口与约束
agents/openai.yaml       Skill 显示及调用信息
scripts/                 数据、分析、报告、回测与测试
references/              模型、规则、来源索引、数据/报告契约
assets/source-notes/      可选私有资料位置（公开版不含原资料）
docs/PUBLISHING.md        GitHub 首次发布步骤
.github/                 自动测试与协作模板
```

## 范围与已知限制

- 优先支持 A 股，含港股/美股适配；尚未完成所有市场实时端到端验证。
- 行业指数、商品、汇率等只按实际暴露或用户要求加入，生猪不是默认前提。历史期货标识仅保留在合成适配测试中。
- 图形阈值是可审阅的工程近似；27 个框架不等于 27 个经过独立验证的预测器。
- 部分形态语义、量度目标与图示仍需完善；1小时/4小时周期未完整接入。见实现清单。
- 尚无独立样本外盈利证明；前复权历史、连续合约构造、交易日历和数据供应商变化均限制研究结论。
- 无券商连接，不自动下单。正式方向是可复盘的研究判断，不是收益承诺。

## 来源与许可

理论来源于《金融市场技术分析》《日本蜡烛图技术》的讲课笔记整理，并非教材全文。公开版**不含第三方讲义 PDF、原图截图、含原图的整合 PDF、真实行情快照或商业字体**；保留定位索引与工程实现。缺原资料时不得声称已完成原图复核。

本项目原创代码与文档采用 [MIT License](LICENSE)，第三方作品和服务不在该授权范围内。详见 [第三方说明](THIRD_PARTY_NOTICES.md)。

参与改进见 [贡献指南](CONTRIBUTING.md)，首次发布见 [发布步骤](docs/PUBLISHING.md)。
