"""数据库模块

提供两个连接池：
- get_shared_pg_pool(): psycopg2 ThreadedConnectionPool，供 mem0/pgvector 使用
- get_postgres_pool():  asyncpg Pool，供聊天历史和心跳持久化使用

以及聊天历史的读写函数。
"""

import logging
import os

logger = logging.getLogger(__name__)

# ============= PostgreSQL 启用标志 =============

USE_POSTGRES: bool = os.getenv("POSTGRES_URL") is not None

if USE_POSTGRES:
    logger.info("✅ 使用 mem0 + pgvector 向量存储（LLM 事实提取 + 高并发）")
else:
    logger.info("使用 mem0 + Chroma 向量存储")
    logger.info(
        "💡 提示: 设置 POSTGRES_URL 环境变量可启用 pgvector "
        "以获得更好的并发性能和记忆质量"
    )


# ============= psycopg2 连接池（mem0 / pgvector 专用）=============

_shared_pg_pool = None


def get_shared_pg_pool():
    """获取全局共享的 psycopg2 连接池（懒加载）。

    供 mem0 实例复用，避免每个用户×角色对各自创建独立连接池。

    :returns: ThreadedConnectionPool 或 None（未启用 PostgreSQL 时）
    """
    global _shared_pg_pool
    if _shared_pg_pool is None and USE_POSTGRES:
        import numpy as np
        import psycopg2.extensions

        class _AsVector:
            def __init__(self, vec):
                self._vec = vec

            def getquoted(self):
                return (
                    "'"
                    + "[" + ",".join(str(float(v)) for v in self._vec) + "]"
                    + "'::vector"
                ).encode()

        psycopg2.extensions.register_adapter(np.ndarray, _AsVector)

        from psycopg2.pool import ThreadedConnectionPool
        _shared_pg_pool = ThreadedConnectionPool(
            minconn=5,
            maxconn=50,
            dsn=os.getenv("POSTGRES_URL"),
        )
        logger.info("✅ 创建全局共享 psycopg2 连接池 (min=5, max=50)")
    return _shared_pg_pool


# ============= asyncpg 连接池（聊天历史 / 心跳持久化）=============

_postgres_pool = None


async def get_postgres_pool():
    """获取 asyncpg 连接池，并在首次调用时建表（懒加载）。

    :returns: asyncpg.Pool 或 None（未启用 PostgreSQL 时）
    """
    global _postgres_pool
    if _postgres_pool is None and USE_POSTGRES:
        import asyncpg
        postgres_url = os.getenv(
            "POSTGRES_URL",
            "postgresql://postgres:mysecretpassword@localhost:5433/postgres",
        )
        _postgres_pool = await asyncpg.create_pool(
            postgres_url,
            min_size=2,
            max_size=10,
            command_timeout=60,
        )
        async with _postgres_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expert_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    emotion TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_user_expert
                ON chat_history(user_id, expert_id)
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_heartbeats (
                    user_id TEXT NOT NULL,
                    expert_id TEXT NOT NULL,
                    last_active_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_greeting_time TIMESTAMP,
                    greeting_count INT DEFAULT 0,
                    PRIMARY KEY (user_id, expert_id)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS group_chat_history (
                    id SERIAL PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    sender_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_group_chat_group_ts
                ON group_chat_history(group_id, timestamp)
            """)
    return _postgres_pool


# ============= 聊天历史读写 =============

async def save_chat_history_to_db(
    user_id: str,
    expert_id: str,
    user_message: str,
    ai_response: str,
    emotion: str,
) -> None:
    """保存一轮对话到 PostgreSQL。

    :param user_id: 用户 ID
    :param expert_id: 角色 ID
    :param user_message: 用户消息
    :param ai_response: AI 回复
    :param emotion: 情绪标签（可为 None）
    """
    try:
        pool = await get_postgres_pool()
        if pool:
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO chat_history "
                    "(user_id, expert_id, role, content) "
                    "VALUES ($1, $2, $3, $4)",
                    user_id, expert_id, "user", user_message,
                )
                await conn.execute(
                    "INSERT INTO chat_history "
                    "(user_id, expert_id, role, content, emotion) "
                    "VALUES ($1, $2, $3, $4, $5)",
                    user_id, expert_id, "assistant", ai_response, emotion,
                )
                logger.info(f"💾 聊天历史已保存: {user_id}/{expert_id}")
    except Exception as e:
        logger.warning(f"保存聊天历史到数据库失败: {e}")


async def load_chat_history_from_db(
    user_id: str,
    expert_id: str,
    limit: int = 50,
) -> list:
    """从 PostgreSQL 加载聊天历史（按时间正序）。

    :param user_id: 用户 ID
    :param expert_id: 角色 ID
    :param limit: 最多返回条数
    :returns: 消息列表 [{role, content, emotion, timestamp}]
    """
    try:
        logger.info(f"🔍 尝试从PostgreSQL加载历史: {user_id}/{expert_id}")
        pool = await get_postgres_pool()
        if pool:
            logger.info("✅ PostgreSQL pool可用，开始查询...")
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT role, content, emotion, timestamp
                       FROM (
                           SELECT role, content, emotion, timestamp
                           FROM chat_history
                           WHERE user_id = $1 AND expert_id = $2
                           ORDER BY timestamp DESC
                           LIMIT $3
                       ) sub
                       ORDER BY timestamp ASC""",
                    user_id, expert_id, limit,
                )
            messages = [
                {
                    "role": r["role"],
                    "content": r["content"],
                    "emotion": r["emotion"],
                    "timestamp": (
                        r["timestamp"].isoformat()
                        if r["timestamp"] else None
                    ),
                }
                for r in rows
            ]
            logger.info(
                f"✅ 从PostgreSQL加载了 {len(messages)} 条历史记录"
            )
            return messages
        else:
            logger.warning("⚠️ PostgreSQL pool不可用")
        return []
    except Exception as e:
        logger.error(f"❌ 加载聊天历史失败: {e}")
        return []


async def save_group_message_to_db(
    group_id: str,
    sender_id: str,
    sender_name: str,
    role: str,
    content: str,
) -> None:
    """保存群聊单条消息到 group_chat_history 表。

    :param group_id: 群组 ID
    :param sender_id: 发送者 ID（user_id 或 expert_id）
    :param sender_name: 发送者名称
    :param role: 'user' 或 'assistant'
    :param content: 消息内容（原始文本，不含 sender_name 前缀）
    """
    try:
        pool = await get_postgres_pool()
        if not pool:
            return
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO group_chat_history "
                "(group_id, sender_id, sender_name, role, content) "
                "VALUES ($1, $2, $3, $4, $5)",
                group_id, sender_id, sender_name, role, content,
            )
    except Exception as e:
        logger.warning(f"保存群聊消息失败 ({group_id}): {e}")


async def load_group_history_from_db(
    group_id: str,
    limit: int = 30,
) -> list:
    """从 group_chat_history 加载最近 N 条消息（时间正序）。

    :param group_id: 群组 ID
    :param limit: 最多返回条数
    :returns: 消息列表 [{role, content, sender_name, sender_id}]
              content 为原始文本，不含 sender_name 前缀
    """
    try:
        pool = await get_postgres_pool()
        if not pool:
            return []
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT sender_id, sender_name, role, content
                   FROM (
                       SELECT sender_id, sender_name, role, content, timestamp
                       FROM group_chat_history
                       WHERE group_id = $1
                       ORDER BY timestamp DESC
                       LIMIT $2
                   ) sub
                   ORDER BY timestamp ASC""",
                group_id, limit,
            )
        return [
            {
                "role": r["role"],
                "content": r["content"],
                "sender_name": r["sender_name"],
                "sender_id": r["sender_id"],
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"加载群聊历史失败 ({group_id}): {e}")
        return []


async def delete_chat_message_from_db(
    user_id: str,
    expert_id: str,
    mes: str,
) -> int:
    """删除 chat_history 中匹配 mes 的最近一条用户消息及其紧随的 AI 回复。

    :param user_id: 用户 ID
    :param expert_id: 角色 ID
    :param mes: 用户消息内容（模糊匹配）
    :returns: 实际删除的行数
    """
    try:
        pool = await get_postgres_pool()
        if not pool:
            return 0
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, timestamp FROM chat_history "
                "WHERE user_id=$1 AND expert_id=$2 AND role='user' "
                "AND content LIKE $3 "
                "ORDER BY timestamp DESC LIMIT 1",
                user_id, expert_id, f"%{mes}%",
            )
            if not row:
                return 0
            ids_to_delete = [row["id"]]
            next_row = await conn.fetchrow(
                "SELECT id FROM chat_history "
                "WHERE user_id=$1 AND expert_id=$2 AND role='assistant' "
                "AND timestamp > $3 "
                "ORDER BY timestamp ASC LIMIT 1",
                user_id, expert_id, row["timestamp"],
            )
            if next_row:
                ids_to_delete.append(next_row["id"])
            await conn.execute(
                "DELETE FROM chat_history WHERE id = ANY($1)",
                ids_to_delete,
            )
            return len(ids_to_delete)
    except Exception as e:
        logger.warning(f"删除聊天记录失败: {e}")
        return 0


async def load_recent_chat_history(
    user_id: str,
    expert_id: str,
    limit: int = 10,
) -> list:
    """加载最近 N 条聊天记录（按时间正序返回）。

    :param user_id: 用户 ID
    :param expert_id: 角色 ID
    :param limit: 最多返回条数
    :returns: 消息列表 [{role, content}]
    """
    try:
        pool = await get_postgres_pool()
        if not pool:
            return []
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT role, content, emotion, timestamp
                   FROM chat_history
                   WHERE user_id = $1 AND expert_id = $2
                   ORDER BY timestamp DESC LIMIT $3""",
                user_id, expert_id, limit,
            )
        messages = [
            {"role": r["role"], "content": r["content"]} for r in rows
        ]
        messages.reverse()
        return messages
    except Exception as e:
        logger.error(f"加载最近聊天历史失败: {e}")
        return []
