#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis 连接注册表

支持水平扩展的 WebSocket 连接管理
"""

import logging
import json
import asyncio
from typing import Dict, Optional, Set, Callable, Any
from datetime import datetime

from .config import get_config
from .models import ConnectionInfo, generate_connection_id

logger = logging.getLogger(__name__)

# 可选导入
try:
    import aioredis
    AIOREDIS_AVAILABLE = True
except ImportError:
    AIOREDIS_AVAILABLE = False
    logger.warning("⚠️ aioredis 未安装，Redis 连接注册表将不可用")



class ConnectionRegistry:
    """
    连接注册表基类
    """

    async def register_connection(
        self,
        user_id: str,
        expert_id: str,
        connection_id: str,
        websocket: Any = None,
        metadata: Dict = None
    ):
        """注册连接"""
        raise NotImplementedError

    async def unregister_connection(self, user_id: str, connection_id: str):
        """注销连接"""
        raise NotImplementedError

    async def get_connection(self, user_id: str) -> Optional[Any]:
        """获取用户连接"""
        raise NotImplementedError

    async def is_user_online(self, user_id: str) -> bool:
        """检查用户是否在线"""
        raise NotImplementedError

    async def broadcast_to_user(self, user_id: str, message: Dict) -> bool:
        """向用户广播消息"""
        raise NotImplementedError


class InMemoryConnectionRegistry(ConnectionRegistry):
    """
    内存连接注册表 (原有实现)

    用于单机部署和回滚方案
    """

    def __init__(self):
        """初始化内存注册表"""
        # 存储活跃的 WebSocket 连接
        self.active_websockets: Dict[str, Any] = {}
        # 用户到连接的映射
        self.user_to_connection: Dict[str, str] = {}
        # 连接到用户的映射
        self.connection_to_user: Dict[str, str] = {}
        # 用户到角色的映射
        self.user_expert_mapping: Dict[str, str] = {}

    async def register_connection(
        self,
        user_id: str,
        expert_id: str,
        connection_id: str,
        websocket: Any = None,
        metadata: Dict = None
    ):
        """注册连接"""
        if websocket:
            self.active_websockets[connection_id] = websocket
        self.user_to_connection[user_id] = connection_id
        self.connection_to_user[connection_id] = user_id
        self.user_expert_mapping[user_id] = expert_id

        logger.info(f"✅ 注册连接: {user_id} -> {connection_id}")

    async def unregister_connection(self, user_id: str, connection_id: str):
        """注销连接 — 只清理属于本连接的映射，防止误删新连接"""
        self.active_websockets.pop(connection_id, None)
        self.connection_to_user.pop(connection_id, None)
        # 只有当映射仍指向本连接时才删除
        if self.user_to_connection.get(user_id) == connection_id:
            self.user_to_connection.pop(user_id, None)
            self.user_expert_mapping.pop(user_id, None)

        logger.info(f"🗑️ 注销连接: {user_id} -> {connection_id}")

    async def get_connection(self, user_id: str) -> Optional[Any]:
        """获取用户连接"""
        connection_id = self.user_to_connection.get(user_id)
        if not connection_id:
            return None
        return self.active_websockets.get(connection_id)

    async def is_user_online(self, user_id: str) -> bool:
        """检查用户是否在线"""
        return user_id in self.user_to_connection

    async def broadcast_to_user(self, user_id: str, message: Dict) -> bool:
        """向用户广播消息"""
        websocket = await self.get_connection(user_id)
        if not websocket:
            return False

        try:
            await websocket.send_json(message)
            return True
        except Exception as e:
            logger.error(f"❌ WebSocket 推送失败: {e}")
            # 清理失效连接
            connection_id = self.user_to_connection.get(user_id)
            if connection_id:
                await self.unregister_connection(user_id, connection_id)
            return False

    def get_expert_id(self, user_id: str) -> Optional[str]:
        """获取用户对应的角色ID"""
        return self.user_expert_mapping.get(user_id)


class RedisConnectionRegistry(ConnectionRegistry):
    """
    Redis 连接注册表

    支持:
    1. 跨实例共享连接状态
    2. Redis Pub/Sub 消息广播
    3. 水平扩展
    """

    # Redis key 前缀
    CONNECTION_PREFIX = "ws:connection:"
    USER_PREFIX = "ws:user:"
    ONLINE_USERS_KEY = "ws:online_users"
    PUBSUB_CHANNEL_PREFIX = "ws:user:"

    def __init__(self, redis_url: str = None):
        """初始化 Redis 注册表"""
        self.config = get_config()
        self.redis_url = redis_url or self.config.redis_url

        # 本地 WebSocket 存储 (只存储本实例的连接)
        self._local_websockets: Dict[str, Any] = {}

        # Redis 连接
        self._redis = None
        self._pubsub = None

        # 订阅任务
        self._subscribe_task = None

        logger.info("✅ RedisConnectionRegistry 初始化")

    async def _get_redis(self):
        """获取 Redis 连接"""
        if self._redis is None:
            if not AIOREDIS_AVAILABLE:
                raise RuntimeError("aioredis 未安装，无法使用 Redis 连接注册表")
            self._redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        return self._redis

    async def _get_pubsub(self):
        """获取 PubSub 连接"""
        if self._pubsub is None:
            redis = await self._get_redis()
            self._pubsub = redis.pubsub()
        return self._pubsub

    async def register_connection(
        self,
        user_id: str,
        expert_id: str,
        connection_id: str = None,
        websocket: Any = None,
        metadata: Dict = None
    ):
        """
        注册连接

        Args:
            user_id: 用户ID
            expert_id: 角色ID
            connection_id: 连接ID (自动生成)
            websocket: WebSocket 对象
            metadata: 元数据
        """
        if connection_id is None:
            connection_id = generate_connection_id()

        metadata = metadata or {}
        now = datetime.now()

        # 保存本地 WebSocket
        if websocket:
            self._local_websockets[connection_id] = websocket

        # 保存到 Redis
        redis = await self._get_redis()
        pipe = redis.pipeline()

        # 连接信息
        connection_key = f"{self.CONNECTION_PREFIX}{connection_id}"
        connection_info = {
            "connection_id": connection_id,
            "user_id": user_id,
            "expert_id": expert_id,
            "connected_at": now.isoformat(),
            "metadata": metadata
        }
        pipe.hset(connection_key, mapping=connection_info)
        pipe.expire(connection_key, 3600)  # 1小时过期

        # 用户映射
        user_key = f"{self.USER_PREFIX}{user_id}"
        pipe.set(user_key, connection_id, ex=3600)

        # 在线用户集合
        pipe.sadd(self.ONLINE_USERS_KEY, user_id)

        await pipe.execute()

        logger.info(f"✅ 注册连接 (Redis): {user_id} -> {connection_id}")

        return connection_id

    async def unregister_connection(self, user_id: str, connection_id: str):
        """注销连接"""
        redis = await self._get_redis()
        pipe = redis.pipeline()

        # 删除连接信息
        connection_key = f"{self.CONNECTION_PREFIX}{connection_id}"
        pipe.delete(connection_key)

        # 删除用户映射
        user_key = f"{self.USER_PREFIX}{user_id}"
        pipe.delete(user_key)

        # 从在线用户集合移除
        pipe.srem(self.ONLINE_USERS_KEY, user_id)

        await pipe.execute()

        # 清理本地 WebSocket
        self._local_websockets.pop(connection_id, None)

        logger.info(f"🗑️ 注销连接 (Redis): {user_id} -> {connection_id}")

    async def get_connection(self, user_id: str) -> Optional[Any]:
        """
        获取用户连接

        注意: 只能获取本实例的连接
        """
        redis = await self._get_redis()
        connection_id = await redis.get(f"{self.USER_PREFIX}{user_id}")

        if not connection_id:
            return None

        # 检查是否是本地连接
        return self._local_websockets.get(connection_id)

    async def is_user_online(self, user_id: str) -> bool:
        """检查用户是否在线"""
        redis = await self._get_redis()
        return await redis.sismember(self.ONLINE_USERS_KEY, user_id)

    async def broadcast_to_user(self, user_id: str, message: Dict) -> bool:
        """
        向用户广播消息

        使用 Redis Pub/Sub 将消息发送到所有实例
        """
        redis = await self._get_redis()

        # 先尝试本地 WebSocket
        local_ws = await self.get_connection(user_id)
        if local_ws:
            try:
                await local_ws.send_json(message)
                return True
            except Exception as e:
                logger.error(f"❌ 本地 WebSocket 推送失败: {e}")

        # 通过 Redis Pub/Sub 广播
        channel = f"{self.PUBSUB_CHANNEL_PREFIX}{user_id}"
        await redis.publish(channel, json.dumps(message))

        logger.info(f"📢 通过 Redis Pub/Sub 广播消息: {user_id}")
        return True

    async def subscribe_user(self, user_id: str, websocket: Any):
        """
        订阅用户的 Redis 消息频道

        在 WebSocket 连接建立后调用
        """
        pubsub = await self._get_pubsub()
        channel = f"{self.PUBSUB_CHANNEL_PREFIX}{user_id}"

        await pubsub.subscribe(channel)

        # 启动监听任务
        async def listener():
            while True:
                try:
                    message = await pubsub.get_message(timeout=1)
                    if message and message['type'] == 'message':
                        data = json.loads(message['data'])
                        await websocket.send_json(data)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"❌ PubSub 监听错误: {e}")

        self._subscribe_task = asyncio.create_task(listener())
        logger.info(f"✅ 订阅用户频道: {user_id}")

    async def unsubscribe_user(self, user_id: str):
        """取消订阅用户频道"""
        if self._subscribe_task:
            self._subscribe_task.cancel()
            try:
                await self._subscribe_task
            except asyncio.CancelledError:
                pass
            self._subscribe_task = None

        pubsub = await self._get_pubsub()
        channel = f"{self.PUBSUB_CHANNEL_PREFIX}{user_id}"
        await pubsub.unsubscribe(channel)
        logger.info(f"❌ 取消订阅用户频道: {user_id}")

    async def get_online_users(self) -> Set[str]:
        """获取所有在线用户"""
        redis = await self._get_redis()
        members = await redis.smembers(self.ONLINE_USERS_KEY)
        return set(members)

    async def get_connection_info(self, connection_id: str) -> Optional[ConnectionInfo]:
        """获取连接信息"""
        redis = await self._get_redis()
        data = await redis.hgetall(f"{self.CONNECTION_PREFIX}{connection_id}")

        if not data:
            return None

        return ConnectionInfo(
            connection_id=data['connection_id'],
            user_id=data['user_id'],
            expert_id=data['expert_id'],
            connected_at=datetime.fromisoformat(data['connected_at']),
            metadata=json.loads(data.get('metadata', '{}'))
        )

    async def cleanup_stale_connections(self):
        """清理过期连接 (由定时任务调用)"""
        redis = await self._get_redis()

        # 检查所有在线用户
        online_users = await self.get_online_users()
        for user_id in online_users:
            user_key = f"{self.USER_PREFIX}{user_id}"
            connection_id = await redis.get(user_key)

            if connection_id:
                connection_key = f"{self.CONNECTION_PREFIX}{connection_id}"
                exists = await redis.exists(connection_key)

                if not exists:
                    # 连接信息已过期，清理用户映射
                    await redis.delete(user_key)
                    await redis.srem(self.ONLINE_USERS_KEY, user_id)
                    logger.info(f"🗑️ 清理过期连接: {user_id}")

    async def close(self):
        """关闭连接"""
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
        if self._redis:
            await self._redis.close()
            self._redis = None


# 全局实例
_global_registry: Optional[ConnectionRegistry] = None


def get_connection_registry() -> ConnectionRegistry:
    """获取全局连接注册表"""
    global _global_registry

    if _global_registry is None:
        config = get_config()
        if config.use_redis_registry and AIOREDIS_AVAILABLE:
            _global_registry = RedisConnectionRegistry()
        else:
            if config.use_redis_registry and not AIOREDIS_AVAILABLE:
                logger.warning("⚠️ Redis 注册表已配置但 aioredis 未安装，使用内存注册表")
            _global_registry = InMemoryConnectionRegistry()

    return _global_registry


def set_connection_registry(registry: ConnectionRegistry):
    """设置全局连接注册表"""
    global _global_registry
    _global_registry = registry
