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

## 注意

- 邮箱使用 GitHub 的 noreply 地址，不会暴露真实邮箱。
- `.gitignore` 已排除 `.env`、`*.pem`、`*.key` 等敏感文件，**不要把密码或密钥提交进仓库**（公开仓库任何人都能看到，即使之后删除，历史里仍在）。

## 许可证

尚未指定。如需开源，可在此处添加 LICENSE 文件。
