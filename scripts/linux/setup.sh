#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo "================================"
echo "  动作数据集 JSON 生成器 - 安装"
echo "================================"
echo ""

ERROR_FLAG=0

# ---- 检测 Python ----
echo "[1/3] 检查 Python..."
PYTHON=""
for cmd in python3 python; do
    if command -v $cmd &>/dev/null; then
        PYTHON=$cmd
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "  ${RED}x Python 未安装${NC}"
    echo "    请通过包管理器安装："
    echo "    Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "    CentOS/RHEL:   sudo yum install python3 python3-pip"
    echo "    Arch:          sudo pacman -S python python-pip"
    echo "    或从 https://www.python.org/downloads/ 下载安装"
    ERROR_FLAG=1
else
    VER=$($PYTHON --version 2>&1)
    echo -e "  ${GREEN}v $VER${NC}"
fi

# ---- 检测 Node.js ----
echo ""
echo "[2/3] 检查 Node.js..."
if ! command -v node &>/dev/null; then
    echo -e "  ${RED}x Node.js 未安装${NC}"
    echo "    请通过包管理器安装："
    echo "    Ubuntu/Debian: sudo apt install nodejs npm"
    echo "    CentOS/RHEL:   sudo yum install nodejs npm"
    echo "    Arch:          sudo pacman -S nodejs npm"
    echo "    或从 https://nodejs.org/zh-cn/download/ 下载安装"
    ERROR_FLAG=1
else
    VER=$(node --version 2>&1)
    echo -e "  ${GREEN}v Node.js $VER${NC}"
fi

if ! command -v npm &>/dev/null; then
    echo -e "  ${RED}x npm 未安装${NC}"
    ERROR_FLAG=1
else
    VER=$(npm --version 2>&1)
    echo -e "  ${GREEN}v npm $VER${NC}"
fi

# ---- 检测 Ollama（可选） ----
echo ""
echo "[3/3] 检查 Ollama（可选）..."
if ! command -v ollama &>/dev/null; then
    echo -e "  ${YELLOW}- Ollama 未安装（将使用要素池模式）${NC}"
    echo "    如需 LLM 模式，请从 https://ollama.com/download/linux 下载安装"
else
    VER=$(ollama --version 2>&1)
    echo -e "  ${GREEN}v Ollama $VER${NC}"
    echo "   检查 qwen3:4b 模型..."
    if ollama list 2>/dev/null | grep -q "qwen3:4b"; then
        echo -e "  ${GREEN}v qwen3:4b 模型已就绪${NC}"
    else
        echo -e "  ${YELLOW}- qwen3:4b 模型未下载，运行: ollama pull qwen3:4b${NC}"
    fi
fi

if [ "$ERROR_FLAG" -eq 1 ]; then
    echo ""
    echo "================================"
    echo -e "  ${RED}请先安装缺失的环境后重新运行${NC}"
    echo "================================"
    exit 1
fi

# ---- 安装 Python 依赖 ----
echo ""
echo "安装 Python 依赖..."
cd "$PROJECT_DIR/backend"
$PYTHON -m pip install -r requirements.txt -q
if [ $? -ne 0 ]; then
    echo -e "  ${YELLOW}Python 依赖安装失败，正在重试...${NC}"
    $PYTHON -m pip install -r requirements.txt -q --default-timeout=60
    if [ $? -ne 0 ]; then
        echo -e "  ${RED}Python 依赖安装失败，请检查网络连接后重试${NC}"
        exit 1
    fi
fi
echo -e "  ${GREEN}v Python 依赖安装完成${NC}"

# ---- 安装 Node.js 依赖 ----
echo ""
echo "安装 Node.js 依赖..."
cd "$PROJECT_DIR/frontend"
npm install --silent 2>/dev/null || npm install
if [ $? -ne 0 ]; then
    echo -e "  ${RED}npm 依赖安装失败，请检查网络连接后重试${NC}"
    exit 1
fi
echo -e "  ${GREEN}v npm 依赖安装完成${NC}"

# ---- 创建 data 目录 ----
mkdir -p "$PROJECT_DIR/backend/data"

# ---- 完成 ----
echo ""
echo "================================"
echo -e "  ${GREEN}安装完成！${NC}请运行 start.sh 启动"
echo "================================"
echo ""
echo "  默认使用「要素池模式」，无需额外配置。"
echo "  如需启用 LLM 模式，请在 backend 目录下创建 .env 文件："
echo "    DEEPSEEK_API_KEY=你的API密钥"
echo "  注册地址：https://platform.deepseek.com"
echo ""
