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
from backend.pdf_extractor import PdfExtractor
from backend.return_calculator import ReturnCalculator


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
st.markdown('<div class="sub-header">上传PDF或粘贴金融条款，AI 一键翻译成大白话 + 流程图 + 风险高亮</div>', unsafe_allow_html=True)

# ============================================================
# 模式切换：单条解读 / 条款对比
# ============================================================
tab_single, tab_compare = st.tabs(["📝 单条解读", "⚖️ 条款对比+智能择优"])

with tab_single:

    # 示例条款快速选择（on_change 回调直接设置 text_area 的 session_state）
    def _on_example_change():
        selected = st.session_state.get("example_selector", "")
        if selected:
            for e in examples:
                if e["name"] == selected:
                    st.session_state["raw_text_input"] = e["text"]
                    break

    col_example, col_style, _ = st.columns([2, 1, 3])
    with col_example:
        example_names = [e["name"] for e in examples] if examples else []
        selected_example = st.selectbox(
            "📋 加载示例条款",
            options=[""] + example_names,
            index=0,
            label_visibility="collapsed",
            key="example_selector",
            on_change=_on_example_change,
        )
    with col_style:
        style = st.selectbox(
            "🎭 翻译风格",
            options=list(STYLE_PRESETS.keys()),
            index=0,
            label_visibility="collapsed",
        )

    # PDF 上传区
    pdf_col1, pdf_col2 = st.columns([3, 1])
    with pdf_col1:
        uploaded_file = st.file_uploader(
            "📁 上传 PDF 文件（产品说明书/合同），自动提取文字",
            type=["pdf"],
            key="pdf_uploader",
            help="支持文字型PDF；扫描件/图片PDF可能无法提取文字",
        )

    # 处理 PDF 上传
    pdf_extractor = PdfExtractor()
    if uploaded_file is not None:
        # 只在新文件上传时提取（避免每次 rerun 都重复提取）
        if st.session_state.get("_pdf_filename") != uploaded_file.name:
            with st.spinner("正在读取 PDF 并提取文字..."):
                pdf_bytes = uploaded_file.read()
                result = pdf_extractor.extract(pdf_bytes)

            if result.success and result.text.strip():
                # 直接设置 text_area 绑定的 session_state，这是唯一能更新 widget 值的方式
                st.session_state["raw_text_input"] = result.text
                st.session_state["_pdf_filename"] = uploaded_file.name
                st.session_state["_pdf_info"] = {
                    "page_count": result.page_count,
                    "char_count": result.char_count,
                    "confidence": result.confidence,
                    "warnings": result.warnings,
                }
                st.rerun()
            else:
                st.error("❌ PDF 提取失败：" + (result.warnings[0] if result.warnings else "未提取到文字"))
                if result.warnings:
                    for w in result.warnings[1:]:
                        st.warning(f"⚠️ {w}")
        else:
            # 同一文件已提取过，显示之前的信息
            info = st.session_state.get("_pdf_info", {})
            if info:
                conf = info.get("confidence", 1.0)
                conf_color = "🟢" if conf >= 0.7 else ("🟡" if conf >= 0.4 else "🔴")
                st.success(
                    f"✅ PDF 提取完成 | {info.get('page_count', '?')}页 | "
                    f"{info.get('char_count', '?')}字 | 置信度 {conf_color} {conf:.0%}"
                )
                for w in info.get("warnings", []):
                    st.warning(f"⚠️ {w}")

    # 文本输入框（通过 key 绑定 session_state，无需 value 参数）
    raw_text = st.text_area(
        "📄 金融条款文本（可编辑）",
        height=200,
        placeholder="在这里粘贴银行理财、保险、基金、借贷等金融产品的条款文本，或上传 PDF 文件自动提取...",
        key="raw_text_input",
    )

    col_btn, col_clear = st.columns([1, 5])
    with col_btn:
        run_button = st.button("🔨 开始粉碎术语", type="primary", use_container_width=True)
    with col_clear:
        if st.button("🗑️ 清空", use_container_width=True):
            for key in ["raw_text_input", "_pdf_filename", "_pdf_info", "pdf_text", "example_selector"]:
                st.session_state.pop(key, None)
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

                # 收益试算（10万元本金）
                st.divider()
                st.subheader("💰 收益试算（以10万元本金为例）")
                calc = ReturnCalculator(principal=100000)
                calc_result = calc.calculate(translation)
                if calc_result.can_calculate and calc_result.scenarios:
                    st.caption(f"产品：{calc_result.product_type} ｜ 期限：{calc_result.term_text} ｜ 本金：100,000.00元")
                    # 每个情景一个卡片
                    cols = st.columns(len(calc_result.scenarios))
                    for idx, scenario in enumerate(calc_result.scenarios):
                        with cols[idx]:
                            is_high = idx == 0
                            bg_color = "#e8f5e9" if is_high else "#fff3e0"
                            border_color = "#2e7d32" if is_high else "#ef6c00"
                            st.markdown(f"""
                            <div style="background:{bg_color};border-radius:10px;padding:15px;border-left:4px solid {border_color};">
                                <div style="font-size:0.85rem;color:#666;margin-bottom:4px;">{scenario.name}</div>
                                <div style="font-size:1.3rem;font-weight:700;color:#1a1a1a;">{scenario.rate_text}</div>
                                <div style="font-size:0.8rem;color:#888;margin-top:8px;">年化收益率</div>
                                <div style="height:1px;background:#ddd;margin:10px 0;"></div>
                                <div style="font-size:0.85rem;color:#555;">到期收益</div>
                                <div style="font-size:1.15rem;font-weight:600;color:{'#2e7d32' if scenario.profit >= 0 else '#c62828'};">
                                    +{calc.format_money(scenario.profit)} 元
                                </div>
                                <div style="font-size:0.85rem;color:#555;margin-top:6px;">到期总金额</div>
                                <div style="font-size:1rem;font-weight:600;color:#1a1a1a;">
                                    {calc.format_money(scenario.total)} 元
                                </div>
                                {'<div style="font-size:0.75rem;color:#c62828;margin-top:8px;">⚠️ ' + scenario.note + '</div>' if scenario.note else ''}
                            </div>
                            """, unsafe_allow_html=True)
                    st.caption("💡 以上为单利估算（本金×年化收益率×期限/365），实际收益以产品合同为准。")
                else:
                    st.info(f"ℹ️ {calc_result.reason or '该产品收益不固定，无法进行简单试算。'}")

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




with tab_compare:
    st.markdown('<div class="sub-header">同时粘贴2-4款产品条款，AI自动对比并推荐最优选择</div>', unsafe_allow_html=True)

    # ---- 风险偏好选择 ----
    col_pref, col_count = st.columns([2, 1])
    with col_pref:
        risk_pref = st.selectbox(
            "🎯 你的风险偏好",
            options=["保守", "稳健", "平衡", "进取", "激进"],
            index=1,
            help="保守=追求本金安全 | 稳健=安全与收益平衡 | 激进=追求高收益",
        )
    with col_count:
        product_count = st.selectbox(
            "📦 对比产品数",
            options=[2, 3, 4],
            index=0,
        )

    st.divider()

    # ---- 多产品输入区 ----
    default_names = ["产品A", "产品B", "产品C", "产品D"]
    product_inputs = []
    pdf_extractor = PdfExtractor()

    def _on_compare_pdf_upload(idx):
        """PDF上传回调：提取文字并填入对应产品文本框（回调在widget实例化前执行，可安全改session_state）"""
        uploaded = st.session_state.get(f"compare_pdf_{idx}")
        if uploaded is not None:
            try:
                pdf_bytes = uploaded.read()
                pdf_result = pdf_extractor.extract(pdf_bytes)
                if pdf_result.success and pdf_result.text.strip():
                    st.session_state[f"compare_text_{idx}"] = pdf_result.text
                    st.session_state[f"_compare_pdf_name_{idx}"] = uploaded.name
                    st.session_state[f"_compare_pdf_info_{idx}"] = {
                        "page_count": pdf_result.page_count,
                        "char_count": pdf_result.char_count,
                        "confidence": pdf_result.confidence,
                        "warnings": pdf_result.warnings,
                    }
                    st.session_state[f"_compare_pdf_error_{idx}"] = ""
                else:
                    st.session_state[f"_compare_pdf_error_{idx}"] = (
                        "❌ PDF提取失败：" + (pdf_result.warnings[0] if pdf_result.warnings else "未提取到文字")
                    )
            except Exception as e:
                st.session_state[f"_compare_pdf_error_{idx}"] = f"❌ PDF读取失败：{e}"

    for i in range(product_count):
        with st.expander(f"📄 {default_names[i]}（点击展开/收起）", expanded=True):
            name_col, text_col = st.columns([1, 5])
            with name_col:
                p_name = st.text_input(
                    "产品名称",
                    value=default_names[i],
                    key=f"compare_name_{i}",
                    label_visibility="collapsed",
                )
            with text_col:
                p_text = st.text_area(
                    f"粘贴{default_names[i]}条款",
                    height=120,
                    placeholder=f"粘贴{default_names[i]}的金融条款文本，或上传PDF自动提取...",
                    key=f"compare_text_{i}",
                    label_visibility="collapsed",
                )

            # PDF 上传（每个产品独立，用回调处理提取）
            pdf_col, info_col = st.columns([2, 3])
            with pdf_col:
                st.file_uploader(
                    f"📁 上传{default_names[i]}的PDF",
                    type=["pdf"],
                    key=f"compare_pdf_{i}",
                    label_visibility="collapsed",
                    on_change=_on_compare_pdf_upload,
                    args=(i,),
                )
            with info_col:
                # 显示提取结果或错误
                pdf_error = st.session_state.get(f"_compare_pdf_error_{i}", "")
                if pdf_error:
                    st.error(pdf_error)
                else:
                    info = st.session_state.get(f"_compare_pdf_info_{i}", {})
                    if info:
                        conf = info.get("confidence", 1.0)
                        conf_icon = "🟢" if conf >= 0.7 else ("🟡" if conf >= 0.4 else "🔴")
                        st.success(f"✅ {info.get('page_count','?')}页 | {info.get('char_count','?')}字 | {conf_icon}{conf:.0%}")
                        for w in info.get("warnings", []):
                            st.warning(f"⚠️ {w}")

            product_inputs.append((p_name, p_text))

    # 对比按钮
    compare_btn = st.button("⚖️ 开始对比分析", type="primary", use_container_width=True)

    # ---- 对比结果展示 ----
    if compare_btn:
        # 校验输入
        valid_products = [(n, t) for n, t in product_inputs if t.strip()]
        if len(valid_products) < 2:
            st.warning("⚠️ 请至少填写2款产品的条款文本")
        else:
            try:
                from backend.comparison import ComparisonEngine
                from backend.config import LLMConfig

                comp_config = LLMConfig(
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    base_url=base_url,
                    temperature=temperature,
                )
                comp_engine = ComparisonEngine(config=comp_config, risk_preference=risk_pref)

                progress_bar = st.progress(0)
                status_text = st.empty()

                def _progress(desc, pct):
                    status_text.text(desc)
                    progress_bar.progress(min(int(pct * 100), 100))

                with st.spinner("正在对比分析..."):
                    comp_result = comp_engine.compare(valid_products, progress_callback=_progress)

                progress_bar.empty()
                status_text.empty()

                # ===== 1. 对比总表 =====
                st.divider()
                st.subheader("📊 对比总表")

                from backend.comparison import COMPARISON_DIMENSIONS
                dim_labels = [label for _, label in COMPARISON_DIMENSIONS]
                product_names = [pa.name for pa in comp_result.products]

                # 构建表格数据
                table_data = {"对比维度": dim_labels}
                for pa in comp_result.products:
                    table_data[pa.name] = [
                        pa.translation.get(key, "—") or "—"
                        for key, _ in COMPARISON_DIMENSIONS
                    ]

                # 用 HTML 表格展示，优势方高亮
                winner_map = comp_result.dimension_winners
                html_rows = []
                for idx, dim_label in enumerate(dim_labels):
                    dim_key = COMPARISON_DIMENSIONS[idx][0]
                    winner = winner_map.get(dim_key, "")
                    cells = [f"<td style='font-weight:600;background:#f5f5f5;'>{dim_label}</td>"]
                    for pa in comp_result.products:
                        val = pa.translation.get(dim_key, "—") or "—"
                        is_winner = (winner == pa.name and winner != "")
                        bg = "#e8f5e9" if is_winner else "#ffffff"
                        badge = " 🏆" if is_winner else ""
                        cells.append(f"<td style='background:{bg};'>{val}{badge}</td>")
                    html_rows.append("<tr>" + "".join(cells) + "</tr>")

                header_cells = "".join(
                    f"<th style='background:#1976d2;color:white;padding:8px;text-align:center;'>{n}</th>"
                    for n in ["对比维度"] + product_names
                )
                st.markdown(f"""
                <table style='width:100%;border-collapse:collapse;font-size:0.9rem;'>
                <thead><tr>{header_cells}</tr></thead>
                <tbody>{''.join(html_rows)}</tbody>
                </table>
                """, unsafe_allow_html=True)
                st.caption("🏆 表示该维度的优势方（收益率更高/风险更低/流动性更好等）")

                # ===== 2. 评分结果 =====
                st.divider()
                st.subheader("🏆 综合评分（风险偏好：" + risk_pref + "型）")

                # 评分卡片
                score_cols = st.columns(len(comp_result.scoring_results))
                for idx, sr in enumerate(comp_result.scoring_results):
                    with score_cols[idx]:
                        medal = ["🥇", "🥈", "🥉", "4️⃣"][sr.rank - 1] if sr.rank <= 4 else ""
                        is_winner = sr.rank == 1
                        border_color = "#ffd700" if is_winner else "#e0e0e0"
                        bg_color = "#fffde7" if is_winner else "#fafafa"
                        dim_bars = ""
                        for d in sr.dimensions:
                            bar_width = int(d.score)
                            dim_bars += f"""
                            <div style='margin:4px 0;'>
                                <div style='font-size:0.75rem;color:#666;display:flex;justify-content:space-between;'>
                                    <span>{d.name}</span><span>{d.score:.0f}</span>
                                </div>
                                <div style='background:#eee;height:6px;border-radius:3px;'>
                                    <div style='background:{"#4caf50" if d.score>=70 else "#ff9800" if d.score>=40 else "#f44336"};width:{bar_width}%;height:6px;border-radius:3px;'></div>
                                </div>
                            </div>"""

                        deduction_html = ""
                        if sr.deductions:
                            deduction_html = "<div style='font-size:0.75rem;color:#c62828;margin-top:6px;'>" + "<br>".join(f"⚠️ {d}" for d in sr.deductions) + "</div>"

                        st.markdown(f"""
                        <div style='background:{bg_color};border:2px solid {border_color};border-radius:12px;padding:15px;text-align:center;'>
                            <div style='font-size:1.5rem;'>{medal}</div>
                            <div style='font-size:1rem;font-weight:700;margin:4px 0;'>{sr.product_name}</div>
                            <div style='font-size:2rem;font-weight:800;color:{"#2e7d32" if is_winner else "#666"};'>{sr.adjusted_score:.1f}</div>
                            <div style='font-size:0.75rem;color:#888;'>综合得分（满分100）</div>
                            <div style='text-align:left;margin-top:10px;'>{dim_bars}</div>
                            {deduction_html}
                        </div>
                        """, unsafe_allow_html=True)

                # ===== 3. 推荐结论 =====
                st.divider()
                rec = comp_result.recommendation
                st.subheader("💡 智能推荐结论")

                st.markdown(f"""
                <div style='background:linear-gradient(135deg,#e3f2fd,#bbdefb);border-radius:12px;padding:20px;border-left:5px solid #1976d2;'>
                    <div style='font-size:1.1rem;font-weight:700;color:#0d47a1;'>
                        🏆 推荐选择：{rec['winner_name']}（综合得分 {rec['winner_score']:.1f}）
                    </div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("**推荐理由：**")
                for reason in rec["reasons"]:
                    st.markdown(f"- ✅ {reason}")

                st.markdown("**⚠️ 风险提示：**")
                for warning in rec["risk_warnings"]:
                    st.markdown(f"- ⚠️ {warning}")

                # 落选原因
                if rec["loser_reasons"]:
                    st.markdown("**📉 其他产品落选原因：**")
                    for pname, reasons in rec["loser_reasons"].items():
                        st.markdown(f"**{pname}：**")
                        for r in reasons:
                            st.markdown(f"  - {r}")

                # ===== 4. 白话对比总结 =====
                st.divider()
                st.subheader("🗣️ 大白话对比总结")
                st.markdown(f"""
                <div style='background:#fff8e1;border-radius:10px;padding:15px;border-left:4px solid #ffa000;'>
                    <div style='font-size:1rem;line-height:1.8;'>{comp_result.plain_summary}</div>
                </div>
                """, unsafe_allow_html=True)

                # 免责声明
                st.divider()
                st.caption(rec["disclaimer"])

            except Exception as e:
                st.error(f"❌ 对比分析失败：{e}")
                st.caption("请检查 API Key 是否正确、网络是否通畅。")

# ============================================================
# 页脚
# ============================================================
st.divider()
st.caption(
    "🔨 术语粉碎机 v1.0 ｜ AI 创意大赛参赛作品 ｜ "
    "本工具仅供学习参考，不构成任何投资建议。金融产品有风险，投资需谨慎。"
)
