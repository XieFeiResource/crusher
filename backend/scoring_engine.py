"""
评分规则引擎
纯 Python 规则实现，不调用 LLM，确保打分客观一致。

五个维度：收益性、安全性、流动性、透明度、费率
每个维度 0-100 分，按预设评分表打分。
综合得分 = Σ(维度得分 × 权重)
附加规则：透明度≤30 总分扣10分；违规承诺安全性直接降至10分。
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("term_crusher.scoring")


# ============================================================
# 数据结构
# ============================================================

@dataclass
class ProductProfile:
    """产品画像（从翻译结果中提取的标准化字段）"""
    name: str = "未命名产品"
    product_type: str = ""
    term: str = ""
    expected_return: str = ""
    risk_level: str = ""
    early_redemption: str = ""
    fee_structure: str = ""
    principal_protection: str = ""
    key_logic: str = ""
    plain_language: str = ""
    # 风险识别结果
    risk_count: int = 0
    high_risk_count: int = 0
    risk_snippets: list = field(default_factory=list)
    # 原始条款文本（用于违规承诺检测）
    raw_text: str = ""
    # 字段完整度（有多少字段不是"原文未说明"）
    field_completeness: float = 1.0


@dataclass
class DimensionScore:
    """单个维度得分"""
    name: str
    score: float
    weight: float
    weighted: float
    reason: str


@dataclass
class ScoringResult:
    """单个产品的评分结果"""
    product_name: str
    dimensions: list[DimensionScore] = field(default_factory=list)
    total_score: float = 0.0
    adjusted_score: float = 0.0  # 附加规则调整后
    deductions: list[str] = field(default_factory=list)
    rank: int = 0


# ============================================================
# 风险偏好权重表
# ============================================================

RISK_PREFERENCE_WEIGHTS = {
    "保守": {"收益性": 0.15, "安全性": 0.40, "流动性": 0.20, "透明度": 0.15, "费率": 0.10},
    "稳健": {"收益性": 0.25, "安全性": 0.35, "流动性": 0.15, "透明度": 0.15, "费率": 0.10},
    "平衡": {"收益性": 0.30, "安全性": 0.25, "流动性": 0.20, "透明度": 0.15, "费率": 0.10},
    "进取": {"收益性": 0.40, "安全性": 0.20, "流动性": 0.15, "透明度": 0.15, "费率": 0.10},
    "激进": {"收益性": 0.50, "安全性": 0.15, "流动性": 0.10, "透明度": 0.15, "费率": 0.10},
}

# 违规承诺关键词（出现则安全性直接降至10分）
ILLEGAL_PROMISES = [
    "保本保息", "保息保本", "绝对安全", "零风险", "无风险",
    "保证收益", "稳赚不赔", "刚性兑付", "本息保障", "100%保本",
    "百分百保本", "不会亏损", "不可能亏损",
]


# ============================================================
# 评分引擎
# ============================================================

class ScoringEngine:
    """评分规则引擎"""

    def __init__(self, risk_preference: str = "稳健"):
        if risk_preference not in RISK_PREFERENCE_WEIGHTS:
            raise ValueError(f"未知风险偏好: {risk_preference}，可选: {list(RISK_PREFERENCE_WEIGHTS.keys())}")
        self.risk_preference = risk_preference
        self.weights = RISK_PREFERENCE_WEIGHTS[risk_preference]

    def score(self, profile: ProductProfile) -> ScoringResult:
        """对单个产品打分"""
        result = ScoringResult(product_name=profile.name)

        # 五维度打分
        dim_funcs = [
            ("收益性", self._score_return),
            ("安全性", self._score_safety),
            ("流动性", self._score_liquidity),
            ("透明度", self._score_transparency),
            ("费率", self._score_fee),
        ]

        total = 0.0
        for dim_name, func in dim_funcs:
            score, reason = func(profile)
            weight = self.weights[dim_name]
            weighted = score * weight
            total += weighted
            result.dimensions.append(DimensionScore(
                name=dim_name,
                score=round(score, 1),
                weight=weight,
                weighted=round(weighted, 2),
                reason=reason,
            ))

        result.total_score = round(total, 1)
        result.adjusted_score = result.total_score

        # 附加规则1：透明度≤30 总分扣10分
        transparency_dim = next(d for d in result.dimensions if d.name == "透明度")
        if transparency_dim.score <= 30:
            result.adjusted_score = round(result.adjusted_score - 10, 1)
            result.deductions.append("透明度过低（≤30分），总分扣10分")

        # 附加规则2：违规承诺检测（安全性已在_score_safety中处理，这里记录）
        if self._has_illegal_promise(profile):
            result.deductions.append("条款中含违规承诺表述，安全性已降至10分")

        # 确保分数不为负
        result.adjusted_score = max(0.0, result.adjusted_score)

        logger.info("产品[%s]评分: 总分%.1f (调整后%.1f) | 偏好=%s",
                    profile.name, result.total_score, result.adjusted_score, self.risk_preference)
        return result

    def score_all(self, profiles: list[ProductProfile]) -> list[ScoringResult]:
        """对多个产品打分并排序"""
        results = [self.score(p) for p in profiles]
        # 按调整后得分降序排列
        results.sort(key=lambda r: r.adjusted_score, reverse=True)
        for i, r in enumerate(results, 1):
            r.rank = i
        return results

    # ============================================================
    # 维度1：收益性
    # ============================================================
    def _score_return(self, p: ProductProfile) -> tuple[float, str]:
        """收益性评分：基于预期收益率"""
        rates = self._extract_rates(p.expected_return + " " + p.key_logic)

        if not rates:
            return 30.0, "未能识别明确收益率，给基础分30"

        # 取最高收益率作为收益性指标（代表潜在收益上限）
        max_rate = max(rates)
        rate_pct = max_rate * 100

        if rate_pct >= 15:
            score = 95
            reason = f"预期年化{rate_pct:.1f}%，收益潜力高"
        elif rate_pct >= 10:
            score = 82
            reason = f"预期年化{rate_pct:.1f}%，收益较好"
        elif rate_pct >= 5:
            score = 68
            reason = f"预期年化{rate_pct:.1f}%，收益中等"
        elif rate_pct >= 3:
            score = 52
            reason = f"预期年化{rate_pct:.1f}%，收益偏低"
        elif rate_pct >= 1:
            score = 35
            reason = f"预期年化{rate_pct:.1f}%，收益较低"
        else:
            score = 15
            reason = f"预期年化仅{rate_pct:.1f}%，收益很低"

        # 如果有0%情景（如雪球敲入），说明收益不确定性大，略降
        if len(rates) >= 2 and min(rates) == 0:
            score = max(score - 5, 10)
            reason += "（存在0%收益情景，扣5分）"

        return score, reason

    # ============================================================
    # 维度2：安全性
    # ============================================================
    def _score_safety(self, p: ProductProfile) -> tuple[float, str]:
        """安全性评分：基于本金保障、风险等级、违规承诺"""
        # 优先检测违规承诺
        if self._has_illegal_promise(p):
            return 10.0, "⚠️ 条款含'保本保息/绝对安全'等违规承诺，监管禁止此类表述，安全性直接降至10分"

        text = f"{p.principal_protection} {p.risk_level} {p.product_type} {p.key_logic}"

        # 本金保障判断
        if "不保本" in p.principal_protection or "可能亏损" in p.principal_protection:
            principal_safe = False
        elif "保本" in p.principal_protection:
            principal_safe = True
        else:
            principal_safe = None  # 未说明

        # 风险等级判断
        risk_score = None
        if "R1" in p.risk_level or "低风险" in p.risk_level:
            risk_score = 90
        elif "R2" in p.risk_level or "中低" in p.risk_level:
            risk_score = 75
        elif "R3" in p.risk_level or "中风险" in p.risk_level or "中等" in p.risk_level:
            risk_score = 58
        elif "R4" in p.risk_level or "中高" in p.risk_level:
            risk_score = 38
        elif "R5" in p.risk_level or "高风险" in p.risk_level:
            risk_score = 18

        # 产品类型辅助判断
        type_score = None
        if any(kw in p.product_type for kw in ["存款", "国债", "货币基金"]):
            type_score = 88
        elif any(kw in p.product_type for kw in ["结构性存款", "理财", "债券"]):
            type_score = 70
        elif any(kw in p.product_type for kw in ["雪球", "收益凭证", "信托"]):
            type_score = 45
        elif any(kw in p.product_type for kw in ["股票", "股票型", "混合", "期货", "期权"]):
            type_score = 25

        # 综合：取风险等级、产品类型、本金保障的综合判断
        scores = [s for s in [risk_score, type_score] if s is not None]
        if scores:
            base = sum(scores) / len(scores)
        else:
            base = 50  # 默认中性

        # 本金保障调整
        if principal_safe is True:
            base = min(base + 10, 95)
            reason_extra = "，本金有保障"
        elif principal_safe is False:
            base = max(base - 15, 5)
            reason_extra = "，不保本"
        else:
            reason_extra = "，本金保障未明确说明"

        # 高风险点数量调整
        if p.high_risk_count >= 3:
            base = max(base - 10, 5)
            reason_extra += f"，含{p.high_risk_count}个高风险点"

        score = round(base, 1)
        reason = f"风险等级{p.risk_level or '未说明'}/{p.product_type or '未分类'}{reason_extra}"
        return score, reason

    # ============================================================
    # 维度3：流动性
    # ============================================================
    def _score_liquidity(self, p: ProductProfile) -> tuple[float, str]:
        """流动性评分：基于是否可提前赎回"""
        text = p.early_redemption

        if "原文未说明" in text or not text or text == "未知":
            return 40.0, "未说明提前赎回规则，流动性不确定，给中性偏低分40"

        if any(kw in text for kw in ["随时", "T+0", "当日", "每日"]):
            if "不可" not in text and "不能" not in text:
                return 92.0, "支持随时赎回，流动性好"

        if any(kw in text for kw in ["T+1", "T+2", "次日", "下一个交易日"]):
            return 78.0, "支持T+1/T+2赎回，流动性较好"

        if any(kw in text for kw in ["封闭期", "锁定期", "持有满", "一定期限"]):
            if "后可" in text or "后可以" in text:
                return 55.0, "封闭期后可赎回，流动性一般"
            return 35.0, "有封闭期/锁定期，流动性较差"

        if any(kw in text for kw in ["不可", "不能", "无法", "不得", "提前终止"]):
            if "违约金" in text or "费用" in text or "罚息" in text:
                return 25.0, "提前赎回需支付违约金/罚息，流动性差"
            return 18.0, "不可提前赎回，流动性很差"

        if any(kw in text for kw in ["违约金", "罚息", "赎回费", "手续费"]):
            return 35.0, "提前赎回有费用，流动性一般"

        return 50.0, f"赎回规则: {text}，流动性中等"

    # ============================================================
    # 维度4：透明度
    # ============================================================
    def _score_transparency(self, p: ProductProfile) -> tuple[float, str]:
        """透明度评分：基于字段完整度和风险揭示充分性"""
        fields = [
            p.product_type, p.term, p.expected_return, p.risk_level,
            p.early_redemption, p.fee_structure, p.principal_protection,
        ]
        unknown_count = sum(1 for f in fields if "原文未说明" in f or not f or f == "未知")
        completeness = 1 - (unknown_count / len(fields))

        # 基础分：字段完整度
        if completeness >= 0.9:
            base = 88
        elif completeness >= 0.7:
            base = 70
        elif completeness >= 0.5:
            base = 50
        elif completeness >= 0.3:
            base = 30
        else:
            base = 15

        # 风险点数量调整：风险点多说明揭示充分（加分），但高风险点多说明产品复杂（减分）
        if p.risk_count >= 3:
            base = min(base + 5, 100)
        if p.high_risk_count >= 2:
            base = max(base - 8, 5)

        unknown_fields = []
        field_names = ["产品类型", "期限", "预期收益", "风险等级", "提前赎回", "费用", "本金保障"]
        for name, val in zip(field_names, fields):
            if "原文未说明" in val or not val or val == "未知":
                unknown_fields.append(name)

        reason = f"字段完整度{completeness:.0%}"
        if unknown_fields:
            reason += f"，未说明: {'、'.join(unknown_fields)}"
        if p.high_risk_count >= 2:
            reason += f"，含{p.high_risk_count}个高风险点"

        return round(base, 1), reason

    # ============================================================
    # 维度5：费率
    # ============================================================
    def _score_fee(self, p: ProductProfile) -> tuple[float, str]:
        """费率评分：基于综合费率"""
        text = p.fee_structure

        if "原文未说明" in text or not text or text == "未知":
            return 50.0, "未说明费率结构，给中性分50"

        if any(kw in text for kw in ["无费用", "无手续费", "0费率", "免费", "无额外费用"]):
            return 95.0, "无额外费用，费率优"

        # 提取费率数字
        rates = self._extract_rates(text)
        if rates:
            max_fee = max(rates) * 100  # 转为百分比
            if max_fee < 0.3:
                return 85.0, f"综合费率约{max_fee:.2f}%，费率低"
            elif max_fee < 0.8:
                return 70.0, f"综合费率约{max_fee:.2f}%，费率较低"
            elif max_fee < 1.5:
                return 52.0, f"综合费率约{max_fee:.2f}%，费率中等"
            elif max_fee < 2.5:
                return 35.0, f"综合费率约{max_fee:.2f}%，费率偏高"
            else:
                return 18.0, f"综合费率约{max_fee:.2f}%，费率高"

        # 关键词判断
        if any(kw in text for kw in ["管理费", "托管费", "销售服务费", "业绩报酬"]):
            items = len(re.findall(r"管理费|托管费|销售服务费|业绩报酬|申购费|赎回费", text))
            if items >= 3:
                return 40.0, f"涉及{items}项费用，费率结构较复杂"
            return 55.0, f"涉及{items}项费用，费率中等"

        return 55.0, f"费率: {text[:30]}"

    # ============================================================
    # 工具方法
    # ============================================================
    @staticmethod
    def _extract_rates(text: str) -> list[float]:
        """从文本中提取所有百分比数字（小数形式）"""
        rates = []
        for m in re.finditer(r"(\d+\.?\d*)\s*%", text):
            try:
                r = float(m.group(1)) / 100.0
                if 0 <= r <= 1.0:
                    rates.append(r)
            except ValueError:
                continue
        return sorted(set(rates), reverse=True)

    @staticmethod
    def _has_illegal_promise(p: ProductProfile) -> bool:
        """检测条款中是否有违规承诺"""
        text = f"{p.raw_text} {p.plain_language} {p.key_logic}"
        for kw in ILLEGAL_PROMISES:
            if kw in text:
                return True
        return False


# ============================================================
# 推荐理由生成（规则-based，不依赖LLM）
# ============================================================

def generate_recommendation(
    winner: ScoringResult,
    losers: list[ScoringResult],
    profiles: dict[str, ProductProfile],
    risk_preference: str,
) -> dict:
    """
    基于评分结果生成推荐理由和落选原因（规则引擎，不调用LLM）。

    Returns:
        {
            "winner_name": str,
            "winner_score": float,
            "reasons": list[str],          # 2-3条推荐理由
            "risk_warnings": list[str],    # 风险提示
            "loser_reasons": dict[str, list[str]],  # 每个落选产品的落选原因
            "disclaimer": str,
        }
    """
    winner_profile = profiles.get(winner.product_name, ProductProfile())
    reasons = []
    risk_warnings = []

    # 找出获胜产品的优势维度
    winner_dims = {d.name: d for d in winner.dimensions}

    # 收益性优势
    if winner_dims["收益性"].score >= 65:
        reasons.append(f"收益性得分{winner_dims['收益性'].score:.0f}，预期回报在同类产品中具有竞争力")
    elif winner_dims["安全性"].score >= 70:
        reasons.append(f"安全性得分{winner_dims['安全性'].score:.0f}，本金保障程度较高，适合{risk_preference}型投资者")

    # 安全性优势
    if winner_dims["安全性"].score >= 75:
        reasons.append(f"安全性得分{winner_dims['安全性'].score:.0f}，风险等级较低，本金相对安全")

    # 流动性优势
    if winner_dims["流动性"].score >= 70:
        reasons.append(f"流动性得分{winner_dims['流动性'].score:.0f}，资金灵活度较好")

    # 费率优势
    if winner_dims["费率"].score >= 70:
        reasons.append(f"费率得分{winner_dims['费率'].score:.0f}，持有成本较低")

    # 透明度
    if winner_dims["透明度"].score >= 70:
        reasons.append(f"透明度得分{winner_dims['透明度'].score:.0f}，条款信息披露较充分")

    # 确保至少2条理由
    if len(reasons) < 2:
        reasons.append(f"综合得分{winner.adjusted_score:.1f}，在对比产品中排名第一")
        reasons.append(f"适配{risk_preference}型风险偏好的权重配置")

    reasons = reasons[:3]

    # 风险提示
    if winner_dims["安全性"].score < 50:
        risk_warnings.append("该产品安全性得分较低，存在本金亏损风险，请谨慎评估")
    if winner_dims["流动性"].score < 40:
        risk_warnings.append("该产品流动性较差，资金可能被长期锁定")
    if winner_dims["透明度"].score <= 30:
        risk_warnings.append("该产品透明度低，关键信息披露不足，已在总分中扣减10分")
    if winner_profile.high_risk_count >= 2:
        risk_warnings.append(f"条款中识别出{winner_profile.high_risk_count}个高风险点，请仔细阅读")
    if not risk_warnings:
        risk_warnings.append("金融产品有风险，过往业绩不代表未来表现，请根据自身情况决策")

    # 落选原因
    loser_reasons = {}
    for loser in losers:
        loser_profile = profiles.get(loser.product_name, ProductProfile())
        loser_dims = {d.name: d for d in loser.dimensions}
        reasons_list = []

        # 对比获胜产品，找出明显劣势
        for dim_name in ["收益性", "安全性", "流动性", "透明度", "费率"]:
            diff = winner_dims[dim_name].score - loser_dims[dim_name].score
            if diff >= 15:
                reasons_list.append(f"{dim_name}落后{diff:.0f}分（{loser_dims[dim_name].score:.0f} vs {winner_dims[dim_name].score:.0f}）")

        if loser.deductions:
            reasons_list.extend(loser.deductions)

        if not reasons_list:
            reasons_list.append(f"综合得分{loser.adjusted_score:.1f}，低于获胜产品{winner.adjusted_score:.1f}")

        loser_reasons[loser.product_name] = reasons_list[:3]

    return {
        "winner_name": winner.product_name,
        "winner_score": winner.adjusted_score,
        "reasons": reasons,
        "risk_warnings": risk_warnings,
        "loser_reasons": loser_reasons,
        "disclaimer": "⚠️ 以上分析基于条款文本的规则化评分，仅供参考，不构成任何投资建议。金融产品有风险，投资需谨慎，请以官方合同和产品说明书为准。",
    }
