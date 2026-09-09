"""评分规则引擎单元测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.scoring_engine import (
    ProductProfile,
    ScoringEngine,
    RISK_PREFERENCE_WEIGHTS,
    ILLEGAL_PROMISES,
    generate_recommendation,
)


def test_weights_sum_to_one():
    """测试所有风险偏好权重合计为1"""
    print("=" * 60)
    print("🧪 测试：风险偏好权重合计为1")
    print("=" * 60)
    for pref, weights in RISK_PREFERENCE_WEIGHTS.items():
        total = sum(weights.values())
        print(f"  {pref}: {total:.2f}")
        assert abs(total - 1.0) < 0.001, f"{pref}权重合计{total}≠1"
    print("✅ 所有权重合计为1")
    return True


def test_conservative_deposit():
    """测试保守型偏好下，保本存款应得高分"""
    print("\n" + "=" * 60)
    print("🧪 测试：保守型偏好 - 保本存款")
    print("=" * 60)

    engine = ScoringEngine(risk_preference="保守")
    profile = ProductProfile(
        name="定期存款",
        product_type="定期存款",
        term="1年",
        expected_return="年化2.5%",
        risk_level="R1低风险",
        early_redemption="可提前支取，按活期计息",
        fee_structure="无额外费用",
        principal_protection="保本保息",
        key_logic="到期获2.5%年化收益",
    )
    result = engine.score(profile)
    print(f"  总分: {result.total_score} (调整后: {result.adjusted_score})")
    for d in result.dimensions:
        print(f"    {d.name}: {d.score} × {d.weight} = {d.weighted} | {d.reason}")

    # 保守型下，存款安全性权重高(0.4)，应该得分较高
    safety = next(d for d in result.dimensions if d.name == "安全性")
    assert safety.score >= 80, f"存款安全性应≥80，实际{safety.score}"
    assert result.adjusted_score > 60, f"保守型存款总分应>60，实际{result.adjusted_score}"
    print("✅ 保守型存款测试通过")
    return True


def test_aggressive_snowball():
    """测试激进型偏好下，雪球产品收益性权重高"""
    print("\n" + "=" * 60)
    print("🧪 测试：激进型偏好 - 雪球产品")
    print("=" * 60)

    engine = ScoringEngine(risk_preference="激进")
    profile = ProductProfile(
        name="雪球收益凭证",
        product_type="收益凭证（雪球结构）",
        term="24个月",
        expected_return="最高年化20%，可能为0%或亏损",
        risk_level="R4中高风险",
        early_redemption="不可主动赎回，触发敲出提前终止",
        fee_structure="无额外费用",
        principal_protection="不保本",
        key_logic="敲出获20%年化，敲入未敲出到期0%或亏损",
        high_risk_count=2,
        risk_count=4,
    )
    result = engine.score(profile)
    print(f"  总分: {result.total_score} (调整后: {result.adjusted_score})")
    for d in result.dimensions:
        print(f"    {d.name}: {d.score} × {d.weight} = {d.weighted} | {d.reason}")

    # 激进型收益性权重0.5，雪球20%收益应得高分
    ret = next(d for d in result.dimensions if d.name == "收益性")
    assert ret.score >= 80, f"雪球收益性应≥80，实际{ret.score}"
    # 安全性应该低
    safety = next(d for d in result.dimensions if d.name == "安全性")
    assert safety.score < 50, f"雪球安全性应<50，实际{safety.score}"
    print("✅ 激进型雪球测试通过")
    return True


def test_illegal_promise_penalty():
    """测试违规承诺：安全性直接降至10分"""
    print("\n" + "=" * 60)
    print("🧪 测试：违规承诺惩罚")
    print("=" * 60)

    engine = ScoringEngine(risk_preference="稳健")
    profile = ProductProfile(
        name="违规产品",
        product_type="理财产品",
        term="1年",
        expected_return="年化8%",
        risk_level="R2中低风险",
        early_redemption="不可赎回",
        fee_structure="无费用",
        principal_protection="保本保息，绝对安全",
        key_logic="保本保息，绝对安全，稳赚不赔",
        raw_text="本产品保本保息，绝对安全，零风险，稳赚不赔",
    )
    result = engine.score(profile)
    safety = next(d for d in result.dimensions if d.name == "安全性")
    print(f"  安全性得分: {safety.score}")
    print(f"  原因: {safety.reason}")
    assert safety.score == 10.0, f"违规承诺安全性应=10，实际{safety.score}"
    assert any("违规承诺" in d for d in result.deductions), "应记录违规承诺扣分"
    print("✅ 违规承诺惩罚测试通过")
    return True


def test_low_transparency_deduction():
    """测试透明度≤30时总分扣10分"""
    print("\n" + "=" * 60)
    print("🧪 测试：低透明度扣分")
    print("=" * 60)

    engine = ScoringEngine(risk_preference="稳健")
    profile = ProductProfile(
        name="模糊产品",
        product_type="",  # 未说明
        term="",
        expected_return="",
        risk_level="",
        early_redemption="",
        fee_structure="",
        principal_protection="",
        key_logic="收益不固定",
    )
    result = engine.score(profile)
    transparency = next(d for d in result.dimensions if d.name == "透明度")
    print(f"  透明度得分: {transparency.score}")
    print(f"  总分: {result.total_score} → 调整后: {result.adjusted_score}")
    print(f"  扣分记录: {result.deductions}")
    assert transparency.score <= 30, f"全字段缺失透明度应≤30，实际{transparency.score}"
    assert abs(result.adjusted_score - (result.total_score - 10)) < 0.01, "透明度≤30应扣10分"
    print("✅ 低透明度扣分测试通过")
    return True


def test_ranking_order():
    """测试多产品排序：保守型下存款应排名第一"""
    print("\n" + "=" * 60)
    print("🧪 测试：多产品排序")
    print("=" * 60)

    engine = ScoringEngine(risk_preference="保守")
    profiles = [
        ProductProfile(
            name="定期存款",
            product_type="定期存款", term="1年", expected_return="年化2.5%",
            risk_level="R1低风险", early_redemption="可提前支取",
            fee_structure="无费用", principal_protection="保本保息",
        ),
        ProductProfile(
            name="雪球产品",
            product_type="收益凭证", term="24个月", expected_return="最高20%",
            risk_level="R4中高风险", early_redemption="不可赎回",
            fee_structure="无费用", principal_protection="不保本",
            high_risk_count=2,
        ),
    ]
    results = engine.score_all(profiles)
    for r in results:
        print(f"  第{r.rank}名: {r.product_name} - {r.adjusted_score}分")

    assert results[0].product_name == "定期存款", "保守型下存款应排第一"
    assert results[0].rank == 1
    assert results[1].rank == 2
    print("✅ 排序测试通过")
    return True


def test_recommendation_generation():
    """测试推荐理由生成"""
    print("\n" + "=" * 60)
    print("🧪 测试：推荐理由生成")
    print("=" * 60)

    engine = ScoringEngine(risk_preference="稳健")
    profiles = [
        ProductProfile(name="产品A", product_type="结构性存款", term="90天",
                       expected_return="4.8%", risk_level="R2", early_redemption="不可赎回",
                       fee_structure="无费用", principal_protection="保本"),
        ProductProfile(name="产品B", product_type="股票基金", term="无固定期限",
                       expected_return="不保证", risk_level="R4", early_redemption="T+1赎回",
                       fee_structure="管理费1.5%", principal_protection="不保本",
                       high_risk_count=3),
    ]
    results = engine.score_all(profiles)
    profiles_dict = {p.name: p for p in profiles}

    rec = generate_recommendation(
        winner=results[0],
        losers=results[1:],
        profiles=profiles_dict,
        risk_preference="稳健",
    )

    print(f"  推荐: {rec['winner_name']} ({rec['winner_score']}分)")
    print(f"  理由: {rec['reasons']}")
    print(f"  风险提示: {rec['risk_warnings']}")
    print(f"  落选原因: {rec['loser_reasons']}")
    print(f"  免责: {rec['disclaimer'][:30]}...")

    assert rec["winner_name"] == results[0].product_name
    assert len(rec["reasons"]) >= 2, "至少2条推荐理由"
    assert len(rec["risk_warnings"]) >= 1
    assert "disclaimer" in rec
    assert "投资建议" in rec["disclaimer"]
    print("✅ 推荐理由生成测试通过")
    return True


def test_structured_deposit_scoring():
    """测试结构性存款（用户常用测试用例）"""
    print("\n" + "=" * 60)
    print("🧪 测试：结构性存款评分")
    print("=" * 60)

    engine = ScoringEngine(risk_preference="稳健")
    profile = ProductProfile(
        name="结构性存款A",
        product_type="结构性存款",
        term="90天",
        expected_return="汇率在区间内4.80%/年，突破区间1.20%/年",
        risk_level="R2中低风险",
        early_redemption="不可提前赎回",
        fee_structure="无额外费用",
        principal_protection="保本",
        key_logic="汇率在145-155区间内获4.80%，突破区间获1.20%",
    )
    result = engine.score(profile)
    print(f"  总分: {result.total_score} (调整后: {result.adjusted_score})")
    for d in result.dimensions:
        print(f"    {d.name}: {d.score} | {d.reason}")

    # 结构性存款保本，安全性应较高
    safety = next(d for d in result.dimensions if d.name == "安全性")
    assert safety.score >= 65, f"保本结构性存款安全性应≥65，实际{safety.score}"
    # 有4.8%收益，收益性应中等偏上
    ret = next(d for d in result.dimensions if d.name == "收益性")
    assert ret.score >= 50, f"4.8%收益性应≥50，实际{ret.score}"
    print("✅ 结构性存款评分测试通过")
    return True


if __name__ == "__main__":
    tests = [
        test_weights_sum_to_one,
        test_conservative_deposit,
        test_aggressive_snowball,
        test_illegal_promise_penalty,
        test_low_transparency_deduction,
        test_ranking_order,
        test_recommendation_generation,
        test_structured_deposit_scoring,
    ]
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
