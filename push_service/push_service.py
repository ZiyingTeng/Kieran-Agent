#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一推送服务

智能路由推送消息:
1. WebSocket (最快，如果在线)
2. 平台推送 (FCM/APNs/WebPush)
3. 离线队列 (兜底)
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from .config import get_config
from .models import PushResult, Platform, MessageType
from .device_manager import DeviceManager
from .offline_queue import OfflineQueue
from .registry import get_connection_registry
from .providers import WebPushProvider, FCMProvider, APNsProvider

logger = logging.getLogger(__name__)


class PushService:
    """
    统一推送服务

    负责协调各种推送渠道，实现智能路由
    """

    def __init__(self):
        """初始化推送服务"""
        self.config = get_config()
        self.device_manager = DeviceManager()
        self.offline_queue = OfflineQueue()
        self.connection_registry = get_connection_registry()

        # 推送提供商
        self.providers: Dict[str, Any] = {}

        # 初始化状态
        self._initialized = False

    async def initialize(self):
        """初始化推送服务"""
        if self._initialized:
            return

        logger.info("🚀 初始化 PushService...")

        # 初始化提供商
        if self.config.enable_web_push:
            web_push = WebPushProvider()
            await web_push.initialize()
            if web_push.is_available():
                self.providers["web"] = web_push
                logger.info("✅ Web Push 提供商已启用")

        if self.config.enable_fcm:
            fcm = FCMProvider()
            await fcm.initialize()
            if fcm.is_available():
                self.providers["android"] = fcm
                # FCM 也支持 Web
                if "web" not in self.providers:
                    self.providers["web"] = fcm
                logger.info("✅ FCM 提供商已启用")

        if self.config.enable_apns:
            apns = APNsProvider()
            await apns.initialize()
            if apns.is_available():
                self.providers["ios"] = apns
                logger.info("✅ APNs 提供商已启用")

        self._initialized = True
        logger.info(f"🎉 PushService 初始化完成 (已启用 {len(self.providers)} 个提供商)")

    async def close(self):
        """关闭推送服务"""
        await self.device_manager.close()
        await self.offline_queue.close()
        if hasattr(self.connection_registry, 'close'):
            await self.connection_registry.close()
        logger.info("👋 PushService 已关闭")

    async def send_to_user(
        self,
        user_id: str,
        expert_id: str,
        title: str,
        body: str,
        message_type: str = "chat",
        data: Dict[str, Any] = None,
        priority: int = 5,
        skip_offline: bool = False
    ) -> PushResult:
        """
        智能推送消息给用户

        路由策略:
        1. WebSocket (最快，如果在线)
        2. 平台推送 (FCM/APNs/WebPush)
        3. 离线队列 (兜底)

        Args:
            user_id: 用户ID
            expert_id: 角色ID
            title: 标题
            body: 消息内容
            message_type: 消息类型
            data: 附加数据
            priority: 优先级 (1-10)
            skip_offline: 是否跳过离线队列

        Returns:
            PushResult: 推送结果
        """
        result = PushResult(user_id=user_id)
        data = data or {}
        data["expert_id"] = expert_id
        data["message_type"] = message_type

        logger.info(f"📤 发送消息给用户: {user_id} ({message_type})")

        # 1. 尝试 WebSocket (最快)
        if await self._try_websocket(user_id, title, body, data):
            result.websocket_sent = True
            result.delivered = True
            logger.info(f"✅ WebSocket 推送成功: {user_id}")
            return result

        # 2. 尝试平台推送
        devices = await self.device_manager.get_user_devices(user_id)
        logger.info(f"📱 用户 {user_id} 有 {len(devices)} 个设备")

        if devices:
            platform_sent = False
            for device in devices:
                provider = self.providers.get(device.platform.value)
                if provider and await provider.send(device.token, title, body, data):
                    result.platforms_sent.append(device.platform.value)
                    platform_sent = True

                    # 记录推送日志
                    await self.device_manager.log_push(
                        user_id=user_id,
                        platform=device.platform.value,
                        message_type=message_type,
                        status="success"
                    )
                else:
                    # 记录失败日志
                    await self.device_manager.log_push(
                        user_id=user_id,
                        platform=device.platform.value,
                        message_type=message_type,
                        status="failed",
                        error_message="Provider unavailable or send failed"
                    )

            if platform_sent:
                result.delivered = True
                logger.info(f"✅ 平台推送成功: {user_id} -> {result.platforms_sent}")
                return result

        # 3. 兜底：存入离线队列
        if not skip_offline:
            await self.offline_queue.enqueue(
                user_id=user_id,
                expert_id=expert_id,
                title=title,
                body=body,
                message_type=message_type,
                data=data,
                priority=priority
            )
            result.queued = True
            logger.info(f"📬 消息已加入离线队列: {user_id}")
        else:
            logger.info(f"⏭️ 跳过离线队列: {user_id}")

        return result

    async def _try_websocket(
        self,
        user_id: str,
        title: str,
        body: str,
        data: Dict[str, Any]
    ) -> bool:
        """
        尝试通过 WebSocket 推送

        Args:
            user_id: 用户ID
            title: 标题
            body: 消息内容
            data: 附加数据

        Returns:
            bool: 是否成功
        """
        try:
            # 检查用户是否在线
            is_online = await self.connection_registry.is_user_online(user_id)
            if not is_online:
                logger.debug(f"用户 {user_id} 不在线")
                return False

            # 构建消息
            message = {
                "type": data.get("message_type", "chat"),
                "title": title,
                "body": body,
                "data": data,
                "timestamp": datetime.now().isoformat()
            }

            # 发送消息
            success = await self.connection_registry.broadcast_to_user(user_id, message)
            return success

        except Exception as e:
            logger.error(f"❌ WebSocket 推送异常: {e}")
            return False

    async def register_device(
        self,
        user_id: str,
        expert_id: str,
        platform: str,
        token: str,
        device_info: Dict[str, Any] = None
    ):
        """
        注册设备令牌

        Args:
            user_id: 用户ID
            expert_id: 角色ID
            platform: 平台类型
            token: 设备令牌
            device_info: 设备信息
        """
        return await self.device_manager.register_device(
            user_id=user_id,
            expert_id=expert_id,
            platform=platform,
            token=token,
            device_info=device_info
        )

    async def get_user_devices(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取用户的所有设备

        Args:
            user_id: 用户ID

        Returns:
            List[Dict]: 设备列表
        """
        devices = await self.device_manager.get_user_devices(user_id)
        return [d.to_dict() for d in devices]

    async def unregister_device(self, user_id: str, token: str) -> bool:
        """
        注销设备令牌

        Args:
            user_id: 用户ID
            token: 设备令牌

        Returns:
            bool: 是否成功
        """
        return await self.device_manager.unregister_device(user_id, token)

    async def get_offline_messages(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取用户的离线消息

        Args:
            user_id: 用户ID
            limit: 最大数量

        Returns:
            List[Dict]: 消息列表
        """
        messages = await self.offline_queue.dequeue(user_id, limit)

        # 标记为已发送
        for msg in messages:
            await self.offline_queue.mark_sent(msg.id)

        return [m.to_dict() for m in messages]

    async def clear_offline_messages(
        self,
        user_id: str,
        expert_id: str = None
    ) -> int:
        """
        清空用户的离线消息

        Args:
            user_id: 用户ID
            expert_id: 角色ID (可选)

        Returns:
            int: 清理的消息数量
        """
        return await self.offline_queue.clear_user_messages(user_id, expert_id)

    async def get_stats(self) -> Dict[str, Any]:
        """
        获取推送服务统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "initialized": self._initialized,
            "providers": list(self.providers.keys()),
            "online_users": len(await self.connection_registry.get_online_users())
            if hasattr(self.connection_registry, "get_online_users") else "unknown"
        }


# 全局实例
_global_push_service: Optional[PushService] = None


def get_push_service() -> PushService:
    """获取全局推送服务实例"""
    global _global_push_service

    if _global_push_service is None:
        _global_push_service = PushService()

    return _global_push_service


async def initialize_push_service():
    """初始化全局推送服务"""
    global _global_push_service

    if _global_push_service is None:
        _global_push_service = PushService()

    await _global_push_service.initialize()

    return _global_push_service
