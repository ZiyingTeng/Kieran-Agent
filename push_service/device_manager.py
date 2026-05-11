#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
设备令牌管理

负责管理用户设备的推送令牌
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import json

from .config import get_config
from .models import DeviceInfo, Platform

logger = logging.getLogger(__name__)


class DeviceManager:
    """
    设备令牌管理器

    负责:
    1. 注册设备令牌
    2. 查询用户设备
    3. 注销设备
    4. 清理过期设备
    """

    def __init__(self):
        """初始化设备管理器"""
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

    async def register_device(
        self,
        user_id: str,
        expert_id: str,
        platform: str,
        token: str,
        device_info: Dict[str, Any] = None
    ) -> DeviceInfo:
        """
        注册设备令牌

        Args:
            user_id: 用户ID
            expert_id: 角色ID
            platform: 平台类型 (ios/android/web)
            token: 设备令牌
            device_info: 设备信息

        Returns:
            DeviceInfo: 设备信息
        """
        pool = await self._get_pool()
        device_info = device_info or {}

        async with pool.acquire() as conn:
            # 检查是否已存在
            existing = await conn.fetchrow(
                """SELECT id FROM device_tokens
                   WHERE user_id = $1 AND platform = $2 AND token = $3""",
                user_id, platform, token
            )

            now = datetime.now()

            if existing:
                # 更新现有设备
                await conn.execute(
                    """UPDATE device_tokens
                       SET expert_id = $1, is_active = true,
                           device_info = $2::jsonb, updated_at = $3, last_used_at = $3
                       WHERE id = $4""",
                    expert_id, json.dumps(device_info), now, existing['id']
                )
                device_id = existing['id']
                logger.info(f"✅ 更新设备令牌: {user_id} ({platform})")
            else:
                # 插入新设备
                device_id = await conn.fetchval(
                    """INSERT INTO device_tokens
                       (user_id, expert_id, platform, token, device_info, created_at, updated_at, last_used_at)
                       VALUES ($1, $2, $3, $4, $5::jsonb, $6, $6, $6)
                       RETURNING id""",
                    user_id, expert_id, platform, token, json.dumps(device_info), now
                )
                logger.info(f"✅ 注册新设备令牌: {user_id} ({platform})")

            return DeviceInfo(
                id=device_id,
                user_id=user_id,
                expert_id=expert_id,
                platform=Platform(platform) if platform in [p.value for p in Platform] else Platform.WEB,
                token=token,
                device_info=device_info,
                is_active=True,
                created_at=now,
                updated_at=now,
                last_used_at=now
            )

    async def get_user_devices(self, user_id: str) -> List[DeviceInfo]:
        """
        获取用户的所有设备

        Args:
            user_id: 用户ID

        Returns:
            List[DeviceInfo]: 设备列表
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, user_id, expert_id, platform, token, device_info,
                          is_active, created_at, updated_at, last_used_at
                   FROM device_tokens
                   WHERE user_id = $1 AND is_active = true
                   ORDER BY last_used_at DESC""",
                user_id
            )

            devices = [
                DeviceInfo(
                    id=row['id'],
                    user_id=row['user_id'],
                    expert_id=row['expert_id'],
                    platform=Platform(row['platform']),
                    token=row['token'],
                    device_info=row['device_info'] or {},
                    is_active=row['is_active'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    last_used_at=row['last_used_at']
                )
                for row in rows
            ]

            return devices

    async def get_devices_by_platform(self, user_id: str, platform: str) -> List[DeviceInfo]:
        """
        获取用户指定平台的设备

        Args:
            user_id: 用户ID
            platform: 平台类型

        Returns:
            List[DeviceInfo]: 设备列表
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, user_id, expert_id, platform, token, device_info,
                          is_active, created_at, updated_at, last_used_at
                   FROM device_tokens
                   WHERE user_id = $1 AND platform = $2 AND is_active = true
                   ORDER BY last_used_at DESC""",
                user_id, platform
            )

            devices = [
                DeviceInfo(
                    id=row['id'],
                    user_id=row['user_id'],
                    expert_id=row['expert_id'],
                    platform=Platform(row['platform']),
                    token=row['token'],
                    device_info=row['device_info'] or {},
                    is_active=row['is_active'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    last_used_at=row['last_used_at']
                )
                for row in rows
            ]

            return devices

    async def unregister_device(self, user_id: str, token: str) -> bool:
        """
        注销设备令牌

        Args:
            user_id: 用户ID
            token: 设备令牌

        Returns:
            bool: 是否成功
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            result = await conn.execute(
                """DELETE FROM device_tokens
                   WHERE user_id = $1 AND token = $2""",
                user_id, token
            )

            if result == "DELETE 1":
                logger.info(f"✅ 注销设备令牌: {user_id}")
                return True
            else:
                logger.warning(f"⚠️ 设备令牌不存在: {user_id}, {token}")
                return False

    async def update_last_used(self, device_id: int):
        """
        更新设备最后使用时间

        Args:
            device_id: 设备ID
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE device_tokens
                   SET last_used_at = $1
                   WHERE id = $2""",
                datetime.now(), device_id
            )

    async def cleanup_inactive_devices(self, days: int = 30) -> int:
        """
        清理长时间未使用的设备

        Args:
            days: 天数阈值

        Returns:
            int: 清理的设备数量
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            threshold = datetime.now() - __import__('datetime').timedelta(days=days)
            result = await conn.execute(
                """DELETE FROM device_tokens
                   WHERE last_used_at < $1 OR created_at < $2""",
                threshold, threshold
            )

            count = int(result.split()[-1])
            logger.info(f"🗑️ 清理了 {count} 个不活跃设备")
            return count

    async def log_push(
        self,
        user_id: str,
        platform: str,
        message_type: str,
        status: str,
        error_message: str = None
    ):
        """
        记录推送日志

        Args:
            user_id: 用户ID
            platform: 平台
            message_type: 消息类型
            status: 状态
            error_message: 错误信息
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO push_logs (user_id, platform, message_type, status, error_message)
                   VALUES ($1, $2, $3, $4, $5)""",
                user_id, platform, message_type, status, error_message
            )
