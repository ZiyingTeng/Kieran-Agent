"""聊天模型配置模块

仅支持 relay-gemma4-remote 模型（外网可用）。
"""

import logging
import os

logger = logging.getLogger(__name__)

# ============= 模型选择（从环境变量读取，仅支持 relay-gemma4-remote）=============

CHAT_MODEL: str = os.getenv("CHAT_MODEL", "relay-gemma4-remote")
GROUP_CHAT_MODEL: str = os.getenv("GROUP_CHAT_MODEL", CHAT_MODEL)

# ============= 模型配置表 =============

MODEL_CONFIGS: dict = {
    "relay-gemma4-remote": {
        "model_name": os.getenv(
            "LLM_MODEL", "google/gemma-4-26B-A4B-it"
        ),
        # use_relay=True → RelayClient（RSA 鉴权）
        # use_relay=False → DirectApiChatModel（OpenAI 兼容）
        "use_relay": os.getenv("ENERGY_API_KEY", "") != "",
        "direct_api": os.getenv("ENERGY_API_KEY", "") == "",
        "relay_path": os.getenv(
            "RELAY_API_PATH", "/v3/openrouterchatgpt"
        ),
        "base_url": os.getenv(
            "LLM_BASE_URL",
            "http://148.153.121.250:8001/v1/chat/completions",
        ),
        "api_key_env": "RELAY_GEMMA4_API_KEY",
        "description": "Gemma4-26B remote⚡",
    },
}

# ============= 当前模型配置 =============

current_model_config: dict = MODEL_CONFIGS.get(
    CHAT_MODEL, MODEL_CONFIGS["relay-gemma4-remote"]
)

# 启动日志
logger.info(
    f"💬 聊天模型: {current_model_config['description']} ({CHAT_MODEL})"
)
if GROUP_CHAT_MODEL:
    _gcm = MODEL_CONFIGS.get(GROUP_CHAT_MODEL)
    if _gcm:
        logger.info(
            f"💬 群聊模型: {_gcm['description']} ({GROUP_CHAT_MODEL})"
        )
    else:
        logger.warning(
            f"⚠️ GROUP_CHAT_MODEL={GROUP_CHAT_MODEL} "
            f"未在 MODEL_CONFIGS 中找到，群聊将回退到 {CHAT_MODEL}"
        )


def get_model_config(model_name: str) -> dict:
    """根据模型名获取配置，未找到时返回当前配置。

    :param model_name: 模型名称
    :returns: 模型配置字典
    """
    return MODEL_CONFIGS.get(model_name, current_model_config)
