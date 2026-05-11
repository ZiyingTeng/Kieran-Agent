#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推送服务数据模型
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from pydantic import BaseModel, Field
from shortuuid import ShortUUID


class Platform(str, Enum):
    """推送平台"""
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


class MessageType(str, Enum):
    """消息类型"""
    CHAT = "chat"
    GREETING = "greeting"
    SYSTEM = "system"


class MessageStatus(str, Enum):
    """消息状态"""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    EXPIRED = "expired"


class PushStatus(str, Enum):
    """推送状态"""
    SUCCESS = "success"
    FAILED = "failed"
    QUEUED = "queued"
    OFFLINE = "offline"


# ==================== Pydantic 模型 (API 请求/响应) ====================

class DeviceRegisterRequest(BaseModel):
    """设备注册请求"""
    user_id: str = Field(..., description="用户ID")
    expert_id: str = Field(..., description="角色ID")
    platform: Platform = Field(..., description="平台类型")
    token: str = Field(..., description="设备令牌")
    device_info: Dict[str, Any] = Field(default_factory=dict, description="设备信息")


class DeviceUnregisterRequest(BaseModel):
    """设备注销请求"""
    user_id: str = Field(..., description="用户ID")
    token: str = Field(..., description="设备令牌")


class PushMessageRequest(BaseModel):
    """推送消息请求"""
    user_id: str = Field(..., description="用户ID")
    expert_id: str = Field(..., description="角色ID")
    title: str = Field(..., description="标题")
    body: str = Field(..., description="消息内容")
    message_type: MessageType = Field(default=MessageType.CHAT, description="消息类型")
    data: Dict[str, Any] = Field(default_factory=dict, description="附加数据")
    priority: int = Field(default=5, ge=1, le=10, description="优先级 (1-10)")


class TestPushRequest(BaseModel):
    """测试推送请求"""
    user_id: str = Field(..., description="用户ID")
    expert_id: str = Field(..., description="角色ID")
    message: str = Field(..., description="测试消息")


class DeviceInfoResponse(BaseModel):
    """设备信息响应"""
    id: int
    user_id: str
    expert_id: str
    platform: str
    device_info: Dict[str, Any]
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]


class PushResponse(BaseModel):
    """推送响应"""
    success: bool
    user_id: str
    delivered: bool = False
    websocket_sent: bool = False
    platforms_sent: List[str] = Field(default_factory=list)
    queued: bool = False
    error: Optional[str] = None


class OfflineMessageResponse(BaseModel):
    """离线消息响应"""
    id: int
    user_id: str
    expert_id: str
    message_type: str
    title: Optional[str]
    body: str
    data: Dict[str, Any]
    status: str
    created_at: datetime
    expires_at: datetime


# ==================== Dataclass 模型 (内部使用) ====================

@dataclass
class PushResult:
    """推送结果"""
    user_id: str
    delivered: bool = False
    websocket_sent: bool = False
    platforms_sent: List[str] = field(default_factory=list)
    queued: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "user_id": self.user_id,
            "delivered": self.delivered,
            "websocket_sent": self.websocket_sent,
            "platforms_sent": self.platforms_sent,
            "queued": self.queued,
            "error": self.error
        }


@dataclass
class DeviceInfo:
    """设备信息"""
    id: Optional[int] = None
    user_id: str = ""
    expert_id: str = ""
    platform: Platform = Platform.WEB
    token: str = ""
    device_info: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "expert_id": self.expert_id,
            "platform": self.platform.value if isinstance(self.platform, Platform) else self.platform,
            "device_info": self.device_info,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None
        }


@dataclass
class OfflineMessage:
    """离线消息"""
    id: Optional[int] = None
    user_id: str = ""
    expert_id: str = ""
    message_type: MessageType = MessageType.CHAT
    title: Optional[str] = None
    body: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5
    status: MessageStatus = MessageStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    def __post_init__(self):
        if self.scheduled_at is None:
            self.scheduled_at = datetime.now()
        if self.expires_at is None:
            from .config import get_config
            config = get_config()
            self.expires_at = datetime.now() + __import__('datetime').timedelta(
                days=config.offline_expire_days
            )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "expert_id": self.expert_id,
            "message_type": self.message_type.value if isinstance(self.message_type, MessageType) else self.message_type,
            "title": self.title,
            "body": self.body,
            "data": self.data,
            "priority": self.priority,
            "status": self.status.value if isinstance(self.status, MessageStatus) else self.status,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }


@dataclass
class ConnectionInfo:
    """连接信息 (Redis 存储)"""
    connection_id: str
    user_id: str
    expert_id: str
    connected_at: datetime
    last_ping: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "connection_id": self.connection_id,
            "user_id": self.user_id,
            "expert_id": self.expert_id,
            "connected_at": self.connected_at.isoformat(),
            "last_ping": self.last_ping.isoformat() if self.last_ping else None,
            "metadata": self.metadata
        }


def generate_connection_id() -> str:
    """生成唯一的连接 ID"""
    return ShortUUID().random(length=12)
