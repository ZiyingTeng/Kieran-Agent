#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FCM (Firebase Cloud Messaging) 提供商

支持 Android 和 Web 推送
"""

import logging
from typing import Dict, Any, List
from pathlib import Path

from .base import BasePushProvider
from ..config import get_config

logger = logging.getLogger(__name__)

# 可选导入
try:
    from pyfcm import FCMNotification
    PYFCM_AVAILABLE = True
except ImportError:
    PYFCM_AVAILABLE = False
    logger.warning("⚠️ pyfcm 未安装，FCM 将不可用")


class FCMProvider(BasePushProvider):
    """
    FCM 推送提供商

    支持:
    - Android 推送 (通过 FCM)
    - Web 推送 (通过 FCM)
    """

    def __init__(self):
        """初始化 FCM 提供商"""
        super().__init__("android")
        self.config = get_config()
        self._client = None

    async def initialize(self):
        """初始化提供商"""
        if not PYFCM_AVAILABLE:
            logger.warning("pyfcm 未安装，FCM Provider 不可用")
            self._initialized = False
            return

        # 检查配置
        has_credentials = (
            self.config.fcm_credentials_path and
            Path(self.config.fcm_credentials_path).exists()
        )
        has_api_key = bool(self.config.fcm_api_key)

        if not has_credentials and not has_api_key:
            logger.warning("⚠️ FCM 凭证未配置，FCM 将不可用")
            self._initialized = False
            return

        try:

            if has_credentials:
                self._client = FCMNotification(
                    service_credentials_file=self.config.fcm_credentials_path
                )
            else:
                self._client = FCMNotification(api_key=self.config.fcm_api_key)

            self._initialized = True
            logger.info("✅ FCM Provider 初始化完成")

        except ImportError:
            logger.warning("⚠️ pyfcm 未安装，FCM 将不可用")
            self._initialized = False
        except Exception as e:
            logger.error(f"❌ FCM 初始化失败: {e}")
            self._initialized = False

    async def send(
        self,
        token: str,
        title: str,
        body: str,
        data: Dict[str, Any] = None
    ) -> bool:
        """
        发送 FCM 推送通知

        Args:
            token: 设备令牌
            title: 标题
            body: 消息内容
            data: 附加数据

        Returns:
            bool: 是否成功
        """
        if not self._initialized or not self._client:
            logger.warning("FCM Provider 未初始化")
            return False

        try:
            data = data or {}

            # 发送通知
            result = self._client.notify_single_device(
                registration_id=token,
                message_title=title,
                message_body=body,
                data_message=data,
                sound='default',
                badge=1
            )

            # 检查结果
            if result.get('success') == 1:
                self._log_send(True, token)
                return True
            else:
                error = result.get('results', [{}])[0].get('error', 'Unknown')
                self._log_send(False, token, error)

                # 检查是否是无效令牌
                if error in ('InvalidRegistration', 'NotRegistered', 'MismatchSenderId'):
                    logger.warning(f"⚠️ FCM 令牌已失效，需要清理: {token[:20]}...")

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
        批量发送 FCM 推送通知

        Args:
            tokens: 设备令牌列表
            title: 标题
            body: 消息内容
            data: 附加数据

        Returns:
            Dict[str, bool]: 每个令牌的发送结果
        """
        if not self._initialized or not self._client:
            logger.warning("FCM Provider 未初始化")
            return {token: False for token in tokens}

        try:
            data = data or {}

            # FCM 批量发送限制: 最多 1000 个令牌
            chunks = [tokens[i:i + 1000] for i in range(0, len(tokens), 1000)]
            results = {}

            for chunk in chunks:
                result = self._client.notify_multiple_devices(
                    registration_ids=chunk,
                    message_title=title,
                    message_body=body,
                    data_message=data,
                    sound='default',
                    badge=1
                )

                # 解析结果
                for i, token in enumerate(chunk):
                    if i < len(result.get('results', [])):
                        error = result['results'][i].get('error')
                        results[token] = error is None

                        if error in ('InvalidRegistration', 'NotRegistered'):
                            logger.warning(f"⚠️ FCM 令牌已失效: {token[:20]}...")
                    else:
                        results[token] = False

            return results

        except Exception as e:
            logger.error(f"❌ FCM 批量发送失败: {e}")
            return {token: False for token in tokens}

    async def send_to_topic(
        self,
        topic: str,
        title: str,
        body: str,
        data: Dict[str, Any] = None
    ) -> bool:
        """
        向主题发送推送

        Args:
            topic: 主题名称
            title: 标题
            body: 消息内容
            data: 附加数据

        Returns:
            bool: 是否成功
        """
        if not self._initialized or not self._client:
            return False

        try:
            result = self._client.notify_topic_subscribers(
                topic_name=topic,
                message_title=title,
                message_body=body,
                data_message=data
            )

            return result.get('success') == 1

        except Exception as e:
            logger.error(f"❌ FCM 主题推送失败: {e}")
            return False
