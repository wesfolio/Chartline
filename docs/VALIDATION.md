# 发布前验证

2026-09-20，Windows / Python 3.12：

- `python -m pytest scripts/tests -q`：63 passed in 59.60s。
- skill-creator quick_validate：Skill is valid。
- `python scripts/audit_sources.py`：36页、46图、41规则映射结构通过。
- 发布ZIP不包含第三方PDF、DOCX、字体、真实行情文件、Python缓存或虚拟环境。

测试价格与成交量为合成数据，验证软件契约而非市场表现。GitHub Actions 尚未远程执行，Linux及全新依赖安装仍需发布后验证；实时数据抓取与PDF渲染没有在本次打包任务重新验证。原图不在公开版，因此此处不声称完成原图复核。
