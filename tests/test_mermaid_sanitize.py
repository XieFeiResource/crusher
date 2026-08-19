"""
验证 Mermaid 清洗函数能处理雪球产品等复杂场景
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.flowchart import FlowchartGenerator


def test_snowball_mermaid():
    """模拟 LLM 为雪球产品生成的有问题的 Mermaid 代码"""
    print("=" * 60)
    print("🧪 测试：雪球产品 Mermaid 清洗（含 < > % 等特殊字符）")
    print("=" * 60)

    # 这是 LLM 可能生成的有问题的代码（含 < > ? \n）
    bad_mermaid = """flowchart TD
    A[买入雪球产品] --> B{每月观察日是否敲出?}
    B -->|收盘≥期初103%| C[提前终止,支付20%年化]
    B -->|未敲出| D{是否发生敲入}
    D -->|收盘<期初75%| E[曾敲入]
    D -->|从未敲入| F[到期支付20%年化]
    E --> G{到期价格≥期初?}
    G -->|是| H[返还本金]
    G -->|否| I[按跌幅亏损]
    style C fill:#e1f5e1,stroke:#2e7d32,color:#1b5e20
    style F fill:#e1f5e1,stroke:#2e7d32,color:#1b5e20
    style H fill:#e1f5e1,stroke:#2e7d32,color:#1b5e20
    style I fill:#ffe1e1,stroke:#c62828,color:#b71c1c"""

    print("\n❌ 清洗前（含 < > ?，会渲染失败）：")
    print(bad_mermaid)

    cleaned = FlowchartGenerator._sanitize(bad_mermaid)

    print("\n✅ 清洗后：")
    print(cleaned)

    # 断言
    assert "<" not in cleaned, "清洗后仍包含 <"
    assert "?" not in cleaned, "清洗后仍包含 ?"
    # > 只应出现在箭头 --> 中
    for line in cleaned.split("\n"):
        if ">" in line and "-->" not in line:
            # 检查是否有独立的 >（不在箭头中）
            import re
            standalone = re.findall(r"(?<!-)>", line)
            assert not standalone, f"行中存在独立的 >: {line}"

    assert "flowchart TD" in cleaned
    assert "期初103%" in cleaned or "期初103％" in cleaned
    assert "期初75%" in cleaned or "期初75％" in cleaned
    # 节点标签应该被双引号包裹
    assert '"买入雪球产品"' in cleaned
    assert '"提前终止' in cleaned
    # style 行应保持不变
    assert "style C fill:#e1f5e1" in cleaned

    print("\n✅ 所有断言通过！清洗后的代码可正常渲染。")
    return True


def test_simple_mermaid():
    """测试简单结构性存款场景"""
    print("\n" + "=" * 60)
    print("🧪 测试：结构性存款 Mermaid 清洗")
    print("=" * 60)

    bad = """flowchart TD
    A[买入产品] --> B{汇率是否在145-155区间?}
    B -->|是| C[年化收益4.80%]
    B -->|否| D[年化收益1.20%]
    style C fill:#e1f5e1,stroke:#2e7d32,color:#1b5e20
    style D fill:#ffe1e1,stroke:#c62828,color:#b71c1c"""

    cleaned = FlowchartGenerator._sanitize(bad)
    print("\n清洗后：")
    print(cleaned)

    assert "?" not in cleaned
    assert '"买入产品"' in cleaned
    assert "145-155" in cleaned
    assert "style C fill:#e1f5e1" in cleaned
    print("\n✅ 通过！")
    return True


def test_already_quoted():
    """测试已经用引号包裹的标签不会被重复包裹"""
    print("\n" + "=" * 60)
    print("🧪 测试：已引号包裹的标签不重复包裹")
    print("=" * 60)

    good = """flowchart TD
    A["买入产品"] --> B{"是否满足"}
    B -->|是| C["高收益"]
    style C fill:#e1f5e1"""

    cleaned = FlowchartGenerator._sanitize(good)
    print("\n清洗后：")
    print(cleaned)

    # 不应出现双引号嵌套 [""...""]
    assert '[""买入产品""]' not in cleaned
    assert '{""是否满足""}' not in cleaned
    assert '"买入产品"' in cleaned
    print("\n✅ 通过！")
    return True


if __name__ == "__main__":
    results = []
    for test in [test_snowball_mermaid, test_simple_mermaid, test_already_quoted]:
        try:
            ok = test()
            results.append((test.__name__, ok))
        except Exception as e:
            print(f"\n❌ {test.__name__} 失败: {e}")
            results.append((test.__name__, False))

    print("\n" + "=" * 60)
    print("🏁 测试汇总")
    print("=" * 60)
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")
    passed = sum(1 for _, ok in results if ok)
    print(f"\n通过: {passed}/{len(results)}")
    sys.exit(0 if passed == len(results) else 1)
