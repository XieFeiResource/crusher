"""
阶段三：风险识别与高亮定位
"""
import logging

from .llm_client import LLMClient
from .prompts import STAGE3_USER_PROMPT

logger = logging.getLogger("term_crusher.risk")


class RiskAnalyzer:
    """条款风险分析器"""

    def __init__(self, client: LLMClient):
        self.client = client

    def analyze(self, raw_text: str) -> list[dict]:
        """
        识别条款中的风险点。

        Args:
            raw_text: 原始金融条款文本

        Returns:
            风险点列表，每项包含 snippet, risk_level, explanation
        """
        logger.info("=" * 50)
        logger.info("🚀 阶段三：风险识别与高亮定位")
        logger.info("输入文本长度: %d 字符", len(raw_text))

        user_prompt = STAGE3_USER_PROMPT.format(raw_text=raw_text)

        try:
            result = self.client.chat_json(
                user_prompt=user_prompt,
                system_prompt="你是一位严格的金融合规审查专家，擅长发现条款中对消费者不利的细节。只输出 JSON。",
                temperature=0.2,
                stage="阶段三-风险识别",
            )
        except Exception as e:
            logger.error("风险识别调用失败: %s", e)
            return []

        if not isinstance(result, list):
            logger.warning("返回结果不是列表，类型: %s", type(result).__name__)
            return []

        logger.info("模型返回 %d 个候选风险点", len(result))

        # 过滤无效项并校验字段
        valid_risks = []
        skipped = 0
        for item in result:
            if not isinstance(item, dict):
                skipped += 1
                continue
            snippet = item.get("snippet", "").strip()
            if not snippet:
                skipped += 1
                continue
            # 确保 snippet 在原文中存在（用于高亮匹配）
            if snippet not in raw_text:
                logger.debug("跳过不在原文中的片段: %s", snippet[:50])
                skipped += 1
                continue
            valid_risks.append({
                "snippet": snippet,
                "risk_level": item.get("risk_level", "中"),
                "explanation": item.get("explanation", "").strip(),
            })

        # 按风险等级排序：高 > 中 > 低
        level_order = {"高": 0, "中": 1, "低": 2}
        valid_risks.sort(key=lambda x: level_order.get(x["risk_level"], 3))

        logger.info("✅ 阶段三完成 | 有效风险点 %d 个（跳过 %d 个）", len(valid_risks), skipped)
        for i, r in enumerate(valid_risks, 1):
            logger.info("  风险%d [%s] %s → %s", i, r["risk_level"], r["snippet"][:40], r["explanation"][:50])

        return valid_risks
