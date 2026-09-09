"""测试收益计算器"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.return_calculator import ReturnCalculator


def test_structured_deposit():
    """测试结构性存款"""
    print("=" * 60)
    print("🧪 测试：结构性存款（汇率挂钩）")
    print("=" * 60)

    calc = ReturnCalculator(principal=100000)
    translation = {
        "product_type": "结构性存款",
        "term": "90天",
        "expected_return": "汇率在区间内4.80%/年，突破区间1.20%/年",
        "principal_protection": "保本",
        "key_logic": "汇率在145-155区间内获4.80%，突破区间获1.20%",
    }
    result = calc.calculate(translation)

    print(f"产品: {result.product_type}")
    print(f"期限: {result.term_text} ({result.term_days}天)")
    print(f"本金: {calc.format_money(result.principal)}元")
    print(f"可计算: {result.can_calculate}")
    for s in result.scenarios:
        print(f"  {s.name}: 年化{s.rate_text} → 收益{calc.format_money(s.profit)}元, 到期{calc.format_money(s.total)}元")

    assert result.can_calculate
    assert len(result.scenarios) == 2
    assert abs(result.scenarios[0].annual_rate - 0.048) < 0.001
    assert abs(result.scenarios[1].annual_rate - 0.012) < 0.001
    # 10万 * 4.8% * 90/365 ≈ 1183.56
    assert 1100 < result.scenarios[0].profit < 1300
    print("✅ 结构性存款测试通过")
    return True


def test_snowball():
    """测试雪球产品"""
    print("\n" + "=" * 60)
    print("🧪 测试：雪球产品")
    print("=" * 60)

    calc = ReturnCalculator(principal=100000)
    translation = {
        "product_type": "收益凭证（雪球结构）",
        "term": "24个月",
        "expected_return": "最高年化20%，可能为0%或亏损",
        "principal_protection": "不保本",
        "key_logic": "敲出获20%年化，未敲入获20%，敲入未敲出到期0%或亏损",
    }
    result = calc.calculate(translation)

    print(f"产品: {result.product_type}")
    print(f"期限: {result.term_text} ({result.term_days}天)")
    print(f"可计算: {result.can_calculate}")
    for s in result.scenarios:
        print(f"  {s.name}: 年化{s.rate_text} → 收益{calc.format_money(s.profit)}元, 到期{calc.format_money(s.total)}元")

    assert result.can_calculate
    assert result.term_days == 720  # 24个月 * 30
    assert len(result.scenarios) >= 2
    print("✅ 雪球产品测试通过")
    return True


def test_single_rate():
    """测试单一收益率产品"""
    print("\n" + "=" * 60)
    print("🧪 测试：单一收益率（定期存款）")
    print("=" * 60)

    calc = ReturnCalculator(principal=100000)
    translation = {
        "product_type": "定期存款",
        "term": "1年",
        "expected_return": "年化2.5%",
        "principal_protection": "保本",
        "key_logic": "到期获2.5%年化收益",
    }
    result = calc.calculate(translation)

    print(f"期限: {result.term_days}天")
    for s in result.scenarios:
        print(f"  {s.name}: 年化{s.rate_text} → 收益{calc.format_money(s.profit)}元")

    assert result.can_calculate
    assert result.term_days == 365
    assert len(result.scenarios) == 1
    assert abs(result.scenarios[0].profit - 2500) < 1
    print("✅ 单一收益率测试通过")
    return True


def test_cannot_calculate():
    """测试无法计算的情况"""
    print("\n" + "=" * 60)
    print("🧪 测试：无法计算（无收益率）")
    print("=" * 60)

    calc = ReturnCalculator(principal=100000)
    translation = {
        "product_type": "基金",
        "term": "无固定期限",
        "expected_return": "不保证收益",
        "principal_protection": "不保本",
        "key_logic": "随市场波动",
    }
    result = calc.calculate(translation)
    print(f"可计算: {result.can_calculate}")
    print(f"原因: {result.reason}")
    assert not result.can_calculate
    print("✅ 无法计算测试通过")
    return True


if __name__ == "__main__":
    tests = [test_structured_deposit, test_snowball, test_single_rate, test_cannot_calculate]
    results = []
    for test in tests:
        try:
            ok = test()
            results.append((test.__name__, ok))
        except Exception as e:
            print(f"\n❌ {test.__name__} 失败: {e}")
            import traceback
            traceback.print_exc()
            results.append((test.__name__, False))

    print("\n" + "=" * 60)
    print("🏁 测试汇总")
    print("=" * 60)
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")
    passed = sum(1 for _, ok in results if ok)
    print(f"\n通过: {passed}/{len(results)}")
    sys.exit(0 if passed == len(results) else 1)
