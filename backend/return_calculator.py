"""
收益试算模块
根据 AI 提取的产品参数，以指定本金（默认10万元）计算不同情景下的收益。
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("term_crusher.return_calc")


@dataclass
class ReturnScenario:
    """单个收益情景"""
    name: str           # 情景名称，如"高收益情景"
    annual_rate: float  # 年化收益率（小数，如0.048表示4.8%）
    rate_text: str      # 原始收益率描述
    profit: float       # 收益金额（元）
    total: float        # 到期总金额（本金+收益）
    is_principal_safe: bool = True  # 是否保本
    note: str = ""      # 补充说明


@dataclass
class ReturnCalculation:
    """收益试算结果"""
    principal: float                 # 本金
    term_days: int                   # 投资期限（天）
    term_text: str                   # 期限描述
    product_type: str                # 产品类型
    scenarios: list[ReturnScenario] = field(default_factory=list)
    can_calculate: bool = False      # 是否能计算
    reason: str = ""                 # 无法计算的原因


class ReturnCalculator:
    """收益计算器"""

    # 期限解析：中文 → 天数
    TERM_PATTERNS = [
        (re.compile(r"(\d+)\s*天"), lambda m: int(m.group(1))),
        (re.compile(r"(\d+)\s*个?月"), lambda m: int(m.group(1)) * 30),
        (re.compile(r"(\d+)\s*年"), lambda m: int(m.group(1)) * 365),
        (re.compile(r"(\d+)\s*周"), lambda m: int(m.group(1)) * 7),
    ]

    # 收益率提取正则（匹配 4.80%、20%、1.5%~5.2% 等）
    RATE_PATTERN = re.compile(r"(\d+\.?\d*)\s*%")

    def __init__(self, principal: float = 100000.0):
        self.principal = principal

    def calculate(self, translation: dict) -> ReturnCalculation:
        """
        根据翻译结果计算收益。

        Args:
            translation: 阶段一输出的翻译字典

        Returns:
            ReturnCalculation
        """
        result = ReturnCalculation(
            principal=self.principal,
            term_days=0,
            term_text=translation.get("term", "未知"),
            product_type=translation.get("product_type", "未知"),
        )

        # 1. 解析期限
        term_text = translation.get("term", "")
        result.term_days = self._parse_term(term_text)

        # 2. 收集所有收益率相关文本
        expected_return = translation.get("expected_return", "")
        key_logic = translation.get("key_logic", "")
        principal_protection = translation.get("principal_protection", "")

        all_text = f"{expected_return} {key_logic}"

        # 3. 判断是否保本
        is_safe = "不保本" not in principal_protection and "亏损" not in principal_protection

        # 4. 提取收益率并识别情景
        rates = self._extract_rates(all_text)

        if not rates:
            result.can_calculate = False
            result.reason = "未能从条款中识别出明确的年化收益率"
            return result

        if result.term_days == 0:
            result.can_calculate = False
            result.reason = "未能识别投资期限，无法计算收益"
            return result

        # 5. 根据收益率数量和产品类型生成情景
        result.scenarios = self._build_scenarios(
            rates=rates,
            product_type=result.product_type,
            term_days=result.term_days,
            is_safe=is_safe,
            key_logic=key_logic,
        )

        if result.scenarios:
            result.can_calculate = True

        return result

    def _parse_term(self, term_text: str) -> int:
        """解析期限为天数"""
        if not term_text or term_text == "原文未说明":
            return 0
        for pattern, converter in self.TERM_PATTERNS:
            match = pattern.search(term_text)
            if match:
                return converter(match)
        logger.debug("无法解析期限: %s", term_text)
        return 0

    def _extract_rates(self, text: str) -> list[float]:
        """从文本中提取所有年化收益率（小数形式）"""
        rates = []
        for match in self.RATE_PATTERN.finditer(text):
            rate = float(match.group(1)) / 100.0
            # 过滤不合理的收益率（>100% 可能是其他数字，0%保留为有效情景）
            if 0 <= rate <= 1.0:
                rates.append(rate)
        # 去重并降序排列
        rates = sorted(set(rates), reverse=True)
        logger.debug("提取到收益率: %s", [f"{r:.2%}" for r in rates])
        return rates

    def _build_scenarios(
        self,
        rates: list[float],
        product_type: str,
        term_days: int,
        is_safe: bool,
        key_logic: str,
    ) -> list[ReturnScenario]:
        """
        根据收益率和产品类型构建收益情景。
        """
        scenarios = []
        year_fraction = term_days / 365.0

        if len(rates) == 1:
            # 单一收益率
            rate = rates[0]
            profit = self.principal * rate * year_fraction
            scenarios.append(ReturnScenario(
                name="预期收益",
                annual_rate=rate,
                rate_text=f"{rate*100:.2f}%",
                profit=profit,
                total=self.principal + profit,
                is_principal_safe=is_safe,
            ))
        elif len(rates) >= 2:
            # 多个收益率，区分高低情景
            high_rate = rates[0]
            low_rate = rates[-1]

            # 根据 key_logic 判断情景名称
            if "敲出" in key_logic or "雪球" in product_type:
                high_name = "敲出/未敲入（最高收益）"
                low_name = "敲入未敲出（最低收益）"
            elif "区间" in key_logic or "突破" in key_logic:
                high_name = "汇率/价格在区间内（高收益）"
                low_name = "突破区间（低收益）"
            else:
                high_name = "最好情景"
                low_name = "最坏情景"

            # 高收益情景
            high_profit = self.principal * high_rate * year_fraction
            scenarios.append(ReturnScenario(
                name=high_name,
                annual_rate=high_rate,
                rate_text=f"{high_rate*100:.2f}%",
                profit=high_profit,
                total=self.principal + high_profit,
                is_principal_safe=is_safe,
            ))

            # 低收益情景
            low_profit = self.principal * low_rate * year_fraction
            scenarios.append(ReturnScenario(
                name=low_name,
                annual_rate=low_rate,
                rate_text=f"{low_rate*100:.2f}%",
                profit=low_profit,
                total=self.principal + low_profit,
                is_principal_safe=is_safe,
                note="若产品不保本，最坏情景可能亏损本金" if not is_safe else "",
            ))

            # 如果有中间收益率，也展示
            if len(rates) > 2:
                for mid_rate in rates[1:-1]:
                    mid_profit = self.principal * mid_rate * year_fraction
                    scenarios.append(ReturnScenario(
                        name=f"中间情景 ({mid_rate*100:.2f}%)",
                        annual_rate=mid_rate,
                        rate_text=f"{mid_rate*100:.2f}%",
                        profit=mid_profit,
                        total=self.principal + mid_profit,
                        is_principal_safe=is_safe,
                    ))

        return scenarios

    @staticmethod
    def format_money(amount: float) -> str:
        """格式化金额：100000 → 100,000.00"""
        return f"{amount:,.2f}"

    @staticmethod
    def format_rate(rate: float) -> str:
        """格式化收益率：0.048 → 4.80%"""
        return f"{rate*100:.2f}%"
