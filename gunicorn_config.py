"""
Gunicorn configuration for Chatjoy multi-worker deployment.

Usage:
    gunicorn -c gunicorn_config.py app:app

Workers communicate through shared Redis (session state) +
Nginx ip_hash sticky sessions (WebSocket affinity).
"""

import multiprocessing
import os

# ============= Worker 配置 =============

# Worker 数量: 对于 I/O 密集型 AI 聊天服务，2-4 个 worker 通常足够
# 每个 worker 内部由 uvicorn 的 asyncio event loop 处理高并发
# 不要设太多 — 每个 worker 都有自己的 LRU cache，太多会浪费内存
workers = int(os.getenv("GUNICORN_WORKERS", 4))

# 使用 UvicornWorker 以支持 async FastAPI
worker_class = "uvicorn.workers.UvicornWorker"

# ============= 网络配置 =============

# 绑定地址 — 没有 Nginx 时用 0.0.0.0 直连
# 加了 Nginx 后改成 127.0.0.1:8001
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8001")

# ============= 超时配置 =============

# WebSocket 长连接需要更长的超时
# graceful_timeout: Worker 收到 SIGTERM 后的优雅关闭时间
# timeout: Worker 心跳超时（0 = 禁用，适合长连接场景）
timeout = int(os.getenv("GUNICORN_TIMEOUT", 120))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", 30))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", 5))

# ============= 进程管理 =============

# Worker 处理指定数量请求后自动重启（防内存泄漏）
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", 5000))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", 500))

# preload_app: 不预加载 — 每个 worker 需要独立的 event loop 和 Redis 连接
preload_app = False

# ============= 日志配置 =============

# 日志文件 — daemon 模式下必须写文件，否则看不到输出
_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_log_dir, exist_ok=True)

accesslog = os.getenv("GUNICORN_ACCESS_LOG", os.path.join(_log_dir, "access.log"))
errorlog = os.getenv("GUNICORN_ERROR_LOG", os.path.join(_log_dir, "error.log"))
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# Access log format: 包含响应时间和 worker PID
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s %(p)s'

# ============= Server hooks =============

def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Starting Chatjoy with %d workers", server.cfg.workers)


def post_worker_init(worker):
    """Called just after a worker has been initialized."""
    worker.log.info("Worker %s (PID %s) initialized", worker.age, worker.pid)


def worker_exit(server, worker):
    """Called when a worker exits."""
    server.log.info("Worker %s (PID %s) exiting", worker.age, worker.pid)
