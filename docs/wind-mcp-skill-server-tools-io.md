# Wind MCP Skill — Server 与工具 入参 / 出参参考（逐工具）

本文件逐个记录 `skills/wind-mcp-skill`（CLI 版本 **2.0.3**）通过本地 CLI 访问的 **7 个 Wind MCP 服务、35 个工具**的入参、出参、格式与**每个工具的实测示例**。所有示例均为 **2026-08-24 实测**，数值随行情/报告期变化，仅示字段与形态。

- 契约权威来源：`skills/wind-mcp-skill/references/*.md`
- 工具清单权威：`skills/wind-mcp-skill/scripts/tool-manifest.json`
- 校验/规范化规则：`skills/wind-mcp-skill/scripts/call-rules.json`
- 信封实现：`skills/wind-mcp-skill/scripts/cli.mjs`

---

## 1. 调用方式（统一入口）

```bash
node scripts/cli.mjs call <server_type> <tool_name> '<params_json>'
```

- 先 `cd` 到 `skills/wind-mcp-skill/`（SKILL.md 所在目录），再用相对路径执行。
- `<params_json>` 是一个 JSON 对象。POSIX shell 优先内联传参；非 POSIX 环境（PowerShell / cmd / 执行器包装）将 UTF-8 JSON 写入 `scripts/request-<后缀>.json`，以 `@scripts/request-<后缀>.json` 传入，调用后删除。
- 认证 Key 读取顺序：`~/.wind-aifinmarket/config`（`WIND_API_KEY=`）> skill 本地 `config.json`（`{"wind_api_key":"..."}`）> 环境变量 `WIND_API_KEY`。

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

- **自然语言工具**统一只传一个字符串：绝大多数领域用 **`question`**；**`financial_docs` 例外用 `query`**。
- **代码型工具**（价格指标 / K线 / 分钟）用结构化参数：

| 字段 | 适用 | 类型 | 格式 / 约束 |
| --- | --- | --- | --- |
| `windcode` | 价格指标 / K线 / 分钟 | string | 名称或 Wind 代码，如 `贵州茅台` 或 `600519.SH`；价格指标支持逗号分隔多标的，单次 ≤50 个 |
| `indexes` | 价格指标 | string | 指标字段名，逗号分隔；须逐字取自 `references/*-indicators.md`，表外字段被判「无效的行情指标」并忽略 |
| `begin_date` / `end_date` | K线 | string | **必填**，`yyyy-MM-dd`；`begin_date` 不得晚于 `end_date` |
| `begin` / `end` | 分钟 | string | 可选，`yyyy-MM-dd`；缺省=最新交易日；不可只传 `end` |
| `period` | K线 | string | `1min/5min/10min/15min/30min/60min/120min/240min/1d/1w/1mo/1y/1q/6mo`，默认 `1d`（CLI 自动映射为后端编码，日 K 传 `1d`） |
| `aftype` | K线 | string | `0`=前复权(默认)/`1`=后复权/`2`=不复权 |
| `issusp` | K线 | string | `0`=不含停牌/`1`=含停牌(默认) |
| `beginDate` / `endDate` | economic 取数 | string | `yyyy-MM-dd`，须成对；与 `observation` 互斥 |
| `observation` | economic 取数 | string | 近 N 期数字字符串如 `"10"`；与 `beginDate`/`endDate` 互斥 |
| `top_k` | financial_docs | integer | 返回文档数（默认 5） |

---

## 3. 出参（返回结果）通用结构

每次 `call` 的 stdout 只有两种形态：**成功是数据对象，失败是错误信封**。

**成功信封**：顶层是 MCP `result`，业务数据在 `content[0].text`（**通常是 JSON 字符串，需二次解析**），CLI 另附 `cli_meta`：

```json
{
  "content": [ { "type": "text", "text": "<后端业务 JSON 字符串>" } ],
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

`cli_meta`：`server_type`/`tool_name` 回显路由；`tables[].actual_row_count` 是每个数据块的**实际返回行数**（只报实际行数）；`warnings` 非空须保留数据并说明（如 `BACKEND_INVALID_AS_NULL`：`INVALID`→`null`；`UNRELIABLE_DECLARED_COUNT`：`excelTotalCount` 不可据以判断完整性）；`completeness` 正常为 `not_asserted`。

读值要点：
- **单位/量级** 以返回体自带元数据为准——行情类在 `data.unit`，列定义里可能带 `unit`，EDB 在 `meta.unit` / `meta.magnitude`；缺失则保留原值并标注单位未知，不自行换算。
- `null` 表示缺失/不适用，**禁止当 0**。
- 无匹配时后端可能返回纯文本（如 economic「没有搜索到指标」）而非 JSON，`content[0].text` 原样透传。

**失败信封**：`{ "ok": false, "code": "...", "message": "..." }`。错误码见 §5。

> **下文各工具示例只展开 `content[0].text` 内的业务 JSON**（省略外层 `content`/`isError`/`cli_meta` 包裹）；序列/列表类只截取前 2 行、条数在文字中标注，`…` 表示截断。

---

## 4. `stock_data`（股票，10 个工具）

### 4.1 `get_stock_price_indicators` — 时点行情截面
入参：`windcode`(必), `indexes`(可，取自 `references/stock-indicators.md`)

```bash
node scripts/cli.mjs call stock_data get_stock_price_indicators \
  '{"windcode":"600519.SH","indexes":"中文简称,最新成交价,涨跌幅,总市值1,市盈率(TTM),股息率"}'
```
```json
{"data":{"columns":[{"name":"中文简称","type":"string"},{"name":"最新成交价","type":"string"},{"name":"涨跌幅","type":"string"},{"name":"总市值1","type":"string"},{"name":"市盈率(TTM)","type":"string"},{"name":"股息率","type":"string"},{"name":"Wind代码","type":"string"}],
"rows":[["贵州茅台","1304.66","2.50","1.63093e+12","20.028","3.99","600519.SH"]],
"unit":{"总市值1":"元","最新成交价":"元"}},"error":null}
```
> `indexes` 字段名须逐字匹配；无效字段（如「总市值」「市盈率PE(TTM)」）会在 `data.message` 提示「无效的行情指标: ...」并被忽略。

### 4.2 `get_stock_kline` — 区间 K 线
入参：`windcode`,`begin_date`,`end_date`(必), `period`/`aftype`/`issusp`/`afdate`(可)

```bash
node scripts/cli.mjs call stock_data get_stock_kline \
  '{"windcode":"600519.SH","begin_date":"2026-08-18","end_date":"2026-08-22","period":"1d"}'
```
返回 4 行（每行一个周期），节选 2 行：
```json
{"data":{"columns":[{"name":"TIME","type":"string"},{"name":"OPEN","type":"string"},{"name":"MATCH","type":"string"},{"name":"HIGH","type":"string"},{"name":"LOW","type":"string"},{"name":"TURNOVER","type":"string"},{"name":"VOLUME","type":"string"},{"name":"CHANGEHANDRATE","type":"string"},{"name":"AVPRICE","type":"string"}],
"rows":[["2026-08-18T00:00:00.000+08:00","1291.00","1297.99","1302.90","1285.17","5007014692","3872283","0.3098","1293.04"],
        ["2026-08-19T00:00:00.000+08:00","1300.00","1307.88","1308.88","1290.50","4876774762","3754751","0.3004","1298.83"]],
"unit":{"OPEN 单位：":"元","MATCH 单位：":"元","VOLUME 单位：":"股","TURNOVER 单位：":"元"}},"error":null}
```
> 列义：TIME 时间、OPEN 开、MATCH 收、HIGH 高、LOW 低、TURNOVER 成交额、VOLUME 成交量、CHANGEHANDRATE 换手率、AVPRICE 均价。

### 4.3 `get_stock_quote` — 分钟量价序列
入参：`windcode`(必), `begin`/`end`(可)

```bash
node scripts/cli.mjs call stock_data get_stock_quote \
  '{"windcode":"600519.SH","begin":"2026-08-21","end":"2026-08-21"}'
```
单日返回 238 条（每分钟一条），节选 2 条（列同 K 线）：
```json
{"data":{"columns":[{"name":"TIME"},{"name":"OPEN"},{"name":"MATCH"},{"name":"HIGH"},{"name":"LOW"},{"name":"TURNOVER"},{"name":"VOLUME"},{"name":"CHANGEHANDRATE"},{"name":"AVPRICE"}],
"rows":[["2026-08-21T09:30:00.000+08:00","1291.50","1285.00","1291.50","1285.00","77855842","60400","0.0048","1289.00"],
        ["2026-08-21T09:31:00.000+08:00","1284.99","1288.38","1290.99","1282.60","75028829","58300","0.0047","1286.94"]],
"unit":{"MATCH 单位：":"元","VOLUME 单位：":"股","TURNOVER 单位：":"元"}},"error":null}
```

### 4.4 `search_stocks` — 条件筛选（未指定标的）
入参：`question`

```bash
node scripts/cli.mjs call stock_data search_stocks \
  '{"question":"筛选沪深市场市值超2000亿且股息率超3%的股票"}'
```
返回 32 行代码列表，节选 3 行：
```json
{"data":{"data":[{"columns":[{"name":"Wind代码","type":"string"},{"name":"证券简称","type":"string"},{"name":"总市值1","type":"number","unit":"亿元"},{"name":"交易币种","type":"string"},{"name":"股息率TTM","type":"number","unit":"%"}],
"rows":[["601857.SH","中国石油",19938.2003,"CNY",4.2077],
        ["600519.SH","贵州茅台",16309.3146,"CNY",3.9875],
        ["000651.SZ","格力电器",2321.7827,"CNY",7.2302]]}]},"error":null}
```
> 返回代码可再传入各属性工具取详情。

### 4.5 `get_stock_basicinfo` — 公司档案（静态）
入参：`question`

```bash
node scripts/cli.mjs call stock_data get_stock_basicinfo \
  '{"question":"查询贵州茅台（600519.SH）的基本档案"}'
```
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"注册资本","unit":"亿元"},{"name":"公司中文名称"},{"name":"公司英文名称"},{"name":"公司属性"},{"name":"成立日期","type":"date"},{"name":"员工总数","unit":"人"},{"name":"城市"},{"name":"注册资本币种"}],
"rows":[["600519.SH","贵州茅台",12.5008,"贵州茅台酒股份有限公司","Kweichow Moutai Co.,Ltd.","地方国有企业","1999-11-20",34992,"仁怀市","CNY"]]}]},"error":null}
```

### 4.6 `get_stock_fundamentals` — 财务与估值
入参：`question`

```bash
node scripts/cli.mjs call stock_data get_stock_fundamentals \
  '{"question":"查询贵州茅台（600519.SH）2024-12-31的ROE、营业收入和净利润"}'
```
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"2024年ROE","type":"number","unit":"%"},{"name":"2024年营业收入","type":"number","unit":"亿元"},{"name":"2024年净利润","type":"number","unit":"亿元"}],
"rows":[["600519.SH","贵州茅台",38.4283,1708.9915,893.3473]]}]},"error":null}
```

### 4.7 `get_stock_equity_holders` — 股本与股东
入参：`question`

```bash
node scripts/cli.mjs call stock_data get_stock_equity_holders \
  '{"question":"查询贵州茅台（600519.SH）的前十大股东及流通A股占比"}'
```
返回**两个数据块**：前十大股东（10 行，节选 2）＋股本占比（1 行）：
```json
{"data":{"data":[
  {"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"前十大股东名称"},{"name":"前十大股东持股比例","type":"number","unit":"%"},{"name":"名次","type":"number"}],
   "rows":[["600519.SH","贵州茅台","中国贵州茅台酒厂(集团)有限责任公司",54.5,1],
           ["600519.SH","贵州茅台","贵州省国有资本运营有限责任公司",4.56,2]]},
  {"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"流通A股","unit":"股"},{"name":"总股本","unit":"股"},{"name":"流通A股占总股本比例"}],
   "rows":[["600519.SH","贵州茅台",1250081601,1250081601,1]]}
]},"error":null}
```

### 4.8 `get_stock_events` — 公司行动与事件（结构化）
入参：`question`

```bash
node scripts/cli.mjs call stock_data get_stock_events \
  '{"question":"查询贵州茅台（600519.SH）2024年的分红派息"}'
```
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"2024年每股收益EPS_期末股本摊薄","unit":"元"},{"name":"2024年净利润","unit":"亿元"},{"name":"2024年现金分红总额","unit":"亿元"},{"name":"2024年每股股利_税前","unit":"元"},{"name":"2024年股息率","unit":"%"},{"name":"2024年股利支付率","unit":"%"}],
"rows":[["600519.SH","贵州茅台",68.6422,893.3473,346.7116,27.673,4.8467,40.3149]]}]},"error":null}
```

### 4.9 `get_stock_technicals` — 派生技术指标/形态
入参：`question`

```bash
node scripts/cli.mjs call stock_data get_stock_technicals \
  '{"question":"查询贵州茅台（600519.SH）最新的MACD和20日涨跌幅"}'
```
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"近20交易日涨跌幅","type":"number","unit":"%"},{"name":"最新DIFF值","type":"number"},{"name":"最新DEA值","type":"number"},{"name":"最新MACD值","type":"number"}],
"rows":[["600519.SH","贵州茅台",1.1756,5.1544,13.6044,-16.8999]]}]},"error":null}
```

### 4.10 `get_risk_metrics` — 定量风险指标
入参：`question`

```bash
node scripts/cli.mjs call stock_data get_risk_metrics \
  '{"question":"查询宁德时代（300750.SZ）过去1年的Beta、年化波动率和最大回撤"}'
```
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"过去1年BETA","type":"number"},{"name":"过去1年最大回撤","type":"number","unit":"%"}],
"rows":[["300750.SZ","宁德时代",0.9098,-24.1826]]}]},"error":null}
```

---

## 5. `fund_data`（基金 / ETF / LOF，10 个工具）

> 场外基金代码如 `005827.OF`（价格口径为净值，走 `get_fund_performance`）；ETF/LOF 如 `588200.SH`（有场内行情）。`indexes` 取自 `references/fund-indicators.md`。

### 5.1 `get_fund_price_indicators` — 场内基金时点行情
入参：`windcode`(必), `indexes`(可)

```bash
node scripts/cli.mjs call fund_data get_fund_price_indicators \
  '{"windcode":"588200.SH","indexes":"中文简称,最新成交价,涨跌幅,成交额,IOPV,贴水率"}'
```
```json
{"data":{"columns":[{"name":"中文简称"},{"name":"最新成交价"},{"name":"涨跌幅"},{"name":"成交额"},{"name":"IOPV"},{"name":"贴水率"},{"name":"Wind代码"}],
"rows":[["科创芯片ETF嘉实","1.134","-3.32","3430786891","1.1348","-3.333","588200.SH"]],
"unit":{"成交额":"元"}},"error":null}
```
> `贴水率` 即场内溢折率（正溢价/负折价）；`七日年化收益率`、`万份基金收益` 仅货币基金有效。

### 5.2 `get_fund_kline` — 场内基金区间 K 线
入参：`windcode`,`begin_date`,`end_date`(必), `period`/`aftype`/`issusp`/`afdate`(可)

```bash
node scripts/cli.mjs call fund_data get_fund_kline \
  '{"windcode":"588200.SH","begin_date":"2026-08-18","end_date":"2026-08-22","period":"1d"}'
```
返回 4 行，节选 2 行（列同股票 K 线）：
```json
{"data":{"columns":[{"name":"TIME"},{"name":"OPEN"},{"name":"MATCH"},{"name":"HIGH"},{"name":"LOW"},{"name":"TURNOVER"},{"name":"VOLUME"},{"name":"CHANGEHANDRATE"},{"name":"AVPRICE"}],
"rows":[["2026-08-18T00:00:00.000+08:00","1.273","1.275","1.285","1.245","3959456751","3128078365","7.464","1.266"],
        ["2026-08-19T00:00:00.000+08:00","1.240","1.177","1.244","1.165","5082450956","4228774929","10.069","1.202"]],
"unit":{"TURNOVER 单位：":"元"}},"error":null}
```

### 5.3 `get_fund_quote` — 场内基金分钟序列
入参：`windcode`(必), `begin`/`end`(可)

```bash
node scripts/cli.mjs call fund_data get_fund_quote \
  '{"windcode":"588200.SH","begin":"2026-08-21","end":"2026-08-21"}'
```
单日返回 240 条，节选 2 条：
```json
{"data":{"columns":[{"name":"TIME"},{"name":"OPEN"},{"name":"MATCH"},{"name":"HIGH"},{"name":"LOW"},{"name":"TURNOVER"},{"name":"VOLUME"},{"name":"CHANGEHANDRATE"},{"name":"AVPRICE"}],
"rows":[["2026-08-21T09:30:00.000+08:00","1.171","1.174","1.175","1.166","41700477","35609475","0.0836","1.171"],
        ["2026-08-21T09:31:00.000+08:00","1.174","1.170","1.176","1.168","28319711","24168311","0.0567","1.172"]],
"unit":{"TURNOVER 单位：":"元"}},"error":null}
```

### 5.4 `search_funds` — 条件筛选（未指定产品）
入参：`question`

```bash
node scripts/cli.mjs call fund_data search_funds \
  '{"question":"筛选股票型基金中近一年收益率超20%的产品"}'
```
返回 100 行，节选 2 行：
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"近1年回报","type":"number","unit":"%"}],
"rows":[["024662.OF","富国创业板人工智能ETF联接A",50.1845],
        ["012552.OF","天弘中证芯片产业ETF联接A",48.9387]]}]},"error":null}
```

### 5.5 `get_fund_financials` — 基金财务报表与分红
入参：`question`

```bash
node scripts/cli.mjs call fund_data get_fund_financials \
  '{"question":"查询易方达蓝筹精选(005827.OF)最近一个报告期的基金利润和管理费"}'
```
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"最新报告期利润","type":"number","unit":"亿元"},{"name":"最新基金管理费","type":"number","unit":"亿元"}],
"rows":[["005827.OF","易方达蓝筹精选",27.9703,4.3495]]}]},"error":null}
```

### 5.6 `get_fund_holdings` — 持仓 / 投资组合
入参：`question`

```bash
node scripts/cli.mjs call fund_data get_fund_holdings \
  '{"question":"查询易方达蓝筹精选(005827.OF)最新的前十大重仓股"}'
```
返回 10 行，节选 2 行：
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"前十名重仓股股票代码"},{"name":"前十名重仓股票名称"},{"name":"前十名重仓股持股市值","type":"number","unit":"亿元"},{"name":"前十名重仓股市值占基金资产净值比","type":"number","unit":"%"},{"name":"名次","type":"number"}],
"rows":[["005827.OF","易方达蓝筹精选","0700.HK","腾讯控股",11.6862,5.7241,1],
        ["005827.OF","易方达蓝筹精选","600519.SH","贵州茅台",11.4815,5.6238,2]]}]},"error":null}
```

### 5.7 `get_fund_holders` — 份额、规模与持有人结构
入参：`question`

```bash
node scripts/cli.mjs call fund_data get_fund_holders \
  '{"question":"查询易方达蓝筹精选(005827.OF)最新规模和机构持有比例"}'
```
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"最新规模","type":"number","unit":"亿元"},{"name":"最新机构投资者持有比例","type":"number","unit":"%"},{"name":"最新机构投资者持有比例时间"},{"name":"最新规模时间"}],
"rows":[["005827.OF","易方达蓝筹精选",310.2104,0.7715,"Q4 FY2025",null]]}]},"error":null}
```
> `最新规模时间` 为 `null`（缺失，不可当 0）。

### 5.8 `get_fund_performance` — 净值、业绩与评价
入参：`question`（场外基金唯一价格口径=净值，走本工具）

```bash
node scripts/cli.mjs call fund_data get_fund_performance \
  '{"question":"查询易方达蓝筹精选(005827.OF)近一年收益率和最大回撤"}'
```
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"近1年回报","type":"number","unit":"%"},{"name":"近1年最大回撤","type":"number","unit":"%"}],
"rows":[["005827.OF","易方达蓝筹精选",-22.6716,-28.3589]]}]},"error":null}
```

### 5.9 `get_fund_company_info` — 管理人（基金公司）档案
入参：`question`

```bash
node scripts/cli.mjs call fund_data get_fund_company_info \
  '{"question":"查询易方达蓝筹精选(005827.OF)管理人的在管规模和基金经理人数"}'
```
返回**三个数据块**：
```json
{"data":{"data":[
  {"columns":[{"name":"基金管理人"},{"name":"易方达蓝筹精选管理人在管基金规模","type":"number","unit":"万亿元"}],
   "rows":[["易方达基金管理有限公司",2.6952]]},
  {"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"现任基金经理姓名"}],
   "rows":[["005827.OF","易方达蓝筹精选","张坤,何一铖,杨思亮"]]},
  {"columns":[{"name":"易方达蓝筹精选基金经理数量","type":"number"}],
   "rows":[[1]]}
]},"error":null}
```

### 5.10 `get_fund_info` — 产品档案（静态/准静态）
入参：`question`

```bash
node scripts/cli.mjs call fund_data get_fund_info \
  '{"question":"易方达蓝筹精选混合(005827.OF)的基金经理、成立日期和管理费率"}'
```
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"现任基金经理姓名"},{"name":"基金成立日","type":"date"},{"name":"管理费率_支持历史","type":"number","unit":"%"}],
"rows":[["005827.OF","易方达蓝筹精选","张坤,何一铖,杨思亮","2018-09-05",1.2]]}]},"error":null}
```

---

## 6. `index_data`（指数 / 板块，6 个工具）

> 已确认标准代码可直传，如 `000300.SH`、`HSI.HI`。`indexes` 取自 `references/index-indicators.md`。

### 6.1 `get_index_price_indicators` — 指数时点行情
入参：`windcode`(必), `indexes`(可)

```bash
node scripts/cli.mjs call index_data get_index_price_indicators \
  '{"windcode":"000300.SH","indexes":"中文简称,最新成交价,涨跌幅,成交额"}'
```
```json
{"data":{"columns":[{"name":"中文简称"},{"name":"最新成交价"},{"name":"涨跌幅"},{"name":"成交额"},{"name":"Wind代码"}],
"rows":[["沪深300","4563.13","-1.21","590425593700","000300.SH"]],
"unit":{"成交额":"元"}},"error":null}
```

### 6.2 `get_index_kline` — 指数区间 K 线
入参：`windcode`,`begin_date`,`end_date`(必), `period`/`aftype`/`issusp`/`afdate`(可)

```bash
node scripts/cli.mjs call index_data get_index_kline \
  '{"windcode":"000300.SH","begin_date":"2026-08-18","end_date":"2026-08-22","period":"1d"}'
```
返回 4 行，节选 2 行：
```json
{"data":{"columns":[{"name":"TIME"},{"name":"OPEN"},{"name":"MATCH"},{"name":"HIGH"},{"name":"LOW"},{"name":"TURNOVER"},{"name":"VOLUME"},{"name":"CHANGEHANDRATE"},{"name":"AVPRICE"}],
"rows":[["2026-08-18T00:00:00.000+08:00","4734.07","4725.81","4744.01","4687.53","619828730100","20424551400","0.6098","4722.85"],
        ["2026-08-19T00:00:00.000+08:00","4660.06","4588.70","4674.38","4568.07","705253505400","24407009000","0.7287","4622.80"]],
"unit":{"TURNOVER 单位：":"元"}},"error":null}
```

### 6.3 `get_index_quote` — 指数分钟点位序列
入参：`windcode`(必), `begin`/`end`(可)

```bash
node scripts/cli.mjs call index_data get_index_quote \
  '{"windcode":"000300.SH","begin":"2026-08-21","end":"2026-08-21"}'
```
单日返回 240 条，节选 2 条：
```json
{"data":{"columns":[{"name":"TIME"},{"name":"OPEN"},{"name":"MATCH"},{"name":"HIGH"},{"name":"LOW"},{"name":"TURNOVER"},{"name":"VOLUME"},{"name":"CHANGEHANDRATE"},{"name":"AVPRICE"}],
"rows":[["2026-08-21T09:30:00.000+08:00","4585.44","4588.80","4588.84","4585.44","17255188900","574048500","0.0171","4587.13"],
        ["2026-08-21T09:31:00.000+08:00","4589.02","4582.55","4589.02","4582.51","9583912600","327580400","0.0269","4585.77"]],
"unit":{"TURNOVER 单位：":"元"}},"error":null}
```

### 6.4 `get_index_basicinfo` — 指数静态概况
入参：`question`

```bash
node scripts/cli.mjs call index_data get_index_basicinfo \
  '{"question":"查询沪深300指数的基本信息，包括发布机构、基日和成份股数量"}'
```
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"发布机构"},{"name":"基期","type":"date"},{"name":"成份个数","type":"number","unit":"个"}],
"rows":[["000300.SH","沪深300","中证指数有限公司","2004-12-31",300]]}]},"error":null}
```

### 6.5 `get_index_fundamentals` — 成份股加权基本面/估值
入参：`question`

```bash
node scripts/cli.mjs call index_data get_index_fundamentals \
  '{"question":"查询沪深300指数最新的PE和PB"}'
```
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"最新PB","type":"number","unit":"倍"},{"name":"最新PE","type":"number"},{"name":"交易时间"},{"name":"日期"}],
"rows":[["000300.SH","沪深300",1.4467,14.0439,"20260824 15:00:06","20260824"]]}]},"error":null}
```

### 6.6 `get_index_technicals` — 指数派生技术指标
入参：`question`

```bash
node scripts/cli.mjs call index_data get_index_technicals \
  '{"question":"查询沪深300指数最新的MACD和20日涨跌幅"}'
```
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"最新MACD指数平滑移动平均","type":"number"},{"name":"最新MACD指数平滑移动平均.MACD指标选项"},{"name":"近20交易日涨跌幅","type":"number","unit":"%"}],
"rows":[["000300.SH","沪深300",-28.2885,"DIFF",-2.9623]]}]},"error":null}
```

---

## 7. `bond_data`（债券，4 个工具）

> 债券服务**没有**行情快照 / K 线 / 分钟工具；四个工具均为自然语言 `question`。

### 7.1 `get_bond_basicinfo` — 债券静态档案
入参：`question`

```bash
node scripts/cli.mjs call bond_data get_bond_basicinfo \
  '{"question":"查询24国债01(019742.SH)的票面利率、期限和到期日期"}'
```
返回 2 行（NER 命中相关债券）：
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"票面利率_指定日期","type":"number","unit":"%"},{"name":"剩余期限_下一行权日","type":"number","unit":"年"},{"name":"到期日期","type":"date"}],
"rows":[["019742.SH","24特国01",2.57,27.737,"2054-05-20"],
        ["019732.SH","24国债01",2.37,2.3945,"2029-01-15"]]}]},"error":null}
```

### 7.2 `get_bond_issuer_info` — 发债主体档案
入参：`question`

```bash
node scripts/cli.mjs call bond_data get_bond_issuer_info \
  '{"question":"查询24国债01(019732.SH)发债主体的名称和主体信用评级"}'
```
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"债务主体名称"},{"name":"债务主体中文简称"},{"name":"主体评级"}],
"rows":[["019732.SH","24国债01","中华人民共和国财政部","",""]]}]},"error":null}
```
> 国债主体为财政部，`主体评级` 为空串（该口径不适用）。

### 7.3 `get_bond_market_data` — 区间行情与估值
入参：`question`

```bash
node scripts/cli.mjs call bond_data get_bond_market_data \
  '{"question":"查询24国债01(019732.SH)最新的到期收益率和修正久期"}'
```
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"最新收盘价收益率","type":"number","unit":"元"},{"name":"最新收盘价收益率.债券价格类型"},{"name":"交易币种"},{"name":"最新收盘价修正久期","type":"number"}],
"rows":[["019732.SH","24国债01",1.2011,"收益率","CNY",2.3018]]}]},"error":null}
```

### 7.4 `get_bond_financial_data` — 发债主体财务（报告期）
入参：`question`

```bash
node scripts/cli.mjs call bond_data get_bond_financial_data \
  '{"question":"查询24万科01发债主体2024年的营业收入和净利润"}'
```
```json
{"data":{"data":[{"columns":[{"name":"Wind代码"},{"name":"证券简称"},{"name":"2024年营业收入","type":"number","unit":"亿元"},{"name":"2024年净利润","type":"number","unit":"亿元"},{"name":"记账本位币"},{"name":"债务主体名称"}],
"rows":[["F1000621.00","万科企业股份有限公司",3431.7644,-487.0393,"CNY",""]]}]},"error":null}
```
> 主体财务用于公司类发债主体；国债/政金债类主体无营收口径。

---

## 8. `financial_docs`（公告 / 新闻，RAG，2 个工具）

> 本域自然语言参数为 **`query`**（不是 `question`）。每条含 `title`/`date`/`doc_type`/`relevance`(相关度)/`content`(正文)/`url`；`total` 为返回条数（实测返回条数可能不完全等于 `top_k`）。

### 8.1 `get_company_announcements` — 上市公司公告
入参：`query`(必), `top_k`(可，默认 5)

```bash
node scripts/cli.mjs call financial_docs get_company_announcements \
  '{"query":"查询贵州茅台2024年年度分红方案的公告","top_k":2}'
```
返回 4 条，正文截断，节选 1 条：
```json
{"data":{"items":[
  {"title":"贵州茅台:2024年年度利润分配方案公告",
   "date":"2025-04-03","doc_type":"announcement","relevance":0.5895,
   "content":"贵州茅台:2024年年度利润分配方案公告 证券代码：600519 编号：临2025－009 …",
   "url":"https://m.wind.com.cn/mobwftweb/M/?code=279EC2C422A7&…"}
],"total":4},"error":null}
```

### 8.2 `get_financial_news` — 财经新闻
入参：`query`(必), `top_k`(可，默认 5)

```bash
node scripts/cli.mjs call financial_docs get_financial_news \
  '{"query":"美联储利率政策","top_k":2}'
```
返回 5 条，正文截断，节选 1 条：
```json
{"data":{"items":[
  {"title":"美联储公布最新利率决议",
   "date":"2026-07-30","doc_type":"news","relevance":0.964,
   "content":"……美联储宣布将联邦基金利率目标区间维持在3.5%至3.75%之间不变……",
   "url":"https://t.wind.com.cn/mobwftweb/M/news.html?…"}
],"total":5},"error":null}
```

---

## 9. `economic_data`（宏观 / 行业 EDB 指标，2 个工具）

> **先 `search` 确认代码，再 `query` 取数**。日期用 `beginDate`/`endDate` 或 `observation`，不要塞进 `question`。

### 9.1 `search_economic_indicator` — 找指标 / 确认代码（不取数值）
入参：`question`（仅此一项，`allowed` 只允许 `question`）

```bash
node scripts/cli.mjs call economic_data search_economic_indicator \
  '{"question":"中国GDP现价当季值相关指标"}'
```
返回 `metrics` 指标元信息数组（无时间序列）：
```json
{"metrics":[{"code":"M5567876","name":"中国:GDP:现价:当季值","unit":"亿元","source":"国家统计局","magnitude":"亿","currency":"人民币","updateDate":"20260720","freq":"季"}]}
```

### 9.2 `query_economic_indicator_data` — 取时间序列数值
入参：`question`(必) + (`beginDate`+`endDate`) **或** `observation`（二者互斥；只给 `question` 会被拒）

```bash
node scripts/cli.mjs call economic_data query_economic_indicator_data \
  '{"question":"中国GDP现价当季值","observation":"4"}'
```
返回 `metrics[].{meta, date[], value[]}`（`date`/`value` 等长并行）：
```json
{"metrics":[{
  "meta":{"code":"M5567876","name":"中国:GDP:现价:当季值","unit":"亿元","source":"国家统计局","magnitude":"亿","currency":"人民币","updateDate":"20260720","freq":"季"},
  "date":["20250930","20251231","20260331","20260630"],
  "value":[354106.2,387911.3,334192.9,361511.1]
}]}
```
> `question` 也可直接传指标代码（如 `M5567876`，多个用英文逗号分隔）。

---

## 10. `analytics_data`（跨标的聚合 / 计算，1 个工具）

> 仅当专项工具无法覆盖（字段/口径/无结果）时兜底；**不得**替代行情/K线/分钟/价格指标。返回**计算结果**，不返回实体列表。

### 10.1 `get_financial_data` — 自定义指标组合 / 跨实体聚合
入参：`question`

```bash
node scripts/cli.mjs call analytics_data get_financial_data \
  '{"question":"贵州茅台、五粮液、泸州老窖三只股票最新总市值的合计"}'
```
```json
{"data":{"data":[{"columns":[{"name":"最新总市值合计","type":"number","unit":"万亿元"}],
"rows":[[2.0343]]}]},"error":null}
```

---

## 11. 错误信封示例（失败形态）

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
{ "ok": false, "code": "PARAM_VALIDATION_ERROR",
  "message": "query_economic_indicator_data 必须显式提供 observation 或 beginDate/endDate（不能只给 question）" }
```

**接口层错误（后端原文）：** `{ "ok": false, "code": "backend_error", "message": "认证失败" }`

### 错误码表

| 类别 | code | 含义 |
| --- | --- | --- |
| 本地/参数 | `AUTH_ERROR` | Key 未配置或认证失败 |
| | `INVALID_PARAMS_JSON` | `params` 不是合法 JSON |
| | `PARAM_TYPE_ERROR` | `params` 非对象或字段类型错误 |
| | `PARAM_VALIDATION_ERROR` | 缺必填/枚举/成对/互斥/日期顺序等业务参数问题 |
| | `PARAM_CONFLICT_ERROR` | 参数组合冲突 |
| | `PARAMS_FILE_ERROR` | `@file` 参数文件读取失败 |
| | `ROUTE_ERROR` | `server_type`/`tool_name` 非法 |
| | `USAGE_ERROR` | 命令用法错误 |
| 网络/运行 | `RATE_LIMIT_ERROR` | 请求过频（HTTP 429） |
| | `NETWORK_ERROR` | 网络/服务暂不可用（HTTP 5xx 或连接失败） |
| | `TOOL_RUNTIME_ERROR` | 响应解析失败 |
| | `SETUP_ERROR` | 本地配置写入/环境问题 |
| | `UNKNOWN` | 未归类错误 |
| 接口层 | `backend_error` | 接口返回错误，`message` 为后端原文 |

---

## 12. 完成状态（供调用方收口）

SKILL.md 约定的收口状态：`DONE`、`DONE_WITH_LIMITS`、`NO_RESULTS`、`BLOCKED_KEY`、`BLOCKED_QUOTA`、`BLOCKED_RUNTIME`、`OUT_OF_SCOPE`。

成功返回数据时附数据来源声明（语言随提问语言）：

> 数据来源于万得 Wind 金融数据服务。 / Data sourced from Wind Financial Data Service.

---

*本文档基于 wind-mcp-skill CLI v2.0.3，35 个工具示例均为 2026-08-24 实测抓取（`content[0].text` 已展开、序列/列表已节选）。字段与形态若与 `references/*.md` 契约或实测返回不一致，以契约与实测为准。*
