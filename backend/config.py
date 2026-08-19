"""
配置管理模块
从环境变量 / .env 文件加载 LLM API 配置，支持多服务商切换。
"""
import os
from dataclasses import dataclass, field
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# 各服务商默认 API 地址
PROVIDER_DEFAULTS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
}


@dataclass
class LLMConfig:
    """LLM 调用配置"""
    api_key: str = ""
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    base_url: str = ""
    temperature: float = 0.3
    max_tokens: int = 2048

    def __post_init__(self):
        # 若未指定 base_url，使用服务商默认地址
        if not self.base_url and self.provider in PROVIDER_DEFAULTS:
            self.base_url = PROVIDER_DEFAULTS[self.provider]["base_url"]
        # 若 model 为默认值但 provider 变了，同步更新
        if self.model == "deepseek-chat" and self.provider != "deepseek":
            self.model = PROVIDER_DEFAULTS.get(self.provider, {}).get("model", self.model)


def load_config() -> LLMConfig:
    """从环境变量加载配置"""
    api_key = os.getenv("LLM_API_KEY", "").strip()
    provider = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
    model = os.getenv("LLM_MODEL", "").strip()
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "2048"))

    if not model:
        model = PROVIDER_DEFAULTS.get(provider, {}).get("model", "deepseek-chat")

    return LLMConfig(
        api_key=api_key,
        provider=provider,
        model=model,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
    )
