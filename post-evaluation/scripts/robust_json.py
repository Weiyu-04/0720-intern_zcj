#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON 加载 + 可读且"处方式"的报错（post-evaluation 专用）。

**为什么需要它**：本技能第4步会产出一份 combined_data.json。事故调查报告正文
经常带引号（如：参见报告"三、（三）存在的问题"），手写/编辑 JSON 时极易把它写成
**未转义的半角 `"`**——它会让解析器以为字符串在此提前结束。裸 `json.load` 只抛一个
**字节偏移**（`Expecting ',' delimiter (char 268)`），模型/人都看不出错在哪、该怎么改，
于是陷入逐条 `replace` / `sed` 的**打地鼠**：引号遍布全文，每修一处只暴露下一处，
永远收敛不了（本技能历史上真实发生过）。

**本模块只做一件事：把那层不可读的报错，换成"定位到行、带 `^` 指示符、并给出
一次性正确做法"的说明。** 它**不做静默自动修复**——正文是要"照抄一字不改"、供专家
法律评审的文书，绝不能让脚本猜着改（改错了还会悄悄污染，比直接失败更糟）。真要
一次性转义，请显式走 `--fix`（会改写文本，改完必须人工核对）。

作为库用（generate_tables.py / merge_tables.py 都用它）：
    from robust_json import load_json_or_explain
    data = load_json_or_explain(path)   # 解析不了 → 打印处方式报错并 SystemExit(1)

作为命令行用：
    python robust_json.py <file.json>          # 只校验；坏了给可读报错（并提示可 --fix 的处数）
    python robust_json.py <file.json> --fix    # 显式一次性转义未转义引号并写回（改文本，需人工核对）
"""
import sys
import os
import json

_CLOSERS = set(",:}]")


def repair_unescaped_quotes(s):
    """转义 JSON 字符串值内部未转义的半角双引号，返回 (修复后文本, 修复处数)。

    ⚠️ 这是一个**启发式**、并不健全：判据是"一个半角 `"` 只有当其后第一个非空白
    字符是 `, : } ]` 或文件结束时才算字符串结束符，否则视为正文引号并转义"。因此
    当正文里的引号恰好紧跟半角 `, : } ]`（如 `他说"是的",我同意`、`比例"3":1`）时会**误判**，
    可能截断/改坏文本。所以它**只在显式 `--fix` 下使用**，且要求人工核对；主加载路径
    （load_json_or_explain）不调用它。
    """
    out = []
    in_str = False
    fixes = 0
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if not in_str:
            out.append(c)
            if c == '"':
                in_str = True
            i += 1
            continue
        # ---- 字符串内部 ----
        if c == '\\':
            out.append(c)
            if i + 1 < n:
                out.append(s[i + 1])
                i += 2
            else:
                i += 1
            continue
        if c == '"':
            j = i + 1
            while j < n and s[j] in " \t\r\n":
                j += 1
            if j >= n or s[j] in _CLOSERS:
                out.append(c)          # 结构性字符串结束符
                in_str = False
            else:
                out.append('\\"')      # 正文里的引号 → 转义
                fixes += 1
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out), fixes


def _diagnose(text, err, path):
    """把 json.JSONDecodeError 渲染成定位到行、带 ^、并给出一次性做法的处方式报错。"""
    lines = text.splitlines()
    lineno = getattr(err, "lineno", 1)
    colno = getattr(err, "colno", 1)
    line = lines[lineno - 1] if 1 <= lineno <= len(lines) else ""
    caret = " " * max(colno - 1, 0) + "^"
    _, fixes = repair_unescaped_quotes(text)
    detected = f"  检测到约 {fixes} 处疑似未转义的半角引号。\n" if fixes else ""
    me = os.path.basename(__file__)
    return (
        f"\n[JSON 解析失败] {path}\n"
        f"  第 {lineno} 行第 {colno} 列：{err.msg}\n"
        f"    {line}\n"
        f"    {caret}\n"
        f"{detected}"
        f"  多半是字符串里用了**半角 \"**（报告正文的引号）没有转义。\n"
        f"  ⚠️ 不要逐条 replace / sed 去改——引号遍布全文，改不完（会打地鼠）。\n"
        f"  一次性正确做法（三选一，优先 1）：\n"
        f"    1) 重新用 merge_tables.py 从 table2.json / table3.json 生成 combined_data.json\n"
        f"       （最稳：合并走 json.dump，转义由库负责，绝不会产出坏引号）；\n"
        f"    2) 把源头正文里的半角 \" 改成全角 “ ”（或写成转义的 \\\"）后重跑；\n"
        f"    3) 显式运行 `python {me} <file> --fix` 一次性转义——会改写文本，"
        f"改完请**人工核对被改处**（此法是启发式，可能误判）。\n"
    )


def load_json_or_explain(path):
    """严格解析 JSON；失败则打印**处方式可读报错**并退出（不静默改写文本）。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        sys.stderr.write(_diagnose(text, e, path))
        raise SystemExit(1)


def _cli():
    if len(sys.argv) < 2:
        print("用法: python robust_json.py <file.json> [--fix]", file=sys.stderr)
        raise SystemExit(2)
    path = sys.argv[1]
    do_fix = "--fix" in sys.argv[2:]
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        json.loads(text)
        print(f"OK: {path} 是合法 JSON。")
        return
    except json.JSONDecodeError as e:
        if not do_fix:
            sys.stderr.write(_diagnose(text, e, path))
            raise SystemExit(1)
    # --fix：显式一次性转义。仅当修复后确实合法才写回，否则响亮失败、不写垃圾。
    repaired, fixes = repair_unescaped_quotes(text)
    try:
        json.loads(repaired)
    except json.JSONDecodeError as e2:
        sys.stderr.write(_diagnose(repaired, e2, path))
        print("（--fix 未能修好：可能不是引号问题，或正文引号紧跟半角标点导致误判。请人工检查。）",
              file=sys.stderr)
        raise SystemExit(1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(repaired)
    print(f"已转义 {fixes} 处未转义引号并写回：{path}")
    print("⚠️ 这是启发式修复，请人工核对被改处是否与报告原文一致（尤其正文里本就带引号的句子）。")


if __name__ == "__main__":
    _cli()
