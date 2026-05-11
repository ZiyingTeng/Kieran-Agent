from fastapi import FastAPI, HTTPException, Request, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Literal, AsyncGenerator
import os
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
import asyncio
import logging
import random
import uuid

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

# 必须最先导入：读取并清除全局代理，避免 Privoxy 拦截内网请求
import proxy_config  # noqa: F401
_SAVED_PROXY = proxy_config.SAVED_PROXY  # 向后兼容：保留模块级名称

from agentscope.agent import ReActAgent
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel
from agentscope.memory import Mem0LongTermMemory, InMemoryMemory, RedisMemory
from mem0.vector_stores.configs import VectorStoreConfig
from group_manager import GroupManager, Group, GroupSession, GroupMessage

# 导入自定义工具
from tools_to_toolkit import create_girlfriend_toolkit

# 导入消息重新生成管理器
from message_regeneration_manager import get_regeneration_manager

# 导入心跳系统
from heartbeat_scheduler import (
    HeartbeatScheduler, get_heartbeat_scheduler, initialize_heartbeat_scheduler
)
from heartbeat_greeting_generator import (
    HeartbeatGreetingGenerator, get_greeting_generator, initialize_greeting_generator
)

# 导入用户画像管理
from user_profile_manager_v2 import (
    UserProfileManager, get_profile_manager
)

# 导入推送服务
from push_service import (
    get_push_service, initialize_push_service
)
from push_service.api import router as push_api_router

# 导入 Redis 会话管理器
from session_manager import (
    SessionManager, get_session_manager, initialize_session_manager
)

# ============= 日志配置 =============

_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # 控制台 (开发模式 python app.py 可见)
        logging.FileHandler(os.path.join(_log_dir, "app.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# 屏蔽 mem0 库的 INFO 级别日志
logging.getLogger("mem0").setLevel(logging.WARNING)


# ============= Mem0 Record Monkey Patch =============
# Gemini 3.1 API 要求 function_call parts 携带 thought_signature，
# 但 AgentScope 的 parse/format 链路会丢失它。在此 monkey-patch 修复。



def _patch_mem0_record():
    """record() 只提取用户事实"""
    from agentscope.memory import Mem0LongTermMemory
    from agentscope.message import Msg

    _original_record = Mem0LongTermMemory.record

    async def _patched_record(self, msgs, memory_type=None, infer=True, **kwargs):
        if isinstance(msgs, Msg):
            msgs = [msgs]
        msg_list = [m for m in msgs if m is not None]
        if not msg_list:
            return

        # 按角色分离消息，保留上下文但只以 user 消息为主
        messages = []
        for msg in msg_list:
            role = getattr(msg, "role", "assistant")
            content = str(msg.content) if hasattr(msg, "content") else str(msg)
            if not content.strip():
                continue
            messages.append({"role": role, "content": content})

        # 确保有用户消息，否则跳过
        has_user = any(m["role"] == "user" for m in messages)
        if not has_user:
            return

        user_messages = [m for m in messages if m["role"] == "user"]

        await self._mem0_record(
            user_messages,
            memory_type=memory_type,
            infer=infer,
            **kwargs,
        )

    Mem0LongTermMemory.record = _patched_record
    logger.info("✅ mem0 record() monkey-patch 已应用（只提取用户事实）")

_patch_mem0_record()


# ============= PostgreSQL 支持 =============

from database import (
    USE_POSTGRES,
    get_shared_pg_pool,
    get_postgres_pool,
    save_chat_history_to_db,
    load_chat_history_from_db,
    load_recent_chat_history,
    delete_chat_message_from_db,
)

# ============= 群聊服务 =============

import group_chat_service
from group_chat_service import (
    get_or_create_group_memory,
    retrieve_group_memories,
    record_group_memories,
    format_group_context,
    generate_agent_response_in_group,
)

import routers.groups as groups_router_module
from routers.groups import router as groups_router



# ============= 并发控制 =============

# 限制同时处理的请求数量（避免 API 限流和数据库锁定）
MAX_CONCURRENT_REQUESTS = 100 
request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)


# ============= 心跳系统全局变量 =============
_heartbeat_scheduler: Optional[HeartbeatScheduler] = None
_greeting_generator: Optional[HeartbeatGreetingGenerator] = None


# ============= 记忆大小配置 =============

# 私聊：保留最近 20 条消息
MAX_PRIVATE_CHAT_HISTORY = 20

# 群聊：保留最近 50 条消息
MAX_GROUP_CHAT_HISTORY = 50


# ============= 全局聊天模型配置 =============

from model_config import (
    CHAT_MODEL,
    GROUP_CHAT_MODEL,
    MODEL_CONFIGS,
    current_model_config,
)
import llm_service
from llm_service import (
    AsyncLongTermMemoryWrapper,
    create_memory_for_user_and_girlfriend,
    create_agent,
    get_model_config,
    call_gemini_api,
    call_llm_with_config,
)




# ============= 角色配置管理 =============
# 使用CharacterConfigManager从characters目录加载角色
from character_config_manager import CharacterConfigManager

# 获取脚本所在目录的绝对路径
SCRIPT_DIR = Path(__file__).parent.resolve()
CHARACTERS_DIR = SCRIPT_DIR / "characters"
USER_CHARACTERS_DIR = SCRIPT_DIR / "users_characters"

# 初始化角色管理器
character_manager = CharacterConfigManager(
    characters_dir=str(CHARACTERS_DIR),
    user_characters_dir=str(USER_CHARACTERS_DIR),
)
logger.info(f"✅ 已加载 {character_manager.get_count()} 个角色配置")

GIRLFRIENDS_CONFIG_FILE = "girlfriends_config.json"
NEXT_CUSTOM_ID_START = 100000  # 用户自定义女友ID起始值

# 数据库存储目录
DATABASE_DIR = Path("databases")
DATABASE_DIR.mkdir(exist_ok=True)  # 确保目录存在


# 保留 GIRLFRIENDS_CONFIG 变量（使用character_manager）
GIRLFRIENDS_CONFIG = character_manager.get_all()

# 创建全局群组管理器实例
group_manager = GroupManager()


# ============= WebSocket 连接管理 =============
# 存储活跃的 WebSocket 连接: {connection_id: websocket}
active_websockets: Dict[str, WebSocket] = {}

# 用户到连接的映射: {user_id: connection_id}
user_to_connection: Dict[str, str] = {}

# 连接到用户的映射: {connection_id: user_id}
connection_to_user: Dict[str, str] = {}

# 用户到角色的映射: {user_id: expert_id}
user_expert_mapping: Dict[str, str] = {}




class GirlfriendInfo(BaseModel):
    expertId: str
    girlfriend_id: str = ""
    name: str
    description: str = ""
    sys_prompt: Optional[str] = None
    is_system: bool = False
    owner_id: Optional[str] = None


class CreateGirlfriendRequest(BaseModel):
    name: str = Field(..., description="角色名称")
    sys_prompt: str = Field(..., description="系统提示词，定义角色的性格和说话风格")
    model_name: str = Field(default="relay-gemma4-remote", description="使用的模型名称")


class UpdateGirlfriendRequest(BaseModel):
    name: Optional[str] = Field(None, description="女友名称")
    sys_prompt: Optional[str] = Field(None, description="系统提示词")
    model_name: Optional[str] = Field(None, description="使用的模型名称")


# ============= AIGirl兼容的数据模型 =============

class ChatRequest(BaseModel):
    """聊天请求模型（与AIGirl项目完全兼容）"""
    userId: str  # 用户ID
    expertId: str  # 角色ID
    mes: str  # 消息内容（单个字符串）
    source: Optional[str] = "0"  # LLM来源：0=默认模型，1=备用模型（保留字段）
    modelName: Optional[str] = None  # 预留字段，指定使用的模型名称
    apiPath: Optional[str] = None  # 预留字段，指定API路径
    imageUrl: Optional[str] = None  # 预留字段，指定图片URL（多模态支持）

    # 中继鉴权动态参数（客户端按需传入，覆盖服务端默认值）
    appId: Optional[str] = None
    pkgName: Optional[str] = None
    publicKey: Optional[str] = None
    rkey: Optional[str] = None
    country: Optional[str] = None

    # 重新生成相关字段
    retry: Optional[bool] = False  # 是否为重新生成请求
    messageId: Optional[str] = None  # 要重新生成的消息ID（可选）


class DeleteRequest(BaseModel):
    """删除类接口请求模型（聊天记录删除、角色删除）"""
    userId: str
    expertId: str
    mes: Optional[str] = None


class UpdateHistoryRequest(BaseModel):
    """更新聊天记录请求模型"""
    userId: str  # 用户ID
    expertId: str  # 角色ID
    mes: str  # 用户消息（用于定位要修改的对话）
    replay: Optional[str] = None  # 修改后的回复消息（PDF规范字段名）
    reply: Optional[str] = None   # 兼容旧字段名


class ChatResponse(BaseModel):
    """聊天响应模型（与AIGirl项目完全兼容）"""
    success: bool = True
    error: str = "success"
    content: Optional[str] = None
    emotion: Optional[str] = None
    code: int = 0


# ============= 群聊相关数据模型 =============

class CreateGroupRequest(BaseModel):
    """创建群组请求"""
    name: str = Field(..., description="群组名称")
    members: List[str] = Field(..., description="成员角色ID列表")
    userId: str = Field(alias="user_id", serialization_alias="userId", description="创建者用户ID")
    turn_strategy: str = Field(default="reaction", description="发言策略: round_robin, random, reaction")
    auto_response: bool = Field(default=True, description="是否自动让AI回应")

    model_config = {"populate_by_name": True}


class GroupChatRequest(BaseModel):
    """群聊消息请求"""
    message: str = Field(..., description="消息内容")
    userId: str = Field(alias="user_id", serialization_alias="userId", description="用户ID")
    mentioned_girlfriends: Optional[List[str]] = Field(default_factory=list, description="被@的角色ID列表")

    model_config = {"populate_by_name": True}


class GroupChatResponse(BaseModel):
    """群聊消息响应"""
    success: bool
    group_id: str
    user_message: Optional[dict] = None
    ai_responses: List[dict] = Field(default_factory=list)
    error: Optional[str] = None


class AddGroupMemberRequest(BaseModel):
    """添加群组成员请求"""
    expertId: str = Field(..., description="角色ID")


class UpdateGroupNameRequest(BaseModel):
    """更新群组名称请求"""
    name: str = Field(..., description="新的群组名称")


# ============= 会话存储 (Redis) =============
# SessionManager 通过 Redis 存储会话元数据和工作记忆（RedisMemory），
# 通过进程内 LRU Cache 缓存 Agent 和 Mem0 对象。


# ============= 会话管理功能 =============

async def cleanup_inactive_sessions(max_idle_seconds: int = 3600):
    """清理不活跃会话（委托给 SessionManager）"""
    sm = get_session_manager()
    return await sm.cleanup_inactive_sessions(max_idle_seconds)


async def get_session_stats():
    """获取会话统计信息（委托给 SessionManager）"""
    sm = get_session_manager()
    return await sm.get_stats()



async def get_or_create_session(userId: str, expertId: str, session_id: str) -> Dict:
    """获取或创建 session（委托给 Redis SessionManager）"""
    sm = get_session_manager()

    if userId is None:
        userId = f"anonymous_{datetime.now().timestamp()}"

    all_configs = character_manager.get_all()
    if expertId is None or expertId not in all_configs:
        expertId = "101"

    if session_id is None:
        session_id = f"{userId}_{expertId}_session_{datetime.now().timestamp()}"

    session = await sm.get_or_create_session(userId, expertId, session_id)

    try:
        heartbeat_scheduler = get_heartbeat_scheduler()
        heartbeat_scheduler.update_user_activity(userId, expertId)
    except Exception as e:
        logger.debug(f"更新心跳调度器失败: {e}")

    return session


# ============= FastAPI 应用 =============

app = FastAPI(
    title="Girlfriend Chat API",
    description="女友聊天系统 - 用户可以选择不同风格的女友"
)

app.include_router(groups_router)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件服务（用于网页界面）
web_dir = Path(__file__).parent / "web"
web_dist_dir = Path(__file__).parent / "web" / "dist"
if web_dist_dir.exists():
    # 优先使用新的 React 构建版本
    app.mount("/assets", StaticFiles(directory=str(web_dist_dir / "assets")), name="assets")
    logger.info(f"✅ 使用新的 React 前端: http://localhost:8001/")
elif web_dir.exists():
    app.mount("/web", StaticFiles(directory=str(web_dir)), name="web")
    logger.info(f"✅ 静态文件服务已启用: http://localhost:8001/web/index.html")
else:
    logger.warning(f"⚠️  web 目录不存在: {web_dir}")


# ============= 应用启动事件 =============

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    global _heartbeat_scheduler, _greeting_generator

    # 确保 PostgreSQL 表已建立（含 group_chat_history）
    if USE_POSTGRES:
        for _attempt in range(5):
            try:
                await get_postgres_pool()
                break
            except Exception as _e:
                if _attempt < 4:
                    logger.warning(
                        "⚠️ PostgreSQL 连接失败 (第 %d 次), 2s 后重试: %s",
                        _attempt + 1, _e,
                    )
                    await asyncio.sleep(2)
                else:
                    raise
        logger.info("✅ PostgreSQL 表检查完成")

    # 注入 llm_service 所需的运行时依赖（character_manager、DATABASE_DIR）
    llm_service.configure(character_manager, DATABASE_DIR)
    logger.info("✅ llm_service 配置完成")

    # 注入 group_chat_service 所需的运行时依赖
    group_chat_service.configure(character_manager, group_manager, DATABASE_DIR)
    logger.info("✅ group_chat_service 配置完成")

    # 注入 groups router 所需的运行时依赖
    groups_router_module.configure(character_manager, group_manager)
    logger.info("✅ groups router 配置完成")

    # 初始化 Redis 会话管理器并注册工厂函数
    logger.info("🚀 初始化 Redis SessionManager...")
    sm = get_session_manager()
    sm.set_factories(
        create_agent_fn=create_agent,
        create_mem0_fn=create_memory_for_user_and_girlfriend,
    )
    logger.info("✅ SessionManager 就绪，工厂函数已注册")

    logger.info("🚀 初始化推送服务...")

    # 初始化推送服务
    try:
        push_service = await initialize_push_service()
        logger.info("✅ 推送服务初始化完成")
    except Exception as e:
        logger.warning(f"⚠️ 推送服务初始化失败: {e}")
        logger.info("推送功能将使用 WebSocket 直连模式")

    # 注册推送服务 API 路由
    app.include_router(push_api_router)
    logger.info("✅ 推送服务 API 路由已注册")

    # ---- 心跳调度器: 多 Worker 模式下只由一个 Worker 运行 ----
    # 使用 Redis SETNX 做 Leader 选举，避免重复推送
    heartbeat_leader_key = f"{sm._key_prefix}heartbeat_leader"
    # 清理残留的旧 leader key（Gunicorn 被 kill 时 shutdown 可能来不及执行）
    import socket as _socket
    _my_hostname = _socket.gethostname()
    _leader_value = f"{_my_hostname}:{os.getpid()}"

    old_leader = await sm._redis.get(heartbeat_leader_key)
    if old_leader:
        _parts = old_leader.split(":", 1) if ":" in old_leader else ("", old_leader)
        old_hostname, old_pid_str = _parts[0], _parts[-1]
        try:
            old_pid = int(old_pid_str)
        except ValueError:
            old_pid = 0
        import psutil
        # 只有当 hostname 相同（同一台机器/容器）且 PID 已消失时才清理
        if old_hostname == _my_hostname and not psutil.pid_exists(old_pid):
            await sm._redis.delete(heartbeat_leader_key)
            logger.info(
                "🗑️ 清理残留的心跳 Leader key (旧 %s 已不存在)", old_leader
            )
        elif old_hostname != _my_hostname:
            # 来自不同容器实例的旧 key，直接覆盖
            await sm._redis.delete(heartbeat_leader_key)
            logger.info(
                "🗑️ 清理跨容器残留的心跳 Leader key (旧 hostname: %s)", old_hostname
            )
    is_leader = await sm._redis.set(
        heartbeat_leader_key,
        _leader_value,
        nx=True,   # 只在 key 不存在时设置
        ex=3600,    # 1 小时过期（与检查间隔一致，Worker 挂了其他可接管）
    )

    # 每个 Worker 都初始化问候生成器（trigger 端点任意 worker 可用）
    async def greeting_model_caller(raw_messages: list) -> str:
        """用 relay-gemma4-remote 生成问候（带完整对话历史轮次）"""
        from model_config import MODEL_CONFIGS
        from llm_service import call_llm_with_config
        result = await call_llm_with_config(
            user_message="",
            system_prompt="",
            model_config=MODEL_CONFIGS["relay-gemma4-remote"],
            raw_messages=raw_messages,
        )
        if not result:
            raise RuntimeError("问候生成 LLM 调用失败")
        return result

    _greeting_generator = initialize_greeting_generator(
        model_caller=greeting_model_caller,
        chat_history_loader=load_recent_chat_history
    )
    logger.info("✅ 问候生成器初始化完成 (PID %s)", os.getpid())

    if is_leader:
        logger.info("🚀 本 Worker (PID %s) 竞选为心跳调度 Leader，初始化心跳调度器...", os.getpid())

        _heartbeat_scheduler = initialize_heartbeat_scheduler(
            check_interval_hours=1,
            inactive_threshold_hours=4,
            min_greeting_interval_hours=24,
            greeting_probability=0.3,
        )

        async def generate_greeting_callback(user_id, expert_id, **_kwargs):
            """问候生成回调"""
            character_config = character_manager.get(expert_id) or {}
            return await _greeting_generator.generate_greeting(
                user_id=user_id,
                expert_id=expert_id,
                character_config=character_config
            )

        _heartbeat_scheduler.register_greeting_generator(generate_greeting_callback)
        _heartbeat_scheduler.register_push_notification(push_notification_with_service)

        await _heartbeat_scheduler.load_from_db()
        _heartbeat_scheduler.start()

        # 启动后台任务定期续约 Leader 锁
        async def _renew_heartbeat_leader():
            while True:
                await asyncio.sleep(1800)  # 每 30 分钟续约一次
                try:
                    await sm._redis.expire(heartbeat_leader_key, 3600)
                except Exception as e:
                    logger.warning(f"心跳 Leader 续约失败: {e}")
        asyncio.create_task(_renew_heartbeat_leader())

        logger.info("💓 心跳调度器已启动 (Leader PID: %s)", os.getpid())
    else:
        logger.info("⏭️ 本 Worker (PID %s) 非心跳 Leader，跳过心跳调度器初始化", os.getpid())


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理资源"""
    global _heartbeat_scheduler

    # 关闭推送服务
    try:
        push_service = get_push_service()
        await push_service.close()
        logger.info("🛑 推送服务已关闭")
    except Exception as e:
        logger.warning(f"⚠️ 关闭推送服务失败: {e}")

    if _heartbeat_scheduler:
        _heartbeat_scheduler.stop()
        # 释放 Leader 锁，让其他 Worker 可以接管
        try:
            sm = get_session_manager()
            await sm._redis.delete(f"{sm._key_prefix}heartbeat_leader")
        except Exception:
            pass
        logger.info("🛑 心跳调度器已停止，Leader 锁已释放")

    # 关闭 SessionManager
    try:
        sm = get_session_manager()
        await sm.close()
    except Exception as e:
        logger.warning(f"⚠️ 关闭 SessionManager 失败: {e}")


@app.get("/")
async def root():
    # 返回聊天界面
    web_dist_dir = Path(__file__).parent / "web" / "dist"
    if web_dist_dir.exists():
        index_file = web_dist_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
    # 回退到旧版本
    return RedirectResponse(url="/web/index.html")


@app.get("/girlfriends", response_model=List[GirlfriendInfo])
async def list_girlfriends():
    """列出所有可用的角色

    包括系统角色和所有用户自定义角色。
    权限隐藏由客户端实现：用户只能在 app 上看到自己创建的自定义角色。
    """
    girlfriends = []
    for expertId, config in character_manager.get_all().items():
        girlfriends.append(GirlfriendInfo(
            expertId=expertId,
            girlfriend_id=expertId,
            name=config["name"],
            description=config.get("description", "")[:100],
        ))
    return girlfriends


@app.get("/girlfriends/{expertId}", response_model=GirlfriendInfo)
async def get_girlfriend_detail(expertId: str):
    """获取指定角色的详细信息"""
    config = character_manager.get(expertId)
    if config is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    return GirlfriendInfo(
        expertId=expertId,
        girlfriend_id=expertId,
        name=config["name"],
        description=(config.get("sys_prompt") or "")[:100],
        sys_prompt=config.get("sys_prompt") or "",
        is_system=config.get("is_system", True),
        owner_id=config.get("owner_id"),
    )


@app.post("/girlfriends", response_model=GirlfriendInfo)
async def create_character(request: CreateGirlfriendRequest):
    """创建自定义角色"""
    try:
        config = character_manager.create_custom(
            name=request.name,
            sys_prompt=request.sys_prompt,
            model_name=request.model_name,
        )
        return GirlfriendInfo(
            expertId=config["expertId"],
            girlfriend_id=config["expertId"],
            name=config["name"],
            is_system=False,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {str(e)}")


@app.put("/girlfriends/{expertId}", response_model=GirlfriendInfo)
async def update_girlfriend(
    expertId: str,
    request: UpdateGirlfriendRequest,
):
    """更新自定义角色"""
    try:
        config = character_manager.update_custom(
            expert_id=expertId,
            name=request.name,
            sys_prompt=request.sys_prompt,
            model_name=request.model_name,
        )
        return GirlfriendInfo(
            expertId=expertId,
            girlfriend_id=expertId,
            name=config["name"],
            description=(config.get("sys_prompt") or "")[:100],
            is_system=False,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="角色不存在")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"更新失败: {str(e)}")


@app.delete("/girlfriends/{expertId}")
async def delete_girlfriend(expertId: str):
    """删除自定义角色"""
    try:
        character_manager.delete_custom(expertId)
        return {"success": True, "message": f"角色 {expertId} 已删除"}
    except KeyError:
        raise HTTPException(status_code=404, detail="角色不存在")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"删除失败: {str(e)}")


# ============= 系统管理端点 =============

@app.post("/admin/cleanup")
async def cleanup_sessions(max_idle_seconds: int = 3600):
    """清理不活跃的会话，释放内存

    Args:
        max_idle_seconds: 最大空闲时间（秒），默认 3600 (1小时)
    """
    try:
        cleanup_count = await cleanup_inactive_sessions(max_idle_seconds)
        return {
            "message": f"已清理 {cleanup_count} 个不活跃会话",
            "cleanup_count": cleanup_count,
            "max_idle_seconds": max_idle_seconds
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清理失败: {str(e)}")


@app.get("/admin/stats")
async def admin_stats():
    """获取详细的系统统计信息"""
    try:
        stats = await get_session_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")


@app.get("/health/detailed")
async def health_check():
    """健康检查 - 详细版本"""
    try:
        session_stats = await get_session_stats()

        # 检查各个组件
        health = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "sessions": {
                    "status": "ok",
                    "total_users": session_stats["total_users"],
                    "total_sessions": session_stats["total_sessions"]
                },
                "memory": {
                    "status": "ok",
                    "usage_mb": session_stats["memory_mb"]
                }
            }
        }

        # 检查是否需要清理
        if session_stats["total_sessions"] > 1000:
            health["warnings"] = [
                f"会话数量较多 ({session_stats['total_sessions']})，建议调用 /admin/cleanup 清理"
            ]

        return health
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@app.post("/api/mobile/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """聊天接口（与AIGirl项目完全兼容）

    与AIGirl项目的POST /api/mobile/chat接口完全兼容：
    - 接收单个字符串消息(mes)，转换为内部消息数组格式
    - 返回AIGirl格式的响应{success, error, content, code}
    - 支持source、modelName、apiPath、imageUrl等预留字段
    - 支持动态模型切换（通过modelName和apiPath参数）
    - ✅ 使用完整的Agent系统（支持工具调用和记忆管理）
    """
    try:
        # 使用信号量限制并发
        async with request_semaphore:
            # 获取角色配置
            girlfriend_config = character_manager.get(request.expertId)
            if not girlfriend_config:
                return ChatResponse(
                    success=False,
                    error=f"未找到expertId为 {request.expertId} 的角色",
                    content=None,
                    code=-1
                )

            # 获取或创建 session（Redis-backed）
            fixed_sid = f"{request.userId}_{request.expertId}_session"
            session = await get_or_create_session(request.userId, request.expertId, fixed_sid)

            # 实际的 session_id
            actual_session_id = f"{request.userId}_{request.expertId}_session_*"

            agent = session["agent"]
            memory = session["memory"]

            # 处理重新生成：清理多重记忆
            if request.retry:
                logger.info(f"🔄 检测到重新生成请求 (messageId: {request.messageId})")

                # 从短期记忆中删除最后的AI消息
                last_msg = await SessionManager.get_last_message(memory)
                if last_msg and hasattr(last_msg, 'role') and last_msg.role == 'assistant':
                    await SessionManager.remove_last_message(memory, role='assistant')
                    logger.info(f"🗑️  已从短期记忆删除上次AI回复")

                # 使用重新生成管理器清理长期记忆
                try:
                    regeneration_manager = get_regeneration_manager()
                    long_term_memory = session.get("long_term_memory")

                    await regeneration_manager.handle_regeneration(
                        session_id=actual_session_id,
                        user_message_id=None,
                        old_assistant_message_id=request.messageId,
                        memory=memory,
                        long_term_memory=long_term_memory,
                        user_id=request.userId,
                        expert_id=request.expertId
                    )
                except Exception as e:
                    logger.warning(f"⚠️ 清理长期记忆失败: {e}")

            # 限制短期记忆大小，避免过多历史导致模型输入过大
            await SessionManager.trim_memory(memory, MAX_PRIVATE_CHAT_HISTORY)

            # 🔄 转换消息格式：工具调用完全由 ReActAgent 处理
            agentscope_messages = [
                Msg(
                    name=request.userId or "用户",
                    role="user",
                    content=request.mes,
                )
            ]

            # agent.reply() 获取完整推理过程
            if CHAT_MODEL.startswith("relay"):
                try:
                    agent.model.session_memory = session.get("memory")
                    agent.model._relay_params = {
                        "app_id": request.appId,
                        "pkg_name": request.pkgName,
                        "public_key": request.publicKey,
                        "rkey": request.rkey or "",
                        "country": request.country or "",
                        "image_url": request.imageUrl or "",
                        "model_name": request.modelName or "",
                        "api_path": request.apiPath or "",
                    }
                except Exception:
                    pass
            reply_msg = await agent.reply(agentscope_messages)

            # 🔥 提取完整的推理过程
            content = ""
            if hasattr(reply_msg, 'content'):
                raw = reply_msg.content

                # 直接从 block 列表提取文本
                if isinstance(raw, list):
                    text_parts = []
                    for block in raw:
                        if isinstance(block, dict) and block.get('type') == 'text':
                            text_parts.append(block.get('text') or '')
                    content = ''.join(text_parts)
                    logger.info(f"🔍 从 {len(raw)} 个 block 中提取文本: {len(content)} 字符")
                elif isinstance(raw, str):
                    content = raw
                else:
                    content = str(raw)


            if not content:
                logger.warning(f"⚠️ 模型返回空内容，reply_msg type: {type(reply_msg)}, content blocks: {reply_msg.content}")
                content = ""

            text = content

            # 如果文本为空，提供友好提示
            if not text or text.isspace():
                text = f"{girlfriend_config['name']}在思考中..."

            # 记录日志
            logger.info(f"AI响应生成成功: mes={request.mes}, userId={request.userId}, "
                       f"expertId={request.expertId}, source={request.source}, "
                       f"响应内容={text[:50]}...")

            # agent.reply() 已将消息写入短期+长期记忆，此处只做 DB 持久化
            try:
                # 💾 保存聊天历史到PostgreSQL（同步等待，确保保存完成）
                try:
                    await save_chat_history_to_db(
                        request.userId,
                        request.expertId,
                        request.mes,
                        text,
                        None
                    )
                except Exception as e:
                    logger.warning(f"保存聊天历史到数据库失败: {e}")

                # 用户画像追踪暂时停用（画像系统待架构优化后重新启用）
                # profile_manager = get_profile_manager()
                # current_round = profile_manager.increment_round(...)
                # if profile_manager.should_trigger_summary(...):
                #     asyncio.create_task(trigger_summary())

            except Exception as e:
                logger.warning(f"保存对话记忆失败: {e}")

            # 返回AIGirl格式的响应
            return ChatResponse(
                success=True,
                error="success",
                content=text,
                emotion=None,
                code=0
            )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"处理失败: {str(e)[:200]}\n{traceback.format_exc()}"
        logger.error(f"AIGirl聊天接口错误: {error_detail}")

        # 检查是否是 API Key 相关错误
        error_str = str(e).lower()
        if "api_key" in error_str or "api key" in error_str or "authentication" in error_str:
            return ChatResponse(
                success=False,
                error=f"API 配置错误: 请确保已设置相应的API密钥环境变量",
                content=None,
                code=-100
            )

        return ChatResponse(
            success=False,
            error=str(e)[:200],
            content=None,
            code=-1
        )


@app.post("/api/roles/upload")
async def aigirl_upload_role(request: Request):
    """AIGirl兼容的上传角色配置接口

    与AIGirl项目的POST /api/roles/upload接口完全兼容：
    - 接收原始JSON字符串格式的角色配置
    - 保存到characters目录
    - 返回{success, msg}格式
    """
    try:
        # 获取原始body（字符串）
        raw_body = await request.body()
        json_str = raw_body.decode("utf-8")

        # 解析JSON
        data = json.loads(json_str)

        # 提取expertId
        expert_id = data.get("expertId")
        if not expert_id:
            return {"success": False, "msg": "缺少 expertId 字段"}

        # 保存到characters目录
        success = character_manager.create(data)

        if success:
            logger.info(f"✅ 上传新角色: {expert_id} - {data.get('name', '')}")
            return {"success": True, "msg": "ok"}
        else:
            return {"success": False, "msg": f"角色 {expert_id} 已存在或创建失败"}

    except json.JSONDecodeError:
        return {"success": False, "msg": "无效的 JSON 字符串"}
    except Exception as e:
        logger.error(f"AIGirl上传角色失败: {e}")
        return {"success": False, "msg": f"上传失败: {str(e)}"}


@app.post("/api/roles/delete")
async def delete_role_chat_history(request: DeleteRequest):
    """删除聊天历史接口（与AIGirl项目对应）

    mes=None 时删除全部；mes 有值时只删除匹配的那条用户消息及
    其紧随的 AI 回复（Redis 工作记忆 + PostgreSQL chat_history）。
    """
    try:
        userId = request.userId
        expertId = request.expertId
        mes = request.mes or None  # 空字符串也视为未传

        sm = get_session_manager()

        if mes is None:
            # 删除全部：清空 Redis 会话 + PostgreSQL 聊天历史
            await sm.delete_sessions(userId, expertId)
            pool = await get_postgres_pool()
            if pool:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "DELETE FROM chat_history "
                        "WHERE user_id=$1 AND expert_id=$2",
                        userId, expertId,
                    )
            logger.info(
                f"✅ 清空全部聊天历史: userId={userId},"
                f" expertId={expertId}"
            )
            return {
                "success": True,
                "msg": (
                    f"用户 {userId} 与角色 {expertId} 的聊天历史已清空"
                ),
            }
        else:
            # 删除单条：Redis 工作记忆 + PostgreSQL
            fixed_sid = f"{userId}_{expertId}_session"
            redis_deleted = False
            if await sm.has_sessions(userId, expertId):
                session = await get_or_create_session(
                    userId, expertId, fixed_sid
                )
                redis_deleted = await SessionManager.find_and_delete_message(
                    session["memory"], mes
                )
            db_deleted = await delete_chat_message_from_db(
                userId, expertId, mes
            )
            if redis_deleted or db_deleted:
                logger.info(
                    f"✅ 删除单条消息: userId={userId},"
                    f" expertId={expertId}, mes={mes[:30]}"
                )
                return {"success": True, "msg": "消息已删除"}
            else:
                return {
                    "success": False,
                    "msg": "未找到匹配的消息",
                }

    except Exception as e:
        logger.error(f"删除聊天历史失败: {e}")
        return {"success": False, "msg": f"删除聊天历史失败: {str(e)}"}


@app.post("/api/roles/role_delete")
async def aigirl_delete_role(request: DeleteRequest):
    """删除角色配置接口
    - 删除指定角色配置文件
    - 返回{success, msg}格式
    - 权限隔离由客户端实现（客户端只显示该用户的自定义角色）
    """
    try:
        expertId = request.expertId

        success = character_manager.delete(expertId)
        if success:
            logger.info(f"✅ 删除角色: {expertId}")
            return {"success": True, "msg": f"角色 {expertId} 删除成功"}
        else:
            return {"success": False, "msg": f"未找到角色 {expertId}"}

    except Exception as e:
        logger.error(f"删除角色失败: {e}")
        return {"success": False, "msg": f"删除角色失败: {str(e)}"}


@app.post("/api/roles/update_history")
async def update_history(request: UpdateHistoryRequest):
    """更新聊天记录接口

    手动修改AI的历史回复内容：
    - 根据用户消息定位对话
    - 将对应的AI回复修改为新内容
    - 同时更新内存和历史文件
    """
    try:
        userId = request.userId
        expertId = request.expertId
        target_mes = request.mes
        # 兼容 replay（PDF规范）和 reply（旧字段名）
        new_reply = request.replay or request.reply
        if not new_reply:
            return {"success": False, "msg": "缺少 replay 或 reply 参数"}

        # 获取会话（通过 SessionManager）
        sm = get_session_manager()
        if not await sm.has_sessions(userId, expertId):
            return {"success": False, "msg": "未找到对应的会话记录"}

        # 获取当前会话的 memory 并执行查找/更新
        fixed_sid = f"{userId}_{expertId}_session"
        session = await get_or_create_session(userId, expertId, fixed_sid)
        memory = session["memory"]

        found = await SessionManager.find_and_update_reply(
            memory, target_mes, new_reply,
        )

        if found:
            logger.info(
                f"✅ 更新聊天记录: userId={userId},"
                f" expertId={expertId}"
            )
            logger.info(f"   原消息: {target_mes}")
            logger.info(f"   新回复: {new_reply[:50]}...")
            return {"success": True, "msg": "聊天记录更新成功"}
        else:
            return {"success": False, "msg": "未找到匹配的用户消息"}

    except Exception as e:
        logger.error(f"更新聊天记录失败: {e}")
        return {"success": False, "msg": f"更新聊天记录失败: {str(e)}"}


@app.get("/api")
async def aigirl_api_info():
    """AIGirl兼容的API信息接口

    - 返回API基本信息
    """
    return {
        "name": "AgentScope Runtime API",
        "version": "1.0.0",
        "description": "AIGirl兼容的AI女友聊天系统",
        "endpoints": {
            "chat": "/api/mobile/chat",
            "roles_upload": "/api/roles/upload",
            "roles_delete": "/api/roles/delete",
            "role_delete": "/api/roles/role_delete",
            "girlfriends": "/girlfriends",
            "history": "/history",
            "clear": "/clear",
            "models": "/api/models"
        }
    }


@app.get("/api/models")
async def list_models():
    """获取所有可用的模型配置

    返回所有支持的LLM模型列表，包括：
    - 模型名称
    - 模型描述
    - 是否需要API密钥
    - API密钥环境变量名
    """
    models = []
    for model_id, config in MODEL_CONFIGS.items():
        model_info = {
            "id": model_id,
            "name": config["model_name"],
            "description": config["description"],
            "requires_api_key": config.get("api_key_env", "") != "FAKE_API_KEY",
            "api_key_env": config.get("api_key_env", ""),
        }

        # 添加特殊标记
        if model_id == CHAT_MODEL:
            model_info["is_default"] = True

        models.append(model_info)

    return {
        "success": True,
        "models": models,
        "current_model": CHAT_MODEL
    }


@app.get("/history")
async def get_history(user_id: str, expertId: str, limit: int = 50):
    """获取聊天历史接口

    与AIGirl项目的GET /history接口完全兼容：
    - 优先从PostgreSQL加载历史（持久化）
    - 如果数据库无数据，从内存加载
    - 返回历史记录列表
    """
    try:
        # 运行时检查PostgreSQL是否可用
        use_postgres = os.getenv("POSTGRES_URL") is not None
        logger.info(f"🔍 历史请求: {user_id}/{expertId}, use_postgres={use_postgres}")

        # 优先从PostgreSQL加载历史（持久化）
        if use_postgres:
            db_history = await load_chat_history_from_db(user_id, expertId, limit)
            logger.info(f"📊 db_history结果: {len(db_history)} 条记录")
            if db_history:
                logger.info(f"✅ 从PostgreSQL加载历史: userId={user_id}, expertId={expertId}, 消息数={len(db_history)}")
                return {"success": True, "history": db_history}
            else:
                logger.info(f"⚠️ PostgreSQL无历史记录，尝试内存加载")

        # 从 Redis 工作记忆加载历史（回退方案）
        sm = get_session_manager()
        if not await sm.has_sessions(user_id, expertId):
            logger.info(f"⚠️ Redis 中无会话: {user_id}/{expertId}")
            return {"success": True, "history": [], "message": "无聊天历史"}

        try:
            fixed_sid = f"{user_id}_{expertId}_session"
            session = await get_or_create_session(user_id, expertId, fixed_sid)
            memory = session["memory"]
            msgs = await SessionManager.get_all_messages(
                memory, roles=["user", "assistant"],
            )
            all_messages = [
                {
                    "role": m.role,
                    "content": str(m.content),
                    "name": getattr(m, "name", ""),
                }
                for m in msgs
            ]
        except Exception as mem_err:
            logger.warning(f"⚠️ Redis 记忆加载失败: {mem_err}")
            all_messages = []

        logger.info(f"✅ 从 Redis 加载历史: userId={user_id}, expertId={expertId}, "
                   f"消息数={len(all_messages)}")
        return {"success": True, "history": all_messages}

    except Exception as e:
        logger.error(f"获取聊天历史失败: {e}")
        return {"success": False, "error": str(e)}


@app.post("/clear")
async def clear_chat_history(user_id: str, expertId: str):
    """清空聊天历史接口

    与AIGirl项目的POST /clear接口完全兼容：
    - 使用查询参数：user_id 和 expertId
    - 清空指定用户和角色的聊天历史
    - 返回{success, msg}格式
    """
    try:
        # 清空 Redis 中的会话和工作记忆
        sm = get_session_manager()
        await sm.delete_sessions(user_id, expertId)

        logger.info(f"✅ 清空聊天历史: userId={user_id}, expertId={expertId}")
        return {"success": True, "msg": f"用户 {user_id} 与角色 {expertId} 的聊天历史已清空"}

    except Exception as e:
        logger.error(f"清空聊天历史失败: {e}")
        return {"success": False, "msg": f"清空聊天历史失败: {str(e)}"}


@app.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str):
    """获取指定 session 的聊天历史"""
    try:
        # 通过 Redis 查找 session 元数据
        sm = get_session_manager()
        meta = await sm.find_session_by_id(session_id)
        if not meta:
            raise HTTPException(status_code=404, detail="Session 不存在")

        # 获取该 session 的 RedisMemory 并读取所有消息
        session_obj = await sm.get_or_create_session(
            meta["user_id"], meta["expert_id"], session_id,
        )
        memory = session_obj["memory"]
        all_msgs = await SessionManager.get_all_messages(memory)

        messages = []
        for msg in all_msgs:
            # 跳过内部系统消息
            if msg.role in ["system", "long_term_memory"]:
                continue
            content_str = msg.content if isinstance(msg.content, str) else str(msg.content)
            if "[{" in content_str and "'tool_use'" in content_str:
                continue
            if content_str.startswith("<long_term_memory>"):
                continue

            messages.append({
                "role": msg.role,
                "content": content_str,
                "name": msg.name if hasattr(msg, "name") else None,
            })

        return {
            "session_id": session_id,
            "messages": messages,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话历史失败: {e}")
        raise HTTPException(status_code=500, detail="获取会话历史失败")


@app.get("/admin/sessions")
async def list_sessions():
    """列出所有用户、女友和 session"""
    result = {
        "users": []
    }

    sm = get_session_manager()
    all_sessions = await sm.list_all_sessions()

    for userId, girlfriends in all_sessions.items():
        user_data = {
            "userId": userId,
            "girlfriends": []
        }

        for expertId, session_list in girlfriends.items():
            girlfriend_config = character_manager.get(expertId)
            if girlfriend_config is None:
                girlfriend_config = character_manager.get("tiantian") or {"name": "Unknown"}

            girlfriend_data = {
                "expertId": expertId,
                "name": girlfriend_config.get("name", "Unknown"),
                "sessions": []
            }

            for sess_info in session_list:
                girlfriend_data["sessions"].append({
                    "session_id": sess_info.get("session_id", ""),
                    "created_at": sess_info.get("created_at", ""),
                    "last_activity": sess_info.get("last_activity", ""),
                })

            user_data["girlfriends"].append(girlfriend_data)

        result["users"].append(user_data)

    return result


# ============= 用户画像 API =============

@app.get("/user_profile/{user_id}/{expert_id}")
async def get_user_profile(user_id: str, expert_id: str):
    """获取用户画像内容

    Args:
        user_id: 用户ID
        expert_id: 角色ID

    Returns:
        用户画像内容和统计信息
    """
    try:
        profile_manager = get_profile_manager()

        # 获取画像内容
        profile_content = await profile_manager.load_profile(user_id, expert_id)

        # 获取统计信息
        stats = profile_manager.get_profile_stats(user_id, expert_id)

        return {
            "success": True,
            "user_id": user_id,
            "expert_id": expert_id,
            "profile": profile_content,
            "stats": stats
        }

    except Exception as e:
        logger.error(f"获取用户画像失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/user_profile/{user_id}/{expert_id}/trigger_summary")
async def trigger_profile_summary(user_id: str, expert_id: str):
    """手动触发用户画像总结（对话结束时调用）

    Args:
        user_id: 用户ID
        expert_id: 角色ID

    Returns:
        总结结果
    """
    try:
        profile_manager = get_profile_manager()

        # 获取当前会话
        session = get_or_create_session(user_id, expert_id, None)
        _ltm = session.get("long_term_memory")

        # 创建模型调用函数
        async def model_caller(prompt: str) -> str:
            return await call_llm_with_config(
                user_message=prompt,
                system_prompt="You are a professional user-profile curator. Output strict JSON only.",
                model_config=current_model_config,
                history=None
            )

        # 使用 mem0 事实整理结构化画像
        summary = await profile_manager.summarize_and_save(
            user_id=user_id,
            expert_id=expert_id,
            model_caller=model_caller,
            long_term_memory=_ltm,
        )

        # 重置对话轮次
        profile_manager.reset_rounds(user_id, expert_id)

        return {
            "success": True,
            "message": "用户画像总结完成",
            "summary": summary if summary else "无新发现"
        }

    except Exception as e:
        logger.error(f"触发用户画像总结失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.delete("/user_profile/{user_id}/{expert_id}")
async def delete_user_profile(user_id: str, expert_id: str):
    """删除用户画像

    Args:
        user_id: 用户ID
        expert_id: 角色ID

    Returns:
        删除结果
    """
    try:
        from pathlib import Path

        json_path = Path("user_profiles") / f"{user_id}_{expert_id}.json"
        md_path = Path("user_profiles") / f"{user_id}_{expert_id}.md"
        rounds_path = Path("user_profiles") / f".{user_id}_{expert_id}_rounds.json"

        deleted = False

        for p in [json_path, md_path, rounds_path]:
            if p.exists():
                p.unlink()
                deleted = True

        if deleted:
            return {
                "success": True,
                "message": f"已删除用户画像: {user_id} + {expert_id}"
            }
        else:
            return {
                "success": False,
                "message": "用户画像不存在"
            }

    except Exception as e:
        logger.error(f"删除用户画像失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# ============= 心跳调度器相关 API =============

@app.get("/heartbeat/stats")
async def get_heartbeat_stats():
    """获取心跳调度器统计信息

    Returns:
        调度器统计信息
    """
    try:
        heartbeat_scheduler = get_heartbeat_scheduler()
        stats = heartbeat_scheduler.get_stats()

        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        logger.error(f"获取心跳统计失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/heartbeat/user/{user_id}/{expert_id}")
async def get_user_heartbeat(user_id: str, expert_id: str):
    """获取用户心跳信息

    Args:
        user_id: 用户ID
        expert_id: 角色ID

    Returns:
        用户心跳信息
    """
    try:
        heartbeat_scheduler = get_heartbeat_scheduler()
        heartbeat = heartbeat_scheduler.get_user_heartbeat(user_id, expert_id)

        if heartbeat:
            return {
                "success": True,
                "data": {
                    "user_id": heartbeat.user_id,
                    "expert_id": heartbeat.expert_id,
                    "last_active_time": heartbeat.last_active_time.isoformat(),
                    "last_greeting_time": heartbeat.last_greeting_time.isoformat() if heartbeat.last_greeting_time else None,
                    "greeting_count": heartbeat.greeting_count,
                    "is_active": heartbeat.is_active
                }
            }
        else:
            return {
                "success": False,
                "message": "用户心跳信息不存在"
            }
    except Exception as e:
        logger.error(f"获取用户心跳失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/heartbeat/{user_id}/{expert_id}/trigger_greeting")
async def trigger_heartbeat_greeting(user_id: str, expert_id: str):
    """手动触发心跳问候（用于测试）。

    直接在当前 worker 生成并推送，不依赖 leader 选举。
    """
    try:
        from heartbeat_greeting_generator import get_greeting_generator
        greeting_gen = get_greeting_generator()
        if greeting_gen.model_caller is None:
            return {"success": False, "error": "问候生成器未初始化，请重启服务"}

        character_config = character_manager.get(expert_id) or {}
        greeting = await greeting_gen.generate_greeting(
            user_id=user_id,
            expert_id=expert_id,
            character_config=character_config,
        )
        if not greeting:
            return {"success": False, "error": "LLM 未返回内容"}

        await push_notification_with_service(user_id, expert_id, greeting)
        return {
            "success": True,
            "message": "问候已发送",
            "data": {"greeting_message": greeting},
        }
    except Exception as e:
        logger.error(f"手动触发问候失败: {e}")
        return {"success": False, "error": str(e)}


@app.post("/heartbeat/start")
async def start_heartbeat_scheduler():
    """启动心跳调度器

    Returns:
        启动结果
    """
    try:
        heartbeat_scheduler = get_heartbeat_scheduler()

        if heartbeat_scheduler.scheduler.running:
            return {
                "success": False,
                "message": "心跳调度器已经在运行"
            }

        heartbeat_scheduler.start()

        return {
            "success": True,
            "message": "心跳调度器已启动"
        }
    except Exception as e:
        logger.error(f"启动心跳调度器失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/heartbeat/stop")
async def stop_heartbeat_scheduler():
    """停止心跳调度器

    Returns:
        停止结果
    """
    try:
        heartbeat_scheduler = get_heartbeat_scheduler()

        if not heartbeat_scheduler.scheduler.running:
            return {
                "success": False,
                "message": "心跳调度器未运行"
            }

        heartbeat_scheduler.stop()

        return {
            "success": True,
            "message": "心跳调度器已停止"
        }
    except Exception as e:
        logger.error(f"停止心跳调度器失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# ============= WebSocket 支持 =============

@app.websocket("/ws/{user_id}/{expert_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str, expert_id: str):
    """
    WebSocket 连接端点

    支持：
    - 实时聊天消息
    - 心跳问候推送
    - 连接状态管理
    """
    import time
    start_time = time.time()

    await websocket.accept()

    accept_time = time.time()
    if accept_time - start_time > 0.1:
        logger.warning(f"⚠️ WebSocket accept 耗时: {(accept_time - start_time)*1000:.2f}ms")

    # 生成唯一的连接 ID
    connection_id = str(uuid.uuid4())

    # 保存连接
    active_websockets[connection_id] = websocket
    user_to_connection[user_id] = connection_id
    connection_to_user[connection_id] = user_id
    user_expert_mapping[user_id] = expert_id

    logger.info(f"✅ WebSocket 连接建立: {user_id} -> {expert_id} ({connection_id})")

    # 桥接：同步注册到 PushService 的 ConnectionRegistry
    try:
        push_service = get_push_service()
        await push_service.connection_registry.register_connection(
            user_id=user_id,
            expert_id=expert_id,
            connection_id=connection_id,
            websocket=websocket
        )
    except Exception as e:
        logger.debug(f"注册到 PushService 连接注册表失败: {e}")

    # 更新心跳（用户现在在线）- 使用非阻塞方式
    try:
        heartbeat_scheduler = get_heartbeat_scheduler()
        heartbeat_scheduler.update_user_activity(user_id, expert_id)
    except Exception as e:
        logger.debug(f"更新心跳调度器失败: {e}")

    # 离线消息不再通过 WebSocket 重复投递：
    # 问候消息已保存到 chat_history (Phase 2c)，前端切换角色时会通过
    # GET /history 加载，无需 WebSocket 额外推送（避免与 loadHistoryFromBackend 产生重复）。
    # 离线队列保留用于未来平台推送 (FCM/APNs/WebPush)。

    total_time = (time.time() - start_time) * 1000
    if total_time > 100:
        logger.warning(f"⚠️ WebSocket 连接建立总耗时: {total_time:.2f}ms")

    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                logger.warning(f"⚠️ 无效的 JSON 消息: {data}")
                continue

            msg_type = message.get("type")

            if msg_type == "chat":
                # 处理聊天消息
                await handle_websocket_chat(user_id, expert_id, message.get("content", ""), websocket)

            elif msg_type == "heartbeat":
                # 客户端心跳（仅保持 WebSocket 连接，不更新活跃时间）
                # 活跃时间只在用户真正发消息时才更新，避免误判为"活跃"
                await websocket.send_json({"type": "heartbeat_ack"})

            elif msg_type == "ping":
                # WebSocket ping/pong
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info(f"❌ WebSocket 断开: {user_id} ({connection_id})")

    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")

    finally:
        # 清理连接 — 只清理属于本连接的映射，避免误删新连接
        active_websockets.pop(connection_id, None)
        connection_to_user.pop(connection_id, None)
        # 只有当映射仍指向本连接时才删除，防止新连接被误清
        if user_to_connection.get(user_id) == connection_id:
            user_to_connection.pop(user_id, None)
            user_expert_mapping.pop(user_id, None)

        # 同步从 PushService 连接注册表注销
        try:
            push_service = get_push_service()
            await push_service.connection_registry.unregister_connection(user_id, connection_id)
        except Exception:
            pass


async def handle_websocket_chat(user_id: str, expert_id: str, content: str, websocket: WebSocket):
    """
    处理 WebSocket 聊天消息

    与 HTTP /api/mobile/chat 共享核心逻辑：
    - 工具调用由 ReActAgent 自动处理
    - block 列表文本提取
    - 清理模型输出
    - 聊天历史持久化
    """
    import time
    start_time = time.time()

    try:
        # 获取或创建会话（Redis-backed）
        fixed_sid = f"{user_id}_{expert_id}_session"
        session = await get_or_create_session(user_id, expert_id, fixed_sid)
        agent = session["agent"]
        memory = session["memory"]

        girlfriend_config = character_manager.get(expert_id) or character_manager.get("101") or {}

        # 限制短期记忆大小
        await SessionManager.trim_memory(memory, MAX_PRIVATE_CHAT_HISTORY)

        # 转换消息格式：工具调用完全由 ReActAgent 处理
        agentscope_messages = [
            Msg(name=user_id, role="user", content=content)
        ]

        # 调用 agent
        if CHAT_MODEL.startswith("relay"):
            try:
                agent.model.session_memory = session.get("memory")
            except Exception:
                pass
        agent_start = time.time()
        reply_msg = await agent.reply(agentscope_messages)
        agent_time = (time.time() - agent_start) * 1000
        logger.info(f"🤖 [WS] AI 响应耗时: {agent_time:.2f}ms")

        # 提取文本：从 block 列表中提取
        response_text = ""
        if hasattr(reply_msg, 'content'):
            raw = reply_msg.content
            if isinstance(raw, list):
                text_parts = []
                for block in raw:
                    if isinstance(block, dict) and block.get('type') == 'text':
                        text_parts.append(block.get('text') or '')
                response_text = ''.join(text_parts)
                logger.info(f"🔍 [WS] 从 {len(raw)} 个 block 中提取文本: {len(response_text)} 字符")
            elif isinstance(raw, str):
                response_text = raw
            else:
                response_text = str(raw)
        if not response_text:
            response_text = str(reply_msg)


        if not response_text or response_text.isspace():
            response_text = f"{girlfriend_config.get('name', 'AI')}在思考中..."

        # 发送响应
        await websocket.send_json({
            "type": "chat_response",
            "content": response_text,
            "emotion": None,
            "timestamp": datetime.now().isoformat()
        })

        # 保存聊天历史到 PostgreSQL
        try:
            await save_chat_history_to_db(user_id, expert_id, content, response_text, None)
        except Exception as e:
            logger.warning(f"[WS] 保存聊天历史到数据库失败: {e}")

        # 更新心跳
        heartbeat_scheduler = get_heartbeat_scheduler()
        heartbeat_scheduler.update_user_activity(user_id, expert_id)

    except Exception as e:
        logger.error(f"处理聊天消息失败: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })


async def push_notification_with_service(user_id: str, expert_id: str, message: str) -> bool:
    """
    使用 PushService 推送消息给用户 (支持离线推送)

    智能路由策略:
    1. WebSocket (如果在线)
    2. 平台推送 (FCM/APNs/WebPush)
    3. 离线队列 (兜底)

    Args:
        user_id: 用户ID
        expert_id: 角色ID
        message: 要推送的消息

    Returns:
        bool: 推送是否成功 (至少一个渠道成功)
    """
    try:
        push_service = get_push_service()

        result = await push_service.send_to_user(
            user_id=user_id,
            expert_id=expert_id,
            title="想念你～",
            body=message,
            message_type="greeting",
            priority=3  # 低优先级
        )

        # Phase 2c: 将问候消息保存到聊天历史，确保刷新页面后仍然可见
        try:
            pool = await get_postgres_pool()
            if pool:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO chat_history (user_id, expert_id, role, content, emotion) VALUES ($1, $2, $3, $4, $5)",
                        user_id, expert_id, "assistant", message, "爱意"
                    )
                logger.info(f"💾 问候消息已保存到聊天历史: {user_id}/{expert_id}")
        except Exception as e:
            logger.warning(f"保存问候到聊天历史失败: {e}")

        return result.delivered or result.queued

    except Exception as e:
        logger.error(f"❌ PushService 推送失败: {e}")
        # 降级到原有 WebSocket 推送
        return await push_websocket_notification(user_id, expert_id, message)


async def push_websocket_notification(user_id: str, expert_id: str, message: str) -> bool:
    """
    通过 WebSocket 推送消息给用户

    Args:
        user_id: 用户ID
        expert_id: 角色ID
        message: 要推送的消息

    Returns:
        bool: 推送是否成功
    """
    connection_id = user_to_connection.get(user_id)
    if not connection_id:
        logger.debug(f"⚠️ 用户 {user_id} 未在线")
        return False

    websocket = active_websockets.get(connection_id)
    if not websocket:
        logger.debug(f"⚠️ 连接 {connection_id} 不存在")
        return False

    try:
        response = {
            "type": "heartbeat_greeting",
            "expert_id": expert_id,
            "content": message,
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send_json(response)
        logger.info(f"✅ WebSocket 推送成功: {user_id}")
        return True

    except Exception as e:
        logger.error(f"❌ WebSocket 推送失败: {e}")
        # 清理失效的连接 — 只清理属于本连接的映射
        active_websockets.pop(connection_id, None)
        connection_to_user.pop(connection_id, None)
        if user_to_connection.get(user_id) == connection_id:
            user_to_connection.pop(user_id, None)
        return False


# ============= 前端界面 =============

# 挂载静态文件目录
web_dir = Path(__file__).parent / "web"
if web_dir.exists():
    app.mount("/web", StaticFiles(directory=str(web_dir)), name="web")


@app.get("/chat")
async def chat_interface():
    """聊天界面入口"""
    chat_file = web_dir / "chat" / "index.html"
    if chat_file.exists():
        return FileResponse(str(chat_file))
    else:
        raise HTTPException(status_code=404, detail="聊天界面文件不存在")


# ============= 启动服务器 =============

if __name__ == "__main__":
    import uvicorn
    logger.info("=" * 60)
    logger.info("AI女友聊天系统启动 (开发模式 - 单 Worker)")
    logger.info("=" * 60)
    logger.info(f"聊天界面: http://localhost:8001/chat")
    logger.info(f"API文档:  http://localhost:8001/docs")
    logger.info(f"WebSocket: ws://localhost:8001/ws/{{user_id}}/{{expert_id}}")
    logger.info("=" * 60)
    logger.info("生产模式请使用: ./start_production.sh")
    logger.info("=" * 60)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info",
    )