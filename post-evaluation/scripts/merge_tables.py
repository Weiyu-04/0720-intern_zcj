#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 table2.json 与 table3.json 合并成 generate_tables.py 需要的单一输入。

**为什么要有它**：SKILL 第4步原来让模型“手工把 table2 和 table3_groups 合并成
一份 JSON”。手写/重排大段中文正文时，模型很容易把报告里的引号写成未转义的半角 "，
导致后续 json.load 失败。用脚本合并，**合并输出走 json.dump（转义由库负责），产出的
combined_data.json 恒为合法 JSON**——把"手写整份 JSON"这个大活口消掉。

> 注意：这不等于全链路免疫。你在第2步**就地编辑 table2.json** 填评估内容/方式/佐证
> 材料时，仍可能把引号写成未转义半角，导致**这里读取 table2.json 就先失败**。所以源头
> 正文的引号请一律用全角 “ ”；真读失败了，下面的 load_json_or_explain 会给处方式报错。

输入：
  - table2.json ：segment_table2.py 的产出，且已由你（LLM）填好评估内容/方式/佐证材料。
                  形如 {"table2": [...], "_diagnostics": {...}}
  - table3.json ：parse_table3.py 的产出（并经你兜底校验）。
                  形如 {"table3_groups": [...], "_diagnostics": {...}}
输出：
  - combined_data.json：{"table2": [...], "table3_groups": [...]}（去掉 _diagnostics）

用法：
    python merge_tables.py <table2.json> <table3.json> <combined_out.json>

若某份输入被手工编辑后混入未转义半角引号，load_json_or_explain 会给出定位到行、
带一次性正确做法的处方式报错（不静默改文本），按提示改源头引号或重跑即可。
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from robust_json import load_json_or_explain


def main():
    if len(sys.argv) < 4:
        print("用法: python merge_tables.py <table2.json> <table3.json> <combined_out.json>",
              file=sys.stderr)
        sys.exit(1)
    t2_path, t3_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

    d2 = load_json_or_explain(t2_path)
    d3 = load_json_or_explain(t3_path)

    table2 = d2.get("table2", d2 if isinstance(d2, list) else [])
    table3_groups = d3.get("table3_groups", d3 if isinstance(d3, list) else [])

    if not isinstance(table2, list):
        print(f"[merge_tables] 警告：{t2_path} 里没有数组 table2，按空表处理。", file=sys.stderr)
        table2 = []
    if not isinstance(table3_groups, list):
        print(f"[merge_tables] 警告：{t3_path} 里没有数组 table3_groups，按空表处理。", file=sys.stderr)
        table3_groups = []

    combined = {"table2": table2, "table3_groups": table3_groups}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    n_rows3 = sum(len(g.get("rows", [])) for g in table3_groups if isinstance(g, dict))
    print(f"OK: 已合并 → {out_path}")
    print(f"  table2 行数：{len(table2)}")
    print(f"  table3 组数：{len(table3_groups)}（子行合计 {n_rows3}）")


if __name__ == "__main__":
    main()
