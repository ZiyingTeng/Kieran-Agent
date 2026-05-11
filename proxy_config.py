"""代理配置模块

必须在所有其他模块（特别是 agentscope 等 HTTP 客户端）初始化之前导入。
读取并清除全局代理环境变量，避免 Privoxy 拦截内网请求
（vLLM at 192.168.1.18, Redis, PostgreSQL）。

外网客户端（relay_client 等）从此模块读取 SAVED_PROXY 使用代理。
"""

import os

# 保存代理地址供外网客户端使用
SAVED_PROXY: str = (
    os.environ.get("HTTP_PROXY")
    or os.environ.get("http_proxy")
    or os.environ.get("HTTPS_PROXY")
    or os.environ.get("https_proxy")
    or ""
)

# 清除全局代理
for _proxy_key in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
    os.environ.pop(_proxy_key, None)
