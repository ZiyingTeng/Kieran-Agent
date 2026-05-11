#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推送服务 API 路由

提供设备令牌管理和推送相关的 HTTP API
"""

import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, status

from .models import (
    DeviceRegisterRequest,
    DeviceUnregisterRequest,
    PushMessageRequest,
    TestPushRequest,
    PushResponse,
    DeviceInfoResponse,
    OfflineMessageResponse
)
from .push_service import get_push_service

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(
    prefix="/api/push",
    tags=["push"]
)


@router.post("/register", response_model=Dict[str, Any])
async def register_device(req: DeviceRegisterRequest):
    """
    注册设备推送令牌

    Args:
        req: 设备注册请求

    Returns:
        注册结果
    """
    try:
        push_service = get_push_service()

        device = await push_service.register_device(
            user_id=req.user_id,
            expert_id=req.expert_id,
            platform=req.platform.value,
            token=req.token,
            device_info=req.device_info
        )

        return {
            "success": True,
            "device_id": device.id,
            "message": "设备注册成功"
        }

    except Exception as e:
        logger.error(f"❌ 设备注册失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"设备注册失败: {str(e)}"
        )


@router.get("/devices", response_model=Dict[str, Any])
async def get_user_devices(user_id: str):
    """
    获取用户的所有已注册设备

    Args:
        user_id: 用户ID

    Returns:
        设备列表
    """
    try:
        push_service = get_push_service()

        devices = await push_service.get_user_devices(user_id)

        return {
            "success": True,
            "devices": devices,
            "count": len(devices)
        }

    except Exception as e:
        logger.error(f"❌ 获取设备列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取设备列表失败: {str(e)}"
        )


@router.delete("/unregister", response_model=Dict[str, Any])
async def unregister_device(req: DeviceUnregisterRequest):
    """
    取消设备推送

    Args:
        req: 设备注销请求

    Returns:
        注销结果
    """
    try:
        push_service = get_push_service()

        success = await push_service.unregister_device(
            user_id=req.user_id,
            token=req.token
        )

        if success:
            return {
                "success": True,
                "message": "设备注销成功"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="设备不存在"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 设备注销失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"设备注销失败: {str(e)}"
        )


@router.post("/send", response_model=PushResponse)
async def send_push_message(req: PushMessageRequest):
    """
    发送推送消息

    Args:
        req: 推送消息请求

    Returns:
        推送结果
    """
    try:
        push_service = get_push_service()

        result = await push_service.send_to_user(
            user_id=req.user_id,
            expert_id=req.expert_id,
            title=req.title,
            body=req.body,
            message_type=req.message_type.value,
            data=req.data,
            priority=req.priority
        )

        return PushResponse(**result.to_dict())

    except Exception as e:
        logger.error(f"❌ 发送推送失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"发送推送失败: {str(e)}"
        )


@router.post("/test", response_model=Dict[str, Any])
async def test_push(req: TestPushRequest):
    """
    测试推送 (用于调试)

    Args:
        req: 测试推送请求

    Returns:
        推送结果
    """
    try:
        push_service = get_push_service()

        result = await push_service.send_to_user(
            user_id=req.user_id,
            expert_id=req.expert_id,
            title="测试消息",
            body=req.message,
            message_type="system",
            priority=5
        )

        return {
            "success": result.delivered or result.queued,
            "result": result.to_dict()
        }

    except Exception as e:
        logger.error(f"❌ 测试推送失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"测试推送失败: {str(e)}"
        )


@router.get("/offline/{user_id}", response_model=Dict[str, Any])
async def get_offline_messages(user_id: str, limit: int = 10):
    """
    获取用户的离线消息

    Args:
        user_id: 用户ID
        limit: 最大数量

    Returns:
        离线消息列表
    """
    try:
        push_service = get_push_service()

        messages = await push_service.get_offline_messages(user_id, limit)

        return {
            "success": True,
            "messages": messages,
            "count": len(messages)
        }

    except Exception as e:
        logger.error(f"❌ 获取离线消息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取离线消息失败: {str(e)}"
        )


@router.delete("/offline/{user_id}", response_model=Dict[str, Any])
async def clear_offline_messages(user_id: str, expert_id: str = None):
    """
    清空用户的离线消息

    Args:
        user_id: 用户ID
        expert_id: 角色ID (可选)

    Returns:
        清理结果
    """
    try:
        push_service = get_push_service()

        count = await push_service.clear_offline_messages(user_id, expert_id)

        return {
            "success": True,
            "cleared_count": count,
            "message": f"已清空 {count} 条离线消息"
        }

    except Exception as e:
        logger.error(f"❌ 清空离线消息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清空离线消息失败: {str(e)}"
        )


@router.get("/stats", response_model=Dict[str, Any])
async def get_push_stats():
    """
    获取推送服务统计信息

    Returns:
        统计信息
    """
    try:
        push_service = get_push_service()

        stats = await push_service.get_stats()

        return {
            "success": True,
            "stats": stats
        }

    except Exception as e:
        logger.error(f"❌ 获取统计信息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计信息失败: {str(e)}"
        )


@router.get("/health", response_model=Dict[str, Any])
async def health_check():
    """
    健康检查

    Returns:
        健康状态
    """
    return {
        "status": "healthy",
        "service": "push_service",
        "version": "1.0.0"
    }
