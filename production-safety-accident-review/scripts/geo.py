#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
地名确定性归一（离线查表，不接任何在线 API）。

用途：把警情文本中"事故发生地点"归一到全国"省—地级—县级"三级行政区划及代码，
供地点记录与管辖统计单位判断（纳统一般规则第22条：由事故发生地应急管理部门统计）。
地点不参与事故分类/等级/行业领域三项结论。

分工：模型负责从警情中**语义抽取"事故发生地点"短语**（不要把单位名称如"某市某某公司"
当作地点），再调用本脚本做确定性归一；行政区划与代码由查表给出，不由模型臆断。

数据：scripts/data/geo.json（由 build_geo.py 从《行政区划 截止2016年07月31日》抽取，
省31/地344/县2852）。数据截止2016-07-31，之后的区划调整（撤县设区等）以最新为准。
"""
from __future__ import annotations

import json
import os

_DATA = os.path.join(os.path.dirname(__file__), "data", "geo.json")
_G = None
_NAME_INDEX = None

# 地级占位名（直辖市/省直辖下的虚层），不作为可匹配地名，但保留用于链路上溯
_PLACEHOLDER = {"市辖区", "县", "省直辖县级行政区划", "直辖县", "自治区直辖县级行政区划"}

# 通用地域词型县名：**由纯方位/通用地域描述词构成**的区名（东/西/南/北·城/老城/新城/城关·
# 城东/城西/城南/城北·郊/矿/新市/市中 + 区），它们既是行政区名、又是常见泛地域说法。当归一**仅凭
# 它**定到某县、且文本没有"与归一一致"的省/市锚点时，可能是泛指而非确指该区（如"在老城区的工地"
# 未必指洛阳老城区、"在东区的工地"未必指攀枝花东区）。命中只**附核实提示、不改归一结果**。
# 成员按**语义**（是否纯方位/通用地域词）而非"库中是否唯一"来定：同名多个的（城区/郊区/市中区…）
# 会先走歧义分支被拦截、根本到不了提示；这里真正兜住的是"同名唯一被静默确指"的（老城区/东区/
# 西区/城东区/城西区/城北区/新市区）。含库中不存在的词（南区/城南区等）是无害的语义预留。
_GENERIC_AREA = frozenset({
    "城区", "郊区", "老城区", "新城区", "城关区", "矿区", "市中区",
    "东区", "西区", "南区", "北区", "城东区", "城西区", "城南区", "城北区", "新市区",
})


def _load():
    global _G, _NAME_INDEX
    if _G is None:
        with open(_DATA, encoding="utf-8") as f:
            _G = json.load(f)
        _NAME_INDEX = {}
        for code, rec in _G["codes"].items():
            if rec["name"] in _PLACEHOLDER:
                continue
            _NAME_INDEX.setdefault(rec["name"], []).append(code)
    return _G


def _codes():
    _load()
    return _G["codes"]


def _municipalities():
    return _load()["meta"]["municipalities"]


def _chain(code: str) -> dict:
    """从任意层级代码上溯，返回 {省:(code,name), 地:(code,name), 县:(code,name)}（有则填）。"""
    codes = _codes()
    out = {}
    node = code
    seen = set()
    while node and node in codes and node not in seen:
        seen.add(node)
        rec = codes[node]
        out.setdefault(rec["level"], (node, rec["name"]))
        node = rec["parent"]
    return out


def _find_free(text, name, consumed):
    """返回 name 在 text 中不与已占用文本段重叠的首个出现位置，无则 -1。"""
    start = 0
    while True:
        i = text.find(name, start)
        if i < 0:
            return -1
        s, e = i, i + len(name)
        if not any(s < ce and cs < e for cs, ce in consumed):
            return i
        start = i + 1


def _surviving_names(text: str) -> list:
    """最长匹配：按名称长度降序占用文本段，抑制被长地名包含的短地名（如'河东区'内的'东区'）。"""
    _load()
    names = sorted((n for n in _NAME_INDEX if n in text), key=lambda n: -len(n))
    consumed, keep = [], []
    for n in names:
        idx = _find_free(text, n, consumed)
        if idx >= 0:
            consumed.append((idx, idx + len(n)))
            keep.append(n)
    return keep


def _hits(names: list, level: str) -> list:
    """从已存活地名中取某层级的 (code, name)。"""
    res = []
    for n in names:
        for c in _NAME_INDEX.get(n, []):
            if _codes()[c]["level"] == level:
                res.append((c, n))
    return res


def normalize(text: str) -> dict:
    """
    归一"事故发生地点"短语。返回：
        ok, 省/地级/县级（各为 {code,name} 或 None）, 是否直辖市,
        ambiguous, candidates（歧义时列出候选链）, remainder（县级以下残余文本）,
        basis（管辖依据）, note（提示）
    """
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "地点文本为空。"}

    names = _surviving_names(text)
    prov = _hits(names, "省")
    pref = _hits(names, "地")
    county = _hits(names, "县")

    prov_codes = {c for c, _ in prov}
    pref_codes = {c for c, _ in pref}

    def _consistent(county_code):
        ch = _chain(county_code)
        p = ch.get("省", (None,))[0]
        d = ch.get("地", (None,))[0]
        if prov_codes and p not in prov_codes:
            return False
        if pref_codes and d not in pref_codes:
            return False
        return True

    resolved_code, level_resolved = None, None

    if county:
        cand = [c for c, _ in county]
        if len(cand) > 1:
            filtered = [c for c in cand if _consistent(c)]
            cand = filtered if filtered else cand
        cand = list(dict.fromkeys(cand))
        if len(cand) == 1:
            resolved_code, level_resolved = cand[0], "县"
        else:
            # 仍歧义：列候选链，交人工/上游补充省市
            candidates = []
            for c in cand[:12]:
                ch = _chain(c)
                candidates.append({
                    "县级": {"code": c, "name": _codes()[c]["name"]},
                    "省": _fmt(ch.get("省")), "地级": _fmt_pref(ch),
                })
            return {"ok": False, "ambiguous": True, "candidates": candidates,
                    "note": f"县级地名有 {len(cand)} 个同名候选，文本未提供可判定的省/市，需补充上级行政区。"}
    elif pref:
        resolved_code, level_resolved = pref[0][0], "地"
    elif prov:
        resolved_code, level_resolved = prov[0][0], "省"
    else:
        return {"ok": False, "ambiguous": False,
                "note": "未在文本中识别到省/地级/县级行政区划名，请确认地点或标'待核实'。"}

    ch = _chain(resolved_code)
    prov_t = ch.get("省")
    is_muni = bool(prov_t and prov_t[0] in _municipalities())
    pref_out = _fmt_pref(ch)  # 直辖市占位地级→None

    result = {
        "ok": True,
        "ambiguous": False,
        "是否直辖市": is_muni,
        "省": _fmt(prov_t),
        "地级": pref_out,
        "县级": _fmt(ch.get("县")),
        "解析层级": level_resolved,
        "remainder": _remainder(text, ch, prov + pref + county),
    }
    loc = "·".join(x["name"] for x in (result["省"], result["地级"], result["县级"]) if x)
    result["basis"] = (f"事故发生地归一为「{loc}」（{'直辖市' if is_muni else '一般省份'}），"
                       f"由该地应急管理部门负责统计（《生产安全事故统计调查制度》一般规则第22条）。")
    # 通用地域词型县名 + 无"与归一一致"的省/市锚点 → 归一可能是泛指，附核实提示（只提示、不改归一）。
    # 抑制条件看"锚点是否与归一一致"，不只看"有没有锚点"——否则文本给了**冲突**的省/市
    # （如"广东省老城区"仍被归一到河南洛阳）时，反而会把最该发的提示抑制掉。
    if level_resolved == "县":
        cn = (result["县级"] or {}).get("name", "")
        if cn in _GENERIC_AREA:
            rp = ch.get("省", (None,))[0]
            rd = ch.get("地", (None,))[0]
            consistent_anchor = (rp in prov_codes) or (rd in pref_codes)
            if not consistent_anchor:
                result["注意"] = (f"「{cn}」既是行政区名、也是常见泛地域说法，且文本未给"
                                  f"（或所给与归一不一致的）省/市锚点；归一到「{loc}」系按同名唯一区"
                                  f"推定，请据警情核实是否确指该区。")
    return result


def _fmt(t):
    return {"code": t[0], "name": t[1]} if t else None


def _fmt_pref(chain: dict):
    """地级：若为直辖市占位层（名在占位集或省为直辖市），返回 None。"""
    d = chain.get("地")
    p = chain.get("省")
    if not d:
        return None
    if p and p[0] in _municipalities():
        return None
    if _codes()[d[0]]["name"] in _PLACEHOLDER:
        return None
    return {"code": d[0], "name": d[1]}


def _remainder(text, chain, hits):
    r = text
    for _, name in hits:
        r = r.replace(name, "")
    return r.strip("，,。 、-—") or None


def _selftest():
    # 直辖市（无地级层）
    r = normalize("北京市海淀区中关村大街")
    assert r["ok"] and r["省"]["name"] == "北京市" and r["县级"]["name"] == "海淀区"
    assert r["是否直辖市"] and r["地级"] is None, r
    # 仅给区名，唯一 → 上溯省
    r2 = normalize("天河区某小区")
    assert r2["ok"] and r2["省"]["name"] == "广东省" and r2["县级"]["name"] == "天河区"
    # 一般省份三级
    r4 = normalize("浙江省杭州市余杭区某路")
    assert r4["ok"] and r4["省"]["name"] == "浙江省" and r4["地级"]["name"] == "杭州市"
    # 同名区县歧义
    amb = normalize("河东区")
    assert not amb["ok"] and amb.get("ambiguous"), amb
    # 有省市则消歧
    fixed = normalize("天津市河东区")
    assert fixed["ok"] and fixed["县级"]["name"] == "河东区" and fixed["省"]["name"] == "天津市"
    # 通用地域词型县名(库中唯一:老城区/东区/城北区…) + 无一致省市锚点 → 附核实提示（不改归一）
    for loc0, cn0 in (("在老城区的工地", "老城区"), ("在东区的工地", "东区"), ("城北区某厂", "城北区")):
        ra = normalize(loc0)
        assert ra["ok"] and ra.get("注意") and ra["县级"]["name"] == cn0, (loc0, ra)
    # 有"与归一一致"的省/市锚点(洛阳市) → 确指，不提示
    assert "注意" not in normalize("洛阳市老城区某厂")
    # 锚点与归一冲突(文本"广东省"、归一到河南洛阳) → 不能抑制提示，反而要提示（C-4）
    r_conf = normalize("广东省老城区某厂")
    assert r_conf["ok"] and r_conf.get("注意"), r_conf
    # 普通具体区名不触发提示
    assert "注意" not in normalize("浙江省杭州市余杭区某路")
    print("selftest OK")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="地名确定性归一（离线，省—地级—县级）")
    p.add_argument("--loc", help="事故发生地点短语")
    p.add_argument("--json", action="store_true")
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    if a.selftest:
        _selftest()
    elif a.loc:
        res = normalize(a.loc)
        if a.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        elif res["ok"]:
            loc = "·".join(x["name"] for x in (res["省"], res["地级"], res["县级"]) if x)
            print(f"归一：{loc}" + ("（直辖市）" if res["是否直辖市"] else ""))
            if res["remainder"]:
                print(f"县级以下：{res['remainder']}")
            print(f"依据：{res['basis']}")
            if res.get("注意"):
                print(f"注意：{res['注意']}")
        elif res.get("ambiguous"):
            print(f"地名歧义：{res['note']}")
            for c in res["candidates"]:
                loc = "·".join(x["name"] for x in (c["省"], c["地级"], c["县级"]) if x)
                print(f"  候选：{loc}")
        else:
            print(res.get("note", "无法归一"))
    else:
        p.print_help()
