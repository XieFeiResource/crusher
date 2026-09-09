"""
条款对比分析模块
对多款金融产品进行参数提取、维度对齐、评分和白话对比总结。
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from .config import LLMConfig
from .pipeline import TermCrusherPipeline
from .scoring_engine import (
    ProductProfile,
    ScoringEngine,
    ScoringResult,
    generate_recommendation,
)
from .llm_client import LLMClient

logger = logging.getLogger("term_crusher.comparison")


# 统一对比维度
COMPARISON_DIMENSIONS = [
    ("product_type", "产品类型"),
    ("term", "投资期限"),
    ("expected_return", "预期收益率"),
    ("risk_level", "风险等级"),
    ("principal_protection", "本金保障"),
    ("early_redemption", "流动性(提前赎回)"),
    ("fee_structure", "综合费率"),
]


@dataclass
class ProductAnalysis:
    """单个产品的完整分析结果"""
    name: str
    raw_text: str
    translation: dict = field(default_factory=dict)
    risks: list = field(default_factory=list)
    profile: ProductProfile = field(default_factory=ProductProfile)
    scoring: Optional[ScoringResult] = None


@dataclass
class ComparisonResult:
    """对比分析总结果"""
    products: list[ProductAnalysis] = field(default_factory=list)
    scoring_results: list[ScoringResult] = field(default_factory=list)
    recommendation: dict = field(default_factory=dict)
    plain_summary: str = ""
    dimension_winners: dict[str, str] = field(default_factory=dict)  # 每个维度的优势产品


class ComparisonEngine:
    """条款对比引擎"""

    def __init__(self, config: LLMConfig, risk_preference: str = "稳健"):
        self.config = config
        self.risk_preference = risk_preference
        self.pipeline = TermCrusherPipeline(config=config)
        self.scoring = ScoringEngine(risk_preference=risk_preference)
        self.llm = LLMClient(config)

    def compare(
        self,
        products: list[tuple[str, str]],  # [(name, text), ...]
        progress_callback=None,
    ) -> ComparisonResult:
        """
        执行多产品对比分析。

        Args:
            products: [(产品名, 条款文本), ...]
            progress_callback: 进度回调 (stage_desc, progress_0-1)
        """
        result = ComparisonResult()
        n = len(products)

        # 第一步：对每个产品独立执行参数提取和风险识别
        for i, (name, text) in enumerate(products):
            if progress_callback:
                progress_callback(f"正在分析「{name}」（{i+1}/{n}）...", i / n * 0.6)

            logger.info("对比分析 - 处理产品[%d/%d]: %s", i + 1, n, name)

            # 只跑阶段一（翻译提取）和阶段三（风险识别），不需要流程图
            translation = self.pipeline.translator.translate(text, style="通俗版")
            risks = self.pipeline.risk_analyzer.analyze(text)

            # 构建产品画像
            profile = self._build_profile(name, text, translation, risks)

            pa = ProductAnalysis(
                name=name,
                raw_text=text,
                translation=translation,
                risks=risks,
                profile=profile,
            )
            result.products.append(pa)

        # 第二步：评分
        if progress_callback:
            progress_callback("正在计算综合评分...", 0.65)

        profiles = [pa.profile for pa in result.products]
        scoring_results = self.scoring.score_all(profiles)
        result.scoring_results = scoring_results

        # 把评分结果关联回 ProductAnalysis
        profile_map = {p.name: p for p in result.products}
        for sr in scoring_results:
            if sr.product_name in profile_map:
                profile_map[sr.product_name].scoring = sr

        # 第三步：维度优势方判定
        if progress_callback:
            progress_callback("正在对比各维度优势...", 0.75)
        result.dimension_winners = self._find_dimension_winners(result.products)

        # 第四步：生成推荐结论
        if progress_callback:
            progress_callback("正在生成推荐结论...", 0.85)

        winner = scoring_results[0]
        losers = scoring_results[1:]
        profiles_dict = {pa.name: pa.profile for pa in result.products}
        result.recommendation = generate_recommendation(
            winner=winner,
            losers=losers,
            profiles=profiles_dict,
            risk_preference=self.risk_preference,
        )

        # 第五步：LLM 生成白话对比总结
        if progress_callback:
            progress_callback("正在生成白话对比总结...", 0.92)
        result.plain_summary = self._generate_plain_summary(result.products, result.scoring_results)

        if progress_callback:
            progress_callback("对比分析完成", 1.0)

        return result

    def _build_profile(
        self,
        name: str,
        raw_text: str,
        translation: dict,
        risks: list,
    ) -> ProductProfile:
        """从翻译结果构建标准化产品画像"""
        high_risk = sum(1 for r in risks if r.get("risk_level") == "高")

        # 计算字段完整度
        fields = [
            translation.get("product_type", ""),
            translation.get("term", ""),
            translation.get("expected_return", ""),
            translation.get("risk_level", ""),
            translation.get("early_redemption", ""),
            translation.get("fee_structure", ""),
            translation.get("principal_protection", ""),
        ]
        unknown = sum(1 for f in fields if "原文未说明" in f or not f or f == "未知")
        completeness = 1 - (unknown / len(fields))

        return ProductProfile(
            name=name,
            product_type=translation.get("product_type", ""),
            term=translation.get("term", ""),
            expected_return=translation.get("expected_return", ""),
            risk_level=translation.get("risk_level", ""),
            early_redemption=translation.get("early_redemption", ""),
            fee_structure=translation.get("fee_structure", ""),
            principal_protection=translation.get("principal_protection", ""),
            key_logic=translation.get("key_logic", ""),
            plain_language=translation.get("plain_language", ""),
            risk_count=len(risks),
            high_risk_count=high_risk,
            risk_snippets=[r.get("snippet", "") for r in risks],
            raw_text=raw_text,
            field_completeness=completeness,
        )

    def _find_dimension_winners(self, products: list[ProductAnalysis]) -> dict[str, str]:
        """
        判定每个对比维度的优势方。
        返回 {维度key: 优势产品名}，无法判定时返回空字符串。
        """
        winners = {}
        dim_map = {k: v for k, v in COMPARISON_DIMENSIONS}

        for key, label in COMPARISON_DIMENSIONS:
            values = {}
            for pa in products:
                val = pa.translation.get(key, "")
                if val and "原文未说明" not in val and val != "未知":
                    values[pa.name] = val

            if len(values) < 2:
                winners[key] = ""
                continue

            # 根据维度类型判定优势
            if key == "expected_return":
                # 收益率越高越好
                winner = max(values, key=lambda n: self._extract_max_rate(values[n]))
                winners[key] = winner
            elif key == "risk_level":
                # 风险越低越好
                winner = min(values, key=lambda n: self._risk_level_score(values[n]))
                winners[key] = winner
            elif key == "principal_protection":
                # 保本优于不保本
                winner = max(values, key=lambda n: self._principal_score(values[n]))
                winners[key] = winner
            elif key == "early_redemption":
                # 流动性越好越优
                winner = max(values, key=lambda n: self._liquidity_score(values[n]))
                winners[key] = winner
            elif key == "fee_structure":
                # 费率越低越好
                winner = min(values, key=lambda n: self._extract_max_rate(values[n]) if self._extract_max_rate(values[n]) > 0 else 999)
                winners[key] = winner
            else:
                # 产品类型、期限等无法简单判定优劣
                winners[key] = ""

        return winners

    def _generate_plain_summary(
        self,
        products: list[ProductAnalysis],
        scoring: list[ScoringResult],
    ) -> str:
        """用 LLM 生成白话对比总结"""
        # 构建对比信息
        info_lines = []
        for pa in products:
            t = pa.translation
            sr = next((s for s in scoring if s.product_name == pa.name), None)
            score_str = f"{sr.adjusted_score:.1f}分" if sr else "未评分"
            info_lines.append(
                f"【{pa.name}】综合得分{score_str}\n"
                f"  类型: {t.get('product_type', '未知')}\n"
                f"  期限: {t.get('term', '未知')}\n"
                f"  收益: {t.get('expected_return', '未知')}\n"
                f"  风险: {t.get('risk_level', '未知')}\n"
                f"  本金: {t.get('principal_protection', '未知')}\n"
                f"  白话: {t.get('plain_language', '')}"
            )

        winner_name = scoring[0].product_name if scoring else ""

        prompt = f"""请用通俗易懂的大白话，对比以下{len(products)}款金融产品的核心差异，并给出选择建议。

产品信息：
{chr(10).join(info_lines)}

综合得分排名：{ ' > '.join(f'{s.product_name}({s.adjusted_score:.1f}分)' for s in scoring) }
风险偏好：{self.risk_preference}型

要求：
1. 用300字以内的大白话总结，像跟朋友聊天一样
2. 说清楚每款产品的核心特点和最大区别
3. 说明为什么{winner_name}综合得分更高
4. 给出适合什么人的选择建议
5. 不要使用专业术语，必要时用比喻
"""

        try:
            summary = self.llm.chat(
                user_prompt=prompt,
                system_prompt="你是一位贴心的金融理财顾问，擅长用大白话给普通人解释金融产品的区别，说话幽默接地气。",
                temperature=0.4,
                stage="对比总结",
            )
            return summary
        except Exception as e:
            logger.error("白话对比总结生成失败: %s", e)
            return f"（白话总结生成失败：{e}）"

    # ============================================================
    # 维度比较辅助方法
    # ============================================================
    @staticmethod
    def _extract_max_rate(text: str) -> float:
        """从文本中提取最大收益率"""
        import re
        rates = []
        for m in re.finditer(r"(\d+\.?\d*)\s*%", text):
            try:
                r = float(m.group(1))
                if 0 < r <= 100:
                    rates.append(r)
            except ValueError:
                continue
        return max(rates) if rates else 0.0

    @staticmethod
    def _risk_level_score(text: str) -> float:
        """风险等级转分数（越低越好）"""
        if "R1" in text or "低风险" in text:
            return 1
        if "R2" in text or "中低" in text:
            return 2
        if "R3" in text or "中风险" in text or "中等" in text:
            return 3
        if "R4" in text or "中高" in text:
            return 4
        if "R5" in text or "高风险" in text:
            return 5
        return 3

    @staticmethod
    def _principal_score(text: str) -> float:
        """本金保障评分（越高越好）"""
        if "不保本" in text or "可能亏损" in text:
            return 1
        if "部分保本" in text:
            return 2
        if "保本" in text:
            return 3
        return 1.5

    @staticmethod
    def _liquidity_score(text: str) -> float:
        """流动性评分（越高越好）"""
        if any(k in text for k in ["随时", "T+0", "当日"]):
            return 5
        if any(k in text for k in ["T+1", "T+2", "次日"]):
            return 4
        if "封闭期后" in text or "持有满" in text:
            return 3
        if any(k in text for k in ["不可", "不能", "无法"]):
            return 1
        if "违约金" in text or "罚息" in text:
            return 2
        return 2.5
