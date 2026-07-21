#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
事故等级确定性判定。

依据：《生产安全事故报告和调查处理条例》（国务院令第493号）第三条，
      与《生产安全事故统计调查制度》主要指标解释第9条一致。

前置：本步是判定链的第三步，只有在第一步"确认为生产安全事故"、第二步"确认纳入
统计"之后才进入本步。非事故或不纳统的，不出等级。

设计目的：等级判定是"数值比阈值"，属可精确计算的部分，交由本脚本完成，不由模型
推断。模型负责从警情文本中语义抽取三个维度的数值后调用本脚本。

三个维度（任一达到更高级即升级，取最高）：
  1) 死亡人数（含下落不明）
  2) 重伤人数（含急性工业中毒；统计制度一般规则第21条，急性工业中毒计为重伤）
  3) 直接经济损失（单位：万元；1亿元 = 10000万元）—— 与人数并列，绝不可漏。

关键：区分"已知为0"与"未掌握"。
  - 已知数值传入具体数字（含0）。
  - 未掌握传入 None：该维度不参与定级，仅作"补充后可能上调"的提示。
  因为未知维度只会让严重程度上升、不会下降，所以按已知维度得到的等级是"下界"，
  补充未掌握维度后只可能上调、不会下调。警情文本常常不给经济损失数字，必须如实
  按未掌握处理，不能拿0冒充，否则会低估等级。

"以上"包括本数，"以下"不包括本数（第493号令原文）。
"""

from __future__ import annotations

_ORDER = ["一般", "较大", "重大", "特别重大"]  # 严重程度从低到高

_CLAUSE = {
    "特别重大": "《生产安全事故报告和调查处理条例》（国务院令第493号）第三条第（一）项",
    "重大": "《生产安全事故报告和调查处理条例》（国务院令第493号）第三条第（二）项",
    "较大": "《生产安全事故报告和调查处理条例》（国务院令第493号）第三条第（三）项",
    "一般": "《生产安全事故报告和调查处理条例》（国务院令第493号）第三条第（四）项",
}

_BAND_TEXT = {
    "死亡": {"特别重大": "死亡30人以上", "重大": "死亡10人以上30人以下",
             "较大": "死亡3人以上10人以下", "一般": "死亡3人以下"},
    "重伤": {"特别重大": "重伤100人以上", "重大": "重伤50人以上100人以下",
             "较大": "重伤10人以上50人以下", "一般": "重伤10人以下"},
    "直接经济损失": {"特别重大": "直接经济损失1亿元以上",
                     "重大": "直接经济损失5000万元以上1亿元以下",
                     "较大": "直接经济损失1000万元以上5000万元以下",
                     "一般": "直接经济损失1000万元以下"},
}


def _level_by_deaths(d: int) -> str:
    if d >= 30:
        return "特别重大"
    if d >= 10:
        return "重大"
    if d >= 3:
        return "较大"
    return "一般"


def _level_by_injuries(s: int) -> str:
    if s >= 100:
        return "特别重大"
    if s >= 50:
        return "重大"
    if s >= 10:
        return "较大"
    return "一般"


def _level_by_loss_wan(w: float) -> str:
    if w >= 10000:
        return "特别重大"
    if w >= 5000:
        return "重大"
    if w >= 1000:
        return "较大"
    return "一般"


def grade(deaths=None, serious_injuries=None, direct_loss_wan=None) -> dict:
    """
    返回事故等级判定结果（dict）。任一维度可传 None 表示"未掌握"。

    参数：
        deaths            死亡人数（含下落不明），非负整数或 None
        serious_injuries  重伤人数（含急性工业中毒），非负整数或 None
        direct_loss_wan   直接经济损失（万元），非负数或 None
    """
    # 校验已知维度。注意 bool 是 int 的子类，True/False 会被 isinstance(x,int) 放行
    # （True 当 1、False 当 0），须显式挡掉，避免把布尔误当人数定级。
    if isinstance(deaths, bool) or isinstance(serious_injuries, bool) or isinstance(direct_loss_wan, bool):
        raise ValueError("死亡/重伤/损失不接受布尔值（bool），请传非负数或 None。")
    if deaths is not None and (not isinstance(deaths, int) or deaths < 0):
        raise ValueError(f"死亡人数必须为非负整数或 None，收到：{deaths!r}")
    if serious_injuries is not None and (not isinstance(serious_injuries, int) or serious_injuries < 0):
        raise ValueError(f"重伤人数必须为非负整数或 None，收到：{serious_injuries!r}")
    if direct_loss_wan is not None:
        # 非数值字符串等直接 float() 会抛裸 ValueError（无上下文），转成友好报错。
        try:
            _loss = float(direct_loss_wan)
        except (TypeError, ValueError):
            raise ValueError(f"直接经济损失（万元）必须为非负数或 None，收到：{direct_loss_wan!r}")
        if _loss < 0:
            raise ValueError(f"直接经济损失（万元）必须为非负数或 None，收到：{direct_loss_wan!r}")

    known, unknown = {}, []
    if deaths is not None:
        known["死亡"] = _level_by_deaths(deaths)
    else:
        unknown.append("死亡人数")
    if serious_injuries is not None:
        known["重伤"] = _level_by_injuries(serious_injuries)
    else:
        unknown.append("重伤人数")
    if direct_loss_wan is not None:
        known["直接经济损失"] = _level_by_loss_wan(float(direct_loss_wan))
    else:
        unknown.append("直接经济损失")

    if not known:
        return {"ok": False,
                "error": "死亡、重伤、直接经济损失三个维度均未掌握，无法判定等级。",
                "hint": "至少需要一个维度的数值（含已知为0）。"}

    level = max(known.values(), key=_ORDER.index)
    drivers = [dim for dim, lv in known.items() if lv == level]
    provisional = bool(unknown)

    hit = "；".join(f"{dim}命中「{_BAND_TEXT[dim][level]}」" for dim in drivers)
    basis = f"依据{_CLAUSE[level]}，{hit}，判定为「{level}事故」。"
    if provisional:
        basis += (f"（注意：{'、'.join(unknown)}未掌握，未参与定级；本等级为在已知维度下的"
                  f"下界初判，补充上述维度后只可能上调、不会下调，须在研判说明中标注。）")

    return {
        "ok": True,
        "level": level,
        "provisional": provisional,
        "by_dimension": known,
        "unknown": unknown,
        "drivers": drivers,
        "basis": basis,
        "inputs": {"死亡人数": deaths, "重伤人数": serious_injuries,
                   "直接经济损失_万元": direct_loss_wan},
    }


def _fmt_num(v):
    return "未掌握" if v is None else v


def _format(r: dict) -> str:
    if not r.get("ok"):
        return f"无法判定等级：{r['error']}\n提示：{r['hint']}"
    i = r["inputs"]
    lines = [
        "事故等级判定",
        f"  输入：死亡 {_fmt_num(i['死亡人数'])}，重伤 {_fmt_num(i['重伤人数'])}，"
        f"直接经济损失 {_fmt_num(i['直接经济损失_万元'])}（万元）",
        f"  已知维度：{'，'.join(f'{k}→{v}' for k, v in r['by_dimension'].items())}",
    ]
    if r["unknown"]:
        lines.append(f"  未掌握：{'、'.join(r['unknown'])}")
    lines.append(f"  结论：{r['level']}事故" + ("（初判，可能上调）" if r["provisional"] else ""))
    lines.append(f"  依据：{r['basis']}")
    return "\n".join(lines)


def _selftest() -> None:
    # 三则样例：均1人死亡、其余未掌握 → 一般（初判）
    r = grade(deaths=1)
    assert r["level"] == "一般" and r["provisional"] and r["unknown"] == ["重伤人数", "直接经济损失"]
    # 经济损失单独驱动定级（人数为0）——证明不是只看人数
    assert grade(deaths=0, serious_injuries=0, direct_loss_wan=2000)["level"] == "较大"
    assert grade(direct_loss_wan=8000)["level"] == "重大"
    assert grade(direct_loss_wan=10000)["level"] == "特别重大"
    # 损失未掌握但描述重大财产损毁时，模型应传 None，不得传0；此处验证 None 不定损失维度
    r2 = grade(deaths=1, direct_loss_wan=None)
    assert "直接经济损失" not in r2["by_dimension"] and r2["provisional"]
    # 已知0 与 未掌握 区分：全已知0 → 一般且非初判
    r3 = grade(deaths=0, serious_injuries=0, direct_loss_wan=0)
    assert r3["level"] == "一般" and not r3["provisional"]
    # 人数阈值边界（以上含本数、以下不含本数）
    assert grade(deaths=2)["level"] == "一般"
    assert grade(deaths=3)["level"] == "较大"
    assert grade(deaths=10)["level"] == "重大"
    assert grade(deaths=30)["level"] == "特别重大"
    assert grade(serious_injuries=10)["level"] == "较大"
    assert grade(serious_injuries=50)["level"] == "重大"
    assert grade(serious_injuries=100)["level"] == "特别重大"
    # 损失阈值边界
    assert grade(direct_loss_wan=999)["level"] == "一般"
    assert grade(direct_loss_wan=1000)["level"] == "较大"
    assert grade(direct_loss_wan=5000)["level"] == "重大"
    # 多维取最高
    r4 = grade(deaths=2, serious_injuries=60, direct_loss_wan=100)
    assert r4["level"] == "重大" and r4["drivers"] == ["重伤"]
    # 三维全未掌握 → 无法判定
    assert not grade()["ok"]
    # 健壮性：bool 不被当作 int 放行（True 会被误当 1 人死亡）
    for bad in (True, False):
        try:
            grade(deaths=bad)
            assert False, "bool 应被拒"
        except ValueError:
            pass
    # 健壮性：非数值损失给友好 ValueError 而非裸 float() 报错
    try:
        grade(direct_loss_wan="很多")
        assert False, "非数值损失应被拒"
    except ValueError:
        pass
    print("selftest OK")


if __name__ == "__main__":
    import argparse
    import json

    p = argparse.ArgumentParser(
        description="事故等级确定性判定（国务院令第493号第三条）。未给的维度视为未掌握(None)。")
    p.add_argument("--deaths", type=int, default=None, help="死亡人数（含下落不明）；不传=未掌握")
    p.add_argument("--serious", type=int, default=None, help="重伤人数（含急性工业中毒）；不传=未掌握")
    p.add_argument("--loss", type=float, default=None, help="直接经济损失（万元）；不传=未掌握")
    p.add_argument("--json", action="store_true", help="以JSON输出")
    p.add_argument("--selftest", action="store_true", help="运行内置用例自检")
    a = p.parse_args()

    if a.selftest:
        _selftest()
    else:
        res = grade(a.deaths, a.serious, a.loss)
        print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else _format(res))
