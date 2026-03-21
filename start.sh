#!/bin/bash
# JavSpider Stack - 一键启动脚本
# https://github.com/YOUR_USERNAME/javspider_stack

set -e
cd "$(dirname "$0")"

echo "=================================="
echo "  JavSpider Stack"
echo "=================================="
echo ""

# 检查 Python 版本
PYTHON=$(which python3 2>/dev/null || which python 2>/dev/null || echo "")
if [ -z "$PYTHON" ]; then
  echo "❌ 未找到 Python，请先安装 Python 3.11+"
  echo "   下载地址：https://www.python.org/downloads/"
  exit 1
fi

PYTHON_VER=$($PYTHON --version 2>&1)
echo "✅ Python: $PYTHON_VER"

# 虚拟环境（优先 .venv，其次 .venv_v2）
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ] && [ -d ".venv_v2" ]; then
  VENV_DIR=".venv_v2"
fi
if [ ! -d "$VENV_DIR" ]; then
  echo "🔧 创建虚拟环境 ..."
  $PYTHON -m venv "$VENV_DIR"
fi

# 激活虚拟环境
source "$VENV_DIR/bin/activate"

# 安装/更新依赖
echo "📦 安装依赖（首次较慢）..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "✅ 依赖安装完成"

# 初始化数据库（自动建表）
echo "🗄️  初始化数据库..."
python -c "from db import init_db; init_db(); print('✅ 数据库就绪')"

# 创建图片目录（如不存在）
mkdir -p static/covers static/avatars data

# 启动服务
PORT=${PORT:-8088}
echo ""
echo "🚀 启动服务："
echo "   本机访问 → http://localhost:$PORT"
echo "   局域网   → http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo "YOUR_IP"):$PORT"
echo ""
echo "   按 Ctrl+C 停止服务"
echo ""

uvicorn api.main:app --host 0.0.0.0 --port "$PORT" --reload --log-level info
