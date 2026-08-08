#!/bin/bash
# 安装桌面快捷方式，安装后可从应用菜单或桌面双击启动

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

DESKTOP_FILE="$SCRIPT_DIR/json-generator.desktop"
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

echo "================================"
echo "  安装桌面快捷方式"
echo "================================"
echo ""

# 生成 .desktop 文件（填入实际项目路径）
cat > "$DESKTOP_FILE" << DESKTOP_END
[Desktop Entry]
Type=Application
Name=JSON生成器
Name[en]=JSON Generator
Comment=动作数据集 JSON 生成器
Comment[en]=Motion Dataset JSON Generator
Icon=utilities-terminal
Terminal=true
Exec=bash "$PROJECT_DIR/scripts/linux/start.sh"
Path=$PROJECT_DIR
Categories=Development;Utility;
DESKTOP_END

echo "  已生成: $DESKTOP_FILE"

# 安装到应用菜单
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
cp "$DESKTOP_FILE" "$APPS_DIR/"
echo -e "  ${GREEN}v 已安装到应用菜单${NC}"

# 安装到桌面（可选）
DESKTOP_DIR="$HOME/Desktop"
if [ -d "$DESKTOP_DIR" ]; then
    cp "$DESKTOP_FILE" "$DESKTOP_DIR/"
    chmod +x "$DESKTOP_DIR/json-generator.desktop"
    echo -e "  ${GREEN}v 已添加到桌面${NC}"
else
    # 部分发行版使用中文桌面路径
    DESKTOP_DIR="$HOME/桌面"
    if [ -d "$DESKTOP_DIR" ]; then
        cp "$DESKTOP_FILE" "$DESKTOP_DIR/"
        chmod +x "$DESKTOP_DIR/json-generator.desktop"
        echo -e "  ${GREEN}v 已添加到桌面${NC}"
    fi
fi

echo ""
echo "================================"
echo -e "  ${GREEN}安装完成！${NC}"
echo ""
echo "  启动方式："
echo "  1. 应用菜单中搜索「JSON生成器」"
echo "  2. 双击桌面上的「JSON生成器」图标"
echo "  3. 终端运行: bash $PROJECT_DIR/scripts/linux/start.sh"
echo ""
echo -e "  ${CYAN}Tip: 首次双击 .desktop 文件可能需要右键 →「允许启动」${NC}"
echo ""
