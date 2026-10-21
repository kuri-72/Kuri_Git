# Kuri_Git

kuri72 的代码仓库。

## 说明

初次初始化，内容待补充。

## 开始使用

```bash
git clone https://github.com/kuri-72/Kuri_Git.git
```

## 目录结构

```text
.
├── README.md
└── .gitignore
```

## 多设备同步（三台设备）

核心只有一句话：**改之前先拉（pull），改完就推（push）**。

### 新设备第一次使用

```bash
# 1. 安装 Git for Windows（https://git-scm.com/download/win）

# 2. 设置身份（必须和 GitHub 账号对应，否则提交不算你的）
git config --global user.name  "kuri72"
git config --global user.email "345989840+kuri-72@users.noreply.github.com"

# 3. 克隆仓库
git clone https://github.com/kuri-72/Kuri_Git.git

# 4. 第一次 push 时会弹出 GitHub 登录窗口，授权一次即可，之后不用再登录
```

### 日常：每次开始工作前

```bash
git pull
```

### 日常：改完之后

```bash
git add -A
git commit -m "说明这次改了什么"
git push
```

### 三台设备的正确顺序

假设 A、B、C 三台设备：

1. 在 A 改完 → `push`
2. 换到 B 之前 → **先 `pull`**，再改，改完 `push`
3. 换到 C 之前 → **先 `pull`**，再改，改完 `push`

只要每次都遵守「先 pull 再改」，就不会冲突。

### 如果 push 被拒绝

说明别的设备先推了新提交，你的本地落后了。按顺序执行：

```bash
git pull
git push
```

### 两个必须记住的禁忌

- **不要在没 pull 的情况下直接 push**，尤其是隔了很久才打开另一台设备。
- **不要用 `git push --force`**，除非你清楚地知道要丢弃远端内容。

## 交接给 AI 助手（换新设备时用）

换到新设备时，把这一节连同上面的内容一起发给 AI 助手，并授予完整权限。

### 任务目标

在这台新设备上配置好 Git 环境，克隆本仓库，并保证能正常 pull / push。

### 关键信息

- 仓库地址：`https://github.com/kuri-72/Kuri_Git.git`
- 分支：`main`
- 提交身份：`kuri72` / `345989840+kuri-72@users.noreply.github.com`
- **邮箱必须使用上面的 noreply 地址，绝对不要用真实邮箱**（用户明确不希望邮箱公开）

### 执行步骤

1. 检查 Git 是否安装：`git --version`。未安装则用 `winget install --id Git.Git -e` 安装。
2. 设置全局身份：
   ```bash
   git config --global user.name  "kuri72"
   git config --global user.email "345989840+kuri-72@users.noreply.github.com"
   ```
3. 克隆仓库到用户指定目录（默认桌面），**不要放在 OneDrive 等自动同步目录里**。
4. 验证：`git ls-remote origin` 能读到 `refs/heads/main`，且 SHA 与本地 `git rev-parse HEAD` 一致。
5. 首次 push 会弹出 GitHub 浏览器授权窗口，**需要用户本人手动完成登录**，助手无法代为点击。

### 已知环境问题（Windows + DeepSeek Harness 沙箱）

- 受限沙箱下 Git 的 schannel TLS 后端会报 `SEC_E_NO_CREDENTIALS`，解决办法：
  ```bash
  git config --global http.sslBackend openssl
  ```
- Git Credential Manager 在受限沙箱下会直接崩溃（退出码 `0xE0434352`），**认证环节需要完整权限**（danger-full-access）。
- Git 可能不在 PATH 中，常见位置：`C:\Program Files\Git\cmd\git.exe`。
- 本地代理（如 Clash Verge，端口 7897）访问 GitHub 可能失败：此时**让 Git 走直连**，不要配 `http.proxy`。
- 网络不稳时 `git push` 会报 `Connection was reset`，这是暂时的，重试若干次通常能成功。

### 禁止事项

- **不要执行 `git push --force`**，除非用户明确要求。
- **不要提交 `.env`、密钥、密码、token**。
- **不要改写已有提交历史**（`rebase`、`filter-branch`、`commit --amend` 等），除非用户明确要求。

### 验收标准

- `git log --format="%ae"` 输出的邮箱**全部**是 noreply 地址。
- `git status -sb` 显示 `## main...origin/main`，无 ahead / behind。
- `git ls-remote origin` 的 `main` SHA 与本地 `HEAD` 一致。

## 注意

- 邮箱使用 GitHub 的 noreply 地址，不会暴露真实邮箱。
- `pull` / `push` 是 Git 自身的命令，**与 VSCode 无关**；VSCode 只是可选的可视化外壳。
- `.gitignore` 已排除 `.env`、`*.pem`、`*.key` 等敏感文件，**不要把密码或密钥提交进仓库**（公开仓库任何人都能看到，即使之后删除，历史里仍在）。

## 许可证

尚未指定。如需开源，可在此处添加 LICENSE 文件。
