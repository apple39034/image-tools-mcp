#!/usr/bin/env bash
# image-tools-mcp 一键安装脚本
# 用法：bash install.sh [--scope user|local]
#   --scope user   全局注册（默认，所有项目可用）
#   --scope local  仅当前项目注册

set -e

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCOPE="user"

# 解析参数
while [[ $# -gt 0 ]]; do
  case $1 in
    --scope) SCOPE="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

echo "==> image-tools-mcp 安装"
echo "    安装目录: $INSTALL_DIR"
echo "    注册范围: $SCOPE"
echo ""

# 检查 uv
if ! command -v uv &>/dev/null; then
  echo "错误：未找到 uv，请先安装：https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

# 检查 claude
if ! command -v claude &>/dev/null; then
  echo "错误：未找到 claude CLI，请先安装 Claude Code"
  exit 1
fi

# 安装依赖
echo "==> 安装 Python 依赖..."
cd "$INSTALL_DIR"
uv sync
echo "    依赖安装完成 ✓"

# 注册到 Claude Code
echo "==> 注册 MCP 服务到 Claude Code（scope: $SCOPE）..."

# 先移除旧的同名注册（忽略错误）
claude mcp remove image-tools -s "$SCOPE" 2>/dev/null || true

claude mcp add -s "$SCOPE" image-tools -- \
  uv run --project "$INSTALL_DIR" "$INSTALL_DIR/server.py"

echo "    注册完成 ✓"
echo ""
echo "==> 安装成功！重启 Claude Code 后运行 /mcp 确认 image-tools ✓ Connected"
