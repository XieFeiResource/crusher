"""验证阶段二提示词的 .replace() 修复"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.prompts import STAGE2_USER_PROMPT

logic = '每月第3个星期三观察敲出，若收盘价≥期初103%则提前终止；若曾跌破期初75%且未敲出，到期按期末价格结算。'

# 修复后：用 replace
try:
    result = STAGE2_USER_PROMPT.replace("{logic_summary}", logic)
    print("✅ .replace() 成功，提示词长度:", len(result))
    assert "每月第3个星期三" in result
    # Mermaid 示例的花括号应保持原样
    assert 'B{"观察日条件是否满足"}' in result
    print("✅ Mermaid 示例花括号保持原样")
except Exception as e:
    print("❌ .replace() 失败:", e)
    sys.exit(1)

# 修复前：用 format 会崩溃
try:
    STAGE2_USER_PROMPT.format(logic_summary=logic)
    print("⚠️ .format() 居然成功了")
except KeyError as e:
    print("❌ .format() 崩溃（复现bug）KeyError:", e)
except Exception as e:
    print("❌ .format() 崩溃:", type(e).__name__, e)

print("\n✅ 修复验证通过：使用 .replace() 后阶段二不再崩溃")
