#!/usr/bin/env bash
# scripts/sync-github.sh — sync DecoupleAI assets to GitHub with auto-updated README
#
# 用法:
#   1. 手动调用: bash scripts/sync-github.sh
#   2. AI agent 调用: 传入 --files "file1 file2 ..." --dirs "dir1 dir2 ..." --commit-msg "..."
#
# 做什么:
#   1. clone GitHub 仓库到 $TMPDIR
#   2. 复制指定文件/目录到仓库对应路径
#   3. 扫描 my-skills/，重建 README.md 中的 my-skills 索引段
#   4. 提交 + 推送
#
# 依赖: SSH key ~/.ssh/github_ed25519 已上传 GitHub
set -euo pipefail

REPO="ssh://git@ssh.github.com:443/Jim0818/DecoupleAI.git"
BRANCH="main"
SSH_KEY="$HOME/.ssh/github_ed25519"
GIT_SSH="ssh -i $SSH_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
TMPDIR="${TMPDIR:-/tmp/claude-501}"
WORKDIR=""

# --- 参数 ---
FILES=""          # 空格分隔的文件列表
DIRS=""           # 空格分隔的目录列表
COMMIT_MSG=""     # commit message
DRY_RUN=false     # 只打 log 不实际推送
SYNC_SKILLS_ONLY=false  # 仅重新生成 README skills 索引 + 推送

usage() {
  cat <<'HELP'
sync-github.sh — 同步资产到 GitHub 并自动更新 README

选项:
  --files "a b"      要复制的文件（相对于 DecoupleAI 项目根）
  --dirs "x y"       要复制的目录（相对于 DecoupleAI 项目根）
  --commit-msg "M"   commit 信息
  --skills-only      仅重建 my-skills 索引 + 推送（无文件复制）
  --dry-run          不实际推送
  -h, --help         此帮助

示例:
  bash scripts/sync-github.sh --files "skills/skill-optimizer/SKILL.md" --dirs "skills/skill-optimizer/references skills/skill-optimizer/scripts" --commit-msg "Update skill-optimizer"
  bash scripts/sync-github.sh --skills-only   # 仅刷新 README 索引
HELP
}

# --- 参数解析 ---
DAI="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
while [ $# -gt 0 ]; do
  case "$1" in
    --files)       FILES="$2"; shift 2 ;;
    --dirs)        DIRS="$2"; shift 2 ;;
    --commit-msg)  COMMIT_MSG="$2"; shift 2 ;;
    --skills-only) SYNC_SKILLS_ONLY=true; shift ;;
    --dry-run)     DRY_RUN=true; shift ;;
    -h|--help)     usage; exit 0 ;;
    *) echo "Unknown: $1"; usage; exit 1 ;;
  esac
done

# --- 前置检查 ---
if ! $SYNC_SKILLS_ONLY && [ -z "$FILES" ] && [ -z "$DIRS" ]; then
  echo "ERROR: 至少指定 --files 或 --dirs，或使用 --skills-only" >&2
  usage; exit 1
fi
[ -z "$COMMIT_MSG" ] && COMMIT_MSG="sync: update DecoupleAI assets"

# --- Clone ---
WORKDIR="$TMPDIR/DecoupleAI"
rm -rf "$WORKDIR" 2>/dev/null || true
echo "→ Cloning $REPO ..."
GIT_SSH_COMMAND="$GIT_SSH" git clone "$REPO" "$WORKDIR"

# --- 复制文件 ---
if ! $SYNC_SKILLS_ONLY; then
  echo "→ Copying assets..."
  for f in $FILES; do
    src="$DAI/$f"
    dst="$WORKDIR/$f"
    [ -f "$src" ] || { echo "  ⚠ 文件不存在: $src (跳过)"; continue; }
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    echo "  ✓ $f"
  done
  for d in $DIRS; do
    src="$DAI/$d"
    dst="$WORKDIR/$d"
    [ -d "$src" ] || { echo "  ⚠ 目录不存在: $src (跳过)"; continue; }
    mkdir -p "$(dirname "$dst")"
    cp -r "$src" "$dst"
    echo "  ✓ $d/"
  done
fi

# --- 重建 my-skills 索引 ---
# 委托 Python 脚本扫描 my-skills/ 并注入 README（处理 YAML frontmatter 比 bash 更稳健）
echo "→ Rebuilding my-skills index..."
python3 "$WORKDIR/scripts/inject-readme-index.py" "$WORKDIR/README.md"

# --- 写入 README 本身（首次，如果 README 只有占位符） ---
if [ "$(wc -c < "$WORKDIR/README.md")" -lt 50 ]; then
  echo "→ README.md 为空或占位，写入完整模板..."
  # 从 DecoupleAI 项目 docs/ 读取模板
  cp "$DAI/docs/github-readme-template.md" /dev/null 2>/dev/null || true
fi

# --- Commit & Push ---
echo "→ Committing..."
cd "$WORKDIR"
git config user.email "lj50005@163.com"
git config user.name "Jim0818"
git add -A

if git diff --cached --quiet; then
  echo "→ 无变更，跳过 commit"
else
  git commit -m "$COMMIT_MSG"
  echo "→ Pushing to $BRANCH..."
  if $DRY_RUN; then
    echo "[DRY RUN] 跳过 git push"
  else
    GIT_SSH_COMMAND="$GIT_SSH" git push origin "$BRANCH"
    echo "✓ 推送完成 → https://github.com/Jim0818/DecoupleAI"
  fi
fi
