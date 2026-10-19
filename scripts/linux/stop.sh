#!/bin/bash
# 独立停服脚本：一键清理 JSON 生成器的所有进程
# 适用于：关闭终端后残留的孤儿服务、新旧实例端口冲突等场景

GREEN='\033[0;32m'
NC='\033[0m'

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

echo "================================"
echo "  停止 JSON 生成器服务"
echo "================================"
echo ""

# 1. 结束仍在运行的 start.sh（含持续监控循环；其自带清理逻辑会随之执行）
#    注意: 此匹配会覆盖命令行含 start.sh 的进程（如正在编辑该文件的 vim），
#    下方会先列出匹配结果再执行，请确认无误。
MATCHES=$(pgrep -af 'start\.sh' 2>/dev/null)
if [ -n "$MATCHES" ]; then
    echo "  结束残留的 start.sh 进程:"
    echo "$MATCHES" | sed 's/^/    /'
    pkill -f 'start\.sh' 2>/dev/null
    sleep 0.5
else
    echo "  无残留的 start.sh 进程"
fi

# 2. 按端口清理前后端（含历史遗留的孤儿子进程）
echo ""
echo "  清理端口占用..."
kill_port 8000
kill_port 5173
sleep 1

# 3. 验证结果
echo ""
if port_in_use 8000 || port_in_use 5173; then
    echo "  ! 仍有端口未释放，请手动执行:"
    echo "    ss -tlnp | grep -E ':8000|:5173'"
    echo "    kill -9 <PID>"
    exit 1
else
    echo -e "  ${GREEN}v 8000 / 5173 端口均已释放，服务已全部停止${NC}"
fi
echo ""
