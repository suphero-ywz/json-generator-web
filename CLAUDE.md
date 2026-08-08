## 项目概述

动作数据集 JSON 生成器 — 光学动作捕捉数据采集的训练数据集生成工具。支持 DeepSeek LLM 和要素池两种生成模式，涵盖 16 个动作类别。

## 技术栈

- 前端: Vue 3 + Vite (JavaScript)
- 后端: Python FastAPI + SQLite (aiosqlite)
- LLM: DeepSeek API (deepseek-chat)

## 常用命令

### 前端 (frontend/)

```bash
cd frontend
npm install          # 安装依赖
npm run dev          # 开发服务器 (端口 5173)
npm run build        # 生产构建
npm run preview      # 预览生产构建
```

### 后端 (backend/)

```bash
cd backend
pip install -r requirements.txt   # 安装依赖
python main.py                     # 启动 API 服务 (端口 8000)
```

### 一键启动

```bash
# Windows（双击）
scripts/windows/start.bat

# Linux（终端）
chmod +x scripts/linux/setup.sh scripts/linux/start.sh
bash scripts/linux/setup.sh   # 首次运行：安装依赖
bash scripts/linux/start.sh   # 启动前后端服务

# Linux（双击桌面图标）
bash scripts/linux/install-desktop.sh   # 安装桌面快捷方式（仅需一次）
# 之后可从应用菜单或桌面双击「JSON生成器」启动
```

## 项目结构

```
frontend/           # Vue 3 SPA — 可视化配置、生成、预览、下载
backend/            # FastAPI — RESTful API、生成调度、校验、持久化
scripts/            # 启动/打包脚本
```

## 注意事项

- LLM 模式需要在 `backend/.env` 中配置 `DEEPSEEK_API_KEY`
- 前端开发服务器通过 Vite proxy 将 `/api` 代理到后端 `127.0.0.1:8000`
- API 文档: `http://localhost:8000/docs`
