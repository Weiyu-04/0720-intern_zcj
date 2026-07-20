#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""容错 JSON 加载器（post-evaluation 专用兜底）。

**为什么需要它**：本技能第4步要把 table2/table3 合并成一份 JSON 再交给
generate_tables.py。事故调查报告正文里经常带引号（如：参见报告"三、（三）
存在的问题"），模型手写/编辑 JSON 时很容易把这种引号写成**半角 ASCII 双引号
"**（而不是全角 “”）。字符串值里未转义的半角 " 会被 JSON 解析器当成字符串结束，
于是 json.load 直接抛 `Expecting ',' delimiter`——只给一个字节偏移量，模型看不懂，
就会陷入一次次 replace 打地鼠（历史上真实发生过）。

**这里做三件事**：
  1. 先按严格 JSON 解析——合法就原样返回，绝不改动。
  2. 失败则做一次**修复**：把字符串值内部“非结构性”的半角双引号转义掉
     （启发式：一个 " 只有在其后第一个非空白字符是 , : } ] 或文件结束时，
      才是真正的字符串结束符；否则它是正文里的引号，应转义）。修复后重新解析。
  3. 仍失败则打印**定位到行、带指示符 ^ 的清晰报错**（而不是原始 traceback），
     并明确提示“半角引号 → 全角引号”这一最常见原因，让模型一步到位地改对。

作为库用：
    from robust_json import load_json_tolerant
    data = load_json_tolerant(path)   # 解析不了会 SystemExit(1) 并打印可读报错

作为命令行用（校验/就地修复）：
    python robust_json.py <file.json>          # 只校验并报告
    python robust_json.py <file.json> --fix    # 就地修复并写回
"""
import sys
import json

_CLOSERS = set(",:}]")


def repair_unescaped_quotes(s):
    """转义 JSON 字符串值内部未转义的半角双引号，返回 (修复后文本, 修复处数)。

    逐字符状态机：只在“字符串内部”动手，且只处理那些**不是**结构性结束符的
    半角双引号。已经是 \\" 的转义引号原样跳过，不会二次转义。合法 JSON 传进来
    时不会命中任何修复点（因为合法 JSON 里字符串内引号本就已转义）。
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
            # 转义序列：连同下一个字符原样保留
            out.append(c)
            if i + 1 < n:
                out.append(s[i + 1])
                i += 2
            else:
                i += 1
            continue
        if c == '"':
            # 向后看第一个非空白字符，判断这个 " 是“真结束符”还是“正文引号”
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


def _pretty_error(text, err, path):
    """把 json.JSONDecodeError 渲染成定位到行、带 ^ 指示符的可读报错。"""
    lines = text.splitlines()
    lineno = getattr(err, "lineno", 1)
    colno = getattr(err, "colno", 1)
    line = lines[lineno - 1] if 1 <= lineno <= len(lines) else ""
    caret = " " * (max(colno - 1, 0)) + "^"
    return (
        f"\n[JSON 解析失败] {path}\n"
        f"  位置：第 {lineno} 行，第 {colno} 列 —— {err.msg}\n"
        f"    {line}\n"
        f"    {caret}\n"
        f"  最常见原因：字符串里的引号用了**半角 \"**。请把正文引号改成**全角 “ ”**，\n"
        f"  或写成转义的 \\\"。（例：报告\"三、（三）\" → 报告“三、（三）”）\n"
    )


def load_json_tolerant(path, *, verbose=True):
    """读取 JSON：严格解析 → 失败则修复重试 → 仍失败打印可读报错并退出。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    repaired, fixes = repair_unescaped_quotes(text)
    if fixes:
        try:
            data = json.loads(repaired)
            if verbose:
                print(f"[robust_json] 已自动修复 {fixes} 处未转义的半角引号（{path}）。"
                      f"建议后续在源头用全角 “ ” 以免依赖兜底。", file=sys.stderr)
            return data
        except json.JSONDecodeError as e2:
            sys.stderr.write(_pretty_error(repaired, e2, path))
            raise SystemExit(1)
    # 无可修复点，说明是别的语法错误——直接给定位报错
    try:
        json.loads(text)
    except json.JSONDecodeError as e:
        sys.stderr.write(_pretty_error(text, e, path))
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
    except json.JSONDecodeError:
        pass
    repaired, fixes = repair_unescaped_quotes(text)
    try:
        json.loads(repaired)
    except json.JSONDecodeError as e:
        sys.stderr.write(_pretty_error(repaired, e, path))
        raise SystemExit(1)
    if do_fix:
        with open(path, "w", encoding="utf-8") as f:
            f.write(repaired)
        print(f"已修复 {fixes} 处未转义引号并写回：{path}")
    else:
        print(f"可修复：{fixes} 处未转义的半角引号。加 --fix 就地修复。")


if __name__ == "__main__":
    _cli()
