#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 检测 Python 命令
PYTHON=""
for cmd in python3 python; do
    if command -v $cmd &>/dev/null; then
        PYTHON=$cmd
        break
    fi
done

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
GRAY='\033[0;90m'
NC='\033[0m'

BE_PID=""
FE_PID=""

cleanup() {
    echo ""
    echo -ne "  停止服务..."
    [ -n "$BE_PID" ] && kill "$BE_PID" 2>/dev/null
    [ -n "$FE_PID" ] && kill "$FE_PID" 2>/dev/null
    # 确保子进程也被终止
    jobs -p | xargs -r kill 2>/dev/null
    echo -e " ${GREEN}完成${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

check() {
    curl -sf --max-time 3 "$1" > /dev/null 2>&1 && return 0 || return 1
}

# ---- 首次运行检查 ----
if [ ! -d "$PROJECT_DIR/frontend/node_modules" ]; then
    echo "  首次运行 - 需要先安装依赖，请稍候..."
    bash "$SCRIPT_DIR/setup.sh"
    if [ $? -ne 0 ]; then
        echo "安装失败，退出"
        exit 1
    fi
fi

# ---- 创建 data 目录 ----
mkdir -p "$PROJECT_DIR/backend/data"

# ---- 清理旧进程 ----
echo ""
echo "  清理端口占用..."
fuser -k 8000/tcp 2>/dev/null || true
fuser -k 5173/tcp 2>/dev/null || true
sleep 1

# ---- 启动服务 ----
echo ""
echo -e "  ${GRAY}正在启动服务...${NC}"

cd "$PROJECT_DIR/backend"
$PYTHON main.py &>/dev/null &
BE_PID=$!

cd "$PROJECT_DIR/frontend"
npx vite --host &>/dev/null &
FE_PID=$!

# ---- 等待就绪 ----
echo -e "  ${GRAY}等待服务就绪...${NC}"
OK_BE=false; OK_FE=false; N=0

while ! $OK_BE || ! $OK_FE; do
    sleep 1; N=$((N + 1))

    if ! $OK_BE && check "http://localhost:8000/api/status"; then OK_BE=true; fi
    if ! $OK_FE && check "http://localhost:5173"; then OK_FE=true; fi

    BE_STR="..."; FE_STR="..."
    $OK_BE && BE_STR="OK"
    $OK_FE && FE_STR="OK"

    echo -ne "\r  Backend $BE_STR  |  Frontend $FE_STR  |  ${N}s"

    if [ $N -ge 30 ]; then
        echo ""
        echo "  启动超时，请确认已运行 setup.sh 安装依赖"
        read -p "  继续等待?(Y/N) " ans
        if [[ ! "$ans" =~ ^[yY] ]]; then exit 1; fi
        N=0
    fi
done

# ---- 就绪面板 ----
echo ""
echo ""
echo -e "  Backend   ${CYAN}http://localhost:8000/docs${NC}"
echo -e "  Frontend  ${CYAN}http://localhost:5173${NC}"
echo ""
echo -e "  ${GREEN}● 服务运行中  |  Ctrl+C 停止${NC}"

# ---- 持续监控 ----
while true; do
    sleep 5
    BE_STR="OK"; FE_STR="OK"
    BE_COL="$GRAY"; FE_COL="$GRAY"

    if ! check "http://localhost:8000/api/status"; then
        BE_STR="!!"; BE_COL="$RED"
    fi
    if ! check "http://localhost:5173"; then
        FE_STR="!!"; FE_COL="$RED"
    fi

    echo -ne "\r  Backend ${BE_COL}${BE_STR}${NC}  |  Frontend ${FE_COL}${FE_STR}${NC}"
done
