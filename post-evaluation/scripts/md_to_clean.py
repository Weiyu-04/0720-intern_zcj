#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 parse_document 产出的 Markdown 清成干净正文 txt，供 segment_table2 / parse_table3 使用。

**为什么需要它**（OCR 版专用桥梁）：本副本技能一律用平台工具 `parse_document`（MinerU
VLM/markitdown）解析上传件，产出是**忠实转换的 Markdown**——保留 `#` 标题标记、`**强调**`、
`| 表格 |`、页码、页眉页脚、脚注定义与上标标记。而下游 `segment_table2.py`/`parse_table3.py`
期望的是**干净的章节散文**（靠"五、事故整改和防范措施""（一）"、逐句号切行等锚点解析），
markdown 语法和脚注/页码混入会打乱这些锚点。本脚本确定性地把这些噪声剥掉，尽量还原成
原版 `extract_clean.py` 那样的干净正文。

**局限（务必知悉）**：md 里没有 PDF 的字号信息，脚注/页眉的识别不如 extract_clean 精确，
只能按文本模式启发式剥，可能剥不净、也可能误伤。**残留噪声需 LLM 在第2/3步兜底校验时
对照原文人工剔除**（见 SKILL 第1步）。同输入同输出（纯规则、无模型）。

用法：python md_to_clean.py <in.md> [<out.txt>]
"""
import sys
import re


def clean(md: str):
    """返回 (清洗后正文, 被丢弃的 markdown 表格行数)。"""
    out = []
    table_dropped = 0
    for raw in md.splitlines():
        s = raw.rstrip()
        t = s.strip()

        # 1-2) markdown 表格：分隔行(|---|)与内容行(| … |)一律丢弃。
        # 报告的"五、整改措施""四、处理建议"章节是散文，表格通常是责任花名册/统计，
        # 不是 segment_table2/parse_table3 的抽取来源；把表格 de-pipe 进正文反而会
        # 粘连、污染相邻句子。故整行丢弃，数量报到 stderr 供人工对照 md 原文核。
        if "|" in s and re.fullmatch(r"[\s:\|\-]+", t) and "-" in t:
            table_dropped += 1
            continue
        if t.startswith("|") and s.count("|") >= 2:
            table_dropped += 1
            continue

        # 3) 丢脚注定义行 [^1]: … 或 [1] …（同 extract_clean 的兜底）
        if re.match(r"^\[\^?\d+\]", t):
            continue
        # 4) 丢页码 / 页眉页脚常见形态
        if re.fullmatch(r"-?\s*\d{1,4}\s*-?", t):                       # "- 12 -" / "12"
            continue
        if re.fullmatch(r"第\s*\d+\s*页(\s*/?\s*共\s*\d+\s*页)?", t):     # "第 3 页 / 共 20 页"
            continue
        # 5) 丢 markdown 分隔线 --- *** ___
        if re.fullmatch(r"([-*_]\s*){3,}", t):
            continue

        # 6) 去标题井号：## 五、… -> 五、…
        s = re.sub(r"^\s{0,3}#{1,6}\s+", "", s)
        # 7) 去引用块 > 、无序列表符号 - * +（保留内容；有序列表 1. 2. 是正文，保留）
        s = re.sub(r"^\s{0,3}>\s?", "", s)
        s = re.sub(r"^\s{0,3}[-*+]\s+", "", s)
        # 8) 去强调 **x** / *x* / __x__ / _x_ 、行内代码 `x`（保留内容）
        s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
        s = re.sub(r"\*([^*]+)\*", r"\1", s)
        s = re.sub(r"__([^_]+)__", r"\1", s)
        s = re.sub(r"`([^`]+)`", r"\1", s)
        # 9) 图片/链接：![alt](url) 整块删；[text](url) 保留 text
        s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
        s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
        # 10) 去行内脚注上标标记 [1] [12]（保守：仅孤立的 [1~3 位数字]）
        s = re.sub(r"\[\d{1,3}\]", "", s)

        out.append(s.rstrip())

    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)      # 折叠多余空行
    return text.strip() + "\n", table_dropped


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python md_to_clean.py <in.md> [<out.txt>]", file=sys.stderr)
        sys.exit(1)
    res, table_dropped = clean(open(sys.argv[1], encoding="utf-8").read())
    if table_dropped:
        print(f"[md_to_clean] 已丢弃 {table_dropped} 行 markdown 表格（表格通常不是抽取来源）。"
              f"如报告把整改要求/处理建议排成了表格，请对照 md 原文人工补回。", file=sys.stderr)
    if len(sys.argv) > 2:
        open(sys.argv[2], "w", encoding="utf-8").write(res)
        print(f"已写: {sys.argv[2]} {len(res)} 字符")
    else:
        print(res)
