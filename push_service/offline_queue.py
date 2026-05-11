#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
离线消息队列

负责管理离线消息的存储和检索
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import json

from .config import get_config
from .models import OfflineMessage, MessageType, MessageStatus

logger = logging.getLogger(__name__)


class OfflineQueue:
    """
    离线消息队列

    负责:
    1. 入队: 将消息存入离线队列
    2. 出队: 获取待发送的消息
    3. 标记已发送
    4. 清理过期消息
    """

    def __init__(self):
        """初始化离线队列"""
        self.config = get_config()
        self._pool = None

    async def _get_pool(self):
        """获取数据库连接池"""
        if self._pool is None:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                self.config.postgres_url,
                min_size=5,
                max_size=20
            )
        return self._pool

    async def close(self):
        """关闭连接池"""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def enqueue(
        self,
        user_id: str,
        expert_id: str,
        title: str,
        body: str,
        message_type: str = "chat",
        data: Dict[str, Any] = None,
        priority: int = 5,
        scheduled_at: datetime = None
    ) -> OfflineMessage:
        """
        将消息加入离线队列

        Args:
            user_id: 用户ID
            expert_id: 角色ID
            title: 标题
            body: 消息内容
            message_type: 消息类型
            data: 附加数据
            priority: 优先级 (1-10, 越小越优先)
            scheduled_at: 计划发送时间

        Returns:
            OfflineMessage: 离线消息
        """
        pool = await self._get_pool()
        data = data or {}
        now = datetime.now()
        scheduled_at = scheduled_at or now
        expires_at = now + timedelta(days=self.config.offline_expire_days)

        # 确保 message_type 是枚举值
        if isinstance(message_type, str):
            try:
                message_type = MessageType(message_type)
            except ValueError:
                message_type = MessageType.CHAT

        async with pool.acquire() as conn:
            message_id = await conn.fetchval(
                """INSERT INTO offline_messages
                   (user_id, expert_id, message_type, title, body, data,
                    priority, status, retry_count, max_retries,
                    scheduled_at, expires_at)
                   VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, $12)
                   RETURNING id""",
                user_id, expert_id,
                message_type.value if isinstance(message_type, MessageType) else message_type,
                title, body, json.dumps(data) if data else '{}',
                priority, "pending", 0, self.config.max_retries,
                scheduled_at, expires_at
            )

            logger.info(f"✅ 消息加入离线队列: {user_id} (ID: {message_id})")

            return OfflineMessage(
                id=message_id,
                user_id=user_id,
                expert_id=expert_id,
                message_type=message_type,
                title=title,
                body=body,
                data=data,
                priority=priority,
                status=MessageStatus.PENDING,
                scheduled_at=scheduled_at,
                expires_at=expires_at
            )

    async def dequeue(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[OfflineMessage]:
        """
        获取用户的待发送消息

        Args:
            user_id: 用户ID
            limit: 最大数量

        Returns:
            List[OfflineMessage]: 消息列表
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            now = datetime.now()

            rows = await conn.fetch(
                """SELECT id, user_id, expert_id, message_type, title, body, data,
                          priority, status, retry_count, max_retries,
                          scheduled_at, sent_at, expires_at
                   FROM offline_messages
                   WHERE user_id = $1
                     AND status = 'pending'
                     AND scheduled_at <= $2
                     AND expires_at > $2
                   ORDER BY priority ASC, scheduled_at ASC
                   LIMIT $3
                   FOR UPDATE SKIP LOCKED""",
                user_id, now, limit
            )

            messages = [
                OfflineMessage(
                    id=row['id'],
                    user_id=row['user_id'],
                    expert_id=row['expert_id'],
                    message_type=MessageType(row['message_type']),
                    title=row['title'],
                    body=row['body'],
                    data=row['data'] or {},
                    priority=row['priority'],
                    status=MessageStatus(row['status']),
                    retry_count=row['retry_count'],
                    max_retries=row['max_retries'],
                    scheduled_at=row['scheduled_at'],
                    sent_at=row['sent_at'],
                    expires_at=row['expires_at']
                )
                for row in rows
            ]

            return messages

    async def mark_sent(self, message_id: int) -> bool:
        """
        标记消息已发送

        Args:
            message_id: 消息ID

        Returns:
            bool: 是否成功
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            result = await conn.execute(
                """UPDATE offline_messages
                   SET status = 'sent', sent_at = $1
                   WHERE id = $2""",
                datetime.now(), message_id
            )

            if result == "UPDATE 1":
                logger.info(f"✅ 消息已发送: {message_id}")
                return True
            return False

    async def mark_failed(
        self,
        message_id: int,
        error_message: str = None
    ) -> bool:
        """
        标记消息发送失败

        Args:
            message_id: 消息ID
            error_message: 错误信息

        Returns:
            bool: 是否应该重试
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            # 获取当前重试次数
            row = await conn.fetchrow(
                """SELECT retry_count, max_retries FROM offline_messages
                   WHERE id = $1""",
                message_id
            )

            if not row:
                return False

            retry_count = row['retry_count']
            max_retries = row['max_retries']

            if retry_count >= max_retries:
                # 达到最大重试次数，标记为失败
                await conn.execute(
                    """UPDATE offline_messages
                       SET status = 'failed'
                       WHERE id = $1""",
                    message_id
                )
                logger.warning(f"❌ 消息发送失败 (已达最大重试): {message_id}")
                return False
            else:
                # 增加重试次数
                await conn.execute(
                    """UPDATE offline_messages
                       SET retry_count = retry_count + 1
                       WHERE id = $1""",
                    message_id
                )
                logger.info(f"🔄 消息重试: {message_id} ({retry_count + 1}/{max_retries})")
                return True

    async def get_pending_messages(
        self,
        limit: int = 100
    ) -> List[OfflineMessage]:
        """
        获取所有待发送的消息 (用于批量处理)

        Args:
            limit: 最大数量

        Returns:
            List[OfflineMessage]: 消息列表
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            now = datetime.now()

            rows = await conn.fetch(
                """SELECT id, user_id, expert_id, message_type, title, body, data,
                          priority, status, retry_count, max_retries,
                          scheduled_at, sent_at, expires_at
                   FROM offline_messages
                   WHERE status = 'pending'
                     AND scheduled_at <= $1
                     AND expires_at > $1
                   ORDER BY priority ASC, scheduled_at ASC
                   LIMIT $2
                   FOR UPDATE SKIP LOCKED""",
                now, limit
            )

            messages = [
                OfflineMessage(
                    id=row['id'],
                    user_id=row['user_id'],
                    expert_id=row['expert_id'],
                    message_type=MessageType(row['message_type']),
                    title=row['title'],
                    body=row['body'],
                    data=row['data'] or {},
                    priority=row['priority'],
                    status=MessageStatus(row['status']),
                    retry_count=row['retry_count'],
                    max_retries=row['max_retries'],
                    scheduled_at=row['scheduled_at'],
                    sent_at=row['sent_at'],
                    expires_at=row['expires_at']
                )
                for row in rows
            ]

            return messages

    async def cleanup_expired_messages(self) -> int:
        """
        清理过期消息

        Returns:
            int: 清理的消息数量
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            result = await conn.execute(
                """DELETE FROM offline_messages
                   WHERE expires_at < $1 OR status = 'expired'""",
                datetime.now()
            )

            count = int(result.split()[-1])
            logger.info(f"🗑️ 清理了 {count} 条过期消息")
            return count

    async def get_user_pending_count(self, user_id: str) -> int:
        """
        获取用户待发送消息数量

        Args:
            user_id: 用户ID

        Returns:
            int: 待发送消息数量
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            count = await conn.fetchval(
                """SELECT COUNT(*) FROM offline_messages
                   WHERE user_id = $1 AND status = 'pending' AND expires_at > $2""",
                user_id, datetime.now()
            )

            return count or 0

    async def clear_user_messages(
        self,
        user_id: str,
        expert_id: str = None
    ) -> int:
        """
        清空用户的离线消息 (用户上线后调用)

        Args:
            user_id: 用户ID
            expert_id: 角色ID (可选，如果指定则只清空该角色的消息)

        Returns:
            int: 清理的消息数量
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            if expert_id:
                result = await conn.execute(
                    """DELETE FROM offline_messages
                       WHERE user_id = $1 AND expert_id = $2""",
                    user_id, expert_id
                )
            else:
                result = await conn.execute(
                    """DELETE FROM offline_messages
                       WHERE user_id = $1""",
                    user_id
                )

            count = int(result.split()[-1])
            logger.info(f"🗑️ 清空用户 {user_id} 的 {count} 条离线消息")
            return count
