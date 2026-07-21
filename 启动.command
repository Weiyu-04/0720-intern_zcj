#!/bin/bash
# ============================================================
#  一键启动「中城交智枢」本地开发环境（前端 + 后端）
#  用法：双击本文件即可。
#  停止：在弹出的终端窗口里按  Control + C ，或直接关闭窗口。
# ============================================================

# 让脚本能找到 uv / pnpm / node / make（双击运行时不会自动加载你的 shell 配置）
export PATH="$HOME/.local/bin:/opt/miniconda3/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# 进入项目目录（本脚本所在文件夹下的 MainAgent）
cd "$(dirname "$0")/MainAgent" || { echo "❌ 找不到 MainAgent 目录"; read -r; exit 1; }

# 加载 .env（模型 Key、OnlyOffice 密钥等）
set -a
[ -f .env ] && source .env
set +a

echo "========================================"
echo "   启动中城交智枢 · 本地开发环境"
echo "========================================"

# 先清理可能残留的旧进程，避免端口被占用
pkill -f "uvicorn app.gateway" 2>/dev/null
pkill -f "next dev" 2>/dev/null
sleep 1

echo "→ 启动后端 (:8001, 热重载) ..."
# 注意：项目路径含中文，且 uv run 会反复重装本地包 → 直接用 venv python 起，
# 并显式加 PYTHONPATH + 强制 UTF-8，绕开中文路径 .pth 解码坑。
( cd backend && \
  LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONIOENCODING=utf-8 PYTHONUTF8=1 PYTHONPATH=".:packages/harness" \
  .venv/bin/python -m uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001 --reload ) &
BACK_PID=$!

echo "→ 启动前端 (:3000) ..."
( cd frontend && pnpm dev ) &
FRONT_PID=$!

# 窗口关闭 / 按 Ctrl+C 时，同时停掉前后端
cleanup() {
  echo ""
  echo "正在停止前后端 ..."
  kill "$BACK_PID" "$FRONT_PID" 2>/dev/null
  pkill -f "uvicorn app.gateway" 2>/dev/null
  pkill -f "next dev" 2>/dev/null
  exit 0
}
trap cleanup INT TERM

echo ""
echo "✅ 正在启动，请等 30~60 秒（后端要加载库，第一次稍慢）"
echo "   然后浏览器打开：  http://localhost:3000"
echo ""
echo "   ⛔ 要停止：在本窗口按  Control + C ，或直接关闭本窗口"
echo "========================================"
echo ""

wait
