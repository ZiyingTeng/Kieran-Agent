#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
心跳调度器（Heartbeat Scheduler）

类似 CoPaw 的 Heartbeat Scheduler，实现：
1. 每隔一小时检查用户最后活跃时间
2. 如果超过 24 小时未活跃，生成主动问候
3. 通过服务器推送到用户聊天界面

使用 APScheduler 实现定时任务
"""

import logging
import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.executors.asyncio import AsyncIOExecutor

logger = logging.getLogger(__name__)


@dataclass
class UserHeartbeat:
    """用户心跳信息"""
    user_id: str
    expert_id: str
    last_active_time: datetime
    last_greeting_time: Optional[datetime] = None
    greeting_count: int = 0
    is_active: bool = True


@dataclass
class GreetingResult:
    """问候结果"""
    success: bool
    user_id: str
    expert_id: str
    greeting_message: str
    timestamp: datetime
    error: Optional[str] = None


class HeartbeatScheduler:
    """
    心跳调度器

    负责定期检查用户活跃度，并为长时间未活跃的用户生成主动问候
    """

    def __init__(
        self,
        check_interval_hours: int = 1, # 每隔多少小时检查一次用户心跳
        inactive_threshold_hours: int = 4, # 超过多少小时未活跃则认为用户不活跃
        min_greeting_interval_hours: int = 24, # 最小问候间隔，防止频繁打扰用户
        greeting_probability: float = 0.3, # 每次检查时符合条件的角色发问候的概率
    ):

        self.check_interval = check_interval_hours
        self.inactive_threshold = timedelta(hours=inactive_threshold_hours)
        self.min_greeting_interval = timedelta(hours=min_greeting_interval_hours)
        self.greeting_probability = greeting_probability

        # 存储用户心跳信息
        self.user_heartbeats: Dict[str, UserHeartbeat] = {}

        # APScheduler 实例
        self.scheduler = AsyncIOScheduler(
            executors={
                'default': AsyncIOExecutor()
            },
            timezone='Asia/Shanghai'
        )

        # 问候生成器回调函数
        self.greeting_generator_callback = None

        # 推送回调函数
        self.push_notification_callback = None

        # 统计信息
        self.stats = {
            'total_checks': 0,
            'inactive_users_detected': 0,
            'greetings_sent': 0,
            'greetings_failed': 0,
            'last_check_time': None
        }

        logger.info(f"✅ HeartbeatScheduler 初始化完成")
        logger.info(f"   检查间隔: {check_interval_hours} 小时")
        logger.info(f"   不活跃阈值: {inactive_threshold_hours} 小时")
        logger.info(f"   最小问候间隔: {min_greeting_interval_hours} 小时")
        logger.info(f"   问候概率: {greeting_probability*100:.0f}%")

    def start(self):
        """启动心跳调度器"""
        if self.scheduler.running:
            logger.warning("⚠️  HeartbeatScheduler 已经在运行")
            return

        # 添加定时任务
        self.scheduler.add_job(
            self._check_heartbeats,
            trigger=IntervalTrigger(hours=self.check_interval),
            id='heartbeat_check',
            name='检查用户心跳',
            replace_existing=True
        )

        # 启动后 30 秒执行一次首次检查（让系统暖机完成）
        self.scheduler.add_job(
            self._check_heartbeats,
            trigger='date',
            run_date=datetime.now() + timedelta(seconds=30),
            id='heartbeat_startup_check',
            name='启动后首次心跳检查',
        )

        self.scheduler.start()
        logger.info(f"🚀 HeartbeatScheduler 已启动")
        logger.info(f"   首次检查: 30 秒后")
        logger.info(f"   周期检查: 每 {self.check_interval} 小时")

    def stop(self):
        """停止心跳调度器"""
        if not self.scheduler.running:
            logger.warning("⚠️  HeartbeatScheduler 未运行")
            return

        self.scheduler.shutdown(wait=False)
        logger.info(f"🛑 HeartbeatScheduler 已停止")

    def update_user_activity(self, user_id: str, expert_id: str, session_data: Dict = None):
        """
        更新用户活跃时间（同步更新内存，异步写 DB）

        Args:
            user_id: 用户ID
            expert_id: 专家/角色ID
            session_data: 会话数据（可选）
        """
        key = f"{user_id}_{expert_id}"
        now = datetime.now()

        # 如果用户不存在，创建新记录
        if key not in self.user_heartbeats:
            self.user_heartbeats[key] = UserHeartbeat(
                user_id=user_id,
                expert_id=expert_id,
                last_active_time=now
            )
            logger.info(f"✅ 注册用户心跳: {key}")
        else:
            # 更新活跃时间
            old_time = self.user_heartbeats[key].last_active_time
            self.user_heartbeats[key].last_active_time = now
            logger.info(f"🔄 更新用户活跃时间: {key}, 上次活跃: {old_time}")

        # 异步写入 DB（不阻塞调用方）
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._persist_activity(user_id, expert_id, now))
        except RuntimeError:
            pass  # 没有事件循环时跳过持久化

    async def _persist_activity(self, user_id: str, expert_id: str, active_time: datetime):
        """异步将活跃时间写入 PostgreSQL"""
        try:
            from database import get_postgres_pool
            pool = await get_postgres_pool()
            if pool:
                async with pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO user_heartbeats (user_id, expert_id, last_active_time)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (user_id, expert_id) DO UPDATE
                        SET last_active_time = $3
                    """, user_id, expert_id, active_time)
        except Exception as e:
            logger.warning(f"⚠️ 心跳持久化失败: {e}")

    async def _persist_greeting(self, user_id: str, expert_id: str, greeting_time: datetime):
        """将问候时间写入 PostgreSQL（UPSERT，确保行一定存在）"""
        try:
            from database import get_postgres_pool
            pool = await get_postgres_pool()
            if pool:
                async with pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO user_heartbeats (user_id, expert_id, last_active_time, last_greeting_time, greeting_count)
                        VALUES ($1, $2, $3, $3, 1)
                        ON CONFLICT (user_id, expert_id) DO UPDATE
                        SET last_greeting_time = $3, greeting_count = user_heartbeats.greeting_count + 1
                    """, user_id, expert_id, greeting_time)
        except Exception as e:
            logger.warning(f"⚠️ 问候时间持久化失败: {e}")

    async def load_from_db(self):
        """启动时从 PostgreSQL 恢复心跳数据"""
        try:
            from database import get_postgres_pool
            pool = await get_postgres_pool()
            if not pool:
                logger.info("ℹ️ PostgreSQL 未配置，跳过心跳数据恢复")
                return

            async with pool.acquire() as conn:
                rows = await conn.fetch("SELECT * FROM user_heartbeats")
                for row in rows:
                    key = f"{row['user_id']}_{row['expert_id']}"
                    self.user_heartbeats[key] = UserHeartbeat(
                        user_id=row['user_id'],
                        expert_id=row['expert_id'],
                        last_active_time=row['last_active_time'],
                        last_greeting_time=row['last_greeting_time'],
                        greeting_count=row['greeting_count'] or 0,
                    )
                logger.info(f"✅ 从 DB 恢复 {len(rows)} 条心跳记录")
        except Exception as e:
            logger.warning(f"⚠️ 从 DB 恢复心跳数据失败: {e}")

    def register_greeting_generator(self, callback):
        """
        注册问候生成器回调函数

        回调函数签名：
        async def generate_greeting(user_id: str, expert_id: str) -> str
        """
        self.greeting_generator_callback = callback
        logger.info("✅ 注册问候生成器回调")

    def register_push_notification(self, callback):
        """
        注册推送通知回调函数

        回调函数签名：
        async def push_notification(user_id: str, expert_id: str, message: str) -> bool
        """
        self.push_notification_callback = callback
        logger.info("✅ 注册推送通知回调")

    async def _check_heartbeats(self):
        """
        检查所有用户的心跳

        每个符合条件的 user-character 对独立以 greeting_probability 概率
        决定是否发送问候，自然分散问候时机，避免同时轰炸。
        """
        logger.info(f"🔍 开始检查用户心跳... (共 {len(self.user_heartbeats)} 条)")

        self.stats['total_checks'] += 1
        self.stats['last_check_time'] = datetime.now()

        now = datetime.now()
        eligible = []
        skipped_by_prob = 0

        for key, heartbeat in self.user_heartbeats.items():
            if now - heartbeat.last_active_time <= self.inactive_threshold:
                continue
            if not self._should_send_greeting(heartbeat, now):
                continue
            # 概率过滤：每个角色独立掷骰
            if random.random() > self.greeting_probability:
                skipped_by_prob += 1
                logger.debug(f"🎲 跳过问候(概率): {key}")
                continue
            eligible.append(heartbeat)

        self.stats['inactive_users_detected'] += len(eligible)

        for hb in eligible:
            logger.info(f"💤 不活跃: {hb.user_id}_{hb.expert_id}, "
                        f"不活跃时长: {now - hb.last_active_time}")

        if eligible:
            logger.info(f"📬 发送 {len(eligible)} 条问候 (概率跳过 {skipped_by_prob} 条)...")

            tasks = [
                self._send_greeting_to_user(heartbeat)
                for heartbeat in eligible
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, GreetingResult):
                    if result.success:
                        self.stats['greetings_sent'] += 1
                    else:
                        self.stats['greetings_failed'] += 1

        logger.info(f"✅ 心跳检查完成: 总计={len(self.user_heartbeats)}, "
                    f"问候={len(eligible)}, 概率跳过={skipped_by_prob}")

    def _should_send_greeting(self, heartbeat: UserHeartbeat, now: datetime) -> bool:
        """
        判断是否应该发送问候

        防止频繁打扰用户，需要满足：
        1. 超过不活跃阈值
        2. 距离上次问候超过最小间隔（或从未发送过问候）
        """
        if heartbeat.last_greeting_time is None:
            # 从未发送过问候，可以发送
            return True

        # 检查距离上次问候的时间
        time_since_last_greeting = now - heartbeat.last_greeting_time

        if time_since_last_greeting > self.min_greeting_interval:
            return True

        logger.debug(f"⏸️  跳过问候 {heartbeat.user_id}_{heartbeat.expert_id}: "
                    f"距离上次问候不足 {self.min_greeting_interval}")
        return False

    async def _send_greeting_to_user(self, heartbeat: UserHeartbeat) -> GreetingResult:
        """
        为单个用户发送问候

        Args:
            heartbeat: 用户心跳信息

        Returns:
            GreetingResult: 问候结果
        """
        user_id = heartbeat.user_id
        expert_id = heartbeat.expert_id
        now = datetime.now()

        try:
            # 1. 生成问候消息
            if self.greeting_generator_callback is None:
                logger.warning("⚠️  未注册问候生成器，跳过本次问候")
                return GreetingResult(
                    success=False,
                    user_id=user_id,
                    expert_id=expert_id,
                    greeting_message="",
                    timestamp=now,
                    error="未注册问候生成器"
                )
            greeting_message = await self.greeting_generator_callback(
                user_id=user_id,
                expert_id=expert_id,
                last_active_time=heartbeat.last_active_time,
                current_time=now
            )

            logger.info(f"📝 生成问候消息: {user_id}_{expert_id}")
            logger.info(f"   内容: {greeting_message[:100]}...")

            # 2. 先持久化到 DB（崩溃恢复时以 DB 为准，避免重复问候）
            await self._persist_greeting(user_id, expert_id, now)
            heartbeat.last_greeting_time = now
            heartbeat.greeting_count += 1

            # 3. 推送消息给用户
            push_success = True
            if self.push_notification_callback:
                push_success = await self.push_notification_callback(
                    user_id=user_id,
                    expert_id=expert_id,
                    message=greeting_message
                )
            else:
                logger.warning("⚠️  未注册推送回调，问候未发送")

            if push_success:
                logger.info(f"✅ 问候已发送: {user_id}_{expert_id}")
                return GreetingResult(
                    success=True,
                    user_id=user_id,
                    expert_id=expert_id,
                    greeting_message=greeting_message,
                    timestamp=now
                )
            else:
                logger.warning(f"⚠️  问候推送失败: {user_id}_{expert_id}")
                return GreetingResult(
                    success=False,
                    user_id=user_id,
                    expert_id=expert_id,
                    greeting_message=greeting_message,
                    timestamp=now,
                    error="推送失败"
                )

        except Exception as e:
            logger.error(f"❌ 发送问候失败: {user_id}_{expert_id}, 错误: {e}")
            return GreetingResult(
                success=False,
                user_id=user_id,
                expert_id=expert_id,
                greeting_message="",
                timestamp=now,
                error=str(e)
            )

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            **self.stats,
            'total_users': len(self.user_heartbeats),
            'scheduler_running': self.scheduler.running,
            'next_check_time': self.scheduler.get_job('heartbeat_check').next_run_time if self.scheduler.running else None
        }

    def get_user_heartbeat(self, user_id: str, expert_id: str) -> Optional[UserHeartbeat]:
        """获取用户心跳信息"""
        key = f"{user_id}_{expert_id}"
        return self.user_heartbeats.get(key)

    def remove_user_heartbeat(self, user_id: str, expert_id: str):
        """移除用户心跳"""
        key = f"{user_id}_{expert_id}"
        if key in self.user_heartbeats:
            del self.user_heartbeats[key]
            logger.info(f"🗑️  移除用户心跳: {key}")

    async def manually_trigger_greeting(self, user_id: str, expert_id: str) -> GreetingResult:
        """
        手动触发问候（用于测试）

        Args:
            user_id: 用户ID
            expert_id: 专家/角色ID

        Returns:
            GreetingResult: 问候结果
        """
        key = f"{user_id}_{expert_id}"
        if key not in self.user_heartbeats:
            return GreetingResult(
                success=False,
                user_id=user_id,
                expert_id=expert_id,
                greeting_message="",
                timestamp=datetime.now(),
                error="用户不存在"
            )

        heartbeat = self.user_heartbeats[key]
        return await self._send_greeting_to_user(heartbeat)


# 全局单例
_global_heartbeat_scheduler: Optional[HeartbeatScheduler] = None


def get_heartbeat_scheduler() -> HeartbeatScheduler:
    """获取全局心跳调度器实例"""
    global _global_heartbeat_scheduler
    if _global_heartbeat_scheduler is None:
        _global_heartbeat_scheduler = HeartbeatScheduler()
    return _global_heartbeat_scheduler


def initialize_heartbeat_scheduler(
    check_interval_hours: int = 1,
    inactive_threshold_hours: int = 24,
    min_greeting_interval_hours: int = 48,
    greeting_probability: float = 0.3,
) -> HeartbeatScheduler:
    """
    初始化全局心跳调度器

    Args:
        check_interval_hours: 检查间隔（小时）
        inactive_threshold_hours: 不活跃阈值（小时）
        min_greeting_interval_hours: 最小问候间隔（小时）
        greeting_probability: 每次检查时符合条件角色发问候的概率

    Returns:
        HeartbeatScheduler: 调度器实例
    """
    global _global_heartbeat_scheduler

    if _global_heartbeat_scheduler is None:
        _global_heartbeat_scheduler = HeartbeatScheduler(
            check_interval_hours=check_interval_hours,
            inactive_threshold_hours=inactive_threshold_hours,
            min_greeting_interval_hours=min_greeting_interval_hours,
            greeting_probability=greeting_probability,
        )

    return _global_heartbeat_scheduler
