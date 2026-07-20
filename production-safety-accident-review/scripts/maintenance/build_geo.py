#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性构建工具：把《行政区划 截止2016年07月31日》Excel 抽取成 data/geo.json，
供 geo.py 运行时离线查表，用于把警情文本中的地名确定性归一到"省—地级—县级"，
不接任何在线 API。

Excel 结构（Sheet1）：上级编码 | 编码(12位) | 名称 | 简码 | 性质
  性质：0=省级 1=地级 2=县级 3=乡镇街道 4=村居委会
本工具只取 0/1/2 三级（省/地/县），跳过 3/4（乡镇、村居共约71万条，地点记录用不到）。
编码取前6位（国标行政区划代码），parent 取上级编码前6位。

用法：python3 build_geo.py [Excel路径]
"""
import json
import os
import sys

import openpyxl

DEFAULT_XLSX = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "制度文件",
    "行政区划 截止2016年07月31日.xlsx",
)
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "geo.json")

LEVEL = {"0": "省", "1": "地", "2": "县"}
# 四直辖市省级代码（其下的"市辖区/县"为占位地级层）
MUNICIPALITIES = {"110000": "北京市", "120000": "天津市",
                  "310000": "上海市", "500000": "重庆市"}


def build(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb["Sheet1"]
    codes = {}
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue
        parent = str(row[0]).strip() if row[0] else ""
        code = str(row[1]).strip() if row[1] else ""
        name = str(row[2]).strip() if row[2] else ""
        xz = str(row[4]).strip() if row[4] is not None else ""
        if xz not in LEVEL or not code or not name:
            continue
        c6 = code[:6]
        p6 = parent[:6] if parent else None
        codes[c6] = {"name": name, "level": LEVEL[xz], "parent": p6}

    payload = {
        "meta": {
            "source": "行政区划 截止2016年07月31日",
            "as_of": "2016-07-31",
            "levels": "0省/1地/2县（不含乡镇村居）",
            "municipalities": MUNICIPALITIES,
            "counts": {
                lvl: sum(1 for v in codes.values() if v["level"] == lvl)
                for lvl in ("省", "地", "县")
            },
        },
        "codes": codes,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"写出 {OUT}")
    print("统计:", payload["meta"]["counts"])
    for c in ("310105", "310114", "310120", "110105", "371300"):
        print(f"  {c} -> {codes.get(c)}")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_XLSX)
