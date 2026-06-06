# Git SSH 提交 GitHub 备忘

> 项目无 `.git` 目录（`git init` 后置），外部 push 走临时 clone → commit → push 模式。
> 本文档记录 SSH 认证踩过的坑和最终可行的配置。

## 环境

- **GitHub 账号**: Jim0818
- **仓库**: `github.com/Jim0818/DecoupleAI`
- **本地 SSH 密钥**: `~/.ssh/github_ed25519`（GitHub 已上传对应公钥）

## 踩坑记录

### 1. 默认 22 端口不通

```bash
ssh -T git@github.com
# → ssh: connect to host github.com port 22: Operation timed out
```

网络环境封锁了标准 SSH 22 端口。

### 2. 443 端口可用（ssh.github.com）

```bash
ssh -p 443 -T git@ssh.github.com
# → Hi Jim0818! You've successfully authenticated...
```

GitHub 提供了 `ssh.github.com` 的 HTTPS 443 端口作为 SSH 备用入口。

### 3. 必须显式指定密钥

即使 `~/.ssh/id_ed25519` 存在，`git@ssh.github.com` 也不会自动匹配 GitHub 专用密钥。需要 `-i` 显式指定：

```bash
ssh -i ~/.ssh/github_ed25519 -p 443 -T git@ssh.github.com
```

## 最终可用配置

### 克隆仓库

```bash
cd "$TMPDIR"
git clone git@github.com:Jim0818/DecoupleAI.git
```

克隆默认使用 `git@github.com`（22 端口），在 sandbox 内大概率超时。改 remote：

```bash
git remote set-url origin ssh://git@ssh.github.com:443/Jim0818/DecoupleAI.git
```

### Remote URL 格式

```
ssh://git@ssh.github.com:443/Jim0818/DecoupleAI.git
```

注意：`ssh.github.com` 的 URL 格式是 `ssh://git@ssh.github.com:443/用户/仓库.git`，不是 `git@ssh.github.com:用户/仓库.git`（后者端口号不是标准写法）。

### 推送

```bash
GIT_SSH_COMMAND="ssh -i ~/.ssh/github_ed25519 -o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes" \
  git push origin main
```

`GIT_SSH_COMMAND` 拆解：
| 参数 | 作用 |
|---|---|
| `-i ~/.ssh/github_ed25519` | 强制使用 GitHub 专用密钥 |
| `-o IdentitiesOnly=yes` | 不尝试其他密钥（避免 agent 干扰） |
| `-o StrictHostKeyChecking=accept-new` | 首次连接自动接受 host key |

### 完整脚本模板

```bash
# 1. 克隆
cd "$TMPDIR" && git clone https://github.com/Jim0818/DecoupleAI.git

# 2. 切到 SSH 443 端口
cd DecoupleAI
git remote set-url origin ssh://git@ssh.github.com:443/Jim0818/DecoupleAI.git

# 3. 提交
git config user.email "lj50005@163.com"
git config user.name "Jim0818"
git add -A
git commit -m "your commit message"

# 4. 推送
GIT_SSH_COMMAND="ssh -i ~/.ssh/github_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" \
  git push origin main
```

## 快速验证

推送前先测连通性：

```bash
ssh -i ~/.ssh/github_ed25519 -p 443 -T git@ssh.github.com
# 预期输出: Hi Jim0818! You've successfully authenticated, but GitHub does not provide shell access.
```

## 2026-06-06 实际执行记录

- 上传内容：`my-skills/skill-optimizer/`（4 文件）
- Commit: `3555334`，分支 `main`
- 成功推送至 `ssh.github.com:443`
