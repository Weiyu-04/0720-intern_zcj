# 后评估小助手 & 事故研判助手 · 技能仓库 + 工作交接

> 这个仓库放的是「中城交智枢 / ZCJAgent」Agent 平台**应急指挥调度域**的两个技能。
> **本文件既是仓库说明，也是工作交接** —— 接手或新开会话继续工作前，**先通读本文件**。
> 平台本体（全栈 MainAgent）是另一个仓库，本仓库只含这两个**技能包**（`SKILL.md` + 脚本 + 参考 + 模板）。
> 最后更新：2026-07-21

---

## 0. 仓库里有什么

| 目录 | 技能 | 输入 → 输出 |
|---|---|---|
| `post-evaluation/` | **后评估小助手** | 《事故调查报告》→ 表2/表3 两张评估表，各出 **Word + Excel**（共 4 个文件）+ 展示思考过程 |
| `production-safety-accident-review/` | **事故研判助手** | 警情/事故快报文本 → 是否生产安全事故 / 是否纳统 / 等级 / 类型(GB6441-2025) / 行业领域编码。**输出是聊天文本，不产文件** |

两者互相独立、无依赖，可分开集成。都挂 `emergency-dispatch`（应急指挥调度）域。

---

## 1. 铁律（改任何东西前先记住）

1. **答案不泄漏**：后评估的 `5·6`、`12·22` 两案例的**已填好评估表 = 测试集**；研判的样例同理。技能里的知识只能来自规范/国标/指南定义 + 通用领域知识，**绝不能把案例答案写进技能**（`SKILL.md`/`references`/模板都不行）。客户样板 xlsx 只可用于对齐格式与规则，**不可抄其评估内容答案**。
2. **不过拟合**：对比范例是为发现"通用问题"，不是把输出调到和范例一致。只改通用规则，不做"某行就该输出某编号"的硬编码。要分清是"模型问题"还是"范例自己的选择"。
3. **代码管结构、LLM 管语义**（见 §5）：能确定性解析的一律用脚本；模型只做真语义判断 + 兜底校验。

---

## 2. 本轮（0720 会话）做了什么

在带教交接的基础上，这一轮针对**稳定性与规范**做了：

- **修 JSON 手写脆弱点**（后评估历史最大坑）：第4步曾让模型手写整份 `combined_data.json`，报告正文引号易写成未转义半角 `"`，`json.load` 只抛字节偏移 → agent 反复 `replace`/`sed` 打地鼠。改法：
  - 新增 `scripts/merge_tables.py`：从 `table2.json`+`table3.json` 用 `json.dump` 合并，**从源头免手写整份 JSON**；
  - 新增 `scripts/robust_json.py`：JSON 坏了给**定位到行 + 一次性正确做法**的处方式报错（**不静默改正文**）；`--fix` 才做启发式转义且须人工核对；
  - 第2/3步加**"填完立刻校验 JSON"闸**，坏了当场改、不带病往后走。
- **加 `allowed-tools` 白名单**（收窄工具面、禁掉自由发挥）：
  - `post-evaluation`：`[parse_document, bash, read_file, write_file, str_replace, present_files]`
  - `production-safety-accident-review`：`[bash, read_file, write_file]`（**刻意不含任何 web 工具**，从工具层坐实"绝不上网查主营"）
- **第1步取文本 = 两条对等路由**：①**文本型 PDF** → `extract_clean.py`（按字号剥脚注/页码）；②**扫描件/图片型 PDF / Word / 其它非 PDF** → `parse_document`(OCR) → **`md_to_clean.py`** 把 md 确定性清成正文。**两条路都经一道确定性清洗、都落到同一个 `clean_report.txt` 再进第2步**，下游拿到的输入对等。OCR 路残留脚注需人工补剔、且 OCR 可能认错字（见"已知局限"），故其第2/3步兜底校验要更严。
  - > 扫描件 PDF 的 OCR 由平台 `parse_document`（底层 MinerU）提供，**这属 MainAgent 部署侧配置，技能不管**。
- **description 规范化**：三个技能描述去跨技能引用、去实现泄露、触发改用用户可观测条件、各加排他边界（后评估↔研判互不越界）。
- **OCR 变体（曾建 `post-evaluation-ocr`）已移除**：它对编排模型没有独立可观测的触发点（"要不要走 OCR"是执行期才知道的事，用户不会这么说），与主技能触发不可区分、易挑花眼。扫描件能力保留在 `post-evaluation` 的 parse_document 回退分支里。
- **自查清除"模型够不到的引用"**：SKILL / references / 脚本注释里，凡指向模型看不见的东西——客户样本 xlsx 路径（含测试集案名「1222事故」，碰"答案不泄漏"铁律）、真实公司名当例子（绿地钢构/山东中诚）——全部删除或泛化（"客户样板"→"客户口径"、真名→"××公司"），并删掉无引用的 `.bak` 模板。**原则：SKILL.md 与 references/ 是喂给模型的，里面只能出现模型能读/能跑的自有文件或它懂的概念/法规，不能出现指向外部/历史文件的字眼。**

---

## 3. 当前状态 & 待办

技能能端到端跑通：**上传报告 → 产出 4 个文件 → 可在线预览/编辑/下载 → 展示思考过程**。

| 模块 | 状态 |
|---|---|
| 技能大脑（SKILL.md + 参考） | 完成，已按客户最新口径对齐 + 本轮规范化 |
| 确定性脚本 | 完成，两案例验证通过，输出稳定（md5 恒定） |
| 4 文件产出（docx + xlsx） | 完成，版式对齐客户样板 |
| OnlyOffice 预览/在线编辑/下载 | 完成，浏览器已验收 |
| **新案例泛化验证** | **未做 ← 最大风险（见下）** |

**待办（按优先级）**：
1. **新案例泛化验证（演示前必做）**：目前只在 `5·6`、`12·22` 上验过，而 `12·22` 是调试样本。拿一份**没见过的报告**跑一遍，重点看 `_diagnostics.warnings`（脚本自报没把握的行；失手时标 `待定(LLM兜底)`，不静默输出垃圾）。
2. **表3 真实界面端到端复核**：表3 至今只做过内部直打模型测试，没走真实界面。
3. **技能正式上线方式待带教确认**：`skills/` 是 gitignored；平台代码里有 `POST /api/skills/upload?scope=public`（管理员上传 `.skill` 包），但那是从代码看到的机制，**须确认公司流程**。
4. **后续阶段**：表1（人工补，附盖章自评估报告）；评估报告生成（本期不做）。

**增强项**：
5. ✅ **（已完成）post-evaluation 并入 `md_to_clean.py`**：OCR 路（扫描件/Word/非 PDF）现在 `parse_document` 出 md 后**自动跑 `md_to_clean.py` 确定性清洗**（剥 `#`/`**`/表格/`[N]`/脚注定义/页码），和 PDF 路一样"先清洗再进第2步"，**清洗这一步两条路已对等**。残留差距（脚注按模式非字号剥、OCR 认错字）见"已知局限"。
6. **（未做）第1步加"乱码/有效性判定 → OCR 回退"**：见下"已知局限"。

> **⚠️ 输入处理已知局限（重要）**：`extract_clean.py` 只处理**版面噪声**（页码/脚注/断句），**不修字符层面的乱码**——PDF 内嵌字体的 ToUnicode 映射坏/缺时，抽出来是错字，脚本原样穿过（garbage in/out）。现路由只在 `extract_clean` 抽**空**（扫描件）时才退 `parse_document(OCR)`，**乱码 PDF 有文本层、非空 → 不触发回退**。好在乱码不会静默出错表（下游 `segment_table2`/`parse_table3` 找不到"五、事故整改""（一）"等中文锚点 → 产空骨架 → 模型兜底校验会发现），但要人工改走 OCR 才能修（OCR 认像素、绕过坏字体映射）。**根治办法 = 待办 6**：抽完自检"章节锚点缺失 + CJK 有效字符占比异常低 → 判乱码、和扫描件一样自动退 OCR"。

---

## 4. 架构：代码管结构，LLM 管语义

拆行/定主体/表3解析这类**句法结构**任务用**确定性代码**（模型做会 9/13/6/13 行乱跳）；模型只做**真语义**（评估内容匹配 42 条特征库）。**代码为主 + LLM 强制兜底校验**：代码遇没见过的格式会失手，故**自报 `_diagnostics.warnings`**，由 LLM 对照原文抓漏补错。兜底是"敢用代码"的前提，也是防过拟合的解药。

**后评估流水线**（`post-evaluation/scripts/`）：
```
第1步 extract_clean   PDF→干净正文（剥页码/脚注；扫描件退 parse_document）
第2步 segment_table2  表2骨架(序号/拆子行/主体) → LLM 校验 warnings + 填评估内容/方式
第3步 parse_table3    表3三级分组全解析          → LLM 校验 warnings
      merge_tables    合并两份分表 JSON（免手写）
      robust_json     JSON 校验闸/处方式报错
第4步 generate_tables 出 4 个文件 → present_files 全部交付 + 思考过程
```

**泛化要点（改代码前必读，勿只按一份报告调）**：
- **小标题三种排版**：A型独占一行无句号 / B型带句号正文挤同行 / 跨行断在词中。已用「物理行为主+句号为辅+判断句号前是否要求句」兼容。只按句号切会把首条要求吞进标题。
- **拆子行只认顿号「、」不认「及」**（"属地政府及市安委会成员单位"是一个整体主体）。
- **主体识别** = 具名主体 + 模态词(要/应/应当/须)；无模态词用动词兜底并标**中置信度**交 LLM 复核。
- **泛称展开**（"各相关单位"→具体单位）与**名称规范化**由 LLM 做，代码只标出来。

研判助手（`production-safety-accident-review/`）：五步闸门链（是否事故→纳统→等级→类型→行业领域），`grade.py`/`encode.py`/`geo.py`/`industry_signal.py` 做确定性计算，`data/` 下 `gbt4754.json`（1381 小类）+ `geo.json`（全国省地县）是硬依赖。**全程离线、不联网查主营**（`industry_signal.py` 闸门：无出处只能填"未掌握"、列候选）。

---

## 5. 客户口径（**最高优先依据**）

样板：`表2和表3-【1222事故】-增加地标对应列.xlsx`（客户 2026-07-16 提供，优先级高于旧范例）。"地标对应列" = 评估内容/评估方式，对应地标《后评估指南》**附录A**。⚠️ 它是 12·22 的**填好答案（测试集）**——只对齐格式规则，**不抄答案**。

**表2（8 列）** `序号|整改要求|整改主体|评估内容|评估方式|佐证材料|整改情况|说明`
- 章节标题 (一)(二)(三) 单独成行：序号=1/2/3、整改要求=小标题、**其余列 `-`**
- 数据行 `N.M`；多个具名单位并列 → 拆子行 `N.M-1/N.M-2`，第2行起整改要求写「同上」
- **整改要求**：逐字照录、脚本产出、**模型一字不许改**（曾出现模型"顺手精简"删句的严重错误）
- **评估内容**：填「编号 + 附录A 条目原文」；**客户明确：匹配度 30-50% 即可**，不必过度纠结
- **评估方式**：查速查表、合并去重　·　**佐证材料**：客户「先空着后续开发」，本期非重点　·　**整改情况**：留空，三档

**表3（7 列 + 三级分组）** `序号|事故责任人员/单位(括号内隶属单位)|处理建议|提供材料单位|佐证材料|处理情况|说明`

| 组 | 内容 | 提供材料单位 |
|---|---|---|
| 行刑衔接情况 | ③刑事，**全部人员合并为一行** | 办案的公安、检察院、法院 |
| 行政处罚情况 | ①行政处罚，逐个 | **被处罚方自己**（个人取所属单位）— **不是市应急局**（它只是处罚机关）|
| （其他处理情况）| ④其他主管部门（有则出现）| 相应主管部门 |
| 企业内部处理情况 | ②内部处分，逐个 | 责任人所属单位 |

- 「不予追究责任」的人员（如已死亡）**不列入**　·　同一人受多种处理 → **各组各列一次，不去重**　·　处理情况留空，三档

---

## 6. 集成到平台（MainAgent 侧）

- **放哪**：解压到 `MainAgent/backend/skills/public/` 下，**保持目录名不变**（目录名即技能名，`domains.json` 靠它引用）。技能自动发现（`os.walk` 扫到 `SKILL.md` 即收），public 技能默认 enabled。
- **挂菜单**：改 `backend/skills/domains.json`，在 `emergency-dispatch` 域下填槽位 `skill_name`（`post-evaluation` / `production-safety-accident-review`）。**先解压目录再改 domains.json**（反了会触发 `_null_orphans()` 把 `skill_name` 静默置 null）。
- **硬前提**：
  - `config.yaml` 的 `sandbox.allow_host_bash: true`（example 默认 false；两个技能都跑 python 脚本，false 则全废）。
  - `frontend/next.config.js` 的 `experimental.proxyClientMaxBodySize: "80mb"`（上传代理默认 10MB，事故报告 PDF 可 >15MB，不改传不上）。
  - **python 依赖**：`post-evaluation` 需 `python-docx / openpyxl / PyMuPDF`；`production-safety-accident-review` 零依赖（纯标准库）。技能跑的 `python` 取决于 PATH（带教机为 `/opt/miniconda3/bin/python`，三包齐全）。
- **别只拷 .py**：`production-safety-accident-review/scripts/data/` 下两个 json 与 `post-evaluation/templates/` 下 docx 模板是硬依赖。
- 改技能后**必须新建对话**（旧对话用旧系统提示，不生效）。

---

## 7. 起服务 & 测试

**起服务坑**：项目路径含中文，`uv run` 会因 `.pth` 解码中文路径失败/并发重装崩 → **不要用 `uv run`，直接用 `.venv/bin/python`** + 显式 `PYTHONPATH` + UTF-8 环境变量。
```bash
cd MainAgent/backend
set -a && source ../.env && set +a
LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 PYTHONIOENCODING=utf-8 PYTHONUTF8=1 PYTHONPATH=".:packages/harness" \
  .venv/bin/python -m uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001 --reload
# 前端：cd MainAgent/frontend && pnpm dev（:3000）　OnlyOffice 容器 :8080
```

**只测确定性部分（不花模型钱、秒出）**：
```bash
python post-evaluation/scripts/extract_clean.py  <PDF> clean.txt
python post-evaluation/scripts/segment_table2.py clean.txt t2.json   # 看 _diagnostics
python post-evaluation/scripts/parse_table3.py   clean.txt t3.json
python post-evaluation/scripts/merge_tables.py   t2.json t3.json combined.json
python post-evaluation/scripts/generate_tables.py combined.json out/  # 出 4 文件
```
**界面端到端**：localhost:3000 →「应急指挥调度」→ 对应技能 → **必须新建对话** → 上传 PDF → 看思考过程 + 4 文件。
> ⚠️ 会话临时目录（scratchpad）的中间文件**会随会话消失**，要保留的放进项目里。

---

## 8. 踩过的坑（省时间用）

| 坑 | 真相 |
|---|---|
| **JSON 打地鼠**（改一处引号又冒一处） | 别逐条 `replace`/`sed`——引号遍布全文改不完。用 `merge_tables.py` 重新生成，或把源头引号改全角；`robust_json.py` 会给处方式报错 |
| **模型把原文"顺手精简"了** | SKILL 已钉死列归属：序号/整改要求归脚本，模型只能改 主体/评估内容/评估方式/佐证材料 |
| **max_tokens 给小了** | reasoning 吃光额度 → JSON 截断 → 正文为空。给 ≥32000 |
| **改了技能却没生效** | 旧对话用旧系统提示，**必须新建对话** |
| **网页历史对话消失** | 摘要中间件 `RemoveMessage` 从 state 真删消息（界面读的就是 state）。根因：系统提示词占 ~25.5k 且每轮重发，按阈值 32000 只剩 ~6.5k 给对话 → 两三轮就摘要。已上调 `summarization.trigger` 32000→80000、`keep` 10→40（per-run，改完下条消息即生效，不用重启）。**sqlite 里数据都在，不是真丢** |
| **OnlyOffice 报"无权限操作"** | 与权限/JWT 无关，真凶是**文档 key 太长**（中文名 json 转义每字 6 字符破 300，OnlyOffice ≤128）。已修成 32 字符摘要。排查一律先 `docker logs onlyoffice-ds`，前端报错不可信 |

> **摘要阈值 80k 的未解风险**：查不到默认模型 `deepseek-v4-flash` 的上下文窗口。若模型上下文 < 80k 会在摘要触发前就 `context length exceeded` → 改回 32000，或用 `type: fraction, value: 0.8`（按模型上限比例、换模型也安全）。**更根本**：25.5k 系统提示每轮重发是浪费（判别特征库 42 条占大头、只匹配那步用），可改成按需 `read_file` 读 references，固定开销降到几 k。

---

## 9. MainAgent 侧参考

- MainAgent 远程：`git@codeup.aliyun.com:zcjsh/Products/TongDaAgent/MainAgent.git`；技能所在分支 `feature/post-evaluation-assistant`（基于 **EMB**，合并目标 EMB，**不是 main**）。`config.yaml`/`.env`/`skills/` 均 git 忽略。
- 默认模型 `deepseek-v4-flash` @ `https://llm.zcjsh.com/v1`（`$DEEPSEEK_API_KEY` 在 `.env`），`temperature: 0.2`。
- OnlyOffice 用官方镜像 `onlyoffice/documentserver:9.3.1` 原版、仅环境变量配置（本体零改）；平台对接改动见 `MainAgent/Onlyoffice.md`。本地 config 用 `localhost:8080`+`host.docker.internal:8001`，Compose/服务器部署要改回 `onlyoffice-docs`+`gateway:8001`+`/onlyoffice`（原值在 config 注释里）。
- 跑这两个技能**不需要 OnlyOffice**（4 文件下载走 `/api/threads/{id}/artifacts?download=true`，与 `/api/onlyoffice/*` 独立）；OnlyOffice 只是让 docx/xlsx 能在线预览/编辑。
