"""
阶段二：Mermaid 流程图生成
"""
import logging
import re

from .llm_client import LLMClient
from .prompts import STAGE2_USER_PROMPT

logger = logging.getLogger("term_crusher.flowchart")


class FlowchartGenerator:
    """收益逻辑流程图生成器"""

    def __init__(self, client: LLMClient):
        self.client = client

    def generate(self, logic_summary: str) -> str:
        """
        根据产品逻辑生成 Mermaid flowchart 代码。

        Args:
            logic_summary: 阶段一输出的 key_logic 字段

        Returns:
            Mermaid 代码字符串（不含 ```mermaid 包裹）
        """
        logger.info("=" * 50)
        logger.info("🚀 阶段二：Mermaid 流程图生成")

        if not logic_summary or logic_summary == "原文未说明":
            logger.warning("key_logic 为空，使用默认流程图")
            return self._default_flowchart()

        logger.info("输入逻辑摘要: %s", logic_summary[:100])

        # 用 replace 而非 format，避免提示词中 Mermaid 示例的 {} 被误解析为格式化占位符
        user_prompt = STAGE2_USER_PROMPT.replace("{logic_summary}", logic_summary)

        raw = self.client.chat(
            user_prompt=user_prompt,
            system_prompt="你是一位专业的 Mermaid 图表生成专家，只输出 Mermaid 代码，不输出任何解释。",
            temperature=0.2,
            stage="阶段二-流程图",
        )

        mermaid_code = self.client.extract_mermaid(raw)
        logger.debug("提取的 Mermaid 代码:\n%s", mermaid_code)

        mermaid_code = self._sanitize(mermaid_code)
        logger.debug("清洗后的 Mermaid 代码:\n%s", mermaid_code)

        # 基本校验：必须包含 flowchart
        if "flowchart" not in mermaid_code.lower() and "graph" not in mermaid_code.lower():
            logger.warning("生成的代码不包含 flowchart/graph，使用默认流程图")
            return self._default_flowchart()

        logger.info("✅ 阶段二完成 | 流程图 %d 行", len(mermaid_code.splitlines()))
        return mermaid_code

    @staticmethod
    def _sanitize(code: str) -> str:
        """
        清洗 Mermaid 代码，修复常见渲染问题：
        1. 节点/边标签中的 < 和 > 会被解析为 HTML → 替换为全角 ＜ ＞
        2. 节点标签中的 ? 在旧版 Mermaid 会解析失败 → 移除
        3. 字面 \n 换行 → 替换为 <br/>
        4. 所有节点标签用双引号包裹，彻底规避特殊字符
        5. 跳过 style/flowchart/subgraph 等非节点行
        """
        lines = code.strip().split("\n")
        cleaned = []

        skip_pattern = re.compile(
            r'^(style|classDef|class|flowchart|graph|subgraph|end|direction|linkStyle|%%)',
            re.IGNORECASE,
        )

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # 跳过非节点行
            if skip_pattern.match(stripped):
                cleaned.append(stripped)
                continue

            # 1. 替换危险字符 < （箭头中不含 <，可全局安全替换）
            stripped = stripped.replace("<", "＜")
            # 替换 > 但保留箭头 -->（负向回顾：> 前面不是 -）
            stripped = re.sub(r"(?<!-)>", "＞", stripped)

            # 2. 移除节点标签中的 ?（在引号包裹前处理，只处理括号内的）
            stripped = re.sub(r"([\[{(])[^}\])]*\?[^}\])]*([}\])])",
                              lambda m: m.group(0).replace("?", ""), stripped)

            # 3. 字面 \n → Mermaid 换行
            stripped = stripped.replace("\\n", "<br/>")

            # 4. 用双引号包裹所有节点标签（从复杂形状到简单形状，避免重复匹配）
            # 注意：(?!") 负向先行断言确保已引号包裹的标签不会被重复包裹
            stripped = re.sub(r'(\w+)\(\((?!")([^)]+?)\)\)', r'\1(("\2"))', stripped)
            # rounded: ID(label) → ID("label")
            stripped = re.sub(r'(\w+)\((?!")([^)]+?)\)', r'\1("\2")', stripped)
            # decision: ID{label} → ID{"label"}
            stripped = re.sub(r'(\w+)\{(?!")([^}]+?)\}', r'\1{"\2"}', stripped)
            # rectangle: ID[label] → ID["label"]
            stripped = re.sub(r'(\w+)\[(?!")([^\]]+?)\]', r'\1["\2"]', stripped)

            cleaned.append(stripped)

        return "\n".join(cleaned)

    @staticmethod
    def _default_flowchart() -> str:
        """默认占位流程图"""
        return """flowchart TD
    A[买入金融产品] --> B{收益条件是否满足}
    B -->|是| C[获得预期收益]
    B -->|否| D[收益降低或本金受损]
    style C fill:#e1f5e1,stroke:#2e7d32,color:#1b5e20
    style D fill:#ffe1e1,stroke:#c62828,color:#b71c1c"""
