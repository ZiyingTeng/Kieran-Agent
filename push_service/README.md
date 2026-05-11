# 企业级推送架构 - Phase 1 实施完成

## 已实现功能

### 1. 核心模块 (push_service/)

```
push_service/
├── __init__.py           # 包入口
├── config.py             # 配置管理
├── models.py             # 数据模型
├── registry.py           # 连接注册表 (内存 + Redis)
├── device_manager.py     # 设备令牌管理
├── offline_queue.py      # 离线消息队列
├── push_service.py       # 统一推送服务
├── api.py                # REST API 路由
├── tasks.py              # Celery 异步任务
├── migrations.py         # 数据库迁移工具
├── test_push_service.py  # 测试脚本
└── providers/
    ├── __init__.py       # 提供商入口
    ├── base.py           # 提供商基类
    ├── web_push.py       # Web Push (VAPID)
    ├── fcm.py            # FCM 推送
    └── apns.py           # APNs 推送
```

### 2. 数据库表 (PostgreSQL)

- `device_tokens` - 设备令牌存储
- `offline_messages` - 离线消息队列
- `push_logs` - 推送日志
- `websocket_connections` - WebSocket 连接历史

### 3. API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/push/register` | POST | 注册设备令牌 |
| `/api/push/devices` | GET | 获取用户设备列表 |
| `/api/push/unregister` | DELETE | 注销设备 |
| `/api/push/send` | POST | 发送推送消息 |
| `/api/push/test` | POST | 测试推送 |
| `/api/push/offline/{user_id}` | GET | 获取离线消息 |
| `/api/push/offline/{user_id}` | DELETE | 清空离线消息 |
| `/api/push/stats` | GET | 获取统计信息 |
| `/api/push/health` | GET | 健康检查 |

### 4. 智能推送路由

```
send_to_user() 智能路由:
1. WebSocket (最快，如果在线)
2. 平台推送 (FCM/APNs/WebPush)
3. 离线队列 (兜底)
```

### 5. 与现有系统集成

- 已集成到 `app.py`
- 心跳调度器使用新的 `PushService`
- 支持原有 WebSocket 直连作为降级方案

## 环境变量配置

```bash
# .env 新增
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1

# FCM 配置 (可选)
FCM_CREDENTIALS=/path/to/firebase-service-account.json
FCM_API_KEY=your_api_key

# APNs 配置 (可选)
APNS_KEY_ID=your_key_id
APNS_TEAM_ID=your_team_id
APNS_KEY_PATH=/path/to/apns-key.p8
APNS_USE_SANDBOX=false

# Web Push 配置 (可选)
VAPID_PUBLIC_KEY=your_vapid_public_key
VAPID_PRIVATE_KEY=your_vapid_private_key
VAPID_SUBJECT=mailto:admin@example.com

# 功能开关
USE_REDIS_REGISTRY=false  # 默认关闭
ENABLE_FCM=true
ENABLE_APNS=true
ENABLE_WEB_PUSH=true
```

## 使用示例

### 注册设备

```bash
curl -X POST http://localhost:8001/api/push/register \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "expert_id": "1001",
    "platform": "web",
    "token": "device_token_here",
    "device_info": {"browser": "Chrome"}
  }'
```

### 发送推送

```bash
curl -X POST http://localhost:8001/api/push/send \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "expert_id": "1001",
    "title": "新消息",
    "body": "你好！",
    "message_type": "chat"
  }'
```

### Python 代码

```python
from push_service import get_push_service

push_service = await initialize_push_service()

# 发送消息
result = await push_service.send_to_user(
    user_id="user123",
    expert_id="1001",
    title="想念你～",
    body="好久不见，最近怎么样？",
    message_type="greeting"
)
```

## 后续阶段 (待实施)

- **Phase 3**: Web Push 推送 (Service Worker 集成)
- **Phase 4**: Redis 连接注册表替换内存存储
- **Phase 5**: FCM/APNs 移动端推送

## 测试

```bash
# 运行测试
python -m push_service.test_push_service

# 数据库迁移
python -m push_service.migrations --action migrate
python -m push_service.migrations --action status
```

## 可选依赖安装

```bash
# Web Push
pip install pywebpush

# FCM
pip install pyfcm

# APNs
pip install apns2

# Redis (用于连接注册表)
pip install aioredis
```
