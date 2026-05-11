#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APNs (Apple Push Notification Service) 提供商

支持 iOS 推送
"""

import logging
from typing import Dict, Any, List
from pathlib import Path

from .base import BasePushProvider
from ..config import get_config

logger = logging.getLogger(__name__)

# 可选导入
try:
    from apns2 import credentials, client
    APNS2_AVAILABLE = True
except ImportError:
    APNS2_AVAILABLE = False
    logger.warning("⚠️ apns2 未安装，APNs 将不可用")


class APNsProvider(BasePushProvider):
    """
    APNs 推送提供商

    支持 iOS 设备推送
    """

    def __init__(self):
        """初始化 APNs 提供商"""
        super().__init__("ios")
        self.config = get_config()
        self._client = None

    async def initialize(self):
        """初始化提供商"""
        if not APNS2_AVAILABLE:
            logger.warning("apns2 未安装，APNs Provider 不可用")
            self._initialized = False
            return

        # 检查配置
        if not self.config.apns_key_path or not self.config.apns_key_id or not self.config.apns_team_id:
            logger.warning("⚠️ APNs 配置不完整，APNs 将不可用")
            self._initialized = False
            return

        key_path = Path(self.config.apns_key_path)
        if not key_path.exists():
            logger.warning(f"⚠️ APNs 密钥文件不存在: {self.config.apns_key_path}")
            self._initialized = False
            return

        try:

            # 创建认证凭证
            auth_key = credentials.AuthorizationCredentials(
                key_path=str(key_path),
                key_id=self.config.apns_key_id,
                team_id=self.config.apns_team_id
            )

            # 创建客户端
            if self.config.apns_use_sandbox:
                self._client = client.ApnClient(
                    credentials=auth_key,
                    use_sandbox=True
                )
            else:
                self._client = client.ApnClient(
                    credentials=auth_key,
                    use_sandbox=False
                )

            self._initialized = True
            logger.info("✅ APNs Provider 初始化完成")

        except ImportError:
            logger.warning("⚠️ apns2 未安装，APNs 将不可用")
            self._initialized = False
        except Exception as e:
            logger.error(f"❌ APNs 初始化失败: {e}")
            self._initialized = False

    async def send(
        self,
        token: str,
        title: str,
        body: str,
        data: Dict[str, Any] = None
    ) -> bool:
        """
        发送 APNs 推送通知

        Args:
            token: 设备令牌 (device token)
            title: 标题
            body: 消息内容
            data: 附加数据

        Returns:
            bool: 是否成功
        """
        if not self._initialized or not self._client:
            logger.warning("APNs Provider 未初始化")
            return False

        if not APNS2_AVAILABLE:
            return False

        try:
            from apns2 import payload

            # 构建 payload
            alert = payload.PayloadAlert(
                title=title,
                body=body
            )

            # 自定义数据
            custom_data = data or {}

            # 构建 payload
            apns_payload = payload.Payload(
                alert=alert,
                badge=1,
                sound='default',
                custom=custom_data
            )

            # 发送推送
            result = self._client.send(
                token=token,
                notification=apns_payload
            )

            # APNs 返回 200 表示成功
            if result.status_code == 200:
                self._log_send(True, token)
                return True
            else:
                self._log_send(False, token, f"HTTP {result.status_code}")

                # 检查是否是无效令牌 (400 Bad Request)
                if result.status_code == 400:
                    logger.warning(f"⚠️ APNs 令牌可能已失效: {token[:20]}...")

                return False

        except Exception as e:
            self._log_send(False, token, str(e))
            return False

    async def send_batch(
        self,
        tokens: List[str],
        title: str,
        body: str,
        data: Dict[str, Any] = None
    ) -> Dict[str, bool]:
        """
        批量发送 APNs 推送通知

        Args:
            tokens: 设备令牌列表
            title: 标题
            body: 消息内容
            data: 附加数据

        Returns:
            Dict[str, bool]: 每个令牌的发送结果
        """
        results = {}

        for token in tokens:
            results[token] = await self.send(token, title, body, data)

        return results

    async def send_silent(
        self,
        token: str,
        data: Dict[str, Any]
    ) -> bool:
        """
        发送静默推送 (后台更新)

        Args:
            token: 设备令牌
            data: 附加数据

        Returns:
            bool: 是否成功
        """
        if not self._initialized or not self._client:
            return False

        if not APNS2_AVAILABLE:
            return False

        try:
            from apns2 import payload

            # 静默推送使用 content-available: 1
            apns_payload = payload.Payload(
                content_available=True,
                custom=data
            )

            result = self._client.send(
                token=token,
                notification=apns_payload
            )

            return result.status_code == 200

        except Exception as e:
            logger.error(f"❌ APNs 静默推送失败: {e}")
            return False
