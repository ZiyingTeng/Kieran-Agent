# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Chatjoy 2.0** is a production AI agent chat application built on FastAPI + AgentScope. It provides multi-character AI chat (individual and group), user profiling, proactive engagement (heartbeat greetings), and push notifications. The codebase is a monorepo with a Python backend (root-level modules) and a React/TypeScript frontend (`frontend/`).

**Deployment:** Docker image `chatjoy:2.0` + Docker Compose (includes PostgreSQL + pgvector + Redis). See DEPLOY.md for full deployment instructions.

## Development Commands

### Backend

```bash
# Install with dev + extension dependencies
pip install -e ".[dev,ext]"

# Run dev server (single worker)
uvicorn app:app --reload --port 8001

# Run production (multi-worker Gunicorn, uses vllm-env conda env)
./start_production.sh            # start (default 4 workers)
./start_production.sh stop       # stop
./start_production.sh restart    # restart
./start_production.sh status     # check status

# Linting & formatting
pre-commit run --all-files
pre-commit run black --all-files
pre-commit run flake8 --all-files
```

### Frontend

```bash
cd frontend
npm install
npm run dev       # Vite dev server
npm run build     # tsc + vite build (output goes to web/dist/)
npm run lint      # ESLint
```

After frontend changes, `npm run build` is required — FastAPI serves static files from `web/dist/`.

### Testing

```bash
pytest                              # run all tests
pytest test_plugins.py              # plugin/tool tests (root level)
pytest path/to/test_file.py::test_name  # single test
coverage run -m pytest              # with coverage

# Long-term memory stress test (hits a running server)
python tests/test_ltm.py --base http://localhost:8001

# LTM noise control test (multilingual, configurable user/expert)
python tests/test_ltm_kr.py --base http://localhost:8001 --expert 148
python tests/test_ltm_kr.py --skip-chat --user <existing_user_id> --expert 148  # recall only
```

pytest is configured with `asyncio_mode = "auto"` — async test functions work without explicit markers. Test files live in `tests/` (`test_ltm.py`, `test_ltm_kr.py`, `test_websocket.html`) and in `push_service/test_push_service.py`. Load test scripts and reports live under `load_tests/`.

### Logs

- **App logs:** `logs/app.log` (Python logger output)
- **Gunicorn access:** `logs/access.log`
- **Gunicorn errors:** `logs/error.log`

When debugging multi-worker issues, check both `app.log` (event sequence) and `error.log` (worker crashes).

## Architecture

### Backend Layout (root-level Python modules)

- **`app.py`** — FastAPI application. Remaining HTTP/WebSocket endpoints (individual chat, admin, heartbeat, WebSocket, user profile). Mounts `routers/groups.py` via `include_router`. Main entry point (~2045 lines after ongoing decoupling; `get_or_create_session` lives here). `ChatRequest` includes optional relay auth fields (`appId`, `pkgName`, `publicKey`, `rkey`, `country`) and per-request model override fields (`modelName`, `apiPath`) — when present they override server-side env defaults and are injected into both `agent.model._relay_params` and `session["long_term_memory"]._relay_params` before `agent.reply()`. Client omitting `modelName`/`apiPath` falls back to server defaults transparently. **Error response:** on AI failure (❌-prefixed text, or thinking placeholder), the endpoint returns HTTP 500 + `{success:false, content:null, code:-100}` and skips DB write entirely. `_thinking_placeholder(char_name, user_msg)` returns a language-aware fallback ("在思考中..." for Chinese input, "is thinking..." otherwise). **WebSocket traffic:** in production all real chat goes through HTTP `/api/mobile/chat`; the `/ws/{user_id}/{expert_id}` endpoint only handles connection management and heartbeat pings — no actual chat volume. **`DeleteRequest`** model (`/api/roles/delete`): `userId` + `expertId` required, `mes: Optional[str] = None` — `mes=None` clears all history (Redis session + PostgreSQL); `mes` provided deletes that specific message. **Important:** the early return at line ~817 (`if not girlfriend_config`) has no logger call — requests failing here leave zero trace in app.log; add `logger.warning()` if debugging "未找到角色" issues from relay.
- **`proxy_config.py`** — Must be imported first. Reads and clears HTTP proxy env vars at import time so internal requests (vLLM, Redis, PostgreSQL) bypass Privoxy. Exports `SAVED_PROXY` for external clients.
- **`database.py`** — Two PostgreSQL connection pools: psycopg2 `ThreadedConnectionPool` (for mem0/pgvector) via `get_shared_pg_pool()`, and asyncpg `Pool` (for chat history + heartbeat persistence) via `get_postgres_pool()`. Also exports `save_chat_history_to_db`, `load_chat_history_from_db`, `load_recent_chat_history`, `delete_chat_message_from_db`.
- **`model_config.py`** — `MODEL_CONFIGS` table, `CHAT_MODEL`, `GROUP_CHAT_MODEL`, `current_model_config`. Single source of truth for all model definitions.
- **`llm_service.py`** — LLM service layer. Contains `AsyncLongTermMemoryWrapper` (with LTM write filtering and retrieval dedup/reranking — see LTM Noise Control below), `create_memory_for_user_and_girlfriend`, `create_agent` (ReActAgent factory registered with SessionManager), `get_model_config`, `call_llm_with_config` (relay-gemma4-remote router). Requires `llm_service.configure(character_manager, DATABASE_DIR)` call in `startup_event` before use. **`call_llm_with_config` relay-branch message conversion (lines ~822-857)**: when `raw_messages` is passed, the OpenAI-format list is collapsed to relay v3's three-field format `(system, history_data, input_txt)`. Two non-obvious behaviors: (1) **多个 `role=system` 消息按出现顺序用 `\n\n` 拼接**进 `system` 字段（之前的实现是后一条覆盖前一条，会丢失角色人设——心跳问候同时塞 persona + task 两条 system 就踩到过）；(2) **若末尾消息是 `system` 且没有可用的 user 内容**（典型场景：心跳问候把 task prompt 作为末尾 system 追加），那条 system 会被提升为 `input_txt` 并从 `system` 段剔除避免重复，否则中继会因 `input_txt=""` 返回 `[427] Model input cannot be empty`。
- **`group_chat_service.py`** — Group chat service layer. Contains group long-term memory management (`get_or_create_group_memory`, `retrieve_group_memories`, `record_group_memories`), `format_group_context`, `update_conversation_summary`, and `generate_agent_response_in_group` (multi-model router for group replies, including SKIP logic). `generate_agent_response_in_group` accepts an optional `group_background: str` parameter — when set, a `[Scene Background]` block is injected into the system prompt after the character's personality and before the reply guidelines, so all characters in the group share the same scene context. Requires `group_chat_service.configure(character_manager, group_manager, DATABASE_DIR)` call in `startup_event` before use.
- **`session_manager.py`** — Redis-backed stateless session management. TTL-LRU cache for in-process Agent objects (default `cache_ttl=3600s`), Redis for session metadata + RedisMemory (default `session_ttl=7200s`). Enables horizontal scaling across Gunicorn workers. **Cache-miss rehydration**: `get_or_create_session` after building a fresh `RedisMemory` checks `memory.size() == 0`; if empty (Redis short-term keys expired, e.g. user idle >2h), it calls the registered `_load_history_fn` (`load_recent_chat_history`, registered via `set_chat_history_loader()` from `app.py`) to pull the last N rows (N=`MAX_PRIVATE_CHAT_HISTORY`=20) from PostgreSQL `chat_history` and `memory.add()` them as `Msg` objects. Logs `♻️ 短期记忆回灌`. This prevents the "user comes back next day, AI starts fresh" failure mode that occurred when Redis short-term keys expired without any rehydration path. Cross-session narrative continuity is additionally covered by the user-profile injection in `app.py`'s chat handler (see User Profile section).
- **`group_manager.py`** — Multi-agent group chat orchestration. File-based persistence (`data/groups/groups.json`) with cross-worker sync via mtime detection (see Multi-Worker Pitfalls below). `Group` dataclass includes `background: str = ""` — an optional scene context string stored in the JSON and passed to `generate_agent_response_in_group` at chat time.
- **`user_profile_manager_v2.py`** — Structured user profiling with 5 semantic tables (`user_traits`, `relationship`, `events`, `preferences`, `agreements`). Uses Mem0 facts as input + relay-gemma4-remote for qualitative synthesis (`ORGANIZE_PROMPT`). Profiles stored as JSON in `user_profiles/{user_id}_{expert_id}.json`. **Currently enabled** in the chat path (see "User Profile (5-table synthesised memory)" below). Key prompt/format details: (1) `_fetch_mem0_facts` extracts `created_at`/`updated_at` (Mem0 stores in **UTC ISO 8601**) and prefixes each fact line as `[YYYY-MM-DD] text` so the synthesis LLM can produce time-tagged events. (2) `ORGANIZE_PROMPT` injects `Today: {today} (UTC)` plus a timezone note so the LLM uses fuzzy phrasing ("that night" / "around that time") in event descriptions to avoid contradicting users' local-time framing. (3) Anti-pollution rule: prompt explicitly tells the LLM that some raw mem0 facts may describe the AI character's behaviour (legacy Milvus migration polluted ~135k+49k rows), and to drop such facts entirely rather than synthesise them into the profile.
- **`heartbeat_scheduler.py`** / **`heartbeat_greeting_generator.py`** — Proactive engagement system. APScheduler with Redis leader election, probability-based greeting, story-driven LLM prompts. **Message layout** (`generate_greeting` 内构造的 `raw_messages`)：`[system(persona+profile), ...history_turns..., system(task prompt)]`——任务指令作为末尾 system 消息追加，依赖 `call_llm_with_config` relay-branch 把它提升为 `input_txt`（见 `llm_service.py` 条目）。`_GREETING_TASK_PROMPT` 头部带 `[System Note — instruction for the AI, not a user message]` OOC 标记，并明确要求模型不要回显该标记，避免模型把指令文本当作真实用户输入复述出来。
- **`character_config_manager.py`** — Loads character cards from two directories: `characters/*.json` (official, read-only) and `users_characters/*.json` (user-created custom characters, IDs ≥ `USER_CHAR_ID_MIN=100000`). All keys stored as `str(expert_id)` — critical: JSON files may have integer `expertId` values, always convert to string. Provides `create_custom`, `update_custom`, `delete_custom` — none enforce owner_id, so any authenticated call can manage any custom character. **On 251:** character dirs are bind-mounted from host: `/data/Characters/characters/` → `/app/characters/`, `/data/Characters/users_characters/` → `/app/users_characters/`. Always inspect host paths, not container paths. Currently ~447 official + ~5114 user characters. **Common pitfall:** if `get(expert_id)` returns None for a character whose file exists, check (1) whether the file is in `users_characters/` (old code only loaded `characters/`), (2) whether the key is stored as int instead of str (old bug — fixed in current code).
- **`gunicorn_config.py`** — Multi-worker production config (4 workers, UvicornWorker, 120s timeout).
- **`message_regeneration_manager.py`** — Handles "regenerate" requests by soft-deleting (marking as superseded) the prior AI message across all 3 memory tiers.
- **`relay_client.py`** — Relay API client (`RelayClient`) for RSA-authenticated async-poll relay, and `get_direct_api_cls()` for standard OpenAI-compatible endpoints (with configurable proxy). Used by `create_agent()` in `llm_service.py`. Contains `_convert_history()` which deduplicates `history_data` by (1) removing empty assistant entries where non-empty ones follow, then (2) removing consecutive identical entries — order matters to avoid duplicate user messages after gap removal. Also contains `_format_ltm_block()` which rewrites the AgentScope LTM injection into a more directive English instruction before it is appended to the system prompt. **Relay auth scheme (v2):** UUID removed; sign is now `MD5(pkgName + timestamp)` only; decrypt payload includes `check:"1"`, optional `imageUrl`, and `platFormId:"googlellm"` when `api_path==/v5/mmchatgpt`; form params include `rkey` and `country`. Six params (`appId`, `pkgName`, `publicKey`, `rkey`, `model_name`, `api_path`) are dynamic per-call — `RelayApiChatModel` reads them from `self._relay_params` (set by `app.py` before each `agent.reply()` call). `model_name` and `api_path` in `_relay_params` override the instance-level defaults; empty string falls back to instance defaults. **Timestamp fix (251 production):** `cur_time = int(datetime.now().timestamp() * 1000)` is computed once in `call()` and passed to `_build_decrypt_payload(cur_time=cur_time)` — previously two separate `datetime.now()` calls caused sign/appTime mismatch → 验签失败. **Content violation retry:** relay error codes are embedded in error strings as `[code]` (e.g. `❌ 中继结果获取失败[428]: ...`) so the retry path can parse them. Retry is triggered when the error code is in `{428, 300, 71007, 54100}` — the retry uses `gemini-2.5-flash` via `/v5/mmchatgpt` with a character-voice refusal prompt and four `BLOCK_NONE` safety thresholds. Code 428+`PROHIBITED_CONTENT` after retry means the relay's own filter blocked even the retry — no further attempt is made.
- **`tools_to_toolkit.py`** — Defines and registers the tool set available to agents (time, weather, etc.).

### Routers (`routers/`)

FastAPI `APIRouter` modules extracted from `app.py`. Each router is mounted via `app.include_router()` and requires a `configure()` call in `startup_event` to inject runtime dependencies.

- **`routers/groups.py`** — All `/groups/*` endpoints (12 routes): group CRUD, member management, group chat (normal + SSE streaming). Also defines the 6 Pydantic models specific to group chat (`CreateGroupRequest`, `GroupChatRequest`, `GroupChatResponse`, etc.). `CreateGroupRequest` includes `background: Optional[str]` — when provided it is stored on the `Group` and injected as `[Scene Background]` into every character's system prompt at chat time. Both `group_chat` and `group_chat_stream` apply an 8-second `asyncio.wait_for` timeout to `retrieve_group_memories` — if fastembed is cold (model not cached), LTM is skipped gracefully. Depends on `group_chat_service` for business logic.

### Push Service (`push_service/`)

Self-contained push notification subsystem with multi-provider support (WebSocket, FCM, APNs, Web Push), offline message queue, device token management, and Redis-backed connection registry. Currently inactive — providers not configured.

### Frontend (`frontend/`)

React 19 + TypeScript + Vite + Tailwind CSS. State managed with Zustand. Built output goes to `web/dist/` for static serving by FastAPI.

### Docs (`cookbook/`)

Sphinx-based documentation site (English under `cookbook/en/`, Chinese under `cookbook/zh/`), built via `cookbook/build.sh`. Not served by the runtime — published separately.

### Memory Hierarchy

1. **Short-term** (RedisMemory) — current session chat messages, bound to `(user_id, expert_id, session_id)`. Trimmed to last **20 messages per request** (`MAX_PRIVATE_CHAT_HISTORY`, line 184 in app.py). Note: `SessionManager.trim_memory` is **destructive** (calls `memory.delete([...])`, not just a view filter) — messages beyond the window are permanently removed from Redis. Short-term window only carries the current-conversation continuity; cross-session narrative recall (events from yesterday, relationship state) is delegated to the user profile injection (see tier 4), not to a longer short-term window.
2. **Medium-term** — there is no separate medium-term tier; the RedisMemory above survives worker restarts (Redis-backed) and is rehydrated from PostgreSQL on cache-miss (see `session_manager.py`).
3. **Long-term** (Mem0 + PostgreSQL pgvector) — persistent user knowledge. Protected by LTM Noise Control (see below).
4. **Cross-session synthesised profile** (`user_profiles/*.json`) — 5-table semantic portrait synthesised every 5 rounds from Mem0 facts; injected into the system prompt per-request. Covers the "narrative continuity across sessions" gap that LTM facts alone cannot fill (LTM stores identity facts like "user 喜欢吃辣"; profile's `events` and `relationship` tables carry storyline beats like "5/10 海边散步，用户提到见父母"). See "User Profile" section below.

### LTM Noise Control

`AsyncLongTermMemoryWrapper` in `llm_service.py` implements a two-layer noise control pipeline for long-term memory:

**Layer 1 — Write-time LLM filter** (`_classify_personal_info`):
- Before each mem0 write, the latest user message is sent to relay-gemma4-remote for binary classification: does this message contain a concrete, lasting personal fact (name, age, occupation, family, pets, food preferences, hobbies, life goals)?
- Routes through `RelayClient` when `use_relay=True` (prod), or falls back to direct OpenAI-compatible API when `use_relay=False` (dev). Calls use `stream=False, max_tokens=8` for speed.
- NO → write is blocked entirely. YES → only the last user+assistant message pair is passed to mem0 (not the full short-term memory history, to prevent noise from earlier turns being re-extracted).
- The user message is first cleaned by `_extract_raw_user_text()` which strips any `<long_term_memory>` blocks injected by AgentScope, and messages with `name="long_term_memory"` are skipped when selecting the user message to classify.
- On LLM call failure, the write is allowed (fail-open). Background task runs after response sent to user; does not block chat latency.
- **Relay params:** `AsyncLongTermMemoryWrapper` has a `_relay_params: dict` attribute. `app.py` sets it to the same per-request credentials (`appId`, `pkgName`, `publicKey`, `rkey`, `country`) as `agent.model._relay_params` before each reply. This ensures the filter uses the caller's relay quota bucket, not the fixed env-default `appId` (`YZ053`) which caused ~0.25% rate-limited 410 failures when all background filter tasks shared one bucket.

**Layer 2 — Retrieval-time dedup & reranking** (`retrieve`):
- Fetches top-10 from mem0's vector search (pgvector cosine distance).
- **Character-level dedup** (threshold 0.75): normalized strings with ≥75% character overlap are merged.
- **Cross-language entity dedup**: extracts entity keywords (names, Korean/Chinese words, numbers, English words 3+ chars) from each fact; if two facts share ≥60% of their entity set, the later one is dropped.
- **Question demotion**: entries ending with `?/？` or matching common question patterns (Korean/Chinese/English) are moved to the end of the result list, so factual statements occupy the top positions.

**Important**: `app.py` must NOT call `long_term_memory.record()` directly — AgentScope's `ReActAgent.reply()` already triggers record via the wrapper. A duplicate call in `app.py` was removed because it bypassed the filter and caused noise+duplication.

### User Profile (5-table synthesised memory)

Per-request flow in `app.py` /api/mobile/chat handler:
1. **Inject** (before `agent.reply()`): `profile_mgr.load_profile_sync()` reads the JSON profile (cheap disk read); `agent._sys_prompt` is rebuilt as `agent._base_sys_prompt + [About the User] profile_text`. **Must write `_sys_prompt` (storage attribute), not `sys_prompt` (which is a read-only `@property` in `ReActAgent` that also appends an `agent_skill_prompt` suffix)**. `_base_sys_prompt` is captured at agent creation in `create_agent()` so re-injection on every request doesn't compound; for agents already in LRU cache from before this code shipped, the chat handler falls back to reading `agent._sys_prompt` (clean persona, since old code never injected) and saves it as `_base_sys_prompt`.
2. **Auto-trigger** (after successful reply + DB save): `profile_mgr.increment_round()` bumps the per-(user, expert) counter; if `rounds % 5 == 0`, an `asyncio.create_task(_profile_summarize_async(...))` fires-and-forgets. The async task uses the caller's `agent.model._relay_params` so the synthesis LLM call goes through the user's relay quota (avoids env-default `appId` rate limits).
3. **Persistence**: synthesis writes to `user_profiles/{user_id}_{expert_id}.json`. Round counter persisted at `user_profiles/{user_id}_{expert_id}.rounds.json`.

Why not inject at `create_agent()` time (the original design that was disabled): agents stay in LRU cache up to 1 hour, so a profile updated at round 5 would not be picked up by the same agent at round 6-30. Per-request injection fixes this with a single disk read (~milliseconds) per chat.

### Data Flow (Chat Request)

User message -> HTTP `/api/mobile/chat` -> Session retrieval (Redis + LRU cache, **rehydrate from PG if RedisMemory empty**) -> `trim_memory` (cap RedisMemory at 40) -> **Profile injection: rebuild `agent._sys_prompt` = base persona + latest user profile** -> `agent.reply()` (which internally retrieves LTM, calls model, writes to RedisMemory + triggers async LTM record via `AsyncLongTermMemoryWrapper`) -> Save chat_history to PG -> **Bump round counter; if rounds %5==0 fire async profile synthesis** -> Response to user

### LLM Routing

Model is **relay-gemma4-remote** (external network compatible, no domestic API needed). Both `CHAT_MODEL` and `GROUP_CHAT_MODEL` default to relay-gemma4-remote. Two call paths:

- **Individual chat**: AgentScope `ReActAgent` with DirectApiChatModel wrapper (relay-gemma4-remote)
- **Group chat**: `generate_agent_response_in_group()` in `group_chat_service.py` delegates to `call_llm_with_config()` in `llm_service.py` (relay-gemma4-remote via direct_api).

Only relay-gemma4-remote is supported. All LLM calls (including mem0 fact extraction and LTM filtering) use relay-gemma4-remote.

**Proxy handling:** `proxy_config.py` is imported first in `app.py` — it reads and clears all HTTP proxy env vars, saving the value as `SAVED_PROXY`. This prevents Privoxy from intercepting internal requests (vLLM at `192.168.1.18`, Redis, PostgreSQL). `relay_client.py` imports `SAVED_PROXY` from `proxy_config` (not from `app`) to route relay API calls through the proxy. All other HTTP clients should use `proxy=None` explicitly.

**Important note on filter routing:** The LTM write-time filter (`_classify_personal_info` in `llm_service.py`) routes through `RelayClient` when `use_relay=True` (production), avoiding the hardcoded internal vLLM address. This ensures filter calls complete in ~2–3s instead of timing out on unreachable URLs.

## Multi-Worker Pitfalls

Production runs **2 Gunicorn workers** (configured via `GUNICORN_WORKERS=2` in `/opt/docker-compose_yml/ai-character-project_overseas/.env` on the 251 server; `.env` has been updated to 3, takes effect on next container restart). Each has its own Python process with separate in-memory state.

**Individual chat sessions** — handled correctly via Redis. No issues.

**Group chat state** — uses file-based persistence (`groups.json`). `GroupManager` has `_reload_if_changed()` that checks file mtime before every read. If you add new read methods to GroupManager, you **must** call `_reload_if_changed()` first, otherwise other workers' writes will be invisible.

**Heartbeat scheduler** — only one worker should run it. Redis leader election via `SETNX` on key `heartbeat_leader` with 1-hour TTL + 30-minute renewal. Stale leader keys from dead PIDs are cleaned at startup via `psutil.pid_exists()`.

**Heartbeat persistence** — uses PostgreSQL UPSERT (`INSERT ... ON CONFLICT DO UPDATE`) to prevent duplicates. DB is always written before updating in-memory state.

## Performance & Concurrency

**Latency (measured on AWS production)**:
- Single user, fresh session: ~3.3s (relay task queue + polling)
- Single user, cached agent: ~1.5–2s
- 5 concurrent users: 4.2–5.6s (all successful)

Bottleneck is relay server task queue; local code paths (session lookup, Redis, in-memory LRU) are negligible.

**Concurrency limits**:
- Per-worker: `MAX_CONCURRENT_REQUESTS = 100` (semaphore on `/api/mobile/chat`)
- Gunicorn workers: 2 currently in production (`.env` updated to 3, takes effect on next restart)
- Effective capacity: ~200 concurrent requests across all workers (will be ~300 after restart)
- True ceiling: relay server throughput (external dependency)

**Background tasks** (do not block response):
- LTM filter: `_classify_personal_info` runs async after response sent (~2–3s via relay, or fails open)
- Mem0 extraction: fact storage in pgvector (~2–3s)
- Chat history persistence: DB write (~100ms)

These backgrounds queue but do not delay response to user.

## Milvus → PostgreSQL Historical Data Migration

One-time migration of pre-existing chat history and mem0 facts from Milvus (legacy) into local PostgreSQL. Script: `scripts/migrate_milvus_to_local.py`.

**Phase 1** (`--phase chat`): Reads Milvus `girlfriend_db.vectors` collection and inserts rows into `chat_history` table. Idempotent — deduplicates by `(user_id, expert_id, role, md5(content))`.

**Phase 2** (`--phase mem0`): For each `(user_id, expert_id)` pair in `chat_history`, feeds user messages in batches to mem0 for fact extraction. Checkpoint file at `scripts/.mem0_backfill_progress.json` — supports resume after interruption. Use `--reset-progress` to restart from scratch.

**psycopg2 pool GC bug:** mem0's `Mem0LongTermMemory` destructor calls `pool.closeall()` on the shared psycopg2 `ThreadedConnectionPool`, permanently destroying it for subsequent instances. The proxy-object approach (`_NoClosePoolProxy`) does NOT work because agentscope captures the `get_shared_pg_pool` function reference at import time. **Fix:** patch the class method directly before any mem0 instances are created:
```python
from psycopg2.pool import ThreadedConnectionPool
ThreadedConnectionPool.closeall = lambda self: None
```

**Running Phase 2 safely** (SSH-disconnect-proof):
```bash
# On the production server, start in a screen session
screen -dmS migrate bash -c "
  docker exec ai-character-project_overseas-app-1 \
    python /app/scripts/migrate_milvus_to_local.py \
    --phase mem0 --cutoff '2026-04-23T00:00:00' \
    2>&1 | tee /tmp/migrate_phase2.log
"
# Monitor progress (connect to pgvector container)
docker exec ai-character-project_overseas-pgvector-1 \
  psql -U postgres -d postgres -c 'SELECT COUNT(*) FROM mem0;'
```

**Docker networking:** Milvus and the app container are in separate Compose stacks (separate bridge networks). Milvus port 19530 is bound to `0.0.0.0` on the host, so from the app container it is reachable via the host's public IP (`3.146.204.251:19530`).

## Code Standards

- **Python line length:** 79 chars (Black configured)
- **Formatting:** Black, flake8 (ignores: F401, F403, W503, E731), mypy, pylint
- **Lazy loading required:** Optional dependencies must be imported at point of use, not at module top. For base class imports, use factory pattern:
  ```python
  def get_xxx_cls() -> "MyClass":
      from xxx import BaseClass
      class MyClass(BaseClass): ...
      return MyClass
  ```
- **Docstrings:** RST format, English only
- **PR titles:** Conventional Commits — `feat(scope): description`, `fix(scope): description`, etc.
- **Pre-commit is mandatory.** Modify code to pass checks rather than skipping them.

## Key Dependencies

- **AgentScope** (`agentscope>=1.0.14,<1.1.0`) — multi-agent framework providing ReActAgent, memory, model wrappers. ≥1.0.14 required for `MemoryConfig` in `Mem0LongTermMemory`; avoid 1.1.0+ for stability.
- **Mem0** (`mem0ai>=0.1.117,<2.0.0`) — long-term memory and fact extraction. Version 2.0.0+ broke `search()` API (removed `user_id`/`run_id` top-level params); stay <2.0.0.
- **fastembed** (`fastembed>=0.4.0`) — local embedding model for pgvector. Downloads `intfloat/multilingual-e5-large` (~600MB) on first run; cache at `fastembed_cache` volume.
- **Model support:** relay-gemma4-remote (external network, no domestic API key needed)
- **Redis** — session state, memory, heartbeat leader election
- **PostgreSQL** — chat history, heartbeat state, user profiles; pgvector for embeddings

## Environment

Requires a `.env` file at root with: `CHAT_MODEL=relay-gemma4-remote`, `GROUP_CHAT_MODEL=relay-gemma4-remote`, API key (`RELAY_GEMMA4_API_KEY`, optional — no auth required), Redis config, PostgreSQL connection string, `HTTP_PROXY` (if internal network requires proxy to reach external relay server). The conda environment `vllm-env` (Python 3.10) is used for dev; production uses Docker image `chatjoy:2.0`.

## Docker Deployment (Production)

```bash
# Build the image (at project root)
docker build -t chatjoy:2.0 .

# Create .env file with required settings (see DEPLOY.md § 1.3)
echo "CHAT_MODEL=relay-gemma4-remote" > .env
echo "GROUP_CHAT_MODEL=relay-gemma4-remote" >> .env
echo "POSTGRES_PASSWORD=your_strong_password" >> .env
# ... add other env vars

# Start with Docker Compose
docker compose up -d

# Verify health
curl http://localhost:8001/health
docker compose ps  # all services should be healthy
```

See **DEPLOY.md** for comprehensive deployment guide (multi-worker config, Nginx reverse proxy, bare-metal fallback, data migration).

## Production Servers

### 251 — Production (AWS)

- **IP:** `3.146.204.251` | **SSH:** `ubuntu@3.146.204.251` (sudo su - for root)
- **Stack:** Docker Compose at `/opt/docker-compose_yml/ai-character-project_overseas/`
- **App container:** `ai-character-project_overseas-app-1` | **Port:** 8001
- **Relay:** Production relay (full auth scheme with timestamp fix applied to `relay_client.py`)
- **Logs:** `docker logs ai-character-project_overseas-app-1`
- **Character dirs (host):** `/data/Characters/characters/` and `/data/Characters/users_characters/`
- **Current image:** `chatjoy:2.0` (rebuild after every batch of hot-patches)

### 162 — Test Server

- **IP:** `3.149.187.162` | **SSH:** `root@3.149.187.162`
- **Stack:** Direct uvicorn (no Docker) at `/data/test/Chatjoy2/`, port 8002
- **Relay:** Test relay — different connection approach from 251; `relay_client.py` intentionally kept at older version (no `cur_time` fix needed for test relay)
- **Restart (本地登录后):** `pkill -f 'uvicorn app:app' && cd /data/test/Chatjoy2 && nohup venv/bin/python3 venv/bin/uvicorn app:app --host 0.0.0.0 --port 8002 --workers 1 >> logs/app.log 2>&1 &`
- **Restart (通过 ssh 单条命令远程执行):** 必须加 `setsid` + `</dev/null` + `disown`，否则新进程会被 ssh 会话退出连带杀掉（光 `nohup &` 不够）：
  ```
  ssh root@3.149.187.162 "cd /data/test/Chatjoy2 && setsid nohup \
    venv/bin/python3 venv/bin/uvicorn app:app --host 0.0.0.0 --port 8002 \
    --workers 1 </dev/null >>logs/app.log 2>&1 & disown; sleep 1; echo started"
  ```
  验证一定要看 `ss -tlnp | grep 8002` 和实际打一个端点，不要只 `ps`。
- **Code sync:** All files except `relay_client.py` should match 251

## Hot-Patching (251 Docker Container)

**⚠️ DO NOT use `docker cp -` / `docker cp /dev/stdin` to pipe file content into the container.** `docker cp` treats `-` / stdin as a tar stream, so raw source bytes get interpreted as tar headers and a garbage file lands at the destination. Past incident: container then entered crash-restart loop because Python couldn't import the corrupted module, and recovery required manually fixing the file inside the container. **Always scp the real file to the server first, then `docker cp /path/to/real/file container:/app/file`.**

When you need to fix a bug without recreating the container:

```bash
# 1. Copy file to server then into container
sshpass -p '...' scp file.py ubuntu@3.146.204.251:/tmp/
ssh ubuntu@3.146.204.251 "sudo docker cp /tmp/file.py ai-character-project_overseas-app-1:/app/file.py"

# 2. Delete stale .pyc cache (IMPORTANT — Python may load old bytecode otherwise)
ssh ubuntu@3.146.204.251 "sudo docker exec ai-character-project_overseas-app-1 \
  rm -f /app/__pycache__/file.cpython-310.pyc"

# 3. Send SIGHUP to Gunicorn master for graceful worker reload
ssh ubuntu@3.146.204.251 "sudo docker exec ai-character-project_overseas-app-1 \
  python3 -c 'import os, signal; os.kill(1, signal.SIGHUP)'"
```

**After hot-patching, rebuild the image** so fixes survive container recreation:
```bash
# Update build context and rebuild
sudo cp /tmp/file.py /opt/docker-compose_yml/ai-character-project_overseas/
cd /opt/docker-compose_yml/ai-character-project_overseas
sudo docker build -t chatjoy:2.0 .
```

**Note:** Container restart (crash recovery) preserves hot-patched files in the writable layer. Container *recreation* (`docker-compose up --force-recreate`) does NOT — it uses the image. Always rebuild image after patching.
