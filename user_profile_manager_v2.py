#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户画像管理器 V2 — 结构化记忆表

核心改进（相比旧版）：
1. 用 mem0 提取的事实作为输入（而非原始对话历史）
2. 输出结构化 JSON 而非自由文本 markdown
3. LLM 将事实分类到 5 张语义表中
4. 增量更新：每次总结合并新旧画像

语义表：
- user_traits: 用户基本信息、性格、身份
- relationship: 用户与角色的关系状态
- events: 重要事件和经历
- preferences: 用户偏好和习惯
- agreements: 约定、承诺、任务
"""

import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import aiofiles
import re

logger = logging.getLogger(__name__)

# 结构化画像 JSON 的版本号
PROFILE_VERSION = 2

# 5-table semantic schema definitions
TABLE_DEFINITIONS = {
    "user_traits": (
        "The user's personal attributes, identity, and character — "
        "e.g. name, age, occupation, personality traits, appearance"
    ),
    "relationship": (
        "The relational state and emotional connection between the user "
        "and the AI character — e.g. nicknames, intimacy level, "
        "relationship progression, mutual attitudes"
    ),
    "events": (
        "Significant events or experiences that occurred during "
        "conversations — e.g. dates, arguments, shared secrets, "
        "anniversaries, milestones"
    ),
    "preferences": (
        "Likes, dislikes, habits, and lifestyle preferences explicitly "
        "expressed by the user — e.g. favourite food, music, activities, "
        "daily routines"
    ),
    "agreements": (
        "Commitments, promises, or action items between the user and the "
        "AI character — e.g. plans to meet, mutual pledges, pending tasks"
    ),
}

# Table labels used when formatting profiles for prompt injection
TABLE_LABELS = {
    "user_traits": "User Traits",
    "relationship": "Relationship",
    "events": "Key Events",
    "preferences": "Preferences",
    "agreements": "Agreements",
}


def _make_empty_profile(user_id: str, expert_id: str) -> Dict[str, Any]:
    """创建空的结构化画像"""
    return {
        "version": PROFILE_VERSION,
        "user_id": user_id,
        "expert_id": expert_id,
        "updated_at": datetime.now().isoformat(),
        "tables": {name: [] for name in TABLE_DEFINITIONS},
    }


class UserProfileManagerUniversal:
    """用户画像管理器 — 结构化记忆表版本"""

    # Primary prompt: merge mem0 facts + existing profile into structured JSON
    ORGANIZE_PROMPT = """You are a user-profile curator for an AI companion system. \
Your task is to synthesise raw memory facts into a qualitative character portrait \
of the user. Do NOT simply copy facts — instead, distil patterns, tendencies, and \
emotional characteristics that help the AI understand who this person is.

## Today's Date
{today} (UTC)

**Timezone note**: All dates are in UTC. The user is likely speaking from a \
local timezone which can differ from UTC by up to ±14 hours, so when they say \
things like "last night" or "yesterday" the actual UTC date may shift by one \
day. When writing event time markers, prefer the precise [YYYY-MM-DD] date \
from the fact prefix, but in the event's description use slightly fuzzy \
phrasing like "around that time" / "that night" rather than asserting an \
exact moment, so the AI doesn't contradict the user's local-time framing.

## Raw Memory Facts
(Each fact may be prefixed with [YYYY-MM-DD] showing when it was originally \
recorded in UTC — use these dates to set time markers on events.)
{facts_text}

## Existing Profile
{existing_text}

Synthesise everything into the five tables below and output valid JSON only \
(no markdown fences, no extra text):

1. user_traits   — {def_user_traits}
2. relationship  — {def_relationship}
3. events        — {def_events}
4. preferences   — {def_preferences}
5. agreements    — {def_agreements}

Output schema:
{{
  "user_traits": ["qualitative description 1", "qualitative description 2"],
  "relationship": ["qualitative description 1"],
  "events": ["[YYYY-MM-DD] event description 1"],
  "preferences": ["qualitative description 1"],
  "agreements": ["qualitative description 1"]
}}

Rules:
- SYNTHESISE, do not copy raw facts verbatim. \
  Bad: "User said they are tired today." \
  Good: "Tends to feel drained after demanding workdays and will openly say so."
- Merge multiple related facts into one generalised insight where possible. \
  Bad: "Likes spicy hot pot" + "Likes spicy food" → duplicate. \
  Good: "Has a strong preference for spicy, bold-flavoured food (e.g. hot pot)."
- You MAY infer reasonable patterns from repeated behaviour, but flag uncertainty \
  with "seems to" or "tends to" rather than asserting as absolute fact.
- **Record only the USER's own attributes, actions, statements, or experiences;
  NEVER record the AI character's behaviour, dialogue, or attitudes — even
  when the raw fact describes them.** Some raw facts may be polluted and
  describe what the AI character said or did rather than the user. Before
  writing any entry, identify whose action/state the underlying fact is
  about; if it is the AI character (or an unclear/ambiguous subject), drop
  it entirely. When in doubt, skip rather than guess.
- Deduplicate: if the existing profile already captures a trait well, keep it \
  unchanged unless newer facts update or contradict it.
- Each entry must be one concise sentence (≤ 25 words).
- **For "events" entries, prefix with a time marker in square brackets**: \
  prefer the exact date from the fact's [YYYY-MM-DD] prefix (e.g. \
  "[2026-05-10] Late-night walk along the beach, intimate mood, user broached \
  meeting the AI's parents."). If no date is available, fall back to a relative \
  marker like "[recently]" or "[last week]". This lets the AI place events on \
  a timeline when the user references "that night" / "last week".
- Use an empty array [] for any table with no relevant information.
- LANGUAGE: write every entry in English. The profile will be injected into \
  the system prompt across a multilingual user base; English is the neutral \
  carrier that minimises interference with the AI's language detection when \
  replying to the user. If a name, place, or concept from the user's own \
  language has no natural English equivalent, keep the original term verbatim \
  (transliteration optional). Do not translate the user's preferred name or \
  nicknames; quote them as-is.
- **SIZE LIMITS — enforce on EVERY synthesis, even when no new facts are
  present.** Cap each table at: user_traits ≤ 10, relationship ≤ 10,
  events ≤ 20, preferences ≤ 15, agreements ≤ 10. When a table is over
  its cap, do NOT simply drop excess entries; merge the OLDEST entries
  (for events use the [YYYY-MM-DD] prefix to identify oldest; for the
  other tables use the order of the existing array, treating the front
  as older) into a single concise summary entry that preserves the gist
  of what was merged. For events specifically, the merged summary entry
  should carry a fuzzy time marker like "[before YYYY-MM]" or "[earlier]"
  so the AI still knows the merged batch came from older history. Always
  keep the most recent / most specific entries verbatim; only compress
  the historical tail.
- If there is nothing new to add or change AND every table is already
  within its size cap, reproduce the existing profile unchanged.
"""

    # Fallback prompt: extract profile directly from conversation history
    FALLBACK_PROMPT = """You are a user-profile curator for an AI companion system. \
Analyse the conversation history below and extract factual information about \
the USER into a structured JSON profile.

## Conversation History
{conversation_history}

## Existing Profile
{existing_text}

Classify the extracted information into the five tables below and output valid \
JSON only (no markdown fences, no extra text):

1. user_traits   — personal attributes, identity, and character of the user
2. relationship  — relational state and emotional connection with the AI character
3. events        — significant events or experiences that occurred
4. preferences   — likes, dislikes, habits, and lifestyle preferences
5. agreements    — commitments, promises, or action items

Output schema:
{{
  "user_traits": ["concise fact 1", "concise fact 2"],
  "relationship": ["concise fact 1"],
  "events": ["concise fact 1"],
  "preferences": ["concise fact 1"],
  "agreements": ["concise fact 1"]
}}

Rules:
- Record only facts about the USER; never record traits of the AI character.
- Deduplicate: merge overlapping entries into the most informative version.
- Each entry must be one concise sentence (≤ 20 words).
- Use an empty array [] for any table with no relevant information.
- LANGUAGE: write every entry in the same language as the user's messages \
in the conversation. Do not translate.
- If nothing new can be extracted, output {{"no_update": true}}.
"""

    def __init__(self, profiles_dir: str = "user_profiles"):
        """初始化用户画像管理器"""
        self.profiles_dir = Path(profiles_dir)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        # 对话轮次追踪
        self._conversation_rounds: Dict[str, int] = {}
        self._last_summary_time: Dict[str, datetime] = {}

    # ============= 路径与键 =============

    def _get_profile_key(self, user_id: str, expert_id: str) -> str:
        return f"{user_id}_{expert_id}"

    def _get_profile_path(self, user_id: str, expert_id: str) -> Path:
        """获取 JSON 画像文件路径"""
        return self.profiles_dir / f"{user_id}_{expert_id}.json"

    def _get_rounds_path(self, user_id: str, expert_id: str) -> Path:
        return self.profiles_dir / f".{user_id}_{expert_id}_rounds.json"

    # ============= 轮次追踪 =============

    def increment_round(self, user_id: str, expert_id: str) -> int:
        key = self._get_profile_key(user_id, expert_id)
        current_round = self._conversation_rounds.get(key, 0)

        if current_round == 0:
            rounds_file = self._get_rounds_path(user_id, expert_id)
            if rounds_file.exists():
                try:
                    with open(rounds_file, 'r') as f:
                        data = json.load(f)
                        current_round = data.get('round', 0)
                except Exception:
                    current_round = 0

        current_round += 1
        self._conversation_rounds[key] = current_round
        self._save_rounds(user_id, expert_id, current_round)

        logger.debug(f"对话轮次: {user_id} + {expert_id} = 第 {current_round} 轮")
        return current_round

    def _save_rounds(self, user_id: str, expert_id: str, rounds: int):
        rounds_file = self._get_rounds_path(user_id, expert_id)
        try:
            with open(rounds_file, 'w') as f:
                json.dump({
                    'round': rounds,
                    'updated_at': datetime.now().isoformat()
                }, f)
        except Exception as e:
            logger.error(f"保存轮次失败: {e}")

    def reset_rounds(self, user_id: str, expert_id: str):
        key = self._get_profile_key(user_id, expert_id)
        self._conversation_rounds[key] = 0
        self._save_rounds(user_id, expert_id, 0)

    def should_trigger_summary(self, user_id: str, expert_id: str, rounds: int) -> bool:
        return rounds % 5 == 0

    # ============= 核心：总结并保存 =============

    async def summarize_and_save(
        self,
        user_id: str,
        expert_id: str,
        model_caller: callable,
        long_term_memory=None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        """
        从 mem0 事实（或对话历史）整理结构化用户画像

        Args:
            user_id: 用户ID
            expert_id: 角色ID
            model_caller: LLM 调用函数 (prompt: str) -> str
            long_term_memory: Mem0LongTermMemory 对象（优先使用）
            conversation_history: 对话历史字典列表（降级方案）

        Returns:
            更新后的画像摘要文本，或 None
        """
        try:
            # 1. 加载现有画像
            existing_profile = await self._load_profile_json(user_id, expert_id)
            existing_text = self._profile_to_text(existing_profile)

            # 2. 获取 mem0 事实（优先），否则用对话历史
            facts_text = None
            if long_term_memory is not None:
                facts_text = await self._fetch_mem0_facts(long_term_memory, user_id)

            if facts_text:
                # 使用 mem0 事实
                prompt = self.ORGANIZE_PROMPT.format(
                    today=datetime.now().strftime("%Y-%m-%d"),
                    facts_text=facts_text,
                    existing_text=existing_text or "（暂无）",
                    def_user_traits=TABLE_DEFINITIONS["user_traits"],
                    def_relationship=TABLE_DEFINITIONS["relationship"],
                    def_events=TABLE_DEFINITIONS["events"],
                    def_preferences=TABLE_DEFINITIONS["preferences"],
                    def_agreements=TABLE_DEFINITIONS["agreements"],
                )
                logger.info(f"使用 mem0 事实整理画像: {user_id} + {expert_id}")
            elif conversation_history:
                # 降级：使用对话历史
                history_text = self._format_conversation_history(conversation_history)
                prompt = self.FALLBACK_PROMPT.format(
                    conversation_history=history_text,
                    existing_text=existing_text or "（暂无）",
                )
                logger.info(f"使用对话历史整理画像（降级）: {user_id} + {expert_id}")
            else:
                logger.warning(f"无数据源可用，跳过画像更新: {user_id} + {expert_id}")
                return None

            # 3. 调用 LLM
            logger.info(f"开始整理用户画像: {user_id} + {expert_id}")
            raw_response = await model_caller(prompt)

            if not raw_response:
                logger.warning("LLM 返回空响应")
                return None

            # 4. 解析 JSON
            new_tables = self._parse_llm_response(raw_response)
            if new_tables is None:
                logger.warning(f"LLM 响应解析失败，保留现有画像")
                return None

            if new_tables.get("no_update"):
                logger.info("本次无新发现，跳过保存")
                return None

            # 5. 构建并保存新画像
            new_profile = _make_empty_profile(user_id, expert_id)
            for table_name in TABLE_DEFINITIONS:
                entries = new_tables.get(table_name, [])
                if isinstance(entries, list):
                    new_profile["tables"][table_name] = entries

            await self._save_profile_json(user_id, expert_id, new_profile)

            key = self._get_profile_key(user_id, expert_id)
            self._last_summary_time[key] = datetime.now()

            summary_text = self._profile_to_text(new_profile)
            logger.info(f"用户画像已更新: {user_id} + {expert_id}")
            return summary_text

        except Exception as e:
            logger.error(f"整理用户画像失败: {e}", exc_info=True)
            return None

    # ============= mem0 事实获取 =============

    async def _fetch_mem0_facts(self, long_term_memory, user_id: str) -> Optional[str]:
        """从 mem0 获取所有事实

        Args:
            long_term_memory: Mem0LongTermMemory 对象
            user_id: 用户ID

        Returns:
            格式化的事实文本，或 None
        """
        try:
            # 访问底层 mem0 AsyncMemory 客户端
            mem0_client = getattr(long_term_memory, 'long_term_working_memory', None)
            if mem0_client is None:
                logger.warning("无法获取 mem0 客户端")
                return None

            # 获取该用户的所有记忆
            result = await mem0_client.get_all(
                user_id=getattr(long_term_memory, 'user_id', user_id),
                limit=100,
            )

            # 解析结果
            memories = []
            if isinstance(result, dict):
                memories = result.get("results", [])
            elif isinstance(result, list):
                memories = result

            if not memories:
                logger.info(f"mem0 中无事实: {user_id}")
                return None

            # 格式化为文本（保留时间戳信息，供 ORGANIZE_PROMPT 给 events
            # 打时间标记。Mem0 的字段里通常有 updated_at / created_at，
            # 形如 "2026-05-10T14:23:01.000000-07:00"，我们只取日期部分。）
            lines = []
            for mem in memories:
                if isinstance(mem, dict):
                    text = mem.get("memory", "") or mem.get("content", "")
                    if text:
                        ts = (
                            mem.get("updated_at")
                            or mem.get("created_at")
                            or ""
                        )
                        ts_prefix = f"[{ts[:10]}] " if len(ts) >= 10 else ""
                        lines.append(f"- {ts_prefix}{text}")
                elif isinstance(mem, str):
                    lines.append(f"- {mem}")

            if not lines:
                return None

            logger.info(f"获取到 {len(lines)} 条 mem0 事实: {user_id}")
            return "\n".join(lines)

        except Exception as e:
            logger.error(f"获取 mem0 事实失败: {e}")
            return None

    # ============= 对话历史格式化（降级方案） =============

    def _format_conversation_history(self, history: List[Dict[str, Any]]) -> str:
        lines = []
        for i, msg in enumerate(history, 1):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')

            if isinstance(content, list) and content:
                for item in content:
                    if isinstance(item, dict) and 'text' in item:
                        content = item['text']
                        break

            if isinstance(content, str):
                content = re.sub(r'```json\s*\n?', '', content)
                content = re.sub(r'```\s*$', '', content)
                if 'final_reply' in content:
                    match = re.search(r'"final_reply":\s*"([^"]+)"', content)
                    if match:
                        content = match.group(1)

            if role == 'user':
                name = msg.get('name', '用户')
                lines.append(f"{i}. {name}: {content}")
            elif role == 'assistant':
                name = msg.get('name', 'AI')
                lines.append(f"   {name}: {content}")

        return '\n'.join(lines)

    # ============= LLM 响应解析 =============

    def _parse_llm_response(self, raw: str) -> Optional[Dict[str, Any]]:
        """从 LLM 响应中提取 JSON"""
        if not raw or not raw.strip():
            return None

        text = raw.strip()

        # 尝试提取 ```json ... ``` 代码块
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1).strip()

        # 尝试直接解析
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # 尝试找到第一个 { 和最后一个 }
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace > first_brace:
            try:
                result = json.loads(text[first_brace:last_brace + 1])
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

        logger.warning(f"无法解析 LLM 响应为 JSON: {text[:200]}")
        return None

    # ============= JSON 画像读写 =============

    async def _load_profile_json(self, user_id: str, expert_id: str) -> Dict[str, Any]:
        """加载 JSON 画像，如果不存在则返回空画像"""
        json_path = self._get_profile_path(user_id, expert_id)

        # 优先读 JSON
        if json_path.exists():
            try:
                async with aiofiles.open(json_path, mode='r', encoding='utf-8') as f:
                    content = await f.read()
                profile = json.loads(content)
                if isinstance(profile, dict) and "tables" in profile:
                    return profile
            except Exception as e:
                logger.error(f"读取 JSON 画像失败: {e}")

        return _make_empty_profile(user_id, expert_id)

    async def _save_profile_json(self, user_id: str, expert_id: str, profile: Dict[str, Any]):
        """保存 JSON 画像"""
        json_path = self._get_profile_path(user_id, expert_id)
        try:
            profile["updated_at"] = datetime.now().isoformat()
            content = json.dumps(profile, ensure_ascii=False, indent=2)
            async with aiofiles.open(json_path, mode='w', encoding='utf-8') as f:
                await f.write(content)
            logger.debug(f"保存 JSON 画像: {json_path}")
        except Exception as e:
            logger.error(f"保存 JSON 画像失败: {e}")

    # ============= 画像加载（外部调用） =============

    async def load_profile(self, user_id: str, expert_id: str) -> str:
        """加载用户画像并返回格式化文本（供 inject_into_prompt 使用）"""
        profile = await self._load_profile_json(user_id, expert_id)
        text = self._profile_to_text(profile)

        logger.debug(f"加载用户画像: {len(text)} 字符")
        return text

    def load_profile_sync(self, user_id: str, expert_id: str) -> str:
        """同步加载用户画像（用于 create_session 等同步上下文）"""
        json_path = self._get_profile_path(user_id, expert_id)

        # 优先读 JSON
        if json_path.exists():
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    profile = json.load(f)
                if isinstance(profile, dict) and "tables" in profile:
                    return self._profile_to_text(profile)
            except Exception as e:
                logger.error(f"同步读取 JSON 画像失败: {e}")

        return ""

    # ============= 画像转文本 =============

    def _profile_to_text(self, profile: Dict[str, Any]) -> str:
        """将结构化画像转换为人类可读文本"""
        if not profile or "tables" not in profile:
            return ""

        tables = profile["tables"]
        sections = []

        for table_name, label in TABLE_LABELS.items():
            entries = tables.get(table_name, [])
            if entries:
                lines = [f"[{label}]"]
                for entry in entries:
                    if isinstance(entry, str):
                        lines.append(f"- {entry}")
                    elif isinstance(entry, dict):
                        lines.append(f"- {entry.get('content', str(entry))}")
                sections.append("\n".join(lines))

        return "\n\n".join(sections)

    # ============= Prompt 注入 =============

    def inject_into_prompt(self, system_prompt: str, profile_content: str) -> str:
        """将用户画像注入到系统提示词中"""
        if not profile_content or profile_content.strip() == "":
            return system_prompt

        injection = f"""

[About the User]
The following is what you have learned about this user through your conversations:

{profile_content}

Use this knowledge to personalise your responses naturally — do not quote or \
repeat these facts mechanically.
"""
        return system_prompt + injection

    # ============= 统计信息 =============

    def get_profile_stats(self, user_id: str, expert_id: str) -> Dict[str, Any]:
        """获取画像统计信息"""
        json_path = self._get_profile_path(user_id, expert_id)

        stats = {
            "has_profile": False,
            "format": None,
            "updated_at": None,
            "table_counts": {},
            "total_entries": 0,
        }

        if json_path.exists():
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    profile = json.load(f)
                stats["has_profile"] = True
                stats["format"] = "json_v2"
                stats["updated_at"] = profile.get("updated_at")
                tables = profile.get("tables", {})
                for name in TABLE_DEFINITIONS:
                    count = len(tables.get(name, []))
                    stats["table_counts"][name] = count
                    stats["total_entries"] += count
            except Exception:
                pass

        # 轮次信息
        key = self._get_profile_key(user_id, expert_id)
        stats["current_round"] = self._conversation_rounds.get(key, 0)
        last_time = self._last_summary_time.get(key)
        if last_time:
            stats["last_summary_at"] = last_time.isoformat()

        return stats


# 兼容性别名
class UserProfileManager(UserProfileManagerUniversal):
    pass


# 全局单例
_profile_manager_instance = None

def get_profile_manager() -> UserProfileManager:
    global _profile_manager_instance
    if _profile_manager_instance is None:
        _profile_manager_instance = UserProfileManager()
    return _profile_manager_instance
