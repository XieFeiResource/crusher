# 🔨 术语粉碎机 - 金融条款 AI 解读工作台

> AI 创意大赛参赛作品：将晦涩金融条款一键转化为大白话、参数卡片、流程图和风险高亮。

## ✨ 功能特性

| 模块 | 功能 |
|------|------|
| 📁 PDF上传 | 上传PDF产品说明书/合同，自动提取文字、修复断行、清洗格式 |
| 💡 白话翻译 | 100字以内通俗解释，支持4种风格（通俗版/大妈版/专业版/幽默版） |
| 📊 参数卡片 | 自动提取产品类型、期限、收益率、风险等级、本金保障、赎回条件、费用结构 |
| 📈 流程图 | AI 自动生成 Mermaid 收益逻辑流程图，赚钱路径绿色、亏钱路径红色 |
| ⚠️ 风险高亮 | 在原文上高亮标注风险点，鼠标悬停查看解读，按高/中/低分级 |

## 📁 项目结构

```
term_crusher/
├── app.py                  # Streamlit 前端主程序
├── requirements.txt        # Python 依赖
├── .env.example            # 环境变量配置模板
├── README.md               # 本文件
├── backend/
│   ├── __init__.py
│   ├── config.py           # 配置管理（多服务商支持）
│   ├── llm_client.py       # LLM 客户端（OpenAI兼容接口+重试+JSON解析+日志）
│   ├── prompts.py          # 三阶段提示词模板
│   ├── translator.py       # 阶段一：白话翻译+结构化提取
│   ├── flowchart.py        # 阶段二：Mermaid流程图生成+清洗
│   ├── risk_analyzer.py    # 阶段三：风险识别与高亮
│   ├── pdf_extractor.py    # PDF文字提取+断行修复+格式清洗
│   └── pipeline.py         # 处理流水线（串联三阶段）
└── data/
    └── examples.json       # 5个示例条款（结构性存款/雪球/保险/基金/借贷）
```

## 🚀 快速开始

### 1. 安装依赖

```bash
cd term_crusher
pip install -r requirements.txt
```

### 2. 配置 API Key

方式一：复制 `.env.example` 为 `.env`，填入你的 API Key：

```bash
cp .env.example .env
# 编辑 .env，设置 LLM_API_KEY=sk-xxx
```

方式二：启动后在网页左侧侧边栏直接填入 API Key。

### 3. 启动应用

```bash
streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`。

## 🔧 支持的 LLM 服务商

| 服务商 | provider 值 | 默认模型 | API 地址 |
|--------|------------|----------|----------|
| DeepSeek | `deepseek` | `deepseek-chat` | https://api.deepseek.com/v1 |
| Kimi (月之暗面) | `kimi` | `moonshot-v1-8k` | https://api.moonshot.cn/v1 |
| 通义千问 | `qwen` | `qwen-plus` | https://dashscope.aliyuncs.com/compatible-mode/v1 |
| OpenAI | `openai` | `gpt-4o-mini` | https://api.openai.com/v1 |

所有服务商均使用 OpenAI 兼容接口，在侧边栏切换即可。

## 🎯 使用流程

1. **上传PDF或粘贴文本**（二选一）：
   - 点击「📁 上传 PDF 文件」选择产品说明书或合同，系统自动提取文字并显示页数、字数、置信度
   - 或直接在文本框粘贴金融条款（也可从下拉框选择5个内置示例）
2. 选择翻译风格（通俗版/大妈版/专业版/幽默版）
3. 点击「🔨 开始粉碎术语」
4. 查看结果：
   - 左侧：原文 + 风险高亮（红=高风险，橙=中风险，黄=低风险）
   - 右侧：大白话解读 + 7项关键参数卡片
   - 下方：风险点详解 + 收益逻辑流程图

> **PDF 提取说明**：支持文字型 PDF；扫描件/图片 PDF 可能无法提取文字（会显示警告）。提取后的文字可在文本框中编辑修改后再处理。

## 🧪 内置示例条款

- 结构性存款（汇率挂钩）
- 雪球产品（中证500挂钩）
- 保险条款（重疾险）
- 基金合同（主动权益）
- 借贷合同（消费贷）

## ⚠️ 免责声明

本工具仅供学习和参考使用，AI 生成的解读可能存在误差，不构成任何投资建议。
金融产品有风险，投资需谨慎，请以官方合同条款为准。
