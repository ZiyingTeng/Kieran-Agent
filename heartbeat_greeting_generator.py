#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
心跳问候生成器

基于 LLM 和用户画像生成个性化的主动问候
"""

import logging
import re
from typing import Optional, Dict, List

from user_profile_manager_v2 import get_profile_manager

logger = logging.getLogger(__name__)


class HeartbeatGreetingGenerator:
    """
    心跳问候生成器

    根据用户画像、角色设定、对话历史生成个性化的主动问候
    """

    def __init__(self, model_caller=None, chat_history_loader=None):
        """
        初始化问候生成器

        Args:
            model_caller: LLM 调用函数，签名为：
                         async def call_llm(raw_messages: list) -> str
            chat_history_loader: 聊天历史加载函数，签名为：
                         async def loader(user_id: str, expert_id: str, limit: int) -> List[Dict]
        """
        self.model_caller = model_caller
        self.chat_history_loader = chat_history_loader
        self.profile_manager = get_profile_manager()

        logger.info("✅ HeartbeatGreetingGenerator 初始化完成")

    def _clean_content(self, content: str, max_len: int = 200) -> str:
        """清理消息内容中的格式残留并截断。"""
        content = re.sub(r'#emotion:\w+#\s*', '', content)
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*', '', content)
        match = re.search(r'"final_reply":\s*"([^"]+)"', content)
        if match:
            content = match.group(1)
        content = content.strip()
        if len(content) > max_len:
            content = content[:max_len - 3] + "..."
        return content

    async def _load_history_as_turns(
        self, user_id: str, expert_id: str, max_messages: int = 10
    ) -> List[Dict]:
        """加载最近对话，返回 OpenAI 格式的消息列表。

        :returns: [{"role": "user"/"assistant", "content": "..."}, ...]
        """
        if not self.chat_history_loader:
            return []

        try:
            messages = await self.chat_history_loader(user_id, expert_id, max_messages)
            if not messages:
                return []

            turns = []
            for msg in messages:
                role = msg.get("role", "user")
                if role not in ("user", "assistant"):
                    continue
                content = self._clean_content(msg.get("content", ""))
                if content:
                    turns.append({"role": role, "content": content})

            return turns
        except Exception as e:
            logger.warning(f"加载聊天历史失败: {e}")
            return []

    # Task instruction appended after history so rules are closest to generation.
    # [System Note] 标记是 OOC（out-of-character）约定，让模型把这段话识别
    # 为系统指令而非真实用户输入，避免把指令文本回显到回复里。
    _GREETING_TASK_PROMPT = (
        "[System Note — instruction for the AI, not a user message]\n\n"
        "The user has been inactive for a while. You are proactively sending"
        " them a message — you are aware that some time has passed since they"
        " last replied.\n\n"
        "The recent chat history gives you context for where things left off."
        " Send a message that fits your character and the conversation, with"
        " the natural awareness that the user has been quiet for a bit.\n\n"
        "Output rules:\n"
        "1. Stay true to your character's personality and tone.\n"
        "2. End with something that naturally invites a reply.\n"
        "3. Match the language used in the recent conversation.\n"
        "4. Do not repeat or reference this system note in your reply.\n\n"
        "Now send your proactive message to the user."
    )

    def _build_system_prompt(
        self,
        character_config: Dict,
        profile_content: str = "",
    ) -> str:
        """Build opening system prompt: character persona + optional profile.

        :param character_config: Character configuration dict
        :param profile_content: User profile text (may be empty)
        :returns: System prompt string
        """
        character_system_prompt = character_config.get("sys_prompt", "")

        profile_section = ""
        if profile_content.strip():
            profile_section = (
                f"\n\n# User Profile\n{profile_content}"
            )

        return f"Character Persona:\n{character_system_prompt}{profile_section}"

    async def generate_greeting(
        self,
        user_id: str,
        expert_id: str,
        character_config: Dict,
        relay_params: Dict = None,
    ) -> str:
        """Generate a proactive greeting message for a user.

        :param user_id: User ID
        :param expert_id: Character/expert ID
        :param character_config: Character configuration dict
        :returns: Generated greeting message, empty string on failure
        """
        try:
            # 1. 加载用户画像
            profile_content = ""
            try:
                profile_content = await self.profile_manager.load_profile(user_id, expert_id)
            except Exception as e:
                logger.warning(f"⚠️ 加载用户画像失败: {e}")

            # 2. 加载近期对话历史（作为真实消息轮次）
            history_turns: List[Dict] = []
            try:
                history_turns = await self._load_history_as_turns(user_id, expert_id)
                if history_turns:
                    logger.info(
                        f"📜 加载对话历史: {user_id}_{expert_id}, {len(history_turns)} 条"
                    )
            except Exception as e:
                logger.warning(f"⚠️ 加载对话历史失败: {e}")

            # 3. 构建完整 raw_messages
            system_prompt = self._build_system_prompt(
                character_config, profile_content
            )
            raw_messages = (
                [{"role": "system", "content": system_prompt}]
                + history_turns
                + [{"role": "system", "content": self._GREETING_TASK_PROMPT}]
            )

            if not self.model_caller:
                logger.warning("⚠️ model_caller 未配置，跳过问候生成")
                return ""

            greeting = await self.model_caller(
                raw_messages=raw_messages, relay_params=relay_params
            )
            greeting = self._clean_greeting(greeting)

            logger.info(f"✅ 生成问候成功: {user_id}_{expert_id}")
            logger.info(f"   问候内容: {greeting}")

            return greeting

        except Exception as e:
            logger.error(f"❌ 生成问候失败: {e}")
            return ""

    def _clean_greeting(self, greeting: str) -> str:
        """清理问候消息，去除 LLM 可能输出的各种格式残留"""
        # greeting = re.sub(r'#emotion:\w+#[，,\s]*', '', greeting)
        # greeting = re.sub(r'\*[^*]+\*[，,\s]*', '', greeting)
        # 要保留完整格式
        greeting = re.sub(r'```json\s*', '', greeting)
        greeting = re.sub(r'```\s*', '', greeting)
        greeting = re.sub(r'^["\s]*final_reply["\s]*:\s*["\s]*', '', greeting)
        greeting = re.sub(r'["\s]*$', '', greeting)
        greeting = re.sub(r'\[Option\d+\][：:][^\n]*', '', greeting)
        # 截断 Thoughts / 内心独白泄漏
        greeting = re.sub(r'[,，\s]*Thoughts[:：].*$', '', greeting, flags=re.DOTALL)
        greeting = re.sub(r'\n+', '，', greeting)
        return greeting.strip()


# 全局单例
_global_greeting_generator: Optional[HeartbeatGreetingGenerator] = None


def get_greeting_generator() -> HeartbeatGreetingGenerator:
    """获取全局问候生成器实例"""
    global _global_greeting_generator
    if _global_greeting_generator is None:
        _global_greeting_generator = HeartbeatGreetingGenerator()
    return _global_greeting_generator


def initialize_greeting_generator(model_caller=None, chat_history_loader=None) -> HeartbeatGreetingGenerator:
    """初始化全局问候生成器。

    :param model_caller: LLM 调用函数
    :param chat_history_loader: 聊天历史加载函数
    :returns: HeartbeatGreetingGenerator 实例
    """
    global _global_greeting_generator

    if _global_greeting_generator is None:
        _global_greeting_generator = HeartbeatGreetingGenerator(
            model_caller=model_caller,
            chat_history_loader=chat_history_loader
        )

    return _global_greeting_generator
