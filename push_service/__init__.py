#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业级推送服务

支持:
- WebSocket 实时推送
- 离线消息队列
- 设备令牌管理 (FCM/APNs/WebPush)
- Redis 连接注册表 (水平扩展)

使用示例:
    from push_service import get_push_service

    push_service = get_push_service()

    # 发送消息给用户 (智能路由)
    result = await push_service.send_to_user(
        user_id="user123",
        expert_id="expert456",
        title="新消息",
        body="你好！",
        message_type="chat"
    )

    # 注册设备
    await push_service.register_device(
        user_id="user123",
        expert_id="expert456",
        platform="web",
        token="device_token"
    )
"""

from .config import PushConfig, get_config
from .models import (
    PushResult,
    DeviceRegisterRequest,
    DeviceUnregisterRequest,
    PushMessageRequest,
    DeviceInfo,
    OfflineMessage
)
from .device_manager import DeviceManager
from .offline_queue import OfflineQueue
from .push_service import PushService, get_push_service, initialize_push_service
from .registry import ConnectionRegistry, get_connection_registry

__all__ = [
    # Config
    "PushConfig",
    "get_config",
    # Models
    "PushResult",
    "DeviceRegisterRequest",
    "DeviceUnregisterRequest",
    "PushMessage",
    "DeviceInfo",
    "OfflineMessage",
    # Core
    "DeviceManager",
    "OfflineQueue",
    "PushService",
    "get_push_service",
    "initialize_push_service",
    "ConnectionRegistry",
    "get_connection_registry",
]

__version__ = "1.0.0"
