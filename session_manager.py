"""
Redis-backed stateless session manager.

Replaces the in-memory `users_sessions` dict with:
- Redis: session metadata + working memory (via AgentScope RedisMemory)
- Process-local LRU cache: Agent and Mem0LongTermMemory objects (rehydratable)

Design:
    Request → SessionManager.get_or_create_session()
                ├── Redis: metadata (created_at, last_activity)
                ├── RedisMemory: short-term chat history (per session)
                ├── LRU Cache hit? → return cached Agent
                └── LRU Cache miss → factory rebuilds Agent + Mem0 → cache it
"""

import os
import logging
import threading
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============= LRU 缓存 =============


class TTLLRUCache:
    """Thread-safe LRU cache with per-entry TTL."""

    def __init__(self, maxsize: int = 200, ttl_seconds: int = 3600):
        self._data: OrderedDict = OrderedDict()
        self._timestamps: Dict[str, datetime] = {}
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._data:
                return None
            ts = self._timestamps.get(key)
            if ts and (datetime.now() - ts).total_seconds() > self._ttl:
                self._data.pop(key, None)
                self._timestamps.pop(key, None)
                return None
            self._data.move_to_end(key)
            return self._data[key]

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
            self._data[key] = value
            self._timestamps[key] = datetime.now()
            while len(self._data) > self._maxsize:
                k, _ = self._data.popitem(last=False)
                self._timestamps.pop(k, None)

    def remove(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)
            self._timestamps.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._timestamps.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def items(self) -> list:
        with self._lock:
            return list(self._data.items())


# ============= 对话管理 =============


class SessionManager:
    """
    Stateless session manager backed by Redis.

    - Session metadata stored in Redis Hash
    - Working memory (short-term) stored via AgentScope RedisMemory
    - Agent & Mem0 objects cached in process-local LRU (rebuilt on miss)
    """

    # Redis key patterns (prefixed at runtime)
    META_KEY = "session:{user_id}:{expert_id}:{session_id}:meta"
    USER_EXPERTS_SET = "user:{user_id}:experts"
    EXPERT_SESSIONS_SET = "user:{user_id}:expert:{expert_id}:sessions"

    def __init__(
        self,
        redis_url: Optional[str] = None,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        key_prefix: str = "asgf:",
        session_ttl: int = 7200,
        cache_maxsize: int = 200,
        cache_ttl: int = 3600,
    ):
        import redis.asyncio as aioredis

        # Redis client for metadata
        if redis_url:
            self._redis = aioredis.from_url(redis_url, decode_responses=True)
            self._pool = aioredis.ConnectionPool.from_url(
                redis_url, decode_responses=True,
            )
        else:
            self._redis = aioredis.Redis(
                host=redis_host, port=redis_port, db=redis_db,
                password=redis_password, decode_responses=True,
            )
            self._pool = aioredis.ConnectionPool(
                host=redis_host, port=redis_port, db=redis_db,
                password=redis_password, decode_responses=True,
            )

        self._key_prefix = key_prefix
        self._session_ttl = session_ttl

        # Process-local caches
        self._session_cache = TTLLRUCache(
            maxsize=cache_maxsize, ttl_seconds=cache_ttl,
        )
        self._mem0_cache = TTLLRUCache(
            maxsize=max(cache_maxsize // 2, 50), ttl_seconds=cache_ttl * 2,
        )

        # Factory functions — registered by app.py via set_factories()
        self._create_agent_fn: Optional[Callable] = None
        self._create_mem0_fn: Optional[Callable] = None

        logger.info(
            f"✅ SessionManager 初始化 (prefix={key_prefix}, "
            f"session_ttl={session_ttl}s, cache_max={cache_maxsize})"
        )

    # ---- Factory registration ----

    def set_factories(
        self,
        create_agent_fn: Callable,
        create_mem0_fn: Callable,
    ) -> None:
        """Register factory functions for rebuilding Agent / Mem0."""
        self._create_agent_fn = create_agent_fn
        self._create_mem0_fn = create_mem0_fn

    # ---- Key helpers ----

    def _key(self, pattern: str, **kwargs) -> str:
        return self._key_prefix + pattern.format(**kwargs)

    # ---- RedisMemory factory ----

    def create_memory(
        self, user_id: str, expert_id: str, session_id: str,
    ):
        """Create a RedisMemory bound to the given session (shares pool)."""
        from agentscope.memory import RedisMemory

        return RedisMemory(
            session_id=f"{expert_id}:{session_id}",
            user_id=user_id,
            connection_pool=self._pool,
            key_prefix=f"{self._key_prefix}mem:",
            key_ttl=self._session_ttl,
        )

    # ---- Mem0 (long-term) cache ----

    def get_or_create_mem0(self, user_id: str, expert_id: str):
        """Get / rebuild Mem0LongTermMemory — cached per (user, expert)."""
        cache_key = f"{user_id}:{expert_id}"
        cached = self._mem0_cache.get(cache_key)
        if cached is not None:
            return cached

        if self._create_mem0_fn is None:
            raise RuntimeError(
                "Mem0 factory not set. Call set_factories() first.",
            )

        instance = self._create_mem0_fn(user_id, expert_id)
        self._mem0_cache.put(cache_key, instance)
        logger.info(f"🧠 Mem0 创建并缓存: {user_id}/{expert_id}")
        return instance

    # ============= Core: get_or_create_session =============

    async def get_or_create_session(
        self,
        user_id: str,
        expert_id: str,
        session_id: str,
    ) -> Dict:
        """Return a session dict {agent, memory, long_term_memory, ...}.

        On LRU cache hit the dict is returned directly (fast path).
        On miss: metadata is checked / created in Redis, Agent + Mem0 are
        rebuilt via registered factories, and the result is cached.
        """
        cache_key = f"{user_id}:{expert_id}:{session_id}"

        # --- fast path: process-local cache ---
        cached = self._session_cache.get(cache_key)
        if cached is not None:
            await self._touch_session(user_id, expert_id, session_id)
            return cached

        # --- slow path: rebuild from Redis + factories ---
        meta_key = self._key(
            self.META_KEY,
            user_id=user_id, expert_id=expert_id, session_id=session_id,
        )
        meta = await self._redis.hgetall(meta_key)

        now_iso = datetime.now().isoformat()
        if not meta:
            meta = {
                "user_id": user_id,
                "expert_id": expert_id,
                "session_id": session_id,
                "created_at": now_iso,
                "last_activity": now_iso,
            }
            pipe = self._redis.pipeline()
            await pipe.hset(meta_key, mapping=meta)
            await pipe.expire(meta_key, self._session_ttl)
            await pipe.sadd(
                self._key(self.USER_EXPERTS_SET, user_id=user_id), expert_id,
            )
            await pipe.sadd(
                self._key(
                    self.EXPERT_SESSIONS_SET,
                    user_id=user_id, expert_id=expert_id,
                ),
                session_id,
            )
            await pipe.execute()
            logger.info(f"📝 新会话: {user_id}/{expert_id}/{session_id}")
        else:
            await self._redis.expire(meta_key, self._session_ttl)

        # Build components
        memory = self.create_memory(user_id, expert_id, session_id)
        long_term_memory = self.get_or_create_mem0(user_id, expert_id)

        if not self._create_agent_fn:
            raise RuntimeError("Agent factory not set.")
        agent = self._create_agent_fn(
            user_id, expert_id, memory, long_term_memory,
        )

        session = {
            "agent": agent,
            "memory": memory,
            "long_term_memory": long_term_memory,
            "created_at": meta.get("created_at", now_iso),
            "last_activity": now_iso,
        }

        self._session_cache.put(cache_key, session)
        return session

    async def _touch_session(
        self, user_id: str, expert_id: str, session_id: str,
    ):
        meta_key = self._key(
            self.META_KEY,
            user_id=user_id, expert_id=expert_id, session_id=session_id,
        )
        pipe = self._redis.pipeline()
        await pipe.hset(meta_key, "last_activity", datetime.now().isoformat())
        await pipe.expire(meta_key, self._session_ttl)
        await pipe.execute()

    # ============= 删除 =============

    async def delete_sessions(self, user_id: str, expert_id: str):
        """Delete all sessions for a (user, expert) pair."""
        sessions_key = self._key(
            self.EXPERT_SESSIONS_SET,
            user_id=user_id, expert_id=expert_id,
        )
        session_ids = await self._redis.smembers(sessions_key)

        for sid in session_ids:
            # Metadata
            meta_key = self._key(
                self.META_KEY,
                user_id=user_id, expert_id=expert_id, session_id=sid,
            )
            await self._redis.delete(meta_key)

            # Working memory (RedisMemory keys)
            mem = self.create_memory(user_id, expert_id, sid)
            try:
                await mem.clear()
                await mem.close()
            except Exception:
                pass

            # Evict from LRU
            self._session_cache.remove(f"{user_id}:{expert_id}:{sid}")

        # Index sets
        await self._redis.delete(sessions_key)
        await self._redis.srem(
            self._key(self.USER_EXPERTS_SET, user_id=user_id), expert_id,
        )
        self._mem0_cache.remove(f"{user_id}:{expert_id}")

        logger.info(
            f"🗑️ 已删除: {user_id}/{expert_id} ({len(session_ids)} sessions)"
        )

    # ============= 清理 =============

    async def cleanup_inactive_sessions(
        self, max_idle_seconds: int = 3600,
    ) -> int:
        """Evict inactive sessions (Redis TTL handles data; this cleans cache)."""
        cutoff = datetime.now() - timedelta(seconds=max_idle_seconds)
        count = 0

        cursor = 0
        prefix_pattern = f"{self._key_prefix}session:*:meta"
        while True:
            cursor, keys = await self._redis.scan(
                cursor, match=prefix_pattern, count=100,
            )
            for key in keys:
                meta = await self._redis.hgetall(key)
                try:
                    la = datetime.fromisoformat(meta.get("last_activity", ""))
                    if la < cutoff:
                        uid = meta.get("user_id", "")
                        eid = meta.get("expert_id", "")
                        sid = meta.get("session_id", "")
                        await self._redis.delete(key)
                        self._session_cache.remove(f"{uid}:{eid}:{sid}")
                        count += 1
                except (ValueError, TypeError):
                    pass
            if cursor == 0:
                break

        if count:
            logger.info(f"🧹 清理 {count} 个不活跃会话")
        return count

    # ============= 统计信息 =============

    async def get_stats(self) -> Dict:
        users: set = set()
        pairs: set = set()
        total = 0

        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor, match=f"{self._key_prefix}session:*:meta", count=100,
            )
            for key in keys:
                meta = await self._redis.hgetall(key)
                uid = meta.get("user_id", "")
                eid = meta.get("expert_id", "")
                users.add(uid)
                pairs.add(f"{uid}:{eid}")
                total += 1
            if cursor == 0:
                break

        # Process memory
        memory_mb = 0
        try:
            import psutil
            memory_mb = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
        except Exception:
            pass

        return {
            "total_users": len(users),
            "total_user_girlfriend_pairs": len(pairs),
            "total_sessions": total,
            "cache_sessions": len(self._session_cache),
            "cache_mem0": len(self._mem0_cache),
            "memory_mb": round(memory_mb, 1),
            "databases": [],
        }

    async def list_all_sessions(self) -> Dict:
        """Returns {user_id: {expert_id: [session_info, ...]}}"""
        result: Dict = {}

        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor, match=f"{self._key_prefix}session:*:meta", count=100,
            )
            for key in keys:
                meta = await self._redis.hgetall(key)
                uid = meta.get("user_id", "")
                eid = meta.get("expert_id", "")
                sid = meta.get("session_id", "")
                result.setdefault(uid, {}).setdefault(eid, []).append({
                    "session_id": sid,
                    "created_at": meta.get("created_at", ""),
                    "last_activity": meta.get("last_activity", ""),
                })
            if cursor == 0:
                break

        return result

    async def find_session_by_id(self, session_id: str) -> Optional[Dict]:
        """Scan Redis for a session with the given session_id."""
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor,
                match=f"{self._key_prefix}session:*:{session_id}:meta",
                count=100,
            )
            for key in keys:
                meta = await self._redis.hgetall(key)
                if meta and meta.get("session_id") == session_id:
                    return meta
            if cursor == 0:
                break
        return None

    async def has_sessions(self, user_id: str, expert_id: str) -> bool:
        sessions_key = self._key(
            self.EXPERT_SESSIONS_SET,
            user_id=user_id, expert_id=expert_id,
        )
        return (await self._redis.scard(sessions_key)) > 0

    # ============= 内存辅助方法 =============
    # Replace all direct memory.content access patterns with these async
    # methods. They work with both RedisMemory and InMemoryMemory.

    @staticmethod
    async def get_last_message(memory, role: Optional[str] = None):
        """Get the last message (optionally filtered by role)."""
        msgs = await memory.get_memory(prepend_summary=False)
        if role:
            msgs = [m for m in msgs if m.role == role]
        return msgs[-1] if msgs else None

    @staticmethod
    async def remove_last_message(
        memory, role: Optional[str] = None,
    ) -> bool:
        """Remove the last message. Returns True if a message was removed."""
        msgs = await memory.get_memory(prepend_summary=False)
        if role:
            targets = [m for m in msgs if m.role == role]
        else:
            targets = msgs
        if targets:
            await memory.delete([targets[-1].id])
            return True
        return False

    @staticmethod
    async def trim_memory(memory, max_size: int):
        """Keep only the most recent *max_size* messages."""
        size = await memory.size()
        if size > max_size:
            msgs = await memory.get_memory(prepend_summary=False)
            to_remove = msgs[: size - max_size]
            if to_remove:
                await memory.delete([m.id for m in to_remove])

    @staticmethod
    async def get_all_messages(
        memory, roles: Optional[List[str]] = None,
    ) -> list:
        """Get all messages, optionally filtered by role list."""
        msgs = await memory.get_memory(prepend_summary=False)
        if roles:
            msgs = [m for m in msgs if m.role in roles]
        return msgs

    @staticmethod
    async def get_memory_size(memory) -> int:
        return await memory.size()

    @staticmethod
    async def clear_memory(memory):
        await memory.clear()

    @staticmethod
    async def find_and_delete_message(
        memory, target_user_content: str,
    ) -> bool:
        """Find a user message containing *target_user_content* and delete
        it along with the immediately following assistant message.
        Returns True on success.
        """
        msgs = await memory.get_memory(prepend_summary=False)
        for i, msg in enumerate(msgs):
            if (
                msg.role == "user"
                and target_user_content in str(msg.content)
            ):
                ids_to_delete = [msg.id]
                if (
                    i + 1 < len(msgs)
                    and msgs[i + 1].role == "assistant"
                ):
                    ids_to_delete.append(msgs[i + 1].id)
                await memory.delete(ids_to_delete)
                return True
        return False

    @staticmethod
    async def find_and_update_reply(
        memory, target_user_content: str, new_reply: str,
    ) -> bool:
        """Find a user message containing *target_user_content*, then replace
        the immediately following assistant message with *new_reply*.
        Returns True on success.
        """
        from agentscope.message import Msg

        msgs = await memory.get_memory(prepend_summary=False)
        for i, msg in enumerate(msgs):
            if msg.role == "user" and target_user_content in str(msg.content):
                if i + 1 < len(msgs) and msgs[i + 1].role == "assistant":
                    old_msg = msgs[i + 1]
                    await memory.delete([old_msg.id])
                    new_msg = Msg(
                        name=old_msg.name, role="assistant",
                        content=new_reply,
                    )
                    await memory.add(new_msg)
                    return True
        return False

    # ============= 生命周期 =============

    async def close(self):
        self._session_cache.clear()
        self._mem0_cache.clear()
        try:
            await self._redis.aclose()
        except Exception:
            pass
        logger.info("✅ SessionManager 已关闭")


# ============= 全局单例 =============

_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get the global SessionManager singleton."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(
            redis_url=os.getenv("REDIS_URL"),
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_db=int(os.getenv("REDIS_DB", "0")),
            redis_password=os.getenv("REDIS_PASSWORD"),
            key_prefix=os.getenv("REDIS_KEY_PREFIX", "asgf:"),
            session_ttl=int(os.getenv("SESSION_TTL", "7200")),
            cache_maxsize=int(os.getenv("SESSION_CACHE_SIZE", "200")),
            cache_ttl=int(os.getenv("SESSION_CACHE_TTL", "3600")),
        )
    return _session_manager


def initialize_session_manager(**kwargs) -> SessionManager:
    """Create and register the global SessionManager with explicit params."""
    global _session_manager
    _session_manager = SessionManager(**kwargs)
    return _session_manager
