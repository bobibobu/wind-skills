# `economic_data` 工具契约

只用于宏观和行业 EDB 指标。自然语言统一使用 `question`；日期统一使用 `beginDate` / `endDate`。

- 按职责分两个工具：只要指标元信息用 `search_economic_indicator`；要具体数值时间序列用 `query_economic_indicator_data`。**工具名即模式**，不再有 `executionMode` 字段。
- `query_economic_indicator_data` 必须提供完整日期范围（`beginDate` + `endDate`）或 `observation`，两者互斥；只给 `question` 会被后端拒绝。
- 日期字段使用 `beginDate` / `endDate`，格式 `yyyy-MM-dd`。
- `observation` 只能是数字字符串（近 N 期，如 `10`），**新后端不再支持 `all`**。
- 后端将合法日期误报为 observation 格式错误时，视为后端问题：停止自动修正并透传错误。
- 不得把日期范围擅自改成 `observation`。

## 工具契约

### `search_economic_indicator`（找指标 / 确认代码，不取数）

根据自然语言需求，从 Wind EDB 经济数据库中检索并匹配相关经济指标，返回指标的元信息（指标名称、指标代码、频率、单位、来源等），**不返回具体数值数据**。适用于查找可用指标、筛选指标，以及提数前确认指标代码的场景。

输入说明：
`question`：用户的自然语言搜索问句，例如“中国近三年GDP相关指标”“上海CPI有哪些”“有哪些出口相关指标”。

返回结果：`metrics` 数组，每条为扁平的指标元信息对象（`code`、`name`、`unit`、`source`、`magnitude`、`currency`、`updateDate`、`freq`；`%` 类指标可能省略 `magnitude`/`currency`），不含时间序列。

| 参数 | 必填 | 类型 | 示例 / 默认 | 官方说明 |
| --- | --- | --- | --- | --- |
| `question` | 是 | string | 中国近三年GDP相关指标 | 自然语言搜索问句。仅描述要找的指标，不填时间与换算参数。 |

### `query_economic_indicator_data`（取时间序列数值）

根据自然语言问句**或指标代码**，从 Wind EDB 获取宏观经济指标的时间序列数据。`question` 既可传自然语言（如“提取中国GDP数据”），也可直接传指标代码（如 `M5567876`，多个代码用英文逗号分隔）。时间范围只能通过 `beginDate`/`endDate` 或 `observation` 传入，**不要塞进 `question`**。

调用约束：必须显式提供 `beginDate`+`endDate` 或 `observation`；只给 `question` 后端会返回“observation或者[beginDate、endDate]必须填一个”。

返回结果：`metrics` 数组，每条为 `{ meta, date[], value[] }`——`meta` 为指标元信息（同上 8 字段），`date[]` 与 `value[]` 为等长并行的日期与数值数组。

| 参数 | 必填 | 类型 | 枚举 | 示例 / 默认 | 官方说明 |
| --- | --- | --- | --- | --- | --- |
| `question` | 是 | string | — | 中国GDP现价当季值 / `M5567876` | 自然语言问句或指标代码（多个代码用英文逗号分隔）。时间范围通过 `beginDate`/`endDate` 或 `observation` 显式传入，不要写进 `question`。 |
| `beginDate` | 否 | string | — | 2025-01-01 | 数据提取开始日期，格式 `yyyy-MM-dd`。须与 `endDate` 成对出现；与 `observation` 互斥。 |
| `endDate` | 否 | string | — | 2025-12-31 | 数据提取结束日期，格式 `yyyy-MM-dd`。须与 `beginDate` 成对出现；与 `observation` 互斥。 |
| `observation` | 否 | string | — | 10 | 观测期数，近 N 期填数字字符串（如近10期填 `10`）。**不支持 `all`**。与 `beginDate`/`endDate` 互斥。 |

> 说明：后端另有 `targetMagnitude`/`targetCurrency`/`targetFrequency` 三个换算对齐参数，本 skill 取数模式沿用旧契约字段集，不暴露这三个字段；如需跨口径对齐/换算，交由 `analytics_data` 或后续版本处理。
