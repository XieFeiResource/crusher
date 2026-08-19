"""
LLM 客户端模块
封装 OpenAI 兼容接口的调用，支持多服务商，带重试和错误处理。

日志说明：
  - 设置环境变量 LLM_LOG=1 或调用 LLMClient.enable_logging() 开启详细日志
  - 日志会打印：每次调用的 system prompt、user prompt、模型原始响应、解析结果
  - 也可以在代码中直接 import logging; logging.basicConfig(level=logging.DEBUG)
"""
import json
import logging
import os
import re
import time
from typing import Optional

from .config import LLMConfig

# 模块级 logger
logger = logging.getLogger("term_crusher.llm")

# 日志分隔线
SEP = "=" * 70
SUB_SEP = "-" * 70


def setup_logging(level: int = logging.DEBUG):
    """
    配置日志输出到终端。
    在程序入口调用一次即可，例如 app.py 顶部或测试脚本中。
    """
    root = logging.getLogger("term_crusher")
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)


# 如果环境变量开启了日志，自动配置
if os.getenv("LLM_LOG", "").strip() in ("1", "true", "yes", "on"):
    setup_logging()


class LLMClient:
    """统一的 LLM 调用客户端"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None
        self._call_count = 0  # 调用计数，用于日志标记
        self._init_client()

    @staticmethod
    def enable_logging(level: int = logging.DEBUG):
        """开启详细日志（便捷方法）"""
        setup_logging(level)
        logger.info("LLM 详细日志已开启")

    def _init_client(self):
        """初始化 OpenAI 兼容客户端"""
        try:
            from openai import OpenAI
            kwargs = {
                "api_key": self.config.api_key,
            }
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = OpenAI(**kwargs)
            logger.debug(
                "LLM 客户端初始化完成 | provider=%s model=%s base_url=%s",
                self.config.provider,
                self.config.model,
                self.config.base_url,
            )
        except ImportError:
            raise ImportError(
                "未安装 openai 库，请运行: pip install openai"
            )

    def chat(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stage: str = "",
    ) -> str:
        """
        发起一次聊天补全请求，返回纯文本回复。
        带指数退避重试机制。

        Args:
            stage: 可选的阶段名称，用于日志标记（如"阶段一-翻译"）
        """
        self._call_count += 1
        call_id = self._call_count
        stage_tag = f" [{stage}]" if stage else ""

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        temp = temperature if temperature is not None else self.config.temperature
        max_tok = max_tokens if max_tokens is not None else self.config.max_tokens

        # ===== 打印请求日志 =====
        logger.info(SEP)
        logger.info("📤 LLM 请求 #%d%s | model=%s temp=%.2f max_tokens=%d",
                    call_id, stage_tag, self.config.model, temp, max_tok)
        logger.info(SUB_SEP)

        if system_prompt:
            logger.debug("【System Prompt】\n%s\n%s", system_prompt, SUB_SEP)
        else:
            logger.debug("【System Prompt】(无)")

        logger.debug("【User Prompt】\n%s\n%s", user_prompt, SUB_SEP)

        # ===== 调用 API =====
        max_retries = 3
        for attempt in range(max_retries):
            try:
                t0 = time.time()
                response = self._client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=temp,
                    max_tokens=max_tok,
                )
                elapsed = time.time() - t0
                result = response.choices[0].message.content.strip()

                # ===== 打印响应日志 =====
                logger.info("📥 LLM 响应 #%d%s | 耗时%.2fs | %d字符",
                            call_id, stage_tag, elapsed, len(result))
                logger.debug("【原始响应】\n%s\n%s", result, SEP)

                # 打印 token 用量（如果有）
                usage = getattr(response, "usage", None)
                if usage:
                    logger.debug(
                        "【Token用量】prompt=%d completion=%d total=%d",
                        getattr(usage, "prompt_tokens", 0),
                        getattr(usage, "completion_tokens", 0),
                        getattr(usage, "total_tokens", 0),
                    )

                return result

            except Exception as e:
                logger.warning("⚠️  调用 #%d 第%d次尝试失败: %s", call_id, attempt + 1, e)
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info("   等待 %.0fs 后重试...", wait_time)
                    time.sleep(wait_time)
                else:
                    logger.error("❌ LLM 调用 #%d 最终失败（已重试%d次）: %s",
                                 call_id, max_retries, e)
                    raise RuntimeError(f"LLM 调用失败（已重试{max_retries}次）: {e}")

    def chat_json(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        stage: str = "",
    ) -> dict | list:
        """
        调用 LLM 并解析返回的 JSON。
        自动处理 ```json 代码块包裹和多余文字。
        """
        raw = self.chat(user_prompt, system_prompt, temperature, stage=stage)
        parsed = self._parse_json(raw)

        # 打印解析后的 JSON
        logger.debug("【JSON解析结果】\n%s\n%s",
                     json.dumps(parsed, ensure_ascii=False, indent=2), SEP)
        return parsed

    @staticmethod
    def _parse_json(text: str) -> dict | list:
        """从 LLM 回复中提取并解析 JSON"""
        logger.debug("开始解析 JSON，原始文本长度: %d", len(text))

        # 尝试提取 ```json ... ``` 代码块
        json_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if json_block:
            candidate = json_block.group(1).strip()
            logger.debug("从代码块中提取到 JSON 候选，长度: %d", len(candidate))
        else:
            candidate = text.strip()
            logger.debug("未找到代码块，使用全文作为候选")

        # 尝试直接解析
        try:
            result = json.loads(candidate)
            logger.debug("JSON 直接解析成功")
            return result
        except json.JSONDecodeError:
            logger.debug("直接解析失败，尝试截取花括号...")

        # 尝试截取第一个 { 到最后一个 }
        obj_match = re.search(r"\{[\s\S]*\}", candidate)
        if obj_match:
            try:
                result = json.loads(obj_match.group(0))
                logger.debug("从花括号截取解析成功")
                return result
            except json.JSONDecodeError:
                pass

        # 尝试截取第一个 [ 到最后一个 ]
        arr_match = re.search(r"\[[\s\S]*\]", candidate)
        if arr_match:
            try:
                result = json.loads(arr_match.group(0))
                logger.debug("从方括号截取解析成功")
                return result
            except json.JSONDecodeError:
                pass

        logger.error("JSON 解析失败，原始文本前500字符:\n%s", text[:500])
        raise ValueError(f"无法从 LLM 回复中解析 JSON:\n{text[:500]}")

    @staticmethod
    def extract_mermaid(text: str) -> str:
        """从 LLM 回复中提取 Mermaid 代码"""
        logger.debug("提取 Mermaid 代码，原始文本长度: %d", len(text))

        mermaid_block = re.search(r"```mermaid\s*([\s\S]*?)```", text, re.IGNORECASE)
        if mermaid_block:
            result = mermaid_block.group(1).strip()
            logger.debug("从 mermaid 代码块中提取成功，%d行", len(result.splitlines()))
            return result

        # 如果没有代码块，尝试找 flowchart 开头
        flow_match = re.search(r"(flowchart\s+[\s\S]*)", text, re.IGNORECASE)
        if flow_match:
            result = flow_match.group(1).strip()
            logger.debug("从 flowchart 关键字提取成功，%d行", len(result.splitlines()))
            return result

        logger.warning("未提取到 Mermaid 代码，返回原文")
        return text.strip()
