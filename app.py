"""
术语粉碎机 - Streamlit 前端主程序
金融条款 AI 解读工作台：白话翻译 + 参数卡片 + 流程图 + 风险高亮
"""
import json
import os
import sys

import streamlit as st
import streamlit.components.v1 as components

# 将项目根目录加入 path，便于导入 backend
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.config import LLMConfig, PROVIDER_DEFAULTS
from backend.pipeline import TermCrusherPipeline
from backend.prompts import STYLE_PRESETS
from backend.llm_client import setup_logging


# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="术语粉碎机 - 金融条款AI解读",
    page_icon="🔨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 自定义样式
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #1e3a5f, #2e7d32);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #666;
        font-size: 0.95rem;
        margin-bottom: 1.5rem;
    }
    .risk-high {
        background-color: #ffebee;
        border-left: 4px solid #c62828;
        padding: 8px 12px;
        border-radius: 4px;
        margin: 4px 0;
    }
    .risk-mid {
        background-color: #fff3e0;
        border-left: 4px solid #ef6c00;
        padding: 8px 12px;
        border-radius: 4px;
        margin: 4px 0;
    }
    .risk-low {
        background-color: #fffde7;
        border-left: 4px solid #f9a825;
        padding: 8px 12px;
        border-radius: 4px;
        margin: 4px 0;
    }
    .param-card {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 12px;
        text-align: center;
        border: 1px solid #e0e0e0;
    }
    .param-label {
        font-size: 0.8rem;
        color: #888;
        margin-bottom: 4px;
    }
    .param-value {
        font-size: 1rem;
        font-weight: 600;
        color: #1e3a5f;
    }
    .highlight-text {
        background: linear-gradient(transparent 60%, #ffd54f 60%);
        padding: 0 2px;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# 侧边栏：API 配置
# ============================================================
with st.sidebar:
    st.header("⚙️ 设置")

    # 尝试从环境变量读取
    env_api_key = os.getenv("LLM_API_KEY", "")
    env_provider = os.getenv("LLM_PROVIDER", "deepseek")

    provider = st.selectbox(
        "LLM 服务商",
        options=list(PROVIDER_DEFAULTS.keys()),
        index=list(PROVIDER_DEFAULTS.keys()).index(env_provider) if env_provider in PROVIDER_DEFAULTS else 0,
        help="选择你使用的大模型服务商",
    )

    default_model = PROVIDER_DEFAULTS[provider]["model"]
    model = st.text_input("模型名称", value=default_model)

    api_key = st.text_input(
        "API Key",
        value=env_api_key,
        type="password",
        placeholder="sk-...",
        help="填入你的 API Key，也可以在 .env 文件中配置 LLM_API_KEY",
    )

    base_url = st.text_input(
        "API 地址（可选）",
        value=PROVIDER_DEFAULTS[provider]["base_url"],
        help="一般不需要修改，使用自定义接口时填写",
    )

    temperature = st.slider("创意度 (temperature)", 0.0, 1.0, 0.3, 0.1,
                            help="越低越严谨，越高越活泼")

    verbose_log = st.checkbox("📋 打印详细日志到终端", value=False,
                              help="开启后，每次LLM调用的完整提示词和响应会打印到运行streamlit的终端窗口")

    st.divider()
    st.caption("💡 提示：API Key 仅在本次会话中使用，不会上传或保存。")


# ============================================================
# 加载示例条款
# ============================================================
EXAMPLES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "examples.json")

@st.cache_data
def load_examples():
    try:
        with open(EXAMPLES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


examples = load_examples()


# ============================================================
# 主界面
# ============================================================
st.markdown('<div class="main-header">🔨 术语粉碎机</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">粘贴金融条款，AI 一键翻译成大白话 + 流程图 + 风险高亮</div>', unsafe_allow_html=True)

# 示例条款快速选择
col_example, col_style, _ = st.columns([2, 1, 3])
with col_example:
    example_names = [e["name"] for e in examples] if examples else []
    selected_example = st.selectbox(
        "📋 加载示例条款",
        options=[""] + example_names,
        index=0,
        label_visibility="collapsed",
    )
with col_style:
    style = st.selectbox(
        "🎭 翻译风格",
        options=list(STYLE_PRESETS.keys()),
        index=0,
        label_visibility="collapsed",
    )

# 输入区
default_text = ""
if selected_example:
    for e in examples:
        if e["name"] == selected_example:
            default_text = e["text"]
            break

raw_text = st.text_area(
    "📄 粘贴金融条款文本",
    value=default_text,
    height=180,
    placeholder="在这里粘贴银行理财、保险、基金、借贷等金融产品的条款文本...",
    key="raw_text_input",
)

col_btn, col_clear = st.columns([1, 5])
with col_btn:
    run_button = st.button("🔨 开始粉碎术语", type="primary", use_container_width=True)
with col_clear:
    if st.button("🗑️ 清空", use_container_width=True):
        st.session_state.pop("raw_text_input", None)
        st.rerun()


# ============================================================
# 处理与展示
# ============================================================
def highlight_risks_in_text(text: str, risks: list) -> str:
    """将原文中的风险片段用 HTML 高亮标记"""
    if not risks:
        return text
    # 按片段长度降序排列，避免短片段被长片段包含时重复替换
    sorted_risks = sorted(risks, key=lambda r: len(r["snippet"]), reverse=True)
    highlighted = text
    for risk in sorted_risks:
        snippet = risk["snippet"]
        if snippet and snippet in highlighted:
            # 用占位符替换，避免重复高亮
            placeholder = f"@@RISK_{id(risk)}@@"
            highlighted = highlighted.replace(snippet, placeholder)
    # 替换占位符为高亮 HTML
    for risk in sorted_risks:
        placeholder = f"@@RISK_{id(risk)}@@"
        color_class = {
            "高": "background:#ffcdd2;border-bottom:2px solid #c62828;",
            "中": "background:#ffe0b2;border-bottom:2px solid #ef6c00;",
            "低": "background:#fff9c4;border-bottom:2px solid #f9a825;",
        }.get(risk["risk_level"], "background:#fff9c4;border-bottom:2px solid #f9a825;")
        highlighted = highlighted.replace(
            placeholder,
            f'<span style="{color_class}padding:1px 3px;border-radius:3px;" title="{risk["explanation"]}">{risk["snippet"]}</span>'
        )
    return highlighted


def render_mermaid(mermaid_code: str):
    """渲染 Mermaid 流程图"""
    html = f"""
    <div style="background:white;padding:20px;border-radius:8px;border:1px solid #e0e0e0;">
        <div class="mermaid">{mermaid_code}</div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            flowchart: {{ useMaxWidth: true, htmlLabels: true, curve: 'basis' }}
        }});
    </script>
    """
    components.html(html, height=450, scrolling=True)


def render_param_cards(translation: dict):
    """渲染关键参数卡片"""
    params = [
        ("产品类型", translation.get("product_type", "-")),
        ("投资期限", translation.get("term", "-")),
        ("预期收益", translation.get("expected_return", "-")),
        ("风险等级", translation.get("risk_level", "-")),
        ("本金保障", translation.get("principal_protection", "-")),
        ("提前赎回", translation.get("early_redemption", "-")),
        ("费用结构", translation.get("fee_structure", "-")),
    ]
    # 每行3个卡片
    for i in range(0, len(params), 3):
        cols = st.columns(3)
        for j in range(3):
            if i + j < len(params):
                label, value = params[i + j]
                with cols[j]:
                    st.markdown(f"""
                    <div class="param-card">
                        <div class="param-label">{label}</div>
                        <div class="param-value">{value}</div>
                    </div>
                    """, unsafe_allow_html=True)


if run_button:
    if not raw_text.strip():
        st.warning("⚠️ 请先粘贴或输入金融条款文本")
    elif not api_key.strip():
        st.error("❌ 请在左侧侧边栏填入 API Key，或在 .env 文件中配置 LLM_API_KEY")
    else:
        # 构建配置
        config = LLMConfig(
            api_key=api_key.strip(),
            provider=provider,
            model=model.strip() or default_model,
            base_url=base_url.strip(),
            temperature=temperature,
        )

        progress_bar = st.progress(0)
        status_text = st.empty()

        def progress_callback(stage: str, pct: float):
            progress_bar.progress(min(int(pct * 100), 100))
            status_text.text(f"⏳ {stage}")

        try:
            # 开启详细日志
            if verbose_log:
                setup_logging()

            pipeline = TermCrusherPipeline(config=config)
            result = pipeline.run(
                raw_text=raw_text,
                style=style,
                progress_callback=progress_callback,
            )

            progress_bar.empty()
            status_text.empty()
            st.success("✅ 术语粉碎完成！")

            translation = result["translation"]
            flowchart_code = result["flowchart"]
            risks = result["risks"]

            # ===== 输出区 =====
            st.divider()

            # 第一行：原文（高亮） + 白话解读
            col_left, col_right = st.columns([1, 1])

            with col_left:
                st.subheader("📄 原文（风险高亮）")
                if risks:
                    legend_html = """
                    <div style="margin-bottom:10px;font-size:0.8rem;">
                        <span style="background:#ffcdd2;padding:2px 6px;border-radius:3px;">高风险</span>
                        <span style="background:#ffe0b2;padding:2px 6px;border-radius:3px;margin-left:8px;">中风险</span>
                        <span style="background:#fff9c4;padding:2px 6px;border-radius:3px;margin-left:8px;">低风险</span>
                        <span style="color:#888;margin-left:8px;">（鼠标悬停查看说明）</span>
                    </div>
                    """
                    st.markdown(legend_html, unsafe_allow_html=True)
                    highlighted = highlight_risks_in_text(raw_text, risks)
                    st.markdown(
                        f'<div style="background:#fafafa;padding:15px;border-radius:8px;'
                        f'border:1px solid #e0e0e0;line-height:1.8;white-space:pre-wrap;">'
                        f'{highlighted}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.info("未识别到明显风险点（或该条款较为规范）")
                    st.markdown(
                        f'<div style="background:#fafafa;padding:15px;border-radius:8px;'
                        f'border:1px solid #e0e0e0;line-height:1.8;white-space:pre-wrap;">'
                        f'{raw_text}</div>',
                        unsafe_allow_html=True,
                    )

            with col_right:
                st.subheader("💡 大白话解读")
                st.markdown(
                    f'<div style="background:linear-gradient(135deg,#e3f2fd,#e8f5e9);'
                    f'padding:20px;border-radius:12px;border-left:5px solid #1e3a5f;'
                    f'font-size:1.05rem;line-height:1.8;">'
                    f'💬 {translation.get("plain_language", "（解析失败）")}</div>',
                    unsafe_allow_html=True,
                )

                st.subheader("📊 关键参数")
                render_param_cards(translation)

            # 第二行：风险点详情
            if risks:
                st.divider()
                st.subheader("⚠️ 风险点详解")
                for i, risk in enumerate(risks, 1):
                    level = risk["risk_level"]
                    css_class = {"高": "risk-high", "中": "risk-mid", "低": "risk-low"}.get(level, "risk-low")
                    level_emoji = {"高": "🔴", "中": "🟠", "低": "🟡"}.get(level, "🟡")
                    st.markdown(f"""
                    <div class="{css_class}">
                        <b>{level_emoji} 风险点 {i}（{level}风险）</b><br>
                        <b>原文：</b>"{risk['snippet']}"<br>
                        <b>解读：</b>{risk['explanation']}
                    </div>
                    """, unsafe_allow_html=True)

            # 第三行：流程图
            st.divider()
            st.subheader("📈 收益逻辑流程图")
            st.caption("绿色节点 = 赚钱/高收益路径 ｜ 红色节点 = 亏钱/低收益路径")
            render_mermaid(flowchart_code)

        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            st.error(f"❌ 处理失败：{e}")
            st.caption("请检查 API Key 是否正确、网络是否通畅，或尝试更换服务商/模型。")


# ============================================================
# 页脚
# ============================================================
st.divider()
st.caption(
    "🔨 术语粉碎机 v1.0 ｜ AI 创意大赛参赛作品 ｜ "
    "本工具仅供学习参考，不构成任何投资建议。金融产品有风险，投资需谨慎。"
)
