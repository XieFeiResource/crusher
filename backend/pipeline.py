"""
处理流水线模块
串联三阶段：翻译提取 → 流程图生成 → 风险识别
支持进度回调，便于前端展示处理状态。
"""
import logging
import time
from typing import Callable, Optional

from .config import LLMConfig, load_config
from .llm_client import LLMClient
from .translator import TermTranslator
from .flowchart import FlowchartGenerator
from .risk_analyzer import RiskAnalyzer

logger = logging.getLogger("term_crusher.pipeline")

ProgressCallback = Callable[[str, float], None]
"""进度回调函数签名: (阶段描述, 进度0-1)"""


class TermCrusherPipeline:
    """术语粉碎机完整处理流水线"""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or load_config()
        self.client = LLMClient(self.config)
        self.translator = TermTranslator(self.client)
        self.flowchart_gen = FlowchartGenerator(self.client)
        self.risk_analyzer = RiskAnalyzer(self.client)

    def run(
        self,
        raw_text: str,
        style: str = "通俗版",
        progress_callback: Optional[ProgressCallback] = None,
    ) -> dict:
        """
        执行完整的三阶段处理。

        Args:
            raw_text: 原始金融条款文本
            style: 翻译风格
            progress_callback: 进度回调函数

        Returns:
            {
                "translation": {...},      # 阶段一结果
                "flowchart": "mermaid...",  # 阶段二结果
                "risks": [...],             # 阶段三结果
            }
        """
        def _report(stage: str, pct: float):
            if progress_callback:
                progress_callback(stage, pct)

        t_total = time.time()
        logger.info("#" * 70)
        logger.info("🔨 术语粉碎机流水线开始")
        logger.info("输入文本: %d 字符 | 风格: %s | 模型: %s",
                    len(raw_text), style, self.config.model)
        logger.info("#" * 70)

        # 阶段一：翻译与结构化提取
        _report("正在翻译条款并提取关键要素...", 0.1)
        t1 = time.time()
        translation = self.translator.translate(raw_text, style=style)
        logger.info("阶段一耗时: %.2fs", time.time() - t1)
        _report("白话翻译完成", 0.4)

        # 阶段二：生成流程图
        _report("正在生成收益逻辑流程图...", 0.5)
        t2 = time.time()
        flowchart = self.flowchart_gen.generate(translation.get("key_logic", ""))
        logger.info("阶段二耗时: %.2fs", time.time() - t2)
        _report("流程图生成完成", 0.7)

        # 阶段三：风险识别
        _report("正在识别条款中的风险点...", 0.8)
        t3 = time.time()
        risks = self.risk_analyzer.analyze(raw_text)
        logger.info("阶段三耗时: %.2fs", time.time() - t3)
        _report("风险识别完成", 1.0)

        logger.info("#" * 70)
        logger.info("✅ 流水线完成 | 总耗时 %.2fs | LLM调用 %d 次 | 风险点 %d 个",
                    time.time() - t_total, self.client._call_count, len(risks))
        logger.info("#" * 70)

        return {
            "translation": translation,
            "flowchart": flowchart,
            "risks": risks,
        }
