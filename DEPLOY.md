# AgentScope Runtime — 正式服部署指南

> **推荐方案**：使用 Docker Compose 一键部署（见第一节），应用、Redis、PostgreSQL 全部容器化，无需手动管理 Python 环境和 Docker 依赖。
> 裸机部署方案保留在第二节，作为备用。

---

## 一、Docker Compose 部署（推荐）

### 1.1 前提要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Ubuntu 22.04（推荐） |
| Docker Engine | ≥ 24.0 |
| Docker Compose | ≥ 2.20（`docker compose` 子命令，非 `docker-compose`） |

### 1.2 解压项目

```bash
tar -xzf chatjoy-2.0.tar.gz
cd Chatjoy2.0
```

### 1.3 配置环境变量

在项目根目录创建 `.env` 文件（格式见第五节），Docker Compose 会自动读取。

需要额外在 `.env` 中加一行设置数据库密码（可自定义，默认 `mysecretpassword`）：

```dotenv
POSTGRES_PASSWORD=your_strong_password_here
```

> `POSTGRES_URL` 这一行在 Docker 模式下**无需填写**——Compose 会自动用服务名覆盖连接串。
> `REDIS_HOST` / `REDIS_PORT` 同理，Compose 会覆盖。

### 1.4 首次启动

```bash
# 构建应用镜像（首次约需 5–10 分钟，下载依赖）
docker compose build

# 后台启动所有服务
docker compose up -d
```

启动后验证：

```bash
# 查看各容器状态（app / redis / pgvector 均应为 healthy）
docker compose ps

# 应用健康检查
curl http://localhost:8001/health
```

### 1.5 日常运维

```bash
docker compose stop          # 停止（保留数据）
docker compose start         # 恢复
docker compose restart app   # 仅重启应用（不重启数据库）
docker compose down          # 停止并删除容器（数据卷保留）
docker compose down -v       # ⚠️ 删除容器 + 数据卷（数据清空，慎用）
```

查看日志：

```bash
docker compose logs -f app       # 应用实时日志
docker compose logs --tail=100 app  # 最近 100 行
# 应用日志也会写入宿主机 ./logs/ 目录
```

### 1.6 更新应用

```bash
# 解压新版本后重新构建并滚动重启
docker compose build app
docker compose up -d app     # 自动替换旧容器，数据卷不受影响
```

### 1.7 自定义 Worker 数量

```bash
GUNICORN_WORKERS=8 docker compose up -d app
```

或在 `.env` 中添加 `GUNICORN_WORKERS=8`。

---

## 二、裸机部署（备用方案）

### 前提要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Ubuntu 22.04（推荐） |
| Python | 3.10（严格要求，通过 Miniconda 管理） |
| Docker | 已安装并运行（用于启动 Redis / PostgreSQL） |

---

## 三、安装 Miniconda 并创建 Python 环境（裸机方案）

```bash
# 下载并安装 Miniconda（如已安装可跳过）
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh -b -p $HOME/miniconda3
source $HOME/miniconda3/etc/profile.d/conda.sh

# 创建专用 Python 3.10 环境（名称必须为 vllm-env，启动脚本依赖此名称）
conda create -n vllm-env python=3.10 -y
conda activate vllm-env

# 安装项目依赖（ext 包含 mem0、gunicorn 等生产依赖）
pip install -e ".[ext]"

# 额外安装数据库驱动（pyproject.toml 中未声明但运行时需要）
pip install asyncpg psycopg2-binary httpx python-dotenv
```

---

## 四、启动 Docker 服务（裸机方案）

项目依赖两个 Docker 容器，**必须在启动应用前运行**。

### 4.1 Redis

```bash
docker run -d \
  --name redis \
  --restart unless-stopped \
  -p 6379:6379 \
  -v redis_data:/data \
  redis:7-alpine \
  redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
```

### 4.2 PostgreSQL（带 pgvector 扩展）

```bash
docker run -d \
  --name pgvector \
  --restart unless-stopped \
  -p 5433:5432 \
  -v pgvector_data:/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=mysecretpassword \
  pgvector/pgvector:pg16
```

> **注意**：端口映射为 `5433:5432`（宿主机 5433 → 容器 5432），`.env` 中连接串需对应。

启动后验证：

```bash
docker exec redis redis-cli ping          # 应返回 PONG
docker exec pgvector pg_isready -U postgres  # 应返回 accepting connections
```

---

## 五、配置环境变量（两种方案通用）

在项目根目录创建 `.env` 文件，填入以下所有字段（向负责人索取实际值）：

```dotenv
# 模型选择 — 仅支持 relay-gemma4-remote（外网可用，无需国内 API）
CHAT_MODEL=relay-gemma4-remote
GROUP_CHAT_MODEL=relay-gemma4-remote

# API Keys
RELAY_GEMMA4_API_KEY=     # 中继 Gemma4（无需鉴权可留空）

# 代理（仅当部署环境需要走代理时配置）
HTTP_PROXY=
NO_PROXY=localhost,127.0.0.1,pgvector,redis

# PostgreSQL（对应上面 Docker 容器）
POSTGRES_URL=postgresql://postgres:mysecretpassword@localhost:5433/postgres

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_KEY_PREFIX=asgf:
SESSION_TTL=86400
SESSION_CACHE_SIZE=100
SESSION_CACHE_TTL=300
```

---

## 六、关于 DASHSCOPE_API_KEY 的多处用途

`DASHSCOPE_API_KEY` 是整个服务最关键的 Key，它同时被三个地方使用：

| 用途 | 模型 | 说明 |
|------|------|------|
| **主聊天模型** | `relay-gemma4-remote` | 角色对话核心 |
| **mem0 事实提取**（LTM 写入过滤器） | `relay-gemma4-remote` | 每轮对话后判断用户消息是否含个人信息，YES 才写入长期记忆 |
| **mem0 向量化**（LTM 相似度检索） | mem0 内置默认向量 | 将记忆转为向量存入 pgvector，检索时用于语义相似度排序 |

所有 LLM 调用均使用 `relay-gemma4-remote`，该模型为外网可用，无需国内 API key。

---

## 七、离线推送系统（框架已就绪，待接入）

推送服务代码位于 `push_service/`，框架完整，支持 **FCM（Android）、APNs（iOS）、Web Push（H5）** 三种通道，以及离线消息队列（7 天有效期，Redis 暂存）。

**当前状态**：服务已随主应用启动（`app.py` 中 `initialize_push_service()` 已被调用），API 路由也已挂载（`/push/*`），但三个推送通道均未配置，推送请求会静默失败。

### 启用 FCM（Android 推送）

在 Firebase 控制台下载服务账号 JSON，上传到服务器，然后在 `.env` 中填写：

```dotenv
FCM_CREDENTIALS=/path/to/firebase-service-account.json
ENABLE_FCM=true
```

### 启用 APNs（iOS 推送）

在 Apple Developer 后台生成 APNs Key（.p8 文件），填写：

```dotenv
APNS_KEY_ID=<10位Key ID>
APNS_TEAM_ID=<10位Team ID>
APNS_KEY_PATH=/path/to/AuthKey_XXXXXXXXXX.p8
APNS_USE_SANDBOX=false   # 正式环境为 false，测试环境为 true
ENABLE_APNS=true
```

### 启用 Web Push（H5 浏览器推送）

生成 VAPID 密钥对（一次性操作）：

```bash
python -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); print('pub:', v.public_key); print('pri:', v.private_key)"
```

填写到 `.env`：

```dotenv
VAPID_PUBLIC_KEY=<生成的公钥>
VAPID_PRIVATE_KEY=<生成的私钥>
VAPID_SUBJECT=mailto:admin@yourdomain.com
ENABLE_WEB_PUSH=true
```

### 客户端接入

客户端需调用以下接口注册设备 Token，服务端才能向该设备推送：

```
POST /push/devices/register
{
  "user_id": "用户ID",
  "device_token": "FCM/APNs Token 或 Web Push subscription JSON",
  "platform": "android" | "ios" | "web"
}
```

推送消息入口（供心跳系统和业务代码调用）：

```
POST /push/send
{
  "user_id": "用户ID",
  "title": "消息标题",
  "body": "消息内容",
  "data": {}   # 自定义透传数据
}
```

---

## 九、数据迁移（正式上线前）

> 此步骤将旧服务器的聊天历史和 mem0 记忆迁移到本机 PostgreSQL。
> 需要能访问旧服务器的 Milvus 服务。

在 `.env` 中补充旧服务器 Milvus 连接信息（向负责人索取）：

```dotenv
MILVUS_HOST=<旧服务器 IP>
MILVUS_PORT=19530
MILVUS_TOKEN=<如有>
```

**Phase 1：迁移聊天历史**

```bash
conda activate vllm-env
python scripts/migrate_milvus_to_local.py --phase chat
```

**Phase 2：mem0 事实回填**（耗时较长，可分批执行）

```bash
# 建议先小范围测试
python scripts/migrate_milvus_to_local.py --phase mem0 --start "2025-03-01T00:00:00"

# 确认无误后全量跑
python scripts/migrate_milvus_to_local.py --phase mem0
```

两个阶段均幂等，中断后重跑不会重复写入。

---

## 十、启动服务（裸机方案）

```bash
cd /path/to/Chatjoy2.0
./start_production.sh          # 启动（默认 4 个 worker，监听 0.0.0.0:8001）
./start_production.sh status   # 查看状态
./start_production.sh stop     # 停止
./start_production.sh restart  # 重启
```

启动前脚本会自动检查：`.env` 是否存在、Redis 是否运行、gunicorn 是否安装。

**自定义 worker 数量：**

```bash
GUNICORN_WORKERS=8 ./start_production.sh
```

**日志位置：**

```
logs/access.log   # HTTP 访问日志
logs/error.log    # 错误日志（含 worker crash 信息）
logs/app.log      # 应用业务日志（Python logger 输出）
```

---

## 十一、验证服务正常

```bash
# 健康检查（返回 200 即正常）
curl http://localhost:8001/health

# 查看进程
./start_production.sh status
```

---

## 十二、目录结构说明

```
Chatjoy2.0/
├── app.py                  # FastAPI 主入口
├── start_production.sh     # 生产启动脚本
├── gunicorn_config.py      # Gunicorn 配置（worker 数、超时、日志路径等）
├── .env                    # 环境变量（需手动创建，不随代码分发）
├── characters/             # 角色卡配置（JSON），运行时加载 （建议根据线上角色更新一下）
├── data/groups/            # 群组数据持久化
├── user_profiles/          # 用户画像 JSON (目前没启用该功能)
├── logs/                   # 日志目录（自动创建）
├── web/dist/               # 前端静态文件（实则不需要）
└── scripts/
    └── migrate_milvus_to_local.py  # 数据迁移脚本
```

---

## 十三、常见问题

**Q: 启动报 `conda 环境不存在: vllm-env`**
A: 执行第三节中的 `conda create -n vllm-env python=3.10 -y` 并安装依赖。

**Q: 启动报 `Redis is not running`**
A: 执行第四节中的 Redis docker run 命令，或 `docker start redis`（如容器已存在）。

**Q: 请求报错 `500 Internal Privoxy Error`**
A: 检查 `.env` 中 `HTTP_PROXY` 是否指向正确的 Privoxy 地址，或该机器上 Privoxy 是否运行。

**Q: 迁移脚本报 `could not connect to server` (Milvus)**
A: 确认旧服务器 Milvus 端口可访问：`nc -zv <MILVUS_HOST> 19530`。

**Q: mem0 回填报 `DataInspectionFailed`（内容违规）**
A: 正常现象，用户消息中有被 qwen-turbo 内容审核拦截的内容，脚本会自动跳过该批次继续执行，不影响整体迁移。
