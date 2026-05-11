#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web Push 提供商

使用 Web Push API (VAPID) 发送浏览器推送通知
"""

import logging
from typing import Dict, Any, List

from .base import BasePushProvider
from ..config import get_config

logger = logging.getLogger(__name__)

# 可选导入
try:
    from pywebpush import webpush, WebPushException
    PYWEBPUSH_AVAILABLE = True
except ImportError:
    PYWEBPUSH_AVAILABLE = False
    logger.warning("⚠️ pywebpush 未安装，Web Push 将不可用")


class WebPushProvider(BasePushProvider):
    """
    Web Push 提供商

    使用 VAPID (Voluntary Application Server Identification)
    发送 Web Push 通知
    """

    def __init__(self):
        """初始化 Web Push 提供商"""
        super().__init__("web")
        self.config = get_config()

    async def initialize(self):
        """初始化提供商"""
        if not PYWEBPUSH_AVAILABLE:
            logger.warning("pywebpush 未安装，Web Push Provider 不可用")
            self._initialized = False
            return

        # 检查 VAPID 配置
        if not self.config.vapid_private_key or not self.config.vapid_public_key:
            logger.warning("⚠️ VAPID keys 未配置，Web Push 将不可用")
            self._initialized = False
            return

        self._initialized = True
        logger.info("✅ WebPush Provider 初始化完成")

    async def send(
        self,
        token: str,
        title: str,
        body: str,
        data: Dict[str, Any] = None
    ) -> bool:
        """
        发送 Web Push 通知

        Args:
            token: 订阅信息 (JSON 字符串)
            title: 标题
            body: 消息内容
            data: 附加数据

        Returns:
            bool: 是否成功
        """
        if not self._initialized or not PYWEBPUSH_AVAILABLE:
            logger.warning("WebPush Provider 未初始化")
            return False

        import json

        try:
            # 解析订阅信息
            subscription_info = json.loads(token) if isinstance(token, str) else token

            # 构建推送数据
            push_data = {
                "title": title,
                "body": body,
                "icon": "/favicon.ico",
                "badge": "/badge.png",
                "data": data or {}
            }

            # 发送推送
            webpush(
                subscription_info=subscription_info,
                data=json.dumps(push_data),
                vapid_private_key=self.config.vapid_private_key,
                vapid_claims={
                    "sub": self.config.vapid_subject
                }
            )

            self._log_send(True, token)
            return True

        except WebPushException as e:
            self._log_send(False, token, str(e))
            # 检查是否是无效订阅 (需要清理)
            if hasattr(e, 'response') and e.response and e.response.status_code in (400, 404, 410):
                logger.warning(f"⚠️ 订阅已失效，需要清理: {token[:20]}...")
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
        批量发送 Web Push 通知

        Args:
            tokens: 订阅信息列表
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


# 生成 VAPID 密钥对的辅助函数
def generate_vapid_keys() -> Dict[str, str]:
    """
    生成 VAPID 密钥对

    Returns:
        Dict[str, str]: 包含 public_key 和 private_key
    """
    import base64

    # 使用简单的 ECDH 密钥生成
    # 实际项目中应该使用 py_vapid 或类似库
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization

        # 生成私钥
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())

        # 导出公钥
        public_key = private_key.public_key()

        # 序列化为 base64url 格式
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )

        # 转换为 base64url
        def base64url_encode(data):
            return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

        return {
            "private_key": base64url_encode(private_bytes),
            "public_key": base64url_encode(public_bytes[1:])  # 跳过第一个字节 (格式标识)
        }
    except ImportError:
        # 如果 cryptography 不可用，返回占位符
        logger.warning("⚠️ cryptography 库未安装，无法生成 VAPID 密钥")
        return {
            "private_key": "PLACEHOLDER_PRIVATE_KEY",
            "public_key": "PLACEHOLDER_PUBLIC_KEY"
        }
