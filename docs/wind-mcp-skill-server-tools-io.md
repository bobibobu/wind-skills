# Wind MCP Skill — Server 与工具 入参 / 出参参考

本文件记录 `skills/wind-mcp-skill` 当前（CLI 版本 **2.0.3**）通过本地 CLI 访问的 **7 个 Wind MCP 服务**及其全部工具的入参、出参、格式与示例。所有示例均为 **2026-08-24 实测样例**，数值随行情/报告期变化，仅示形态。

- 契约权威来源：`skills/wind-mcp-skill/references/*.md`（每个 server 一份）
- 工具清单权威：`skills/wind-mcp-skill/scripts/tool-manifest.json`
- 校验/规范化规则：`skills/wind-mcp-skill/scripts/call-rules.json`
- 信封实现：`skills/wind-mcp-skill/scripts/cli.mjs`

---

## 1. 调用方式（统一入口）

所有取数都经本地 CLI 转发到 MCP，命令固定为四段：

```bash
node scripts/cli.mjs call <server_type> <tool_name> '<params_json>'
```

- 先 `cd` 到 `skills/wind-mcp-skill/`（SKILL.md 所在目录），再用相对路径执行。
- `<params_json>` 是一个 JSON 对象。POSIX shell 优先内联传参；非 POSIX 环境（PowerShell / cmd / 经执行器包装）将 UTF-8 JSON 写入 `scripts/request-<后缀>.json`，以 `@scripts/request-<后缀>.json` 传入，调用后删除。
- 认证 Key 读取顺序：`~/.wind-aifinmarket/config`（`WIND_API_KEY=`）> skill 本地 `config.json`（`{"wind_api_key":"..."}`）> 环境变量 `WIND_API_KEY`。

辅助命令（非取数）：

| 命令 | 作用 |
| --- | --- |
| `cli.mjs list-tools <server_type>` | 拉取后端官方工具描述与 `inputSchema` |
| `cli.mjs open-portal` | 打开万得开发者中心获取 API Key |
| `cli.mjs setup-key <KEY> --scope <global\|skill>` | 写入 API Key |
| `cli.mjs diagnose` | 查看自动更新状态 |

### 7 个 server_type 一览

| `server_type` | 覆盖范围 | 契约 | 工具数 |
| --- | --- | --- | --- |
| `stock_data` | 股票（A股/港股/美股）筛选、行情、K线、分钟、档案、财务、股东、事件、技术、风险 | `references/stock.md` | 10 |
| `fund_data` | 基金/ETF/LOF 筛选、行情、K线、分钟、档案、财务、持仓、业绩、持有人、公司 | `references/fund.md` | 10 |
| `index_data` | 指数/板块 行情、K线、分钟、档案、基本面、技术 | `references/index.md` | 6 |
| `bond_data` | 债券 档案、发债主体、行情估值、主体财务 | `references/bond.md` | 4 |
| `financial_docs` | 上市公司公告、财经新闻（RAG 文本检索） | `references/financial-docs.md` | 2 |
| `economic_data` | 宏观/行业/汇率 EDB 指标（找指标 + 取时间序列） | `references/economic.md` | 2 |
| `analytics_data` | 跨标的聚合、加权、排名、复合指标推导（计算结果，非实体列表） | `references/analytics.md` | 1 |

---

## 2. 入参（请求参数）通用约定

各工具的具体参数在第 4 节逐一列出。以下是跨工具的公共规则。

### 2.1 两类工具的入参风格

- **代码型工具**（价格指标、K 线、分钟行情）：显式结构化参数 `windcode` / `indexes` / `begin_date` / `end_date` / `period` 等。
- **自然语言工具**（档案、财务、股东、事件、技术、风险、持仓、业绩、筛选、analytics 等）：统一只传一个自然语言参数。
  - 绝大多数领域用 **`question`**。
  - **`financial_docs` 例外，用 `query`**（`get_company_announcements` / `get_financial_news`）。
  - `question` / `query` 建议为「实体 + 指标 + 指标参数（日期/窗口/报告期）」的组合；筛选类只写条件、不写实体。

### 2.2 关键字段格式

| 字段 | 适用工具 | 类型 | 格式 / 约束 |
| --- | --- | --- | --- |
| `windcode` | 价格指标 / K线 / 分钟 | string | 名称或 Wind 代码，如 `贵州茅台` 或 `600519.SH`；价格指标支持英文逗号分隔多标的，**单次 ≤50 个** |
| `indexes` | 价格指标 | string | 指标字段名，英文逗号分隔；取值须逐字来自 `references/*-indicators.md`，表外字段会被后端判为「无效的行情指标」 |
| `begin_date` / `end_date` | K 线 | string | **必填**，绝对日期 `yyyy-MM-dd`；`begin_date` 不得晚于 `end_date` |
| `begin` / `end` | 分钟行情 | string | 可选，`yyyy-MM-dd`；未指定默认最新交易日；不可只传 `end` 不传 `begin` |
| `period` | K 线 | string | 见下方枚举；默认 `1d` |
| `aftype` | K 线 | string | `0`=前复权（默认）/ `1`=后复权 / `2`=不复权 |
| `issusp` | K 线 | string | `0`=不含停牌 / `1`=含停牌（默认 `1`） |
| `beginDate` / `endDate` | economic 取数 | string | `yyyy-MM-dd`，须成对；与 `observation` 互斥 |
| `observation` | economic 取数 | string | 近 N 期，数字字符串如 `"10"`；与 `beginDate`/`endDate` 互斥 |
| `top_k` | financial_docs | integer | 返回文档数上限，默认 `5` |

### 2.3 K 线 `period` 枚举（CLI 会自动映射为后端编码）

对外只接受下列值，CLI 内部映射为后端数字编码：

| 传入 | 后端 | 传入 | 后端 | 传入 | 后端 |
| --- | --- | --- | --- | --- | --- |
| `1min` | 1 | `60min` | 7 | `1w` | 11 |
| `5min` | 3 | `120min` | 8 | `1mo` | 12 |
| `10min` | 4 | `240min` | 9 | `1y` | 13 |
| `15min` | 5 | `1d` | 10 | `1q` | 14 |
| `30min` | 6 | | | `6mo` | 15 |

> 日 K 传 `1d`（不要直接传后端数字）。传入非法枚举会返回 `PARAM_VALIDATION_ERROR`。

### 2.4 economic 取数的互斥约束

`query_economic_indicator_data` 的时间范围**必须**显式提供 `beginDate`+`endDate`（成对）**或** `observation`，二者互斥；只给 `question` 会被拒（本地校验直接返回 `PARAM_VALIDATION_ERROR`）。时间范围不要塞进 `question`。

---

## 3. 出参（返回结果）通用结构

每次 `call` 的 stdout 只有两种形态：**成功是数据对象，失败是错误信封**。

### 3.1 成功信封

顶层是 MCP `result` 对象，后端业务数据放在 `content[0].text`（**通常是 JSON 字符串**，需二次解析），CLI 另附一个 `cli_meta`：

```json
{
  "content": [ { "type": "text", "text": "<后端返回的 JSON 字符串或纯文本>" } ],
  "isError": false,
  "cli_meta": {
    "schema_version": "1.0",
    "server_type": "stock_data",
    "tool_name": "get_stock_price_indicators",
    "completeness": "not_asserted",
    "tables": [ { "path": "$.data", "actual_row_count": 1 } ],
    "warnings": []
  }
}
```

`cli_meta` 字段：

| 字段 | 含义 |
| --- | --- |
| `schema_version` | cli_meta 结构版本，当前 `1.0` |
| `server_type` / `tool_name` | 本次调用的路由，便于回溯 |
| `completeness` | `not_asserted`（正常）或 `unknown`（后端带 `excelTotalCount` 时，提示不得据其判断完整性） |
| `tables` | 每个结构化数据块的路径与 **实际行数** `actual_row_count`（只报实际返回行数） |
| `warnings` | 非空时须保留数据并说明；常见 `BACKEND_INVALID_AS_NULL`（`INVALID`→`null`）、`UNRELIABLE_DECLARED_COUNT` |

### 3.2 `content[0].text` 内部的 4 种数据形态

| 形态 | 结构 | 出现于 |
| --- | --- | --- |
| **A. 扁平列式** | `{"data":{"columns":[{name,type}],"rows":[[...]],"unit":{...}},"error":null}` | 价格指标、K 线、分钟行情 |
| **B. 嵌套列式** | `{"data":{"data":[{"columns":[{name,type,unit?}],"rows":[[...]]}]},"error":null}` | 自然语言工具、筛选、analytics（列上可带 `unit`） |
| **C. 指标元/序列** | `{"metrics":[{...}]}`（search）/ `{"metrics":[{"meta":{...},"date":[...],"value":[...]}]}`（query） | economic |
| **D. RAG 文档** | `{"data":{"items":[{content,date,doc_type,relevance,title,url}],"total":N},"error":null}` | financial_docs |

读值要点：
- **单位/量级** 以返回体自带元数据为准——行情类在 `data.unit`，列定义里可能带 `unit`，EDB 在 `meta.unit` 与 `meta.magnitude`；元数据缺失则保留原值并标注单位未知，不自行换算。
- `null` 表示缺失/不适用，**禁止当 0**（后端 `INVALID` 已由 CLI 转 `null` 并在 `warnings` 标注）。
- 只报告实际返回行数；`excelTotalCount` 仅为原始字段，不得据此推断总数、排名全集或分页状态。
- 无匹配时后端可能返回纯文本（如 economic「没有搜索到指标」）而非 JSON，此时 `content[0].text` 原文透传。

### 3.3 失败信封

```json
{ "ok": false, "code": "PARAM_VALIDATION_ERROR", "message": "字段 'begin_date' 不能晚于 'end_date'" }
```

错误码分两类：

**本地 / 参数 / 网络类**（CLI 生成，`code` 指明原因）：

| code | 含义 |
| --- | --- |
| `AUTH_ERROR` | API Key 未配置或认证失败 |
| `INVALID_PARAMS_JSON` | `params` 不是合法 JSON |
| `PARAM_TYPE_ERROR` | `params` 非对象或字段类型错误 |
| `PARAM_VALIDATION_ERROR` | 缺必填 / 枚举 / 成对 / 互斥 / 日期顺序等业务参数问题 |
| `PARAM_CONFLICT_ERROR` | 参数组合冲突 |
| `PARAMS_FILE_ERROR` | `@file` 参数文件读取失败 |
| `ROUTE_ERROR` | `server_type` 或 `tool_name` 非法 |
| `USAGE_ERROR` | 命令用法错误 |
| `RATE_LIMIT_ERROR` | 请求过频（HTTP 429） |
| `NETWORK_ERROR` | 网络/服务暂不可用（HTTP 5xx 或连接失败） |
| `TOOL_RUNTIME_ERROR` | 响应解析失败 |
| `SETUP_ERROR` | 本地配置写入/环境问题 |
| `UNKNOWN` | 未归类错误 |

**接口层错误**：`code` 固定为 `backend_error`，`message` 为接口原文（如 `"认证失败"`、`"observation或者[beginDate、endDate]必须填一个"`）。这类错误直接向用户报告，不切换服务伪装成功。

---

## 4. 各 Server 与工具明细

> 约定：下表「入参」列只列该工具**自有**参数；`question` / `query` 为必填字符串（除非另注）。「出参形态」对应 §3.2 的 A/B/C/D。

### 4.1 `stock_data`（股票）

| 工具 | 用途 | 入参 | 出参形态 |
| --- | --- | --- | --- |
| `get_stock_price_indicators` | 时点行情截面（最新价/涨跌/市值/PE 等） | `windcode`(必), `indexes`(可) | A |
| `get_stock_kline` | 区间 K 线（分钟级至年） | `windcode`,`begin_date`,`end_date`(必), `period`/`aftype`/`issusp`/`afdate`(可) | A |
| `get_stock_quote` | 分钟级量价序列 | `windcode`(必), `begin`/`end`(可) | A |
| `search_stocks` | 未指定标的时按条件筛选股票 | `question` | B |
| `get_stock_basicinfo` | 公司身份与分类档案（静态） | `question` | B |
| `get_stock_fundamentals` | 财务原始指标 + 衍生估值 | `question` | B |
| `get_stock_equity_holders` | 股本结构与股东构成 | `question` | B |
| `get_stock_events` | 公司行动与事件（结构化） | `question` | B |
| `get_stock_technicals` | 派生技术指标/形态 | `question` | B |
| `get_risk_metrics` | 定量风险指标（Beta/波动/VaR/回撤等） | `question` | B |

**示例 — `get_stock_price_indicators`（形态 A）**

```bash
node scripts/cli.mjs call stock_data get_stock_price_indicators \
  '{"windcode":"600519.SH","indexes":"中文简称,最新成交价,涨跌幅,总市值1,市盈率(TTM),股息率"}'
```

`content[0].text` 展开后：

```json
{
  "data": {
    "columns": [
      {"name":"中文简称","type":"string"}, {"name":"最新成交价","type":"string"},
      {"name":"涨跌幅","type":"string"}, {"name":"总市值1","type":"string"},
      {"name":"市盈率(TTM)","type":"string"}, {"name":"股息率","type":"string"},
      {"name":"Wind代码","type":"string"}
    ],
    "rows": [["贵州茅台","1304.66","2.50","1.63093e+12","20.028","3.99","600519.SH"]],
    "unit": {"总市值1":"元","最新成交价":"元"}
  },
  "error": null
}
```

> 注意：`indexes` 传入的字段名必须逐字来自 `references/stock-indicators.md`。无效字段（如误写「总市值」「市盈率PE(TTM)」）会在返回体 `data.message` 里提示「无效的行情指标: ...」并被忽略。

**示例 — `get_stock_kline`（形态 A，多行序列）**

```bash
node scripts/cli.mjs call stock_data get_stock_kline \
  '{"windcode":"600519.SH","begin_date":"2026-08-18","end_date":"2026-08-22","period":"1d"}'
```

```json
{
  "data": {
    "columns": [
      {"name":"TIME","type":"string"},{"name":"OPEN","type":"string"},{"name":"MATCH","type":"string"},
      {"name":"HIGH","type":"string"},{"name":"LOW","type":"string"},{"name":"TURNOVER","type":"string"},
      {"name":"VOLUME","type":"string"},{"name":"CHANGEHANDRATE","type":"string"},{"name":"AVPRICE","type":"string"}
    ],
    "rows": [
      ["2026-08-18T00:00:00.000+08:00","1291.00","1297.99","1302.90","1285.17","5007014692","3872283","0.3098","1293.04"],
      ["2026-08-19T00:00:00.000+08:00","1300.00","1307.88","1308.88","1290.50","4876774762","3754751","0.3004","1298.83"],
      ["2026-08-21T00:00:00.000+08:00","1291.50","1272.83","1291.50","1272.01","4278311022","3347231","0.2678","1278.16"]
    ],
    "unit": {"OPEN 单位：":"元","MATCH 单位：":"元","VOLUME 单位：":"股","TURNOVER 单位：":"元"}
  },
  "error": null
}
```

（列含义：TIME 时间、OPEN 开、MATCH 收、HIGH 高、LOW 低、TURNOVER 成交额、VOLUME 成交量、CHANGEHANDRATE 换手率、AVPRICE 均价。）

**示例 — `get_stock_fundamentals`（形态 B，列带 `unit`）**

```bash
node scripts/cli.mjs call stock_data get_stock_fundamentals \
  '{"question":"查询贵州茅台（600519.SH）2024-12-31的ROE、营业收入和净利润"}'
```

```json
{
  "data": {
    "data": [{
      "columns": [
        {"name":"Wind代码","type":"string"}, {"name":"证券简称","type":"string"},
        {"name":"2024年ROE","type":"number","unit":"%"},
        {"name":"2024年营业收入","type":"number","unit":"亿元"},
        {"name":"2024年净利润","type":"number","unit":"亿元"}
      ],
      "rows": [["600519.SH","贵州茅台",38.4283,1708.9915,893.3473]]
    }]
  },
  "error": null
}
```

**示例 — `search_stocks`（形态 B，筛选返回代码列表，节选）**

```bash
node scripts/cli.mjs call stock_data search_stocks \
  '{"question":"筛选沪深市场市值超2000亿且股息率超3%的股票"}'
```

```json
{
  "data": {
    "data": [{
      "columns": [
        {"name":"Wind代码","type":"string"}, {"name":"证券简称","type":"string"},
        {"name":"总市值1","type":"number","unit":"亿元"}, {"name":"交易币种","type":"string"},
        {"name":"股息率TTM","type":"number","unit":"%"}
      ],
      "rows": [
        ["601857.SH","中国石油",19938.2003,"CNY",4.2077],
        ["600519.SH","贵州茅台",16309.3146,"CNY",3.9875],
        ["000651.SZ","格力电器",2321.7827,"CNY",7.2302]
      ]
    }]
  },
  "error": null
}
```

> `search_*` 返回的是符合条件的代码列表（本例实测 32 行，此处节选 3 行），可再传入各属性工具取详情。

### 4.2 `fund_data`（基金 / ETF / LOF）

| 工具 | 用途 | 入参 | 出参形态 |
| --- | --- | --- | --- |
| `get_fund_price_indicators` | 场内基金(ETF/LOF)时点行情 | `windcode`(必), `indexes`(可) | A |
| `get_fund_kline` | 场内基金区间 K 线 | `windcode`,`begin_date`,`end_date`(必), `period`/`aftype`/`issusp`/`afdate`(可) | A |
| `get_fund_quote` | 场内基金分钟序列 | `windcode`(必), `begin`/`end`(可) | A |
| `search_funds` | 未指定产品时按条件筛选基金 | `question` | B |
| `get_fund_info` | 产品档案（静态/准静态） | `question` | B |
| `get_fund_financials` | 基金财务报表与分红 | `question` | B |
| `get_fund_holdings` | 投资组合/持仓 | `question` | B |
| `get_fund_holders` | 份额、规模与持有人结构 | `question` | B |
| `get_fund_performance` | 净值、业绩度量与评价 | `question` | B |
| `get_fund_company_info` | 管理人（基金公司）档案 | `question` | B |

- 场外基金代码如 `005827.OF`；ETF/LOF 如 `588200.SH`、`159915.SZ`。
- 场外基金没有场内行情，其价格口径为净值，走 `get_fund_performance`；价格指标/K线/分钟仅限场内基金。
- `indexes` 取值来自 `references/fund-indicators.md`。

**示例 — `get_fund_info`（形态 B）**

```bash
node scripts/cli.mjs call fund_data get_fund_info \
  '{"question":"易方达蓝筹精选混合(005827.OF)的基金经理、成立日期和管理费率"}'
```

```json
{
  "data": {
    "data": [{
      "columns": [
        {"name":"Wind代码","type":"string"}, {"name":"证券简称","type":"string"},
        {"name":"现任基金经理姓名","type":"string"}, {"name":"基金成立日","type":"date"},
        {"name":"管理费率_支持历史","type":"number","unit":"%"}
      ],
      "rows": [["005827.OF","易方达蓝筹精选","张坤,何一铖,杨思亮","2018-09-05",1.2]]
    }]
  },
  "error": null
}
```

### 4.3 `index_data`（指数 / 板块）

| 工具 | 用途 | 入参 | 出参形态 |
| --- | --- | --- | --- |
| `get_index_price_indicators` | 指数时点行情 | `windcode`(必), `indexes`(可) | A |
| `get_index_kline` | 指数区间 K 线 | `windcode`,`begin_date`,`end_date`(必), `period`/`aftype`/`issusp`/`afdate`(可) | A |
| `get_index_quote` | 指数分钟点位序列 | `windcode`(必), `begin`/`end`(可) | A |
| `get_index_basicinfo` | 指数静态概况与关联信息 | `question` | B |
| `get_index_fundamentals` | 成份股加权基本面/估值 | `question` | B |
| `get_index_technicals` | 指数派生技术指标 | `question` | B |

- 已确认的标准代码可直传，如 `000300.SH`、`HSI.HI`；不猜未知后缀。`indexes` 取值来自 `references/index-indicators.md`。

**示例 — `get_index_price_indicators`（形态 A）**

```bash
node scripts/cli.mjs call index_data get_index_price_indicators \
  '{"windcode":"000300.SH","indexes":"中文简称,最新成交价,涨跌幅,成交额"}'
```

```json
{
  "data": {
    "columns": [
      {"name":"中文简称","type":"string"},{"name":"最新成交价","type":"string"},
      {"name":"涨跌幅","type":"string"},{"name":"成交额","type":"string"},{"name":"Wind代码","type":"string"}
    ],
    "rows": [["沪深300","4563.13","-1.21","590425593700","000300.SH"]],
    "unit": {"成交额":"元"}
  },
  "error": null
}
```

### 4.4 `bond_data`（债券）

> 债券服务**没有**行情快照 / K 线 / 分钟工具；四个工具均为自然语言 `question`，返回形态 B。

| 工具 | 用途 | 入参 | 出参形态 |
| --- | --- | --- | --- |
| `get_bond_basicinfo` | 债券静态档案（发行要素/评级/类型） | `question` | B |
| `get_bond_issuer_info` | 发债主体档案 | `question` | B |
| `get_bond_market_data` | 区间行情与估值（价格/收益率/久期等） | `question` | B |
| `get_bond_financial_data` | 发债主体财务数据（报告期） | `question` | B |

**示例 — `get_bond_basicinfo`（形态 B）**

```bash
node scripts/cli.mjs call bond_data get_bond_basicinfo \
  '{"question":"查询24国债01(019742.SH)的票面利率、期限和到期日期"}'
```

```json
{
  "data": {
    "data": [{
      "columns": [
        {"name":"Wind代码","type":"string"}, {"name":"证券简称","type":"string"},
        {"name":"票面利率_指定日期","type":"number","unit":"%"},
        {"name":"剩余期限_下一行权日","type":"number","unit":"年"},
        {"name":"到期日期","type":"date"}
      ],
      "rows": [
        ["019742.SH","24特国01",2.57,27.737,"2054-05-20"],
        ["019732.SH","24国债01",2.37,2.3945,"2029-01-15"]
      ]
    }]
  },
  "error": null
}
```

### 4.5 `financial_docs`（公告 / 新闻，RAG）

> 本域自然语言参数为 **`query`**（不是 `question`），返回形态 D。

| 工具 | 用途 | 入参 | 出参形态 |
| --- | --- | --- | --- |
| `get_company_announcements` | 检索上市公司公告文本 | `query`(必), `top_k`(可，默认 5) | D |
| `get_financial_news` | 检索财经新闻文本 | `query`(必), `top_k`(可，默认 5) | D |

**示例 — `get_financial_news`（形态 D，正文与部分条目已截断）**

```bash
node scripts/cli.mjs call financial_docs get_financial_news \
  '{"query":"美联储利率政策","top_k":2}'
```

```json
{
  "data": {
    "items": [
      {
        "title": "美联储公布最新利率决议",
        "date": "2026-07-30",
        "doc_type": "news",
        "relevance": 0.964,
        "content": "……美联储宣布将联邦基金利率目标区间维持在3.5%至3.75%之间不变……（正文截断）",
        "url": "https://t.wind.com.cn/mobwftweb/M/news.html?...（略）"
      }
    ],
    "total": 5
  },
  "error": null
}
```

每条含 `title` / `date` / `doc_type` / `relevance`(相关度) / `content`(正文) / `url`。`total` 为本次返回条数。

### 4.6 `economic_data`（宏观 / 行业 EDB 指标）

> 两个工具分工明确：**先 `search` 确认代码，再 `query` 取数**。自然语言统一用 `question`；日期用 `beginDate`/`endDate` 或 `observation`。

| 工具 | 用途 | 入参 | 出参形态 |
| --- | --- | --- | --- |
| `search_economic_indicator` | 找指标 / 确认代码（**不取数值**） | `question`（仅此一项） | C-search |
| `query_economic_indicator_data` | 取指标时间序列数值 | `question`(必) + (`beginDate`+`endDate`) **或** `observation` | C-query |

**示例 — `search_economic_indicator`（形态 C，返回指标元信息数组）**

```bash
node scripts/cli.mjs call economic_data search_economic_indicator \
  '{"question":"中国GDP现价当季值相关指标"}'
```

```json
{
  "metrics": [
    {
      "code": "M5567876", "name": "中国:GDP:现价:当季值",
      "unit": "亿元", "source": "国家统计局",
      "magnitude": "亿", "currency": "人民币",
      "updateDate": "20260720", "freq": "季"
    }
  ]
}
```

**示例 — `query_economic_indicator_data`（形态 C，`meta` + 等长 `date[]`/`value[]`）**

```bash
node scripts/cli.mjs call economic_data query_economic_indicator_data \
  '{"question":"中国GDP现价当季值","observation":"4"}'
```

```json
{
  "metrics": [
    {
      "meta": {
        "code": "M5567876", "name": "中国:GDP:现价:当季值",
        "unit": "亿元", "source": "国家统计局",
        "magnitude": "亿", "currency": "人民币",
        "updateDate": "20260720", "freq": "季"
      },
      "date":  ["20250930","20251231","20260331","20260630"],
      "value": [354106.2, 387911.3, 334192.9, 361511.1]
    }
  ]
}
```

- `question` 也可直接传指标代码（如 `M5567876`，多个用英文逗号分隔）。
- 只给 `question` 不给时间范围会被拒（`PARAM_VALIDATION_ERROR` / 后端 `backend_error`）。
- 无匹配时后端返回纯文本「没有搜索到指标」，`content[0].text` 原样透传。

### 4.7 `analytics_data`（跨标的聚合 / 计算）

> 仅当专项工具无法覆盖（字段/口径/无结果）时兜底；**不得**替代行情/K线/分钟/价格指标。返回**计算结果**（形态 B），不返回实体列表。

| 工具 | 用途 | 入参 | 出参形态 |
| --- | --- | --- | --- |
| `get_financial_data` | 自定义指标组合、跨实体聚合、加权/排名/复合推导 | `question` | B |

**示例 — `get_financial_data`（形态 B，聚合结果）**

```bash
node scripts/cli.mjs call analytics_data get_financial_data \
  '{"question":"贵州茅台、五粮液、泸州老窖三只股票最新总市值的合计"}'
```

```json
{
  "data": {
    "data": [{
      "columns": [{"name":"最新总市值合计","type":"number","unit":"万亿元"}],
      "rows": [[2.0343]]
    }]
  },
  "error": null
}
```

---

## 5. 错误信封示例

**参数校验失败（日期顺序）：**

```bash
node scripts/cli.mjs call stock_data get_stock_kline \
  '{"windcode":"600519.SH","begin_date":"2026-08-22","end_date":"2026-08-18","period":"1d"}'
```

```json
{ "ok": false, "code": "PARAM_VALIDATION_ERROR", "message": "字段 'begin_date' 不能晚于 'end_date'" }
```

**缺少时间范围（economic 取数）：**

```bash
node scripts/cli.mjs call economic_data query_economic_indicator_data '{"question":"中国GDP"}'
```

```json
{
  "ok": false,
  "code": "PARAM_VALIDATION_ERROR",
  "message": "query_economic_indicator_data 必须显式提供 observation 或 beginDate/endDate（不能只给 question）"
}
```

**接口层认证失败（后端原文）：**

```json
{ "ok": false, "code": "backend_error", "message": "认证失败" }
```

---

## 6. 完成状态（供调用方收口）

SKILL.md 约定的收口状态：`DONE`、`DONE_WITH_LIMITS`、`NO_RESULTS`、`BLOCKED_KEY`、`BLOCKED_QUOTA`、`BLOCKED_RUNTIME`、`OUT_OF_SCOPE`。

成功返回数据时附数据来源声明（语言随提问语言）：

> 数据来源于万得 Wind 金融数据服务。 / Data sourced from Wind Financial Data Service.

---

*本文档基于 wind-mcp-skill CLI v2.0.3，示例为 2026-08-24 实测。字段与形态若与 `references/*.md` 契约不一致，以契约与实测返回为准。*
