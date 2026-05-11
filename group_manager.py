#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
群组管理模块
实现多智能体群聊功能
"""

from typing import List, Dict, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
import json
import logging
import os

logger = logging.getLogger(__name__)


@dataclass
class GroupMessage:
    """群组消息"""
    sender_id: str          # 发送者ID (user_id 或 girlfriend_id)
    sender_name: str        # 发送者名称
    content: str            # 消息内容
    role: str              # "user" 或 "assistant"
    timestamp: str         # 时间戳
    message_id: str = ""   # 消息唯一ID

    def to_dict(self) -> dict:
        return {
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "content": self.content,
            "role": self.role,
            "timestamp": self.timestamp,
            "message_id": self.message_id
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'GroupMessage':
        return cls(
            sender_id=data["sender_id"],
            sender_name=data["sender_name"],
            content=data["content"],
            role=data["role"],
            timestamp=data["timestamp"],
            message_id=data.get("message_id", "")
        )


@dataclass
class Group:
    """群组配置"""
    group_id: str                  # 群组ID
    group_name: str                # 群组名称
    members: List[str]             # 成员女友ID列表
    owner_id: str                  # 创建者用户ID
    created_at: str                # 创建时间

    # 群组配置
    max_members: int = 10          # 最大成员数
    is_active: bool = True         # 是否活跃

    # 发言规则
    turn_strategy: str = "reaction"  # 发言策略: round_robin, random, reaction
    auto_response: bool = True       # 是否自动让AI回应

    # 场景背景（可选，由用户创建群聊时设定）
    background: str = ""

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "group_name": self.group_name,
            "members": self.members,
            "owner_id": self.owner_id,
            "created_at": self.created_at,
            "max_members": self.max_members,
            "is_active": self.is_active,
            "turn_strategy": self.turn_strategy,
            "auto_response": self.auto_response,
            "background": self.background,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Group':
        return cls(
            group_id=data["group_id"],
            group_name=data["group_name"],
            members=data["members"],
            owner_id=data["owner_id"],
            created_at=data["created_at"],
            max_members=data.get("max_members", 10),
            is_active=data.get("is_active", True),
            turn_strategy=data.get("turn_strategy", "reaction"),
            auto_response=data.get("auto_response", True),
            background=data.get("background", ""),
        )


@dataclass
class GroupSession:
    """群组会话"""
    group_id: str
    messages: List[GroupMessage] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # 发言状态
    current_speaker_index: int = 0
    last_user_message_time: Optional[str] = None

    # 🆕 对话摘要和关键信息记忆
    conversation_summary: str = ""  # 对话摘要
    key_facts: List[str] = field(default_factory=list)  # 关键事实列表

    def add_message(self, message: GroupMessage):
        """添加消息"""
        if not message.message_id:
            message.message_id = f"{self.group_id}_{len(self.messages)}_{int(datetime.now().timestamp())}"
        self.messages.append(message)

    def get_messages(self, limit: Optional[int] = None) -> List[dict]:
        """获取消息历史"""
        msgs = [msg.to_dict() for msg in self.messages]
        if limit and len(msgs) > limit:
            return msgs[-limit:]
        return msgs

    def clear_history(self):
        """清空历史记录"""
        self.messages = []
        self.current_speaker_index = 0
        self.conversation_summary = ""
        self.key_facts = []

    def update_summary(self, new_summary: str, new_facts: List[str] = None):
        """更新对话摘要"""
        self.conversation_summary = new_summary
        if new_facts:
            # 合并关键事实，去重
            for fact in new_facts:
                if fact not in self.key_facts:
                    self.key_facts.append(fact)

    def get_context_for_agent(self, limit: int = 20) -> tuple:
        """
        获取适合Agent的上下文

        Returns:
            (messages_list, summary_text, key_facts_list)
        """
        msgs = self.get_messages(limit)
        summary = self.conversation_summary
        facts = self.key_facts.copy()
        return (msgs, summary, facts)

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "messages": [msg.to_dict() for msg in self.messages],
            "created_at": self.created_at,
            "current_speaker_index": self.current_speaker_index,
            "last_user_message_time": self.last_user_message_time,
            "conversation_summary": self.conversation_summary,
            "key_facts": self.key_facts
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'GroupSession':
        messages = [GroupMessage.from_dict(msg) for msg in data.get("messages", [])]
        return cls(
            group_id=data["group_id"],
            messages=messages,
            created_at=data.get("created_at", datetime.now().isoformat()),
            current_speaker_index=data.get("current_speaker_index", 0),
            last_user_message_time=data.get("last_user_message_time"),
            conversation_summary=data.get("conversation_summary", ""),
            key_facts=data.get("key_facts", [])
        )


class GroupManager:
    """群组管理器"""

    # 数据存储路径 - 使用绝对路径避免工作目录问题
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(_BASE_DIR, "data/groups")
    GROUPS_FILE = os.path.join(DATA_DIR, "groups.json")

    def __init__(self, auto_save: bool = True):
        # 群组配置: group_id -> Group
        self.groups: Dict[str, Group] = {}

        # 群组会话: group_id -> GroupSession
        self.sessions: Dict[str, GroupSession] = {}

        # 用户的所有群组: user_id -> List[group_id]
        self.user_groups: Dict[str, List[str]] = {}

        # 是否自动保存
        self.auto_save = auto_save

        # 文件变更检测（多 worker 同步）
        self._last_file_mtime: float = 0.0

        # 确保数据目录存在
        os.makedirs(self.DATA_DIR, exist_ok=True)

        # 加载已保存的数据
        self.load_from_file()

    def save_to_file(self):
        """保存群组数据到文件"""
        try:
            data = {
                "groups": {gid: g.to_dict() for gid, g in self.groups.items()},
                "sessions": {sid: s.to_dict() for sid, s in self.sessions.items()},
                "user_groups": self.user_groups
            }

            with open(self.GROUPS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 记录写入后的 mtime，避免自己触发 reload
            self._last_file_mtime = os.path.getmtime(self.GROUPS_FILE)
        except Exception as e:
            logger.error(f"保存群组数据失败: {e}")

    def load_from_file(self):
        """从文件加载群组数据"""
        try:
            if not os.path.exists(self.GROUPS_FILE):
                return

            with open(self.GROUPS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 加载群组
            self.groups = {
                gid: Group.from_dict(g_data)
                for gid, g_data in data.get("groups", {}).items()
            }

            # 加载会话
            self.sessions = {
                sid: GroupSession.from_dict(s_data)
                for sid, s_data in data.get("sessions", {}).items()
            }

            # 加载用户群组映射
            self.user_groups = data.get("user_groups", {})

            # 记录文件 mtime
            self._last_file_mtime = os.path.getmtime(self.GROUPS_FILE)

            logger.info(
                f"已加载 {len(self.groups)} 个群组和"
                f" {len(self.sessions)} 个会话"
            )
        except Exception as e:
            logger.error(f"加载群组数据失败: {e}")

    def _reload_if_changed(self):
        """检测文件是否被其他 worker 修改，是则重新加载"""
        try:
            if not os.path.exists(self.GROUPS_FILE):
                return
            current_mtime = os.path.getmtime(self.GROUPS_FILE)
            if current_mtime > self._last_file_mtime:
                logger.info("检测到 groups.json 被其他进程更新，重新加载")
                self.load_from_file()
        except Exception as e:
            logger.warning(f"检测文件变更失败: {e}")

    def create_group(
        self,
        group_name: str,
        members: List[str],
        owner_id: str,
        turn_strategy: str = "reaction",
        auto_response: bool = True,
        background: str = "",
    ) -> str:
        """
        创建群组

        Args:
            group_name: 群组名称
            members: 成员女友ID列表
            owner_id: 创建者用户ID
            turn_strategy: 发言策略
            auto_response: 是否自动回应

        Returns:
            群组ID
        """
        # 生成群组ID
        group_id = f"group_{owner_id}_{int(datetime.now().timestamp())}"

        # 创建群组
        group = Group(
            group_id=group_id,
            group_name=group_name,
            members=members,
            owner_id=owner_id,
            created_at=datetime.now().isoformat(),
            turn_strategy=turn_strategy,
            auto_response=auto_response,
            background=background,
        )

        # 创建群组会话
        session = GroupSession(group_id=group_id)

        # 保存
        self.groups[group_id] = group
        self.sessions[group_id] = session

        # 添加到用户的群组列表
        if owner_id not in self.user_groups:
            self.user_groups[owner_id] = []
        self.user_groups[owner_id].append(group_id)

        # 自动保存
        if self.auto_save:
            self.save_to_file()

        return group_id

    def get_group(self, group_id: str) -> Optional[Group]:
        """获取群组配置"""
        self._reload_if_changed()
        return self.groups.get(group_id)

    def get_group_session(self, group_id: str) -> Optional[GroupSession]:
        """获取群组会话"""
        self._reload_if_changed()
        return self.sessions.get(group_id)

    def get_user_groups(self, user_id: str) -> List[Group]:
        """获取用户的所有群组"""
        self._reload_if_changed()
        group_ids = self.user_groups.get(user_id, [])
        return [self.groups[gid] for gid in group_ids if gid in self.groups]

    def add_member(self, group_id: str, girlfriend_id: str) -> bool:
        """添加成员到群组"""
        group = self.get_group(group_id)
        if not group:
            return False

        if girlfriend_id in group.members:
            return False  # 已存在

        if len(group.members) >= group.max_members:
            return False  # 达到上限

        group.members.append(girlfriend_id)

        if self.auto_save:
            self.save_to_file()

        return True

    def remove_member(self, group_id: str, girlfriend_id: str) -> bool:
        """从群组移除成员"""
        group = self.get_group(group_id)
        if not group:
            return False

        if girlfriend_id not in group.members:
            return False

        group.members.remove(girlfriend_id)

        if self.auto_save:
            self.save_to_file()

        return True

    def update_name(self, group_id: str, new_name: str) -> bool:
        """更新群组名称"""
        group = self.get_group(group_id)
        if not group:
            return False

        if not new_name or not new_name.strip():
            return False

        group.group_name = new_name.strip()

        if self.auto_save:
            self.save_to_file()

        return True

    def delete_group(self, group_id: str, user_id: str) -> bool:
        """删除群组"""
        group = self.get_group(group_id)
        if not group or group.owner_id != user_id:
            return False

        # 删除群组和会话
        del self.groups[group_id]
        if group_id in self.sessions:
            del self.sessions[group_id]

        # 从用户群组列表中移除
        if user_id in self.user_groups and group_id in self.user_groups[user_id]:
            self.user_groups[user_id].remove(group_id)

        if self.auto_save:
            self.save_to_file()

        return True

    def add_message(
        self,
        group_id: str,
        sender_id: str,
        sender_name: str,
        content: str,
        role: str = "user"
    ) -> Optional[GroupMessage]:
        """
        添加消息到群组

        Args:
            group_id: 群组ID
            sender_id: 发送者ID
            sender_name: 发送者名称
            content: 消息内容
            role: 角色 (user/assistant)

        Returns:
            创建的消息对象，失败返回None
        """
        session = self.get_group_session(group_id)
        if not session:
            return None

        message = GroupMessage(
            sender_id=sender_id,
            sender_name=sender_name,
            content=content,
            role=role,
            timestamp=datetime.now().isoformat()
        )

        session.add_message(message)

        # 如果是用户消息，更新最后发言时间
        if role == "user":
            session.last_user_message_time = message.timestamp

        # 自动保存
        if self.auto_save:
            self.save_to_file()

        return message

    def get_group_messages(
        self,
        group_id: str,
        limit: Optional[int] = None
    ) -> List[dict]:
        """获取群组消息历史"""
        session = self.get_group_session(group_id)
        if not session:
            return []
        return session.get_messages(limit)

    def clear_group_messages(self, group_id: str) -> bool:
        """清空群组消息历史"""
        session = self.get_group_session(group_id)
        if not session:
            return False
        session.clear_history()

        if self.auto_save:
            self.save_to_file()

        return True

    def detect_mentioned_members(
        self,
        group_id: str,
        message: str,
        girlfriend_names: Dict[str, str]
    ) -> List[str]:
        """
        检测消息中被提到的成员

        Args:
            group_id: 群组ID
            message: 消息内容
            girlfriend_names: girlfriend_id -> name 的映射

        Returns:
            被提到的成员ID列表
        """
        group = self.get_group(group_id)
        if not group:
            return []

        mentioned = []
        message_lower = message.lower()

        for girlfriend_id in group.members:
            name = girlfriend_names.get(girlfriend_id, "")
            if name and name in message:
                mentioned.append(girlfriend_id)

        return mentioned

    def get_member_response_order(
        self,
        group_id: str,
        last_message: GroupMessage
    ) -> List[str]:
        """
        根据发言策略获取回应的成员顺序

        Args:
            group_id: 群组ID
            last_message: 最后一条消息

        Returns:
            应该回应的成员ID列表
        """
        group = self.get_group(group_id)
        if not group:
            return []

        session = self.get_group_session(group_id)

        if group.turn_strategy == "round_robin":
            # 轮流发言：从当前发言者开始
            members = group.members
            start_idx = session.current_speaker_index % len(members)
            ordered_members = members[start_idx:] + members[:start_idx]

            # 更新下次发言者
            session.current_speaker_index = (start_idx + 1) % len(members)
            return ordered_members

        elif group.turn_strategy == "random":
            # 随机选择一个成员
            import random
            return [random.choice(group.members)] if group.members else []

        else:  # reaction
            # 反应触发：所有成员都可以回应
            # 这里返回所有成员，实际是否回应由Agent决定
            return group.members.copy()

    def get_group_context_for_agent(
        self,
        group_id: str,
        girlfriend_id: str,
        limit: int = 20
    ) -> dict:
        """
        为特定Agent获取群组上下文（包含摘要和关键事实）

        Args:
            group_id: 群组ID
            girlfriend_id: 女友ID
            limit: 消息数量限制

        Returns:
            {
                "messages": 格式化的消息上下文列表,
                "summary": 对话摘要,
                "key_facts": 关键事实列表,
                "full_context": 完整上下文字符串
            }
        """
        session = self.get_group_session(group_id)
        if not session:
            return {
                "messages": [],
                "summary": "",
                "key_facts": [],
                "full_context": ""
            }

        messages = session.get_messages(limit)

        # 转换为Agent可理解的格式
        context = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "assistant"

            # 如果是assistant消息，检查是否是自己发的
            if role == "assistant":
                if msg["sender_id"] == girlfriend_id:
                    # 自己的消息，可以标记为特殊角色
                    context.append({
                        "role": "assistant",  # 自己之前的发言
                        "content": f"{msg['sender_name']}: {msg['content']}",
                        "name": msg["sender_name"]
                    })
                else:
                    # 其他AI的消息，当作用户消息处理（因为这是群聊上下文）
                    context.append({
                        "role": "user",  # 其他人的发言
                        "content": f"{msg['sender_name']}: {msg['content']}",
                        "name": msg["sender_name"]
                    })
            else:
                # 用户消息
                context.append({
                    "role": "user",
                    "content": f"{msg['sender_name']}: {msg['content']}",
                    "name": msg["sender_name"]
                })

        # 构建完整上下文（包含摘要和关键事实）
        summary = session.conversation_summary or "暂无对话摘要"
        key_facts = session.key_facts or []

        # 组装完整上下文
        full_context_parts = []
        if summary:
            full_context_parts.append(f"【对话摘要】\n{summary}")
        if key_facts:
            full_context_parts.append(f"【重要信息】\n" + "\n".join(f"- {fact}" for fact in key_facts))
        full_context_parts.append(f"【最近对话】")

        return {
            "messages": context,
            "summary": summary,
            "key_facts": key_facts,
            "full_context": "\n".join(full_context_parts)
        }

    def get_stats(self) -> dict:
        """获取群组统计信息"""
        return {
            "total_groups": len(self.groups),
            "active_groups": sum(1 for g in self.groups.values() if g.is_active),
            "total_messages": sum(len(s.messages) for s in self.sessions.values())
        }
