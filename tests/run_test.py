"""
术语粉碎机 - 测试用例运行脚本

用法：
  python tests/run_test.py                  # 运行所有测试用例（需要API Key）
  python tests/run_test.py --offline        # 仅运行离线逻辑验证（无需API Key）
  python tests/run_test.py --case case_id   # 运行指定用例
"""
import argparse
import json
import os
import sys

# 将项目根目录加入 path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from backend.config import load_config
from backend.flowchart import FlowchartGenerator
from backend.llm_client import LLMClient
from backend.pipeline import TermCrusherPipeline


TESTS_DIR = os.path.join(PROJECT_ROOT, "tests")


def load_test_cases(case_id=None):
    """加载测试用例"""
    cases = []
    for fname in os.listdir(TESTS_DIR):
        if fname.startswith("case_") and fname.endswith(".json"):
            fpath = os.path.join(TESTS_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                case = json.load(f)
            if case_id is None or case.get("case_id") == case_id:
                cases.append(case)
    return cases


# ============================================================
# 离线测试：验证 Mermaid 清洗逻辑（无需 API Key）
# ============================================================
def test_mermaid_sanitization():
    """验证流程图问号清洗逻辑"""
    print("=" * 60)
    print("🧪 离线测试：Mermaid 问号清洗")
    print("=" * 60)

    # 模拟之前导致失败的 Mermaid 代码
    bad_mermaid = """flowchart TD
    A[买入产品] --> B{观察日条件是否满足?}
    B -->|是| C[获得高收益4.80%?]
    B -->|否| D[仅获低收益1.20%]
    style C fill:#e1f5e1,stroke:#2e7d32,color:#1b5e20
    style D fill:#ffe1e1,stroke:#c62828,color:#b71c1c"""

    cleaned = FlowchartGenerator._sanitize(bad_mermaid)

    # 断言：不包含问号
    assert "?" not in cleaned, f"清洗后仍包含问号:\n{cleaned}"
    # 断言：保留核心内容
    assert "观察日条件是否满足" in cleaned
    assert "4.80" in cleaned
    assert "1.20" in cleaned
    assert "flowchart TD" in cleaned
    # 断言：样式保留
    assert "fill:#e1f5e1" in cleaned
    assert "fill:#ffe1e1" in cleaned

    print("✅ 问号清洗通过")
    print(f"\n清洗前（含?，会渲染失败）：")
    print(bad_mermaid)
    print(f"\n清洗后（无?，可正常渲染）：")
    print(cleaned)
    print()

    # 测试默认流程图也不含问号
    default = FlowchartGenerator._default_flowchart()
    assert "?" not in default, "默认流程图包含问号"
    print("✅ 默认流程图无问号")
    print()
    return True


def test_prompt_no_question_mark():
    """验证提示词示例中不含问号"""
    print("=" * 60)
    print("🧪 离线测试：提示词无问号")
    print("=" * 60)
    from backend.prompts import STAGE2_USER_PROMPT
    # 示例结构中不应该有 ?
    example_section = STAGE2_USER_PROMPT.split("示例结构")[1] if "示例结构" in STAGE2_USER_PROMPT else ""
    assert "?" not in example_section, "提示词示例中仍包含问号"
    assert "问号" in STAGE2_USER_PROMPT and "不要使用" in STAGE2_USER_PROMPT, "提示词缺少问号禁令"
    assert "小于号" in STAGE2_USER_PROMPT or "<" in STAGE2_USER_PROMPT, "提示词缺少小于号禁令"
    print("✅ 阶段二提示词已明确禁止 ? < > 等特殊字符，示例也已修正")
    print()
    return True


# ============================================================
# 在线测试：运行完整流水线（需要 API Key）
# ============================================================
def validate_translation(result, expected):
    """校验翻译结果"""
    errors = []
    trans = result.get("translation", {})

    # plain_language 包含关键词
    for kw in expected.get("plain_language_contains", []):
        if kw not in trans.get("plain_language", ""):
            errors.append(f"白话翻译缺少关键词: {kw}")

    # 精确匹配字段
    for field in ["product_type", "term", "early_redemption"]:
        if field in expected:
            actual = trans.get(field, "")
            exp = expected[field]
            if exp != "原文未说明" and exp not in actual and actual not in exp:
                errors.append(f"{field}: 期望包含'{exp}'，实际为'{actual}'")

    # 包含匹配字段
    for field in ["expected_return_contains", "risk_level_contains", "principal_protection_contains", "key_logic_contains"]:
        if field in expected:
            actual_field = field.replace("_contains", "")
            actual = trans.get(actual_field, "")
            for kw in expected[field]:
                if kw not in actual:
                    errors.append(f"{actual_field}: 期望包含'{kw}'，实际为'{actual}'")

    return errors


def validate_flowchart(result, expected):
    """校验流程图"""
    errors = []
    code = result.get("flowchart", "")

    for kw in expected.get("must_contain", []):
        if kw not in code:
            errors.append(f"流程图缺少: {kw}")

    for forbidden in expected.get("must_not_contain", []):
        if forbidden in code:
            errors.append(f"流程图包含禁用字符: {forbidden}")

    if expected.get("must_have_green_style") and "fill:#e1f5e1" not in code:
        errors.append("流程图缺少绿色节点样式")

    if expected.get("must_have_red_style") and "fill:#ffe1e1" not in code:
        errors.append("流程图缺少红色节点样式")

    return errors


def validate_risks(result, expected, raw_text):
    """校验风险识别"""
    errors = []
    risks = result.get("risks", [])

    if len(risks) < expected.get("min_count", 0):
        errors.append(f"风险点数量不足: 期望至少{expected['min_count']}个，实际{len(risks)}个")

    if expected.get("snippets_must_be_in_original"):
        for r in risks:
            snippet = r.get("snippet", "")
            if snippet and snippet not in raw_text:
                errors.append(f"风险片段不在原文中: {snippet[:30]}...")

    valid_levels = expected.get("risk_levels", [])
    for r in risks:
        level = r.get("risk_level", "")
        if level not in valid_levels:
            errors.append(f"无效风险等级: {level}")

    return errors


def run_online_test(case):
    """运行单个在线测试用例"""
    print(f"\n{'=' * 60}")
    print(f"🚀 在线测试: {case['case_name']} ({case['case_id']})")
    print("=" * 60)

    config = load_config()
    if not config.api_key:
        print("❌ 未配置 API Key，请设置环境变量 LLM_API_KEY 或在 .env 中配置")
        return False

    pipeline = TermCrusherPipeline(config=config)
    raw_text = case["input"]["raw_text"]
    style = case["input"].get("style", "通俗版")

    print(f"📝 输入文本（{len(raw_text)}字）:")
    print(raw_text[:200] + "..." if len(raw_text) > 200 else raw_text)
    print()

    def progress(stage, pct):
        print(f"  ⏳ {stage} ({int(pct*100)}%)")

    try:
        result = pipeline.run(raw_text, style=style, progress_callback=progress)
    except Exception as e:
        print(f"❌ 流水线执行失败: {e}")
        return False

    print("\n📊 结果校验:")
    all_errors = []

    # 校验翻译
    trans_errors = validate_translation(result, case.get("expected_translation", {}))
    if trans_errors:
        print("  ❌ 翻译校验:")
        for e in trans_errors:
            print(f"     - {e}")
        all_errors.extend(trans_errors)
    else:
        print("  ✅ 翻译校验通过")

    # 校验流程图
    flow_errors = validate_flowchart(result, case.get("expected_flowchart", {}))
    if flow_errors:
        print("  ❌ 流程图校验:")
        for e in flow_errors:
            print(f"     - {e}")
        all_errors.extend(flow_errors)
    else:
        print("  ✅ 流程图校验通过")

    # 校验风险
    risk_errors = validate_risks(result, case.get("expected_risks", {}), raw_text)
    if risk_errors:
        print("  ❌ 风险校验:")
        for e in risk_errors:
            print(f"     - {e}")
        all_errors.extend(risk_errors)
    else:
        print("  ✅ 风险校验通过")

    # 输出实际结果摘要
    print("\n📋 实际结果摘要:")
    trans = result.get("translation", {})
    print(f"  白话翻译: {trans.get('plain_language', 'N/A')[:80]}...")
    print(f"  产品类型: {trans.get('product_type', 'N/A')}")
    print(f"  期限: {trans.get('term', 'N/A')}")
    print(f"  预期收益: {trans.get('expected_return', 'N/A')}")
    print(f"  风险等级: {trans.get('risk_level', 'N/A')}")
    print(f"  本金保障: {trans.get('principal_protection', 'N/A')}")
    print(f"  风险点数: {len(result.get('risks', []))}")
    print(f"  流程图行数: {len(result.get('flowchart', '').splitlines())}")

    if result.get("risks"):
        print("\n  ⚠️  识别到的风险点:")
        for i, r in enumerate(result["risks"], 1):
            print(f"    {i}. [{r['risk_level']}] {r['snippet'][:40]}... → {r['explanation'][:50]}")

    passed = len(all_errors) == 0
    print(f"\n{'✅ 测试通过' if passed else '❌ 测试失败'} ({len(all_errors)} 个问题)")
    return passed


def main():
    parser = argparse.ArgumentParser(description="术语粉碎机测试运行器")
    parser.add_argument("--offline", action="store_true", help="仅运行离线测试（无需API Key）")
    parser.add_argument("--case", type=str, default=None, help="指定测试用例ID")
    parser.add_argument("--log", action="store_true", help="打印详细LLM调用日志（提示词+响应）")
    args = parser.parse_args()

    if args.log:
        from backend.llm_client import setup_logging
        setup_logging()

    print("🔨 术语粉碎机 - 测试运行器\n")

    # 始终运行离线测试
    offline_ok = True
    try:
        offline_ok = test_mermaid_sanitization() and test_prompt_no_question_mark()
    except AssertionError as e:
        print(f"❌ 离线测试断言失败: {e}")
        offline_ok = False
    except Exception as e:
        print(f"❌ 离线测试异常: {e}")
        offline_ok = False

    if args.offline:
        print("\n" + "=" * 60)
        print(f"🏁 离线测试{'全部通过' if offline_ok else '存在失败'}")
        print("=" * 60)
        sys.exit(0 if offline_ok else 1)

    # 在线测试
    cases = load_test_cases(args.case)
    if not cases:
        print("⚠️  未找到测试用例")
        sys.exit(1)

    print(f"\n📦 找到 {len(cases)} 个测试用例\n")

    results = []
    for case in cases:
        ok = run_online_test(case)
        results.append((case["case_id"], ok))

    print("\n" + "=" * 60)
    print("🏁 测试汇总")
    print("=" * 60)
    for cid, ok in results:
        print(f"  {'✅' if ok else '❌'} {cid}")
    passed = sum(1 for _, ok in results if ok)
    print(f"\n通过: {passed}/{len(results)}")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
