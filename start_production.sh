#!/usr/bin/env bash
#
# Chatjoy 生产环境启动脚本
#
# 用法:
#   ./start_production.sh          # 默认 4 workers
#   GUNICORN_WORKERS=8 ./start_production.sh   # 自定义 worker 数
#   ./start_production.sh stop     # 停止服务
#   ./start_production.sh restart  # 重启服务
#   ./start_production.sh status   # 查看状态
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ============= Conda 环境 =============
# 直接使用 vllm-env 的 Python，不依赖 conda activate（避免 set -u 冲突）
CONDA_ENV="${CONDA_ENV:-vllm-env}"
VENV_BIN="${HOME}/miniconda3/envs/${CONDA_ENV}/bin"

if [ ! -x "${VENV_BIN}/python" ]; then
    echo "[ERROR] conda 环境不存在: ${CONDA_ENV} (${VENV_BIN}/python)"
    exit 1
fi

# 将 vllm-env/bin 放在 PATH 最前面
export PATH="${VENV_BIN}:${PATH}"

# PID 文件
PID_FILE="${SCRIPT_DIR}/gunicorn.pid"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ============= 前置检查 =============

check_redis() {
    if docker exec redis redis-cli ping &>/dev/null; then
        log_info "Redis: running"
        return 0
    fi
    log_error "Redis is not running! Start it with:"
    echo "  docker run -d --name redis --restart unless-stopped -p 6379:6379 \\"
    echo "    -v redis_data:/data redis:7-alpine redis-server --appendonly yes \\"
    echo "    --maxmemory 512mb --maxmemory-policy allkeys-lru"
    return 1
}

check_postgres() {
    if ss -tlnp 2>/dev/null | grep -q ':5433'; then
        log_info "PostgreSQL: running (port 5433)"
        return 0
    fi
    log_warn "PostgreSQL not detected on port 5433 (may not be required depending on config)"
    return 0
}

check_env() {
    if [ ! -f ".env" ]; then
        log_error ".env file not found!"
        return 1
    fi
    log_info ".env: found"
}

check_dependencies() {
    local gunicorn_bin
    gunicorn_bin=$(command -v gunicorn 2>/dev/null || echo "$HOME/.local/bin/gunicorn")
    if [ ! -x "$gunicorn_bin" ]; then
        log_error "gunicorn not found! Install with: pip install gunicorn"
        return 1
    fi
    log_info "gunicorn: $(${gunicorn_bin} --version 2>&1)"
}

# ============= 命令 =============

do_start() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        log_warn "Server is already running (PID $(cat "$PID_FILE"))"
        echo "  Use: $0 restart"
        return 1
    fi

    log_info "=== Pre-flight checks ==="
    check_env
    check_dependencies
    check_redis
    check_postgres

    # PATH 已在脚本开头设置为 vllm-env/bin 优先

    local workers="${GUNICORN_WORKERS:-4}"
    log_info "=== Starting Chatjoy ==="
    log_info "Workers: ${workers}"
    log_info "Bind: ${GUNICORN_BIND:-127.0.0.1:8001}"
    log_info "PID file: ${PID_FILE}"

    gunicorn -c gunicorn_config.py \
        --pid "$PID_FILE" \
        --daemon \
        app:app

    sleep 1
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        log_info "Server started successfully (PID $(cat "$PID_FILE"))"
        log_info "Logs: gunicorn writes to stdout/stderr by default"
        log_info "  To log to file: GUNICORN_ACCESS_LOG=/var/log/asgf/access.log GUNICORN_ERROR_LOG=/var/log/asgf/error.log $0"
    else
        log_error "Failed to start server. Check error logs."
        return 1
    fi
}

do_stop() {
    if [ ! -f "$PID_FILE" ]; then
        log_warn "PID file not found. Server may not be running."
        return 0
    fi

    local pid
    pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
        log_info "Stopping server (PID $pid) gracefully..."
        kill -SIGTERM "$pid"

        # 等待优雅关闭
        local waited=0
        while kill -0 "$pid" 2>/dev/null && [ $waited -lt 30 ]; do
            sleep 1
            waited=$((waited + 1))
        done

        if kill -0 "$pid" 2>/dev/null; then
            log_warn "Graceful shutdown timed out, sending SIGKILL..."
            kill -SIGKILL "$pid" 2>/dev/null || true
        fi
        log_info "Server stopped."
    else
        log_warn "Process $pid not running. Cleaning up PID file."
    fi
    rm -f "$PID_FILE"
}

do_restart() {
    do_stop
    sleep 1
    do_start
}

do_status() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        local pid
        pid=$(cat "$PID_FILE")
        log_info "Server is running (master PID $pid)"
        log_info "Worker processes:"
        ps --ppid "$pid" -o pid,pcpu,pmem,etime,comm 2>/dev/null || \
            pgrep -P "$pid" | xargs ps -o pid,pcpu,pmem,etime,comm -p 2>/dev/null || \
            log_warn "Could not list worker processes"
    else
        log_warn "Server is not running."
    fi

    echo ""
    check_redis
    check_postgres
}

do_reload() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        local pid
        pid=$(cat "$PID_FILE")
        log_info "Sending HUP to master (PID $pid) — graceful worker restart..."
        kill -HUP "$pid"
        log_info "Reload signal sent. Workers will restart one by one."
    else
        log_warn "Server is not running."
        return 1
    fi
}

# ============= 入口 =============

case "${1:-start}" in
    start)   do_start ;;
    stop)    do_stop ;;
    restart) do_restart ;;
    status)  do_status ;;
    reload)  do_reload ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|reload}"
        exit 1
        ;;
esac
