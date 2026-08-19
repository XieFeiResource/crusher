"""
阶段一：白话翻译与结构化提取
"""
import logging
from typing import Optional
from .llm_client import LLMClient
from .prompts import SYSTEM_PROMPT, STAGE1_USER_PROMPT, STYLE_PRESETS

logger = logging.getLogger("term_crusher.translator")


class TermTranslator:
    """金融条款翻译器"""

    def __init__(self, client: LLMClient):
        self.client = client

    def translate(
        self,
        raw_text: str,
        style: str = "通俗版",
    ) -> dict:
        """
        执行阶段一：白话翻译 + 关键要素提取。

        Args:
            raw_text: 原始金融条款文本
            style: 翻译风格，见 STYLE_PRESETS

        Returns:
            包含 plain_language, product_type, term, expected_return,
            risk_level, early_redemption, fee_structure, principal_protection,
            key_logic 的字典
        """
        logger.info("=" * 50)
        logger.info("🚀 阶段一：白话翻译与结构化提取")
        logger.info("输入文本长度: %d 字符 | 风格: %s", len(raw_text), style)

        style_hint = STYLE_PRESETS.get(style, STYLE_PRESETS["通俗版"])
        system_prompt = SYSTEM_PROMPT + f"\n\n本次翻译风格要求：{style_hint}"

        user_prompt = STAGE1_USER_PROMPT.format(raw_text=raw_text)

        result = self.client.chat_json(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            stage="阶段一-翻译提取",
        )

        # 确保所有字段都存在
        default_fields = {
            "plain_language": "（解析失败，请重试）",
            "product_type": "未知",
            "term": "原文未说明",
            "expected_return": "原文未说明",
            "risk_level": "未知",
            "early_redemption": "原文未说明",
            "fee_structure": "原文未说明",
            "principal_protection": "原文未说明",
            "key_logic": "",
        }
        for key, default in default_fields.items():
            if key not in result or not result[key]:
                result[key] = default

        logger.info("✅ 阶段一完成 | 产品类型=%s | 期限=%s | 风险等级=%s",
                    result.get("product_type"), result.get("term"), result.get("risk_level"))
        return result
