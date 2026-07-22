#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""表3 确定性解析器：干净报告文本 → table3_groups JSON（客户口径·三级分组）。

按"四、处理建议"各小标题关键词分类，套 references/表3规则表.md 的模板，产出：
  组标题行(序号=N, 第2列=组名) + 子行(序号=N.1/N.2…)
  1 行刑衔接情况     ← ③刑事(全部人员合并为一行)，提供材料单位=办案的公安、检察院、法院
  2 行政处罚情况     ← ①行政处罚(逐个)，提供材料单位=被处罚方自己(个人取其所属单位)
  3 企业内部处理情况 ← ②内部处分(逐个)，提供材料单位=所属单位（固定第3组）
  (有则加 其他处理情况) ← ④其他主管部门(有则出现，排在企业内部处理之后)
「四、(一)不予追究责任」的人员不收录。同一人受多种处理→各组各列一次(不去重)。
纯代码、无模型；同一输入永远同一输出。产出含 _diagnostics 供 LLM 兜底校验。
用法：python parse_table3.py <干净txt> [<输出json>]
"""
import re, sys, json

UNIT_SUF = r"(?:公司|集团|单位|部门|委员会|委|中心|监理|站|局|部|队|院|所|厂|企业|政府)"

def get_chapter(text):
    i = [m.start() for m in re.finditer(r'四、[^\n。]*处理建议', text)][-1]
    js = [m.start() for m in re.finditer(r'五、[^\n。]*(整改|防范)', text) if m.start() > i]
    return text[i: js[0] if js else len(text)]

def split_subsections(chap):
    lines = [l.strip() for l in chap.splitlines() if l.strip()]
    subs, h, buf = [], None, []
    for l in lines:
        m = re.match(r'^（[一二三四五六七八九十]）(.*)$', l)
        if m:
            if h is not None: subs.append((h, "".join(buf)))
            h, buf = m.group(1).strip(), []
        elif h is not None:
            buf.append(l)
    if h is not None: subs.append((h, "".join(buf)))
    return subs

def split_items(body):
    idxs = [m.start() for m in re.finditer(r'\d+[\.、]', body)]
    if not idxs:
        return [body]
    return [body[st: (idxs[k + 1] if k + 1 < len(idxs) else len(body))] for k, st in enumerate(idxs)]

def is_unit(name):
    return bool(re.search(UNIT_SUF + r"$", name))

def unit_prefix(s):
    """'例如：××公司法定代表人、董事长' → '××公司'（优先到公司/集团级，避免被'局'截断）"""
    m = re.match(r'^(.+?(?:公司|集团))', s)
    if m: return m.group(1)
    m = re.match(r'^(.+?(?:委员会|监理单位|单位|部门|中心|监理|院|所|厂|局|站))', s)
    return m.group(1) if m else s

def person_of(item):
    b = re.sub(r'^\d+[\.、]\s*', '', item)
    m = re.match(r'^([^（：:。，]+)(?:（([^）]*)）)?', b)
    name = m.group(1).strip().rstrip('：:。，')
    affil = (m.group(2) or "").strip()
    return name, affil, name + (f"（{affil}）" if affil else ""), b

def find_agency(body, default="市应急局"):
    """从'建议市应急局对…依法予以行政处罚'现抽处罚机关，不写死地名。"""
    m = re.search(r'建议(?:由)?([^，。、]*?(?:应急管理局|应急局))对', body)
    return m.group(1) if m else default

def discipline_provider(affil, item):
    """②内部处分：条文点名单位 > 括号隶属单位(剥职务) > 兜底"""
    m = re.search(r'建议(?:由)?([^，。、]*?' + UNIT_SUF + r')给予', item)
    named = m.group(1) if m else ""
    if named and "所在企业" not in named and "所属" not in named:
        return named
    return unit_prefix(affil) if affil else "责任人所属单位"

MAT_CRIMINAL = "按案件最新阶段提供：侦查阶段→公安机关情况说明；审查起诉阶段→公安机关起诉意见书/不起诉意见书；审理阶段→检察机关起诉书/不予起诉决定书；判决阶段→法院判决书等。"
MAT_ADMIN = "1.政府部门出具的行政处罚决定书；\n2.罚款缴纳票据或执行人罚款付款凭证。"
MAT_DISC = "有关单位或其上级单位对责任人的处分扣款材料（决定/通知等）。"
MAT_OTHER = "相应主管部门对责任单位/人员依法依规处理的决定/情况材料。"
GROUP_TITLES = ("行刑衔接情况", "行政处罚情况", "企业内部处理情况", "其他处理情况")

def parse(text):
    chap = get_chapter(text)
    criminal, admin, disc, other = [], [], [], []
    agency, classified = "市应急局", []
    for heading, body in split_subsections(chap):
        if "不予追究" in heading:
            classified.append(f"{heading}→跳过(不予追究)"); continue
        if "刑事" in heading:
            classified.append(f"{heading}→刑事")
            for it in split_items(body):
                if re.match(r'^\d+[\.、]', it):
                    criminal.append(person_of(it)[2])
        elif "行政处罚" in heading:
            classified.append(f"{heading}→行政处罚")
            agency = find_agency(body, agency)
            for it in split_items(body):
                if re.match(r'^\d+[\.、]', it):
                    n, a, d, _ = person_of(it)
                    admin.append({"name": n, "affil": a, "disp": d})
        elif ("问责" in heading) or ("处分" in heading):
            classified.append(f"{heading}→内部处分")
            for it in split_items(body):
                if re.match(r'^\d+[\.、]', it):
                    n, a, d, b = person_of(it)
                    sug = re.search(r'(建议[^。]*?。)', b)
                    disc.append({"disp": d, "affil": a, "item": b, "sug": sug.group(1) if sug else b})
        else:
            classified.append(f"{heading}→其他主管部门")
            m = re.search(r'建议([^，。]*?(?:部门|局|委员会|政府))对([^，。]*?' + UNIT_SUF + r')', body)
            if m:
                other.append({"dept": m.group(1), "unit": m.group(2)})

    rows, gi = [], 0
    def hdr(title):
        nonlocal gi
        gi += 1
        rows.append({"no": str(gi), "person": title, "suggestion": "", "provider": "", "materials": "", "note": ""})
        return gi

    if criminal:
        g = hdr("行刑衔接情况")
        merged = " ".join(f"（{i}）{p}" for i, p in enumerate(criminal, 1))
        rows.append({"no": f"{g}.1", "person": merged,
                     "suggestion": "建议司法机关对前述人员依法实施刑事责任追究。",
                     "provider": "办案的公安、检察院、法院", "materials": MAT_CRIMINAL, "note": ""})
    if admin:
        g = hdr("行政处罚情况")
        for k, a in enumerate(admin, 1):
            prov = a["name"] if is_unit(a["name"]) else (unit_prefix(a["affil"]) if a["affil"] else a["name"])
            rows.append({"no": f"{g}.{k}", "person": a["disp"],
                         "suggestion": f"建议{agency}依法予以行政处罚。",
                         "provider": prov, "materials": MAT_ADMIN, "note": ""})
    # 客户口径 / references/表3规则表.md §二「务必遵守」：企业内部处理固定为第3组，
    # 其他处理情况"有则加"排在其后。故必须先发 disc(内部)、再发 other(其他)——hdr() 按
    # 发射先后给组号，两块顺序即决定组号(内部=3、其他=4)。切勿调换。
    if disc:
        g = hdr("企业内部处理情况")
        for k, d in enumerate(disc, 1):
            rows.append({"no": f"{g}.{k}", "person": d["disp"], "suggestion": d["sug"],
                         "provider": discipline_provider(d["affil"], d["item"]),
                         "materials": MAT_DISC, "note": ""})
    if other:
        g = hdr("其他处理情况")
        for k, o in enumerate(other, 1):
            rows.append({"no": f"{g}.{k}", "person": o["unit"],
                         "suggestion": f"建议{o['dept']}依法依规给予处理。",
                         "provider": o["dept"], "materials": MAT_OTHER, "note": ""})

    warn = []
    for r in rows:
        if r["person"] in GROUP_TITLES:
            continue
        if r["provider"] in ("责任人所属单位",) or "所在企业" in r["provider"]:
            warn.append(f"provider兜底未定位:{r['person'][:12]}")
        if r["suggestion"] and not r["suggestion"].startswith("建议"):
            warn.append(f"处理建议疑似未抽净:{r['person'][:12]}")
    diag = {"总行数": len(rows), "刑事人数": len(criminal), "行政处罚": len(admin),
            "其他部门": len(other), "内部处分": len(disc),
            "小标题分类": classified, "处罚机关(现抽)": agency, "warnings": warn or ["无"]}
    return {"table3_groups": [{"group_title": None, "rows": rows}], "_diagnostics": diag}


def _selftest():
    """回归：企业内部处理固定排在其他处理之前（客户口径 / 表3规则表.md §二「务必遵守」）。
    防"速度重构"或误改把两块顺序调回去。构造同时含"其他主管部门处理"和"企业内部处分"
    两组的最小虚构报告（全占位名，不含任何真实案例答案），断言相对顺序与组号。"""
    rpt = (
        "四、对有关责任人员及单位的处理建议\n"
        "（一）建议给予行政处罚的单位\n"
        "1. 某某有限公司，建议某某县应急管理局对某某有限公司依法予以行政处罚。\n"
        "（二）建议行业主管部门处理的单位\n"
        "建议某某县市场监督管理局对某某租赁有限公司依法依规给予处理。\n"
        "（三）建议企业内部处分的人员\n"
        "1. 某某，某某有限公司安全员，建议由某某有限公司给予其记过处分。\n"
        "五、事故整改和防范措施\n"
    )
    order = [(r["no"], r["person"]) for r in parse(rpt)["table3_groups"][0]["rows"]
             if r["person"] in GROUP_TITLES]
    names = [p for _, p in order]
    assert "企业内部处理情况" in names and "其他处理情况" in names, ("两组都应出现", order)
    # 相对顺序：内部必须排在其他之前（不依赖是否有刑事组，故用相对位置而非绝对组号3/4）
    assert names.index("企业内部处理情况") < names.index("其他处理情况"), \
        ("企业内部处理必须排在其他处理之前", order)
    numof = {p: int(n) for n, p in order}
    assert numof["企业内部处理情况"] < numof["其他处理情况"], ("组号应内部<其他", order)
    print("selftest OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        _selftest()
        sys.exit(0)
    data = parse(open(sys.argv[1], encoding="utf-8").read())
    for r in data["table3_groups"][0]["rows"]:
        if r["person"] in GROUP_TITLES:
            print(f"\n【{r['no']}】{r['person']}")
        else:
            print(f"  [{r['no']}] {r['person'][:44]}")
            print(f"       建议:{r['suggestion'][:32]} | 提供单位:{r['provider'][:24]}")
    print("\n诊断:", json.dumps(data["_diagnostics"], ensure_ascii=False))
    if len(sys.argv) > 2:
        json.dump(data, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
