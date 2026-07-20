#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性构建工具：把《2017国民经济行业分类注释》(GB/T 4754-2017, 2019修订) Excel
抽取成干净的代码库 data/gbt4754.json，供 encode.py 运行时查表使用。

Excel 结构（Sheet1）：
  A列(0)：门类字母 / 大类2位 / 中类3位
  B列(1)：小类4位码
  D列(3)：名称（注释行的说明文字也在D列及其后，靠"是否为代码行"过滤）

用法：
  python3 build_catalog.py [Excel路径]
默认路径为项目 制度文件/2017国民经济行业分类注释.xlsx
"""
import json
import os
import re
import sys

import openpyxl

DEFAULT_XLSX = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "制度文件",
    "2017国民经济行业分类注释.xlsx",
)
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "gbt4754.json")

RE_MENLEI = re.compile(r"^[A-T]$")
RE_DALEI = re.compile(r"^\d{2}$")
RE_ZHONGLEI = re.compile(r"^\d{3}$")
RE_XIAOLEI = re.compile(r"^\d{4}$")


def _first_name(row, start=3, end=12):
    for i in range(start, min(end, len(row))):
        v = row[i]
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def build(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb["Sheet1"]

    codes = {}
    cur = {"门类": None, "门类名": None, "大类": None, "大类名": None,
           "中类": None, "中类名": None}

    for row in ws.iter_rows(values_only=True):
        a = str(row[0]).strip() if row[0] is not None else ""
        b = str(row[1]).strip() if row[1] is not None else ""

        # 先用 A 列更新层级上下文（门类/大类/中类）
        if RE_MENLEI.match(a):
            name = _first_name(row)
            cur.update(门类=a, 门类名=name, 大类=None, 大类名=None, 中类=None, 中类名=None)
            codes[a] = {"name": name, "level": "门类"}
        elif RE_DALEI.match(a):
            name = _first_name(row)
            cur.update(大类=a, 大类名=name, 中类=None, 中类名=None)
            codes[a] = {"name": name, "level": "大类", "门类": cur["门类"]}
        elif RE_ZHONGLEI.match(a):
            name = _first_name(row)
            cur.update(中类=a, 中类名=name)
            codes[a] = {"name": name, "level": "中类",
                        "门类": cur["门类"], "大类": cur["大类"]}

        # 小类在 B 列，独立处理：同一行可能既有中类(A列)又有其唯一小类(B列)，
        # 例如 A='061' B='0610'，不能用 elif 否则会漏掉这类"独子小类"。
        if RE_XIAOLEI.match(b):
            name = _first_name(row)
            codes[b] = {"name": name, "level": "小类", "门类": cur["门类"],
                        "大类": cur["大类"], "中类": cur["中类"]}

    payload = {
        "meta": {
            "source": "GB/T 4754-2017 国民经济行业分类（2019年修订）注释",
            "note": "WSA3XXXX 的后四位取小类4位码（去门类字母）",
            "counts": {
                lvl: sum(1 for v in codes.values() if v["level"] == lvl)
                for lvl in ("门类", "大类", "中类", "小类")
            },
        },
        "codes": codes,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"写出 {OUT}")
    print("统计:", payload["meta"]["counts"])
    # 抽验
    for c in ("5523", "0610", "2612", "5421"):
        print(f"  {c} -> {codes.get(c)}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_XLSX
    build(path)
