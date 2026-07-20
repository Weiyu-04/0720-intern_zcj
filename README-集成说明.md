# 两个技能 · 集成说明

包里是两个技能目录，都归「应急指挥调度」域：

| 目录 | 干什么 | 输入 → 输出 |
|---|---|---|
| `post-evaluation` | 后评估小助手 | 事故调查报告 PDF → 表2/表3 评估表，各出 Word+Excel 共 4 个文件 |
| `production-safety-accident-review` | 事故研判助手 | 警情信息/事故快报文本 → 是否生产安全事故 / 是否纳统 / 等级 / 类型(GB6441-2025) / 行业领域+WSA编码，输出是聊天里的文本，不产文件 |

两者互相独立，没有依赖关系，可以分开集成。

## 放哪

解压到 `MainAgent/backend/skills/public/` 下，**保持目录名不变**（目录名就是技能名，domains.json 靠它引用）：

```
MainAgent/backend/skills/public/
├── post-evaluation/
└── production-safety-accident-review/
```

技能是自动发现的（`os.walk` 扫 `skills/public/`，见到 `SKILL.md` 就收），不用注册。`extensions_config.json` 也不用动——public 技能默认就是 enabled。

## 挂菜单

改 `MainAgent/backend/skills/domains.json`，在 `emergency-dispatch` 域下：

```jsonc
// 现成的空槽，填上即可
{ "id": "risk-assessment", "name": "事故研判助手", "icon": "🧭", "sort": 3,
  "skill_name": "production-safety-accident-review" }

// 这个槽位版本控制里没有，需要新增
{ "id": "accident-post-eval", "name": "后评估小助手", "icon": "📋", "sort": 4,
  "skill_name": "post-evaluation" }
```

`risk-assessment` 原名是「风险研判」，改成「事故研判助手」是因为这技能做的是"警情已发生→判定事故等级/类型"，不是事前评估风险，原名会误导用户。你觉得不合适可以不改，只填 `skill_name` 也能跑。

**包里没有附 domains.json**，因为你那份很可能跟我们的不一样，直接覆盖会冲掉你的东西。按上面改你自己那份就行。

另外提醒一句：**版本控制里的种子 `default_domains.json` 的 emergency-dispatch 下只有 4 个槽位，没有 `accident-post-eval`**。所以 clone 出来的环境不会自带这个槽，得手工加。要让它对新环境可复现，得往种子里补——注意种子只在 `domains.json` 不存在时才播种，已有的机器改种子不生效。

## 两个顺序/路径坑

**先解压目录，再改 domains.json。** 反了会白干：加载时有个 `_null_orphans()`，发现槽位指向的技能目录不存在，会**静默把 `skill_name` 置回 null 并把文件覆盖写回**。

**后端必须从 `backend/` 目录起。** `project_root()` 就是 `Path.cwd()`，技能根目录由它推导。从仓库根起后端，技能路径会变成 `MainAgent/skills`，一个都加载不到。

## 前提条件

**`config.yaml` 里 `sandbox.allow_host_bash: true`** —— 这条是硬前提，example 里默认是 `false`。两个技能都要跑 python 脚本，false 的话**两个都直接废掉**。

**python 依赖**：

- `production-safety-accident-review`：**零依赖**，运行时脚本纯标准库（`grade.py`/`classify_org.py` 零 import，`encode.py`/`geo.py` 只要 json+os）。`scripts/maintenance/` 那三个要 openpyxl，但研判时不调用，只在从 Excel 重建码库时用。
- `post-evaluation`：需要 **python-docx、openpyxl、PyMuPDF**。

注意技能脚本落到哪个 python 取决于 PATH——SKILL.md 里写的是裸 `python`。我们本机是 `/opt/miniconda3/bin/python`（三个包都有）。如果打到一个没装 PyMuPDF 的 python 上，会报 `No module named fitz`。

**别只拷 .py**：`production-safety-accident-review/scripts/data/` 下两个 json（`gbt4754.json` 1381 个行业小类、`geo.json` 全国省地县）是硬依赖，脚本用 `os.path.dirname(__file__)` 相对定位。`post-evaluation/templates/` 下是二进制 docx 模板，`generate_tables.py` 靠它克隆行，也无法从文本重建。（`.bak` 是改动前的原件，不参与运行，删了也行。）

## 跟 OnlyOffice 的关系

**跑这两个技能不需要 OnlyOffice。** 4 个产出文件的下载走的是 `/api/threads/{id}/artifacts?download=true`，跟 `/api/onlyoffice/*` 是完全独立的两条路由，不装 OnlyOffice 照样能下载，只是 docx/xlsx 没法在线预览。

**但有一条容易漏**：`frontend/next.config.js` 的 `experimental.proxyClientMaxBodySize: "80mb"`。它长得像 OnlyOffice 的改动，其实**是 post-evaluation 的真实依赖**——上传代理默认上限 10MB，而事故调查报告 PDF 可以到 15MB 以上，不改就传不上去。

## 验证

集成完起服务，「应急指挥调度」下应该能看到两个可点开的入口。改了技能之后**必须新建对话**——旧对话用的是旧的系统提示词，不会生效。
