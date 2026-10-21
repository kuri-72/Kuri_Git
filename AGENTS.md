# 仓库协作规则（给 AI 助手）

本文件由仓库维护者指定。任何在本仓库里工作的 AI 助手，开工前先读完，并照做。

## 开始前

1. 先 `git pull`，确保基于远端最新的 `main` 工作。
2. 若本地有未提交的改动，先 `git commit`（或 `git stash`）再 pull，不要带着脏工作区硬拉。
3. 校验提交身份：`git config user.email` 必须是 `345989840+kuri-72@users.noreply.github.com`；不对就先改好再提交。

## 结束后

```bash
git add -A
git commit -m "这次改了什么"
git push
```

- 提交信息用一句中文概括这次改动，沿用仓库现有风格（`docs:` / `chore:` / `feat:` 前缀可选）。
- `push` 被拒（远端已有新提交）时：先 `git pull` 解决，再 `git push`。

## 禁止

- `git push --force`（任何形式，包括 `--force-with-lease`）
- 改写已有历史：`commit --amend`、交互式 `rebase`、`filter-branch`、`reset --hard` 后强推
- 提交 `.env`、密钥、证书、token、密码；提交信息里不要出现真实邮箱
- 未经用户同意删除或覆盖用户的文件

## 环境

- 主设备：本机 Windows，仓库在 `C:\Users\ROG\Desktop\Kuri_Git`。
- 远程：SSH `git@github.com:kuri-72/Kuri_Git.git`，私钥 `~/.ssh/id_ed25519_github`，push 无需登录。
- Git 可执行文件：`C:\Program Files\Git\cmd\git.exe`（可能不在 PATH）。
- 本机 Git Credential Manager 一启动就崩溃（`0xE0434352`），HTTPS 认证走不通，统一用 SSH。
- 不要给 Git 配置 `http.proxy`；网络偶发失败时重试即可。

## 交流

- 用中文回复。
