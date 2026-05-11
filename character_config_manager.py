#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
角色配置管理器 - 从characters目录加载角色卡片
兼容AIGirl项目的API接口定义
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

# 配置日志
logger = logging.getLogger(__name__)


USER_CHAR_ID_MIN = 100000


class CharacterConfigManager:
    """角色配置管理器 - 从characters/目录加载角色卡片

    与AIGirl项目兼容：
    - 使用 expertId 作为角色ID
    - 使用 description 字段作为系统提示词
    - 保持所有Character Card字段

    目录职责：
    - characters_dir: 官方角色（由运营上传，只读）
    - user_characters_dir: 用户自定义角色（ID >= 100000，owner 可读写）
    """

    def __init__(
        self,
        characters_dir: str = "characters",
        user_characters_dir: str = "users_characters",
    ):
        """初始化角色管理器

        Args:
            characters_dir: 官方角色目录路径
            user_characters_dir: 用户自定义角色目录路径
        """
        self.characters_dir = Path(characters_dir)
        self.user_characters_dir = Path(user_characters_dir)
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._last_scan_mtime: float = 0.0
        self._last_user_scan_mtime: float = 0.0

        for d in (self.characters_dir, self.user_characters_dir):
            if not d.exists():
                logger.warning(f"Characters目录不存在: {d}")
                d.mkdir(parents=True, exist_ok=True)

        self._load_all_characters()

    def _load_all_characters(self):
        """加载 characters/ 和 users_characters/ 下的所有角色配置"""
        self._configs.clear()
        loaded_count = 0
        failed_count = 0

        dirs = [
            (self.characters_dir, True),
            (self.user_characters_dir, False),
        ]
        for directory, is_system in dirs:
            if not directory.exists():
                continue
            for json_file in sorted(directory.glob("*.json")):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    expert_id = data.get('expertId')
                    if not expert_id:
                        expert_id = json_file.stem
                        data['expertId'] = expert_id
                    if not is_system:
                        data.setdefault('is_system', False)
                    self._configs[str(expert_id)] = self._normalize_config(data)
                    loaded_count += 1
                except Exception as e:
                    logger.error(f"❌ 加载角色失败 {json_file.name}: {e}")
                    failed_count += 1

        try:
            self._last_scan_mtime = os.path.getmtime(self.characters_dir)
        except OSError:
            pass
        try:
            self._last_user_scan_mtime = os.path.getmtime(
                self.user_characters_dir
            )
        except OSError:
            pass

        logger.info(f"成功加载 {loaded_count} 个角色配置")
        if failed_count > 0:
            logger.warning(f"{failed_count} 个文件加载失败")

    def _normalize_config(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化角色配置为内部格式

        Args:
            data: 原始角色卡片数据

        Returns:
            标准化后的配置
        """
        return {
            # 核心字段
            "expertId": data.get("expertId"),
            "id": data.get("expertId"),  # 向后兼容
            "girlfriend_id": data.get("expertId"),  # 向后兼容

            # 基本信息
            "name": data.get("name", ""),
            "gender": data.get("gender", "female"),
            "age": data.get("age", ""),
            "avatar": data.get("avatar", "👩"),

            # 系统提示词（description 优先兼容 AIGirl 格式，sys_prompt 兜底）
            "sys_prompt": data.get("description") or data.get("sys_prompt", ""),
            "description": data.get("description", ""),
            "description2": data.get("description2", ""),
            "system_prompt": data.get("system_prompt", ""),

            # 角色设定
            "personality": data.get("personality", ""),
            "scenario": data.get("scenario", ""),
            "background": data.get("background", ""),

            # 对话示例
            "mes_example": data.get("mes_example", ""),
            "alternate_greetings": data.get("alternate_greetings", ""),

            # 高级设定
            "anti_out_of_character_rules": data.get("anti_out_of_character_rules", ""),
            "user_role": data.get("user_role", ""),
            "behavior": data.get("behavior", ""),

            # 语音相关
            "voiceid": data.get("voiceid", ""),
            "googlevoiceid": data.get("googlevoiceid", ""),
            "voiceprompt": data.get("voiceprompt", ""),

            # 外观相关
            "charactercolor": data.get("charactercolor", ""),
            "characterdetails": data.get("characterdetails", ""),

            # 标签和分类
            "tags": data.get("tags", ""),
            "showtags": data.get("showtags", ""),

            # 功能设置
            "chat_purpose": data.get("chat_purpose", ""),
            "purpose_completion_hint": data.get("purpose_completion_hint", ""),
            "videochat": data.get("videochat", ""),
            "prompt_template": data.get("prompt_template", ""),

            # 状态和设置
            "status": data.get("status", 1),
            "settings": data.get("settings", {}),

            # 内部标记
            "is_system": data.get("is_system", True),
            "owner_id": data.get("owner_id"),
            "model_name": data.get("model_name", "qwen-turbo"),
        }

    def get(self, expert_id: str) -> Optional[Dict[str, Any]]:
        """获取指定角色配置（兼容AIGirl命名）

        Args:
            expert_id: 角色ID

        Returns:
            角色配置字典，不存在返回None
        """
        self._reload_if_changed()
        return self._configs.get(expert_id)

    def get_by_girlfriend_id(self, girlfriend_id: str) -> Optional[Dict[str, Any]]:
        """通过girlfriend_id获取角色（向后兼容）

        Args:
            girlfriend_id: 女友ID

        Returns:
            角色配置字典
        """
        return self._configs.get(girlfriend_id)

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """获取所有角色配置

        Returns:
            所有角色配置字典 {expertId: config}
        """
        self._reload_if_changed()
        return self._configs.copy()

    def get_list(self) -> List[Dict[str, Any]]:
        """获取角色列表（简要信息，用于API返回）

        Returns:
            角色信息列表
        """
        result = []
        for expert_id, config in self._configs.items():
            result.append({
                "expertId": expert_id,
                "id": expert_id,
                "girlfriend_id": expert_id,  # 向后兼容
                "name": config.get("name", ""),
                "avatar": config.get("avatar", "👩"),
                "description": config.get("description", "")[:100] + "...",
            })
        return result

    def _reload_if_changed(self):
        """检测 characters/ 或 users_characters/ 目录变更，有则重新加载"""
        try:
            changed = False
            try:
                if os.path.getmtime(self.characters_dir) > self._last_scan_mtime:
                    changed = True
            except OSError:
                pass
            try:
                if (
                    os.path.getmtime(self.user_characters_dir)
                    > self._last_user_scan_mtime
                ):
                    changed = True
            except OSError:
                pass
            if changed:
                logger.info("检测到角色目录变更，重新加载")
                self._load_all_characters()
        except Exception as e:
            logger.warning(f"检测目录变更失败: {e}")

    def reload(self):
        """重新加载所有角色配置"""
        logger.info("重新加载角色配置...")
        self._load_all_characters()

    def _user_file_path(self, expert_id: str) -> Path:
        """返回用户自定义角色的文件路径"""
        return self.user_characters_dir / f"{expert_id}.json"

    def _next_user_id(self) -> int:
        """分配下一个用户自定义角色数字 ID（>= 100000）"""
        max_id = USER_CHAR_ID_MIN - 1
        for directory in (self.characters_dir, self.user_characters_dir):
            if not directory.exists():
                continue
            for p in directory.glob("*.json"):
                try:
                    n = int(p.stem)
                    if n >= USER_CHAR_ID_MIN:
                        max_id = max(max_id, n)
                except ValueError:
                    pass
        return max_id + 1

    def save(self, expert_id: str, config: Dict[str, Any]) -> bool:
        """保存官方角色配置到 characters/ 目录

        Args:
            expert_id: 角色ID
            config: 角色配置

        Returns:
            是否保存成功
        """
        try:
            file_path = self.characters_dir / f"{expert_id}.json"

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            self._configs[expert_id] = self._normalize_config(config)

            logger.info(f"💾 保存角色配置: {expert_id}")
            return True

        except Exception as e:
            logger.error(f"❌ 保存角色配置失败 {expert_id}: {e}")
            return False

    def _save_user(self, expert_id: str, config: Dict[str, Any]) -> bool:
        """保存用户自定义角色配置到 users_characters/ 目录"""
        try:
            file_path = self._user_file_path(expert_id)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            self._configs[expert_id] = self._normalize_config(config)
            logger.info(f"💾 保存用户角色配置: {expert_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 保存用户角色配置失败 {expert_id}: {e}")
            return False

    def create(self, data: Dict[str, Any]) -> bool:
        """保存完整角色配置（供上传接口使用）

        :param data: 完整的角色配置字典，必须包含 expertId
        :returns: 是否保存成功（已存在则返回 False）
        """
        expert_id = str(data.get("expertId", ""))
        if not expert_id:
            return False
        return self.save(expert_id, data)

    def delete(self, expert_id: str) -> bool:
        """删除角色配置（搜索两个目录）

        :param expert_id: 角色 ID
        :returns: 是否删除成功
        """
        self._reload_if_changed()
        if expert_id not in self._configs:
            return False
        try:
            for directory in (self.user_characters_dir, self.characters_dir):
                file_path = directory / f"{expert_id}.json"
                if file_path.exists():
                    file_path.unlink()
                    break
            del self._configs[expert_id]
            logger.info(f"删除角色: {expert_id}")
            return True
        except Exception as e:
            logger.error(f"删除角色失败 {expert_id}: {e}")
            return False

    def create_custom(
        self,
        name: str,
        sys_prompt: str,
        model_name: str = "relay-gemma4-remote",
    ) -> Dict[str, Any]:
        """创建用户自定义角色，自动分配 >= 100000 的数字 ID

        :param name: 角色名称
        :param sys_prompt: 系统提示词
        :param model_name: 模型名称
        :returns: 创建后的角色配置
        :raises ValueError: 创建失败
        """
        expert_id = str(self._next_user_id())

        config = {
            "expertId": expert_id,
            "name": name,
            "description": sys_prompt,
            "model_name": model_name,
            "is_system": False,
        }

        if not self._save_user(expert_id, config):
            raise ValueError("保存角色配置失败")

        return self._configs[expert_id]

    def update_custom(
        self,
        expert_id: str,
        name: Optional[str] = None,
        sys_prompt: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """更新自定义角色

        :param expert_id: 角色ID
        :param name: 新名称
        :param sys_prompt: 新提示词
        :param model_name: 新模型
        :returns: 更新后的角色配置
        :raises KeyError: 角色不存在
        :raises PermissionError: 尝试修改系统角色
        """
        self._reload_if_changed()
        config = self._configs.get(expert_id)
        if not config:
            raise KeyError(f"角色 {expert_id} 不存在")
        if config.get("is_system"):
            raise PermissionError("不能修改系统角色")

        file_path = self._user_file_path(expert_id)
        if not file_path.exists():
            file_path = self.characters_dir / f"{expert_id}.json"
        with open(file_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)

        if name is not None:
            raw["name"] = name
        if sys_prompt is not None:
            raw["description"] = sys_prompt
        if model_name is not None:
            raw["model_name"] = model_name

        if not self._save_user(expert_id, raw):
            raise ValueError("保存失败")

        return self._configs[expert_id]

    def delete_custom(self, expert_id: str) -> bool:
        """删除自定义角色

        :param expert_id: 角色ID
        :returns: 是否删除成功
        :raises KeyError: 角色不存在
        :raises PermissionError: 尝试删除系统角色
        """
        self._reload_if_changed()
        config = self._configs.get(expert_id)
        if not config:
            raise KeyError(f"角色 {expert_id} 不存在")
        if config.get("is_system"):
            raise PermissionError("不能删除系统角色")

        try:
            file_path = self._user_file_path(expert_id)
            if not file_path.exists():
                file_path = self.characters_dir / f"{expert_id}.json"
            if file_path.exists():
                file_path.unlink()

            del self._configs[expert_id]
            logger.info(f"删除自定义角色: {expert_id}")
            return True

        except (KeyError, PermissionError):
            raise
        except Exception as e:
            logger.error(f"删除角色失败 {expert_id}: {e}")
            return False

    def get_count(self) -> int:
        """获取角色总数"""
        return len(self._configs)

    def exists(self, expert_id: str) -> bool:
        """检查角色是否存在

        Args:
            expert_id: 角色ID

        Returns:
            是否存在
        """
        return expert_id in self._configs


# 全局单例
_global_character_manager: Optional[CharacterConfigManager] = None


def get_character_manager() -> CharacterConfigManager:
    """获取全局角色管理器单例"""
    global _global_character_manager
    if _global_character_manager is None:
        _global_character_manager = CharacterConfigManager()
    return _global_character_manager
