#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行业事故类型编码（按事故发生行业分类，WSA3XXXX）——确定性查表。

依据：GB 6441-2025《生产安全事故分类与编码》第5章：
  - 5.2 事故类型代码共8位：前三位"WSA" + 第四位分类方式 + 后四位类型代码；
  - 5.2 b) 第四位"3"表示"按事故发生行业分类"；
  - 5.5 按行业分类时，后四位按 GB/T 4754 执行，去除门类代码。
示例：内河货物运输（GB/T4754 小类5523）→ WSA35523。

设计目的：行业编码位数必须准确，属于可精确查表的部分，交由本脚本完成，
不由模型臆断。模型负责"读警情文本 → 结合对照表(references/05)确定具体4位小类码"，
再调用本脚本校验并生成 WSA 编码。

数据来源：scripts/data/gbt4754.json（由 build_catalog.py 从
《2017国民经济行业分类注释》Excel 抽取，1381 个小类）。
"""
from __future__ import annotations

import json
import os

_DATA = os.path.join(os.path.dirname(__file__), "data", "gbt4754.json")
_CODES = None

_METHOD_DIGIT = "3"  # 第四位：按事故发生行业分类


def _load() -> dict:
    global _CODES
    if _CODES is None:
        with open(_DATA, encoding="utf-8") as f:
            _CODES = json.load(f)["codes"]
    return _CODES


def info(code: str) -> dict | None:
    """任意层级（门类/大类/中类/小类）查名称与层级。"""
    return _load().get(str(code).strip())


def _hierarchy_text(rec: dict) -> str:
    """组织"门类＞大类＞中类"可读链，用于依据。"""
    codes = _load()
    parts = []
    for key, label in (("门类", "门类"), ("大类", "大类"), ("中类", "中类")):
        c = rec.get(key)
        if c and c in codes:
            parts.append(f"{label}{c} {codes[c]['name']}")
    return "＞".join(parts)


def encode(code: str) -> dict:
    """
    输入 GB/T 4754-2017 四位小类代码，返回 WSA3XXXX 编码及依据。

    返回字段：
        ok        是否成功
        wsa       WSA3XXXX 编码（成功时）
        code      回显四位码
        name      小类名称
        门类/大类/中类  层级代码
        basis     依据链文本
        error     失败原因（失败时）
        hint      失败时的提示
    """
    codes = _load()
    c = str(code).strip()

    if not (c.isdigit() and len(c) == 4):
        return {"ok": False, "code": code,
                "error": "行业编码须为 GB/T4754 的四位小类代码（WSA3 后接4位）。",
                "hint": "可用 search('关键词') 查候选小类；只有4位小类才能编码。"}

    rec = codes.get(c)
    if rec is None:
        return {"ok": False, "code": c,
                "error": f"四位码 {c} 不在 GB/T4754-2017 目录中。",
                "hint": "请核对代码；可用 search('关键词') 查正确小类。"}
    if rec.get("level") != "小类":
        return {"ok": False, "code": c,
                "error": f"{c} 是「{rec['level']}」（{rec['name']}），不是四位小类，不能直接编码。",
                "hint": "需细化到具体四位小类。"}

    wsa = "WSA" + _METHOD_DIGIT + c
    chain = _hierarchy_text(rec)
    basis = (
        f"依据 GB 6441-2025 第5.2、5.5 条（按事故发生行业分类，第四位取“3”，"
        f"后四位取 GB/T4754 小类代码、去门类字母）：行业「{rec['name']}」"
        f"（GB/T4754 小类 {c}；{chain}），事故类型编码为 {wsa}。"
    )
    return {"ok": True, "wsa": wsa, "code": c, "name": rec["name"],
            "门类": rec.get("门类"), "大类": rec.get("大类"), "中类": rec.get("中类"),
            "basis": basis}


def search(keyword: str, level: str = "小类", limit: int = 40) -> list[dict]:
    """按名称关键词查候选代码（默认只搜小类），辅助定位正确的四位码。"""
    kw = str(keyword).strip()
    out = []
    for code, rec in _load().items():
        if level and rec.get("level") != level:
            continue
        if kw and kw in rec.get("name", ""):
            out.append({"code": code, "name": rec["name"], "level": rec["level"]})
    out.sort(key=lambda x: x["code"])
    return out[:limit]


def _selftest() -> None:
    # 标准示例：内河货物运输 5523 -> WSA35523
    r = encode("5523")
    assert r["ok"] and r["wsa"] == "WSA35523", r
    # 采矿业在范围内：煤炭 0610 -> WSA30610
    assert encode("0610")["wsa"] == "WSA30610"
    # 商贸制造在范围内：无机碱制造 2612 -> WSA32612
    assert encode("2612")["wsa"] == "WSA32612"
    # 拒绝非四位/非小类/不存在
    assert not encode("06")["ok"]        # 大类
    assert not encode("552")["ok"]       # 中类
    assert not encode("9999")["ok"]      # 不存在
    assert not encode("55")["ok"]
    # search 能定位
    hits = {h["code"] for h in search("内河货物运输")}
    assert "5523" in hits
    print("selftest OK")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="行业事故类型编码 WSA3XXXX（GB 6441-2025 第5章）")
    p.add_argument("--code", help="GB/T4754 四位小类代码，如 5523")
    p.add_argument("--search", help="按名称关键词查候选小类")
    p.add_argument("--json", action="store_true", help="以JSON输出")
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()

    if a.selftest:
        _selftest()
    elif a.search:
        res = search(a.search)
        if a.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            if not res:
                print("无匹配小类。")
            for h in res:
                print(f"  {h['code']}  {h['name']}")
    elif a.code:
        res = encode(a.code)
        if a.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        elif res["ok"]:
            print(f"编码：{res['wsa']}")
            print(f"行业：{res['name']}（小类{res['code']}）")
            print(f"依据：{res['basis']}")
        else:
            print(f"失败：{res['error']}")
            print(f"提示：{res['hint']}")
    else:
        p.print_help()
