#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推送服务 Celery 任务

异步处理:
1. 离线消息队列
2. 推送失败重试
3. 过期消息清理
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

from celery import Celery, group, chain
from celery.schedules import crontab

from .config import get_config

logger = logging.getLogger(__name__)

# 获取配置
config = get_config()

# 创建 Celery 应用
celery_app = Celery(
    'push_tasks',
    broker=config.celery_broker_url,
    backend=config.celery_broker_url  # 使用 Redis 作为结果后端
)

# Celery 配置
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Shanghai',
    enable_utc=True,
    # 任务路由
    task_routes={
        'push_service.tasks.send_offline_messages': {'queue': 'push'},
        'push_service.tasks.process_single_message': {'queue': 'push'},
        'push_service.tasks.retry_failed_pushes': {'queue': 'push_retry'},
        'push_service.tasks.cleanup_expired_messages': {'queue': 'push_cleanup'},
        'push_service.tasks.cleanup_inactive_devices': {'queue': 'push_cleanup'},
    },
    # 任务限流
    task_annotations={
        'push_service.tasks.send_offline_messages': {'rate_limit': '100/m'},
        'push_service.tasks.retry_failed_pushes': {'rate_limit': '50/m'},
    },
    # 重试配置
    task_default_retry_delay=60,  # 1分钟
    task_max_retries=3,
)


@celery_app.task(bind=True, max_retries=3)
def send_offline_messages(self, batch_size: int = 100):
    """
    处理离线消息队列

    定期从数据库读取待发送消息，尝试通过平台推送发送

    Args:
        batch_size: 每批处理的消息数量

    Returns:
        dict: 处理结果统计
    """
    import asyncio
    from .offline_queue import OfflineQueue
    from .device_manager import DeviceManager
    from .push_service import PushService

    async def _process():
        offline_queue = OfflineQueue()
        device_manager = DeviceManager()
        push_service = PushService()
        await push_service.initialize()

        try:
            # 获取待发送消息
            messages = await offline_queue.get_pending_messages(limit=batch_size)

            if not messages:
                return {"processed": 0, "sent": 0, "failed": 0}

            results = {
                "processed": len(messages),
                "sent": 0,
                "failed": 0,
                "skipped": 0
            }

            for msg in messages:
                try:
                    devices = await device_manager.get_user_devices(msg.user_id)

                    if not devices:
                        results["skipped"] += 1
                        continue

                    sent = False
                    title = getattr(msg, 'title', '') or '新消息'
                    body = getattr(msg, 'body', '') or ''
                    data = getattr(msg, 'data', None) or {}

                    for device in devices:
                        provider = push_service.providers.get(device.platform.value)
                        if not provider:
                            continue
                        try:
                            ok = await provider.send(device.token, title, body, data)
                            if ok:
                                sent = True
                                await device_manager.log_push(
                                    user_id=msg.user_id,
                                    platform=device.platform.value,
                                    message_type=getattr(msg, 'message_type', 'chat'),
                                    status="success",
                                )
                                break  # 一个设备发成功即可
                            else:
                                await device_manager.log_push(
                                    user_id=msg.user_id,
                                    platform=device.platform.value,
                                    message_type=getattr(msg, 'message_type', 'chat'),
                                    status="failed",
                                    error_message="provider returned False",
                                )
                        except Exception as dev_err:
                            logger.warning(f"设备 {device.platform.value} 发送失败: {dev_err}")

                    if sent:
                        await offline_queue.mark_sent(msg.id)
                        results["sent"] += 1
                    else:
                        await offline_queue.mark_failed(msg.id)
                        results["failed"] += 1

                except Exception as e:
                    logger.error(f"处理消息 {msg.id} 失败: {e}")
                    await offline_queue.mark_failed(msg.id, str(e))
                    results["failed"] += 1

            return results

        finally:
            await offline_queue.close()
            await device_manager.close()

    # 运行异步任务
    return asyncio.run(_process())


@celery_app.task(bind=True)
def process_single_message(self, message_id: int, user_id: str, expert_id: str,
                           title: str, body: str, message_type: str = "chat"):
    """
    处理单条离线消息

    Args:
        message_id: 消息ID
        user_id: 用户ID
        expert_id: 角色ID
        title: 标题
        body: 消息内容
        message_type: 消息类型

    Returns:
        bool: 是否成功
    """
    import asyncio
    from .offline_queue import OfflineQueue
    from .device_manager import DeviceManager
    from .push_service import PushService

    async def _process():
        offline_queue = OfflineQueue()
        device_manager = DeviceManager()
        push_service = PushService()
        await push_service.initialize()

        try:
            devices = await device_manager.get_user_devices(user_id)

            if not devices:
                return False

            sent = False
            data = {"expert_id": expert_id, "message_type": message_type}

            for device in devices:
                provider = push_service.providers.get(device.platform.value)
                if not provider:
                    continue
                try:
                    if await provider.send(device.token, title, body, data):
                        sent = True
                        break
                except Exception as e:
                    logger.warning(f"设备 {device.platform.value} 发送失败: {e}")

            if sent:
                await offline_queue.mark_sent(message_id)
                return True
            else:
                await offline_queue.mark_failed(message_id)
                return False

        finally:
            await offline_queue.close()
            await device_manager.close()

    return asyncio.run(_process())


@celery_app.task
def cleanup_expired_messages():
    """
    清理过期消息

    定期清理已过期的离线消息
    """
    import asyncio
    from .offline_queue import OfflineQueue

    async def _cleanup():
        offline_queue = OfflineQueue()
        try:
            count = await offline_queue.cleanup_expired_messages()
            return {"cleaned": count}
        finally:
            await offline_queue.close()

    return asyncio.run(_cleanup())


@celery_app.task
def cleanup_inactive_devices(days: int = 30):
    """
    清理长时间未使用的设备

    Args:
        days: 天数阈值
    """
    import asyncio
    from .device_manager import DeviceManager

    async def _cleanup():
        device_manager = DeviceManager()
        try:
            count = await device_manager.cleanup_inactive_devices(days)
            return {"cleaned": count}
        finally:
            await device_manager.close()

    return asyncio.run(_cleanup())


@celery_app.task
def retry_failed_pushes():
    """
    重试失败的推送

    定期检查状态为 failed 但未达到最大重试次数的消息
    """
    import asyncio
    import asyncpg
    from .config import get_config

    async def _retry():
        config = get_config()

        conn = await asyncpg.create_pool(config.postgres_url, min_size=1, max_size=5)

        try:
            async with conn.acquire() as connection:
                # 查找需要重试的消息
                rows = await connection.fetch("""
                    SELECT id, user_id, expert_id, title, body, message_type, data
                    FROM offline_messages
                    WHERE status = 'failed'
                      AND retry_count < max_retries
                      AND expires_at > NOW()
                    ORDER BY retry_count ASC
                    LIMIT 50
                """)

                if not rows:
                    return {"retried": 0}

                # 重置为 pending 状态，让 send_offline_messages 处理
                for row in rows:
                    await connection.execute("""
                        UPDATE offline_messages
                        SET status = 'pending'
                        WHERE id = $1
                    """, row['id'])

                return {"retried": len(rows)}

        finally:
            await conn.close()

    return asyncio.run(_retry())


@celery_app.task
def sync_online_users_to_redis():
    """
    同步在线用户到 Redis

    定期检查并更新在线用户状态
    """
    import asyncio
    from .registry import get_connection_registry

    async def _sync():
        registry = get_connection_registry()

        if hasattr(registry, 'cleanup_stale_connections'):
            await registry.cleanup_stale_connections()
            return {"synced": True}

        return {"synced": False}

    return asyncio.run(_sync())


# ==================== 定时任务配置 ====================

# 配置 Celery Beat 定时任务
celery_app.conf.beat_schedule = {
    # 每5分钟处理一次离线消息
    'process-offline-messages': {
        'task': 'push_service.tasks.send_offline_messages',
        'schedule': 300.0,  # 5分钟
        'options': {'args': (100,)}
    },
    # 每10分钟重试失败的推送
    'retry-failed-pushes': {
        'task': 'push_service.tasks.retry_failed_pushes',
        'schedule': 600.0,  # 10分钟
    },
    # 每小时清理过期消息
    'cleanup-expired-messages': {
        'task': 'push_service.tasks.cleanup_expired_messages',
        'schedule': crontab(hour='*', minute=0),  # 每小时
    },
    # 每天凌晨2点清理不活跃设备
    'cleanup-inactive-devices': {
        'task': 'push_service.tasks.cleanup_inactive_devices',
        'schedule': crontab(hour=2, minute=0),  # 每天凌晨2点
        'options': {'args': (30,)}
    },
    # 每5分钟同步在线用户
    'sync-online-users': {
        'task': 'push_service.tasks.sync_online_users_to_redis',
        'schedule': 300.0,  # 5分钟
    },
}


# ==================== 便捷命令 ====================

def run_worker():
    """
    启动 Celery Worker

    命令:
        python -m push_service.tasks worker
    """
    import sys

    argv = [
        'worker',
        '--loglevel=info',
        '--queues=push,push_retry,push_cleanup',
        '--concurrency=4',
        '--max-tasks-per-child=1000'
    ]

    celery_app.worker_main(argv)


def run_beat():
    """
    启动 Celery Beat (定时任务调度器)

    命令:
        python -m push_service.tasks beat
    """
    import sys

    argv = [
        'beat',
        '--loglevel=info'
    ]

    celery_app.worker_main(argv)


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == 'worker':
            run_worker()
        elif command == 'beat':
            run_beat()
        else:
            print("用法: python -m push_service.tasks [worker|beat]")
    else:
        print("用法: python -m push_service.tasks [worker|beat]")
