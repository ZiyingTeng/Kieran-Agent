#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
消息重新生成管理器

处理用户点击"重新生成"时的多重记忆清理问题：

1. 短期记忆 (InMemoryMemory) - 弹出最后一条AI消息
2. 长期记忆 (PostgreSQL/Chroma) - 标记为已替换（软删除）
3. 用户画像 (user_profile.md) - 标记相关段落为待更新

策略：
- 采用"标记方案"而非硬删除，避免数据丢失
- 为每条消息添加唯一ID和状态标记
- 软删除：标记为"superseded"（被替换）
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class MessageMetadata:
    """消息元数据"""
    message_id: str
    role: str
    content: str
    timestamp: str
    status: str = "active"  # active / superseded / deleted
    superseded_by: Optional[str] = None
    superseded_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "status": self.status,
            "superseded_by": self.superseded_by,
            "superseded_at": self.superseded_at,
        }


class MessageRegenerationManager:
    """
    消息重新生成管理器

    管理消息的重新生成流程，确保多重记忆系统的一致性
    """

    def __init__(self):
        # 消息元数据注册表: {session_id: [MessageMetadata, ...]}
        self._message_registry: Dict[str, List[MessageMetadata]] = {}
        # 统计
        self._total_regenerations: int = 0

    def generate_message_id(self) -> str:
        """生成唯一消息ID"""
        return str(uuid.uuid4())

    def register_message(
        self,
        session_id: str,
        role: str,
        content: str,
        timestamp: Optional[str] = None,
    ) -> str:
        """
        注册消息到元数据注册表

        Args:
            session_id: 会话ID
            role: 角色 ("user" or "assistant")
            content: 消息内容
            timestamp: 时间戳

        Returns:
            str: 消息ID
        """
        msg_id = self.generate_message_id()
        metadata = MessageMetadata(
            message_id=msg_id,
            role=role,
            content=content,
            timestamp=timestamp or datetime.now().isoformat(),
        )

        if session_id not in self._message_registry:
            self._message_registry[session_id] = []
        self._message_registry[session_id].append(metadata)

        logger.info(f"📝 注册消息: {msg_id}")
        return msg_id

    async def handle_regeneration(
        self,
        session_id: str,
        user_message_id: Optional[str],
        old_assistant_message_id: Optional[str],
        memory,
        long_term_memory,
        user_id: str,
        expert_id: str,
    ) -> Dict[str, Any]:
        """
        处理消息重新生成

        Args:
            session_id: 会话ID
            user_message_id: 用户消息ID
            old_assistant_message_id: 要替换的AI消息ID
            memory: 短期记忆对象 (InMemoryMemory)
            long_term_memory: 长期记忆对象
            user_id: 用户ID
            expert_id: 角色ID

        Returns:
            Dict: 操作结果
        """
        try:
            results = {}

            # 1. 清理短期记忆
            results["short_memory_cleaned"] = self._clean_short_term_memory(
                memory, old_assistant_message_id
            )
            logger.info(f"✅ 短期记忆已清理: {old_assistant_message_id}")

            # 2. 标记长期记忆
            results["long_memory_marked"] = await self._mark_long_term_memory(
                long_term_memory, old_assistant_message_id
            )
            logger.info(f"✅ 长期记忆已标记: {old_assistant_message_id}")

            # 3. 标记用户画像
            results["user_profile_flagged"] = self._flag_user_profile(
                user_id, expert_id, old_assistant_message_id
            )
            logger.info(f"✅ 用户画像已标记: {old_assistant_message_id}")

            # 4. 更新元数据注册表
            self._update_message_registry(session_id, old_assistant_message_id)

            results["success"] = True
            self._total_regenerations += 1

            return results

        except Exception as e:
            logger.error(f"处理重新生成失败: {e}")
            return {"success": False, "errors": str(e)}

    def _clean_short_term_memory(self, memory, message_id: Optional[str]) -> bool:
        """
        清理短期记忆中的消息

        Args:
            memory: InMemoryMemory 对象
            message_id: 消息ID

        Returns:
            bool: 是否成功清理
        """
        try:
            if hasattr(memory, "content") and len(memory.content) > 0:
                last_msg = memory.content[-1]
                if isinstance(last_msg, tuple):
                    last_msg = last_msg[0]

                if hasattr(last_msg, "role") and last_msg.role == "assistant":
                    memory.content.pop()
                    logger.info(f"🗑️  已从短期记忆删除: {message_id}")
                    return True
            return False
        except Exception as e:
            logger.error(f"清理短期记忆失败: {e}")
            return False

    async def _mark_long_term_memory(
        self, long_term_memory, message_id: Optional[str]
    ) -> bool:
        """
        标记长期记忆中的消息为已替换（软删除）

        Args:
            long_term_memory: 长期记忆对象
            message_id: 消息ID

        Returns:
            bool: 是否成功标记
        """
        try:
            if long_term_memory and hasattr(long_term_memory, "add_string"):
                await long_term_memory.add_string(
                    f"[SYSTEM_MARKER] Message {message_id} has been superseded by regeneration.",
                    metadata={"type": "superseded_marker"},
                )
                logger.info(f"🏴 已标记长期记忆: {message_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"标记长期记忆失败: {e}")
            return False

    def _flag_user_profile(
        self, user_id: str, expert_id: str, message_id: Optional[str]
    ) -> bool:
        """
        标记用户画像中相关内容为待更新

        Args:
            user_id: 用户ID
            expert_id: 角色ID
            message_id: 消息ID

        Returns:
            bool: 是否成功标记
        """
        try:
            # 结构化画像（V2）从 mem0 事实全量重建，无需标记
            # 下次总结时会自动包含最新状态
            logger.info(f"🏴 用户画像标记（跳过，V2 自动重建）: {message_id}")
            return True
        except Exception as e:
            logger.error(f"标记用户画像失败: {e}")
            return False

    def _update_message_registry(
        self, session_id: str, old_message_id: Optional[str]
    ):
        """
        更新消息元数据注册表

        Args:
            session_id: 会话ID
            old_message_id: 被替换的消息ID
        """
        if session_id in self._message_registry:
            for msg in self._message_registry[session_id]:
                if msg.message_id == old_message_id:
                    msg.status = "superseded"
                    msg.superseded_at = datetime.now().isoformat()
                    logger.info(f"📝 更新元数据: {old_message_id} -> superseded")
                    break

    def get_message_history(
        self, session_id: str, include_superseded: bool = False
    ) -> List[Dict[str, Any]]:
        """
        获取消息历史

        Args:
            session_id: 会话ID
            include_superseded: 是否包含被替换的消息

        Returns:
            消息历史列表
        """
        if session_id not in self._message_registry:
            return []

        messages = self._message_registry[session_id]
        if include_superseded:
            return [m.to_dict() for m in messages]
        else:
            return [m.to_dict() for m in messages if m.status == "active"]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_regenerations": self._total_regenerations,
            "registered_messages": sum(
                len(msgs) for msgs in self._message_registry.values()
            ),
        }


# 全局单例
_global_regeneration_manager: Optional[MessageRegenerationManager] = None


def get_regeneration_manager() -> MessageRegenerationManager:
    """获取全局重新生成管理器实例"""
    global _global_regeneration_manager
    if _global_regeneration_manager is None:
        _global_regeneration_manager = MessageRegenerationManager()
    return _global_regeneration_manager
