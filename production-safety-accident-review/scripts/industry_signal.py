#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行业信号闸门（确定性，离线）：只回答"输入里有没有行业线索"，不回答"是哪个行业"。

定位（重要，别用错）：
  本件**只阻止答案、不提供答案**。它不判定行业——那是模型据 references/05 做的语义活。
  它判定的是**输入文本的性质**（有没有行业指示词），这是关于文本、不是关于世界的事实，
  故可确定性检测、无需任何企业名录。同一段文字，它每次给同样的结论。

为什么需要它：references/05 §19/§29 已规定"通用设备不足以定唯一行业→列候选"，但该规则的
  触发条件是"①②皆无信号"，而**模型在无信号时未必自认无信号**（凭印象补出一个单位主营，
  于是自认"②明确"，规则不触发）。把这个判断从"模型自觉"改为"代码路由"，输出才稳定。

两个功能：
  scan   —— 扫警情全文与单位名称，判定是否"信号真空"。真空 → 强制走候选分支，禁止唯一小类。
  verify —— 校验"单位主营"这一栏能否在输入里找到**逐字出处**（references/00 来源限定的机械执行）。
            抄不出即无源，必须填"未掌握"。这是模型想做也做不到的检查，不依赖它自我反省。

数据来源（全部是技能已有的通用词表，不含任何案例知识）：
  · 行业指示词 = GB/T 4754-2017 码库（scripts/data/gbt4754.json）里各级行业名称自带的词汇；
  · 通用设备词 = references/05 §19 明文列出的词表（升降平台/起重/行车/叉车/…）；
  · 单位名称信号 = 复用 scripts/classify_org.py。

用法：
  python3 industry_signal.py scan --text "<警情全文>" [--name "<单位全称>"]
  python3 industry_signal.py verify --claim "<拟填入单位主营的内容>" --text "<警情全文>" [--name "<单位全称>"]
"""
from __future__ import annotations

import json
import os
import re

_DATA = os.path.join(os.path.dirname(__file__), "data", "gbt4754.json")

#: references/05 §19 明文的通用设备/动作词——多行业通用，**不足以定到唯一行业**，
#: 但指向"制造业(C)/仓储物流/建筑业(E)"一类实体重工行业（据此列候选，见 §29）。
GENERIC_EQUIPMENT = ("升降平台", "起重", "行车", "叉车", "货车", "脚手架", "电焊机", "装卸搬运")

#: references/05 §18 明文举例的行业指示词。国标码库的名称多为"印染精加工"这类长词，
#: 而警情里写的是"印染"，长词匹配不上，故把文档已列的短词一并纳入。二者都只是搬运
#: 技能自有的通用词表，不新增任何词。
DOC_INDICATORS = ("冶炼", "焊接装配", "印染", "光伏安装", "矿井开采", "货物运输", "餐饮后厨", "窑炉", "货架仓储")

#: 名号噪声词（与 classify_org._NOISE 同源）：公司名里的这些词不含行业指示。
NAME_NOISE = ("实业", "集团", "发展", "科技", "投资", "控股", "管理", "企业", "商务", "国际", "环保", "新能源")

_VOCAB = None


def _vocab() -> set[str]:
    """从 GB/T4754 码库的行业名称里抽出行业词汇。国标自带，非人工编纂。"""
    global _VOCAB
    if _VOCAB is None:
        with open(_DATA, encoding="utf-8") as f:
            codes = json.load(f)["codes"]
        v = set(DOC_INDICATORS)
        for rec in codes.values():
            for tok in re.split(r"[、，（）()和及与\s]+", rec.get("name", "")):
                tok = tok.strip()
                if len(tok) >= 2:
                    v.add(tok)
        _VOCAB = v
    return _VOCAB


def _name_signal(name: str) -> list[dict]:
    """复用 classify_org 判单位名称有无行业信号（不在此重复实现启发式）。"""
    if not name:
        return []
    try:
        from classify_org import classify
    except ImportError:  # 被别处 import 时的兜底
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from classify_org import classify
    r = classify(name)
    return r.get("行业候选", []) if r.get("ok") else []


def scan(text: str, name: str = "") -> dict:
    """扫描输入，判定是否信号真空。真空 → 强制走 references/05 §29 的候选分支。"""
    text = (text or "").strip()
    name = (name or "").strip()
    if not text:
        return {"ok": False, "error": "警情文本为空。"}

    # ① 事故经过里的行业指示词（用国标行业词汇表找；公司名单独走②，此处从全文找）
    hits = sorted((w for w in _vocab() if w in text), key=len, reverse=True)
    equip = [w for w in GENERIC_EQUIPMENT if w in text]
    # ② 单位名称的行业信号
    name_cands = _name_signal(name)
    noise = [w for w in NAME_NOISE if w in name]

    vacuum = (not hits) and (not name_cands)

    if vacuum:
        verdict = "疑似信号真空"
        action = ("① 事故经过与 ② 单位名称都没扫到行业指示词。**下一步必须跑 `verify` 校验你拟填入"
                  "『单位主营』的内容有没有逐字出处**——本 scan 的词表有局限（可能漏词），"
                  "verify 才是判准：verify 说无出处，则『单位主营』只能填'未掌握'，"
                  "并**禁止给出唯一四位小类与确定的 WSA 编码**，改按 references/05 §29 列候选、"
                  "注明'待定到唯一行业后出码'、提示需补充单位主营确认。"
                  "注意：主营'未掌握' ≠ 行业'无法判断'，候选仍要列（§30 只在连候选都列不出时才用）。")
        if equip:
            action += f" 经过含通用设备/动作线索 {equip}，据 §19 可据此收窄候选范围。"
    else:
        verdict = "有行业信号"
        action = ("按 references/05 判据①②正常判定。注意：②公司名**绝不单独定案**，须回到①事故经过印证；"
                  "①②矛盾时以①为准。『单位主营』一栏仍须按 references/00 填写逐字出处（可用 `verify` 自查）。")

    return {
        "ok": True,
        "信号真空": vacuum,
        "判定": verdict,
        "应做": action,
        "经过_行业指示词": hits[:12],
        "经过_通用设备词": equip,
        "名称_行业候选": [f"{c['管理分类']}／大类{c['大类']}（据'{c['matched']}'，{c['confidence']}）" for c in name_cands],
        "名称_噪声词": noise,
    }


def verify(claim: str, text: str, name: str = "") -> dict:
    """校验拟填入『单位主营』的内容能否在输入里找到逐字出处（references/00 来源限定）。

    合法来源只有：警情原文、单位名称。（第三个来源"纳统情形自带的行业"由模型注明条款，不在此校验。）
    抄不出 → 无源 → 该栏只能填"未掌握"。
    """
    claim = (claim or "").strip()
    if not claim:
        return {"ok": False, "error": "claim 为空。"}
    hay = (text or "") + "\n" + (name or "")

    # 把 claim 切成词，逐个查是否在输入里出现过
    toks = [t.strip() for t in re.split(r"[、，,；;。\s（）()／/]+", claim) if len(t.strip()) >= 2]
    grounded = [t for t in toks if t in hay]
    ungrounded = [t for t in toks if t not in hay]

    ok_src = bool(grounded)
    return {
        "ok": True,
        "有出处": ok_src,
        "可在输入中找到的片段": grounded,
        "在输入中找不到的片段": ungrounded,
        "判定": (
            "有出处：上述片段可在警情原文或单位名称中逐字找到，可填入『单位主营』并在出处列抄录。"
            if ok_src else
            "**无出处**：claim 里没有任何片段能在警情原文或单位名称中找到。据 references/00 来源限定，"
            "『单位主营』只能填\"未掌握\"——对该单位经营范围的既有印象／记忆，以及\"据了解／经查／"
            "根据其主营业务判断\"一类表述，都不是合法来源。随后按 references/05 §29 列候选。"
        ),
    }


def _selftest() -> None:
    # --- scan：真空识别。**三条各用不同的通用设备词与名号噪声词**——若只有第一条过、
    #     后两条不过，说明规则被某一组词拟合了，而不是学到了"无行业信号"这个通用性质。
    for text, name, equip_word, noise_word in (
        ("某公司院内，一人被简易升降平台压伤致死。", "某某实业有限公司", "升降平台", "实业"),
        ("某公司院内搭设作业，一人自脚手架跌落致死。", "某某控股有限公司", "脚手架", "控股"),
        ("某公司院内，一名工人在指挥叉车倒车时被碾压致死。", "某某发展有限公司", "叉车", "发展"),
    ):
        r = scan(text, name)
        assert r["信号真空"] is True, (text, r)
        assert equip_word in r["经过_通用设备词"], (text, r)
        assert noise_word in r["名称_噪声词"], (name, r)

    # --- scan：连通用设备词都没有的真空（不靠设备词也要能判真空）
    r0 = scan("某公司院内，一人被高处坠落物砸中致死。", "某某国际有限公司")
    assert r0["信号真空"] is True and not r0["经过_通用设备词"], r0

    # --- scan：名称自带行业词 → 有信号
    r2 = scan("某公司生产车间，一名工人操作机具时受伤致死。", "某某家具制造有限公司")
    assert r2["信号真空"] is False, r2

    # --- scan：经过里有行业词、名称是噪声词 → 有信号
    #     （"印染"来自 references/05 §18 的举例词表；国标码库里是"印染精加工"，短词匹配不上，
    #      所以 DOC_INDICATORS 必须并入词表，否则此例会被误判为真空）
    r3 = scan("某公司印染车间，一名工人跌入染缸致死。", "某某发展有限公司")
    assert r3["信号真空"] is False, r3
    assert "印染" in r3["经过_行业指示词"], r3

    # --- verify：抄得出 → 有出处
    v1 = verify("家具制造", "某公司生产车间…", "某某家具制造有限公司")
    assert v1["有出处"] is True and "家具制造" in v1["可在输入中找到的片段"]

    # --- verify：抄不出 → 无源。这正是"凭印象补主营"会撞上的闸门，
    #     也是本件的核心：它要求一个**会机械失败的动作**（把出处抄出来），而非模型自我反省。
    #     两条各编一套不同的主营，防的是"某一串词被记住"而非"无出处"这个性质。
    for claim, text, name in (
        ("精密轴承、齿轮减速机", "某公司院内，一人被简易升降平台压伤致死。", "某某实业有限公司"),
        ("食用菌培养基、灭菌设备", "某公司院内搭设作业，一人自脚手架跌落致死。", "某某控股有限公司"),
    ):
        v = verify(claim, text, name)
        assert v["有出处"] is False, (claim, v)
        assert not v["可在输入中找到的片段"], (claim, v)

    # --- 自纠正：scan 词表漏词导致误判真空时，verify 能把它纠回来（scan 只提示、verify 才判准）
    text = "某公司甲醇精馏塔区，一名操作工检维修时中毒致死。"
    if scan(text, "某某发展有限公司")["信号真空"]:          # scan 可能漏掉"精馏"这类词
        v3 = verify("甲醇精馏", text, "某某发展有限公司")   # 但主营确有逐字出处
        assert v3["有出处"] is True, v3                     # → verify 放行，不会被误锁进候选分支

    print("selftest OK")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="行业信号闸门：只判输入有无行业线索，不判是哪个行业")
    sub = p.add_subparsers(dest="cmd")

    ps = sub.add_parser("scan", help="扫警情，判定是否信号真空")
    ps.add_argument("--text", required=True, help="警情全文")
    ps.add_argument("--name", default="", help="事故发生单位全称")
    ps.add_argument("--json", action="store_true")

    pv = sub.add_parser("verify", help="校验『单位主营』能否在输入里找到逐字出处")
    pv.add_argument("--claim", required=True, help="拟填入单位主营的内容")
    pv.add_argument("--text", required=True, help="警情全文")
    pv.add_argument("--name", default="", help="事故发生单位全称")
    pv.add_argument("--json", action="store_true")

    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()

    if a.selftest:
        _selftest()
    elif a.cmd == "scan":
        r = scan(a.text, a.name)
        if a.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        elif not r["ok"]:
            print(r["error"])
        else:
            print(f"判定：{r['判定']}")
            print(f"经过·行业指示词：{r['经过_行业指示词'] or '无'}")
            print(f"经过·通用设备词：{r['经过_通用设备词'] or '无'}")
            print(f"名称·行业候选：{r['名称_行业候选'] or '无'}")
            print(f"名称·噪声词：{r['名称_噪声词'] or '无'}")
            print(f"应做：{r['应做']}")
    elif a.cmd == "verify":
        r = verify(a.claim, a.text, a.name)
        if a.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        elif not r["ok"]:
            print(r["error"])
        else:
            print(f"有出处：{'是' if r['有出处'] else '否'}")
            print(f"能找到的片段：{r['可在输入中找到的片段'] or '无'}")
            print(f"找不到的片段：{r['在输入中找不到的片段'] or '无'}")
            print(f"判定：{r['判定']}")
    else:
        p.print_help()
