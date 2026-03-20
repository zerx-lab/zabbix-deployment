#!/usr/bin/env python3
"""
convert_snmp_templates.py
将华三监控平台中支持 SNMP 协议的模板转换为 Zabbix 7.0 YAML 格式，
并通过 Zabbix API 导入。

支持的华三模板类型（SNMP 可采集）：
  - network  → 网络设备（通用 SNMP：IF-MIB / SNMPv2-MIB / HOST-RESOURCES-MIB）
  - linux    → Linux（Linux by SNMP：UCD-SNMP-MIB / IF-MIB）
  - winsvr   → Windows（Windows by SNMP：HOST-RESOURCES-MIB / IF-MIB）
  - brocade  → Brocade FC 存储网络（SW-MIB）
  - ping/pingcmd → ICMP Ping 探测（Zabbix Simple Check）
  - tcpport  → TCP 端口探测（Zabbix Simple Check）

用法：
  # 仅转换，不导入（输出 YAML 到 output/zabbix-templates/）
  python3 scripts/convert_snmp_templates.py

  # 转换并通过 API 导入 Zabbix
  python3 scripts/convert_snmp_templates.py --import

  # 指定 Zabbix 地址 / 凭据
  python3 scripts/convert_snmp_templates.py --import \
      --url http://localhost:8080 \
      --user Admin --password zabbix

  # 只转换特定类型
  python3 scripts/convert_snmp_templates.py --types network,linux

  # 转换后列出生成文件
  python3 scripts/convert_snmp_templates.py --list
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import textwrap
import urllib.request
import uuid as _uuid_mod
from datetime import datetime
from pathlib import Path

# ── 目录配置 ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
H3C_DETAILS_DIR = ROOT / "output" / "monitor-templates" / "details"
OUTPUT_DIR = ROOT / "output" / "zabbix-templates"

# ── Zabbix API 默认配置 ────────────────────────────────────────────────────────
DEFAULT_API_URL = "http://localhost:8080"
DEFAULT_USER = "Admin"
DEFAULT_PASSWORD = "zabbix"

# ── 支持转换的华三类型集合 ────────────────────────────────────────────────────
SNMP_SUPPORTED_TYPES: set[str] = {
    "network",  # 通用网络设备 SNMP
    "linux",  # Linux SNMP
    "kylin",  # 中标麒麟（同 Linux SNMP）
    "kylinos",  # 银河麒麟（同 Linux SNMP）
    "uos",  # UOS（同 Linux SNMP）
    "rocky",  # 凝思磐石（同 Linux SNMP）
    "suse",  # Suse（同 Linux SNMP）
    "winsvr",  # Windows SNMP
    "brocade",  # Brocade FC by SNMP
    "ping",  # 远程 Ping 探测（ICMP Simple Check）
    "pingcmd",  # 本地 Ping 探测（ICMP Simple Check）
    "tcpport",  # TCP 端口探测（Simple Check）
}

# ── 华三类型 → Zabbix 模板组 ──────────────────────────────────────────────────
H3C_TYPE_TO_GROUP: dict[str, str] = {
    "network": "Templates/Network devices",
    "linux": "Templates/Operating systems",
    "kylin": "Templates/Operating systems",
    "kylinos": "Templates/Operating systems",
    "uos": "Templates/Operating systems",
    "rocky": "Templates/Operating systems",
    "suse": "Templates/Operating systems",
    "winsvr": "Templates/Operating systems",
    "brocade": "Templates/Network devices",
    "ping": "Templates/Network devices",
    "pingcmd": "Templates/Network devices",
    "tcpport": "Templates/Network devices",
}

# ── 华三告警级别 → Zabbix Trigger severity ────────────────────────────────────
SEVERITY_MAP: dict[int, str] = {
    1: "INFO",
    2: "WARNING",
    3: "AVERAGE",
    4: "HIGH",
    5: "DISASTER",
}

# ── 华三运算符 → Zabbix 表达式运算符 ─────────────────────────────────────────
# ── 告警运算符映射 ────────────────────────────────────────────────────────────
# 用于 last()/min()/max() 等函数的比较运算符（直接拼接在表达式末尾）
OPERATOR_MAP: dict[str, str] = {
    "GT": ">",
    "GE": ">=",
    "LT": "<",
    "LE": "<=",
    "EQ": "=",
    "NEQ": "<>",
}

# count() 第三参数只支持英文缩写，不支持符号（>= 等）
# 参考：https://www.zabbix.com/documentation/7.0/en/manual/appendix/functions/history
COUNT_OPERATOR_MAP: dict[str, str] = {
    "GT": "gt",
    "GE": "ge",
    "LT": "lt",
    "LE": "le",
    "EQ": "eq",
    "NEQ": "ne",
    "CT": "ge",  # 持续超阈值 → ge
    "DC": "le",  # 持续低于阈值 → le
}

# ────────────────────────────────────────────────────────────────────────────
# SNMP OID 映射表
# key  格式: "{h3c_type}.{unit_key}.{field_key}"
# value:
#   oid        - SNMP OID 字符串（供 snmp_oid 使用）
#   key        - Zabbix item key
#   value_type - FLOAT / UNSIGNED / CHAR / TEXT / LOG
#   units      - Zabbix units 字符串
#   delay      - 采集间隔
#   description - 描述
#   preprocessing - list[dict]，可选，Zabbix item preprocessing 配置
#   is_prototype  - True = LLD item prototype
#   lld_rule      - 所属 LLD 规则 key（仅 is_prototype=True 时有效）
# ────────────────────────────────────────────────────────────────────────────

# ── 公共 SNMP 基础 Items（所有 SNMP 类型共用） ──────────────────────────────
_COMMON_SNMP_ITEMS: list[dict] = [
    {
        "name": "ICMP ping",
        "type": "SIMPLE",
        "key": "icmpping",
        "value_type": "UNSIGNED",
        "units": "",
        "delay": "1m",
        "description": "设备 ICMP ping 可达性。0=不可达，1=可达。",
        "tags": [
            {"tag": "component", "value": "health"},
            {"tag": "component", "value": "network"},
            {"tag": "source", "value": "h3c-converted"},
        ],
        "valuemap": "Service state",
        "triggers": [
            {
                "name": "{TEMPLATE_NAME}: 设备 ICMP ping 不可达",
                "expression": "max(/{TEMPLATE_KEY}/icmpping,#3)=0",
                "priority": "HIGH",
                "description": "连续 3 次 ICMP ping 超时，请检查设备连通性。",
                "tags": [{"tag": "scope", "value": "availability"}],
            }
        ],
    },
    {
        "name": "ICMP ping loss",
        "type": "SIMPLE",
        "key": "icmppingloss",
        "value_type": "FLOAT",
        "units": "%",
        "delay": "1m",
        "description": "ICMP ping 丢包率。",
        "tags": [
            {"tag": "component", "value": "health"},
            {"tag": "component", "value": "network"},
            {"tag": "source", "value": "h3c-converted"},
        ],
        "triggers": [
            {
                "name": "{TEMPLATE_NAME}: ICMP ping 丢包率过高",
                "expression": (
                    "min(/{TEMPLATE_KEY}/icmppingloss,5m)>{$ICMP_LOSS_WARN}"
                    " and min(/{TEMPLATE_KEY}/icmppingloss,5m)<100"
                ),
                "priority": "WARNING",
                "opdata": "Loss: {ITEM.LASTVALUE1}",
                "description": "检测到 ICMP 丢包。",
                "dependencies": [
                    {
                        "name": "{TEMPLATE_NAME}: 设备 ICMP ping 不可达",
                        "expression": "max(/{TEMPLATE_KEY}/icmpping,#3)=0",
                    }
                ],
                "tags": [
                    {"tag": "scope", "value": "availability"},
                    {"tag": "scope", "value": "performance"},
                ],
            }
        ],
    },
    {
        "name": "ICMP response time",
        "type": "SIMPLE",
        "key": "icmppingsec",
        "value_type": "FLOAT",
        "units": "s",
        "delay": "1m",
        "description": "ICMP ping 响应时间（秒）。",
        "tags": [
            {"tag": "component", "value": "health"},
            {"tag": "component", "value": "network"},
            {"tag": "source", "value": "h3c-converted"},
        ],
        "triggers": [
            {
                "name": "{TEMPLATE_NAME}: ICMP ping 响应时间过高",
                "expression": (
                    "avg(/{TEMPLATE_KEY}/icmppingsec,5m)>{$ICMP_RESPONSE_TIME_WARN}"
                ),
                "priority": "WARNING",
                "opdata": "Value: {ITEM.LASTVALUE1}",
                "description": "平均 ICMP 响应时间过高。",
                "dependencies": [
                    {
                        "name": "{TEMPLATE_NAME}: ICMP ping 丢包率过高",
                        "expression": (
                            "min(/{TEMPLATE_KEY}/icmppingloss,5m)>{$ICMP_LOSS_WARN}"
                            " and min(/{TEMPLATE_KEY}/icmppingloss,5m)<100"
                        ),
                    },
                    {
                        "name": "{TEMPLATE_NAME}: 设备 ICMP ping 不可达",
                        "expression": "max(/{TEMPLATE_KEY}/icmpping,#3)=0",
                    },
                ],
                "tags": [
                    {"tag": "scope", "value": "availability"},
                    {"tag": "scope", "value": "performance"},
                ],
            }
        ],
    },
    {
        "name": "SNMP traps (fallback)",
        "type": "SNMP_TRAP",
        "key": "snmptrap.fallback",
        "delay": "0",
        "value_type": "LOG",
        "trends": "0",
        "description": "用于收集所有未被其他 snmptrap item 匹配的 SNMP trap。",
        "logtimefmt": "hh:mm:sszyyyy/MM/dd",
        "tags": [
            {"tag": "component", "value": "network"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "System name",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.2.1.1.5.0]",
        "key": "system.name",
        "delay": "15m",
        "value_type": "CHAR",
        "trends": "0",
        "description": "MIB: SNMPv2-MIB\n系统管理员分配的节点名称（sysName）。",
        "inventory_link": "NAME",
        "preprocessing": [
            {"type": "DISCARD_UNCHANGED_HEARTBEAT", "parameters": ["12h"]}
        ],
        "tags": [
            {"tag": "component", "value": "system"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "System description",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.2.1.1.1.0]",
        "key": "system.descr[sysDescr.0]",
        "delay": "15m",
        "value_type": "CHAR",
        "trends": "0",
        "description": "MIB: SNMPv2-MIB\n实体文本描述，包含硬件型号、OS 版本及网络软件版本（sysDescr）。",
        "inventory_link": "OS",
        "preprocessing": [
            {"type": "DISCARD_UNCHANGED_HEARTBEAT", "parameters": ["12h"]}
        ],
        "tags": [
            {"tag": "component", "value": "system"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "System contact details",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.2.1.1.4.0]",
        "key": "system.contact[sysContact.0]",
        "delay": "15m",
        "value_type": "CHAR",
        "trends": "0",
        "description": "MIB: SNMPv2-MIB\n该节点联系人及联系方式（sysContact）。",
        "inventory_link": "CONTACT",
        "preprocessing": [
            {"type": "DISCARD_UNCHANGED_HEARTBEAT", "parameters": ["12h"]}
        ],
        "tags": [
            {"tag": "component", "value": "system"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "System location",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.2.1.1.6.0]",
        "key": "system.location[sysLocation.0]",
        "delay": "15m",
        "value_type": "CHAR",
        "trends": "0",
        "description": "MIB: SNMPv2-MIB\n节点物理位置（sysLocation）。",
        "inventory_link": "LOCATION",
        "preprocessing": [
            {"type": "DISCARD_UNCHANGED_HEARTBEAT", "parameters": ["12h"]}
        ],
        "tags": [
            {"tag": "component", "value": "system"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "Uptime (network)",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.2.1.1.3.0]",
        "key": "system.net.uptime[sysUpTime.0]",
        "delay": "30s",
        "value_type": "UNSIGNED",
        "units": "uptime",
        "trends": "0",
        "description": "MIB: SNMPv2-MIB\n网管部分自上次初始化后的运行时间（sysUpTime，单位：百分之一秒）。",
        "preprocessing": [
            {
                "type": "MULTIPLIER",
                "parameters": ["0.01"],
            }
        ],
        "tags": [
            {"tag": "component", "value": "system"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "Uptime (hardware)",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.2.1.25.1.1.0]",
        "key": "system.hw.uptime[hrSystemUptime.0]",
        "delay": "30s",
        "value_type": "UNSIGNED",
        "units": "uptime",
        "trends": "0",
        "description": "MIB: HOST-RESOURCES-MIB\n主机自上次初始化后的运行时间（hrSystemUptime，单位：百分之一秒）。",
        "preprocessing": [
            {
                "type": "CHECK_NOT_SUPPORTED",
                "parameters": ["-1"],
                "error_handler": "CUSTOM_VALUE",
                "error_handler_params": "0",
            },
            {
                "type": "MULTIPLIER",
                "parameters": ["0.01"],
            },
        ],
        "tags": [
            {"tag": "component", "value": "system"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "SNMP availability",
        "type": "INTERNAL",
        "key": "zabbix[host,snmp,available]",
        "delay": "1m",
        "value_type": "UNSIGNED",
        "description": "Zabbix 内部 item，记录 SNMP 接口可用状态。",
        "tags": [
            {"tag": "component", "value": "health"},
            {"tag": "source", "value": "h3c-converted"},
        ],
        "valuemap": "zabbix.host.available",
        "triggers": [
            {
                "name": "{TEMPLATE_NAME}: SNMP agent 不可达",
                "expression": (
                    "max(/{TEMPLATE_KEY}/zabbix[host,snmp,available],{$SNMP.TIMEOUT})=0"
                ),
                "priority": "WARNING",
                "description": "在 {$SNMP.TIMEOUT} 时间内 SNMP agent 没有响应。",
                "tags": [{"tag": "scope", "value": "availability"}],
            }
        ],
    },
]

# ── 网络设备专用：接口 LLD ──────────────────────────────────────────────────
_NETWORK_IF_LLD: dict = {
    "name": "Network interface discovery",
    "type": "SNMP_AGENT",
    "snmp_oid": (
        "walk[1.3.6.1.2.1.2.2]"  # IF-MIB::ifTable
    ),
    "key": "net.if.discovery",
    "delay": "1h",
    "description": "MIB: IF-MIB\n发现所有网络接口（ifTable）。",
    "filter": {
        "evaltype": "AND_OR",
        "conditions": [
            {
                "macro": "{#IFADMINSTATUS}",
                "value": "1",
                "operator": "MATCHES_REGEX",
                "formulaid": "A",
            }
        ],
    },
    "lld_macro_paths": [
        {"lld_macro": "{#IFINDEX}", "path": "$.index"},
        {"lld_macro": "{#IFDESCR}", "path": "$.name"},
        {"lld_macro": "{#IFNAME}", "path": "$.name"},
        {"lld_macro": "{#IFALIAS}", "path": "$.alias"},
        {"lld_macro": "{#IFTYPE}", "path": "$.type"},
        {"lld_macro": "{#IFADMINSTATUS}", "path": "$.admin_status"},
        {"lld_macro": "{#SNMPINDEX}", "path": "$.index"},
    ],
    "item_prototypes": [
        {
            "name": "Interface {#IFDESCR}: 入流量",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.2.1.31.1.1.1.6.{#SNMPINDEX}]",  # ifHCInOctets
            "key": "net.if.in[ifHCInOctets.{#SNMPINDEX}]",
            "delay": "3m",
            "value_type": "UNSIGNED",
            "units": "bps",
            "description": "MIB: IF-MIB\nifHCInOctets: 接口入方向字节数（64 位计数器）。",
            "preprocessing": [
                {
                    "type": "CHANGE_PER_SECOND",
                    "parameters": [],
                },
                {
                    "type": "MULTIPLIER",
                    "parameters": ["8"],
                },
            ],
            "tags": [
                {"tag": "component", "value": "network"},
                {"tag": "interface", "value": "{#IFDESCR}"},
                {"tag": "source", "value": "h3c-converted"},
            ],
        },
        {
            "name": "Interface {#IFDESCR}: 出流量",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.2.1.31.1.1.1.10.{#SNMPINDEX}]",  # ifHCOutOctets
            "key": "net.if.out[ifHCOutOctets.{#SNMPINDEX}]",
            "delay": "3m",
            "value_type": "UNSIGNED",
            "units": "bps",
            "description": "MIB: IF-MIB\nifHCOutOctets: 接口出方向字节数（64 位计数器）。",
            "preprocessing": [
                {"type": "CHANGE_PER_SECOND", "parameters": []},
                {"type": "MULTIPLIER", "parameters": ["8"]},
            ],
            "tags": [
                {"tag": "component", "value": "network"},
                {"tag": "interface", "value": "{#IFDESCR}"},
                {"tag": "source", "value": "h3c-converted"},
            ],
        },
        {
            "name": "Interface {#IFDESCR}: 入错误",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.2.1.2.2.1.14.{#SNMPINDEX}]",  # ifInErrors
            "key": "net.if.in.errors[ifInErrors.{#SNMPINDEX}]",
            "delay": "3m",
            "value_type": "UNSIGNED",
            "description": "MIB: IF-MIB\nifInErrors: 接口入方向错误包数。",
            "preprocessing": [{"type": "CHANGE_PER_SECOND", "parameters": []}],
            "tags": [
                {"tag": "component", "value": "network"},
                {"tag": "interface", "value": "{#IFDESCR}"},
                {"tag": "source", "value": "h3c-converted"},
            ],
        },
        {
            "name": "Interface {#IFDESCR}: 出错误",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.2.1.2.2.1.20.{#SNMPINDEX}]",  # ifOutErrors
            "key": "net.if.out.errors[ifOutErrors.{#SNMPINDEX}]",
            "delay": "3m",
            "value_type": "UNSIGNED",
            "description": "MIB: IF-MIB\nifOutErrors: 接口出方向错误包数。",
            "preprocessing": [{"type": "CHANGE_PER_SECOND", "parameters": []}],
            "tags": [
                {"tag": "component", "value": "network"},
                {"tag": "interface", "value": "{#IFDESCR}"},
                {"tag": "source", "value": "h3c-converted"},
            ],
        },
        {
            "name": "Interface {#IFDESCR}: 入丢包",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.2.1.2.2.1.13.{#SNMPINDEX}]",  # ifInDiscards
            "key": "net.if.in.discards[ifInDiscards.{#SNMPINDEX}]",
            "delay": "3m",
            "value_type": "UNSIGNED",
            "description": "MIB: IF-MIB\nifInDiscards: 接口入方向丢弃包数。",
            "preprocessing": [{"type": "CHANGE_PER_SECOND", "parameters": []}],
            "tags": [
                {"tag": "component", "value": "network"},
                {"tag": "interface", "value": "{#IFDESCR}"},
                {"tag": "source", "value": "h3c-converted"},
            ],
        },
        {
            "name": "Interface {#IFDESCR}: 出丢包",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.2.1.2.2.1.19.{#SNMPINDEX}]",  # ifOutDiscards
            "key": "net.if.out.discards[ifOutDiscards.{#SNMPINDEX}]",
            "delay": "3m",
            "value_type": "UNSIGNED",
            "description": "MIB: IF-MIB\nifOutDiscards: 接口出方向丢弃包数。",
            "preprocessing": [{"type": "CHANGE_PER_SECOND", "parameters": []}],
            "tags": [
                {"tag": "component", "value": "network"},
                {"tag": "interface", "value": "{#IFDESCR}"},
                {"tag": "source", "value": "h3c-converted"},
            ],
        },
        {
            "name": "Interface {#IFDESCR}: 速率",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.2.1.31.1.1.1.15.{#SNMPINDEX}]",  # ifHighSpeed
            "key": "net.if.speed[ifHighSpeed.{#SNMPINDEX}]",
            "delay": "5m",
            "value_type": "UNSIGNED",
            "units": "bps",
            "description": "MIB: IF-MIB\nifHighSpeed: 接口额定速率（Mbps 转 bps）。",
            "preprocessing": [
                {
                    "type": "MULTIPLIER",
                    "parameters": ["1000000"],
                }
            ],
            "tags": [
                {"tag": "component", "value": "network"},
                {"tag": "interface", "value": "{#IFDESCR}"},
                {"tag": "source", "value": "h3c-converted"},
            ],
        },
        {
            "name": "Interface {#IFDESCR}: 运行状态",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.2.1.2.2.1.8.{#SNMPINDEX}]",  # ifOperStatus
            "key": "net.if.status[ifOperStatus.{#SNMPINDEX}]",
            "delay": "1m",
            "value_type": "UNSIGNED",
            "description": "MIB: IF-MIB\nifOperStatus: 接口当前运行状态（1=up, 2=down, 3=testing）。",
            "valuemap": "IF-MIB::ifOperStatus",
            "tags": [
                {"tag": "component", "value": "network"},
                {"tag": "interface", "value": "{#IFDESCR}"},
                {"tag": "source", "value": "h3c-converted"},
            ],
            "trigger_prototypes": [
                {
                    "name": "Interface {#IFDESCR}: 接口链路 down",
                    "expression": (
                        "last(/{TEMPLATE_KEY}/net.if.status[ifOperStatus.{#SNMPINDEX}])=2"
                    ),
                    "priority": "AVERAGE",
                    "description": "接口运行状态变为 down。",
                    "tags": [
                        {"tag": "scope", "value": "availability"},
                        {"tag": "interface", "value": "{#IFDESCR}"},
                    ],
                }
            ],
        },
    ],
}

# ── H3C 网络设备专用：实体 LLD（CPU/内存/温度/风扇/电源） ─────────────────
_HH3C_ENTITY_LLD: dict = {
    "name": "Entity discovery (HH3C MIB)",
    "type": "SNMP_AGENT",
    "snmp_oid": "walk[1.3.6.1.4.1.25506.2.6.1.1.1]",  # hh3cEntityExtEntry
    "key": "entity.discovery",
    "delay": "1h",
    "description": "MIB: HH3C-ENTITY-EXT-MIB\n发现 H3C 设备实体（模块/CPU/内存等）。",
    "lld_macro_paths": [
        {"lld_macro": "{#SNMPINDEX}", "path": "$.index"},
        {"lld_macro": "{#ENT_NAME}", "path": "$.name"},
    ],
    "item_prototypes": [
        {
            "name": "Entity {#ENT_NAME}: CPU 利用率",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.4.1.25506.2.6.1.1.1.1.6.{#SNMPINDEX}]",  # hh3cEntityExtCpuUsage
            "key": "system.cpu.util[hh3cEntityExtCpuUsage.{#SNMPINDEX}]",
            "delay": "1m",
            "value_type": "FLOAT",
            "units": "%",
            "description": "MIB: HH3C-ENTITY-EXT-MIB\nhh3cEntityExtCpuUsage: 实体 CPU 利用率（%）。",
            "tags": [
                {"tag": "component", "value": "cpu"},
                {"tag": "source", "value": "h3c-converted"},
            ],
        },
        {
            "name": "Entity {#ENT_NAME}: 内存利用率",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.4.1.25506.2.6.1.1.1.1.8.{#SNMPINDEX}]",  # hh3cEntityExtMemUsage
            "key": "vm.memory.util[hh3cEntityExtMemUsage.{#SNMPINDEX}]",
            "delay": "1m",
            "value_type": "FLOAT",
            "units": "%",
            "description": "MIB: HH3C-ENTITY-EXT-MIB\nhh3cEntityExtMemUsage: 实体内存利用率（%）。",
            "tags": [
                {"tag": "component", "value": "memory"},
                {"tag": "source", "value": "h3c-converted"},
            ],
        },
        {
            "name": "Entity {#ENT_NAME}: 温度",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.4.1.25506.2.6.1.1.1.1.12.{#SNMPINDEX}]",  # hh3cEntityExtTemperature
            "key": "sensor.temp.value[hh3cEntityExtTemperature.{#SNMPINDEX}]",
            "delay": "3m",
            "value_type": "FLOAT",
            "units": "°C",
            "description": "MIB: HH3C-ENTITY-EXT-MIB\nhh3cEntityExtTemperature: 实体温度（℃）。",
            "tags": [
                {"tag": "component", "value": "temperature"},
                {"tag": "source", "value": "h3c-converted"},
            ],
        },
        {
            "name": "Entity {#ENT_NAME}: 错误状态",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.4.1.25506.2.6.1.1.1.1.19.{#SNMPINDEX}]",  # hh3cEntityExtErrorStatus
            "key": "sensor.status[hh3cEntityExtErrorStatus.{#SNMPINDEX}]",
            "delay": "3m",
            "value_type": "UNSIGNED",
            "description": "MIB: HH3C-ENTITY-EXT-MIB\nhh3cEntityExtErrorStatus: 实体错误状态（0=正常）。",
            "tags": [
                {"tag": "component", "value": "hardware"},
                {"tag": "source", "value": "h3c-converted"},
            ],
            "trigger_prototypes": [
                {
                    "name": "Entity {#ENT_NAME}: 硬件故障",
                    "expression": (
                        "last(/{TEMPLATE_KEY}/sensor.status[hh3cEntityExtErrorStatus.{#SNMPINDEX}])<>0"
                    ),
                    "priority": "AVERAGE",
                    "description": "实体报告硬件错误，请检查设备状态。",
                    "tags": [{"tag": "scope", "value": "availability"}],
                }
            ],
        },
    ],
}

# ── Linux SNMP 专用 Items（UCD-SNMP-MIB） ─────────────────────────────────
_LINUX_SNMP_ITEMS: list[dict] = [
    {
        "name": "CPU 总利用率",
        "type": "SNMP_AGENT",
        "snmp_oid": "walk[1.3.6.1.4.1.2021.11]",  # UCD-SNMP-MIB::systemStats
        "key": "system.cpu.walk",
        "delay": "1m",
        "value_type": "TEXT",
        "trends": "0",
        "description": "MIB: UCD-SNMP-MIB\n采集系统 CPU 统计原始数据（walk），供 Dependent item 解析。",
        "tags": [
            {"tag": "component", "value": "cpu"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "CPU 利用率（用户态）",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.4.1.2021.11.9.0]",  # ssCpuUser
        "key": "system.cpu.util[,user]",
        "delay": "1m",
        "value_type": "FLOAT",
        "units": "%",
        "description": "MIB: UCD-SNMP-MIB\nssCpuUser: 用户态 CPU 占比（%）。",
        "tags": [
            {"tag": "component", "value": "cpu"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "CPU 利用率（系统态）",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.4.1.2021.11.10.0]",  # ssCpuSystem
        "key": "system.cpu.util[,system]",
        "delay": "1m",
        "value_type": "FLOAT",
        "units": "%",
        "description": "MIB: UCD-SNMP-MIB\nssCpuSystem: 系统态 CPU 占比（%）。",
        "tags": [
            {"tag": "component", "value": "cpu"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "CPU 利用率（I/O 等待）",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.4.1.2021.11.54.0]",  # ssCpuRawWait
        "key": "system.cpu.util[,iowait]",
        "delay": "1m",
        "value_type": "FLOAT",
        "units": "%",
        "description": "MIB: UCD-SNMP-MIB\nssCpuRawWait: I/O 等待 CPU 占比（%）。",
        "tags": [
            {"tag": "component", "value": "cpu"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "CPU 负载（1分钟）",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.4.1.2021.10.1.3.1]",  # laLoad.1
        "key": "system.cpu.load[all,avg1]",
        "delay": "1m",
        "value_type": "FLOAT",
        "description": "MIB: UCD-SNMP-MIB\nlaLoad.1: 1 分钟平均负载。",
        "tags": [
            {"tag": "component", "value": "cpu"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "CPU 负载（5分钟）",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.4.1.2021.10.1.3.2]",  # laLoad.2
        "key": "system.cpu.load[all,avg5]",
        "delay": "1m",
        "value_type": "FLOAT",
        "description": "MIB: UCD-SNMP-MIB\nlaLoad.2: 5 分钟平均负载。",
        "tags": [
            {"tag": "component", "value": "cpu"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "CPU 负载（15分钟）",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.4.1.2021.10.1.3.3]",  # laLoad.3
        "key": "system.cpu.load[all,avg15]",
        "delay": "1m",
        "value_type": "FLOAT",
        "description": "MIB: UCD-SNMP-MIB\nlaLoad.3: 15 分钟平均负载。",
        "tags": [
            {"tag": "component", "value": "cpu"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "内存总量",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.4.1.2021.4.5.0]",  # memTotalReal
        "key": "vm.memory.total[memTotalReal.0]",
        "delay": "1m",
        "value_type": "UNSIGNED",
        "units": "B",
        "description": "MIB: UCD-SNMP-MIB\nmemTotalReal: 物理内存总量（KB，Zabbix 自动换算 B）。",
        "preprocessing": [{"type": "MULTIPLIER", "parameters": ["1024"]}],
        "tags": [
            {"tag": "component", "value": "memory"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "可用内存",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.4.1.2021.4.11.0]",  # memAvailReal
        "key": "vm.memory.free[memAvailReal.0]",
        "delay": "1m",
        "value_type": "UNSIGNED",
        "units": "B",
        "description": "MIB: UCD-SNMP-MIB\nmemAvailReal: 可用物理内存（KB）。",
        "preprocessing": [{"type": "MULTIPLIER", "parameters": ["1024"]}],
        "tags": [
            {"tag": "component", "value": "memory"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "内存利用率",
        "type": "CALCULATED",
        "key": "vm.memory.util[snmp]",
        "delay": "1m",
        "value_type": "FLOAT",
        "units": "%",
        "params": (
            "100*(last(//vm.memory.total[memTotalReal.0])-last(//vm.memory.free[memAvailReal.0]))"
            "/last(//vm.memory.total[memTotalReal.0])"
        ),
        "description": "根据 memTotalReal / memAvailReal 计算内存利用率（%）。",
        "tags": [
            {"tag": "component", "value": "memory"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "Swap 总量",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.4.1.2021.4.3.0]",  # memTotalSwap
        "key": "system.swap.size[,total]",
        "delay": "1m",
        "value_type": "UNSIGNED",
        "units": "B",
        "description": "MIB: UCD-SNMP-MIB\nmemTotalSwap: Swap 总量（KB）。",
        "preprocessing": [{"type": "MULTIPLIER", "parameters": ["1024"]}],
        "tags": [
            {"tag": "component", "value": "memory"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "Swap 剩余",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.4.1.2021.4.4.0]",  # memAvailSwap
        "key": "system.swap.size[,free]",
        "delay": "1m",
        "value_type": "UNSIGNED",
        "units": "B",
        "description": "MIB: UCD-SNMP-MIB\nmemAvailSwap: Swap 剩余（KB）。",
        "preprocessing": [{"type": "MULTIPLIER", "parameters": ["1024"]}],
        "tags": [
            {"tag": "component", "value": "memory"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
]

# ── Linux SNMP 文件系统 LLD（HOST-RESOURCES-MIB） ─────────────────────────
_LINUX_FS_LLD: dict = {
    "name": "Filesystem discovery (SNMP)",
    "type": "SNMP_AGENT",
    "snmp_oid": "walk[1.3.6.1.2.1.25.3.8]",  # hrStorageEntry（HOST-RESOURCES-MIB）
    "key": "vfs.fs.discovery[snmp]",
    "delay": "1h",
    "description": "MIB: HOST-RESOURCES-MIB\n发现本机存储资源（文件系统）。",
    "lld_macro_paths": [
        {"lld_macro": "{#SNMPINDEX}", "path": "$.index"},
        {"lld_macro": "{#FSNAME}", "path": "$.name"},
        {"lld_macro": "{#FSTYPE}", "path": "$.type"},
    ],
    "filter": {
        "evaltype": "AND_OR",
        "conditions": [
            {
                "macro": "{#FSTYPE}",
                "value": "hrStorageFixedDisk",
                "operator": "MATCHES_REGEX",
                "formulaid": "A",
            }
        ],
    },
    "item_prototypes": [
        {
            "name": "Filesystem {#FSNAME}: 总空间",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.2.1.25.2.3.1.5.{#SNMPINDEX}]",  # hrStorageSize
            "key": "vfs.fs.total[dskTotal.{#SNMPINDEX}]",
            "delay": "1m",
            "value_type": "UNSIGNED",
            "units": "B",
            "description": "MIB: HOST-RESOURCES-MIB\nhrStorageSize: 文件系统总分配块数 × AllocationUnits。",
            "preprocessing": [
                {
                    "type": "MULTIPLIER",
                    "parameters": ["{#ALLOC_UNITS}"],
                }
            ],
            "tags": [
                {"tag": "component", "value": "storage"},
                {"tag": "filesystem", "value": "{#FSNAME}"},
                {"tag": "source", "value": "h3c-converted"},
            ],
        },
        {
            "name": "Filesystem {#FSNAME}: 已用空间",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.2.1.25.2.3.1.6.{#SNMPINDEX}]",  # hrStorageUsed
            "key": "vfs.fs.used[dskUsed.{#SNMPINDEX}]",
            "delay": "1m",
            "value_type": "UNSIGNED",
            "units": "B",
            "description": "MIB: HOST-RESOURCES-MIB\nhrStorageUsed: 已使用块数 × AllocationUnits。",
            "preprocessing": [
                {
                    "type": "MULTIPLIER",
                    "parameters": ["{#ALLOC_UNITS}"],
                }
            ],
            "tags": [
                {"tag": "component", "value": "storage"},
                {"tag": "filesystem", "value": "{#FSNAME}"},
                {"tag": "source", "value": "h3c-converted"},
            ],
        },
        {
            "name": "Filesystem {#FSNAME}: 利用率",
            "type": "CALCULATED",
            "key": "vfs.fs.pused[{#SNMPINDEX}]",
            "delay": "1m",
            "value_type": "FLOAT",
            "units": "%",
            "params": (
                "100*last(//vfs.fs.used[dskUsed.{#SNMPINDEX}])"
                "/last(//vfs.fs.total[dskTotal.{#SNMPINDEX}])"
            ),
            "description": "文件系统使用率（%）。",
            "tags": [
                {"tag": "component", "value": "storage"},
                {"tag": "filesystem", "value": "{#FSNAME}"},
                {"tag": "source", "value": "h3c-converted"},
            ],
        },
    ],
}

# ── Brocade FC 专用 Items（SW-MIB） ─────────────────────────────────────
_BROCADE_FC_ITEMS: list[dict] = [
    {
        "name": "FC switch: CPU 利用率",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.4.1.1588.2.1.1.1.26.1.0]",  # swCpuUsage
        "key": "system.cpu.util",
        "delay": "1m",
        "value_type": "FLOAT",
        "units": "%",
        "description": "MIB: SW-MIB (Brocade)\nswCpuUsage: 交换机 CPU 利用率（%）。",
        "tags": [
            {"tag": "component", "value": "cpu"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "FC switch: 内存利用率",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.4.1.1588.2.1.1.1.26.6.0]",  # swMemUsage
        "key": "vm.memory.util",
        "delay": "1m",
        "value_type": "FLOAT",
        "units": "%",
        "description": "MIB: SW-MIB (Brocade)\nswMemUsage: 内存使用率（%）。",
        "tags": [
            {"tag": "component", "value": "memory"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
    {
        "name": "FC switch: 固件版本",
        "type": "SNMP_AGENT",
        "snmp_oid": "get[1.3.6.1.4.1.1588.2.1.1.1.1.6.0]",  # swFirmwareVersion
        "key": "system.sw.version",
        "delay": "1h",
        "value_type": "CHAR",
        "trends": "0",
        "description": "MIB: SW-MIB\nswFirmwareVersion: Brocade FC 交换机固件版本。",
        "preprocessing": [
            {"type": "DISCARD_UNCHANGED_HEARTBEAT", "parameters": ["12h"]}
        ],
        "tags": [
            {"tag": "component", "value": "system"},
            {"tag": "source", "value": "h3c-converted"},
        ],
    },
]

# ── Brocade FC 端口 LLD ────────────────────────────────────────────────
_BROCADE_PORT_LLD: dict = {
    "name": "FC port discovery (Brocade)",
    "type": "SNMP_AGENT",
    "snmp_oid": "walk[1.3.6.1.4.1.1588.2.1.1.1.6.2.1]",  # swFCPortEntry
    "key": "fc.port.discovery",
    "delay": "1h",
    "description": "MIB: SW-MIB (Brocade)\n发现 FC 端口列表。",
    "lld_macro_paths": [
        {"lld_macro": "{#SNMPINDEX}", "path": "$.index"},
        {"lld_macro": "{#PORT_NAME}", "path": "$.name"},
    ],
    "item_prototypes": [
        {
            "name": "FC port {#SNMPINDEX}: 入字节数",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.4.1.1588.2.1.1.1.6.2.1.11.{#SNMPINDEX}]",  # swFCPortRxWords
            "key": "net.if.in[swFCPortRxWords.{#SNMPINDEX}]",
            "delay": "3m",
            "value_type": "UNSIGNED",
            "units": "Bps",
            "description": "MIB: SW-MIB\nswFCPortRxWords: FC 端口接收字数（4字节/字）。",
            "preprocessing": [
                {"type": "CHANGE_PER_SECOND", "parameters": []},
                {"type": "MULTIPLIER", "parameters": ["4"]},
            ],
            "tags": [
                {"tag": "component", "value": "network"},
                {"tag": "source", "value": "h3c-converted"},
            ],
        },
        {
            "name": "FC port {#SNMPINDEX}: 出字节数",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.4.1.1588.2.1.1.1.6.2.1.12.{#SNMPINDEX}]",  # swFCPortTxWords
            "key": "net.if.out[swFCPortTxWords.{#SNMPINDEX}]",
            "delay": "3m",
            "value_type": "UNSIGNED",
            "units": "Bps",
            "description": "MIB: SW-MIB\nswFCPortTxWords: FC 端口发送字数。",
            "preprocessing": [
                {"type": "CHANGE_PER_SECOND", "parameters": []},
                {"type": "MULTIPLIER", "parameters": ["4"]},
            ],
            "tags": [
                {"tag": "component", "value": "network"},
                {"tag": "source", "value": "h3c-converted"},
            ],
        },
        {
            "name": "FC port {#SNMPINDEX}: 端口状态",
            "type": "SNMP_AGENT",
            "snmp_oid": "get[1.3.6.1.4.1.1588.2.1.1.1.6.2.1.4.{#SNMPINDEX}]",  # swFCPortOpStatus
            "key": "net.if.status[swFCPortOpStatus.{#SNMPINDEX}]",
            "delay": "1m",
            "value_type": "UNSIGNED",
            "description": "MIB: SW-MIB\nswFCPortOpStatus: FC 端口运行状态（1=online, 2=offline）。",
            "valuemap": "Brocade::swFCPortOpStatus",
            "tags": [
                {"tag": "component", "value": "network"},
                {"tag": "source", "value": "h3c-converted"},
            ],
            "trigger_prototypes": [
                {
                    "name": "FC port {#SNMPINDEX}: 端口 offline",
                    "expression": (
                        "last(/{TEMPLATE_KEY}/net.if.status[swFCPortOpStatus.{#SNMPINDEX}])=2"
                    ),
                    "priority": "AVERAGE",
                    "description": "FC 端口状态变为 offline。",
                    "tags": [{"tag": "scope", "value": "availability"}],
                }
            ],
        },
    ],
}

# ── 公共宏定义 ────────────────────────────────────────────────────────────────
_COMMON_MACROS: list[dict] = [
    {
        "macro": "{$SNMP_COMMUNITY}",
        "value": "public",
        "description": "SNMP community string",
    },
    {
        "macro": "{$SNMP.TIMEOUT}",
        "value": "5m",
        "description": "SNMP 连接超时时间",
    },
    {
        "macro": "{$ICMP_LOSS_WARN}",
        "value": "20",
        "description": "ICMP 丢包率告警阈值（%）",
    },
    {
        "macro": "{$ICMP_RESPONSE_TIME_WARN}",
        "value": "0.15",
        "description": "ICMP 响应时间告警阈值（秒）",
    },
]

# ── 公共 Value Maps ───────────────────────────────────────────────────────────
_VALUE_MAPS: list[dict] = [
    {
        "name": "Service state",
        "mappings": [
            {"value": "0", "newvalue": "Down"},
            {"value": "1", "newvalue": "Up"},
        ],
    },
    {
        "name": "IF-MIB::ifOperStatus",
        "mappings": [
            {"value": "1", "newvalue": "up"},
            {"value": "2", "newvalue": "down"},
            {"value": "3", "newvalue": "testing"},
            {"value": "4", "newvalue": "unknown"},
            {"value": "5", "newvalue": "dormant"},
            {"value": "6", "newvalue": "notPresent"},
            {"value": "7", "newvalue": "lowerLayerDown"},
        ],
    },
    {
        "name": "zabbix.host.available",
        "mappings": [
            {"value": "0", "newvalue": "not available"},
            {"value": "1", "newvalue": "available"},
            {"value": "2", "newvalue": "unknown"},
        ],
    },
    {
        "name": "Brocade::swFCPortOpStatus",
        "mappings": [
            {"value": "1", "newvalue": "online"},
            {"value": "2", "newvalue": "offline"},
            {"value": "3", "newvalue": "testing"},
            {"value": "4", "newvalue": "faulty"},
        ],
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# UUID 生成工具（确定性 UUID，相同输入始终得到相同 UUID）
# ══════════════════════════════════════════════════════════════════════════════


def make_uuid(seed: str) -> str:
    """
    基于 seed 字符串生成确定性的、符合 UUIDv4 格式的 UUID。

    Zabbix 7.0 import 要求：
    1. 32 字符十六进制字符串（无连字符）
    2. 版本号必须是 4（UUID v4 格式：xxxxxxxxxxxxxxxx4xxxYxxxxxxxxxxxxxxx）

    实现方式：
    - 对 seed 做 MD5，得到 128 位哈希值
    - 强制将版本位设为 4（位 48-51 = 0100）
    - 强制将 variant 位设为 10xx（RFC 4122 变体，位 64-65 = 10）
    - 输出 32 字符十六进制字符串（不含连字符）

    同一 seed 始终生成同一 UUID，保证幂等性。
    """
    h = hashlib.md5(f"h3c-snmp-convert:{seed}".encode("utf-8")).digest()
    # 转为可修改的字节数组
    b = bytearray(h)
    # 设置版本位（第 6 字节高 4 位）为 4 (0100)
    b[6] = (b[6] & 0x0F) | 0x40
    # 设置 variant 位（第 8 字节高 2 位）为 10 (RFC 4122)
    b[8] = (b[8] & 0x3F) | 0x80
    return b.hex()


# ══════════════════════════════════════════════════════════════════════════════
# YAML 序列化工具（不依赖 pyyaml，手动生成符合 Zabbix 格式的 YAML）
# ══════════════════════════════════════════════════════════════════════════════


def _yaml_str(value: str, indent: int = 0, flow: bool = False) -> str:
    """
    将 Python 字符串序列化为 YAML 标量。
    - 单行短字符串 → 带引号的字面量
    - 多行或含特殊字符的字符串 → 块字面量（|）
    注意：trigger expression 请使用 _yaml_expr() 专用函数。
    """
    prefix = " " * indent
    if "\n" in value or len(value) > 80:
        lines = value.rstrip("\n").split("\n")
        body = "\n".join(prefix + "  " + ln for ln in lines)
        return "|\n" + body
    # 需要引号的字符（% 在 YAML 中作为指令标识符也需要引号）
    needs_quote = any(c in value for c in ":{}[]|>&*!,'#?@`\"\\ %") or value.startswith(
        " "
    )
    if needs_quote or not value:
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    return value


def _yaml_expr(value: str) -> str:
    """
    将 Zabbix trigger expression 序列化为 YAML 标量。
    Zabbix expression 必须始终是单行单引号字符串，
    即使内容超过 80 字符也不换行（Zabbix parser 不接受块字面量）。
    """
    # expression 中可能包含单引号（罕见但可能），需转义
    escaped = value.replace("'", "\\'")
    return f"'{escaped}'"


def _indent(text: str, n: int) -> str:
    prefix = " " * n
    return "\n".join(
        prefix + line if line.strip() else line for line in text.split("\n")
    )


def _yaml_item(item: dict, tpl_key: str, tpl_name: str, indent: int = 6) -> str:
    """将单个 item dict 序列化为 YAML 块（用于 items 列表中的单项）"""
    pad = " " * indent
    seed = f"{tpl_key}:{item['key']}"
    lines: list[str] = [
        f"{pad}- uuid: {make_uuid(seed)}",
        f"{pad}  name: {_yaml_str(item['name'])}",
        f"{pad}  type: {item['type']}",
    ]
    if "snmp_oid" in item:
        lines.append(f"{pad}  snmp_oid: {_yaml_str(item['snmp_oid'])}")
    lines.append(f"{pad}  key: {_yaml_str(item['key'])}")
    # delay 必须是字符串
    delay_val = str(item.get("delay", "1m")).replace("'", "\\'")
    lines.append(f"{pad}  delay: '{delay_val}'")
    if "trends" in item:
        # trends 必须是字符串
        trends_val = str(item["trends"]).replace("'", "\\'")
        lines.append(f"{pad}  trends: '{trends_val}'")
    if item.get("value_type", "UNSIGNED") != "UNSIGNED":
        lines.append(f"{pad}  value_type: {item['value_type']}")
    if item.get("units"):
        lines.append(f"{pad}  units: {_yaml_str(item['units'])}")
    if "params" in item:
        # CALCULATED item 的 params 表达式必须用单引号包裹
        params_val = item["params"].replace("'", "\\'")
        lines.append(f"{pad}  params: '{params_val}'")
    if "inventory_link" in item:
        lines.append(f"{pad}  inventory_link: {item['inventory_link']}")
    if "logtimefmt" in item:
        lines.append(f"{pad}  logtimefmt: {_yaml_str(item['logtimefmt'])}")
    if item.get("description"):
        desc = item["description"]
        if "\n" in desc:
            lines.append(f"{pad}  description: |")
            for dl in desc.rstrip("\n").split("\n"):
                lines.append(f"{pad}    {dl}")
        else:
            lines.append(f"{pad}  description: {_yaml_str(desc)}")
    if "valuemap" in item:
        lines.append(f"{pad}  valuemap:")
        lines.append(f"{pad}    name: {_yaml_str(item['valuemap'])}")
    if item.get("preprocessing"):
        lines.append(f"{pad}  preprocessing:")
        for step in item["preprocessing"]:
            lines.append(f"{pad}    - type: {step['type']}")
            params = step.get("parameters", [])
            if params:
                lines.append(f"{pad}      parameters:")
                for p in params:
                    # preprocessing parameters 必须是字符串
                    p_str = str(p).replace("'", "\\'")
                    lines.append(f"{pad}        - '{p_str}'")
            if "error_handler" in step:
                lines.append(f"{pad}      error_handler: {step['error_handler']}")
            if "error_handler_params" in step:
                eh_val = str(step["error_handler_params"]).replace("'", "\\'")
                lines.append(f"{pad}      error_handler_params: '{eh_val}'")
    if item.get("tags"):
        lines.append(f"{pad}  tags:")
        for tag in item["tags"]:
            lines.append(f"{pad}    - tag: {_yaml_str(tag['tag'])}")
            lines.append(f"{pad}      value: {_yaml_str(tag['value'])}")
    if item.get("triggers"):
        lines.append(f"{pad}  triggers:")
        for trig in item["triggers"]:
            t_seed = f"{seed}:trigger:{trig['name']}"
            expr = (
                trig["expression"]
                .replace("/{TEMPLATE_KEY}/", f"/{tpl_key}/")
                .replace("{TEMPLATE_NAME}", tpl_name)
            )
            lines.append(f"{pad}    - uuid: {make_uuid(t_seed)}")
            lines.append(f"{pad}      expression: {_yaml_expr(expr)}")
            lines.append(
                f"{pad}      name: {_yaml_str(trig['name'].replace('{TEMPLATE_NAME}', tpl_name))}"
            )
            if trig.get("opdata"):
                lines.append(f"{pad}      opdata: {_yaml_str(trig['opdata'])}")
            lines.append(f"{pad}      priority: {trig['priority']}")
            if trig.get("description"):
                lines.append(
                    f"{pad}      description: {_yaml_str(trig['description'])}"
                )
            if trig.get("dependencies"):
                lines.append(f"{pad}      dependencies:")
                for dep in trig["dependencies"]:
                    dep_expr = dep["expression"].replace(
                        "/{TEMPLATE_KEY}/", f"/{tpl_key}/"
                    )
                    dep_name = dep["name"].replace("{TEMPLATE_NAME}", tpl_name)
                    lines.append(f"{pad}        - name: {_yaml_str(dep_name)}")
                    lines.append(f"{pad}          expression: {_yaml_expr(dep_expr)}")
            if trig.get("tags"):
                lines.append(f"{pad}      tags:")
                for tt in trig["tags"]:
                    lines.append(f"{pad}        - tag: {_yaml_str(tt['tag'])}")
                    lines.append(f"{pad}          value: {_yaml_str(tt['value'])}")
    return "\n".join(lines)


def _yaml_item_prototype(
    proto: dict, tpl_key: str, tpl_name: str, indent: int = 12
) -> str:
    """序列化 item prototype"""
    pad = " " * indent
    seed = f"{tpl_key}:proto:{proto['key']}"
    lines: list[str] = [
        f"{pad}- uuid: {make_uuid(seed)}",
        f"{pad}  name: {_yaml_str(proto['name'])}",
        f"{pad}  type: {proto['type']}",
    ]
    if "snmp_oid" in proto:
        lines.append(f"{pad}  snmp_oid: {_yaml_str(proto['snmp_oid'])}")
    lines.append(f"{pad}  key: {_yaml_str(proto['key'])}")
    # delay 必须是字符串
    proto_delay_val = str(proto.get("delay", "3m")).replace("'", "\\'")
    lines.append(f"{pad}  delay: '{proto_delay_val}'")
    if proto.get("value_type", "UNSIGNED") != "UNSIGNED":
        lines.append(f"{pad}  value_type: {proto['value_type']}")
    if proto.get("units"):
        lines.append(f"{pad}  units: {_yaml_str(proto['units'])}")
    if "params" in proto:
        # CALCULATED prototype 的 params 表达式必须用单引号包裹
        proto_params_val = proto["params"].replace("'", "\\'")
        lines.append(f"{pad}  params: '{proto_params_val}'")
    if proto.get("description"):
        desc = proto["description"]
        if "\n" in desc:
            lines.append(f"{pad}  description: |")
            for dl in desc.rstrip("\n").split("\n"):
                lines.append(f"{pad}    {dl}")
        else:
            lines.append(f"{pad}  description: {_yaml_str(desc)}")
    if "valuemap" in proto:
        lines.append(f"{pad}  valuemap:")
        lines.append(f"{pad}    name: {_yaml_str(proto['valuemap'])}")
    if proto.get("preprocessing"):
        lines.append(f"{pad}  preprocessing:")
        for step in proto["preprocessing"]:
            lines.append(f"{pad}    - type: {step['type']}")
            params = step.get("parameters", [])
            if params:
                lines.append(f"{pad}      parameters:")
                for p in params:
                    # preprocessing parameters 必须是字符串
                    p_str = str(p).replace("'", "\\'")
                    lines.append(f"{pad}        - '{p_str}'")
    if proto.get("tags"):
        lines.append(f"{pad}  tags:")
        for tag in proto["tags"]:
            lines.append(f"{pad}    - tag: {_yaml_str(tag['tag'])}")
            lines.append(f"{pad}      value: {_yaml_str(tag['value'])}")
    # trigger prototypes
    if proto.get("trigger_prototypes"):
        lines.append(f"{pad}  trigger_prototypes:")
        for tp in proto["trigger_prototypes"]:
            tp_seed = f"{seed}:tp:{tp['name']}"
            expr = tp["expression"].replace("/{TEMPLATE_KEY}/", f"/{tpl_key}/")
            lines.append(f"{pad}    - uuid: {make_uuid(tp_seed)}")
            lines.append(f"{pad}      expression: {_yaml_expr(expr)}")
            lines.append(f"{pad}      name: {_yaml_str(tp['name'])}")
            lines.append(f"{pad}      priority: {tp['priority']}")
            if tp.get("description"):
                lines.append(f"{pad}      description: {_yaml_str(tp['description'])}")
            if tp.get("tags"):
                lines.append(f"{pad}      tags:")
                for tt in tp["tags"]:
                    lines.append(f"{pad}        - tag: {_yaml_str(tt['tag'])}")
                    lines.append(f"{pad}          value: {_yaml_str(tt['value'])}")
    return "\n".join(lines)


def _yaml_lld(lld: dict, tpl_key: str, tpl_name: str, indent: int = 6) -> str:
    """序列化 LLD 规则（含 item_prototypes）"""
    pad = " " * indent
    seed = f"{tpl_key}:lld:{lld['key']}"
    lines: list[str] = [
        f"{pad}- uuid: {make_uuid(seed)}",
        f"{pad}  name: {_yaml_str(lld['name'])}",
        f"{pad}  type: {lld['type']}",
    ]
    if "snmp_oid" in lld:
        lines.append(f"{pad}  snmp_oid: {_yaml_str(lld['snmp_oid'])}")
    lines.append(f"{pad}  key: {_yaml_str(lld['key'])}")
    # delay 必须是字符串
    lld_delay_val = str(lld.get("delay", "1h")).replace("'", "\\'")
    lines.append(f"{pad}  delay: '{lld_delay_val}'")
    if lld.get("description"):
        desc = lld["description"]
        if "\n" in desc:
            lines.append(f"{pad}  description: |")
            for dl in desc.rstrip("\n").split("\n"):
                lines.append(f"{pad}    {dl}")
        else:
            lines.append(f"{pad}  description: {_yaml_str(desc)}")
    # filter
    if lld.get("filter"):
        f = lld["filter"]
        lines.append(f"{pad}  filter:")
        lines.append(f"{pad}    evaltype: {f.get('evaltype', 'AND_OR')}")
        if f.get("conditions"):
            lines.append(f"{pad}    conditions:")
            for cond in f["conditions"]:
                lines.append(f"{pad}      - macro: {_yaml_str(cond['macro'])}")
                # filter condition value 必须是字符串
                cond_val = str(cond["value"]).replace("'", "\\'")
                lines.append(f"{pad}        value: '{cond_val}'")
                lines.append(
                    f"{pad}        operator: {cond.get('operator', 'MATCHES_REGEX')}"
                )
                lines.append(f"{pad}        formulaid: {cond.get('formulaid', 'A')}")
    # lld_macro_paths
    if lld.get("lld_macro_paths"):
        lines.append(f"{pad}  lld_macro_paths:")
        for mp in lld["lld_macro_paths"]:
            lines.append(f"{pad}    - lld_macro: {_yaml_str(mp['lld_macro'])}")
            lines.append(f"{pad}      path: {_yaml_str(mp['path'])}")
    # item_prototypes
    if lld.get("item_prototypes"):
        lines.append(f"{pad}  item_prototypes:")
        for proto in lld["item_prototypes"]:
            proto_yaml = _yaml_item_prototype(proto, tpl_key, tpl_name, indent + 4)
            lines.append(proto_yaml)
    return "\n".join(lines)


def _yaml_valuemap(vm: dict, indent: int = 4, uuid_prefix: str = "") -> str:
    pad = " " * indent
    seed = (
        f"valuemap:{uuid_prefix}:{vm['name']}"
        if uuid_prefix
        else f"valuemap:{vm['name']}"
    )
    lines = [
        f"{pad}- uuid: {make_uuid(seed)}",
        f"{pad}  name: {_yaml_str(vm['name'])}",
        f"{pad}  mappings:",
    ]
    for m in vm["mappings"]:
        mtype = m.get("type", "EQUAL")
        # value 和 newvalue 在 Zabbix 中必须是字符串，用单引号包裹
        val_str = str(m["value"]).replace("'", "\\'")
        newval_str = str(m["newvalue"]).replace("'", "\\'")
        if mtype != "EQUAL":
            lines.append(f"{pad}    - type: {mtype}")
            lines.append(f"{pad}      value: '{val_str}'")
        else:
            lines.append(f"{pad}    - value: '{val_str}'")
        lines.append(f"{pad}      newvalue: '{newval_str}'")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 模板构建器
# ══════════════════════════════════════════════════════════════════════════════


class TemplateBuilder:
    """
    根据华三模板数据 + SNMP 映射规则，构建 Zabbix YAML 模板。
    每个华三模板对应一个 TemplateBuilder 实例。
    """

    def __init__(self, h3c_tpl: dict) -> None:
        self.h3c = h3c_tpl
        self.h3c_type: str = h3c_tpl.get("type", "")
        self.h3c_name: str = h3c_tpl.get("name", "")
        # Zabbix 模板名：加前缀以避免与系统模板冲突
        self.tpl_name: str = f"H3C {self.h3c_name} by SNMP"
        # Zabbix 内部 key（template 字段）：
        # - 必须是 ASCII（不能含中文）
        # - 去除特殊字符
        # 将中文名转为拼音首字母缩写或直接用 h3c_type 作为唯一标识
        safe_type = self.h3c_type.upper()
        self.tpl_key: str = f"H3C_{safe_type}_by_SNMP"
        self.group: str = H3C_TYPE_TO_GROUP.get(self.h3c_type, "H3C Converted")
        self.items: list[dict] = []
        self.discovery_rules: list[dict] = []
        self.macros: list[dict] = list(_COMMON_MACROS)  # 复制，避免共享
        self._triggers_generated: list[dict] = []

    # ── 内部辅助 ────────────────────────────────────────────────────────────

    def _find_unit(self, unit_key: str) -> dict | None:
        for u in self.h3c.get("unitList", []):
            if u.get("unit") == unit_key:
                return u
        return None

    def _collect_time(self, unit_key: str, default: int = 300) -> str:
        u = self._find_unit(unit_key)
        if u:
            return f"{u.get('collectTime', default)}s"
        return f"{default}s"

    def _add_threshold_triggers(
        self,
        item_key: str,
        h3c_unit: str,
        h3c_field: str,
    ) -> list[dict]:
        """
        从华三 thresholds 中查找对应的阈值配置，
        生成 Zabbix trigger 字典列表（附加到 item.triggers）。
        """
        triggers: list[dict] = []
        for thr in self.h3c.get("thresholds", []):
            for cond in thr.get("conditions", []):
                if cond.get("unit") != h3c_unit or cond.get("field") != h3c_field:
                    continue
                operator = cond.get("operator", "GE")
                zop = OPERATOR_MAP.get(operator)
                if not zop:
                    continue  # RULE/IC/EC/CHG 等运算符暂不转换
                collect_t = self._collect_time(h3c_unit, 300)
                collect_sec = int(collect_t.rstrip("s"))

                for lvl in cond.get("threshold", []):
                    if not lvl.get("enable"):
                        continue
                    level_num = int(lvl.get("level", 4))
                    severity = SEVERITY_MAP.get(level_num, "AVERAGE")
                    value = str(lvl.get("value", ""))
                    trigger_cnt = int(lvl.get("trigger", 1))

                    # count() 专用英文缩写运算符
                    count_op_str = COUNT_OPERATOR_MAP.get(operator, "ge")

                    # 构建表达式
                    if trigger_cnt > 1:
                        window = collect_sec * trigger_cnt
                        expr = (
                            f"count(/{'{TEMPLATE_KEY}'}/{item_key}"
                            f',{window}s,"{count_op_str}","{value}")>={trigger_cnt}'
                        )
                    else:
                        zop_str = OPERATOR_MAP.get(operator, ">=")
                        expr = f"last(/{'{TEMPLATE_KEY}'}/{item_key}){zop_str}{value}"

                    triggers.append(
                        {
                            "name": f"{{TEMPLATE_NAME}}: {self.h3c_name} {h3c_field} {operator} {value}（{severity}）",
                            "expression": expr,
                            "priority": severity,
                            "description": (
                                f"华三阈值转换：{h3c_unit}/{h3c_field} "
                                f"{operator} {value}，"
                                f"持续 {trigger_cnt} 次（每次 {collect_sec}s）。"
                            ),
                            "tags": [{"tag": "scope", "value": "performance"}],
                        }
                    )
        return triggers

    # ── 公共基础 items ────────────────────────────────────────────────────────

    def _add_common_items(self) -> None:
        """添加所有 SNMP 类型共用的基础 items（ICMP / sysDescr / sysUpTime …）"""
        for base_item in _COMMON_SNMP_ITEMS:
            item = dict(base_item)
            # 对 delay 使用华三 collectTime 作为参考（可用性单元）
            if item["key"] == "agent.ping" or item["key"] == "icmpping":
                avail_unit = self._find_unit("AvailableData")
                if avail_unit:
                    ct = avail_unit.get("collectTime", 60)
                    item = {**item, "delay": f"{ct}s"}
            self.items.append(item)

    # ── 网络设备 ─────────────────────────────────────────────────────────────

    def _build_network(self) -> None:
        self._add_common_items()
        # 接口 LLD
        if_lld = dict(_NETWORK_IF_LLD)
        # 根据华三 interface 单元的 collectTime 调整采集间隔
        ct = self._collect_time("interface", 300)
        for proto in if_lld.get("item_prototypes", []):
            if "delay" in proto and proto["delay"] != "1m":
                proto = {**proto, "delay": ct}
        self.discovery_rules.append(if_lld)

        # H3C 私有 MIB 实体 LLD（CPU/内存/温度/风扇）
        entity_lld = dict(_HH3C_ENTITY_LLD)
        # 根据华三阈值添加 CPU trigger prototype
        cpu_unit = self._find_unit("cpu")
        if cpu_unit:
            cpu_proto = entity_lld["item_prototypes"][0]  # CPU 利用率
            cpu_triggers = self._add_threshold_triggers(
                cpu_proto["key"], "cpu", "cpuUtilization"
            )
            if cpu_triggers:
                cpu_proto = {**cpu_proto, "trigger_prototypes": cpu_triggers}
                protos = list(entity_lld["item_prototypes"])
                protos[0] = cpu_proto
                entity_lld = {**entity_lld, "item_prototypes": protos}

        self.discovery_rules.append(entity_lld)

        # 温度/风扇/电源额外宏
        temp_thr = self._get_threshold("boardTemp", "devBoardTemp")
        if temp_thr:
            warn_val = temp_thr.get("warn", "60")
            crit_val = temp_thr.get("crit", "80")
            self.macros.append(
                {
                    "macro": "{$TEMP_WARN}",
                    "value": warn_val,
                    "description": "温度告警阈值（℃）",
                }
            )
            self.macros.append(
                {
                    "macro": "{$TEMP_CRIT}",
                    "value": crit_val,
                    "description": "温度严重告警阈值（℃）",
                }
            )

    def _get_threshold(self, unit_key: str, field_key: str) -> dict[str, str] | None:
        """
        从华三 thresholds 中提取 warn/crit 值（level=3 为 warn，level=4 为 crit）。
        """
        result: dict[str, str] = {}
        for thr in self.h3c.get("thresholds", []):
            for cond in thr.get("conditions", []):
                if cond.get("unit") == unit_key and cond.get("field") == field_key:
                    for lvl in cond.get("threshold", []):
                        if not lvl.get("enable"):
                            continue
                        ln = int(lvl.get("level", 4))
                        val = str(lvl.get("value", ""))
                        if ln == 3:
                            result["warn"] = val
                        elif ln in (4, 5):
                            result["crit"] = val
        return result if result else None

    # ── Linux SNMP ───────────────────────────────────────────────────────────

    def _build_linux_snmp(self) -> None:
        self._add_common_items()

        # CPU + 内存 items
        for item in _LINUX_SNMP_ITEMS:
            it = dict(item)
            if it["key"].startswith("system.cpu."):
                ct = self._collect_time("cpu", 300)
                it["delay"] = ct
            elif it["key"].startswith("vm.memory.") or it["key"].startswith(
                "system.swap."
            ):
                ct = self._collect_time("memory", 300)
                it["delay"] = ct

            # 内存利用率：附加告警触发器
            if it["key"] == "vm.memory.util[snmp]":
                triggers = self._add_threshold_triggers(
                    "vm.memory.util[snmp]", "memory", "memUtilization"
                )
                if triggers:
                    it["triggers"] = triggers

            # CPU 利用率：附加告警触发器
            if it["key"] == "system.cpu.util[,user]":
                triggers = self._add_threshold_triggers(
                    "system.cpu.util[,user]", "cpu", "CpuUtilization"
                )
                if triggers:
                    it["triggers"] = triggers

            self.items.append(it)

        # 文件系统 LLD
        fs_lld = dict(_LINUX_FS_LLD)
        fs_ct = self._collect_time("filesystem", 300)
        for proto in fs_lld.get("item_prototypes", []):
            if proto.get("type") == "CALCULATED":
                # 文件系统利用率 trigger
                triggers = self._add_threshold_triggers(
                    proto["key"], "filesystem", "Utilization"
                )
                if triggers:
                    proto["trigger_prototypes"] = triggers
        self.discovery_rules.append(fs_lld)

        # 接口 LLD
        if_lld = dict(_NETWORK_IF_LLD)
        if_ct = self._collect_time("interface", 300)
        self.discovery_rules.append(if_lld)

    # ── Windows SNMP ─────────────────────────────────────────────────────────

    def _build_windows_snmp(self) -> None:
        self._add_common_items()

        # Windows 通过 HOST-RESOURCES-MIB 获取 CPU/内存
        win_items: list[dict] = [
            {
                "name": "CPU 利用率（Windows SNMP）",
                "type": "SNMP_AGENT",
                "snmp_oid": "get[1.3.6.1.2.1.25.3.3.1.2.1]",  # hrProcessorLoad.1
                "key": "system.cpu.util",
                "delay": self._collect_time("cpu", 300),
                "value_type": "FLOAT",
                "units": "%",
                "description": "MIB: HOST-RESOURCES-MIB\nhrProcessorLoad: 处理器近期运行时间百分比。",
                "tags": [
                    {"tag": "component", "value": "cpu"},
                    {"tag": "source", "value": "h3c-converted"},
                ],
                "triggers": self._add_threshold_triggers(
                    "system.cpu.util", "cpu", "CpuUtilization"
                ),
            },
            {
                "name": "内存总量（Windows SNMP）",
                "type": "SNMP_AGENT",
                "snmp_oid": "get[1.3.6.1.2.1.25.2.2.0]",  # hrMemorySize
                "key": "vm.memory.total[hrMemorySize.0]",
                "delay": self._collect_time("memory", 300),
                "value_type": "UNSIGNED",
                "units": "B",
                "description": "MIB: HOST-RESOURCES-MIB\nhrMemorySize: 主机物理内存总量（KB）。",
                "preprocessing": [{"type": "MULTIPLIER", "parameters": ["1024"]}],
                "tags": [
                    {"tag": "component", "value": "memory"},
                    {"tag": "source", "value": "h3c-converted"},
                ],
            },
        ]
        for item in win_items:
            # 去掉空 triggers 列表
            if "triggers" in item and not item["triggers"]:
                del item["triggers"]
            self.items.append(item)

        # 文件系统 LLD（Windows 同样使用 HOST-RESOURCES-MIB）
        win_fs_lld = dict(_LINUX_FS_LLD)
        win_fs_lld["name"] = "Filesystem discovery (Windows SNMP)"
        self.discovery_rules.append(win_fs_lld)

        # 接口 LLD
        self.discovery_rules.append(dict(_NETWORK_IF_LLD))

    # ── Brocade FC ───────────────────────────────────────────────────────────

    def _build_brocade(self) -> None:
        self._add_common_items()

        # Brocade 专用 items
        for item in _BROCADE_FC_ITEMS:
            it = dict(item)
            if "cpu" in it["key"].lower():
                it["delay"] = self._collect_time("basic", 300)
                triggers = self._add_threshold_triggers(
                    it["key"], "basic", "CpuUtilization"
                )
                if triggers:
                    it["triggers"] = triggers
            elif "memory" in it["key"].lower():
                it["delay"] = self._collect_time("basic", 300)
                triggers = self._add_threshold_triggers(
                    it["key"], "basic", "MemUtilization"
                )
                if triggers:
                    it["triggers"] = triggers
            self.items.append(it)

        # FC 端口 LLD
        self.discovery_rules.append(dict(_BROCADE_PORT_LLD))

    # ── Ping 探测 ────────────────────────────────────────────────────────────

    def _build_ping(self) -> None:
        """ICMP ping 模板：只有 Simple Check items，无 SNMP。"""
        avail_unit = self._find_unit("AvailableData")
        ct = f"{avail_unit.get('collectTime', 60)}s" if avail_unit else "60s"

        ping_items: list[dict] = [
            {
                "name": "ICMP ping",
                "type": "SIMPLE",
                "key": "icmpping",
                "delay": ct,
                "value_type": "UNSIGNED",
                "description": "ICMP ping 可达性检测。0=不可达，1=可达。",
                "valuemap": "Service state",
                "tags": [
                    {"tag": "component", "value": "health"},
                    {"tag": "source", "value": "h3c-converted"},
                ],
                "triggers": [
                    {
                        "name": "{TEMPLATE_NAME}: 设备 ICMP ping 不可达",
                        "expression": "max(/{TEMPLATE_KEY}/icmpping,#3)=0",
                        "priority": "HIGH",
                        "description": "连续 3 次 ICMP ping 超时。",
                        "tags": [{"tag": "scope", "value": "availability"}],
                    }
                ],
            },
            {
                "name": "ICMP ping loss",
                "type": "SIMPLE",
                "key": "icmppingloss",
                "delay": ct,
                "value_type": "FLOAT",
                "units": "%",
                "description": "ICMP ping 丢包率（%）。",
                "tags": [
                    {"tag": "component", "value": "health"},
                    {"tag": "source", "value": "h3c-converted"},
                ],
            },
            {
                "name": "ICMP response time",
                "type": "SIMPLE",
                "key": "icmppingsec",
                "delay": ct,
                "value_type": "FLOAT",
                "units": "s",
                "description": "ICMP ping 响应时间（秒）。",
                "tags": [
                    {"tag": "component", "value": "health"},
                    {"tag": "source", "value": "h3c-converted"},
                ],
            },
        ]
        # 附加华三响应时间阈值
        ping_unit = self._find_unit("ping") or self._find_unit("connection")
        if ping_unit:
            for field in ping_unit.get("fields", []):
                fkey = field.get("field", "")
                if "responseTime" in fkey or "ResponseTime" in fkey:
                    triggers = self._add_threshold_triggers(
                        "icmppingsec", ping_unit["unit"], fkey
                    )
                    if triggers:
                        ping_items[2] = {**ping_items[2], "triggers": triggers}
                    break

        self.items.extend(ping_items)

    # ── TCP Port 探测 ────────────────────────────────────────────────────────

    def _build_tcpport(self) -> None:
        """TCP 端口探测模板。"""
        avail_unit = self._find_unit("AvailableData")
        ct = f"{avail_unit.get('collectTime', 60)}s" if avail_unit else "60s"

        self.items.extend(
            [
                {
                    "name": "TCP port {$TCP_PORT}: 响应状态",
                    "type": "SIMPLE",
                    "key": "net.tcp.service[tcp,,{$TCP_PORT}]",
                    "delay": ct,
                    "value_type": "UNSIGNED",
                    "description": "TCP 端口连通性检测。0=端口不通，1=端口可达。",
                    "valuemap": "Service state",
                    "tags": [
                        {"tag": "component", "value": "health"},
                        {"tag": "source", "value": "h3c-converted"},
                    ],
                    "triggers": [
                        {
                            "name": "{TEMPLATE_NAME}: TCP 端口 {$TCP_PORT} 不可达",
                            "expression": "max(/{TEMPLATE_KEY}/net.tcp.service[tcp,,{$TCP_PORT}],#3)=0",
                            "priority": "AVERAGE",
                            "description": "TCP 端口连续 3 次探测失败。",
                            "tags": [{"tag": "scope", "value": "availability"}],
                        }
                    ],
                },
                {
                    "name": "TCP port {$TCP_PORT}: 响应时间",
                    "type": "SIMPLE",
                    "key": "net.tcp.service.perf[tcp,,{$TCP_PORT}]",
                    "delay": ct,
                    "value_type": "FLOAT",
                    "units": "s",
                    "description": "TCP 端口建立连接所需时间（秒）。0=端口不通。",
                    "tags": [
                        {"tag": "component", "value": "health"},
                        {"tag": "source", "value": "h3c-converted"},
                    ],
                },
            ]
        )
        self.macros.append(
            {
                "macro": "{$TCP_PORT}",
                "value": "80",
                "description": "要监控的 TCP 端口号（请根据实际情况修改）",
            }
        )

    # ── 公共入口 ─────────────────────────────────────────────────────────────

    def build(self) -> str:
        """
        构建并返回 Zabbix 7.0 YAML 字符串。
        """
        h3c_type = self.h3c_type

        # 按类型分派
        if h3c_type == "network":
            self._build_network()
        elif h3c_type in ("linux", "kylin", "kylinos", "uos", "rocky", "suse"):
            self._build_linux_snmp()
        elif h3c_type == "winsvr":
            self._build_windows_snmp()
        elif h3c_type == "brocade":
            self._build_brocade()
        elif h3c_type in ("ping", "pingcmd"):
            self._build_ping()
        elif h3c_type == "tcpport":
            self._build_tcpport()
        else:
            raise ValueError(f"不支持的华三类型: {h3c_type}")

        return self._render_yaml()

    def _render_yaml(self) -> str:
        """将构建好的模板数据渲染为 YAML 字符串"""
        group_uuid = make_uuid(f"group:{self.group}")
        tpl_uuid = make_uuid(f"template:{self.tpl_key}")
        tpl_name_q = _yaml_str(self.tpl_name)
        tpl_key_q = _yaml_str(self.tpl_key)
        group_q = _yaml_str(self.group)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        h3c_id = self.h3c.get("templateId", "")

        lines: list[str] = [
            "zabbix_export:",
            "  version: '7.0'",
            "  template_groups:",
            f"    - uuid: {group_uuid}",
            f"      name: {group_q}",
            "  templates:",
            f"    - uuid: {tpl_uuid}",
            f"      template: {tpl_key_q}",
            f"      name: {tpl_name_q}",
            "      description: |",
            f"        华三监控模板转换（H3C → Zabbix 7.0 SNMP）",
            f"        源模板名称 : {self.h3c_name}",
            f"        源模板 ID  : {h3c_id}",
            f"        华三类型   : {self.h3c_type}",
            f"        转换时间   : {now_str}",
            f"        生成工具   : convert_snmp_templates.py",
            "      groups:",
            f"        - name: {group_q}",
        ]

        # ── items ──
        if self.items:
            lines.append("      items:")
            for item in self.items:
                lines.append(_yaml_item(item, self.tpl_key, self.tpl_name, indent=8))

        # ── discovery_rules ──
        if self.discovery_rules:
            lines.append("      discovery_rules:")
            for lld in self.discovery_rules:
                lines.append(_yaml_lld(lld, self.tpl_key, self.tpl_name, indent=8))

        # ── macros ──
        if self.macros:
            lines.append("      macros:")
            for m in self.macros:
                lines.append(f"        - macro: {_yaml_str(m['macro'])}")
                # macro value 在 Zabbix 中始终是字符串，必须加引号
                macro_val = str(m["value"])
                escaped_val = macro_val.replace("'", "\\'")
                lines.append(f"          value: '{escaped_val}'")
                if m.get("description"):
                    lines.append(
                        f"          description: {_yaml_str(m['description'])}"
                    )

        # ── tags ──
        lines.append("      tags:")
        lines.append("        - tag: source")
        lines.append("          value: h3c-converted")
        lines.append(f"        - tag: h3c-type")
        lines.append(f"          value: {_yaml_str(self.h3c_type)}")

        # ── valuemaps（模板内部，在 tags 之后） ──
        # 每个模板的 valuemap UUID 必须唯一，使用 tpl_key 作为 seed 的一部分
        lines.append("      valuemaps:")
        for vm in _VALUE_MAPS:
            lines.append(_yaml_valuemap(vm, indent=8, uuid_prefix=self.tpl_key))

        return "\n".join(lines) + "\n"


# ══════════════════════════════════════════════════════════════════════════════
# Zabbix API 客户端
# ══════════════════════════════════════════════════════════════════════════════


class ZabbixAPI:
    def __init__(self, url: str, user: str, password: str) -> None:
        self.url = url.rstrip("/") + "/api_jsonrpc.php"
        self.token: str | None = None
        self._login(user, password)

    def _call(self, method: str, params: dict) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        }
        if self.token:
            payload["auth"] = self.token
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.reason}") from e
        if "error" in result:
            err = result["error"]
            raise RuntimeError(
                f"Zabbix API error {err.get('code')}: {err.get('data', err.get('message'))}"
            )
        return result["result"]

    def _login(self, user: str, password: str) -> None:
        self.token = None
        self.token = self._call("user.login", {"username": user, "password": password})

    def ensure_template_group(self, group_name: str) -> str:
        """
        确保模板组存在（不存在则创建）。
        返回 groupid。
        Zabbix 7.0 支持嵌套分组，通过 "/" 分隔父子级。
        """
        # 先查询是否已存在
        result = self._call(
            "templategroup.get",
            {"output": ["groupid", "name"], "filter": {"name": group_name}},
        )
        if result:
            return str(result[0]["groupid"])
        # 不存在则创建
        created = self._call(
            "templategroup.create",
            {"name": group_name},
        )
        gids = created.get("groupids", [])
        if not gids:
            raise RuntimeError(f"创建模板组 '{group_name}' 失败，响应: {created}")
        return str(gids[0])

    def import_template(self, yaml_content: str) -> bool:
        """
        通过 configuration.import 导入 YAML 模板。
        使用完整的 rules 配置确保所有元素正确创建/更新。
        返回 True 表示成功。
        """
        self._call(
            "configuration.import",
            {
                "format": "yaml",
                # Zabbix 7.0 configuration.import rules 字段名经实测验证：
                # - template_groups / templates / items / triggers / graphs → snake_case
                # - discoveryRules / valueMaps / templateDashboards          → camelCase（混用）
                # 以下列表为实测可用的完整集合。
                "rules": {
                    "template_groups": {
                        "createMissing": True,
                        "updateExisting": False,
                    },
                    "templates": {
                        "createMissing": True,
                        "updateExisting": True,
                    },
                    "items": {
                        "createMissing": True,
                        "updateExisting": True,
                        "deleteMissing": False,
                    },
                    "triggers": {
                        "createMissing": True,
                        "updateExisting": True,
                        "deleteMissing": False,
                    },
                    "discoveryRules": {
                        "createMissing": True,
                        "updateExisting": True,
                        "deleteMissing": False,
                    },
                    "valueMaps": {
                        "createMissing": True,
                        "updateExisting": True,
                    },
                    "graphs": {
                        "createMissing": True,
                        "updateExisting": True,
                        "deleteMissing": False,
                    },
                    "templateDashboards": {
                        "createMissing": False,
                        "updateExisting": False,
                        "deleteMissing": False,
                    },
                },
                "source": yaml_content,
            },
        )
        return True

    def template_exists(self, template_name: str) -> bool:
        result = self._call(
            "template.get",
            {"output": ["templateid"], "filter": {"name": template_name}},
        )
        return len(result) > 0


# ══════════════════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════════════════


def load_h3c_templates(h3c_types: set[str]) -> list[dict]:
    """从 details/ 目录加载指定类型的华三模板"""
    templates = []
    if not H3C_DETAILS_DIR.exists():
        print(f"[ERROR] 华三模板目录不存在: {H3C_DETAILS_DIR}", file=sys.stderr)
        sys.exit(1)
    for f in sorted(H3C_DETAILS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text("utf-8"))
            if data.get("type") in h3c_types:
                templates.append(data)
        except Exception as e:
            print(f"  [WARN] 读取 {f.name} 失败: {e}", file=sys.stderr)
    return templates


def convert_all(
    h3c_types: set[str],
    do_import: bool,
    api_url: str,
    api_user: str,
    api_pass: str,
    force: bool = False,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"{'=' * 64}")
    print("华三 SNMP 模板转换器 → Zabbix 7.0 YAML")
    print(f"{'=' * 64}")
    print(f"转换类型: {', '.join(sorted(h3c_types))}")
    print(f"输出目录: {OUTPUT_DIR}")
    if do_import:
        print(f"导入目标: {api_url}")
    print()

    # 加载华三模板
    print("📂 加载华三模板数据...")
    h3c_templates = load_h3c_templates(h3c_types)
    if not h3c_templates:
        print(f"[WARN] 未找到指定类型的华三模板：{h3c_types}")
        return
    print(f"   找到 {len(h3c_templates)} 个待转换模板\n")

    # Zabbix API 连接
    api: ZabbixAPI | None = None
    if do_import:
        print(f"🔌 连接 Zabbix API: {api_url}")
        try:
            api = ZabbixAPI(api_url, api_user, api_pass)
            print("   登录成功\n")
        except Exception as e:
            print(f"[ERROR] 连接 Zabbix 失败: {e}", file=sys.stderr)
            sys.exit(1)

    # 逐模板转换
    success_count = 0
    skip_count = 0
    fail_count = 0
    output_files: list[Path] = []

    for tpl_data in h3c_templates:
        tpl_name_orig = tpl_data.get("name", "unknown")
        tpl_type = tpl_data.get("type", "")
        builder = TemplateBuilder(tpl_data)
        zabbix_tpl_name = builder.tpl_name

        print(f"  ⚙  {tpl_name_orig} ({tpl_type}) → {zabbix_tpl_name}")

        # 生成 YAML
        try:
            yaml_content = builder.build()
        except Exception as e:
            print(f"     ❌ 生成失败: {e}")
            fail_count += 1
            continue

        # 写入文件
        safe_name = (
            builder.tpl_key.replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
            .lower()
        )
        out_file = OUTPUT_DIR / f"{safe_name}.yaml"
        out_file.write_text(yaml_content, encoding="utf-8")
        output_files.append(out_file)

        # 可选导入
        if api is not None:
            if not force and api.template_exists(zabbix_tpl_name):
                print(f"     ⏭  已存在（跳过，使用 --force 强制覆盖）")
                skip_count += 1
                continue
            try:
                # 先确保模板组存在
                try:
                    gid = api.ensure_template_group(builder.group)
                    print(f"     📁 模板组已就绪: {builder.group} (id={gid})")
                except Exception as eg:
                    print(f"     ⚠  创建/确认模板组失败: {eg}，继续尝试导入...")

                api.import_template(yaml_content)
                print(f"     ✅ 导入成功")
                success_count += 1
            except Exception as e:
                print(f"     ❌ 导入失败: {e}")
                fail_count += 1
        else:
            print(f"     📄 已写出: {out_file.name}")
            success_count += 1

    # 汇总
    print(f"\n{'─' * 64}")
    print(f"📊 转换完成:")
    print(f"   成功: {success_count}")
    if skip_count:
        print(f"   跳过: {skip_count}（已存在）")
    if fail_count:
        print(f"   失败: {fail_count}")
    print(f"   输出文件数: {len(output_files)}")
    print(f"   输出目录: {OUTPUT_DIR}")

    if output_files:
        print(f"\n生成文件列表:")
        for f in output_files:
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name}  ({size_kb:.1f} KB)")


def list_generated() -> None:
    """列出已生成的 YAML 文件"""
    if not OUTPUT_DIR.exists():
        print(f"[INFO] 输出目录不存在: {OUTPUT_DIR}")
        print("请先运行转换命令。")
        return
    files = sorted(OUTPUT_DIR.glob("*.yaml"))
    if not files:
        print(f"[INFO] {OUTPUT_DIR} 中没有找到 YAML 文件")
        return
    print(f"已生成的 Zabbix 模板 YAML 文件（{OUTPUT_DIR}）:")
    total_size = 0
    for f in files:
        size_kb = f.stat().st_size / 1024
        total_size += f.stat().st_size
        print(f"  {f.name:<60} {size_kb:>8.1f} KB")
    print(f"\n合计 {len(files)} 个文件，{total_size / 1024:.1f} KB")


# ══════════════════════════════════════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════════════════════════════════════


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="convert_snmp_templates.py",
        description=textwrap.dedent(
            """\
            将华三监控模板（SNMP 支持的类型）转换为 Zabbix 7.0 YAML 模板，
            并可选择通过 Zabbix API 直接导入。

            支持的华三类型：
              network  - 网络设备（通用 SNMP）
              linux    - Linux（UCD-SNMP-MIB）
              kylin    - 中标麒麟（同 Linux）
              kylinos  - 银河麒麟（同 Linux）
              uos      - UOS（同 Linux）
              rocky    - 凝思磐石（同 Linux）
              suse     - Suse（同 Linux）
              winsvr   - Windows（HOST-RESOURCES-MIB）
              brocade  - Brocade FC（SW-MIB）
              ping     - 远程 Ping 探测（ICMP Simple Check）
              pingcmd  - 本地 Ping 探测（ICMP Simple Check）
              tcpport  - TCP 端口探测（Simple Check）
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--types",
        default=",".join(sorted(SNMP_SUPPORTED_TYPES)),
        help="要转换的华三类型（逗号分隔，默认全部）",
    )
    parser.add_argument(
        "--import",
        dest="do_import",
        action="store_true",
        default=False,
        help="转换后通过 Zabbix API 导入",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_API_URL,
        help=f"Zabbix Web URL（默认 {DEFAULT_API_URL}）",
    )
    parser.add_argument(
        "--user",
        default=DEFAULT_USER,
        help=f"Zabbix 用户名（默认 {DEFAULT_USER}）",
    )
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help="Zabbix 密码",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="强制覆盖 Zabbix 中已存在的模板",
    )
    parser.add_argument(
        "--list",
        dest="list_files",
        action="store_true",
        default=False,
        help="列出已生成的 YAML 文件",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=f"YAML 输出目录（默认 {OUTPUT_DIR}）",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # 覆盖输出目录
    global OUTPUT_DIR
    if args.output_dir:
        OUTPUT_DIR = Path(args.output_dir)

    if args.list_files:
        list_generated()
        return 0

    # 解析类型列表
    raw_types = [t.strip() for t in args.types.split(",") if t.strip()]
    unknown = [t for t in raw_types if t not in SNMP_SUPPORTED_TYPES]
    if unknown:
        print(f"[ERROR] 不支持的类型: {unknown}", file=sys.stderr)
        print(f"       支持的类型: {sorted(SNMP_SUPPORTED_TYPES)}", file=sys.stderr)
        return 1

    convert_all(
        h3c_types=set(raw_types),
        do_import=args.do_import,
        api_url=args.url,
        api_user=args.user,
        api_pass=args.password,
        force=args.force,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
