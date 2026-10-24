# Git 钩子

## `pre-commit` — 密钥拦截

提交前扫描暂存区，命中以下任一条件就**拒绝提交**：

| 检查 | 说明 |
|---|---|
| `.env` 被暂存 | 任何路径下的 `.env` 都不许入库 |
| `sk-` + 16 位以上字母数字 | 疑似真实 API Key（`.env.example` 里的占位符已排除） |
| `X72_API_KEY=` 后跟非空值 | 排除 `.md` 与 `.env.example` |

命中时会打印「文件:行号」，方便定位；确认是误报可以用 `git commit --no-verify` 绕过（不推荐）。

## 每台设备启用一次

钩子文件在仓库里，但 **`core.hooksPath` 是本地配置**，所以每台设备克隆后要执行一次：

```bash
git config core.hooksPath .githooks
```

验证是否生效：

```bash
git config --get core.hooksPath     # 应输出 .githooks
```

不执行这一步，钩子不会运行——但 `.gitignore` 里的 `.env` 规则仍然有效。
