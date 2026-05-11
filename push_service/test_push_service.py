#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推送服务测试脚本

测试离线消息队列和设备管理功能
"""

import asyncio
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_offline_queue():
    """测试离线消息队列"""
    from push_service.offline_queue import OfflineQueue

    offline_queue = OfflineQueue()

    try:
        # 测试入队
        logger.info("🧪 测试离线消息入队...")
        message = await offline_queue.enqueue(
            user_id="test_user_001",
            expert_id="1001",
            title="测试消息",
            body="这是一条测试消息",
            message_type="chat",
            priority=5
        )
        logger.info(f"✅ 消息入队成功: ID={message.id}")

        # 测试出队
        logger.info("🧪 测试离线消息出队...")
        messages = await offline_queue.dequeue("test_user_001", limit=10)
        logger.info(f"✅ 获取到 {len(messages)} 条消息")

        # 测试标记已发送
        if messages:
            await offline_queue.mark_sent(messages[0].id)
            logger.info(f"✅ 消息已标记为已发送")

        # 测试获取待发送消息数量
        count = await offline_queue.get_user_pending_count("test_user_001")
        logger.info(f"✅ 用户待发送消息数量: {count}")

        return True

    except Exception as e:
        logger.error(f"❌ 离线消息队列测试失败: {e}")
        return False
    finally:
        await offline_queue.close()


async def test_device_manager():
    """测试设备管理"""
    from push_service.device_manager import DeviceManager
    from push_service.models import Platform

    device_manager = DeviceManager()

    try:
        # 测试注册设备
        logger.info("🧪 测试设备注册...")
        device = await device_manager.register_device(
            user_id="test_user_001",
            expert_id="1001",
            platform="web",
            token="test_token_12345",
            device_info={"browser": "Chrome", "os": "Linux"}
        )
        logger.info(f"✅ 设备注册成功: ID={device.id}")

        # 测试获取用户设备
        logger.info("🧪 测试获取用户设备...")
        devices = await device_manager.get_user_devices("test_user_001")
        logger.info(f"✅ 获取到 {len(devices)} 个设备")

        # 测试注销设备
        if devices:
            await device_manager.unregister_device("test_user_001", devices[0].token)
            logger.info(f"✅ 设备注销成功")

        return True

    except Exception as e:
        logger.error(f"❌ 设备管理测试失败: {e}")
        return False
    finally:
        await device_manager.close()


async def test_push_service():
    """测试统一推送服务"""
    from push_service.push_service import get_push_service, initialize_push_service

    try:
        logger.info("🧪 测试推送服务初始化...")
        push_service = await initialize_push_service()
        logger.info("✅ 推送服务初始化成功")

        # 测试发送消息 (用户离线)
        logger.info("🧪 测试发送离线消息...")
        result = await push_service.send_to_user(
            user_id="test_user_002",
            expert_id="1001",
            title="测试推送",
            body="这是一条测试推送消息",
            message_type="chat"
        )
        logger.info(f"✅ 推送结果: {result.to_dict()}")

        # 测试获取统计信息
        logger.info("🧪 测试获取统计信息...")
        stats = await push_service.get_stats()
        logger.info(f"✅ 统计信息: {stats}")

        # 清理
        await push_service.close()
        return True

    except Exception as e:
        logger.error(f"❌ 推送服务测试失败: {e}")
        return False


async def main():
    """运行所有测试"""
    logger.info("🚀 开始推送服务测试...")
    logger.info("=" * 50)

    results = {}

    # 测试离线消息队列
    results["offline_queue"] = await test_offline_queue()
    logger.info("")

    # 测试设备管理
    results["device_manager"] = await test_device_manager()
    logger.info("")

    # 测试推送服务
    results["push_service"] = await test_push_service()
    logger.info("")

    # 汇总结果
    logger.info("=" * 50)
    logger.info("📊 测试结果汇总:")
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        logger.info(f"   {name}: {status}")

    all_passed = all(results.values())
    if all_passed:
        logger.info("\n🎉 所有测试通过!")
    else:
        logger.warning("\n⚠️ 部分测试失败，请检查日志")

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
