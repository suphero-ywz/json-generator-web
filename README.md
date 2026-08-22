# 动作数据集 JSON 生成器

为**光学动作捕捉数据采集**服务的训练数据集生成工具。批量生成符合规范的动作指令 JSON 数据，涵盖 **16 个动作类别**，支持 **LLM 智能生成**（DeepSeek 云端 / Ollama 本地大模型）与 **要素池规则组合** 两种模式，内置三层校验、去重池、历史记录与批量导出。

> 零配置即可使用：双击启动脚本后，默认以「要素池模式」运行，无需 API Key、无需部署任何模型。

---

## 目录

- [功能特性](#功能特性)
- [技术架构](#技术架构)
- [快速开始](#快速开始)
- [生成模式说明](#生成模式说明)
- [本地大模型部署与接入（Ollama）](#本地大模型部署与接入ollama)
- [DeepSeek 云端接入](#deepseek-云端接入)
- [环境变量参考](#环境变量参考)
- [API 接口文档](#api-接口文档)
- [数据格式规范](#数据格式规范)
- [项目结构](#项目结构)
- [打包与发布](#打包与发布)
- [常见问题](#常见问题-faq)
- [License](#license)

---

## 功能特性

| 特性 | 说明 |
|------|------|
| 双生成模式 | LLM 智能生成 / 要素池规则组合（自动兜底切换） |
| 双 LLM 后端 | DeepSeek 云端 API、Ollama 本地大模型（可并存、自动切换、手动指定） |
| 16 个动作类别 | 站立、行走、跑步、跳跃、下蹲、特技、舞蹈、爬行、单膝跪地、互动、挪动物品、后退、侧移、踏步、上肢动作(比心)、其他 |
| 三层数据校验 | 格式校验 → 内容合法性校验（物理可行、安全伦理、情绪-速度一致）→ 去重校验 |
| 批量生成 | 单次最多 50,000 条 / 文件；批量最多 50 个文件，ZIP 打包下载 |
| 去重池 | 历史 + 导入数据统一去重，避免重复动作 |
| 历史记录 | 生成记录持久化，支持一键重新生成 |
| 任务控制 | 随时取消生成、页面断连自动取消、实时进度条 |
| 数据导入 | 导入已有 JSON，query 自动写入去重池 |

## 技术架构

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | Vue 3 + Vite | SPA 单页应用：可视化配置、生成、预览、下载（端口 5173） |
| 后端 | Python FastAPI | RESTful API：生成调度、数据校验、持久化（端口 8000） |
| 数据库 | SQLite (aiosqlite) | 本地轻量数据库，WAL 模式，存去重池、历史记录 |
| LLM | DeepSeek API / Ollama | OpenAI 兼容接口 + Ollama 原生 `/api/chat`（Qwen3 关闭思维链加速） |

## 快速开始

### 环境要求

- **Python 3.10+**
- **Node.js 18+**
- （可选）Ollama + Qwen3 模型，或 DeepSeek API Key —— 不配置也可使用要素池模式

### Windows 一键启动

```bat
:: 首次使用：安装依赖（自动检测并引导安装 Python / Node.js）
scripts\windows\setup.bat

:: 启动项目（自动拉起后端 + 前端，并打开浏览器）
scripts\windows\start.bat
```

### Linux 一键启动

```bash
chmod +x scripts/linux/setup.sh scripts/linux/start.sh
bash scripts/linux/setup.sh   # 首次运行：安装依赖
bash scripts/linux/start.sh   # 启动前后端服务
```

可选：`bash scripts/linux/install-desktop.sh` 安装桌面快捷方式，之后可从应用菜单双击「JSON生成器」启动。

### 手动启动

```bash
# 后端（端口 8000）
cd backend
pip install -r requirements.txt
python main.py

# 前端（端口 5173，另开终端）
cd frontend
npm install
npm run dev
```

### 访问应用

打开浏览器访问 **http://localhost:5173**

- 后端 API 文档（Swagger UI）：**http://localhost:8000/docs**

## 生成模式说明

| 模式 | 说明 | 配置要求 |
|------|------|----------|
| **要素池模式** | 从预定义的要素池（动作、身体部位、情绪、幅度、速度）随机组合生成，零成本 | 无 |
| **LLM 模式** | 调用大模型创造全新、不模板化的动作数据，质量更高 | DeepSeek Key 或 Ollama 本地模型 |

前端页面可直接选择模式；请求中 `mode` 传 `auto` 时，后端自动判断：LLM 可用走 LLM，否则降级要素池。

## 本地大模型部署与接入（Ollama）

无需联网、无需 API Key、数据不出本机。使用 [Qwen3](https://qwenlm.github.io/)（qwen3:8b）实测单条生成约 2~5 秒（CPU），质量接近云端模型，适合频繁、大批量生成。

### 1. 安装 Ollama

从官网下载 Windows 安装包：**https://ollama.com/download/windows**

安装完成后验证：

```bash
ollama --version
```

> Ollama 安装后默认以系统服务方式常驻后台，监听 `http://127.0.0.1:11434`，无需手动启动。若服务未运行，可运行 `ollama serve` 或在开始菜单启动 "Ollama" 应用。

### 2. 拉取模型

```bash
# 推荐（8B，质量/速度均衡，CPU 可跑）
ollama pull qwen3:8b

# 低配机器可选（4B，更快但质量略低）
ollama pull qwen3:4b
```

查看已安装模型：`ollama list`

### 3. 配置 backend/.env

在 `backend/` 目录下创建 `.env` 文件（可参考 `.env.example`），写入：

```ini
# ===== Ollama 本地（不消耗 API token）=====
OLLAMA_API_BASE=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:8b
```

> `OLLAMA_API_BASE` 写 `http://127.0.0.1:11434` 或 `http://127.0.0.1:11434/v1` 均可，后端会自动适配。
> 修改 `.env` 后需重启后端服务生效。

### 4. 验证接入

```bash
curl http://127.0.0.1:11434/api/tags
```

返回含 `qwen3:8b` 的模型列表即 Ollama 就绪。然后启动项目（`start.bat`），页面右上角后端状态应显示 **Ollama 在线**；或在浏览器打开：

```
http://localhost:8000/api/status
```

响应中 `providers` 数组内 `id: "ollama"` 的 `online: true` 即接入成功。

### 5. 生成时指定使用 Ollama

- 页面：生成模式选「LLM 模式」，大模型后端选「Ollama」
- API：`provider` 参数传 `ollama`

> **后端优先级**：`auto` 模式下 Ollama 优先于 DeepSeek（本地免费优先）。两个后端可并存，一个离线时自动切换另一个。

### GPU / CPU 说明（Windows）

| 场景 | 做法 |
|------|------|
| NVIDIA 显卡（驱动 ≥ 595.97） | 默认即 GPU 推理，`ollama run qwen3:8b` 应显示 "partial GPU" 或全 GPU 加载 |
| 无独显 / 驱动较旧 | 纯 CPU 推理，速度可用（Qwen3-8B 约 5~10 token/s） |
| GPU 推理崩溃（`0xc0000409`） | 已知 Ollama CUDA 层问题，二选一：① 降级 Ollama 至 **0.30.0**；② 以 CPU 模式运行：启动 Ollama 前设置环境变量 `CUDA_VISIBLE_DEVICES=-1` |

项目内置了 CPU 模式启动脚本：

```bat
:: CPU 模式启动 Ollama（设置 CUDA_VISIBLE_DEVICES=-1，绕开 CUDA 崩溃）
scripts\windows\start-ollama-cpu.bat
```

```bash
# Linux / 临时使用：手动以 CPU 模式启动
CUDA_VISIBLE_DEVICES=-1 ollama serve
```

> 本仓库内的 `start-ollama-cpu.bat` 随驱动修复已默认走 GPU 模式；若你的显卡驱动较旧遇到 CUDA 崩溃，按上表第 3 行处理。

## DeepSeek 云端接入

### 1. 获取 API Key

前往 **https://platform.deepseek.com** 注册并创建 API Key。

### 2. 配置 backend/.env

```ini
# ===== DeepSeek 云端 =====
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

可选自定义项（有默认值，一般无需配置）：

```ini
DEEPSEEK_API_BASE=https://api.deepseek.com/v1   # 默认值
DEEPSEEK_MODEL=deepseek-chat                    # 默认值
```

### 3. 验证与使用

启动项目后 `http://localhost:8000/api/status` 中 `id: "deepseek"` 的 `online` 应为 `true`；页面「大模型」下拉选择 **DeepSeek** 即可。API 调用时 `provider` 传 `deepseek`。

## 环境变量参考

所有配置都在 `backend/.env`（不存在则创建），修改后重启后端生效：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_API_KEY` | 空 | DeepSeek API Key（云端 LLM 模式必填） |
| `DEEPSEEK_API_BASE` | `https://api.deepseek.com/v1` | DeepSeek 接口地址 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | DeepSeek 模型名 |
| `OLLAMA_API_BASE` | 空 | Ollama 服务地址（本地 LLM 模式必填），如 `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | `qwen3:8b` | Ollama 模型名 |
| `GEN_CONCURRENCY` | `12` | DeepSeek 并发请求数 |
| `GEN_OLLAMA_CONCURRENCY` | `2` | Ollama 并发请求数（本地推理实测 2 最优） |
| `GEN_BATCH_SIZE` | `5` | DeepSeek 每次调用生成条数 |
| `GEN_OLLAMA_BATCH_SIZE` | `3` | Ollama 每次调用生成条数 |
| `GEN_FILE_CONCURRENCY` | `3` | DeepSeek 批量任务文件级并发 |
| `GEN_OLLAMA_FILE_CONCURRENCY` | `1` | Ollama 批量任务文件级并发（保持串行） |
| `DS_MAX_TOKENS` | `2500` | DeepSeek 单次调用最大输出 token |
| `OLLAMA_MAX_TOKENS` | `2000` | Ollama 单次调用最大输出 token |
| `LLM_RECENT_QUERY_LIMIT` | `12` | 传给 LLM 的已生成 query 上限（防重复） |

## API 接口文档

### 通用说明

- **Base URL**：`http://127.0.0.1:8000`（生产部署可反向代理；前端开发环境经 Vite 代理 `/api` 到后端）
- **请求 / 响应格式**：JSON（`POST /api/import` 为 `multipart/form-data` 文件上传）
- **交互式文档**：`http://localhost:8000/docs`（Swagger UI，可直接调试）
- 生成类接口为**长耗时请求**，建议配合 `task_id` + 进度轮询 + 取消接口使用（见下方示例）

### 接口总览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/status` | 检查 LLM 可用性与各后端状态 |
| POST | `/api/generate` | 单次生成（单文件） |
| POST | `/api/generate/batch` | 批量生成（多文件） |
| POST | `/api/generate/cancel` | 取消进行中的生成任务 |
| GET | `/api/generate/progress` | 查询生成任务进度 |
| GET | `/api/history` | 历史记录列表 |
| DELETE | `/api/history/{id}` | 删除历史记录 |
| POST | `/api/history/{id}/regenerate` | 用历史参数重新生成 |
| POST | `/api/import` | 导入 JSON 到去重池 |
| GET | `/api/query-pool/stats` | 去重池统计 |

### 1. 检查状态 — `GET /api/status`

检查当前生成模式与各 LLM 后端（DeepSeek / Ollama）的配置与在线状态。

**响应示例**：

```json
{
  "llm_available": true,
  "mode": "llm",
  "model": "qwen3:8b",
  "providers": [
    { "id": "ollama", "label": "Ollama", "model": "qwen3:8b", "available": true, "online": true },
    { "id": "deepseek", "label": "DeepSeek", "model": "deepseek-chat", "available": true, "online": false }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `llm_available` | 任一 LLM 后端可用 |
| `mode` | 当前生效模式：`llm` / `element_pool` |
| `model` | 当前默认模型名 |
| `providers[]` | 各后端状态：`available` 为配置层可用，`online` 为实时探测可用 |

### 2. 单次生成 — `POST /api/generate`

**请求体**：

```json
{
  "total_count": 100,
  "categories": [
    { "name": "站立", "weight": 5 },
    { "name": "行走", "weight": 3 }
  ],
  "mode": "auto",
  "actor_id": "Skeleton0",
  "provider": "auto",
  "task_id": "my-task-001"
}
```

| 参数 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| `total_count` | int | ✅ | 1 ~ 50000 | 生成总条数 |
| `categories` | array | ✅ | 非空 | `{name, weight}`；`name` 为 16 个类别之一（见[功能特性](#功能特性)），`weight` 为正整数权重 |
| `mode` | string | - | `auto` / `llm` / `element_pool` | 生成模式；`auto` 按 LLM 可用性自动判断 |
| `actor_id` | string | - | - | actor_id 中 Skeleton 后缀，默认 `Skeleton0` |
| `provider` | string | - | `auto` / `deepseek` / `ollama` | LLM 后端选择，仅 `mode=llm` 时生效 |
| `task_id` | string | - | - | 任务 ID，用于查询进度 / 取消生成 |

**响应示例**：

```json
{
  "success": true,
  "mode": "llm",
  "data": [
    {
      "actor_id": "1_Skeleton0",
      "id": "0001",
      "query": "来，立正",
      "query_description": "[[立正]，[情绪:严肃]]",
      "text": "一个人双脚并拢，全身挺直，标准站姿保持稳定，最后回到站立姿态",
      "motion_description": "[[情绪:严肃]，[动作:立正]，[次数:1次]，[幅度:标准]，[速度:标准]]",
      "is_head": false,
      "voice_feedback": "立正完毕，随时待命！",
      "category": "站立",
      "intent": "单意图动作",
      "aug_text": ["立正", "一个人双脚并拢……", "……"]
    }
  ],
  "record_id": "8f2c1a9e-...",
  "stats": { "站立": 60, "行走": 40 },
  "error": null
}
```

| 字段 | 说明 |
|------|------|
| `success` | 是否成功；`false` 时 `mode` 为 `error`，`error` 含原因 |
| `data[]` | 生成的完整动作记录（字段见[数据格式规范](#数据格式规范)） |
| `record_id` | 历史记录 ID，可用于重新生成 |
| `stats` | 各类别生成条数统计 |

> 长耗时接口（50000 条可能耗时数分钟）：前端断开连接时后端自动取消任务；建议用 `task_id` + 进度接口跟踪。

### 3. 批量生成 — `POST /api/generate/batch`

**请求体**（参数同单次生成，条数限制不同）：

```json
{
  "total_count": 100,
  "file_count": 5,
  "categories": [ { "name": "舞蹈", "weight": 1 } ],
  "mode": "auto",
  "provider": "auto",
  "task_id": "batch-001"
}
```

| 参数 | 约束 | 说明 |
|------|------|------|
| `total_count` | 1 ~ 5000 | 每文件条数 |
| `file_count` | 1 ~ 50 | 文件个数（总条数 = 两者乘积） |

**响应示例**：

```json
{
  "success": true,
  "mode": "llm",
  "files": [
    { "record_id": "file-0001", "data": [...], "stats": { "舞蹈": 100 } },
    { "record_id": "file-0002", "data": [...], "stats": { "舞蹈": 100 } }
  ],
  "error": null
}
```

每个文件的 `data` 可直接保存为独立 JSON 文件，前端会打包为 ZIP 下载。

### 4. 取消生成 — `POST /api/generate/cancel`

**请求体**：

```json
{ "task_id": "my-task-001" }
```

`task_id` 传具体任务 ID 取消单个任务；**省略或传 `null` 取消所有进行中的任务**。

**响应**：

```json
{ "success": true }
```

```json
{ "success": false, "error": "没有进行中的生成任务" }
```

### 5. 查询进度 — `GET /api/generate/progress?task_id=xxx`

配合生成请求中的 `task_id` 使用（前端每 1.5 秒轮询）。

**响应示例**：

```json
{ "success": true, "completed": 60, "total": 100 }
```

批量任务额外返回：

```json
{ "success": true, "completed": 3, "total": 500, "files_done": 1, "files_total": 5 }
```

| 字段 | 说明 |
|------|------|
| `completed` / `total` | 已完成记录数 / 总记录数 |
| `files_done` / `files_total` | （批量）已完成文件数 / 总文件数 |

任务结束（成功或失败）后返回 `{ "success": false, "error": "任务不存在或已结束" }`，客户端应停止轮询。

### 6. 历史记录 — `GET /api/history`

**响应示例**：

```json
{
  "success": true,
  "data": [
    {
      "id": "8f2c1a9e-...",
      "type": "single",
      "count_per_file": 100,
      "file_count": 1,
      "total_records": 100,
      "categories_json": "[{\"name\":\"站立\",\"weight\":5}]",
      "created_at": "2026-08-22 12:00:00"
    }
  ]
}
```

`type` 为 `single`（单次）或 `batch`（批量）。

### 7. 删除历史 — `DELETE /api/history/{id}`

**响应**：`{ "success": true }`；记录不存在返回 404。

### 8. 重新生成 — `POST /api/history/{id}/regenerate`

用历史记录相同的类别与条数重新生成，参数通过 Query String 传：

```
POST /api/history/8f2c1a9e-...?mode=auto&provider=auto&task_id=regen-001
```

响应结构与 `/api/generate`（单次）或 `/api/generate/batch`（批量）一致。

### 9. 导入 JSON — `POST /api/import`

`multipart/form-data`，字段名 `file`，上传 JSON 文件。支持单对象或对象数组，每条含 `query` 字段的记录写入去重池（无 `query` 的跳过），避免后续生成重复。

**响应示例**：

```json
{
  "success": true,
  "imported_count": 95,
  "skipped_count": 5,
  "total_count": 100,
  "error": null
}
```

### 10. 去重池统计 — `GET /api/query-pool/stats`

**响应示例**：

```json
{
  "total": 1234,
  "by_category": { "站立": 300, "行走": 280 },
  "by_source": { "generated": 1100, "imported": 134 }
}
```

### curl 快速示例

```bash
# 检查后端状态
curl http://localhost:8000/api/status

# 单次生成 50 条「站立」动作
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"total_count": 50, "categories": [{"name": "站立", "weight": 1}]}'

# 带任务跟踪的生成流程（适合脚本/第三方系统接入）
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"total_count": 100, "categories": [{"name": "跑步", "weight": 1}], "task_id": "t001"}'

curl "http://localhost:8000/api/generate/progress?task_id=t001"   # 轮询进度

curl -X POST http://localhost:8000/api/generate/cancel \
  -H "Content-Type: application/json" \
  -d '{"task_id": "t001"}'                                        # 需要时取消
```

### 第三方系统接入注意事项

- 后端已开启 CORS（允许 `http://localhost:5173`），跨域前端直连需自行调整 `main.py` 中的 `allow_origins`
- 生成接口为长连接，客户端应设置合理超时（建议 ≥ 5 分钟），或改用 `task_id` + 轮询模式
- 服务地址固定为 `127.0.0.1:8000`，如需局域网/公网访问请使用反向代理（如 Nginx）并将 `host` 改为 `0.0.0.0`

## 数据格式规范

每条生成记录包含以下字段：

| 字段 | 说明 | 示例 |
|------|------|------|
| `actor_id` | 动作执行者标识 | `1_Skeleton0` |
| `id` | 序号（4 位补零） | `0001` |
| `query` | 口语化指令（5-20 字） | `来，立正` |
| `query_description` | 标签格式动作描述 | `[[立正]，[情绪:严肃]]` |
| `text` | 动作文本描述（以「一个人」开头） | `一个人双脚并拢，全身挺直……最后回到站立姿态` |
| `motion_description` | 动作标签（含情绪/动作/次数/幅度/速度） | `[[情绪:严肃]，[动作:立正]，[次数:1次]，[幅度:标准]，[速度:标准]]` |
| `is_head` | 是否仅头部动作 | `true` / `false` |
| `voice_feedback` | 语音反馈（13-22 字） | `立正完毕，随时待命！` |
| `category` | 动作类别 | `站立` |
| `intent` | 意图标签 | `单意图动作` |
| `aug_text` | 6 个文本变体（极简 → 详细） | `["立正", ..., "一个人面带严肃……"]` |

## 项目结构

```
json-generator-web/
├── backend/                  # FastAPI 后端
│   ├── main.py               # API 入口与路由
│   ├── models.py             # Pydantic 请求/响应模型
│   ├── generator.py          # 生成调度器（LLM / 要素池分发、并发控制）
│   ├── llm_client.py         # LLM 客户端（DeepSeek / Ollama 多后端）
│   ├── element_pool.py       # 要素池定义（16 类别关键词库）
│   ├── element_generator.py  # 要素池组合生成器
│   ├── validator.py          # 三层校验流水线
│   ├── database.py           # SQLite 数据库操作（去重池、历史）
│   ├── .env.example          # 环境变量配置示例（复制为 .env 使用）
│   └── requirements.txt
├── frontend/                 # Vue 3 前端
│   ├── src/api/index.js      # API 请求封装
│   ├── src/components/       # 可视化组件
│   └── vite.config.js        # Vite 配置（/api 代理到后端）
├── scripts/
│   ├── windows/              # Windows 启动/安装/打包脚本
│   └── linux/                # Linux 启动/安装脚本
└── README.md
```

## 打包与发布

内置打包脚本会生成一个**干净的发布 ZIP**（排除 node_modules、.git、运行数据、日志、密钥等），可直接作为 GitHub Releases 附件分发：

```bat
scripts\windows\package.bat     :: Windows
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\package.ps1   :: 或 PowerShell 版
```

生成的 `json-generator-web.zip` 位于项目上级目录。接收方解压后：

1. 运行 `scripts\windows\setup.bat` 安装依赖（自动检测 Python / Node.js）
2. 运行 `scripts\windows\start.bat` 启动
3. 可选：按 `backend\.env.example` 配置 LLM（DeepSeek / Ollama）

**发布到 GitHub 的建议流程**：

1. 本仓库源码推送到 GitHub（默认分支 `main`）
2. 在仓库页面创建 **Release**（打 tag 如 `v1.0.0`），附加打包脚本生成的 ZIP
3. README 即为仓库首页展示文档（本项目 README 已内置完整 API 与部署文档）

## 常见问题 FAQ

**Q: 不配置任何 Key 能用吗？**
能。默认要素池模式零配置可用；`mode=auto` 时 LLM 不可用会自动降级。

**Q: 页面显示「LLM 不可用」但已配置 DeepSeek Key？**
① 确认 `backend/.env` 在 `backend/` 目录下且格式正确（`DEEPSEEK_API_KEY=sk-...`）；② 重启后端；③ 打开 `http://localhost:8000/api/status` 查看 `providers[].online`。

**Q: Ollama 已安装但 `/api/status` 显示 offline？**
① `curl http://127.0.0.1:11434/api/tags` 确认 Ollama 服务在跑；② 确认 `.env` 已配置 `OLLAMA_API_BASE`；③ 确认已 `ollama pull` 对应模型。

**Q: Ollama GPU 推理崩溃（错误码 `0xc0000409`）？**
CUDA 层兼容问题：将 Ollama 降级到 0.30.0，或设置 `CUDA_VISIBLE_DEVICES=-1` 以 CPU 模式运行（见[本地大模型部署与接入](#本地大模型部署与接入ollama)）。

**Q: 生成速度慢？**
本地模型建议：Qwen3-4B 而非 8B；调大 `GEN_OLLAMA_CONCURRENCY`（CPU 建议保持 2）；GPU 需确认模型加载到显存（`ollama ps` 查看）。云端模型一般无需调优。

**Q: 生成到一半失败/被取消，为什么？**
任务被取消（前端按钮 / 接口调用 / 页面断连自动取消）、LLM 超时（本地 CPU 单条超过 600 秒）或 LLM 返回格式非法自动降级要素池。可查看 `backend/backend.log`。

**Q: 如何避免生成重复动作？**
去重池自动工作：已生成的 query 会传入 LLM 提示词禁止重复，要素池模式也有独立去重；历史记录不会重复消费。也可用 `/api/import` 导入已有数据。

## License

[MIT](LICENSE)
