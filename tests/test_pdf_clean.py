"""测试 PDF 文本清洗逻辑（无需真实PDF）"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.pdf_extractor import PdfExtractor


def test_line_break_fix():
    """测试中文断行修复（保留段落格式）"""
    print("=" * 60)
    print("🧪 测试：中文断行修复（保留段落格式）")
    print("=" * 60)

    # 模拟 PDF 提取的断行文本
    # 注意：连续非空行是同一段落（应合并），空行是段落分隔（应保留）
    raw = """本产品为结构性存款，期限90天，挂钩美元兑
日元汇率。观察期内若汇率始终位于区间内，
则到期年化收益率为4.80%。

若汇率突破区间，则仅获得活期利息。

第 1 页

本资料仅供参考，不构成投资建议"""

    extractor = PdfExtractor()
    cleaned = extractor._clean_text(raw, page_count=1)

    print("\n原始文本：")
    print(raw)
    print("\n清洗后：")
    print(cleaned)

    # 断言：连续非空行被合并（同一段落内的硬换行）
    assert "美元兑日元汇率" in cleaned, "同段落断行未合并"
    assert "区间内，则到期" in cleaned, "同段落断行未合并"
    # 页码被移除
    assert "第 1 页" not in cleaned, "页码未移除"
    # 页眉页脚被移除
    assert "本资料仅供参考" not in cleaned, "页眉页脚未移除"
    # 段落分隔保留（两个段落之间有空行）
    assert "\n\n" in cleaned, "段落分隔丢失"
    # 空行分隔的段落不被合并
    assert "4.80%。\n\n若汇率突破" in cleaned, "段落分隔被错误合并"
    print("\n✅ 断行修复测试通过（同段落合并，段落间保留空行）")
    return True


def test_english_space():
    """测试英文之间加空格"""
    print("\n" + "=" * 60)
    print("🧪 测试：英文空格处理")
    print("=" * 60)

    extractor = PdfExtractor()
    # 英文行之间应加空格
    lines = ["This is a financial", "product description", "with multiple lines."]
    merged = extractor._merge_paragraph_lines(lines)
    print(f"合并结果: {merged}")
    assert merged == "This is a financial product description with multiple lines."
    print("✅ 英文空格处理通过")
    return True


def test_mixed_cjk_english():
    """测试中英文混合"""
    print("\n" + "=" * 60)
    print("🧪 测试：中英文混合")
    print("=" * 60)

    extractor = PdfExtractor()
    # 中文接英文不需要空格
    lines = ["本产品挂钩USD/JPY", "汇率，期限90天"]
    merged = extractor._merge_paragraph_lines(lines)
    print(f"合并结果: {merged}")
    assert "USD/JPY汇率" in merged, "中英文之间不应有空格"
    print("✅ 中英文混合处理通过")
    return True


def test_page_number_removal():
    """测试页码移除"""
    print("\n" + "=" * 60)
    print("🧪 测试：页码移除")
    print("=" * 60)

    extractor = PdfExtractor()
    page_numbers = ["1", "第 3 页", "Page 5", "12/24", "- 10 -", "  7  "]
    for pn in page_numbers:
        assert extractor._is_page_number(pn), f"未识别为页码: {pn}"
        print(f"  ✅ 识别页码: '{pn}'")

    # 正文不应被误删
    assert not extractor._is_page_number("本产品为结构性存款")
    assert not extractor._is_page_number("收益率为4.80%")
    print("✅ 页码移除测试通过")
    return True


def test_needs_space():
    """测试空格判断逻辑"""
    print("\n" + "=" * 60)
    print("🧪 测试：空格判断逻辑")
    print("=" * 60)

    extractor = PdfExtractor()
    # 中文接中文 → 不需要
    assert not extractor._needs_space("产品", "期限")
    # 英文接英文 → 需要
    assert extractor._needs_space("financial", "product")
    # 中文接英文 → 不需要
    assert not extractor._needs_space("挂钩", "USD")
    # 英文接中文 → 不需要
    assert not extractor._needs_space("USD", "挂钩")
    # 数字接数字 → 需要
    assert extractor._needs_space("100", "200")
    print("✅ 空格判断逻辑通过")
    return True


def test_validation():
    """测试验证和置信度"""
    print("\n" + "=" * 60)
    print("🧪 测试：提取验证")
    print("=" * 60)

    from backend.pdf_extractor import PdfExtractResult
    extractor = PdfExtractor()

    # 正常文本
    r1 = PdfExtractResult(text="本产品为结构性存款，期限90天。" * 10, raw_text="x" * 500, page_count=2)
    r1 = extractor._validate(r1)
    print(f"正常文本: 置信度={r1.confidence}, 警告={r1.warnings}")
    assert r1.confidence > 0.8

    # 过短文本
    r2 = PdfExtractResult(text="短文本", raw_text="短文本", page_count=1)
    r2 = extractor._validate(r2)
    print(f"过短文本: 置信度={r2.confidence}, 警告={r2.warnings}")
    assert r2.confidence < 0.5

    print("✅ 验证逻辑通过")
    return True


if __name__ == "__main__":
    tests = [
        test_line_break_fix,
        test_english_space,
        test_mixed_cjk_english,
        test_page_number_removal,
        test_needs_space,
        test_validation,
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
