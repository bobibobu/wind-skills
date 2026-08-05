# wind-mcp-skill：对标优秀开源 Skill 的评估与分层改造方案

> 状态：**方案 v2（含自评修订，未落地任何修改）**
> 评估对象：`skills/wind-mcp-skill`（SKILL.md 125 行 / cli.mjs v1.11.11 / 7 个领域契约）
> 参照系：Anthropic 官方 Agent Skills 规范、Anthropic `skill-creator`、`obra/superpowers`、`garrytan/gstack`
>
> **v2 相对 v1 的变化**：新增 §4「风险与反对意见（自评）」；§5 改造清单按自评结论重排为 A/B/C/D 四档；
> §6 目标结构改为「A 阶段落地版 + B 阶段条件版」；§0 评分下调了过严的项；砍掉 v1 的 `sync-contracts`
> 折叠方案；evals 从 8 用例 ×2 模型 ×2 对照重构为 3 用例 mock 单模型起步。

---

## 0. 结论速览（修订版）

**总评：合格偏优。按 Anthropic 官方 checklist 逐条对，这个 skill 基本是通过的**——SKILL.md 125 行（上限 500）、引用一层深、>100 行的 reference 有 TOC、按领域切分 reference、脚本"解决而非推回"。在**工具集成型 skill** 这一类里，它的工程化程度超过绝大多数开源 skill。

因此**本方案不是"修违规"，而是"在达标之上继续优化"**。这一点决定了后面所有建议的证据强度：

- 真正有官方依据、当前确实缺失的，只有 **Quick start 示例** 和 **evals** 两项；
- 其余（分层重划、L4 扩大化、门禁重排）都属于**基于假设的优化**，收益未经测量；
- v1 主打的"省 25% token"**不足以支撑这次改造**（详见 §4.1）。

| 维度 | 评级 | 说明 |
| --- | --- | --- |
| 分层加载架构 | A− | 按领域切 reference 是官方 "Pattern 2" 标准形态；L2/L3 边界可优化，但不构成违规 |
| 脚本工程质量 | A | 本地参数校验、结构化错误信封、熔断、并发控制、mock 集成测试 |
| 契约质量（references） | A− | 自动生成 + TOC + BEGIN/END 锚点；唯一问题是 stock.md 负面块重复 |
| SKILL.md 体量与可读性 | B | 125 行合规；问题是**内容生命周期混装**，不是长度 |
| 触发设计（description） | B | 覆盖全但非 "Use when" 句式；**仓库版与安装版已不一致（实 bug）** |
| 反模式 / Common mistakes | C+ | 信息齐全，形式是散文；改成表格会**变长**，与瘦身目标冲突（见 §4.5） |
| 示例 / Quick start | D | **完全缺失**，官方明确要求，投入最小收益最高 |
| 评测（evals） | D | 只有 CLI 单测，无 skill 行为评测；但补齐成本被 v1 严重低估（见 §4.4） |
| 面向人的文档（README） | D | skill 目录无 README |
| Frontmatter 合规性 | **未定** | 4 个非标准字段，但**未验证**分发链路是否消费它们，严重性无法判断 |

---

## 1. 参照系：优秀 Skill 的共识标准

### 1.1 四个来源，各自贡献了什么

| 来源 | 类型 | 贡献的核心观点 |
| --- | --- | --- |
| **Anthropic 官方 best-practices** | 规范 | 三层渐进披露、500 行上限、引用只能一层深、>100 行 reference 要 TOC、按领域切分、自由度匹配脆弱度、≥3 个 eval |
| **Anthropic `skill-creator`** | 官方 skill | 骨架 `SKILL.md + scripts/ + references/ + assets/`、description 要"推"一点（Claude 倾向欠触发）、eval 要跑 with-skill vs baseline 对照 |
| **`obra/superpowers`** | 社区标杆 | **Iron Law：没有失败测试就不许写 skill**（RED→GREEN→REFACTOR）；description 以 "Use when..." 开头且**绝不摘要工作流**；纪律型 skill 要配 **rationalization table**（agent 会找的借口）+ **red flags** 自查清单 |
| **`garrytan/gstack`** | 工作流标杆 | 显式 STOP 门禁、固定工件路径、完成状态（DONE / NEEDS_CONTEXT）、skill 之间的 handoff 管线 |

### 1.2 收敛出的 12 条硬规则

1. Frontmatter 只有 `name` + `description` 参与契约。`name` ≤64 字符、小写字母/数字/连字符、不含 `claude`/`anthropic`；`description` ≤1024 字符、**第三人称**、写清"做什么 + 何时用"。
2. description 是唯一的触发入口，要包含**用户真实说法**和**症状词**，宁可"推"一点；但**不要在 description 里摘要工作流**（agent 可能照着摘要干，不再读正文）。
3. SKILL.md 正文 <500 行；接近上限就加一层结构，而不是继续堆。
4. 引用**只能一层深**（SKILL.md → reference.md）。嵌套引用会导致 agent 用 `head -100` 半读。
5. reference 文件 >100 行必须有目录。
6. 多领域 skill 按**领域**切 reference，不按"章节类型"切。
7. 自由度匹配脆弱度：脆弱、必须一致的操作给**确定性脚本 + 精确命令**；开放性判断给原则。
8. 脚本要"解决问题，而不是把问题推回给 agent"：显式处理错误、无魔法常数、输出可读的修复指引。
9. 用**校验循环**（run validator → fix → repeat）代替祈祷式约束。
10. 用示例传达格式，比用形容词描述格式有效得多。
11. 避免：给太多选项、时效性信息、术语不一致、Windows 路径。
12. 至少 3 个 eval，要有 **baseline（不带 skill）对照**，并在 Haiku/Sonnet/Opus 上都跑。

### 1.3 标准 SKILL 模板（可复用于本仓其余 skill）

按"必选 / 按类型可选"分层。**不是章节越多越好**——只保留执行时真正会被用到的。

```markdown
---
name: <lowercase-hyphen>                 # 必选
description: >-                          # 必选：做什么 + 何时用 + 何时不用
  <一句话能力>。Use when <用户说法/文件类型/上下文>。
  Not for <相邻但不属于本 skill 的场景>。
allowed-tools: <可选，收敛权限面>
---

# <Title>

<1–2 句：核心原则。不解释 Claude 已经知道的常识。>

## Quick start                            ← 必选。一个可直接复制的完整例子
## 何时用 / 何时不用                        ← 必选（工具型尤其重要）
## 路由 / 导航表                            ← 多领域必选
## 工作流                                  ← 必选。有序步骤 + 可勾选清单
## 硬门禁                                  ← 有副作用/配额/安全边界时必选
## Common mistakes                         ← 建议，但注意会增加体量
## 资源导航                                 ← 有 references/scripts 时必选
## 输出契约 / 完成状态                       ← 建议

<!-- 以下按 skill 类型可选，不要为了模板完整而强加 -->
## 启动前置 / 模式分流 / 工件模板 / Handoff / 状态记录
```

| 类型 | 额外保留 | 代表 |
| --- | --- | --- |
| 轻量执行型 | — | 大部分 `*_skill` 分析类 |
| **工具集成型** | 路由表、错误恢复、完成状态 | **wind-mcp-skill**、ifind、tushare |
| 交互咨询型 | 模式分流、AskUserQuestion 规则、工件模板 | wind-alice |
| 跨会话产品型 | 状态记录、学习、升级/遥测 | gstack |

> ⚠️ 这套模板**不建议作为运动式统一动作**推给仓内其余 35 个 skill。多数是分析型 skill，强套工具型章节只会让简单 skill 变臃肿。见 §7。

---

## 2. 现状评估

### 2.1 做得好的 7 点 —— 重构时**必须原样保住**

1. **按领域切 reference**（`references/{stock,fund,index,bond,financial-docs,economic,analytics}.md`），一次只加载 1 个。
2. **契约自动生成 + 锚点隔离**：`<!-- BEGIN MCP TOOLS/LIST GENERATED CONTRACT -->` + `cli.mjs sync-contracts`，契约不会和后端漂移。
3. **机器强制的参数门禁**：`scripts/call-rules.json`（required / enum / paired / mutually_exclusive / ordered_dates / patterns）在**花掉一次后端调用之前**本地拦截。
4. **结构化错误信封**：`error.code` / `agent_action` / `retry` / `circuit_breaker` / `correction`，恢复指引由工具输出在失败那一刻投递。
5. **运行时安全语义注入**（`cli.mjs:169-238`）：`INVALID` → `null` 并附 `BACKEND_INVALID_AS_NULL`；出现 `excelTotalCount` 自动附 `UNRELIABLE_DECLARED_COUNT`；`cli_meta.tables[].actual_row_count` 给真实行数。
6. **完成状态枚举**（DONE / DONE_WITH_LIMITS / NO_RESULTS / BLOCKED_* / OUT_OF_SCOPE）。
7. **带 mock 后端的集成测试**（`tests/mock-fetch.mjs` + `run-error-tests.mjs`）。

### 2.2 确认的问题（按证据强度排序）

| 编号 | 问题 | 证据强度 |
| --- | --- | --- |
| **F1** | **缺 Quick start 完整示例**。SKILL.md 只有命令模板，`cli.mjs` 的 `CALL_EXAMPLES` 只在 `--help` 输出，agent 读不到 | **硬**（官方明确要求 + 文件可验证） |
| **F2** | **仓库版与安装版 description 不一致**（安装版含"A股/港股/美股"分层表述） | **硬**（两份文本可直接比对） |
| **F3** | **门禁 8 与 CLI 运行时注入重复**。「INVALID 禁止当 0」「excelTotalCount 不可信」——CLI 已强制注入且已把 INVALID 改写为 null | **硬**（`cli.mjs:169-238` 代码证据） |
| **F4** | **`cd` 依赖**。`cli.mjs` 用 `fileURLToPath` 算 `SKILL_DIR`，本来与 cwd 无关；`cd` 只为让相对路径成立，在沙箱下易触发额外提示 | **硬**（代码证据） |
| **F5** | **无 skill 行为 evals**。`tests/` 是 CLI 单测（后端错误形状→错误码映射），不是行为评测 | **硬**（官方 checklist 要求 ≥3） |
| **F6** | **skill 目录无 README.md**（面向人的安装/Key 说明） | **硬** |
| **F7** | **术语不一致**：「契约 / 工具契约 / 领域契约」「行情工具 / 价格指标工具」 | **硬** |
| **F8** | **L2 混装失败态内容**：门禁 7、重试前审计 6 条、wind-alice 兜底 4 步只在失败后才有用，却常驻 | **中**（结构判断成立，但拆走的收益未验证——见 §4.3） |
| **F9** | **`stock.md` 有 ~1.3k tokens 镜像重复**：5 个工具各带一份【不要选用本工具的场景】 | **中**（重复属实，但修复方案已否决——见 §5-C） |
| **F10** | **10 条门禁全是"不得/禁止"**，缺 superpowers 式的 `症状\|借口\|正确做法` 结构 | **弱**（改法会让 L2 变长，与瘦身目标冲突） |
| **F11** | **Frontmatter 4 个非标准字段**（`auto_invoke` / `security` / `author` / `homepage` / `examples`）。`security:` 读起来像权限边界但在 Claude Code 侧不生效 | **未验证**（不知道 `npx skills add` / aifinmarket 门户是否消费，严重性无法判断） |

---

## 3. 分层模型（含其局限）

### 3.1 现状是 2.5 层

```
L1  metadata（description）              ~180 tok   常驻
L2  SKILL.md                            ~3146 tok  触发即加载
L3  references/<domain>.md              ~500–5800 tok  按领域加载
```

**L2 承担全部策略，L3 只承担契约。**而"策略"里混着三类生命周期完全不同的内容：每次都要遵守的 / 失败后才需要的 / 拿到结果才需要的。

### 3.2 四层模型及其**真实边界**

```
L1  metadata                    常驻            触发
L2  SKILL.md                    触发即加载      路由 + 示例 + 每次必守规则 + 导航
L3  references/                 按需读取        领域契约
L4  运行时注入 cli_meta / error  命中才出现      结果语义、警告、错误恢复指引
```

L4 已经存在（`cli_meta.warnings`、`error.agent_action`），优点是零常驻成本、贴着数据出现。但 v1 把它吹过头了，**必须同时记住三条限制**：

| 限制 | 说明 |
| --- | --- |
| **L4 只能补救，不能预防** | 警告出现时调用已经花掉了。凡是决定"要不要调、调哪个"的规则，**必须**留在 L2 |
| **L4 不是"不可忽略"** | `cli_meta` 在 `normalizeCallSuccess` 末尾赋值，序列化后排在 `content` **之后**。返回 500 行数据时警告被埋在尾部，agent 可能扫过去 |
| **L4 提高迭代成本** | 每加一条规则要改 CLI + 补测试，而不是改一行文档。对仍在演进的 skill（v1.11.11）是实打实的拖累 |

### 3.3 「规则应该住在哪」判定表（修订）

| 规则的触发时刻 | 该住哪层 | 例子 |
| --- | --- | --- |
| 每次调用**前**要判断 | **L2（不可下沉）** | 选哪个 server_type；日期必须 `yyyy-MM-dd`；串行优先；批量先探针；**要日涨跌幅别用 Quote** |
| 只在特定领域调用时 | **L3 领域契约** | `indexes` 字段表；`总市值1/2` 口径；EDB `observation` 与日期互斥 |
| 只在失败后 | **L4 error 信封**（优先）+ L3 recovery.md（条件） | 重试审计；wind-alice 兜底；熔断 |
| 只在拿到结果时 | **L4 `cli_meta`** + L2 一行索引 | INVALID→null；excelTotalCount 不可信；单位未知 |
| 面向人 | **README.md** | 安装、Key 申请、版本、许可 |

> 注意第一行末尾：**门禁 9（Quote 涨跌幅陷阱）属于"调用前决策"，不能移到 L4。**
> 正确做法是 L2 留一行路由提示 + L4 加一条补救警告，**两边都要**，不是搬家。

### 3.4 token 预算（诚实版）

| 阶段 | 现状 | A 阶段后 | B 阶段后（若审计通过） |
| --- | --- | --- | --- |
| L1 metadata | ~180 | ~220 | ~220 |
| L2 SKILL.md | ~3146 | ~3050 | ~2400 |
| L3 stock.md | ~5817 | ~5817 | ~5817 |
| **成功路径合计** | **~9143** | **~9087** | **~8437（−8%）** |

**结论：token 不是做这件事的理由。** A 阶段基本不省（加了示例、删了重复，互相抵消）；B 阶段省 ~8%，在 200k 窗口里可以忽略。
真正的理由只能是**降噪 → 提升指令遵守率**，而这**尚未被测量**。所以 B 阶段必须先有评测支撑，见 §5-D。

> 估算方法：CJK 按 1 token/字、ASCII 按 0.28 折算。表格中反引号与竖线密集，绝对值可能有 ±30% 偏差；**相对比例比绝对值可信**。

---

## 4. 风险与反对意见（自评）

本章是对 v1 方案的反驳。**每一条都指向 v1 中一项被删除或降级的建议。**

### 4.1 v1 的核心卖点站不住：−25% token 撑不起改造

省 2.2k tokens 在 200k/1M 窗口里几乎不影响任何东西。v1 把它放在结论第一位是**选错了指标**。
真正应该被优化的是路由准确率和字段纪律，但 v1 **没有任何生产数据**证明当前 SKILL.md 的长度导致了这些问题。

→ **修订**：token 预算降级为参考信息（§3.4），不再作为决策依据。

### 4.2 v1 把 L4 吹过头

- 声称 L4"不可能被忽略"——**错误**。`cli_meta` 序列化后排在 `content` 之后，大结果集里会被埋掉。要真做到需把 warnings 提到顶部或走 stderr，这是 v1 未计入的额外工作。
- 主张把门禁 9 移到 L4——**方向错误**。错误发生在选工具的时刻，那时还没有返回值；等 CLI 注入 `MISSING_PRE_CLOSE`，调用已经花掉，还得再发一次。L2 散文是**预防**，L4 注入是**补救**。
- 未提及"语义入代码"的迭代成本。

→ **修订**：§3.2 补三条限制；门禁 9 改为"L2 保留 + L4 补充"，v1 承诺的那 ~180 tokens 节省不存在。

### 4.3 `recovery.md` 拆分可能违反本方案自己提出的原则

v1 明确写了"规则不在上下文里，agent 就不知道自己需要它"，然后转头把恢复规则拆了出去。
问题在于：**「认证/额度/网络错误不得切 analytics 或 wind-alice」恰恰是 agent 最容易给自己找理由绕过的规则**——superpowers 整套 rationalization table 的存在理由就是这个。把它挪得离上下文更远，方向可能是反的。

更关键：**v1 没有审计 `error.agent_action` 现有文案是否已覆盖「重试前审计」那 6 条**。读到的几个定义里有"保持当前 server_type、tool_name 和参数不变"这类表述，看起来部分覆盖，但这是凭印象拆的。

→ **修订**：降级为 B 档，**审计完成前不得动手**（§5-B1）。

### 4.4 v1 把最贵的一步说成了最安全的起点

"先补 evals 拿 baseline"听起来正确，实际成本被严重低估：

- 8 用例 × with-skill/baseline × 2 模型 = **32 次完整 agent 会话**；
- 打的是**真实计费后端**（`DAILY_LIMIT_ERROR` / `BALANCE_ERROR` 都是真错误码），且行情每天变——"茅台最新价"这类断言无法固定；
- 想用 `tests/mock-fetch.mjs` 挡住后端？它是 CLI 的 `--import` 预载模块，**需要 agent 自己发出带预载的命令**，而这就改变了被测对象。要在行为评测里 mock 后端，得先做 harness 改造，v1 完全没有 scope；
- 关键断言（"不得走 analytics_data"）要检查的是**工具调用序列**，不是最终文本，需要 transcript 级检查；
- 官方文档明确写了**没有内置 eval runner**。

→ **修订**：evals 重构为 3 用例、mock 支撑、单模型起步（§5-D）。

### 4.5 v1 有两条自相矛盾的建议

一边要把 L2 压到 ~1900 tokens，一边建议加 Common mistakes 表。superpowers 那种 `症状 | 借口 | 正确做法` 三列表**通常比它替换的散文更长**。这两条互相打架，v1 没说破。

→ **修订**：Common mistakes 降级为 B 档，且明确标注"以提升遵守率为目的，接受 L2 变长"。

### 4.6 Quick start 有副作用

agent 容易过度锚定示例里的 `indexes` 值，照抄到不相关查询上。且它和 `cli.mjs` 的 `CALL_EXAMPLES` 会成为两份真相——markdown 无法引用代码常量，**现实就是会漂移**。

→ **修订**：示例旁必须紧跟一行"字段逐字取自领域契约，勿照抄本例"；接受与 `CALL_EXAMPLES` 双份维护，在 `cli.mjs` 加注释互指。

### 4.7 `sync-contracts` 折叠负面块：风险收益比最差，直接砍

- 那些块是**后端官方描述**，折叠后本地契约不再等于后端原文；
- 实现方式是**对 `<br>` 拼接的中文表格单元格做正则**，后端一改措辞就静默失效或切错；
- 只有 stock 的 5 个工具有这个块，fund/index 一个都没有——转换在各领域表现不一致；
- 换 ~1k tokens，代价是一个永久转换层，以后每次后端契约变更都要过它验证。

→ **修订**：**否决**（§5-C）。保留原文另生成路由矩阵是安全做法，但那样一个 token 都省不下来。

### 4.8 v1 对现状评分过严

按官方 checklist 逐条对，这个 skill 基本通过。v1 在"分层加载架构""SKILL.md 体量"上给 B / B−，但这两项官方标准都是**达标**的。v1 做的是"超出标准继续优化"，证据强度远弱于"修违规"。

→ **修订**：§0 评分表上调，并在结论首句明确本方案的性质。

### 4.9 本次评估**没有验证**的事项

| 未验证项 | 影响 |
| --- | --- |
| **一次 CLI 都没跑过**，所有 CLI 行为判断来自读代码 | 中——代码证据较强，但运行时行为可能有出入 |
| 未核对 SKILL.md 声明的行为与 `cli.mjs` 实际行为是否一致 | **高**——这恰恰是最该查的漂移类型 |
| 未逐个错误码审计 `agent_action` 是否覆盖「重试前审计」6 条 | **高**——直接决定 B1 能否做 |
| 未验证 `npx skills add` / aifinmarket 门户是否消费 frontmatter 非标准字段 | 中——决定 F11 的真实严重性 |
| 无任何生产遥测（真实失败率、误路由率） | **高**——整个"降噪提升遵守率"的假设无从检验 |

---

## 5. 改造清单（按自评结论重排）

### A 档：立即执行 —— 零假设、有硬证据、低风险

| # | 动作 | 对应问题 | 涉及文件 | 预估 |
| --- | --- | --- | --- | --- |
| **A1** | SKILL.md 顶部加 **Quick start**：一个填好的完整调用（命令 + 参数 + 输出片段 + `cli_meta` 形状），**紧跟一行"字段逐字取自领域契约，勿照抄本例"** | F1 | `SKILL.md` | 20 行 / 30 分钟 |
| **A2** | 对齐仓库版与安装版 `description`，并补口语触发词（最新价 / K线 / 选股 / 净值 / 规模 / 持仓 / 公告 / PE / 市值 / 涨跌幅） | F2 | `SKILL.md` | 20 分钟 |
| **A3** | 门禁 8 压缩为一行「结果安全语义以 `cli_meta.warnings` 为准，逐条体现」，删除与 CLI 注入重复的散文 | F3 | `SKILL.md` | 10 分钟 |
| **A4** | 去掉 `cd` 依赖，改为「用 skill 目录绝对路径执行，无需 cd」 | F4 | `SKILL.md` | 5 分钟 |
| **A5** | 术语统一（「领域契约」作为唯一说法；「价格指标工具」与「行情工具」分清） | F7 | `SKILL.md` + references | 20 分钟 |
| **A6** | 新增 skill 目录 `README.md`（能力、安装、Key 申请、版本、已知限制） | F6 | 新增 | 1 小时 |
| **A7** | `cli.mjs` 的 `CALL_EXAMPLES` 处加注释指向 SKILL.md Quick start（接受双份，标明需同步） | 4.6 | `cli.mjs` | 5 分钟 |

**A 档合计约半天，不改变任何运行时行为，不押注任何未验证假设。**

### B 档：需先完成审计才能决定 —— 有价值但依赖前置结论

| # | 动作 | **前置审计（必须先做）** | 若审计不通过 |
| --- | --- | --- | --- |
| **B1** | 抽出 `references/recovery.md`（重试审计 + 熔断 + wind-alice 兜底 4 步），L2 留一行指针 | 逐个错误码核对 `ERROR_DEFINITIONS[*].agent_action` 是否已覆盖「重试前审计」6 条。**只有已覆盖的才允许从 L2 移走**；「不得切 analytics / alice」这类反合理化规则**无论如何留在 L2** | 不拆，只在 L2 内压缩措辞 |
| **B2** | L4 扩大化：Quote 缺 `pre_close`/`pct_chg` 时注入 `MISSING_PRE_CLOSE`；单位缺失时注入 `UNIT_UNKNOWN` | 用 `tests/mock-fetch.mjs` 造 scenario 确认字段缺失的判定条件；**同时确认 warnings 在大结果集里是否真被读到**（否则先把 warnings 提到 `cli_meta` 之前或输出到 stderr） | 只做 stderr 提示，不动 payload |
| **B3** | 把 warnings 从 payload 尾部提前（或复制一份到 stderr），解决 §3.2「不是不可忽略」 | 确认 stderr 不会污染 agent 对 exit 0 的判定 | 保持现状 |
| **B4** | 门禁重排 + Common mistakes 表（`症状 \| 借口 \| 正确做法`） | **需要 D 档评测给出基线**，证明当前门禁形式确实存在遵守率问题 | 不做；现有散文已能表达 |

**B 档共同前提：门禁 9（Quote 涨跌幅）留在 L2，不下沉。**

### C 档：已否决

| # | 动作 | 否决理由 |
| --- | --- | --- |
| **C1** | ~~`sync-contracts` 后处理折叠【不要选用本工具的场景】~~ | 见 §4.7：改写后端官方描述 + 中文正则脆弱 + 各领域不一致 + 永久转换层，换 ~1k tokens 不值 |
| **C2** | ~~删除 frontmatter 的 `author` / `homepage` / `examples`~~ | 分发链路是否消费未验证（F11）。**先查清再说，查清前不动** |
| **C3** | ~~把本模板推给仓内其余 35 个 skill~~ | 多数是分析型 skill，强套工具型章节只会让简单 skill 臃肿。见 §7 |

### D 档：评测（重构版）—— 先拿廉价信号，别一上来建体系

**不要**按 v1 的 8 用例 × 2 对照 × 2 模型（32 次会话、真实计费、断言无法固定）。改为：

**第一轮：3 个用例、mock 后端、单模型（Sonnet）、只测最可疑的一件事**

目标问题：**该走专项工具时，agent 是否会滑向 `analytics_data`？**

| 用例 | 期望 | 判定方式 |
| --- | --- | --- |
| 「贵州茅台今天最新价」 | 命中 `stock_data.get_stock_price_indicators` | 检查工具调用序列，非最终文本 |
| 「中证500指数近30日走势」 | 命中 `index_data.get_index_kline` | 同上 |
| 「日经225今天多少点」 | `OUT_OF_SCOPE`，不调任何工具 | 同上 |

**前置工程（这是 D 档真正的成本，必须先算进去）：**

1. 提供一个稳定的 mock 入口——例如给 `cli.mjs` 加 `WIND_MOCK=1` 环境变量分支，直接复用 `tests/mock-fetch.mjs` 的 scenario，**让 agent 发出的命令保持不变**（避免"改变被测对象"）；
2. 用一个脚本从会话 transcript 里抽取 `cli.mjs call <server_type> <tool_name>` 序列作为断言输入；
3. 每例跑 with-skill / 无 skill 两次，共 6 次会话。

**只有第一轮显示确有误路由，才值得扩到 8 用例 / 多模型 / 字段纪律与错误恢复类。**

---

## 6. 目标 SKILL.md 结构

### 6.1 A 阶段落地版（只做 A 档后的样子）

结构基本不变，**不拆 recovery.md**，重点是补示例、删重复、去 `cd`。

```markdown
---
name: wind-mcp-skill
description: >-
  访问万得 Wind 金融数据。Use when 用户问 A股/港股/美股的最新价、涨跌幅、K线、分钟行情、
  财务、估值、股东、事件、风险；基金/ETF/LOF 的净值、规模、持仓、业绩；指数/板块行情与
  基本面；债券档案与估值；上市公司公告、财经新闻、宏观与行业指标；或需要选股/选基筛选。
  Not for 台股、日股、韩股、欧股、汇率、期货盘口、加密货币或非金融数据。
---

# Wind 万得金融数据

把用户问题映射到 `server_type + tool_name`，只读命中领域的一份契约，只基于返回值作答。

## Quick start                                          ← A1 新增
node <skill 目录绝对路径>/scripts/cli.mjs call stock_data get_stock_price_indicators \
  '{"windcode":"600519.SH","indexes":"最新成交价,涨跌幅"}'

# exit 0 → 解析 stdout；有 content[0].text 时优先解析其中的 JSON
# cli_meta.warnings 里的每一条都必须体现在回答里
# ⚠️ indexes 字段逐字取自领域契约，勿照抄本例

## 领域导航                                              ← 原样保留（7 行表，本 skill 最核心资产）

## 不可协商门禁                                          ← 保留 1–7、9；8 压成一行
  1 路由 / 2 参数 / 3 统一格式 / 4 标的 / 5 指标 / 6 命令 / 7 失败与熔断
  8 结果安全：以 cli_meta.warnings 为准，逐条体现            ← A3 压缩
  9 行情解释：Quote 不保证含昨收；缺 pre_close/pct_chg 时
    禁止用 (收盘-开盘)/开盘 冒充日涨跌幅 → 改用价格指标或 K 线   ← 留在 L2，不下沉

**并发规则** / **批量探针规则** / **Key 判定规则**        ← 原样保留

## 工作流                                                ← 保留，第 7 步去掉 cd
## 重试前审计                                            ← A 阶段保留在此，B1 审计后再决定
## 路由优先级                                            ← 原样保留
## 失败与回答                                            ← A 阶段保留在此
## 完成状态                                              ← 原样保留
```

### 6.2 B 阶段条件版（仅当各自的前置审计通过）

```
skills/wind-mcp-skill/
├── SKILL.md                    L2：路由 + Quick start + 每次必守门禁 + 导航 + 完成状态
│                                   （门禁 9 与「不得切 analytics/alice」永远留在这里）
├── README.md                   面向人：能力 / 安装 / Key / 版本 / 限制          ← A6
├── skill-standard-and-layering-plan.md   ← 本文档。SKILL.md 不引用它，
│                                            因此不进 agent 上下文；仅供维护者阅读
├── references/
│   ├── stock.md  fund.md  index.md  bond.md
│   ├── financial-docs.md  economic.md  analytics.md                        ← 原样不动
│   └── recovery.md             L3：重试审计（仅 agent_action 未覆盖的部分）
│                                   + 熔断细则 + wind-alice 兜底 4 步 + 安装引导   ← B1
├── scripts/
│   ├── cli.mjs                 L4：cli_meta.warnings 前置 / MISSING_PRE_CLOSE
│   │                               / UNIT_UNKNOWN / WIND_MOCK 分支          ← B2 B3 D
│   ├── call-rules.json  tool-manifest.json  update-check.mjs
├── tests/                      CLI 层单测（保留，不与 evals 合并）
└── evals/
    ├── evals.json              3 个路由用例起步                              ← D
    └── extract-tool-calls.mjs  从 transcript 抽工具调用序列                   ← D
```

---

## 7. 不建议做的事

1. **不要**把 gstack 的 profile / 遥测 / 跨会话学习 / 人格化收尾搬过来——本 skill 是取数执行，不是产品化工作流。
2. **不要**把 superpowers 的设计审批流程搬过来——同上。
3. **不要**把领域契约的字段表回填进 SKILL.md——会直接摧毁现有最大的架构优势。
4. **不要**为了"章节完整"补启动前置 / 工件模板 / 状态记录——本 skill 没有这些需求。
5. **不要**在确认分发链路之前删 frontmatter 的 `author` / `homepage` / `examples`（C2）。
6. **不要**手改 `references/*.md` 里 BEGIN/END 锚点之间的内容——会被 `sync-contracts` 覆盖。
7. **不要**把 §1.3 模板作为运动式统一动作推给仓内其余 35 个 skill（C3）。若要推，只推 §1.2 的 12 条规则作为**评审 checklist**，不推章节骨架。
8. **不要**用"省 token"作为立项理由（§4.1）。

---

## 8. 执行顺序

```
第 1 步  A 档全做（半天，零风险，不需要任何前置）
         ↓
第 2 步  两项审计（各半天，纯阅读，不改代码）
         审计① 逐个错误码核对 agent_action 覆盖度        → 决定 B1
         审计② SKILL.md 声明 vs cli.mjs 实际行为一致性     → 可能挖出真 bug，优先级或高于全部 B 档
         ↓
第 3 步  D 档第一轮（3 用例 / mock / 单模型，含 WIND_MOCK 前置工程，1–2 天）
         ↓
    ┌────┴────┐
  有误路由      无误路由
    ↓            ↓
 做 B1 B4     停在这里。B 档不做，
 再跑一轮      因为收益假设已被证伪
```

**核心原则：A 档之后的每一步都必须有前一步的结论支撑，不要因为方案写得完整就把它全做完。**
