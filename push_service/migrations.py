#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推送服务数据库迁移

创建必要的数据库表
"""

import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# SQL 迁移脚本
MIGRATION_SQL = """
-- ============================================
-- 推送服务数据库表
-- ============================================

-- 1. 设备令牌表
CREATE TABLE IF NOT EXISTS device_tokens (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    expert_id VARCHAR(255) NOT NULL,
    platform VARCHAR(20) NOT NULL,  -- 'ios', 'android', 'web'
    token TEXT NOT NULL,
    device_info JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP,
    UNIQUE(user_id, platform, token)
);

CREATE INDEX IF NOT EXISTS idx_device_tokens_user ON device_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_device_tokens_platform ON device_tokens(platform);
CREATE INDEX IF NOT EXISTS idx_device_tokens_active ON device_tokens(is_active) WHERE is_active = true;

-- 2. 离线消息队列表
CREATE TABLE IF NOT EXISTS offline_messages (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    expert_id VARCHAR(255) NOT NULL,
    message_type VARCHAR(50) NOT NULL DEFAULT 'chat',  -- 'chat', 'greeting', 'system'
    title VARCHAR(500),
    body TEXT NOT NULL,
    data JSONB DEFAULT '{}',
    priority INTEGER DEFAULT 5,
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'sent', 'failed', 'expired'
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    scheduled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP,
    expires_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP + INTERVAL '7 days'
);

CREATE INDEX IF NOT EXISTS idx_offline_messages_user_status ON offline_messages(user_id, status);
CREATE INDEX IF NOT EXISTS idx_offline_messages_priority ON offline_messages(priority, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_offline_messages_expires ON offline_messages(expires_at);

-- 3. 推送日志表
CREATE TABLE IF NOT EXISTS push_logs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    platform VARCHAR(20) NOT NULL,
    message_type VARCHAR(50),
    status VARCHAR(20) NOT NULL,  -- 'success', 'failed'
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_push_logs_user ON push_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_push_logs_created ON push_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_push_logs_status ON push_logs(status);

-- 4. WebSocket 连接历史表 (可选，用于分析)
CREATE TABLE IF NOT EXISTS websocket_connections (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    expert_id VARCHAR(255) NOT NULL,
    connection_id VARCHAR(100) NOT NULL,
    connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    disconnected_at TIMESTAMP,
    client_ip VARCHAR(50),
    user_agent TEXT,
    disconnect_reason VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_websocket_user ON websocket_connections(user_id);
CREATE INDEX IF NOT EXISTS idx_websocket_connected_at ON websocket_connections(connected_at);
"""


async def run_migration(postgres_url: str = None):
    """
    运行数据库迁移

    Args:
        postgres_url: PostgreSQL 连接字符串
    """
    if postgres_url is None:
        from push_service.config import get_config
        config = get_config()
        postgres_url = config.postgres_url

    logger.info(f"🚀 开始数据库迁移...")
    logger.info(f"📡 连接到: {postgres_url.split('@')[1] if '@' in postgres_url else postgres_url}")

    try:
        import asyncpg

        # 连接数据库
        conn = await asyncpg.connect(postgres_url)

        # 执行迁移
        await conn.execute(MIGRATION_SQL)

        logger.info("✅ 数据库迁移完成!")

        # 验证表是否创建成功
        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('device_tokens', 'offline_messages', 'push_logs', 'websocket_connections')
            ORDER BY table_name
        """)

        logger.info(f"📊 已创建的表:")
        for table in tables:
            logger.info(f"   - {table['table_name']}")

        # 关闭连接
        await conn.close()

    except Exception as e:
        logger.error(f"❌ 迁移失败: {e}")
        raise


async def rollback_migration(postgres_url: str = None):
    """
    回滚数据库迁移 (删除表)

    Args:
        postgres_url: PostgreSQL 连接字符串
    """
    if postgres_url is None:
        from push_service.config import get_config
        config = get_config()
        postgres_url = config.postgres_url

    logger.warning("⚠️ 开始回滚数据库迁移...")

    try:
        import asyncpg

        conn = await asyncpg.connect(postgres_url)

        # 删除表 (按依赖关系逆序)
        tables = [
            'websocket_connections',
            'push_logs',
            'offline_messages',
            'device_tokens'
        ]

        for table in tables:
            await conn.execute(f'DROP TABLE IF EXISTS {table} CASCADE')
            logger.info(f"🗑️ 已删除表: {table}")

        logger.warning("⚠️ 回滚完成!")

        await conn.close()

    except Exception as e:
        logger.error(f"❌ 回滚失败: {e}")
        raise


async def check_migration_status(postgres_url: str = None) -> dict:
    """
    检查迁移状态

    Args:
        postgres_url: PostgreSQL 连接字符串

    Returns:
        dict: 迁移状态
    """
    if postgres_url is None:
        from push_service.config import get_config
        config = get_config()
        postgres_url = config.postgres_url

    try:
        import asyncpg

        conn = await asyncpg.connect(postgres_url)

        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('device_tokens', 'offline_messages', 'push_logs', 'websocket_connections')
            ORDER BY table_name
        """)

        await conn.close()

        return {
            "migrated": len(tables) >= 3,  # 至少核心3个表
            "tables": [t['table_name'] for t in tables],
            "table_count": len(tables)
        }

    except Exception as e:
        logger.error(f"❌ 检查失败: {e}")
        return {
            "migrated": False,
            "error": str(e)
        }


def main():
    """命令行入口"""
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="推送服务数据库迁移工具")
    parser.add_argument("--action", choices=["migrate", "rollback", "status"], default="migrate",
                        help="操作类型")
    parser.add_argument("--url", help="PostgreSQL 连接字符串")

    args = parser.parse_args()

    if args.action == "migrate":
        asyncio.run(run_migration(args.url))
    elif args.action == "rollback":
        asyncio.run(rollback_migration(args.url))
    elif args.action == "status":
        status = asyncio.run(check_migration_status(args.url))
        print(f"迁移状态: {'✅ 已迁移' if status['migrated'] else '❌ 未迁移'}")
        print(f"表数量: {status.get('table_count', 0)}")
        print(f"已创建表: {', '.join(status.get('tables', []))}")


if __name__ == "__main__":
    main()
