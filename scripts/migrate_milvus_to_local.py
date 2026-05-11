#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Milvus → 本地 PostgreSQL 历史数据迁移脚本

用法：
    # Phase 1：仅迁移聊天历史到 PostgreSQL
    python scripts/migrate_milvus_to_local.py --phase chat

    # Phase 2：对已迁移的历史进行 mem0 事实回填（耗时，可中断重跑）
    python scripts/migrate_milvus_to_local.py --phase mem0

    # 两个阶段连续执行
    python scripts/migrate_milvus_to_local.py --phase all

    # 仅迁移指定截止时间之前的数据（ISO 格式或 Unix 毫秒时间戳字符串）
    python scripts/migrate_milvus_to_local.py --phase chat --cutoff "2025-04-01T00:00:00"

    # 指定用户子集（调试用）
    python scripts/migrate_milvus_to_local.py --phase chat --users user_001 user_002

注意：
  - Phase 1 幂等：同一条记录不会重复写入（按 user_id+expert_id+role+content 去重）
  - Phase 2 幂等：mem0 本身会语义去重，重复运行只会增量补充
  - 运行前确保 .env 已加载（POSTGRES_URL）
  - Phase 2 使用 relay-gemma4-remote 做 LLM 事实提取
"""

import argparse
import asyncio
import gc
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# *** 最优先：在任何 C 扩展（gRPC/pymilvus）加载前清除代理 ***
# gRPC 在 import 时读取系统代理，必须在 import pymilvus 之前清掉
import os as _os
for _k in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy",
           "GRPC_PROXY", "grpc_proxy", "ALL_PROXY", "all_proxy"):
    _os.environ.pop(_k, None)

# 加载项目根目录的 .env
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# proxy_config 再次清代理（覆盖 .env 可能带进来的代理变量）
import proxy_config  # noqa: F401

# 初始化 llm_service 所需的运行时依赖（脚本独立运行，无 FastAPI startup）
from pathlib import Path as _Path
from character_config_manager import CharacterConfigManager as _CCM
import llm_service as _llm_service

_characters_dir = ROOT / "characters"
_character_manager = _CCM(characters_dir=str(_characters_dir))
_database_dir = ROOT / "databases"
_database_dir.mkdir(exist_ok=True)
_llm_service.configure(_character_manager, _database_dir)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ── 防止 mem0 GC 时关闭全局 psycopg2 连接池 ──────────────────
# mem0 每次实例被回收时都会调用 pool.closeall()，导致后续所有实例创建失败。
# 直接在 ThreadedConnectionPool 类上把 closeall() 替换为 no-op，
# 这样无论谁持有 pool 引用都无法关闭它，模块级的 getter 替换无法解决
# agentscope 在 import 时已捕获原始引用的问题。
from psycopg2.pool import ThreadedConnectionPool as _TCP
_TCP.closeall = lambda self: None
# ─────────────────────────────────────────────────────────────

# ============= 配置区 =============

MILVUS_HOST = "3.146.204.251"
MILVUS_PORT = "19530"
MILVUS_DB = "girlfriend_db"
MILVUS_COLLECTION = "vectors"

# Milvus 批次大小（每次 query_iterator 返回的记录数）
MILVUS_BATCH_SIZE = 2000

# mem0 回填：每次喂给 mem0 的对话轮数（每轮 = 1 user + 1 assistant）
MEM0_BATCH_ROUNDS = 8

# mem0 回填：两批之间的间隔秒数（避免 LLM API 限速）
MEM0_BATCH_INTERVAL = 0.3

# mem0 回填：并发处理的用户对数量（可被 --concurrency 覆盖）
MEM0_CONCURRENCY = 8

# mem0 回填进度文件（用于断点续跑）
MEM0_PROGRESS_FILE = ROOT / "scripts" / ".mem0_backfill_progress.json"

TARGET_FIELDS = ["user_id", "character_id", "message_id", "text", "timestamp"]


# ============= 迁移专用 mem0 工厂（relay-gemma4-remote）=============


def _create_migration_memory(user_id: str, expert_id: str):
    """创建用于历史回填的 mem0 实例，LLM 使用 Qwen Turbo (DashScope)。

    :param user_id: 用户 ID
    :param expert_id: 角色 ID
    :returns: Mem0LongTermMemory 实例
    """
    from relay_client import get_direct_api_cls
    from mem0.configs.base import MemoryConfig
    from mem0.embeddings.configs import EmbedderConfig
    from mem0.llms.configs import LlmConfig
    from mem0.vector_stores.configs import VectorStoreConfig
    from agentscope.memory import Mem0LongTermMemory
    from database import get_shared_pg_pool

    girlfriend_config = (
        _character_manager.get(expert_id)
        or _character_manager.get("101")
    )
    name = girlfriend_config["name"]

    embed_model = os.getenv(
        "EMBED_MODEL", "intfloat/multilingual-e5-large"
    )
    embed_dims = int(os.getenv("EMBED_DIMS", "1024"))

    qwen_api_key = os.getenv("DASHSCOPE_API_KEY", "")
    chat_model = get_direct_api_cls()(
        model_name="qwen-turbo",
        base_url=(
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        api_key=qwen_api_key,
        use_proxy=False,
        max_tokens=512,
    )
    logger.debug(f"创建迁移 mem0 实例: {user_id}/{name} (qwen-turbo)")

    mem0_cfg = MemoryConfig(
        llm=LlmConfig(provider="openai", config={}),
        embedder=EmbedderConfig(
            provider="fastembed",
            config={"model": embed_model},
        ),
    )
    vector_store_config = VectorStoreConfig(
        provider="pgvector",
        config={
            "connection_pool": get_shared_pg_pool(),
            "embedding_model_dims": embed_dims,
            "hnsw": True,
        },
    )
    return Mem0LongTermMemory(
        user_name=user_id,
        agent_name=name,
        run_name=f"{expert_id}_service",
        model=chat_model,
        mem0_config=mem0_cfg,
        vector_store_config=vector_store_config,
    )


def extract_timestamp_from_message_id(message_id: str) -> datetime | None:
    """从 message_id 末尾提取时间戳。

    格式：{user_id}_{character_id}_(ai|human)_{timestamp}
    末尾的 timestamp 通常为 Unix 毫秒整数字符串。
    """
    if not message_id:
        return None
    parts = message_id.rsplit("_", 1)
    if len(parts) == 2:
        try:
            return parse_timestamp(parts[-1])
        except Exception:
            pass
    return None


# ============= 工具函数 =============

def parse_timestamp(ts_str) -> datetime:
    """将 Milvus 时间戳解析为 timezone-aware datetime。

    支持格式：
    - datetime 对象（Milvus 有时直接返回，可能是 naive）
    - Unix 毫秒字符串：'1712345678901'
    - Unix 秒字符串：'1712345678'
    - ISO 字符串：'2025-04-01T12:00:00'
    """
    if isinstance(ts_str, datetime):
        if ts_str.tzinfo is None:
            return ts_str.replace(tzinfo=timezone.utc)
        return ts_str
    if not ts_str:
        return datetime.now(timezone.utc)
    try:
        ts = float(ts_str)
        if ts > 1e12:  # 毫秒
            return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        else:  # 秒
            return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, TypeError):
        pass
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        logger.warning(f"无法解析时间戳: {ts_str!r}，使用当前时间")
        return datetime.now(timezone.utc)


def get_role(message_id: str) -> str:
    """从 message_id 中判断消息角色。

    正式服格式：{user_id}_{character_id}_ai_{timestamp}
                 {user_id}_{character_id}_human_{timestamp}

    规则：message_id 中含 '_ai_' → 'assistant'，含 '_human_' → 'user'
    """
    mid = (message_id or "").lower()
    if "_human_" in mid:
        return "user"
    if "_ai_" in mid:
        return "assistant"
    # 兜底：以 _human 或 _ai 结尾（无末尾时间戳的情况）
    if mid.endswith("_human"):
        return "user"
    if mid.endswith("_ai"):
        return "assistant"
    logger.warning(f"无法判断角色，message_id={message_id!r}，默认 user")
    return "user"


# ============= Phase 1：迁移聊天历史 =============

async def migrate_chat_history(
    cutoff: datetime | None = None,
    start: datetime | None = None,
    target_users: list[str] | None = None,
):
    """从 Milvus 拉取历史对话并写入本地 PostgreSQL chat_history 表。"""
    from pymilvus import connections, db, Collection
    from database import get_postgres_pool

    logger.info("=== Phase 1: 迁移聊天历史 ===")
    logger.info(f"Milvus: {MILVUS_HOST}:{MILVUS_PORT} / {MILVUS_DB}.{MILVUS_COLLECTION}")
    if start:
        logger.info(f"起始时间: {start.isoformat()}")
    if cutoff:
        logger.info(f"截止时间: {cutoff.isoformat()}")
    if target_users:
        logger.info(f"目标用户: {target_users}")

    # 连接 Milvus
    logger.info("连接 Milvus...")
    connections.connect(alias="default", host=MILVUS_HOST, port=MILVUS_PORT)
    db.using_database(MILVUS_DB)
    col = Collection(MILVUS_COLLECTION)
    col.load()
    total_in_milvus = col.num_entities
    logger.info(f"Milvus 共 {total_in_milvus} 条记录")

    # 连接本地 PostgreSQL
    pool = await get_postgres_pool()
    if not pool:
        logger.error("PostgreSQL 连接失败，请检查 POSTGRES_URL")
        return

    inserted = 0
    skipped = 0
    total_fetched = 0

    # 构建过滤表达式
    expr = ""
    if target_users:
        user_list = ", ".join(f'"{u}"' for u in target_users)
        expr = f'user_id in [{user_list}]'

    iterator = col.query_iterator(
        batch_size=MILVUS_BATCH_SIZE,
        limit=-1,
        expr=expr,
        output_fields=TARGET_FIELDS,
    )

    async with pool.acquire() as conn:
        # 旧索引把整段 content 塞进 btree，长消息 >2704B 会崩
        await conn.execute(
            "DROP INDEX IF EXISTS idx_chat_user_expert_role_content"
        )
        # 用 md5 函数索引，行宽固定 32 字符，规避 btree 长度限制
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_user_expert_role_md5 "
            "ON chat_history(user_id, expert_id, role, md5(content))"
        )

        while True:
            results = iterator.next()
            if not results:
                break

            total_fetched += len(results)
            batch_rows = []

            for item in results:
                mid = item.get("message_id", "")
                # 优先从 message_id 末尾提取时间戳，fallback 到 timestamp 字段
                ts = (
                    extract_timestamp_from_message_id(mid)
                    or parse_timestamp(item.get("timestamp", ""))
                )

                # 时间范围过滤
                if start and ts < start:
                    continue
                if cutoff and ts > cutoff:
                    continue

                uid = item.get("user_id", "")
                cid = item.get("character_id", "")
                role = get_role(mid)
                content = (item.get("text") or "").strip()

                if not uid or not cid or not content:
                    continue

                batch_rows.append((uid, cid, role, content, ts))

            if not batch_rows:
                continue

            # 批量 upsert（忽略重复：同 user+expert+role+content 视为同一条）
            for uid, cid, role, content, ts in batch_rows:
                existing = await conn.fetchval(
                    "SELECT id FROM chat_history "
                    "WHERE user_id=$1 AND expert_id=$2 AND role=$3 "
                    "AND md5(content)=md5($4) LIMIT 1",
                    uid, cid, role, content,
                )
                if existing:
                    skipped += 1
                    continue

                # chat_history.timestamp 是 TIMESTAMP（无时区）
                # 转为 naive UTC 写入，避免 asyncpg 报 tz mismatch
                ts_naive = (
                    ts.astimezone(timezone.utc).replace(tzinfo=None)
                    if ts.tzinfo is not None else ts
                )
                await conn.execute(
                    "INSERT INTO chat_history "
                    "(user_id, expert_id, role, content, timestamp) "
                    "VALUES ($1, $2, $3, $4, $5)",
                    uid, cid, role, content, ts_naive,
                )
                inserted += 1

            logger.info(
                f"进度: Milvus已读 {total_fetched} | "
                f"写入 {inserted} | 跳过(重复) {skipped}"
            )

    iterator.close()
    connections.disconnect("default")

    logger.info(
        f"=== Phase 1 完成 === "
        f"Milvus读取 {total_fetched} 条，"
        f"写入 {inserted} 条，"
        f"跳过 {skipped} 条"
    )


# ============= Phase 2：mem0 事实回填 =============

async def backfill_mem0(
    target_users: list[str] | None = None,
    cutoff: datetime | None = None,
    start: datetime | None = None,
):
    """为迁移的历史对话回填 mem0 事实。

    对每个 (user_id, expert_id) 对，按时间顺序将对话分批喂给 mem0，
    触发 LLM 事实提取并存入 pgvector。
    """
    from database import get_postgres_pool, USE_POSTGRES

    if not USE_POSTGRES:
        logger.error("Phase 2 需要 PostgreSQL + pgvector，请设置 POSTGRES_URL")
        return

    logger.info("=== Phase 2: mem0 事实回填 ===")

    pool = await get_postgres_pool()
    if not pool:
        logger.error("PostgreSQL 连接失败")
        return


    # 读取断点进度
    progress: dict = {}
    if MEM0_PROGRESS_FILE.exists():
        try:
            progress = json.loads(MEM0_PROGRESS_FILE.read_text())
            logger.info(f"发现断点进度文件，已完成 {len(progress)} 个 user+expert 对")
        except Exception:
            pass

    # 查询所有需要处理的 (user_id, expert_id) 对
    async with pool.acquire() as conn:
        where_clauses = []
        params = []
        if target_users:
            where_clauses.append(
                f"user_id = ANY(${len(params)+1})"
            )
            params.append(target_users)
        if start:
            start_naive = (
                start.astimezone(timezone.utc).replace(tzinfo=None)
                if start.tzinfo is not None else start
            )
            where_clauses.append(f"timestamp >= ${len(params)+1}")
            params.append(start_naive)
        if cutoff:
            cutoff_naive = (
                cutoff.astimezone(timezone.utc).replace(tzinfo=None)
                if cutoff.tzinfo is not None else cutoff
            )
            where_clauses.append(f"timestamp <= ${len(params)+1}")
            params.append(cutoff_naive)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        pairs = await conn.fetch(
            f"SELECT DISTINCT user_id, expert_id FROM chat_history {where_sql}",
            *params,
        )

    logger.info(f"共 {len(pairs)} 个 user+expert 对需要处理")

    sem = asyncio.Semaphore(MEM0_CONCURRENCY)
    progress_lock = asyncio.Lock()

    async def _process_pair(pair):
        uid = pair["user_id"]
        cid = pair["expert_id"]
        key = f"{uid}:{cid}"

        if key in progress:
            return

        async with sem:
            logger.info(f"[开始] {key}")
            await _backfill_one_pair(uid, cid, pool, cutoff, start)
            gc.collect()
            async with progress_lock:
                progress[key] = datetime.now().isoformat()
                MEM0_PROGRESS_FILE.write_text(
                    json.dumps(progress, indent=2)
                )
            logger.info(f"[完成] {key}，进度已保存")

    await asyncio.gather(*[_process_pair(p) for p in pairs])

    logger.info("=== Phase 2 完成 ===")
    logger.info(f"进度文件: {MEM0_PROGRESS_FILE}")
    logger.info("如需重新回填某个用户，删除进度文件中对应条目后重新运行")


async def _backfill_one_pair(
    user_id: str,
    expert_id: str,
    pool,
    cutoff: datetime | None,
    start: datetime | None = None,
):
    """对单个 (user_id, expert_id) 对执行 mem0 回填。"""
    # 从 chat_history 按时间顺序取出该对的全部对话
    async with pool.acquire() as conn:
        where = "user_id=$1 AND expert_id=$2"
        params = [user_id, expert_id]
        if start:
            start_naive = (
                start.astimezone(timezone.utc).replace(tzinfo=None)
                if start.tzinfo is not None else start
            )
            where += f" AND timestamp >= ${len(params)+1}"
            params.append(start_naive)
        if cutoff:
            cutoff_naive = (
                cutoff.astimezone(timezone.utc).replace(tzinfo=None)
                if cutoff.tzinfo is not None else cutoff
            )
            where += f" AND timestamp <= ${len(params)+1}"
            params.append(cutoff_naive)

        rows = await conn.fetch(
            f"SELECT role, content, timestamp "
            f"FROM chat_history WHERE {where} "
            f"ORDER BY timestamp ASC",
            *params,
        )

    if not rows:
        logger.info(f"  {user_id}/{expert_id}: 无历史记录，跳过")
        return

    logger.info(f"  {user_id}/{expert_id}: {len(rows)} 条消息，开始分批提取")

    # 创建 mem0 实例（DashScope Qwen，避免 relay OOM）
    try:
        mem = _create_migration_memory(user_id, expert_id)
    except Exception as e:
        logger.error(f"  创建 mem0 实例失败: {e}")
        return

    # 只取用户消息传给 mem0，避免 AI 反问被误提取为用户事实
    # 每 MEM0_BATCH_ROUNDS 条用户消息提交一次
    current_batch = []

    for row in rows:
        if row["role"] != "user":
            continue
        current_batch.append({
            "role": "user",
            "content": row["content"],
        })
        if len(current_batch) >= MEM0_BATCH_ROUNDS:
            await _submit_batch(mem, current_batch, user_id, expert_id)
            current_batch = []
            await asyncio.sleep(MEM0_BATCH_INTERVAL)

    # 提交剩余消息
    if current_batch:
        await _submit_batch(mem, current_batch, user_id, expert_id)

    # 显式释放 mem0 实例，减轻 GC 压力
    del mem


async def _submit_batch(mem, messages: list, user_id: str, expert_id: str):
    """向 mem0 提交一批消息进行事实提取。

    直接调 mem._mem0_record() 而非 agentscope 的 record()，
    保持 role="user"，使 mem0 选用 USER_MEMORY_EXTRACTION_PROMPT
    提取用户信息，而非 AGENT_MEMORY_EXTRACTION_PROMPT 提取 AI 信息。
    """
    try:
        await mem._mem0_record(messages, infer=True)
        logger.debug(
            f"  {user_id}/{expert_id}: 提交 {len(messages)} 条消息到 mem0"
        )
    except Exception as e:
        logger.warning(f"  mem0 提交失败: {e}")


# ============= 入口 =============

async def main():
    parser = argparse.ArgumentParser(description="Milvus → 本地 PostgreSQL 迁移")
    parser.add_argument(
        "--phase",
        choices=["chat", "mem0", "all"],
        default="chat",
        help="执行阶段: chat=仅迁移聊天历史, mem0=仅回填事实, all=两者都执行",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="起始时间（ISO 格式或 Unix 时间戳），只迁移该时间之后的数据",
    )
    parser.add_argument(
        "--cutoff",
        type=str,
        default=None,
        help="截止时间（ISO 格式或 Unix 时间戳），只迁移该时间之前的数据",
    )
    parser.add_argument(
        "--users",
        nargs="*",
        default=None,
        help="只处理指定的 user_id 列表（可多个，空格分隔）",
    )
    parser.add_argument(
        "--users-file",
        type=str,
        default=None,
        help="从文件读取 user_id 列表（每行一个），与 --users 合并使用",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="并发处理的用户对数量，覆盖脚本默认值",
    )
    parser.add_argument(
        "--reset-progress",
        action="store_true",
        help="清除 mem0 回填的断点进度，从头开始",
    )
    parser.add_argument(
        "--progress-file",
        type=str,
        default=None,
        help="自定义断点进度文件路径（默认使用内置路径）",
    )
    args = parser.parse_args()

    start = None
    if args.start:
        start = parse_timestamp(args.start)
        logger.info(f"起始时间解析结果: {start.isoformat()}")

    cutoff = None
    if args.cutoff:
        cutoff = parse_timestamp(args.cutoff)
        logger.info(f"截止时间解析结果: {cutoff.isoformat()}")

    global MEM0_CONCURRENCY
    if args.concurrency is not None:
        MEM0_CONCURRENCY = args.concurrency
    logger.info(f"LLM 后端: relay-gemma4-remote, 并发: {MEM0_CONCURRENCY}")

    if args.progress_file:
        global MEM0_PROGRESS_FILE
        MEM0_PROGRESS_FILE = Path(args.progress_file)

    if args.reset_progress and MEM0_PROGRESS_FILE.exists():
        MEM0_PROGRESS_FILE.unlink()
        logger.info("已清除 mem0 回填进度文件")

    target_users = list(args.users) if args.users else []
    if args.users_file:
        users_path = Path(args.users_file)
        if users_path.exists():
            file_users = [
                u.strip() for u in users_path.read_text().splitlines()
                if u.strip()
            ]
            target_users = list(set(target_users + file_users))
            logger.info(f"从文件加载 {len(file_users)} 个用户，合计 {len(target_users)} 个")
        else:
            logger.warning(f"--users-file 指定的文件不存在: {users_path}")
    target_users = target_users or None

    if args.phase in ("chat", "all"):
        await migrate_chat_history(
            cutoff=cutoff, start=start, target_users=target_users
        )

    if args.phase in ("mem0", "all"):
        await backfill_mem0(
            cutoff=cutoff, start=start, target_users=target_users
        )


if __name__ == "__main__":
    asyncio.run(main())
