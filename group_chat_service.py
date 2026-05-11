"""Group chat service module.

Provides:
- Group long-term memory creation, retrieval, and recording
- generate_agent_response_in_group: generate a reply for a single character
- format_group_context: format message list into text

Note: configure() must be called to inject runtime dependencies before use,
otherwise a RuntimeError will be raised.
"""

import hashlib
import json
import logging
import os
from typing import List, Optional

from agentscope.memory import Mem0LongTermMemory
from mem0.vector_stores.configs import VectorStoreConfig

from database import USE_POSTGRES, get_shared_pg_pool
from llm_service import call_llm_with_config
from model_config import CHAT_MODEL, GROUP_CHAT_MODEL, MODEL_CONFIGS

logger = logging.getLogger(__name__)

# ============= 模块级配置 (由 app.py startup_event 注入) =============

_character_manager = None
_group_manager = None
_database_dir = None


def configure(character_manager, group_manager, database_dir) -> None:
    """Inject runtime dependencies.

    Must be called in startup_event before any group chat service function
    is triggered.

    :param character_manager: CharacterConfigManager instance
    :param group_manager: GroupManager instance
    :param database_dir: pathlib.Path, mem0 Chroma database storage directory
    """
    global _character_manager, _group_manager, _database_dir
    _character_manager = character_manager
    _group_manager = group_manager
    _database_dir = database_dir


def _get_character_manager():
    if _character_manager is None:
        raise RuntimeError(
            "group_chat_service is not configured: call "
            "group_chat_service.configure(character_manager, group_manager, "
            "database_dir) in startup_event"
        )
    return _character_manager


def _get_group_manager():
    if _group_manager is None:
        raise RuntimeError(
            "group_chat_service is not configured: call "
            "group_chat_service.configure(character_manager, group_manager, "
            "database_dir) in startup_event"
        )
    return _group_manager


def _get_database_dir():
    if _database_dir is None:
        raise RuntimeError(
            "group_chat_service is not configured: call "
            "group_chat_service.configure(character_manager, group_manager, "
            "database_dir) in startup_event"
        )
    return _database_dir


# ============= 群组长期记忆 =============

# 一个群组一个mem0单例 (group_id -> Mem0LongTermMemory)
_group_memories: dict = {}


def cleanup_group_memory(group_id: str) -> None:
    """Remove the in-process mem0 instance when a group is deleted.

    :param group_id: Group ID
    """
    if group_id in _group_memories:
        del _group_memories[group_id]
        logger.info(f"Group {group_id} long-term memory instance cleaned up")


def get_or_create_group_memory(group_id: str) -> Mem0LongTermMemory:
    """Lazy-load: get or create the shared mem0 long-term memory for a group.

    :param group_id: Group ID
    :returns: Mem0LongTermMemory instance
    """
    if group_id in _group_memories:
        return _group_memories[group_id]

    relay_api_key = os.getenv("RELAY_GEMMA4_API_KEY", "")
    llm_base_url = os.getenv(
        "LLM_BASE_URL", "http://148.153.121.250:8001/v1"
    )
    llm_model = os.getenv("LLM_MODEL", "/app/model")
    embed_model = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-large")
    embed_dims = int(os.getenv("EMBED_DIMS", "1024"))
    api_key = relay_api_key if relay_api_key else "dummy-key"

    from relay_client import get_direct_api_cls
    DirectApiChatModel = get_direct_api_cls()
    memory_chat_model = DirectApiChatModel(
        model_name=llm_model,
        base_url=llm_base_url,
        api_key=api_key,
        max_tokens=512,
    )

    from mem0.configs.base import MemoryConfig
    from mem0.embeddings.configs import EmbedderConfig
    from mem0.llms.configs import LlmConfig
    mem0_cfg = MemoryConfig(
        llm=LlmConfig(provider="openai", config={}),
        embedder=EmbedderConfig(
            provider="fastembed",
            config={"model": embed_model},
        ),
    )

    if USE_POSTGRES:
        vs_config = VectorStoreConfig(
            provider="pgvector",
            config={
                "connection_pool": get_shared_pg_pool(),
                "embedding_model_dims": embed_dims,
                "hnsw": True,
            },
        )
    else:
        database_dir = _get_database_dir()
        db_path = str(database_dir / f"mem0_group_{group_id}")
        vs_config = VectorStoreConfig(
            provider="chroma",
            config={"path": db_path},
        )

    mem = Mem0LongTermMemory(
        user_name=group_id,
        agent_name=None,
        run_name=f"group_{group_id}",
        model=memory_chat_model,   # overrides mem0_cfg.llm → agentscope LLM
        mem0_config=mem0_cfg,      # carries fastembed embedder
        vector_store_config=vs_config,
    )
    _group_memories[group_id] = mem
    logger.info(f"✅ Created group long-term memory: {group_id}")
    return mem


async def retrieve_group_memories(
    group_id: str, query: str, limit: int = 5
) -> str:
    """Retrieve facts from a group's long-term memory relevant to query.

    :param group_id: Group ID
    :param query: Search query text
    :param limit: Maximum number of results to return
    :returns: Formatted memory text, empty string when no results
    """
    try:
        mem = get_or_create_group_memory(group_id)
        result = await mem.long_term_working_memory.search(
            query=query,
            user_id=mem.user_id,
            run_id=mem.run_id,
            limit=limit,
        )
        if not result:
            return ""
        memories = (
            result.get("results", result)
            if isinstance(result, dict)
            else result
        )
        if not memories:
            return ""
        lines = []
        for item in memories:
            text = (
                item.get("memory", "")
                if isinstance(item, dict)
                else str(item)
            )
            if text:
                lines.append(f"- {text}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Failed to retrieve group long-term memory ({group_id}): {e}")
        return ""


async def record_group_memories(
    group_id: str, user_message: str
) -> None:
    """Record user message to group long-term memory (async).

    Only the user's own message is stored — character replies are excluded
    to avoid extracting AI-generated text as user facts.

    :param group_id: Group ID
    :param user_message: User message text
    """
    try:
        mem = get_or_create_group_memory(group_id)
        await mem._mem0_record(
            [{"role": "user", "content": user_message}],
            infer=True,
        )
        logger.info(f"✅ Group {group_id} long-term memory recorded")
    except Exception as e:
        logger.error(f"Failed to record group long-term memory ({group_id}): {e}")


# ============= 格式化工具 =============

def format_group_context(context: List[dict]) -> str:
    """Format a group message list into plain text (last 20 messages).

    :param context: List of messages, each containing a content field
    :returns: Multi-line concatenated text
    """
    if not context:
        return "(No messages yet)"
    lines = []
    for msg in context[-20:]:
        content = msg.get("content", "")
        lines.append(content)
    return "\n".join(lines)


# ============= 群聊响应生成 =============

async def generate_agent_response_in_group(
    expertId: str,
    user_message: str,
    group_context: dict,
    group_id: str = "",
    mention_context: str = "",
    must_reply: bool = False,
    long_term_memory_context: str = "",
    group_background: str = "",
) -> Optional[str]:
    """Generate a reply for a single character in a group chat.

    :param expertId: Character ID
    :param user_message: User message text
    :param group_context: Group chat context (fallback when DB unavailable)
    :param group_id: Group ID — used to load persistent history from DB
    :param mention_context: Mention context (e.g. "user @-mentioned you")
    :param must_reply: Whether this character must reply (when @-mentioned)
    :param long_term_memory_context: Long-term memory text retrieved from mem0
    :returns: Reply text, or None if the character chooses to skip
    """
    try:
        character_manager = _get_character_manager()
        logger.info(f"[Group] Generating reply: {expertId}")

        gf_config = character_manager.get(expertId)
        if not gf_config:
            logger.warning(f"[Group] Character config not found: {expertId}")
            return None

        # Load history from DB; fall back to in-memory group_context on failure
        messages = []
        if group_id:
            try:
                from database import load_group_history_from_db
                db_rows = await load_group_history_from_db(group_id, limit=30)
                if db_rows:
                    # Normalise to the same format expected by format_group_context:
                    # content = "sender_name: raw_content"
                    messages = [
                        {
                            "role": r["role"],
                            "content": f"{r['sender_name']}: {r['content']}",
                            "sender_name": r["sender_name"],
                            "sender_id": r["sender_id"],
                        }
                        for r in db_rows
                    ]
                    logger.info(
                        f"[Group] Loaded {len(messages)} messages from DB "
                        f"for group {group_id}"
                    )
            except Exception as e:
                logger.warning(f"[Group] DB history load failed, using memory: {e}")
        if not messages:
            messages = group_context.get("messages", [])

        mention_hint = f"\n⚠️ {mention_context}" if mention_context else ""

        background_hint = (
            f"\n\n[Scene Background]\n{group_background}"
            if group_background else ""
        )

        # LTM block — same format as private chat (_LTM_NEW_HEADER)
        if long_term_memory_context:
            from relay_client import _LTM_NEW_HEADER
            ltm_hint = (
                "\n\n"
                + _LTM_NEW_HEADER
                + long_term_memory_context
                + "\n"
            )
        else:
            ltm_hint = ""

        # Build message history using the `name` field to distinguish speakers.
        # All history messages use role="user" — the model knows who it is from
        # the system prompt. The `name` field carries the actual speaker identity.
        history_msgs: list[dict] = []
        for msg in messages[-14:]:
            content = msg["content"]
            sender_name = msg.get("sender_name", "User")
            # Sanitise name: OpenAI requires [a-zA-Z0-9_-], max 64 chars
            safe_name = "".join(
                c if c.isalnum() or c in "-_" else "_"
                for c in sender_name
            )[:64]
            history_msgs.append(
                {"role": "user", "content": content, "name": safe_name}
            )

        if must_reply:
            system_prompt = (
                f"You are {gf_config['name']} (character ID: {expertId})"
                f" in a group chat.\n"
                f"(Always maintain your unique tone and personality —"
                f" never copy another character's phrasing.)\n\n"
                f"Your personality:"
                f" {gf_config.get('sys_prompt', 'warm and friendly')}"
                f"{background_hint}\n"
                f"{mention_hint}\n"
                f"[Reply Guidelines]\n"
                f"0. **Language**: always reply in the same language"
                f" the user is writing in\n"
                f"1. **Stay consistent**: never contradict what you have"
                f" said before\n"
                f"2. **Avoid repetition**: do not repeat what others have"
                f" already said\n"
                f"3. **Be distinctive**: express yourself in your own way,"
                f" true to your character\n\n"
                f"Give your unique reply now, avoiding repetition."
                f"{ltm_hint}"
            )
        else:
            system_prompt = (
                f"You are {gf_config['name']} (character ID: {expertId})"
                f" in a group chat.\n"
                f"(Always maintain your unique tone and personality —"
                f" never copy another character's phrasing.)\n\n"
                f"Your personality:"
                f" {gf_config.get('sys_prompt', 'warm and friendly')}"
                f"{background_hint}\n"
                f"{mention_hint}\n"
                f"[Reply Decision]\n"
                f"Decide whether you should reply:\n\n"
                f"✅ Reply when (strongly recommended):\n"
                f"1. The user greets everyone or asks how people are doing\n"
                f"2. The user asks a general question directed at the group\n"
                f"3. The user mentions your name or a topic closely related"
                f" to you\n"
                f"4. The topic falls within your interests or expertise\n\n"
                f"❌ Skip (reply with SKIP) when:\n"
                f"1. The topic is completely unrelated to you and highly"
                f" specialized\n"
                f"2. Another character has already given a thorough, accurate"
                f" answer with nothing left to add\n\n"
                f"[Reply Tips]\n"
                f"- **Language**: always reply in the same language"
                f" the user is writing in\n"
                f"- **Important**: if you reply, say something new —"
                f" do not repeat others\n"
                f"- Add a fresh angle, share your own experience, or ask"
                f" a new question\n"
                f"- Avoid filler responses like \"me too\", \"agreed\","
                f" \"yeah\"\n"
                f"- Keep it brief: 1-2 sentences\n\n"
                f"If you choose to skip, reply with exactly one word: SKIP"
                f"{ltm_hint}"
            )

        # debug: prompt fingerprint (diagnose verbatim-copy issues)
        _sp_hash = hashlib.md5(system_prompt.encode("utf-8")).hexdigest()[:8]
        _um_hash = hashlib.md5(user_message.encode("utf-8")).hexdigest()[:8]
        logger.info(
            "[Group debug] expertId=%s name=%s must_reply=%s "
            "sp_hash=%s um_hash=%s history_len=%d sp_head=%r",
            expertId,
            gf_config.get("name"),
            must_reply,
            _sp_hash,
            _um_hash,
            len(history_msgs),
            system_prompt[:120].replace("\n", " "),
        )

        group_model = GROUP_CHAT_MODEL or CHAT_MODEL
        model_config = MODEL_CONFIGS.get(group_model)

        def _is_skip(content: str) -> bool:
            return content == "SKIP" or "SKIP" in content.upper()

        # direct_api / relay models are handled inside call_llm_with_config
        api_key_env = model_config.get("api_key_env")
        if model_config.get("direct_api") or model_config.get("use_relay"):
            api_key = ""
        elif api_key_env and api_key_env != "FAKE_API_KEY":
            api_key = os.getenv(api_key_env)
            if not api_key:
                logger.error(f"API key not found: {api_key_env}")
                return None
        else:
            api_key = model_config.get("api_key", "fake-key")

        try:
            # relay-gemma4-remote: use OpenAI-compat format with name field
            raw_msgs = (
                [{"role": "system", "content": system_prompt}]
                + history_msgs
                + [{"role": "user", "content": user_message}]
            )

            # relay-gemma4-remote via unified interface
            content = await call_llm_with_config(
                user_message=user_message,
                system_prompt=system_prompt,
                model_config=model_config,
                raw_messages=raw_msgs,
            )
            if not content or "❌" in content:
                return None
            if not must_reply and _is_skip(content):
                logger.info(f"{gf_config['name']} chose to skip this topic")
                return None
            return content

        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            return None

    except Exception as e:
        logger.error(f"Failed to generate agent response: {e}")
        return None
