#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推送服务配置
"""

import os
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PushConfig:
    """推送服务配置"""

    # Redis 配置
    redis_url: str = field(default_factory=lambda: os.getenv(
        "REDIS_URL", "redis://localhost:6379/0"
    ))
    redis_connection_pool_size: int = 50

    # PostgreSQL 配置
    postgres_url: str = field(default_factory=lambda: os.getenv(
        "POSTGRES_URL", "postgresql://postgres:mysecretpassword@localhost:5433/postgres"
    ))

    # Celery 配置
    celery_broker_url: str = field(default_factory=lambda: os.getenv(
        "CELERY_BROKER_URL", "redis://localhost:6379/1"
    ))

    # 推送配置
    offline_expire_days: int = field(default_factory=lambda: int(
        os.getenv("PUSH_OFFLINE_EXPIRE_DAYS", "7")
    ))
    max_retries: int = field(default_factory=lambda: int(
        os.getenv("PUSH_MAX_RETRIES", "3")
    ))

    # FCM 配置
    fcm_credentials_path: Optional[str] = field(default_factory=lambda: os.getenv(
        "FCM_CREDENTIALS"
    ))
    fcm_api_key: Optional[str] = field(default_factory=lambda: os.getenv(
        "FCM_API_KEY"
    ))

    # APNs 配置
    apns_key_id: Optional[str] = field(default_factory=lambda: os.getenv(
        "APNS_KEY_ID"
    ))
    apns_team_id: Optional[str] = field(default_factory=lambda: os.getenv(
        "APNS_TEAM_ID"
    ))
    apns_key_path: Optional[str] = field(default_factory=lambda: os.getenv(
        "APNS_KEY_PATH"
    ))
    apns_use_sandbox: bool = field(default_factory=lambda: os.getenv(
        "APNS_USE_SANDBOX", "false"
    ).lower() == "true")

    # Web Push 配置
    vapid_public_key: str = field(default_factory=lambda: os.getenv(
        "VAPID_PUBLIC_KEY", ""
    ))
    vapid_private_key: str = field(default_factory=lambda: os.getenv(
        "VAPID_PRIVATE_KEY", ""
    ))
    vapid_subject: str = field(default_factory=lambda: os.getenv(
        "VAPID_SUBJECT", "mailto:admin@example.com"
    ))

    # 功能开关
    use_redis_registry: bool = field(default_factory=lambda: os.getenv(
        "USE_REDIS_REGISTRY", "false"
    ).lower() == "true")
    enable_fcm: bool = field(default_factory=lambda: os.getenv(
        "ENABLE_FCM", "true"
    ).lower() == "true")
    enable_apns: bool = field(default_factory=lambda: os.getenv(
        "ENABLE_APNS", "true"
    ).lower() == "true")
    enable_web_push: bool = field(default_factory=lambda: os.getenv(
        "ENABLE_WEB_PUSH", "true"
    ).lower() == "true")

    # 性能配置
    websocket_ping_interval: int = 20  # 秒
    websocket_ping_timeout: int = 20  # 秒
    connection_cleanup_interval: int = 300  # 秒

    def __post_init__(self):
        """验证配置"""
        if self.offline_expire_days < 1:
            raise ValueError("offline_expire_days must be at least 1")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")


# 全局配置实例
_global_config: Optional[PushConfig] = None


def get_config(**kwargs) -> PushConfig:
    """
    获取全局配置实例

    Args:
        **kwargs: 配置覆盖参数

    Returns:
        PushConfig: 配置实例
    """
    global _global_config

    if _global_config is None:
        _global_config = PushConfig(**{
            k: v for k, v in kwargs.items()
            if v is not None and hasattr(PushConfig, k)
        })

    return _global_config


def set_config(config: PushConfig):
    """设置全局配置"""
    global _global_config
    _global_config = config
