"""Group chat router module.

Contains all /groups/* endpoints: group CRUD, member management,
chat (normal + SSE streaming), and history management.

Note: configure() must be called to inject character_manager and group_manager
before use.
"""

import asyncio
import json
import logging
import random
from typing import AsyncGenerator, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from database import save_group_message_to_db
from group_chat_service import (
    cleanup_group_memory,
    generate_agent_response_in_group,
    record_group_memories,
    retrieve_group_memories,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/groups", tags=["groups"])

# ============= Module-level config (injected by app.py startup_event) =============

_character_manager = None
_group_manager = None


def configure(character_manager, group_manager) -> None:
    """Inject runtime dependencies.

    :param character_manager: CharacterConfigManager instance
    :param group_manager: GroupManager instance
    """
    global _character_manager, _group_manager
    _character_manager = character_manager
    _group_manager = group_manager


def _cm():
    if _character_manager is None:
        raise RuntimeError(
            "routers.groups is not configured: call configure() in startup_event"
        )
    return _character_manager


def _gm():
    if _group_manager is None:
        raise RuntimeError(
            "routers.groups is not configured: call configure() in startup_event"
        )
    return _group_manager


# ============= Pydantic models =============

class CreateGroupRequest(BaseModel):
    """Create group request."""
    name: str = Field(..., description="Group name")
    members: List[str] = Field(..., description="List of member character IDs")
    userId: str = Field(alias="user_id", serialization_alias="userId", description="Creator user ID")
    turn_strategy: str = Field(default="reaction", description="Turn strategy: round_robin, random, reaction")
    auto_response: bool = Field(default=True, description="Whether AI should auto-respond")
    background: Optional[str] = Field(default=None, description="Optional scene background for the group chat")

    model_config = {"populate_by_name": True}


class GroupChatRequest(BaseModel):
    """Group chat message request."""
    message: str = Field(..., description="Message content")
    userId: str = Field(alias="user_id", serialization_alias="userId", description="User ID")
    mentioned_girlfriends: Optional[List[str]] = Field(default_factory=list, description="List of @-mentioned character IDs")

    model_config = {"populate_by_name": True}


class GroupChatResponse(BaseModel):
    """Group chat message response."""
    success: bool
    group_id: str
    user_message: Optional[dict] = None
    ai_responses: List[dict] = Field(default_factory=list)
    error: Optional[str] = None


class AddGroupMemberRequest(BaseModel):
    """Add group member request."""
    expertId: str = Field(..., description="Character ID")


class UpdateGroupNameRequest(BaseModel):
    """Update group name request."""
    name: str = Field(..., description="New group name")


class UpdateGroupMessageRequest(BaseModel):
    """Update group chat message request."""
    group_id: str
    user_id: str
    expert_id: str
    user_message: str
    new_reply: str


# ============= Group CRUD =============

@router.post("")
async def create_group(request: CreateGroupRequest):
    """Create a group."""
    try:
        for member_id in request.members:
            if not _cm().get(member_id):
                raise HTTPException(
                    status_code=400,
                    detail=f"Character ID {member_id} does not exist"
                )

        group_id = _gm().create_group(
            group_name=request.name,
            members=request.members,
            owner_id=request.userId,
            turn_strategy=request.turn_strategy,
            auto_response=request.auto_response,
            background=request.background or "",
        )

        group = _gm().get_group(group_id)
        return {
            "success": True,
            "group_id": group_id,
            "group": group.to_dict() if group else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create group: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create group: {str(e)}")


@router.get("")
async def list_groups(user_id: str = Query(default="default_user")):
    """Get all groups for a user."""
    try:
        groups = _gm().get_user_groups(user_id)
        return {"userId": user_id, "groups": [g.to_dict() for g in groups]}
    except Exception as e:
        logger.error(f"Failed to list groups: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list groups: {str(e)}")


@router.get("/{group_id}")
async def get_group(group_id: str):
    """Get group details."""
    try:
        group = _gm().get_group(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        return {
            "group": group.to_dict(),
            "message_count": len(_gm().get_group_messages(group_id)),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get group: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get group: {str(e)}")


@router.put("/{group_id}/name")
async def update_group_name(group_id: str, request: UpdateGroupNameRequest):
    """Update group name."""
    try:
        success = _gm().update_name(group_id, request.name)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to update group name")
        group = _gm().get_group(group_id)
        return {"success": True, "group": group.to_dict() if group else None}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update group name: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update group name: {str(e)}")


@router.delete("/{group_id}")
async def delete_group(group_id: str, user_id: str = "default_user"):
    """Delete a group."""
    try:
        success = _gm().delete_group(group_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Group not found or permission denied")
        cleanup_group_memory(group_id)
        return {"success": True, "message": "Group deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete group: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete group: {str(e)}")


@router.post("/{group_id}/members")
async def add_group_member(group_id: str, request: AddGroupMemberRequest):
    """Add a member to a group."""
    try:
        if not _cm().get(request.expertId):
            raise HTTPException(status_code=400, detail="Character ID does not exist")
        success = _gm().add_member(group_id, request.expertId)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to add member (already exists or group is full)")
        group = _gm().get_group(group_id)
        return {"success": True, "group": group.to_dict() if group else None}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add group member: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add group member: {str(e)}")


@router.delete("/{group_id}/members/{expertId}")
async def remove_group_member(group_id: str, expertId: str):
    """Remove a member from a group."""
    try:
        success = _gm().remove_member(group_id, expertId)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to remove member")
        group = _gm().get_group(group_id)
        return {"success": True, "group": group.to_dict() if group else None}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove group member: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to remove group member: {str(e)}")


@router.get("/{group_id}/history")
async def get_group_history(group_id: str, limit: int = 50):
    """Get group chat history."""
    try:
        group = _gm().get_group(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        messages = _gm().get_group_messages(group_id, limit)
        return {
            "group_id": group_id,
            "messages": messages,
            "total_count": len(messages),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get group history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get group history: {str(e)}")


# ============= Group chat (normal) =============

@router.post("/{group_id}/chat", response_model=GroupChatResponse)
async def group_chat(group_id: str, request: GroupChatRequest):
    """Group chat: send a message and get AI responses (concurrent generation)."""
    try:
        logger.info(
            f"Group chat request: group_id={group_id}, userId={request.userId}, "
            f"message={request.message[:50]}, mentioned={request.mentioned_girlfriends}"
        )

        group = _gm().get_group(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")

        group_background = group.background or ""

        user_msg = _gm().add_message(
            group_id=group_id,
            sender_id=request.userId,
            sender_name="User",
            content=request.message,
            role="user",
        )
        if not user_msg:
            raise HTTPException(status_code=500, detail="Failed to add message")
        asyncio.create_task(save_group_message_to_db(
            group_id=group_id,
            sender_id=request.userId,
            sender_name="User",
            role="user",
            content=request.message,
        ))

        ai_responses = []

        group_ltm_context = ""
        try:
            group_ltm_context = await asyncio.wait_for(
                retrieve_group_memories(group_id, request.message, limit=5),
                timeout=8.0,
            )
            if group_ltm_context:
                logger.info(f"[Group] Retrieved group LTM ({len(group_ltm_context)} chars)")
        except asyncio.TimeoutError:
            logger.warning("[Group] Group LTM retrieval timed out, skipping")
        except Exception as e:
            logger.warning(f"[Group] Group LTM retrieval failed: {e}")

        if group.auto_response:
            names = {}
            for gf_id in group.members:
                gf_config = _cm().get(gf_id)
                if gf_config:
                    names[gf_id] = gf_config["name"]

            mentioned_ids = request.mentioned_girlfriends or []

            if mentioned_ids:
                responder_ids = group.members.copy()
                logger.info(
                    f"User @-mentioned characters: "
                    f"{[names.get(gid, gid) for gid in mentioned_ids]} — they must reply"
                )
            else:
                responder_ids = _gm().get_member_response_order(group_id, user_msg)

            immediate_group = []
            delayed_group = []

            for gf_id in responder_ids:
                if gf_id in mentioned_ids:
                    immediate_group.append(gf_id)

            non_mentioned_ids = [gid for gid in responder_ids if gid not in mentioned_ids]
            for gf_id in non_mentioned_ids:
                if random.random() < 0.5:
                    immediate_group.append(gf_id)
                else:
                    delayed_group.append(gf_id)

            logger.info(f"Immediate reply group: {[names.get(gid, gid) for gid in immediate_group]}")
            logger.info(f"Delayed reply group: {[names.get(gid, gid) for gid in delayed_group]}")

            async def generate_single_response(expertId: str, is_delayed: bool = False):
                try:
                    logger.info(f"[Single gen] Start: {expertId}, is_delayed={is_delayed}")
                    gf_config = _cm().get(expertId)
                    if not gf_config:
                        logger.warning(f"[Single gen] Character config not found: {expertId}")
                        return None

                    logger.info(f"[Single gen] Character name: {gf_config.get('name', expertId)}")
                    group_context = _gm().get_group_context_for_agent(
                        group_id, expertId, limit=20
                    )
                    logger.info(
                        f"[Single gen] Group context message count: {len(group_context.get('messages', []))}"
                    )

                    is_mentioned = expertId in mentioned_ids
                    must_reply = is_mentioned

                    if is_mentioned:
                        mention_context = (
                            f"The user @-mentioned you ({gf_config['name']}) directly in the group chat"
                        )
                    elif is_delayed:
                        mention_context = (
                            "Other characters may have already replied. "
                            "Check the latest conversation and decide whether to respond."
                        )
                    else:
                        mention_context = ""

                    logger.info(
                        f"[Single gen] Calling generate_agent_response_in_group, must_reply={must_reply}"
                    )
                    response_text = await generate_agent_response_in_group(
                        expertId=expertId,
                        user_message=request.message,
                        group_context=group_context,
                        group_id=group_id,
                        mention_context=mention_context,
                        must_reply=must_reply,
                        long_term_memory_context=group_ltm_context,
                        group_background=group_background,
                    )
                    logger.info(
                        f"[Single gen] Result: {response_text[:100] if response_text else 'None'}"
                    )

                    if response_text:
                        ai_msg = _gm().add_message(
                            group_id=group_id,
                            sender_id=expertId,
                            sender_name=gf_config["name"],
                            content=response_text,
                            role="assistant",
                        )
                        if ai_msg:
                            asyncio.create_task(save_group_message_to_db(
                                group_id=group_id,
                                sender_id=expertId,
                                sender_name=gf_config["name"],
                                role="assistant",
                                content=response_text,
                            ))
                            return {
                                "expertId": expertId,
                                "name": gf_config["name"],
                                "response": response_text,
                                "message": ai_msg.to_dict(),
                            }
                except Exception as e:
                    logger.error(f"Failed to generate response for {expertId}: {e}")
                    return None

            if immediate_group:
                logger.info(
                    f"[Gather] Generating {len(immediate_group)} immediate replies: {immediate_group}"
                )
                tasks = [generate_single_response(gid, is_delayed=False) for gid in immediate_group]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                ai_responses = [
                    r for r in results if r is not None and not isinstance(r, Exception)
                ]
                logger.info(f"[Gather] Filtered reply count: {len(ai_responses)}")

                if ai_responses:
                    asyncio.create_task(
                        record_group_memories(group_id, request.message)
                    )
            else:
                logger.info("[Gather] immediate_group is empty, skipping immediate replies")

            async def process_delayed_group():
                delayed_responses = []
                for gf_id in delayed_group:
                    delay = random.uniform(5, 10)
                    logger.info(f"{names.get(gf_id, gf_id)} delayed {delay:.1f}s before replying")
                    await asyncio.sleep(delay)
                    result = await generate_single_response(gf_id, is_delayed=True)
                    if result:
                        delayed_responses.append(result)
                return delayed_responses

            asyncio.create_task(process_delayed_group())

        return GroupChatResponse(
            success=True,
            group_id=group_id,
            user_message=user_msg.to_dict(),
            ai_responses=ai_responses,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Group chat failed: {e}")
        return GroupChatResponse(success=False, group_id=group_id, error=str(e))


# ============= Group chat (SSE streaming) =============

@router.post("/{group_id}/chat/stream")
async def group_chat_stream(group_id: str, request: GroupChatRequest):
    """Group chat SSE streaming — real-time push with randomized delays."""
    try:
        group = _gm().get_group(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")

        group_background = group.background or ""

        user_msg = _gm().add_message(
            group_id=group_id,
            sender_id=request.userId,
            sender_name="User",
            content=request.message,
            role="user",
        )
        if not user_msg:
            raise HTTPException(status_code=500, detail="Failed to add message")
        asyncio.create_task(save_group_message_to_db(
            group_id=group_id,
            sender_id=request.userId,
            sender_name="User",
            role="user",
            content=request.message,
        ))

        group_ltm_context = ""
        try:
            group_ltm_context = await asyncio.wait_for(
                retrieve_group_memories(group_id, request.message, limit=5),
                timeout=8.0,
            )
            if group_ltm_context:
                logger.info(f"[SSE] Retrieved group LTM ({len(group_ltm_context)} chars)")
        except asyncio.TimeoutError:
            logger.warning("[SSE] Group LTM retrieval timed out, skipping")
        except Exception as e:
            logger.warning(f"[SSE] Group LTM retrieval failed: {e}")

        async def event_generator() -> AsyncGenerator[str, None]:
            try:
                names = {}
                for gf_id in group.members:
                    gf_config = _cm().get(gf_id)
                    if gf_config:
                        names[gf_id] = gf_config["name"]

                mentioned_ids = request.mentioned_girlfriends or []

                immediate_group = []
                delayed_group = []

                for gf_id in group.members:
                    if gf_id in mentioned_ids:
                        immediate_group.append(gf_id)

                non_mentioned_ids = [gid for gid in group.members if gid not in mentioned_ids]
                for gf_id in non_mentioned_ids:
                    if random.random() < 0.5:
                        immediate_group.append(gf_id)
                    else:
                        delayed_group.append(gf_id)

                if len(non_mentioned_ids) > 1 and len(delayed_group) == 0:
                    if immediate_group:
                        moved = immediate_group.pop()
                        delayed_group.append(moved)

                logger.info(
                    f"[SSE] Immediate reply group: {[names.get(gid, gid) for gid in immediate_group]}"
                )
                logger.info(
                    f"[SSE] Delayed reply group: {[names.get(gid, gid) for gid in delayed_group]}"
                )

                yield f"event: user_message\ndata: {json.dumps(user_msg.to_dict())}\n\n"

                async def generate_single_response(
                    expertId: str,
                    is_delayed: bool = False,
                    is_interaction: bool = False,
                ):
                    try:
                        logger.info(
                            f"[SSE single gen] Start: {expertId}, is_delayed={is_delayed}"
                        )
                        gf_config = _cm().get(expertId)
                        if not gf_config:
                            logger.warning(f"[SSE single gen] Character config not found: {expertId}")
                            return None

                        logger.info(
                            f"[SSE single gen] Character name: {gf_config.get('name', expertId)}"
                        )
                        is_mentioned = expertId in mentioned_ids
                        must_reply = is_mentioned

                        group_context = _gm().get_group_context_for_agent(
                            group_id, expertId, limit=20
                        )
                        messages_count = len(group_context.get("messages", []))
                        logger.info(f"[SSE single gen] Group context message count: {messages_count}")

                        if is_delayed:
                            logger.info(
                                f"[SSE single gen] Delayed character sees {messages_count} messages in context"
                            )

                        interaction_user_message = request.message

                        if is_mentioned:
                            mention_context = (
                                f"The user @-mentioned you ({gf_config['name']}) directly in the group chat"
                            )
                        elif is_interaction:
                            ctx_messages = group_context.get("messages", [])
                            other_replies = [
                                m for m in ctx_messages
                                if m.get("role") == "assistant"
                                and m.get("name") != gf_config["name"]
                            ]
                            if other_replies:
                                logger.info(
                                    f"[SSE interaction] Character sees other replies: "
                                    f"{[m.get('name') for m in other_replies[:3]]}"
                                )
                                target = random.choice(other_replies)
                                target_name = target.get("name", "someone")
                                target_content = target.get("content", "")[:200]
                                interaction_user_message = f"{target_name} said: {target_content}"
                                interaction_types = [
                                    f"[Interaction] {target_name} just spoke. Reply in your own voice and personality "
                                    "with a completely different angle — add a fresh perspective, share your own experience, "
                                    "or ask a new question. **Never paraphrase or copy their words.** "
                                    "Avoid filler phrases like \"me too\" or \"I agree\".",

                                    f"[Interaction] It's your turn to follow up on {target_name}'s topic. "
                                    "Stay true to your own personality and deliver 1-2 sentences of new content; "
                                    "you may pivot to a related sub-topic. **Do not copy or repeat anyone's phrasing.**",

                                    f"[Interaction] {target_name} brought up a topic — respond with your own perspective "
                                    "in one sentence. Do not repeat anything already said; "
                                    "avoid hollow affirmations like \"right\" or \"exactly\".",
                                ]
                                mention_context = random.choice(interaction_types)
                                logger.info(f"[SSE interaction] Replying to {target_name}")
                            else:
                                logger.info("[SSE interaction] No other character replies found, skipping")
                                return None
                        elif is_delayed:
                            ctx_messages = group_context.get("messages", [])
                            other_replies = [
                                m for m in ctx_messages
                                if m.get("role") == "assistant"
                                and m.get("name") != gf_config["name"]
                            ]
                            if other_replies:
                                logger.info(
                                    f"[SSE single gen] Delayed character sees other replies: "
                                    f"{[m.get('name') for m in other_replies[:3]]}"
                                )
                                if random.random() < 0.5:
                                    target_reply = random.choice(other_replies)
                                    target_name = target_reply.get("name", "someone")
                                    delayed_response_types = [
                                        f"[Responding to {target_name}] {target_name} just said something. "
                                        "Reply in your own voice with a different take — share a similar experience, "
                                        "add a new angle, or ask a related question. "
                                        "**Do not echo their content.** Avoid \"me too\" or \"I agree\".",

                                        f"[On {target_name}'s topic] Share your **unique** view or feeling. "
                                        "If your stance is similar, express it differently and add something new. "
                                        "**Strictly no copying anyone's phrasing.**",

                                        f"[Continuing the discussion] {target_name} raised a topic — now you add to it. "
                                        "Make sure it's new content: a detail, a different opinion, or a related sub-topic.",
                                    ]
                                    mention_context = random.choice(delayed_response_types)
                                    logger.info(
                                        f"[SSE single gen] Delayed character chose to respond to {target_name}"
                                    )
                                else:
                                    names_str = ", ".join(
                                        [m.get("name", "someone") for m in other_replies[:3]]
                                    )
                                    mention_context = (
                                        f"You were busy earlier and are just seeing the messages now. "
                                        f"Others have already replied: {names_str}.\n\n"
                                        "**Avoid repeating what has been said.** If you want to express the same idea, "
                                        "say it differently or add a new point. Keep it brief — 1-2 sentences."
                                    )
                                    logger.info("[SSE single gen] Delayed character chose to respond to user message")
                            else:
                                mention_context = (
                                    "You're a little late seeing the message. "
                                    "Decide whether to reply based on the current situation. "
                                    "**If you do reply, say something new — don't simply echo what others have said.**"
                                )
                                logger.info("[SSE single gen] Delayed character sees no other replies")
                        else:
                            mention_context = ""

                        logger.info("[SSE single gen] Calling generate_agent_response_in_group")
                        response_text = await generate_agent_response_in_group(
                            expertId=expertId,
                            user_message=interaction_user_message,
                            group_context=group_context,
                            group_id=group_id,
                            mention_context=mention_context,
                            must_reply=must_reply,
                            long_term_memory_context=group_ltm_context,
                            group_background=group_background,
                        )
                        logger.info(
                            f"[SSE single gen] Result: "
                            f"{response_text[:100] if response_text else 'None'}"
                        )

                        if response_text:
                            ai_msg = _gm().add_message(
                                group_id=group_id,
                                sender_id=expertId,
                                sender_name=gf_config["name"],
                                content=response_text,
                                role="assistant",
                            )
                            if ai_msg:
                                asyncio.create_task(save_group_message_to_db(
                                    group_id=group_id,
                                    sender_id=expertId,
                                    sender_name=gf_config["name"],
                                    role="assistant",
                                    content=response_text,
                                ))
                                return {
                                    "expertId": expertId,
                                    "name": gf_config["name"],
                                    "response": response_text,
                                    "message": ai_msg.to_dict(),
                                }
                    except Exception as e:
                        logger.error(f"[SSE] Failed to generate response for {expertId}: {e}")
                        return None

                # Serial processing of immediate group (stagger requests to avoid relay dedup)
                if immediate_group:
                    logger.info(f"[SSE serial] Generating {len(immediate_group)} immediate replies")
                    results = []
                    for i, gid in enumerate(immediate_group):
                        if i > 0:
                            await asyncio.sleep(0.5)
                        try:
                            result = await generate_single_response(gid, is_delayed=False)
                            results.append(result)
                        except Exception as e:
                            logger.error(f"[SSE serial] Task {i} failed: {e}")
                            results.append(None)
                    logger.info(f"[SSE serial] Done, result count: {len(results)}")

                    for i, result in enumerate(results):
                        if result:
                            logger.info(
                                f"[SSE serial] Sending reply {i+1}: {result.get('name', 'Unknown')}"
                            )
                            yield f"event: ai_response\ndata: {json.dumps(result)}\n\n"

                    valid_results = [r for r in results if r and not isinstance(r, Exception)]
                    if valid_results:
                        asyncio.create_task(
                            record_group_memories(group_id, request.message)
                        )
                else:
                    logger.info("[SSE] immediate_group is empty")

                # Serial processing of delayed group
                for gf_id in delayed_group:
                    delay = random.uniform(2, 6)
                    logger.info(f"[SSE] {names.get(gf_id, gf_id)} delayed {delay:.1f}s before replying")
                    await asyncio.sleep(delay)
                    result = await generate_single_response(gf_id, is_delayed=True)
                    if result:
                        yield f"event: ai_response\ndata: {json.dumps(result)}\n\n"

                # Interaction rounds: characters respond to each other
                MAX_INTERACTION_ROUNDS = 2
                current_round = 0
                while current_round < MAX_INTERACTION_ROUNDS:
                    current_round += 1
                    logger.info(f"[SSE interaction] Round {current_round} starting")

                    interaction_participants = [
                        gf_id for gf_id in group.members
                        if random.random() < 0.6
                    ]
                    if not interaction_participants:
                        logger.info(f"[SSE interaction] Round {current_round}: no participants, ending")
                        break

                    logger.info(
                        f"[SSE interaction] Round {current_round} participants: "
                        f"{[names.get(gid, gid) for gid in interaction_participants]}"
                    )
                    await asyncio.sleep(random.uniform(1, 3))

                    interaction_count = 0
                    for gf_id in interaction_participants:
                        if random.random() < 0.7:
                            result = await generate_single_response(
                                gf_id, is_delayed=True, is_interaction=True
                            )
                            if result:
                                interaction_count += 1
                                logger.info(f"[SSE interaction] {names.get(gf_id, gf_id)} joined interaction")
                                yield f"event: ai_response\ndata: {json.dumps(result)}\n\n"

                    logger.info(
                        f"[SSE interaction] Round {current_round} done, {interaction_count} characters replied"
                    )
                    if interaction_count == 0:
                        logger.info(f"[SSE interaction] Round {current_round}: no replies, ending")
                        break

                yield f"event: done\ndata: {json.dumps({'success': True})}\n\n"


            except Exception as e:
                logger.error(f"[SSE] Processing failed: {e}")
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SSE] Group chat failed: {e}")
        raise HTTPException(status_code=500, detail=f"Group chat failed: {str(e)}")


# ============= History management =============

@router.post("/{group_id}/clear")
async def clear_group_history(group_id: str):
    """Clear group chat history."""
    try:
        success = _gm().clear_group_messages(group_id)
        if not success:
            raise HTTPException(status_code=404, detail="Group not found")
        return {"success": True, "message": "Group history cleared"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear group history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear group history: {str(e)}")


@router.post("/{group_id}/update_message")
async def update_group_message(group_id: str, request: UpdateGroupMessageRequest):
    """Update a historical AI reply in a group chat."""
    try:
        group = _gm().get_group(group_id)
        if not group:
            return {"success": False, "msg": "Group not found"}

        session = _gm().get_group_session(group_id)
        if not session:
            return {"success": False, "msg": "Group session not found"}

        target_config = _cm().get(request.expert_id)
        if not target_config:
            return {"success": False, "msg": "Character not found"}

        found = False
        messages = session.messages

        user_msg_idx = None
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if msg.role == "user" and request.user_message in msg.content:
                user_msg_idx = i
                break

        if user_msg_idx is not None:
            for j in range(user_msg_idx + 1, len(messages)):
                msg = messages[j]
                if msg.role == "user":
                    break
                if msg.role == "assistant" and msg.sender_id == request.expert_id:
                    msg.content = request.new_reply
                    found = True
                    logger.info(
                        f"✅ Updated group message: group_id={group_id}, "
                        f"expert_id={request.expert_id}"
                    )
                    logger.info(f"   User message: {request.user_message}")
                    logger.info(f"   New reply: {request.new_reply[:50]}...")
                    break

        if found:
            try:
                _gm().save_session(group_id, session)
                logger.info("✅ Group message saved to file")
            except Exception as e:
                logger.warning(f"Failed to save group message: {e}")
            return {"success": True, "msg": "Group message updated"}
        else:
            return {"success": False, "msg": "Matching message not found"}

    except Exception as e:
        logger.error(f"Failed to update group message: {e}")
        return {"success": False, "msg": f"Failed to update group message: {str(e)}"}
