# 第一次发布到 GitHub

本目录是可直接放入 Git 仓库的源码，不需要把 ZIP 当作唯一仓库内容。当前仅准备了本地文件，尚未创建远程仓库或发布。

## 1. 决定发布名称与许可

建议仓库名 `chartline`，显示名 **Chartline · 价格见势**，与 Rootline 配套。名称不是商标独占性保证。

已准备 MIT 许可，允许他人使用、修改、再分发和商业使用，须保留许可声明。版权行使用 `Chartline contributors`；你可在发布前改成自己的公开姓名或组织。若不希望允许商业使用，需要重新考虑许可，不能直接保留 MIT 后又增加冲突限制。

确认仅发布此公开版，不上传此前包含第三方讲义和真实快照的完整分享包。

## 2. 创建空仓库

登录 GitHub → 右上角 + → New repository：

- Repository name：`chartline`
- Description：`Evidence-first technical analysis skill with AKShare, chart comparisons and PDF reports.`
- Visibility：Public
- 不勾选初始化 README、.gitignore 或 license，本地已经包含。

## 3. 上传源码

推荐用 GitHub Desktop：Add local repository，必要时选择 Create a repository here，然后提交文件；Publish repository 时使用 `chartline` 并取消私有选项。若前一步已经创建远程仓库，也可以使用下面的命令行。

在解压后含 SKILL.md 和 README.md 的 chartline 根目录执行（需安装 Git）：

```sh
git init -b main
git add .
git status
git commit -m "Initial public release of Chartline"
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/chartline.git
git push -u origin main
```

先把 `YOUR_GITHUB_USERNAME` 改为自己的 GitHub 用户名。如 Git 要求作者信息，用你自己的公开姓名和 GitHub noreply 邮箱配置 `git config user.name` / `git config user.email`；通过 GitHub 的正常认证流程登录，不把密码或令牌写入命令或文件。

`git status` 时检查没有私有资料、环境文件和真实行情。也可以使用 GitHub 网页上传解压后的全部源码，但注意包含 `.github`、`.gitignore` 等隐藏项目文件；命令行或 Desktop 更可靠。

## 4. 查看自动测试

进入 Actions，等待 Tests 完成。第一次 GitHub/Linux 运行尚未在本地 Windows 环境代替验证。失败时按日志处理；不要把绿色 CI 当作预测盈利证明。

在 About 添加主题：`technical-analysis`、`akshare`、`agent-skills`、`python`。在 Settings → Security 启用私密漏洞报告（如该选项可用）。

## 5. 发布版本

Tests 通过后，在 Releases → Draft a new release 中创建标签 `v0.1.0`，标题 `Chartline 0.1.0 — Research Preview`，复制 CHANGELOG 对应条目并勾选预发布。

GitHub 自动提供源码 ZIP。向朋友发送仓库链接即可；他们按 README 安装。后续修改先提交、测试，再建立新版本标签，不覆盖已经发布的版本内容。

## 官方说明

- [创建仓库](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)
- [仓库许可证](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)
