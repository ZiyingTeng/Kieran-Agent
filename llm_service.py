"""LLM 服务模块

提供：
- AsyncLongTermMemoryWrapper: 长期记忆异步包装器
- create_memory_for_user_and_girlfriend: mem0 记忆实例工厂
- create_agent: ReActAgent 工厂（由 SessionManager 调用）
- get_model_config: 根据请求参数获取模型配置
- call_llm_with_config: 统一 LLM 调用接口（relay-gemma4-remote）

注意：使用前必须调用 configure() 注入 character_manager 和 database_dir，
否则 create_agent / create_memory_for_user_and_girlfriend 会抛出 RuntimeError。
"""

import asyncio
import hashlib
import json
import logging
import os
import threading
from typing import Dict, List, Optional

from agentscope.agent import ReActAgent
from agentscope.memory import Mem0LongTermMemory
from agentscope.model import OpenAIChatModel
from mem0.vector_stores.configs import VectorStoreConfig

from database import USE_POSTGRES, get_shared_pg_pool
from model_config import CHAT_MODEL, MODEL_CONFIGS, current_model_config
from tools_to_toolkit import create_girlfriend_toolkit
from user_profile_manager_v2 import get_profile_manager

logger = logging.getLogger(__name__)

# ============= 模块级配置（由 app.py startup_event 注入）=============

_character_manager = None
_database_dir = None

# ============= fastembed 全局单例 =============
# 每个 worker 进程只加载一次 TextEmbedding 模型（~2GB），
# 所有 Mem0LongTermMemory 实例共享同一个对象，避免内存爆炸。
_fastembed_instances: Dict[str, object] = {}
_fastembed_lock = threading.Lock()


def _get_fastembed_singleton(model_name: str) -> object:
    """返回指定 model_name 的全局唯一 TextEmbedding 实例。"""
    if model_name not in _fastembed_instances:
        with _fastembed_lock:
            if model_name not in _fastembed_instances:
                from fastembed import TextEmbedding
                logger.info(
                    f"[fastembed] 首次加载模型: {model_name}（后续复用）"
                )
                _fastembed_instances[model_name] = TextEmbedding(
                    model_name=model_name
                )
    return _fastembed_instances[model_name]


def _patch_pool_closeall() -> None:
    """Prevent mem0 GC from closing the shared psycopg2 pool.

    Mem0LongTermMemory.__del__ calls pool.closeall() which permanently
    destroys the ThreadedConnectionPool for all subsequent instances.
    Patching closeall to a no-op prevents this.
    """
    try:
        from psycopg2.pool import ThreadedConnectionPool
        ThreadedConnectionPool.closeall = lambda self: None
        logger.info("[pool] ThreadedConnectionPool.closeall patched")
    except Exception as e:
        logger.warning(f"[pool] closeall patch failed: {e}")


def _patch_fastembed_singleton() -> None:
    """Monkey-patch FastEmbedEmbedding 使所有实例共享同一个 TextEmbedding。

    在 worker 进程启动时调用一次即可。ONNX Runtime 推理是无状态的，
    多个并发 embed() 调用是线程安全的。
    """
    try:
        from mem0.embeddings.fastembed import FastEmbedEmbedding
        from mem0.embeddings.base import EmbeddingBase

        def _singleton_init(self, config=None):
            EmbeddingBase.__init__(self, config)
            self.config.model = (
                self.config.model or "thenlper/gte-large"
            )
            self.dense_model = _get_fastembed_singleton(
                self.config.model
            )
            if not self.config.embedding_dims:
                self.config.embedding_dims = (
                    self.dense_model.embedding_size
                )

        FastEmbedEmbedding.__init__ = _singleton_init
        logger.info("[fastembed] 单例 patch 已应用")
    except Exception as e:
        logger.warning(f"[fastembed] 单例 patch 失败，跳过: {e}")


def configure(character_manager, database_dir) -> None:
    """注入 character_manager 和 database_dir。

    必须在 startup_event 中调用，早于任何 create_agent /
    create_memory_for_user_and_girlfriend 调用。

    :param character_manager: CharacterConfigManager 实例
    :param database_dir: pathlib.Path，mem0 Chroma 数据库存储目录
    """
    global _character_manager, _database_dir
    _character_manager = character_manager
    _database_dir = database_dir
    _patch_pool_closeall()
    _patch_fastembed_singleton()


def _get_character_manager():
    if _character_manager is None:
        raise RuntimeError(
            "llm_service 未配置：请在 startup_event 中调用 "
            "llm_service.configure(character_manager, database_dir)"
        )
    return _character_manager


def _get_database_dir():
    if _database_dir is None:
        raise RuntimeError(
            "llm_service 未配置：请在 startup_event 中调用 "
            "llm_service.configure(character_manager, database_dir)"
        )
    return _database_dir


# ============= 异步长期记忆包装器 =============

class AsyncLongTermMemoryWrapper:
    """长期记忆的异步包装器。

    将记忆保存操作改为后台 asyncio.create_task 执行，不阻塞主流程。
    """

    def __init__(self, actual_memory):
        self._actual_memory = actual_memory
        self._user_name = getattr(actual_memory, "user_name", "")
        self._agent_name = getattr(actual_memory, "agent_name", "")

    async def record(self, msgs, memory_type=None, infer=True, **kwargs):
        """后台异步记录消息到长期记忆。"""
        asyncio.create_task(
            self._record_in_background(msgs, memory_type, infer, **kwargs)
        )

    async def _record_in_background(self, msgs, memory_type, infer, **kwargs):
        try:
            # 如果最后一条 assistant 消息是错误响应，跳过写入
            assistant_msgs = [
                m for m in msgs if getattr(m, "role", "") == "assistant"
            ]
            if assistant_msgs:
                last_reply = assistant_msgs[-1]
                last_text = (
                    last_reply.content
                    if hasattr(last_reply, "content")
                    else str(last_reply)
                )
                if last_text.startswith("❌"):
                    logger.info("LTM write skipped: error response")
                    return
            filtered = await self._filter_noisy_msgs(msgs)
            if not filtered:
                logger.info("LTM write skipped: no user msg with personal info")
                return
            await self._actual_memory.record(filtered, memory_type, infer, **kwargs)
        except Exception as e:
            logger.error(f"后台保存长期记忆失败: {e}")

    @staticmethod
    def _extract_raw_user_text(content: str) -> str:
        """从可能包含 <long_term_memory> 块的 content 中提取用户原文。"""
        if not content:
            return ""
        import re
        cleaned = re.sub(
            r"<long_term_memory>.*?</long_term_memory>\s*",
            "",
            content,
            flags=re.DOTALL,
        )
        return cleaned.strip()

    async def _filter_noisy_msgs(self, msgs):
        """用 qwen-turbo 判断最新一条用户消息是否含个人信息。

        YES → 只传最后一条 user 消息给 mem0（不传 assistant 回复，避免
              mem0 从 AI 的反问中提取出"事实"污染 LTM）
        NO  → 返回 None 阻止写入
        """
        if not msgs:
            return msgs
        user_msgs = [
            m for m in msgs
            if getattr(m, "role", "") == "user"
            and getattr(m, "name", "") != "long_term_memory"
        ]
        if not user_msgs:
            return msgs
        last_user = user_msgs[-1]
        raw = last_user.content if hasattr(last_user, "content") else str(last_user)
        user_text = self._extract_raw_user_text(raw)
        if not user_text:
            return msgs
        try:
            verdict = await self._classify_personal_info(user_text)
            if not verdict:
                return None
            return [last_user]
        except Exception as e:
            logger.warning(f"LTM filter LLM call failed, allowing write: {e}")
            return msgs

    async def _classify_personal_info(self, text: str) -> bool:
        """调用 relay-gemma4-remote 判断消息是否含用户个人信息。"""
        prompt = (
            "You are a strict filter. Decide whether this message "
            "contains a CONCRETE, LASTING personal fact about the "
            "user — name, age, occupation, family, hometown, pets, "
            "food preferences, hobbies, skills, or life goals.\n\n"
            "Answer YES only if the message DIRECTLY STATES such a "
            "fact. Answer NO for everything else, including:\n"
            "- Questions directed at the AI\n"
            "- Greetings, commands, topic suggestions\n"
            "- Momentary emotions or moods\n"
            "- Relationship talk, jealousy, complaints\n"
            "- Requests (comfort, hugs, songs, recommendations)\n"
            "- Harmful, violent, sexual, or illegal content\n"
            "- Anything that does NOT reveal a lasting personal fact\n\n"
            "Answer only YES or NO."
        )
        from model_config import current_model_config
        if current_model_config.get("use_relay"):
            from relay_client import RelayClient
            client = RelayClient()
            answer = await client.call(
                user_message=text,
                system_prompt=prompt,
                max_tokens=8,
                temperature=0.0,
                model=current_model_config.get(
                    "model_name", "google/gemma-4-26B-A4B-it"
                ),
            )
        else:
            import openai
            relay_api_key = os.getenv("RELAY_GEMMA4_API_KEY", "")
            base_url = os.getenv(
                "LLM_BASE_URL",
                "http://148.153.121.250:8001/v1",
            )
            oai = openai.AsyncOpenAI(
                api_key=relay_api_key if relay_api_key else "dummy-key",
                base_url=base_url,
            )
            resp = await oai.chat.completions.create(
                model=current_model_config.get(
                    "model_name", "/app/model"
                ),
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text},
                ],
                max_tokens=8,
            )
            answer = (
                resp.choices[0].message.content or "YES"
            ).strip().upper()
        answer = (answer or "YES").strip().upper()
        logger.info("LTM filter: '%s' → %s", text[:80], answer)
        return answer.startswith("YES")

    async def add_string(self, string: str, metadata: Dict = None) -> str:
        """后台异步添加字符串记忆，返回假 ID。"""
        asyncio.create_task(
            self._add_string_in_background(string, metadata)
        )
        return f"mem_{hashlib.md5(string.encode()).hexdigest()[:16]}"

    async def _add_string_in_background(self, string: str, metadata: Dict):
        try:
            await self._actual_memory.add_string(string, metadata)
        except Exception as e:
            logger.error(f"后台 add_string 失败: {e}")

    async def get(self, query: str, top_k: int = 5, threshold: float = 0.7):
        return await self._actual_memory.get(query, top_k, threshold)

    async def search(self, query: str, top_k: int = 5, threshold: float = 0.7):
        return await self._actual_memory.search(query, top_k, threshold)

    async def retrieve(self, msg, limit: int = 10, **kwargs):
        """检索长期记忆，取 top-30 后去重、降权，返回多样化结果。"""
        results_str = await self._actual_memory.retrieve(
            msg, limit, **kwargs,
        )
        if not results_str:
            return results_str

        lines = [l.strip() for l in results_str.splitlines() if l.strip()]
        if len(lines) <= 1:
            return results_str

        import re

        def _norm(s: str) -> str:
            return re.sub(
                r"[\s\-_.,，。、：:；;「」『』【】\[\]（）()\"'!！~]+",
                "", s.lower(),
            )

        # 这个不怎么必要 但也先放着！
        def _is_question(s: str) -> bool:
            t = s.rstrip()
            if t.endswith(("?", "？")):
                return True
            if re.search(
                r"(뭐야|뭐였|알아|기억해|어때|줄래|할래|싶어|몰라"
                r"|what|how|who|where|when|why|which"
                r"|是什么|是谁|怎么|哪里|什么时候|为什么)[?？]?\s*$",
                t, re.IGNORECASE,
            ):
                return True
            return False

        _ENTITY_RE = re.compile(
            r"[A-Z][a-z]+(?:\s[A-Z][a-z]+)*"  # English names
            r"|[가-힣]{2,}"                     # Korean words
            r"|\d+"                             # numbers
            r"|[一-龥]{2,}"                      # Chinese words
            r"|[a-zA-Z]{3,}",                   # English words 3+
        )

        def _entities(s: str) -> set:
            return {m.lower() for m in _ENTITY_RE.findall(s)}

        def _is_duplicate(norm_a: str, norm_b: str,
                          ent_a: set, ent_b: set) -> bool:
            if not norm_a or not norm_b:
                return False
            shorter, longer = (
                (norm_a, norm_b) if len(norm_a) <= len(norm_b)
                else (norm_b, norm_a)
            )
            if shorter in longer:
                return True
            overlap = sum(1 for c in shorter if c in longer)
            ratio = overlap / len(shorter)
            if ratio >= 0.75:
                return True
            # 跨语言去重：实体关键词重叠 >= 60%
            if ent_a and ent_b:
                common = ent_a & ent_b
                smaller = min(len(ent_a), len(ent_b))
                if smaller > 0 and len(common) / smaller >= 0.6:
                    return True
            return False

        deduped = []
        deduped_norms = []
        deduped_ents = []
        for line in lines:
            norm = _norm(line)
            ents = _entities(line)
            if any(
                _is_duplicate(norm, kn, ents, ke)
                for kn, ke in zip(deduped_norms, deduped_ents)
            ):
                continue
            deduped.append(line)
            deduped_norms.append(norm)
            deduped_ents.append(ents)

        facts = [l for l in deduped if not _is_question(l)]
        questions = [l for l in deduped if _is_question(l)]
        reordered = facts + questions

        logger.info(
            "LTM retrieve: 原始 %d → 去重 %d（事实 %d / 问句 %d）\n%s",
            len(lines), len(deduped), len(facts), len(questions),
            "\n".join(f"  [{i+1}] {l}" for i, l in enumerate(reordered)),
        )
        return "\n".join(reordered)

    def __getattr__(self, name):
        return getattr(self._actual_memory, name)


# ============= 记忆实例工厂 =============

def create_memory_for_user_and_girlfriend(userId: str, expertId: str):
    """为每个用户×角色组合创建独立的 Mem0 长期记忆实例。

    统一使用 mem0 完整 pipeline（LLM 事实提取 + 语义去重 + 向量搜索）。

    :param userId: 用户 ID
    :param expertId: 角色 ID
    :returns: Mem0LongTermMemory 实例
    """
    character_manager = _get_character_manager()
    database_dir = _get_database_dir()

    girlfriend_config = character_manager.get(expertId)
    if girlfriend_config is None:
        girlfriend_config = character_manager.get("101")

    name = girlfriend_config["name"]

    relay_api_key = os.getenv("RELAY_GEMMA4_API_KEY", "")
    llm_base_url = os.getenv(
        "LLM_BASE_URL", "http://148.153.121.250:8001/v1"
    )
    llm_model = os.getenv("LLM_MODEL", "/app/model")
    embed_model = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-large")
    embed_dims = int(os.getenv("EMBED_DIMS", "1024"))
    api_key = relay_api_key if relay_api_key else "dummy-key"

    if current_model_config.get("use_relay"):
        from relay_client import get_relay_api_cls
        memory_chat_model = get_relay_api_cls()(
            model_name=llm_model,
            api_path=current_model_config.get(
                "relay_path", "/v3/openrouterchatgpt"
            ),
            max_tokens=512,
        )
    else:
        from relay_client import get_direct_api_cls
        memory_chat_model = get_direct_api_cls()(
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
        logger.info(f"创建 mem0+pgvector 记忆: {userId}/{name}")
        vector_store_config = VectorStoreConfig(
            provider="pgvector",
            config={
                "connection_pool": get_shared_pg_pool(),
                "embedding_model_dims": embed_dims,
                "hnsw": True,
            },
        )
    else:
        logger.info(f"创建 mem0+Chroma 记忆: {userId}/{name}")
        db_path = str(database_dir / f"mem0_db_{userId}_{expertId}")
        vector_store_config = VectorStoreConfig(
            provider="chroma",
            config={"path": db_path},
        )

    return Mem0LongTermMemory(
        user_name=userId,
        agent_name=name,
        run_name=f"{expertId}_service",
        model=memory_chat_model,   # overrides mem0_cfg.llm → agentscope LLM
        mem0_config=mem0_cfg,      # carries fastembed embedder
        vector_store_config=vector_store_config,
    )


# ============= Agent 工厂 =============

def create_agent(userId: str, expertId: str, memory, long_term_memory) -> "ReActAgent":
    """ReActAgent 工厂函数，由 SessionManager 调用。

    :param userId: 用户 ID
    :param expertId: 角色 ID
    :param memory: RedisMemory 实例（由 SessionManager 提供）
    :param long_term_memory: Mem0LongTermMemory 实例（由 SessionManager 提供）
    :returns: 配置好的 ReActAgent 实例
    """
    character_manager = _get_character_manager()

    # 从管理器实时获取最新角色配置
    girlfriend_config = character_manager.get(expertId)
    if girlfriend_config is None:
        girlfriend_config = character_manager.get("101")

    original_sys_prompt = girlfriend_config.get(
        "description",
        girlfriend_config.get("sys_prompt", "你是一个友好的AI助手。"),
    )
    wrapped_sys_prompt = original_sys_prompt

    # 用户画像注入暂时停用（画像系统待架构优化后重新启用）
    # profile_manager = get_profile_manager()
    # try:
    #     profile_content = profile_manager.load_profile_sync(userId, expertId)
    #     final_sys_prompt = profile_manager.inject_into_prompt(
    #         wrapped_sys_prompt, profile_content
    #     )
    #     if profile_content.strip():
    #         logger.info(f"✅ 已加载用户画像: {userId} + {expertId}")
    # except Exception as e:
    #     logger.warning(f"⚠️ 加载用户画像失败: {e}")
    #     final_sys_prompt = wrapped_sys_prompt
    final_sys_prompt = wrapped_sys_prompt

    # 根据 CHAT_MODEL 构建模型实例
    if CHAT_MODEL.startswith("relay"):
        if current_model_config.get("use_relay"):
            from relay_client import get_relay_api_cls
            RelayApiChatModel = get_relay_api_cls()
            model_kwargs = {
                "model_name": current_model_config["model_name"],
                "api_path": current_model_config.get(
                    "relay_path", "/v3/openrouterchatgpt"
                ),
            }
            current_model_config["model_class"] = RelayApiChatModel
            logger.info("使用中继 RSA 模型: %s", current_model_config["model_name"])
        elif current_model_config.get("direct_api"):
            from relay_client import get_direct_api_cls
            DirectApiChatModel = get_direct_api_cls()
            model_kwargs = {
                "model_name": current_model_config["model_name"],
                "base_url": current_model_config["base_url"],
                "api_key": os.getenv(
                    current_model_config.get("api_key_env", ""), ""
                ),
                "use_proxy": current_model_config.get("use_proxy", False),
            }
            current_model_config["model_class"] = DirectApiChatModel
            logger.info("使用直连 API 模型: %s", current_model_config["base_url"])
    else:
        api_key = os.getenv(current_model_config["api_key_env"])
        if not api_key:
            error_msg = (
                f"❌ 错误: 未找到环境变量 {current_model_config['api_key_env']}\n"
                f"请确保在 .env 文件中设置了 {current_model_config['api_key_env']}\n"
                f"当前模型: {CHAT_MODEL} ({current_model_config['description']})"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        model_kwargs = {
            "model_name": current_model_config["model_name"],
            "api_key": api_key,
        }
        if "client_args" in current_model_config:
            model_kwargs["client_kwargs"] = current_model_config["client_args"]
        if "generate_kwargs" in current_model_config:
            model_kwargs["generate_kwargs"] = current_model_config["generate_kwargs"]

    # relay 使用 OpenAI formatter
    from agentscope.formatter import OpenAIChatFormatter
    formatter = OpenAIChatFormatter()

    model_instance = current_model_config["model_class"](**model_kwargs)

    # 若模型不支持 tool calling，不传 toolkit
    _gkw = current_model_config.get("generate_kwargs", {})
    toolkit = (
        None
        if _gkw.get("tool_choice") == "none"
        else create_girlfriend_toolkit()
    )

    agent = ReActAgent(
        name=girlfriend_config["name"],
        model=model_instance,
        sys_prompt=final_sys_prompt,
        formatter=formatter,
        memory=memory,
        long_term_memory=AsyncLongTermMemoryWrapper(long_term_memory),
        long_term_memory_mode="both",
        toolkit=toolkit,
    )
    agent.set_console_output_enabled(False)
    return agent


# ============= 模型配置选择 =============

def get_model_config(
    model_name: Optional[str] = None,
    api_path: Optional[str] = None,
) -> Dict:
    """根据请求参数获取模型配置。

    :param model_name: 模型名称（如 "qwen-turbo"、"gemini-2.5-flash"）
    :param api_path: 自定义 API 端点（OpenAI 兼容格式）
    :returns: 模型配置字典
    """
    if model_name and model_name in MODEL_CONFIGS:
        return MODEL_CONFIGS[model_name]
    if api_path:
        return {
            "model_class": OpenAIChatModel,
            "model_name": model_name or "custom-model",
            "api_key_env": "FAKE_API_KEY",
            "api_key": "fake-key",
            "client_args": {"base_url": api_path},
            "generate_kwargs": {"tool_choice": "none"},
            "description": f"自定义API ({api_path})",
        }
    return current_model_config


# ============= Gemini REST API 直接调用 =============

async def call_gemini_api(
    system_prompt: str,
    user_message: str,
    model_name: str = "gemini-2.5-flash",
    api_key: str = None,
    base_url: str = None,
    history: List[Dict] = None,
) -> Optional[str]:
    """通过 Gemini REST API 生成回复。

    :param system_prompt: 系统提示词
    :param user_message: 用户消息
    :param model_name: 模型名称
    :param api_key: Gemini API 密钥
    :param base_url: 自定义代理地址（如 gcpapi.magicutapp.com）
    :param history: 对话历史，格式 [{"role": "user"|"model", "content": "..."}]
    :returns: AI 回复文本，失败时返回 None
    """
    try:
        if not api_key:
            logger.error("未找到 GEMINI_API_KEY")
            return None

        import aiohttp

        # 使用自定义 base_url 时不走代理；否则代理已在启动时清除，此处为 None
        proxy = None
        if base_url:
            logger.info(f"使用自定义 base_url 访问 Gemini API: {base_url}")

        headers = {"Content-Type": "application/json"}

        contents = []
        if system_prompt:
            contents.append({
                "role": "user",
                "parts": [{"text": system_prompt}],
            })
        if history:
            for h in history:
                role = h.get("role", "user")
                contents.append({
                    "role": role,
                    "parts": [{"text": h.get("content", "")}],
                })
        contents.append({
            "role": "user",
            "parts": [{"text": user_message}],
        })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.9,
                "topP": 0.95,
                "topK": 32,
                "maxOutputTokens": 1024,
            },
        }

        api_base = base_url or "https://generativelanguage.googleapis.com"
        api_url = (
            f"{api_base}/v1beta/models/{model_name}"
            f":generateContent?key={api_key}"
        )

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60)
        ) as session:
            kwargs = {"headers": headers, "json": payload}
            if proxy:
                kwargs["proxy"] = proxy
            async with session.post(api_url, **kwargs) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        f"Gemini API 调用失败: {response.status} - {error_text}"
                    )
                    return None
                data = await response.json()

        if "candidates" not in data or not data["candidates"]:
            logger.error(f"Gemini API 响应格式错误: {data}")
            return None

        candidate = data["candidates"][0]
        if "content" not in candidate or "parts" not in candidate["content"]:
            logger.error(f"Gemini API 响应缺少内容: {candidate}")
            return None

        return candidate["content"]["parts"][0]["text"]

    except asyncio.TimeoutError:
        logger.error("调用 Gemini API 超时")
        return None
    except Exception as e:
        logger.error(f"调用 Gemini API 失败: {e}")
        return None


# ============= 统一 LLM 调用接口 =============

async def call_llm_with_config(
    user_message: str,
    system_prompt: str,
    model_config: Dict,
    history: List[Dict] = None,
    raw_messages: List[Dict] = None,
) -> str:
    """使用指定配置调用 LLM，支持多模型路由。

    :param user_message: 用户消息
    :param system_prompt: 系统提示词
    :param model_config: 模型配置字典
    :param history: 对话历史（可选），格式 [{user: ..., model: ...}]
    :param raw_messages: 预构建的 OpenAI 格式消息列表（direct_api 时优先使用，
        会跳过 system_prompt/history/user_message 的自动组装）
    :returns: LLM 回复文本
    """
    try:
        model_name = model_config["model_name"]

        # direct_api: 标准 OpenAI 兼容端点
        # use_proxy=True → 走 SAVED_PROXY；False（默认）→ 直连
        if model_config.get("direct_api"):
            import httpx
            from proxy_config import SAVED_PROXY

            base_url = model_config.get("base_url", "")
            api_key = (
                os.getenv(model_config.get("api_key_env", ""), "")
                or model_config.get("api_key", "")
            )
            endpoint = base_url.rstrip("/")
            if not endpoint.endswith("/chat/completions"):
                endpoint += "/chat/completions"
            if raw_messages is not None:
                msgs = raw_messages
            else:
                msgs: list[dict] = []
                if system_prompt:
                    msgs.append({"role": "system", "content": system_prompt})
                if history:
                    for h in history:
                        if h.get("user"):
                            msgs.append({"role": "user", "content": h["user"]})
                        if h.get("model"):
                            msgs.append(
                                {"role": "assistant", "content": h["model"]}
                            )
                msgs.append({"role": "user", "content": user_message})
            headers = (
                {"Authorization": f"Bearer {api_key}"} if api_key else {}
            )
            proxy = SAVED_PROXY if model_config.get("use_proxy") else None
            payload = {
                "model": model_name,
                "messages": msgs,
                "max_tokens": 1024,
                "temperature": 0.8,
            }
            logger.info(
                "GroupChat DirectAPI 请求:\n%s",
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
            async with httpx.AsyncClient(
                proxy=proxy, timeout=120
            ) as client:
                resp = await client.post(
                    endpoint, json=payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
                logger.info(
                    "GroupChat DirectAPI 响应:\n%s",
                    json.dumps(data, ensure_ascii=False, indent=2),
                )
                return data["choices"][0]["message"]["content"].strip()

        # use_relay: RSA 鉴权中继
        if model_config.get("use_relay"):
            from relay_client import RelayClient
            client = RelayClient()
            # 从 raw_messages 或参数重建 system/history/user
            if raw_messages is not None:
                sys_p = ""
                hist: list[dict] = []
                last_user = user_message
                for m in raw_messages:
                    r, c = m.get("role"), m.get("content", "")
                    if r == "system":
                        sys_p = c
                    elif r == "user":
                        if last_user:
                            hist.append(
                                {"role": "user", "content": last_user}
                            )
                        last_user = c
                    elif r == "assistant":
                        if last_user:
                            hist.append(
                                {"role": "user", "content": last_user}
                            )
                            last_user = ""
                        hist.append(
                            {"role": "assistant", "content": c}
                        )
            else:
                sys_p = system_prompt
                hist = []
                if history:
                    for h in history:
                        if h.get("user"):
                            hist.append(
                                {"role": "user", "content": h["user"]}
                            )
                        if h.get("model"):
                            hist.append(
                                {"role": "assistant",
                                 "content": h["model"]}
                            )
            return await client.call(
                user_message=last_user if raw_messages else user_message,
                system_prompt=sys_p if raw_messages else system_prompt,
                history=hist,
                model=model_name,
                api_path=model_config.get(
                    "relay_path", "/v3/openrouterchatgpt"
                ),
            )

        return f"❌ 不支持的模型配置: {model_name}"

    except Exception as e:
        logger.error(f"调用LLM失败: {e}")
        return f"❌ 调用失败: {str(e)}"
