"""
PDF 文字提取与清洗模块
功能：
  1. 使用 pdfplumber 提取 PDF 全文
  2. 断行修复：中文段落中被硬换行打断的句子自动合并
  3. 格式清洗：去除页眉页脚、页码、多余空白
  4. 提取验证：非空检查、长度检查、乱码检测
  5. 返回提取元数据（页数、字数、置信度）
"""
import io
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("term_crusher.pdf")


@dataclass
class PdfExtractResult:
    """PDF 提取结果"""
    text: str                          # 清洗后的纯文本
    raw_text: str                      # 原始提取文本（未清洗）
    page_count: int = 0                # PDF 页数
    char_count: int = 0                # 清洗后字符数
    raw_char_count: int = 0            # 原始字符数
    confidence: float = 1.0            # 提取置信度 0-1
    warnings: list[str] = field(default_factory=list)  # 警告信息
    success: bool = False              # 是否提取成功


class PdfExtractor:
    """PDF 文字提取与清洗器"""

    # 中文标点（用于判断句末）
    CHINESE_SENTENCE_END = "。！？；：…—"
    # 英文句末标点
    ENGLISH_SENTENCE_END = ".!?:;"
    # 页码模式（单独一行的数字、第X页、Page X等）
    PAGE_NUMBER_PATTERNS = [
        re.compile(r"^\s*第\s*\d+\s*页\s*$"),
        re.compile(r"^\s*Page\s*\d+\s*$", re.IGNORECASE),
        re.compile(r"^\s*\d+\s*\/\s*\d+\s*$"),
        re.compile(r"^\s*-\s*\d+\s*-\s*$"),
        re.compile(r"^\s*\d+\s*$"),
    ]
    # 常见页眉页脚关键词
    HEADER_FOOTER_KEYWORDS = [
        "版权所有", "保密", "机密", "仅供参考", "不构成投资建议",
        "风险提示", "免责声明", "本资料", "本文件",
    ]

    def extract(self, pdf_source) -> PdfExtractResult:
        """
        从 PDF 提取文字。

        Args:
            pdf_source: 文件路径(str)或字节流(bytes/BytesIO)

        Returns:
            PdfExtractResult
        """
        result = PdfExtractResult(raw_text="", text="")

        try:
            import pdfplumber
        except ImportError:
            result.warnings.append("未安装 pdfplumber，请运行: pip install pdfplumber")
            return result

        try:
            # 支持文件路径和字节流
            if isinstance(pdf_source, (bytes, io.BytesIO)):
                if isinstance(pdf_source, bytes):
                    pdf_source = io.BytesIO(pdf_source)
                pdf = pdfplumber.open(pdf_source)
            else:
                pdf = pdfplumber.open(pdf_source)

            page_count = len(pdf.pages)
            result.page_count = page_count
            logger.info("PDF 共 %d 页", page_count)

            # 逐页提取
            raw_pages = []
            for i, page in enumerate(pdf.pages):
                try:
                    page_text = page.extract_text() or ""
                    raw_pages.append(page_text)
                    logger.debug("第 %d 页提取 %d 字符", i + 1, len(page_text))
                except Exception as e:
                    logger.warning("第 %d 页提取失败: %s", i + 1, e)
                    raw_pages.append("")
                    result.warnings.append(f"第{i+1}页提取失败")

            pdf.close()

            # 合并所有页
            raw_text = "\n".join(raw_pages)
            result.raw_text = raw_text
            result.raw_char_count = len(raw_text)

            if not raw_text.strip():
                result.warnings.append("PDF 中未提取到任何文字（可能是扫描件/图片PDF）")
                result.confidence = 0.0
                return result

            # 清洗文本
            cleaned = self._clean_text(raw_text, page_count)
            result.text = cleaned
            result.char_count = len(cleaned)

            # 验证
            result = self._validate(result)
            result.success = True

            logger.info("PDF 提取完成 | %d页 | 原始%d字 | 清洗后%d字 | 置信度%.2f",
                        page_count, result.raw_char_count, result.char_count, result.confidence)
            return result

        except Exception as e:
            logger.error("PDF 提取异常: %s", e)
            result.warnings.append(f"提取异常: {e}")
            return result

    def _clean_text(self, raw_text: str, page_count: int) -> str:
        """
        清洗提取的原始文本：
        1. 统一换行符
        2. 去除页眉页脚和页码
        3. 修复中文断行
        4. 合并段落
        5. 去除多余空白
        """
        # 1. 统一换行符和空白
        text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\t", " ")
        # 去除行首尾空白
        lines = [line.strip() for line in text.split("\n")]

        # 2. 去除页码行和明显的页眉页脚
        cleaned_lines = []
        for line in lines:
            if not line:
                cleaned_lines.append("")  # 保留空行作为段落分隔
                continue
            if self._is_page_number(line):
                continue
            if self._is_header_footer(line, page_count):
                continue
            cleaned_lines.append(line)

        # 3. 修复断行 + 合并段落
        merged = self._fix_line_breaks(cleaned_lines)

        # 4. 最终清洗
        merged = re.sub(r" {2,}", " ", merged)          # 多个空格合并为一个
        merged = re.sub(r"\n{3,}", "\n\n", merged)      # 3个以上换行合并为2个
        merged = merged.strip()

        return merged

    def _is_page_number(self, line: str) -> bool:
        """判断是否为页码行"""
        for pattern in self.PAGE_NUMBER_PATTERNS:
            if pattern.match(line):
                return True
        return False

    def _is_header_footer(self, line: str, page_count: int) -> bool:
        """
        判断是否为页眉页脚。
        策略：短行（<30字）且包含页眉页脚关键词。
        注意：不能误删正文，所以条件要严格。
        """
        if len(line) > 40:
            return False
        for kw in self.HEADER_FOOTER_KEYWORDS:
            if kw in line:
                return True
        return False

    def _fix_line_breaks(self, lines: list[str]) -> str:
        """
        修复 PDF 提取中的断行问题，同时保留原文件段落格式。

        核心逻辑：
        - 连续非空行 → 同一段落，合并断行（中文直接拼接，英文加空格）
        - 空行 → 段落分隔符，始终保留（不跨空行合并）
        - 这样能最大程度保留原 PDF 的段落结构，方便阅读
        """
        if not lines:
            return ""

        paragraphs = []
        current_para = []

        for line in lines:
            if not line:
                # 空行 = 段落分隔，保留
                if current_para:
                    paragraphs.append(self._merge_paragraph_lines(current_para))
                    current_para = []
                paragraphs.append("")  # 占位空行，最后用 \n\n 连接
                continue
            current_para.append(line)

        if current_para:
            paragraphs.append(self._merge_paragraph_lines(current_para))

        # 用 \n 连接（空行占位为 ""，连接后自然形成空行）
        result = "\n".join(paragraphs)
        # 合并多余空行（3个以上 → 2个）
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()

    def _ends_with_sentence(self, line: str) -> bool:
        """判断一行是否以句末标点结尾（表示句子/段落结束）"""
        if not line:
            return False
        last = line.rstrip()[-1]
        return last in self.CHINESE_SENTENCE_END + self.ENGLISH_SENTENCE_END

    def _merge_paragraph_lines(self, lines: list[str]) -> str:
        """
        合并同一段落内的多行文本。
        根据首尾字符判断是否需要加空格（英文）还是直接拼接（中文）。
        """
        if not lines:
            return ""
        if len(lines) == 1:
            return lines[0]

        merged = lines[0]
        for i in range(1, len(lines)):
            prev = merged
            curr = lines[i]

            # 判断是否需要加空格连接
            if self._needs_space(prev, curr):
                merged += " " + curr
            else:
                merged += curr

        return merged

    @staticmethod
    def _needs_space(prev_end: str, next_start: str) -> bool:
        """
        判断两行之间是否需要加空格。
        中文之间不需要空格，英文/数字之间需要。
        """
        if not prev_end or not next_start:
            return False

        prev_char = prev_end[-1]
        next_char = next_start[0]

        # 判断字符类型
        def is_cjk(ch):
            return "\u4e00" <= ch <= "\u9fff" or "\u3000" <= ch <= "\u303f" or "\uff00" <= ch <= "\uffef"

        def is_alnum(ch):
            return ch.isalnum()

        # 中文接中文 → 不需要空格
        if is_cjk(prev_char) and is_cjk(next_char):
            return False
        # 中文接英文/数字 → 不需要空格（中文排版习惯）
        if is_cjk(prev_char) and is_alnum(next_char):
            return False
        # 英文/数字接中文 → 不需要空格
        if is_alnum(prev_char) and is_cjk(next_char):
            return False
        # 英文/数字接英文/数字 → 需要空格
        if is_alnum(prev_char) and is_alnum(next_char):
            return True
        # 其他情况（标点等）→ 不需要空格
        return False

    def _validate(self, result: PdfExtractResult) -> PdfExtractResult:
        """
        验证提取结果质量，计算置信度，添加警告。
        """
        text = result.text
        text_len = len(text)
        # 确保 char_count 与实际文本一致
        if result.char_count == 0 and text:
            result.char_count = text_len

        # 检查是否为空
        if not text.strip():
            result.confidence = 0.0
            result.warnings.append("清洗后文本为空")
            return result

        # 检查长度
        if text_len < 20:
            result.confidence = 0.3
            result.warnings.append(f"提取文本过短（仅{text_len}字），可能是扫描件或内容过少")
        elif text_len < 100:
            result.confidence = 0.6
            result.warnings.append(f"提取文本较短（{text_len}字），请确认是否完整")

        # 乱码检测：统计不可打印字符比例
        non_printable = sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\t")
        if non_printable > 0:
            ratio = non_printable / len(text)
            if ratio > 0.05:
                result.confidence *= 0.5
                result.warnings.append(f"检测到{non_printable}个不可打印字符，可能存在乱码")

        # 中文比例检测（金融条款应为中文为主）
        cjk_count = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        cjk_ratio = cjk_count / max(len(text), 1)
        if cjk_ratio < 0.1 and result.char_count > 50:
            result.warnings.append("中文占比过低，可能是英文文档或提取异常")
            result.confidence *= 0.7

        # 清洗率：清洗后/原始 比例
        if result.raw_char_count > 0:
            clean_ratio = result.char_count / result.raw_char_count
            if clean_ratio < 0.3:
                result.warnings.append(f"清洗后文本仅为原始的{clean_ratio:.0%}，可能过度清洗或原始内容含大量格式符")

        result.confidence = max(0.0, min(1.0, result.confidence))
        return result
