#!/usr/bin/env bash
# image-tools-mcp 更新脚本
# 拉取 GitHub 上最新代码并同步依赖。MCP 注册路径不变，无需重新注册。

set -e

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$INSTALL_DIR"

echo "==> 当前目录: $INSTALL_DIR"

# 检查是 git 仓库
if [ ! -d ".git" ]; then
  echo "错误：$INSTALL_DIR 不是 git 仓库，无法 git pull 更新"
  echo "请重新克隆：rm -rf $INSTALL_DIR && git clone https://github.com/apple39034/image-tools-mcp $INSTALL_DIR"
  exit 1
fi

# 检查未提交修改
if [ -n "$(git status --porcelain)" ]; then
  echo "警告：本地有未提交修改，git pull 可能冲突。继续？(y/N)"
  read -r ans
  [ "$ans" = "y" ] || [ "$ans" = "Y" ] || exit 1
fi

echo "==> git pull..."
git pull --ff-only
echo ""

echo "==> uv sync（同步依赖）..."
uv sync
echo ""

echo "==> 更新完成 ✓"
echo "    在 Claude Code 中执行 /mcp 重连 image-tools，或重启 Claude Code"
