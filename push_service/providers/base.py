#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推送提供商基类
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class BasePushProvider(ABC):
    """
    推送提供商基类

    所有推送提供商必须实现此接口
    """

    def __init__(self, platform: str):
        """
        初始化推送提供商

        Args:
            platform: 平台名称 (ios/android/web)
        """
        self.platform = platform
        self._initialized = False

    @abstractmethod
    async def initialize(self):
        """初始化提供商"""
        pass

    @abstractmethod
    async def send(
        self,
        token: str,
        title: str,
        body: str,
        data: Dict[str, Any] = None
    ) -> bool:
        """
        发送推送通知

        Args:
            token: 设备令牌
            title: 标题
            body: 消息内容
            data: 附加数据

        Returns:
            bool: 是否成功
        """
        pass

    @abstractmethod
    async def send_batch(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: Dict[str, Any] = None
    ) -> Dict[str, bool]:
        """
        批量发送推送通知

        Args:
            tokens: 设备令牌列表
            title: 标题
            body: 消息内容
            data: 附加数据

        Returns:
            Dict[str, bool]: 每个令牌的发送结果
        """
        pass

    def is_available(self) -> bool:
        """检查提供商是否可用"""
        return self._initialized

    def _log_send(self, success: bool, token: str, error: str = None):
        """记录发送日志"""
        if success:
            logger.info(f"✅ {self.platform} 推送成功: {token[:20]}...")
        else:
            logger.warning(f"⚠️ {self.platform} 推送失败: {token[:20]}... - {error}")
