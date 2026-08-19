"""快速验证核心工具函数逻辑"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.llm_client import LLMClient

# 测试 JSON 解析（带代码块）
test1 = 'Some text\n```json\n{"a": 1, "b": "hello"}\n```\nmore text'
r1 = LLMClient._parse_json(test1)
assert r1 == {"a": 1, "b": "hello"}, f"Failed: {r1}"
print("JSON parse (code block): OK")

# 测试 JSON 数组解析
test2 = '[{"snippet": "test", "risk_level": "高"}]'
r2 = LLMClient._parse_json(test2)
assert isinstance(r2, list) and len(r2) == 1
print("JSON parse (array): OK")

# 测试 Mermaid 提取
test3 = "Here is the chart:\n```mermaid\nflowchart TD\n    A-->B\n```"
r3 = LLMClient.extract_mermaid(test3)
assert "flowchart TD" in r3 and "A-->B" in r3
print("Mermaid extract: OK")

# 测试示例数据加载
with open(os.path.join(os.path.dirname(__file__), "data", "examples.json"), "r", encoding="utf-8") as f:
    examples = json.load(f)
assert len(examples) == 5
print(f"Examples loaded: {len(examples)} cases OK")

# 测试配置加载
from backend.config import load_config, PROVIDER_DEFAULTS
cfg = load_config()
assert cfg.provider in PROVIDER_DEFAULTS
print(f"Config load OK (provider={cfg.provider}, model={cfg.model})")

# 测试提示词格式化
from backend.prompts import STAGE1_USER_PROMPT, STAGE2_USER_PROMPT, STAGE3_USER_PROMPT
p1 = STAGE1_USER_PROMPT.format(raw_text="测试条款")
assert "测试条款" in p1
print("Prompt format OK")

print("\n=== ALL LOGIC TESTS PASSED ===")
