# 监控模板 API 字段完整说明文档

> **数据来源**：http://172.32.13.2:30000  
> **接口版本**：统一运维管理平台（H3C iMC 系产品，前端应用名 monitortemplateui）  
> **文档目的**：对 `/monitortemplaters/monitorTemplate/{id}` 接口返回的所有字段进行逐一说明，确保后续向他人讲解或在 Zabbix 等系统中参考使用时无歧义。  
> **文档生成时间**：2026-03-20  

---

## 目录

1. [接口概览](#接口概览)
2. [模板顶层字段](#一模板顶层字段)
3. [typeLabel 对象](#二typelabel-对象)
4. [resGroup 数组](#三resgroup-数组)
5. [unitList 数组（指标单元）](#四unitlist-数组指标单元)
6. [unitList.fields 数组（指标字段）](#五unitlistfields-数组指标字段)
7. [unitList.fields.unitGroup 对象（单位换算组）](#六unitlistfieldsunitgroup-对象单位换算组)
8. [thresholds 数组（告警阈值规则）](#七thresholds-数组告警阈值规则)
9. [thresholds.conditions 数组（阈值触发条件）](#八thresholdsconditions-数组阈值触发条件)
10. [thresholds.conditions.threshold 数组（各级别阈值定义）](#九thresholdsconditionsthreshold-数组各级别阈值定义)
11. [枚举值完整对照表](#十枚举值完整对照表)
12. [字段与网站界面的对应关系](#十一字段与网站界面的对应关系)
13. [可忽略/恒定字段说明](#十二可忽略恒定字段说明)

---

## 接口概览

### 获取模板列表（分页）

```
GET /monitortemplaters/monitorTemplatesSummary?size={n}&start={offset}&regionId=-1
```

- `size`：每页条数
- `start`：偏移量（从 0 开始）
- `regionId=-1`：查询所有区域（不过滤）
- 返回：`totalElements`（总数）、`totalPages`（总页数）、`content`（当前页模板列表）

### 获取单个模板完整详情（含指标）

```
GET /monitortemplaters/monitorTemplate/{templateId}
```

- `templateId`：模板唯一 ID（长整型数字）
- 返回：模板全量信息，包含 `unitList`（指标单元列表）和 `thresholds`（阈值规则列表）

---

## 一、模板顶层字段

| 字段名 | 类型 | 网站界面对应 | 说明 |
|--------|------|-------------|------|
| `templateId` | number | 无（内部 ID）| 模板的唯一标识符，长整型数字（18位）。与 `uuid` 字段值完全相同，两者是同一个 ID 的两种表达，可以互相替代。 |
| `uuid` | number | 无（内部 ID）| 同 `templateId`，历史冗余字段。 |
| `name` | string | 模板列表"名称"列 / 详情页"模板名称" | 模板的中文显示名称，也是用户在界面上看到的名字。如"网络设备"、"VMware ESX"。 |
| `nameEn` | string | 无（仅接口）| 模板名称的英文版本。**注意**：对于大多数内置模板，`nameEn` 和 `name` 的值相同（均为中文或英文产品名），少数自定义模板此字段有独立英文名。实际可等同于 `name` 使用。 |
| `type` | string | 模板列表"类型"列（显示 typeLabel.label）| 模板的类型标识符（英文 Key），是系统内部的唯一类型码。如 `network`、`vmware`、`linux`。这是最重要的标识字段，指标单元（unitList）中的字段均通过此值归属到对应模板类型。 |
| `typeLabel` | object | 模板列表"类型"列 | 模板类型的多语言显示名称，见[第二节](#二typelabel-对象)。 |
| `scene` | string | 无（恒定值）| 固定值为 `"MONITOR"`，表示该模板用于监控场景（区别于其他可能的场景如"巡检"）。本平台所有 236 个模板均为此值，可忽略。 |
| `custom` | boolean | 模板列表"自定义"列 | `true` = 用户自定义创建的模板；`false` = 系统内置模板（随产品预置，不可删除）。网站界面显示"是"或"否"。 |
| `def` | boolean | 无（内部标记）| `true` 表示该模板是某种资源类型的**默认模板**（即该类型资源首次接入时自动应用的模板）。本平台绝大多数内置模板均为 `true`，自定义模板为 `false`。 |
| `describe` | string / null | 详情页"模板描述" | 模板的文字描述说明。大多数内置模板此字段为 `null`（空），自定义模板可填写描述。 |
| `version` | number | 无（内部版本）| 模板数据的版本号。本平台绝大多数为 `1`，少数为 `2`（表示经过升级更新）。用于系统内部的版本管理，无需关注。 |
| `tenantId` | string | 无（租户隔离）| 租户 UUID，用于多租户环境下的数据隔离。单租户部署时所有模板的值相同，可忽略。 |
| `regionId` | number | 无（区域隔离）| 区域 ID，用于多区域部署。`-1` 表示查询时不限区域，返回的模板均属于当前默认区域。 |
| `regionPermission` | boolean | 无（权限控制）| 当前登录用户对该模板所在区域是否有操作权限。`true` = 有权限。 |
| `operationIds` | array\<number\> | 无（权限按钮控制）| 当前用户对该模板可执行的操作 ID 列表。这些数字对应系统权限体系中的具体操作（如查看=801、编辑=802、删除=803 等），前端用于控制界面按钮的显示与隐藏。普通用户无需关注此字段。 |
| `resGroup` | array | 详情页"所属机构/分组" | 模板适用的资源分组（机构/标签组），见[第三节](#三resgroup-数组)。**仅自定义模板有值**，内置模板为空数组 `[]`。 |
| `unitList` | array | 详情页"指标信息"Tab 的指标组列表 | 模板包含的所有指标单元（指标组）列表，是最核心的数据。见[第四节](#四unitlist-数组指标单元)。 |
| `thresholds` | array | 详情页"阈值信息"Tab 的阈值规则列表 | 模板预置的告警阈值规则列表。见[第七节](#七thresholds-数组告警阈值规则)。 |

---

## 二、typeLabel 对象

模板类型的多语言标签，挂载在模板顶层。

```json
"typeLabel": {
  "zh": "网络设备",
  "en": "Network Device",
  "label": "网络设备"
}
```

| 字段名 | 说明 |
|--------|------|
| `zh` | 类型名称的中文显示文本，网站界面"类型"列展示的值。 |
| `en` | 类型名称的英文显示文本，切换语言后界面展示的值。 |
| `label` | 默认 label，内容与 `zh` 完全相同，是历史冗余字段。使用 `zh` 即可。 |

---

## 三、resGroup 数组

模板关联的资源分组信息（仅自定义模板有值）。

```json
"resGroup": [
  {
    "type": "ORGAN",
    "label": "默认机构",
    "value": "209760028721152",
    "groupType": 0
  }
]
```

| 字段名 | 说明 |
|--------|------|
| `type` | 分组类型。目前只有 `"ORGAN"`（机构组织），表示按机构/部门分组。 |
| `label` | 分组的显示名称，网站界面"所属机构/分组"栏展示此值。 |
| `value` | 分组的唯一 ID（与 `operationIds` 中 `defaultManagedGroup` 响应头的值一致）。 |
| `groupType` | 分组类型的数字编码，`0` = 机构组（对应 `type: "ORGAN"`）。当前数据中均为 `0`。 |

---

## 四、unitList 数组（指标单元）

**unitList** 是模板的核心数据，对应网站界面中"指标信息"Tab 里的**指标组**列表。每个 unitList 元素代表一组相关联的指标（如"CPU"、"内存"、"接口统计"）。

```json
{
  "type": "network",
  "unit": "cpu",
  "nameZh": "CPU",
  "nameEn": "CPU Usage",
  "appname": "network",
  "collectTime": 300,
  "scope": 1,
  "defaultUsed": true,
  "defaultCp": false,
  "enableCollectTime": true,
  "dataType": "table",
  "selectedFields": null,
  "allField": true,
  "operations": null,
  "enableDelete": false,
  "mUrl": null,
  "aUrl": null,
  "typeAlias": null,
  "fields": [...]
}
```

| 字段名 | 类型 | 网站界面对应 | 说明 |
|--------|------|-------------|------|
| `unit` | string | 无（内部 Key）| 指标单元的**唯一标识 Key**（英文），是采集系统内部的单元名称。如 `cpu`、`memory`、`interface`。在告警规则（thresholds）中用于定位具体指标。**这是 Zabbix 迁移中最重要的标识符**。 |
| `type` | string | 无（继承自模板）| 所属模板的类型码，与模板顶层的 `type` 字段相同，用于标识该指标单元属于哪类资源。 |
| `nameZh` | string | 指标信息列表"指标组"列 | 指标单元的中文名称，即界面上指标组列显示的名字。如"CPU"、"内存"、"接口统计"。 |
| `nameEn` | string | 无（英文名）| 指标单元的英文名称。 |
| `appname` | string | 无（内部分类）| 指标数据所属的采集应用名。绝大多数为 `"apm"`（Application Performance Management，应用性能管理，即通用采集器），少数网络设备类为 `"network"`（网络专项采集器）。该字段决定后端用哪个采集器采集数据。 |
| `collectTime` | number | 指标信息列表"采集间隔"列 | **采集周期（秒）**。常见值：`60`（1分钟）、`300`（5分钟）、`3600`（1小时）。网站界面显示为"1分钟"、"5分钟"等人性化文本。**Zabbix 对应 Item 的 `delay` 参数**。 |
| `scope` | number | 无（数据维度）| **数据维度/实例粒度**，决定采集结果是单值还是多实例。取值含义：`1` = **实例级**（每个实例单独一行，如每块网卡、每个磁盘分区各占一行，对应 `dataType=table`，即"表格型"多行数据）；`3` = **设备级**（整台设备汇总的单一值，如整台服务器的 CPU 总利用率，对应 `dataType=row`，即"行型"单值数据）。**Zabbix 中 scope=1 对应 Low-Level Discovery（LLD）自动发现场景，scope=3 对应普通 Item**。 |
| `defaultUsed` | boolean | 无（恒定）| 该指标单元是否默认启用。本平台所有 2553 个指标单元均为 `true`，属于恒定字段，可忽略。 |
| `defaultCp` | boolean | 无（概览看板）| 该指标单元是否**默认加入性能概览（CP = Control Panel / 概览面板）**。`true` = 该单元的数据会在资源概览页展示（关键指标）；`false` = 不默认展示，仅在详情页可查。规律：`scope=3`（设备级汇总）的单元通常 `defaultCp=true`（因为是关键概览数据）；`scope=1`（实例级）的单元通常 `defaultCp=false`（因为实例太多不适合概览）。 |
| `enableCollectTime` | boolean | 无（恒定）| 是否允许用户修改采集间隔。本平台所有单元均为 `true`，可忽略。 |
| `dataType` | string | 无（数据格式）| **指标数据的存储格式**，决定采集结果如何存入数据库和展示。取值含义见下方专项说明。 |
| `allField` | boolean | 无（字段选择）| `true` = 选择全部字段进行采集（该指标单元下的所有 fields 都会被采集）；`false` = 仅采集部分字段（由 `selectedFields` 指定）。当前数据中所有单元均为 `true`。 |
| `selectedFields` | null / array | 无 | 当 `allField=false` 时，指定需要采集的字段 Key 列表。当前数据中全部为 `null`（因为 `allField` 均为 `true`）。 |
| `operations` | null / array | 无 | 当前用户对该指标单元的可操作权限列表（同顶层 operationIds 的含义）。当前数据均为 `null`，可忽略。 |
| `enableDelete` | boolean | 无 | 界面上是否允许删除该指标单元。内置模板均为 `false`，自定义模板可能为 `true`。 |
| `mUrl` | null / string | 无 | 指标数据的监控详情跳转 URL（Monitor URL）。当前数据全部为 `null`，暂未使用。 |
| `aUrl` | null / string | 无 | 指标数据的告警详情跳转 URL（Alarm URL）。当前数据全部为 `null`，暂未使用。 |
| `typeAlias` | null / string | 无 | 类型别名，用于某些特殊场景下的类型名称覆盖。当前数据全部为 `null`，可忽略。 |
| `fields` | array | 指标信息列表"指标"列（展开后）| 该指标单元下的具体指标字段列表，见[第五节](#五unitlistfields-数组指标字段)。 |

### dataType 字段枚举值说明

| 值 | 含义 | 典型场景 |
|----|------|---------|
| `"table"` | **表格型**：多行多列结果，每个采集实例占一行（如多块磁盘、多个网卡接口）。对应 `scope=1` 的多实例场景。**Zabbix 需用 LLD 处理**。 |  网卡流量、磁盘 I/O、进程列表 |
| `"row"` | **行型**：单行结果，整体汇总值（如 CPU 总利用率、内存总使用量）。对应 `scope=3` 的单值场景。**Zabbix 直接创建 Item**。 | CPU 利用率、内存总量、系统运行时间 |
| `"record"` | **记录型**：类似 table，但每次采集形成一条记录（多用于变更类、事件类数据，如进程启停记录）。 | 进程变更、服务状态变化 |
| `"custom"` | **自定义型**：采集结果格式由特定脚本定义，不符合通用 table/row 格式（多见于用户自定义命令采集）。 | Linux 自定义命令采集 |
| `"predefine"` | **预定义型**：指标的展示和采集逻辑由系统预先定义的固定模式控制（如 Active Directory 服务状态这类有固定格式的数据）。 | AD 服务、预定义健康检查 |
| `""` (空字符串) | **通用/可用性型**：不需要存储结构化数据，仅判断可用性（如 Ping 测试、协议连通性），不形成存储记录。 | 可用性探测（AvailableData 单元） |

---

## 五、unitList.fields 数组（指标字段）

**fields** 是指标单元的最底层细节，对应网站界面中展开指标组后看到的**具体指标名称列表**，也是 Zabbix Item 的直接对标对象。

```json
{
  "id": 4,
  "type": "network",
  "unit": "cpu",
  "field": "cpuUtilization",
  "appname": "network",
  "nameZh": "CPU利用率",
  "nameEn": "CPU Usage",
  "explainZh": null,
  "explainEn": null,
  "fieldUnit": "%",
  "unitGroup": null,
  "valueType": 0,
  "conditionType": "EQ,GT,GE,LT,LE,CT,DC",
  "optionalValue": null,
  "range": "[0,100]",
  "enableThreshold": true,
  "alarmInst": 0,
  "fieldShow": 1,
  "levelType": 5,
  "fieldTags": null,
  "tags": null,
  "unitNameZh": null,
  "unitNameEn": null,
  "operations": null,
  "enableDelete": false,
  "mUrl": null,
  "defaultThreshold": null
}
```

| 字段名 | 类型 | 网站界面对应 | 说明 |
|--------|------|-------------|------|
| `id` | number | 无（内部 ID）| 字段定义的全局唯一 ID（自增整数）。在 `thresholds.conditions` 中作为 `id` 字段关联对应的阈值条件。 |
| `field` | string | 指标信息"指标"列（展开后的名称对应的内部 Key）| **指标字段的唯一标识 Key**（英文），是采集数据库中的字段名，也是告警规则中引用的字段标识。如 `cpuUtilization`、`memUtilization`、`rxPerSec`。**这是 Zabbix Item key 的直接对应值**。 |
| `type` | string | 无（继承）| 所属模板类型码，与父级 unitList 及模板顶层的 `type` 相同。 |
| `unit` | string | 无（继承）| 所属指标单元 Key，与父级 unitList 的 `unit` 相同。 |
| `appname` | string | 无（继承）| 所属采集应用，与父级 unitList 的 `appname` 相同。 |
| `nameZh` | string | 指标信息列表展开后"指标"列 | 指标字段的**中文名称**，即界面上用户看到的指标名称。如"CPU利用率"、"接口接收速率"。**Zabbix Item name 的参考值**。 |
| `nameEn` | string | 无（英文名）| 指标字段的英文名称，切换语言后展示。**Zabbix Item name（英文）的参考值**。 |
| `explainZh` | string / null | 无（详情说明）| 指标字段的**中文详细说明**，解释该指标的采集内容和含义，如"存储控制器的状态。采集值和转译值对应为:1=Other,2=Unknown,3=OK..."。部分字段为 `null`（网络设备类多为空）。**是理解指标含义的重要说明文字**。 |
| `explainEn` | string / null | 无（英文说明）| 指标字段的英文详细说明，与 `explainZh` 对应。 |
| `fieldUnit` | string / null | 无（单位显示）| **指标的数据单位**，如 `%`、`MB`、`bps`、`ms`、`℃`、`RPM`。如果字段有单位换算（见 unitGroup），则此处存储的是原始采集单位（最小单位）。`null` 表示无单位（如状态值、名称等）。**Zabbix Item units 的参考值**。 |
| `unitGroup` | object / null | 无（单位换算）| **单位换算组**定义，指定该指标可以在哪些单位之间自动换算（如 bps→Kbps→Mbps→Gbps）。`null` 表示不支持换算（固定单位）。详见[第六节](#六unitlistfieldsunitgroup-对象单位换算组)。**Zabbix 中可通过 multiplier 实现类似效果**。 |
| `valueType` | number | 无（数值类型）| **指标值的数据类型**。`0` = **数值型**（整数或浮点数，可进行大小比较，如利用率、温度、速率）；`1` = **字符串型**（文本值，如状态描述"OK"/"Critical"，名称，版本号）。**Zabbix Item type：0→Float/Integer，1→Character/Text**。 |
| `conditionType` | string | 无（阈值告警中的可选运算符）| **该字段支持的告警判断运算符列表**（逗号分隔）。这是在配置告警阈值时可以选择的运算符范围。完整枚举见[第十节枚举值对照表](#十枚举值完整对照表)。 |
| `optionalValue` | string / null | 无（枚举选项）| 当字段为字符串枚举类型时，列出所有可能的采集值及其显示名称（JSON 数组序列化后的字符串）。如风扇状态字段的值为 `[{"name":"正常","nameEn":"Normal"},{"name":"异常","nameEn":"Abnormal"}]`。`null` 表示值不固定（数值型或自由文本）。 |
| `range` | string | 无（值域范围）| **指标值的合法范围**，用于阈值设置时的边界校验。格式为 `[min,max]`，`#` 表示无限制。如 `[0,100]` = 0到100（百分比），`[0,#]` = 0到正无穷，`""` = 无范围约束。 |
| `enableThreshold` | boolean | 无（是否可配置告警）| `true` = 该字段**支持配置告警阈值**（可在阈值信息中添加该字段的触发规则）；`false` = 不支持（仅作为信息性展示指标，不触发告警）。全部 16025 个字段中有 9 个为 `false`（均为 DB2 数据库的配置类信息字段）。 |
| `alarmInst` | number | 无（告警实例标识）| **告警触发时使用哪个字段作为实例标识**，用于区分多实例（如多个接口、多个磁盘）发生的告警。取值含义：`-1` = **该字段本身是实例标识符**（即用于标记实例身份的名称字段，如接口名、磁盘名、进程名，触发告警时展示此字段值作为实例名，不直接触发告警）；`0` = **普通指标字段**，告警触发时使用其所在实例的默认标识（最常见情况，14380个字段）；`1/2/3/4` = **告警时引用第 N 个标识字段作为实例名称**（正整数，指定该行数据中以第几个 `alarmInst=-1` 字段的值作为告警实例名）。**实际含义**：对于 table 类型多实例采集，系统需要知道发生告警的是哪个实例（哪根网线、哪块盘），`alarmInst=-1` 的字段（如接口名称、磁盘挂载点）就是这个"名牌"，`alarmInst=1` 的字段就用第1个名牌字段的值来标记实例。 |
| `fieldShow` | number | 无（恒定）| 字段是否在界面展示，`1` = 展示。本平台所有字段均为 `1`，恒定值，可忽略。 |
| `levelType` | number | 无（恒定）| 告警级别类型，`5` = 支持全部 5 个告警级别（1=提示、2=一般、3=次要、4=重要、5=紧急）。本平台所有字段均为 `5`，恒定值，可忽略。 |
| `fieldTags` | null | 无 | 字段的 Tag 标签（用于分类筛选）。当前所有字段均为 `null`，暂未使用。 |
| `tags` | null | 无 | 同 `fieldTags`，当前均为 `null`。 |
| `unitNameZh` | null / string | 无 | 冗余的单元中文名，通常为 `null`（因为父级 unitList.nameZh 已有此信息）。 |
| `unitNameEn` | null / string | 无 | 冗余的单元英文名，通常为 `null`。 |
| `operations` | null | 无 | 权限操作列表，当前均为 `null`。 |
| `enableDelete` | boolean | 无 | 是否允许删除该字段，内置模板均为 `false`。 |
| `mUrl` | null | 无 | 监控跳转 URL，当前均为 `null`。 |
| `defaultThreshold` | null | 无 | 字段级别的默认阈值配置。当前所有字段均为 `null`（阈值统一在 `thresholds` 数组中定义）。 |

---

## 六、unitList.fields.unitGroup 对象（单位换算组）

当 `unitGroup` 不为 `null` 时，表示该指标支持在多个单位之间自动换算展示（前端根据数值大小自动选择合适的单位）。

```json
"unitGroup": {
  "name": "Network_TransmissionSpeed",
  "label": { "zh": "传输速率", "en": "Transmission Rate", "label": "传输速率" },
  "items": [
    { "name": "Network_TransmissionSpeed", "origin": "bps", "destination": "Kbps", "multiplier": 1000.0 },
    { "name": "Network_TransmissionSpeed", "origin": "Kbps", "destination": "Mbps", "multiplier": 1000.0 },
    { "name": "Network_TransmissionSpeed", "origin": "Mbps", "destination": "Gbps", "multiplier": 1000.0 }
  ],
  "units": ["bps", "Kbps", "Mbps", "Gbps"],
  "appname": "network"
}
```

| 字段名 | 说明 |
|--------|------|
| `name` | 换算组的唯一名称（英文 Key），如 `Capacity`、`Network_TransmissionSpeed`。 |
| `label` | 换算组的多语言显示名称（同 typeLabel 结构）。 |
| `items` | 换算规则列表，每条规则定义从 `origin` 单位到 `destination` 单位的换算系数 `multiplier`（即 1个destination = multiplier 个 origin）。 |
| `units` | 该换算组所有可用单位的有序列表（从小到大）。 |
| `appname` | 所属采集应用名（同 unitList.appname）。 |

### 平台内所有换算组类型

| 换算组 name | 中文含义 | 单位序列 | 换算系数 |
|------------|---------|---------|---------|
| `Capacity` | 容量（通用）| B → KB → MB → GB → TB | ×1024 |
| `CapacityB` | 容量（字节制）| B → KB → MB → GB | ×1024 |
| `CapacityiB` | 容量（iB制）| KiB → MiB → GiB → TiB | ×1024 |
| `DataRate` | 数据速率 | Bps → KBps → MBps → GBps | ×1024 |
| `TransmissionRate` | 传输速率 | bps → Kbps → Mbps → Gbps | ×1000 |
| `TransmissionRateB` | 传输速率（字节）| Bps → KBps → MBps | ×1024 |
| `ThroughputRate` | 吞吐量速率 | bps → Kbps → Mbps → Gbps | ×1000 |
| `Network_TransmissionSpeed` | 网络传输速率 | bps → Kbps → Mbps → Gbps | ×1000 |
| `Network_Time` | 网络时间 | ms → s | ×1000 |
| `Time` | 时间 | ms → s → min → h | 混合 |
| `Frequency` | 频率 | MHz → GHz | ×1000 |

> **Zabbix 注意**：采集到的原始数据单位为 `fieldUnit`（最小单位，如 bps、B、ms），前端展示时会自动按 `unitGroup` 换算。在 Zabbix 中，应以原始单位（`fieldUnit`）存储数据，在展示层配置单位换算（如使用 Zabbix 的 `units` 字段配合自定义乘数）。

---

## 七、thresholds 数组（告警阈值规则）

**thresholds** 是模板预置的告警阈值规则列表，对应网站界面"阈值信息"Tab 展示的内容。每个元素代表一条阈值规则（对应界面一行）。

```json
{
  "id": 10000000,
  "templateId": 209760028721155,
  "resId": null,
  "instanceUnit": null,
  "instanceId": null,
  "rule": null,
  "duration": [],
  "type": "Simple",
  "valueType": "Multistage",
  "conditions": [...],
  "desc": null,
  "thresholds": { "3": {...}, "4": {...} },
  "regionId": 1761206917732
}
```

| 字段名 | 类型 | 网站界面对应 | 说明 |
|--------|------|-------------|------|
| `id` | number | 无（内部 ID）| 阈值规则的唯一 ID（自增整数）。 |
| `templateId` | number | 无（关联）| 所属模板 ID，与顶层 `templateId` 相同，用于数据库关联查询。 |
| `type` | string | "阈值类型"列 | 告警规则类型。当前数据中全部为 `"Simple"`（简单阈值），界面显示"普通阈值"。（系统可能还支持复合阈值等其他类型，但当前模板数据中未出现）。 |
| `valueType` | string | 无（阈值结构类型）| 阈值配置方式。`"SingleStage"` = **单级阈值**：只有一个触发级别（通常用于严重性唯一的事件，如"连接不可达"只有紧急级别）；`"Multistage"` = **多级阈值**：可配置多个不同严重级别的阈值（如 CPU≥70%→次要，CPU≥90%→重要）。决定了 `conditions[].threshold` 数组中有几个 `enable=true` 的条目。 |
| `conditions` | array | "触发条件"列 | 该阈值规则的具体触发条件列表，见[第八节](#八thresholdsconditions-数组阈值触发条件)。一条规则通常只有一个 condition，复合条件时可能有多个。 |
| `thresholds` | object | 无（生效阈值摘要）| **已启用阈值的汇总**，Key 为级别数字（"3"、"4"、"5"），Value 为该级别生效的阈值值和检测次数。这是 `conditions[].threshold` 中 `enable=true` 条目的摘要，方便快速查阅。格式：`{"级别数字": {"level": 级别, "value": {"conditionId": "阈值"}, "trigger": 检测次数}}`。 |
| `desc` | null / string | 无（规则描述）| 阈值规则的描述说明，当前全部为 `null`。 |
| `duration` | array | "适用时间"列 | 该阈值规则的生效时间段列表（时间窗口配置）。当前所有预置规则均为空数组 `[]`，对应界面显示"全部时间"（即全天候生效）。 |
| `resId` | null | 无 | 指定该阈值仅适用于某个具体资源实例的 ID。`null` = 适用于所有使用此模板的资源（模板级规则）。当用户为某台具体服务器定制阈值时此字段才有值。 |
| `instanceUnit` | null | 无 | 指定实例所属的指标单元 Key，与 `resId` 配合使用，当前全部为 `null`。 |
| `instanceId` | null | 无 | 指定具体实例的 ID（如特定网卡、特定磁盘分区），当前全部为 `null`（模板级阈值）。 |
| `rule` | null | 无 | 复杂规则表达式，当前全部为 `null`，可忽略。 |
| `regionId` | number | 无（区域）| 所属区域 ID，与模板顶层 `regionId` 相同。 |

---

## 八、thresholds.conditions 数组（阈值触发条件）

每个 condition 定义了一个具体的触发条件（针对某个指标字段的判断规则）。

```json
{
  "id": 1,
  "type": "network",
  "unit": "cpu",
  "field": "cpuUtilization",
  "valueType": 0,
  "operator": "GE",
  "threshold": [...],
  "value": "[[threshold]]",
  "symbol": "%",
  "range": "[0,100]"
}
```

| 字段名 | 类型 | 网站界面对应 | 说明 |
|--------|------|-------------|------|
| `id` | number | 无（内部 ID）| 条件的唯一 ID，与 `unitList.fields[].id` 关联——**此 id 就是对应指标字段的 id**，通过这个值可以从 unitList.fields 中找到对应的字段定义。同时也作为 `thresholds.thresholds` 摘要中 `value` 对象的 Key。 |
| `type` | string | 无（继承）| 所属模板类型码。 |
| `unit` | string | "触发条件"列（斜杠前）| 触发条件所属的指标单元 Key，与 unitList.fields[].unit 对应。界面中"触发条件"列显示为"单元名/字段名"格式，如"可用性/协议连接"，此为斜杠前的部分（对应单元的 nameZh）。 |
| `field` | string | "触发条件"列（斜杠后字段名的内部 Key）| 触发条件判断的指标字段 Key，与 unitList.fields[].field 对应。 |
| `valueType` | number | 无（数值类型）| 该字段的值类型，同 unitList.fields[].valueType。`0` = 数值，`1` = 字符串。 |
| `operator` | string | "触发条件"列（运算符，如"大于等于"、"等于"）| 触发条件的比较运算符，详见[第十节枚举值对照表](#十枚举值完整对照表)。 |
| `threshold` | array | "告警级别"和"阈值"（展开后）| 各告警级别下的阈值定义列表，见[第九节](#九thresholdsconditionsthreshold-数组各级别阈值定义)。 |
| `value` | string | 无（占位符）| 固定值为 `"[[threshold]]"`，是系统内部的占位符，表示"阈值值在 threshold 数组中定义"，非实际阈值数据，可忽略。 |
| `symbol` | string | "触发条件"列（单位）| 阈值的单位符号（如 `%`、`ms`、`℃`），用于界面展示阈值时附加单位。对应 fields[].fieldUnit。 |
| `range` | string | 无（值域）| 该字段的合法值域范围，同 fields[].range。 |

---

## 九、thresholds.conditions.threshold 数组（各级别阈值定义）

每个条目定义了**某一告警级别**下的触发阈值值和检测次数。一个 condition 通常有 5 个条目，分别对应 5 个告警级别（提示/一般/次要/重要/紧急）。

```json
{
  "level": 3,
  "value": "70",
  "enable": true,
  "trigger": 3
}
```

| 字段名 | 类型 | 网站界面对应 | 说明 |
|--------|------|-------------|------|
| `level` | number | "告警级别"列 | **告警级别**（严重程度）。数字对应含义：`1` = **提示**（最低级，蓝色）；`2` = **一般**（绿色）；`3` = **次要**（黄色）；`4` = **重要**（橙色）；`5` = **紧急**（红色，最高级）。**Zabbix 对应：1→Information，2→Warning，3→Average，4→High，5→Disaster**。 |
| `value` | string | "触发条件"列（阈值具体数值）| **该级别的阈值触发值**，字符串格式（即使是数字也用字符串存储）。对于数值型字段（`valueType=0`）存数字字符串如 `"70"`、`"90"`；对于字符串型字段（`valueType=1`）存匹配文本如 `"无法连接"`、`"异常\|不支持"`（`\|` 是多值 OR 分隔符）。 |
| `enable` | boolean | 无（是否启用）| `true` = 该级别的阈值已**启用**（会实际触发告警）；`false` = 未启用（预置但未开启，不触发）。**重要**：一条 condition 的 5 个级别中，只有 `enable=true` 的级别才会实际生效。`SingleStage` 类型通常只有最高级别 `enable=true`；`Multistage` 类型会有多个级别 `enable=true`（如 level=3 和 level=4 同时生效代表两段阈值）。 |
| `trigger` | number | "检测次数"列 | **持续触发检测次数**，表示连续满足条件多少次才触发告警（防止偶发抖动）。`1` = **即时触发**（条件成立立即告警）；`2` = **触发2次**（连续2次采集都满足条件才告警）；`3` = **触发3次**（连续3次才告警，更稳定）。结合 `collectTime` 可算出实际触发延迟：如 collectTime=300s、trigger=3，则需 900 秒（15分钟）持续满足条件才告警。**Zabbix 对应 trigger expression 中的 `count` 函数或 `nodata` 时间窗口**。 |

---

## 十、枚举值完整对照表

### 告警级别（level）

| 数值 | 含义（中）| 含义（英）| 网站界面颜色 | Zabbix 对应级别 |
|------|----------|----------|------------|----------------|
| 1 | 提示 | Information | 蓝色 | Information |
| 2 | 一般 | Warning | 绿色 | Warning |
| 3 | 次要 | Minor | 黄色 | Average |
| 4 | 重要 | Major | 橙色 | High |
| 5 | 紧急 | Critical | 红色 | Disaster |

### 指标字段值类型（field.valueType）

| 数值 | 含义 | 说明 | Zabbix Item 类型 |
|------|------|------|-----------------|
| 0 | 数值型 | 整数或浮点数，支持 GT/GE/LT/LE 大小比较 | Numeric (float) / Numeric (unsigned) |
| 1 | 字符串型 | 文本值，支持 IC/EC/EQ/NEQ/RULE 字符串匹配 | Character / Text |

### 告警触发运算符（operator / conditionType）

| 缩写 | 英文全称 | 中文含义 | 适用值类型 | Zabbix 表达式对应 |
|------|---------|---------|----------|-----------------|
| `GT` | Greater Than | 大于 | 数值型 | `last() > {$THRESHOLD}` |
| `GE` | Greater than or Equal | 大于等于 | 数值型 | `last() >= {$THRESHOLD}` |
| `LT` | Less Than | 小于 | 数值型 | `last() < {$THRESHOLD}` |
| `LE` | Less than or Equal | 小于等于 | 数值型 | `last() <= {$THRESHOLD}` |
| `EQ` | Equal | 等于 | 数值型 & 字符串型 | `last() = {$THRESHOLD}` |
| `NEQ` | Not EQual | 不等于 | 字符串型 | `last() <> {$THRESHOLD}` |
| `IC` | Include Contains | 包含（模糊匹配）| 字符串型 | `find(/host/key,,"like","{$VAL}")=1` |
| `EC` | Exclude Contains | 不包含 | 字符串型 | `find(/host/key,,"like","{$VAL}")=0` |
| `RULE` | 正则/枚举规则匹配 | 按规则匹配（支持 `\|` 分隔多值 OR）| 字符串型 | `find(/host/key,,"regexp","val1\|val2")=1` |
| `CHG` | CHanGe | 值发生变化 | 数值型 & 字符串型 | `change(/host/key)<>0` |
| `CT` | Continuous Trigger | 持续超阈值 | 数值型 | 结合 `trigger` 次数实现 |
| `DC` | Decrease / Drop | 值下降（持续低于阈值）| 数值型 | 结合 `trigger` 次数实现 |

### 指标单元数据类型（unitList.dataType）

| 值 | 含义 | 存储特征 | Zabbix 处理方式 |
|----|------|---------|----------------|
| `table` | 表格型（多实例多行）| 每个实例一行，多字段多列 | LLD + Dependent Items |
| `row` | 行型（单实例单行）| 整台设备汇总为一行 | 普通 Item |
| `record` | 记录型（变更事件）| 每次变更生成一条记录 | Log Item |
| `custom` | 自定义型 | 格式由脚本定义 | External Check |
| `predefine` | 预定义型 | 固定格式预置采集 | 参考具体字段定义 |
| `""` (空)| 通用型（可用性）| 无结构化数据 | Simple Check / ICMP |

### 指标单元采集范围（unitList.scope）

| 值 | 含义 | 说明 | 对应 dataType |
|----|------|------|--------------|
| 1 | 实例级（多实例）| 每个子实例（接口/磁盘/进程）独立一行 | 通常为 `table` 或 `record` |
| 3 | 设备级（汇总）| 整台设备的汇总单值 | 通常为 `row` 或 `""`（空）|

### 阈值结构类型（thresholds.valueType）

| 值 | 含义 | 特征 |
|----|------|------|
| `SingleStage` | 单级阈值 | 只有一个告警级别启用（通常为级别 5 紧急）。用于非连续值的状态判断，如"连接不可达"只有一种严重程度 |
| `Multistage` | 多级阈值 | 多个告警级别同时启用（如 CPU 70% 次要 + 90% 重要）。用于连续数值的渐进告警 |

### 阈值检测次数（trigger）

| 值 | 含义 | 说明 | 实际延迟计算 |
|----|------|------|------------|
| 1 | 即时触发 | 条件成立立即告警，无延迟 | 0 次延迟 |
| 2 | 连续 2 次 | 需连续 2 个采集周期满足才告警 | 延迟 = collectTime × (2-1) |
| 3 | 连续 3 次 | 需连续 3 个采集周期满足才告警 | 延迟 = collectTime × (3-1) |

---

## 十一、字段与网站界面的对应关系

### 模板列表页（template-list.html）

| 界面列名 | 对应 API 字段 | 备注 |
|---------|--------------|------|
| 名称 | `name` | 模板显示名称 |
| 类型 | `typeLabel.label`（即 `typeLabel.zh`）| 显示类型的中文名 |
| 自定义 | `custom`（true→"是"，false→"否"）| |
| 描述 | `describe` | 为空时显示空白 |

### 模板详情页 - 基本信息

| 界面标签 | 对应 API 字段 | 备注 |
|---------|--------------|------|
| 模板名称 | `name` | |
| 模板描述 | `describe` | |
| 模板类型 | `typeLabel.zh` 或 `typeLabel.label` | |
| 所属机构/分组 | `resGroup[].label`（带前缀"所属机构："）| 内置模板无分组，界面不显示此行 |

### 模板详情页 - 指标信息 Tab

| 界面列名 | 对应 API 字段路径 | 备注 |
|---------|-----------------|------|
| 指标组 | `unitList[].nameZh` | 每行代表一个指标单元 |
| 采集间隔 | `unitList[].collectTime`（秒→分钟转换）| 60s→"1分钟"，300s→"5分钟" |
| 指标（展开后）| `unitList[].fields[].nameZh` | 点击展开行后显示字段名列表 |
| Tag（展开后）| `unitList[].fields[].fieldTags` | 当前均为空 |

### 模板详情页 - 阈值信息 Tab

| 界面列名 | 对应 API 字段路径 | 备注 |
|---------|-----------------|------|
| 阈值类型 | `thresholds[].type`（"Simple"→"普通阈值"）| |
| 适用时间 | `thresholds[].duration`（空数组→"全部时间"）| |
| 告警级别 | `thresholds[].conditions[].threshold[].level`（取 enable=true 的最高级）| `5`→"紧急"，`4`→"重要"，`3`→"次要" |
| 检测次数 | `thresholds[].conditions[].threshold[].trigger`（取 enable=true 对应项）| |
| 触发条件 | `{unitList对应单元nameZh}/{unitList对应字段nameZh} + operator + value` | 如"可用性/协议连接 等于 无法连接" |

> **重要提示**：界面"触发条件"列中"/"前的名称来自 `unitList[单元 unit=condition.unit].nameZh`，"/"后的名称来自 `unitList[].fields[field=condition.field].nameZh`，运算符 `operator` 按枚举值转为中文显示，阈值来自 `threshold[enable=true].value`。

---

## 十二、可忽略/恒定字段说明

以下字段在当前 236 个模板的数据中**只有唯一值或全部为 null**，在分析和迁移时可以安全忽略：

| 字段路径 | 恒定值 | 说明 |
|---------|-------|------|
| `scene` | `"MONITOR"` | 固定为监控场景 |
| `unitList[].defaultUsed` | `true` | 全部默认启用 |
| `unitList[].enableCollectTime` | `true` | 全部允许修改采集间隔 |
| `unitList[].allField` | `true` | 全部采集所有字段 |
| `unitList[].selectedFields` | `null` | 无选择性采集 |
| `unitList[].mUrl` | `null` | 未使用 |
| `unitList[].aUrl` | `null` | 未使用 |
| `unitList[].typeAlias` | `null` | 未使用 |
| `unitList[].operations` | `null` | 无操作权限数据 |
| `fields[].fieldShow` | `1` | 全部显示 |
| `fields[].levelType` | `5` | 全部支持5级告警 |
| `fields[].fieldTags` | `null` | 无 Tag 标注 |
| `fields[].tags` | `null` | 无 Tag 标注 |
| `fields[].unitNameZh` | `null` | 冗余字段 |
| `fields[].unitNameEn` | `null` | 冗余字段 |
| `fields[].operations` | `null` | 无操作权限数据 |
| `fields[].mUrl` | `null` | 未使用 |
| `fields[].defaultThreshold` | `null` | 阈值统一在 thresholds 中定义 |
| `thresholds[].resId` | `null` | 模板级规则，非实例级 |
| `thresholds[].instanceUnit` | `null` | 同上 |
| `thresholds[].instanceId` | `null` | 同上 |
| `thresholds[].rule` | `null` | 未使用复杂规则 |
| `thresholds[].duration` | `[]`（空数组）| 全部时间生效 |
| `thresholds[].desc` | `null` | 无规则描述 |
| `thresholds[].type` | `"Simple"` | 全部为普通阈值 |
| `thresholds[].conditions[].value` | `"[[threshold]]"` | 固定占位符 |
| `nameEn`（顶层）| 多数与 `name` 相同 | 英文名冗余 |
| `uuid`（顶层）| 与 `templateId` 相同 | 重复字段 |

---

## 附录：Zabbix 迁移字段映射速查

| 本平台字段 | Zabbix 对应概念 | 说明 |
|-----------|----------------|------|
| 模板 `name` | Template name | 模板名称 |
| 模板 `type` (key) | Template group / Tag | 可作为 Zabbix 模板分组依据 |
| `unitList[].nameZh` | Application / Item group | 指标组名称（Zabbix 7.0 已废弃 Application，可用 Tag 替代）|
| `unitList[].unit` | 自定义 Tag key | 指标单元唯一标识，建议作为 Item tag |
| `unitList[].collectTime` | Item → Update interval | 采集周期（秒） |
| `fields[].field` | Item key | 指标字段唯一标识（建议作为 item key 的一部分）|
| `fields[].nameZh` | Item name | 指标名称 |
| `fields[].fieldUnit` | Item units | 数据单位 |
| `fields[].valueType=0` | Item type: Numeric float/unsigned | 数值型 |
| `fields[].valueType=1` | Item type: Character/Text | 字符串型 |
| `unitList[].scope=1` + `dataType=table` | LLD (Low-Level Discovery) | 多实例自动发现 |
| `unitList[].scope=3` + `dataType=row` | Regular Item | 单值指标 |
| `thresholds[].conditions[].threshold[].level` | Trigger severity | 告警级别（1→Info, 5→Disaster）|
| `threshold[].value` | Trigger expression threshold value | 阈值比较值 |
| `threshold[].trigger` | Trigger expression count/time window | 检测次数 |
| `threshold[].enable=false` | Trigger disabled | 未启用的告警级别 |
| `operator=GE` | `last()>=` | 大于等于运算符 |
| `operator=EQ` | `last()=` | 等于运算符 |
| `operator=CHG` | `change()<>0` | 值变化触发 |
| `operator=RULE` | `find()=1` with regexp | 正则匹配 |