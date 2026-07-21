#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""表2 确定性拆行/定主体器：干净报告文本 → 表2 骨架 JSON（客户口径）。

产出（按客户口径的表2版式）：
  章节标题行：序号=N，整改要求=「（一）小标题」，其余列 "-"
  数据行：    序号=N.M，整改要求=原文，整改主体=该句的具名施动单位
  拆子行：    多个"具名单位"顿号并列时 → N.M-1 / N.M-2，第2行起整改要求="同上"

拆行规则（纯句法状态机，无模型）——需求口径：**按每段逐句拆分，每一句作为一条整改要求分行罗列**：
  · 每个句号(。)结束一句 → 一条整改要求 → 一行。不按主体合并、不按话题合并。
  · 句首有「具名主体 + 模态词(要/应/应当/须/必须)」→ 主体=该具名主体
  · 句首是光杆模态词(主语承前省，如「要健全…」「应完善…」)→ 仍是独立一行，
    主体**继承上一条的具名主体**——继承来的是上文原文真实出现过的，不是臆造、也不是从别处借的；
    并自报 warning 提示 LLM 复核，且泛称展开须与被继承那行保持一致。
  · 组首就没有主语 → 主体标「待定(LLM兜底)」，交 LLM 判定
  · 泛称主体(各…/本市…/全市…)不拆子行；具名公司并列才拆
评估内容/评估方式/佐证材料留空，由 LLM 后续填（真语义部分）。
产出含 _diagnostics（低置信度行/泛称待展开）供 LLM 兜底校验。
用法：python segment_table2.py <干净txt> [<输出json>]
"""
import re, sys, json

ORG = (r"(?:公司|集团|单位|部门|委员会|安委会|成员单位|国有企业|企业|工地|中心|"
       r"监理|站|局|队|院|所|厂|政府|委|办公室|项目部|班组|机构)")
MODAL = r"(?:要|应当|应|须|必须)"
# 无模态词时的兜底：句首『具名主体 + 常见动词』（如"市交通行政管理部门加强…"）
VERB = r"(?:加强|落实|督促|组织|开展|建立|完善|严格|持续|负责|推进|做好|强化|健全|按照)"
GENERIC = ("各", "全市", "全体", "本市", "所有", "有关", "相关", "其他", "全国", "全")
CN = "一二三四五六七八九十"

def get_chapter_lines(text):
    raw = text.splitlines()
    idx = [i for i, l in enumerate(raw) if l.strip() == "五、事故整改和防范措施"]
    if not idx:  # 兜底：模糊匹配正文标题（取最后一次）
        idx = [i for i, l in enumerate(raw) if re.match(r'^五、.*(整改|防范)', l.strip())]
    ci = idx[-1]
    return [l.strip() for l in raw[ci + 1:] if l.strip()]

def split_subsections(lines):
    """按 （X） 切组，并切出 小标题 / 正文。
    两种排版都要兼容（不同报告不一样，勿只按其一）：
      A) 小标题独占一行、无句号        → 该行余下部分即小标题，正文=后续行
      B) 小标题带句号、正文挤在同一行  → 以该行**第一个句号**切开，句号后并入正文
    以**物理行**为主信号、句号为辅——只按句号切会把 A 型报告的首条要求吞进标题。"""
    acc = []
    for l in lines:
        m = re.match(r'^（([一二三四五六七八九十])）(.*)$', l)
        if m:
            acc.append([m.group(1), m.group(2), []])
        elif acc:
            acc[-1][2].append(l)
    out = []
    for cn, first, rest_lines in acc:
        rest = "".join(rest_lines)
        i = first.find("。")
        if i >= 0:                       # B型：小标题带句号，正文挤在同一行
            out.append((cn, first[:i + 1], first[i + 1:] + rest))
            continue
        # 小标题可能跨行断在词中间（如"…安全管控措"+"施。"）：
        # 若下一句号很近、且句号前那段**不是要求句**(无具名主体+模态词)，则它是标题的尾巴
        j = rest.find("。")
        if 0 <= j <= 10 and subject_of(rest[:j + 1])[0] is None:
            out.append((cn, first + rest[:j + 1], rest[j + 1:]))
        else:                            # A型：小标题独占一行、无句号
            out.append((cn, first, rest))
    return out

def subject_of(sent):
    """句首『具名主体 + 模态词/动词』→ (主体, 置信度)；否则 (None,None)=无主语，续接上一行"""
    for pat, conf in ((MODAL, "high"), (VERB, "mid")):
        m = re.match(r'^(.{2,30}?' + ORG + r')' + pat, sent)
        if m and not re.search(r'[，。；]', m.group(1)):
            return m.group(1), conf
    return None, None

def is_generic(s):
    return s.startswith(GENERIC)

def split_subjects(subj):
    """具名单位的**顿号(、)并列** → 拆子行；泛称短语 → 整体不拆。
    只认顿号：'属地政府及市安委会有关成员单位'用'及'连接，属同一主体整体，不拆。"""
    parts = [p.strip() for p in subj.split("、") if p.strip()]
    if len(parts) >= 2 and all(re.search(ORG + r'$', p) and not is_generic(p) for p in parts):
        return parts
    return [subj]

def parse(text):
    subs = split_subsections(get_chapter_lines(text))
    rows, warn = [], []
    for gi, (cn, heading, body) in enumerate(subs, start=1):
        rows.append({"no": str(gi), "requirement": f"（{cn}）{heading}",
                     "subject": "-", "content": "-", "method": "-", "materials": "-", "note": ""})
        k, cur_subj, cur_no = 0, None, None
        for sent in re.findall(r'[^。]+。', body):
            subj, conf = subject_of(sent)
            inherited = False

            if subj is None:
                if cur_subj is None:     # 组首就没有具名主体 → 交 LLM 兜底
                    k += 1
                    rows.append({"no": f"{gi}.{k}", "requirement": sent, "subject": "待定(LLM兜底)",
                                 "content": "", "method": "", "materials": "", "note": ""})
                    warn.append(f"未识别到具名主体,需LLM判定:{gi}.{k} {sent[:24]}")
                    continue
                if not re.match(r'^' + MODAL, sent):
                    # 句首不是模态词（而是动词/连接词/状语，如「采取…」「进一步…」「在此基础上…」）
                    # → 它是上一条的延续，不是新的整改要求 → 并入上一行。
                    # 依据：客户口径把「…。进一步督促…。对发现的…。在此基础上，形成…。」合为一行。
                    rows[-1]["requirement"] += sent
                    continue
                # 句首是光杆模态词（「要…」「应…」）= 主语承前省略的**新**整改要求 → 独立成行，
                # 主体继承上一条的具名主体。继承来的是上文原文真实出现过的，不臆造、不从别处借。
                # 依据：客户口径对「A要X。A要Y。」切两行；此处唯一差别只是作者省略了重复主语。
                subj, conf, inherited = cur_subj, "high", True
            else:
                cur_subj = subj

            k += 1
            parts = split_subjects(subj)
            for idx, p in enumerate(parts, 1):
                no = f"{gi}.{k}" if len(parts) == 1 else f"{gi}.{k}-{idx}"
                rows.append({"no": no, "requirement": (sent if idx == 1 else "同上"), "subject": p,
                             "content": "", "method": "", "materials": "", "note": ""})
            if inherited:
                warn.append(f"主语承前省略,主体继承自 {cur_no}:{gi}.{k} 「{subj}」(泛称展开须与 {cur_no} 保持一致)")
            else:
                cur_no = f"{gi}.{k}"
                if conf == "mid":
                    warn.append(f"主体靠动词兜底识别(中置信度),请LLM复核:{gi}.{k} {subj}")
                if is_generic(subj) or "的" in subj:
                    warn.append(f"泛称/描述性主体,需结合报告展开为具体单位:{gi}.{k} {subj}")

    data_rows = [r for r in rows if r["subject"] != "-"]
    diag = {"章节数": len(subs), "总行数": len(rows), "数据行": len(data_rows),
            "章节标题行": len(subs), "warnings": warn or ["无"]}
    return {"table2": rows, "_diagnostics": diag}

if __name__ == "__main__":
    data = parse(open(sys.argv[1], encoding="utf-8").read())
    for r in data["table2"]:
        if r["subject"] == "-":
            print(f"\n【{r['no']}】{r['requirement']}")
        else:
            print(f"  [{r['no']}] 主体={r['subject']}")
            print(f"        要求={r['requirement'][:62]}{'…' if len(r['requirement'])>62 else ''}")
    print("\n诊断:", json.dumps(data["_diagnostics"], ensure_ascii=False))
    if len(sys.argv) > 2:
        json.dump(data, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
