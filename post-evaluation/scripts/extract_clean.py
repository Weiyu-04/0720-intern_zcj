#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版面感知的干净文本提取：按字号过滤掉脚注(≤9pt)与内联脚注标记，
保留正文(≥11pt)。被脚注劈开的句子会自动重新拼回。确定性、可复现。"""
import sys, re, fitz
from collections import Counter

def _auto_threshold(doc):
    """自适应正文/脚注阈值：正文=字符数最多的字号(众数)，阈值=众数*0.72(留表头，去脚注)。
    不写死11pt，随报告排版自适应。"""
    hist = Counter()
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    if s["text"].strip():
                        hist[round(s["size"], 1)] += len(s["text"])
    if not hist:
        return 11.0
    body = max(hist, key=hist.get)          # 正文众数字号
    return max(10.0, round(body * 0.72, 1))  # 脚注通常≤正文0.6，表头≈0.75

def extract(pdf):
    doc = fitz.open(pdf)
    thr = _auto_threshold(doc)
    out = []
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                line = "".join(s["text"] for s in l.get("spans", []) if s["size"] >= thr)
                # 防御性兜底：整行是脚注定义"[N] 《…》"的也丢
                if line.strip() and not re.match(r'^\[\d+\]', line.strip()):
                    out.append(line.rstrip())
    text = "\n".join(out)
    # 去"- N -"页码行
    text = "\n".join(ln for ln in text.splitlines()
                     if not re.fullmatch(r"\s*-\s*\d+\s*-\s*", ln.strip()))
    return text

if __name__ == "__main__":
    text = extract(sys.argv[1])
    if len(sys.argv) > 2:
        open(sys.argv[2], "w", encoding="utf-8").write(text)
        print("已写:", sys.argv[2], len(text), "字符")
    else:
        print(text)
