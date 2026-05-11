# Chatjoy 2.0 正式环境部署指南

## 📋 前置条件

```bash
# 检查 Docker 版本（需要 ≥ 24.0）
docker --version

# 检查 Docker Compose 版本（需要 ≥ 2.20）
docker compose version

# 检查磁盘空间（/data 需要至少 50GB）
df -h /data
```

---

## 📦 需要准备的文件

部署前，从开发机获取以下文件到服务器 `/data/chatjoy/`：

```
chatjoy-2.0.tar.gz       (398MB 镜像包)
docker-compose.yml       (容器编排配置)
.env                     (环境变量配置)
llm_service.py           (应用代码修复版)
characters/              (角色配置目录，包含所有 *.json)
```

---

## 🚀 部署步骤

### 第一步：创建部署目录

```bash
mkdir -p /data/chatjoy/{data,logs,user_profiles}
cd /data/chatjoy
```

### 第二步：上传文件

从开发机将以下文件传到 `/data/chatjoy/`：

```bash
# 在开发机执行（或用 SFTP 上传）
scp chatjoy-2.0.tar.gz docker-compose.yml .env llm_service.py root@<服务器IP>:/data/chatjoy/
scp -r characters/ root@<服务器IP>:/data/chatjoy/
```

### 第三步：配置环境变量

编辑 `/data/chatjoy/.env`，确保以下内容存在：

```dotenv
CHAT_MODEL=relay-gemma4-remote
GROUP_CHAT_MODEL=relay-gemma4-remote
RELAY_GEMMA4_API_KEY=
HTTP_PROXY=
NO_PROXY=localhost,127.0.0.1,pgvector,redis
POSTGRES_PASSWORD=chatjoy2026
REDIS_DB=0
REDIS_KEY_PREFIX=asgf:
SESSION_TTL=86400
SESSION_CACHE_SIZE=100
SESSION_CACHE_TTL=300
```

### 第四步：加载 Docker 镜像

```bash
cd /data/chatjoy
docker load -i chatjoy-2.0.tar.gz

# 验证镜像加载成功
docker images | grep chatjoy
# 应输出：chatjoy  2.0  <image_id>  1.58GB
```

### 第五步：启动所有服务

```bash
cd /data/chatjoy
docker compose up -d

# 等待 45 秒让应用初始化
sleep 45
```

### 第六步：验证部署成功

```bash
# 检查容器状态（全部应为 healthy）
docker compose ps

# 健康检查（应返回 JSON）
curl http://localhost:9002/health/detailed

# 预期输出
# {"status":"healthy","timestamp":"...","components":{...}}
```

---

## 📍 访问应用

部署完成后，应用可访问：

```
http://<服务器IP>:9002
```

---

## 🛠️ 日常维护命令

```bash
cd /data/chatjoy

# 查看实时日志
docker compose logs -f app

# 查看最近 100 行日志
docker compose logs --tail=100 app

# 重启应用（保留数据）
docker compose restart app

# 停止所有服务（保留数据）
docker compose stop

# 启动所有服务
docker compose start

# 完全关闭（删除容器但保留数据卷）
docker compose down
```

---

## ⚠️ 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| 端口 9002 被占用 | 其他应用占用 | `netstat -tlnp \| grep 9002` 找出进程，修改 docker-compose.yml 中的端口 |
| 容器无法启动 | 磁盘空间不足 | `df -h /data` 检查，清理空间 |
| 容器反复重启 | 应用启动错误 | `docker logs chatjoy-app-1` 查看错误日志 |
| 无法访问应用 | 防火墙阻止 | `ufw allow 9002` 开放端口 |
| PostgreSQL 连接失败 | 容器健康检查失败 | `docker compose ps` 检查 pgvector 容器状态 |

---

## 📝 项目结构

```
/data/chatjoy/
├── chatjoy-2.0.tar.gz        # Docker 镜像压缩包
├── docker-compose.yml         # 容器编排配置
├── .env                       # 环境变量（不要上传 git）
├── llm_service.py             # 应用代码（覆盖镜像内版本）
├── characters/                # 角色配置（JSON 文件）
├── data/                      # 应用数据目录
│   └── groups/                # 群组数据持久化
├── logs/                      # 应用日志
└── user_profiles/             # 用户画像数据
```

---

## ✅ 部署检查清单

- [ ] Docker ≥ 24.0 已安装
- [ ] Docker Compose ≥ 2.20 已安装
- [ ] `/data/` 磁盘空间 ≥ 50GB
- [ ] 所有文件已上传到 `/data/chatjoy/`
- [ ] `.env` 文件已配置（密码已修改）
- [ ] `docker load` 成功（镜像已加载）
- [ ] `docker compose up -d` 成功
- [ ] 三个容器都显示 `healthy`
- [ ] `/health/detailed` 接口可访问
- [ ] 应用可在 `http://<ip>:9002` 访问

---

## 📞 技术支持

如遇问题，请提供：

1. `docker compose ps` 输出
2. `docker logs chatjoy-app-1 --tail=50` 的错误日志
3. `docker compose exec pgvector pg_isready -U postgres` 的输出
4. 执行失败时的完整错误信息
