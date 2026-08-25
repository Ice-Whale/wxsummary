#!/usr/bin/env bash
# wxsummary 一键安装入口（macOS）
#
# 用法：
#   bash install.sh
#
# 流程：预检 Homebrew / Python3 / git，然后调用 setup.py 完成
# chatlog-keeper 安装、微信密钥提取（active）、首次导出、生成 .env。

set -u

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================================"
echo "  wxsummary · 微信群聊日报一键安装（macOS）"
echo "========================================================"

# ── 1. 检查 Homebrew ──────────────────────────────────────
if ! command -v brew >/dev/null 2>&1; then
  echo "❌ 未检测到 Homebrew。"
  echo "   请先安装 Homebrew（粘贴到终端回车）："
  echo '   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  exit 1
fi
echo "✅ Homebrew 可用"

# ── 2. 检查 Python3 ───────────────────────────────────────
PYTHON=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "⚠️  未检测到 python3，正在通过 Homebrew 安装..."
  brew install python@3.11 || { echo "❌ 安装 python@3.11 失败"; exit 1; }
  PYTHON="$(command -v python3)"
fi
echo "✅ Python3：$PYTHON"

# ── 3. 检查 git ───────────────────────────────────────────
if ! command -v git >/dev/null 2>&1; then
  echo "⚠️  未检测到 git，正在通过 Homebrew 安装..."
  brew install git || { echo "❌ 安装 git 失败"; exit 1; }
fi
echo "✅ git 可用"

# ── 4. 调用 setup.py 完成剩余流程 ─────────────────────────
echo ""
cd "$PROJECT_DIR"
exec "$PYTHON" setup.py "$@"