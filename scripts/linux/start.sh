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

# ---- 端口与进程组工具 ----
# 端口是否被占用（fuser → lsof → ss 三级回退）
port_in_use() {
    local port=$1
    if command -v fuser &>/dev/null; then
        fuser -s "${port}/tcp" 2>/dev/null
    elif command -v lsof &>/dev/null; then
        lsof -ti:"${port}" >/dev/null 2>&1
    else
        ss -tln 2>/dev/null | grep -q ":${port} "
    fi
}

# 强杀占用端口的残留进程（fuser → lsof 回退）
kill_port() {
    local port=$1
    if command -v fuser &>/dev/null; then
        fuser -k "${port}/tcp" 2>/dev/null
    elif command -v lsof &>/dev/null; then
        lsof -ti:"${port}" 2>/dev/null | xargs -r kill -9
    else
        echo "  警告: 未安装 fuser/lsof，无法按端口清理 ${port}" >&2
    fi
}

# 结束整个进程组（连带 uvicorn reload 子进程、vite/esbuild 子进程）
kill_group() {
    local pid=$1
    [ -z "$pid" ] && return
    kill -TERM -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
}

cleanup() {
    # 未启动过服务则无需清理（如 setup 失败提前退出）
    [ -z "$BE_PID$FE_PID" ] && return
    echo ""
    echo -ne "  停止服务..."
    kill_group "$BE_PID"
    kill_group "$FE_PID"
    jobs -p | xargs -r kill 2>/dev/null
    # 等待释放；仍未释放则强制清端口（含历史遗留的孤儿进程）
    sleep 1
    port_in_use 8000 && kill_port 8000
    port_in_use 5173 && kill_port 5173
    echo -e " ${GREEN}完成${NC}"
}

# Ctrl+C、kill 命令、关闭终端窗口（SIGHUP）都会触发清理
trap cleanup EXIT
trap 'exit 0' SIGINT SIGTERM SIGHUP

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
kill_port 8000
kill_port 5173
sleep 1

# ---- 启动服务 ----
echo ""
echo -e "  ${GRAY}正在启动服务...${NC}"

if ! command -v setsid &>/dev/null; then
    echo "  错误: 缺少 setsid（util-linux 包），无法启动"
    exit 1
fi

cd "$PROJECT_DIR/backend"
# setsid: 服务各自成为独立进程组，停止时可整组终止，避免子进程变孤儿
setsid $PYTHON main.py &>/dev/null &
BE_PID=$!

cd "$PROJECT_DIR/frontend"
# 直接调用 vite 本体（不经 npx 包装），保证 PID 即 vite 进程
setsid ./node_modules/.bin/vite --host &>/dev/null &
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
