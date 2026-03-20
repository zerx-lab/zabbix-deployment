#!/usr/bin/env python3
"""
分析 Zabbix 现有模板的 Items，建立与华三监控模板的映射关系数据。
输出结构化 JSON 供后续转换使用。
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

# ── 常量 ──────────────────────────────────────────────────────────────────────

ITEM_TYPE_NAMES = {
    "0": "ZABBIX_PASSIVE",
    "2": "TRAP",
    "3": "SIMPLE",
    "5": "INTERNAL",
    "7": "ZABBIX_ACTIVE",
    "10": "EXTERNAL",
    "11": "ODBC",
    "12": "IPMI",
    "13": "SSH",
    "14": "TELNET",
    "15": "CALCULATED",
    "16": "JMX",
    "17": "SNMP_TRAP",
    "18": "DEPENDENT",
    "19": "HTTP_AGENT",
    "20": "SNMP_AGENT",
    "21": "SCRIPT",
    "22": "BROWSER",
}

VALUE_TYPE_NAMES = {
    "0": "FLOAT",
    "1": "CHAR",
    "2": "LOG",
    "3": "UNSIGNED",
    "4": "TEXT",
    "5": "BINARY",
}

# 目标模板列表：name -> H3C type key 映射
# 用于将 Zabbix 模板与华三模板类型对应
TEMPLATE_TO_H3C = {
    # OS 类
    "Linux by Zabbix agent": "linux",
    "Linux by Zabbix agent active": "linux",
    "Linux by SNMP": "linux",
    "Windows by Zabbix agent": "winsvr",
    "Windows by Zabbix agent active": "winsvr",
    "Windows by SNMP": "winsvr",
    "AIX by Zabbix agent": "aix",
    "FreeBSD by Zabbix agent": "freebsd",
    "HP-UX by Zabbix agent": "hpux",
    "Solaris by Zabbix agent": "solaris",
    "macOS by Zabbix agent": "macos",
    # 网络设备
    "Network Generic Device by SNMP": "network",
    "ICMP Ping": "ping",
    "Brocade FC by SNMP": "brocade",
    "HP Comware HH3C by SNMP": "network",
    "Huawei VRP by SNMP": "network",
    # 数据库
    "MySQL by Zabbix agent 2": "mysql8",
    "MySQL by Zabbix agent": "mysql",
    "MySQL by ODBC": "mysql",
    "PostgreSQL by Zabbix agent 2": "psql",
    "PostgreSQL by Zabbix agent": "psql",
    "Redis by Zabbix agent 2": "redis",
    "MongoDB node by Zabbix agent 2": "mongo",
    "Elasticsearch Cluster by HTTP": "es",
    "MSSQL by Zabbix agent 2": "mssql",
    "Oracle by Zabbix agent 2": "oracle",
    "Oracle by ODBC": "oracle",
    # 应用/中间件
    "Apache Tomcat by JMX": "tomcat",
    "Nginx by HTTP": "nginx",
    "Nginx by Zabbix agent": "nginx",
    "Apache by HTTP": "apache",
    "RabbitMQ node by HTTP": "rabbit",
    "Apache Kafka by JMX": "kafka",
    "Zookeeper by HTTP": "zk",
    "Memcached by Zabbix agent 2": "memch",
    "IIS by Zabbix agent": "iis",
    "PHP-FPM by HTTP": "php",
    "Hadoop by HTTP": "hadoop",
    "Etcd by HTTP": "etcd",
    "Generic Java JMX": "jrt",
    # 容器/虚拟化
    "Docker by Zabbix agent 2": "docker",
    "Kubernetes cluster state by HTTP": "k8s",
    "Kubernetes nodes by HTTP": "k8s",
    "Kubernetes API server by HTTP": "kubemaster",
    "VMware": "vcenter",
    "VMware Guest": "vmware",
    "VMware Hypervisor": "vmware",
}

# H3C 字段 key -> Zabbix item key 的精确映射（手工整理核心映射）
# 格式: "h3c_type.unit.field" -> { zabbix_key, type, proto }
H3C_TO_ZABBIX_KEY_MAP = {
    # ── Linux ──
    "linux.cpu.CpuUtilization": {"key": "system.cpu.util", "proto": False},
    "linux.cpuinfo_stat.IdlePercentage": {
        "key": "system.cpu.util[,idle]",
        "proto": False,
    },
    "linux.cpuinfo_stat.IOwaitPercentage": {
        "key": "system.cpu.util[,iowait]",
        "proto": False,
    },
    "linux.cpuinfo_stat.UserPercentage": {
        "key": "system.cpu.util[,user]",
        "proto": False,
    },
    "linux.cpuinfo_stat.SystemPercentage": {
        "key": "system.cpu.util[,system]",
        "proto": False,
    },
    "linux.cpuinfo_stat.NicePercentage": {
        "key": "system.cpu.util[,nice]",
        "proto": False,
    },
    "linux.memory.MemTotal": {"key": "vm.memory.size[total]", "proto": False},
    "linux.memory.MemFree": {"key": "vm.memory.size[free]", "proto": False},
    "linux.memory.MemUsed": {"key": "vm.memory.size[used]", "proto": False},
    "linux.memory.MemUtilization": {"key": "vm.memory.size[pused]", "proto": False},
    "linux.memory.SwapTotal": {"key": "system.swap.size[,total]", "proto": False},
    "linux.memory.SwapFree": {"key": "system.swap.size[,free]", "proto": False},
    "linux.memory.SwapUtilization": {"key": "system.swap.size[,pused]", "proto": False},
    "linux.load.CpuLoad1": {"key": "system.cpu.load[all,avg1]", "proto": False},
    "linux.load.CpuLoad5": {"key": "system.cpu.load[all,avg5]", "proto": False},
    "linux.load.CpuLoad15": {"key": "system.cpu.load[all,avg15]", "proto": False},
    "linux.filesystem.TotalSpace": {
        "key": "vfs.fs.size[{#FSNAME},total]",
        "proto": True,
    },
    "linux.filesystem.FreeSpace": {"key": "vfs.fs.size[{#FSNAME},free]", "proto": True},
    "linux.filesystem.UsedSpace": {"key": "vfs.fs.size[{#FSNAME},used]", "proto": True},
    "linux.filesystem.Utilization": {
        "key": "vfs.fs.size[{#FSNAME},pused]",
        "proto": True,
    },
    "linux.inode.InodesUsed": {"key": "vfs.fs.inode[{#FSNAME},pused]", "proto": True},
    "linux.interface.rxPerSec": {"key": "net.if.in[{#IFNAME}]", "proto": True},
    "linux.interface.txPerSec": {"key": "net.if.out[{#IFNAME}]", "proto": True},
    "linux.interface.rxErrors": {"key": "net.if.in[{#IFNAME},errors]", "proto": True},
    "linux.interface.txErrors": {"key": "net.if.out[{#IFNAME},errors]", "proto": True},
    "linux.ntp.NtpOffset": {"key": "system.localtime", "proto": False},
    # ── Windows ──
    "winsvr.cpu.CpuUtilization": {"key": "system.cpu.util", "proto": False},
    "winsvr.memory.MemTotal": {"key": "vm.memory.size[total]", "proto": False},
    "winsvr.memory.MemUtilization": {"key": "vm.memory.size[pused]", "proto": False},
    "winsvr.disk.DiskUtilization": {
        "key": "vfs.fs.size[{#FSNAME},pused]",
        "proto": True,
    },
    "winsvr.disk.DiskFreeSpace": {"key": "vfs.fs.size[{#FSNAME},free]", "proto": True},
    "winsvr.load.CpuLoad1": {"key": "system.cpu.load[all,avg1]", "proto": False},
    "winsvr.interface.rxPerSec": {"key": "net.if.in[{#IFNAME}]", "proto": True},
    "winsvr.interface.txPerSec": {"key": "net.if.out[{#IFNAME}]", "proto": True},
    # ── Network (SNMP) ──
    "network.cpu.cpuUtilization": {"key": "system.cpu.util", "proto": False},
    "network.memory.memUtilization": {"key": "vm.memory.size[pused]", "proto": False},
    "network.interface.rxPerSec": {"key": "net.if.in[{#SNMPINDEX}]", "proto": True},
    "network.interface.txPerSec": {"key": "net.if.out[{#SNMPINDEX}]", "proto": True},
    "network.interface.rxUtilization": {
        "key": "net.if.in[{#SNMPINDEX}]",
        "proto": True,
    },
    "network.interface.txUtilization": {
        "key": "net.if.out[{#SNMPINDEX}]",
        "proto": True,
    },
    # ── MySQL ──
    "mysql8.status.Uptime": {"key": "mysql.status[Uptime]", "proto": False},
    "mysql8.status.Threads_connected": {
        "key": "mysql.status[Threads_connected]",
        "proto": False,
    },
    "mysql8.status.Queries": {"key": "mysql.status[Queries]", "proto": False},
    "mysql8.status.Slow_queries": {"key": "mysql.status[Slow_queries]", "proto": False},
    "mysql8.status.Bytes_received": {
        "key": "mysql.status[Bytes_received]",
        "proto": False,
    },
    "mysql8.status.Bytes_sent": {"key": "mysql.status[Bytes_sent]", "proto": False},
    "mysql8.status.Innodb_buffer_pool_read_requests": {
        "key": "mysql.status[Innodb_buffer_pool_read_requests]",
        "proto": False,
    },
    "mysql8.status.Innodb_buffer_pool_reads": {
        "key": "mysql.status[Innodb_buffer_pool_reads]",
        "proto": False,
    },
    "mysql.status.Uptime": {"key": "mysql.status[Uptime]", "proto": False},
    "mysql.status.Threads_connected": {
        "key": "mysql.status[Threads_connected]",
        "proto": False,
    },
    # ── PostgreSQL ──
    "psql.conn.numConnections": {"key": "pgsql.connections", "proto": False},
    "psql.conn.maxConnections": {"key": "pgsql.max_connections", "proto": False},
    "psql.status.uptime": {"key": "pgsql.uptime", "proto": False},
    "psql.database.dbSize": {"key": "pgsql.db.size[{#DBNAME}]", "proto": True},
    # ── Redis ──
    "redis.server.redis_version": {
        "key": "redis.info[Server,redis_version]",
        "proto": False,
    },
    "redis.server.uptime_in_seconds": {
        "key": "redis.info[Server,uptime_in_seconds]",
        "proto": False,
    },
    "redis.memory.used_memory": {
        "key": "redis.info[Memory,used_memory]",
        "proto": False,
    },
    "redis.memory.used_memory_rss": {
        "key": "redis.info[Memory,used_memory_rss]",
        "proto": False,
    },
    "redis.clients.connected_clients": {
        "key": "redis.info[Clients,connected_clients]",
        "proto": False,
    },
    "redis.clients.blocked_clients": {
        "key": "redis.info[Clients,blocked_clients]",
        "proto": False,
    },
    "redis.stats.total_commands_processed": {
        "key": "redis.info[Stats,total_commands_processed]",
        "proto": False,
    },
    "redis.stats.total_connections_received": {
        "key": "redis.info[Stats,total_connections_received]",
        "proto": False,
    },
    # ── Nginx ──
    "nginx.status.active": {"key": "nginx.active_connections", "proto": False},
    "nginx.status.requests": {"key": "nginx.requests.total", "proto": False},
    "nginx.status.reading": {"key": "nginx.reading", "proto": False},
    "nginx.status.writing": {"key": "nginx.writing", "proto": False},
    "nginx.status.waiting": {"key": "nginx.waiting", "proto": False},
    # ── Docker ──
    "docker.container.Status": {
        "key": "docker.container_info[{#NAME},State,Status]",
        "proto": True,
    },
    "docker.container.Running": {
        "key": "docker.container_info[{#NAME},State,Running]",
        "proto": True,
    },
    "docker.info.Containers": {"key": "docker.info[Containers]", "proto": False},
    "docker.info.ContainersRunning": {
        "key": "docker.info[ContainersRunning]",
        "proto": False,
    },
    "docker.info.ContainersPaused": {
        "key": "docker.info[ContainersPaused]",
        "proto": False,
    },
    "docker.info.ContainersStopped": {
        "key": "docker.info[ContainersStopped]",
        "proto": False,
    },
    "docker.info.Images": {"key": "docker.info[Images]", "proto": False},
    # ── Ping ──
    "ping.ping.responseTime": {"key": "icmppingsec", "proto": False},
    "ping.ping.packetLoss": {"key": "icmppingloss", "proto": False},
    "general.AvailableData.AvailabilityData": {"key": "icmpping", "proto": False},
    # ── Zookeeper ──
    "zk.zk.zk_avg_latency": {"key": "zookeeper.avg_latency", "proto": False},
    "zk.zk.zk_outstanding_requests": {
        "key": "zookeeper.outstanding_requests",
        "proto": False,
    },
    "zk.zk.zk_watch_count": {"key": "zookeeper.watch_count", "proto": False},
    "zk.zk.zk_server_state": {"key": "zookeeper.server_state", "proto": False},
    # ── Elasticsearch ──
    "es.cluster.cluster_status": {
        "key": "es.nodes.stats[nodes.{#NODE_ID}.jvm.mem.heap_used_percent]",
        "proto": False,
    },
    # ── Etcd ──
    "etcd.health.health": {"key": "etcd.health", "proto": False},
}

# ── 华三模板类型到 Zabbix 模板的映射（同采集方式归组）──────────────────────────
H3C_TYPE_TO_ZABBIX_TEMPLATE = {
    "linux": ["Linux by Zabbix agent", "Linux by SNMP"],
    "kylin": ["Linux by Zabbix agent"],
    "kylinos": ["Linux by Zabbix agent"],
    "uos": ["Linux by Zabbix agent"],
    "rocky": ["Linux by Zabbix agent"],
    "suse": ["Linux by Zabbix agent"],
    "winsvr": ["Windows by Zabbix agent"],
    "aix": ["AIX by Zabbix agent"],
    "freebsd": ["FreeBSD by Zabbix agent"],
    "hpux": ["HP-UX by Zabbix agent"],
    "solaris": ["Solaris by Zabbix agent"],
    "macos": ["macOS by Zabbix agent"],
    "network": ["Network Generic Device by SNMP"],
    "ping": ["ICMP Ping"],
    "pingcmd": ["ICMP Ping"],
    "brocade": ["Brocade FC by SNMP"],
    "mysql": ["MySQL by Zabbix agent 2", "MySQL by Zabbix agent"],
    "mysql8": ["MySQL by Zabbix agent 2"],
    "psql": ["PostgreSQL by Zabbix agent 2", "PostgreSQL by Zabbix agent"],
    "redis": ["Redis by Zabbix agent 2"],
    "mongo": ["MongoDB node by Zabbix agent 2"],
    "es": ["Elasticsearch Cluster by HTTP"],
    "mssql": ["MSSQL by Zabbix agent 2"],
    "oracle": ["Oracle by Zabbix agent 2"],
    "memch": ["Memcached by Zabbix agent 2"],
    "nginx": ["Nginx by HTTP", "Nginx by Zabbix agent"],
    "apache": ["Apache by HTTP"],
    "tomcat": ["Apache Tomcat by JMX"],
    "rabbit": ["RabbitMQ node by HTTP"],
    "kafka": ["Apache Kafka by JMX"],
    "zk": ["Zookeeper by HTTP"],
    "iis": ["IIS by Zabbix agent"],
    "php": ["PHP-FPM by HTTP"],
    "hadoop": ["Hadoop by HTTP"],
    "etcd": ["Etcd by HTTP"],
    "jrt": ["Generic Java JMX"],
    "docker": ["Docker by Zabbix agent 2"],
    "k8s": ["Kubernetes cluster state by HTTP", "Kubernetes nodes by HTTP"],
    "kubemaster": ["Kubernetes API server by HTTP"],
    "vcenter": ["VMware"],
    "vmware": ["VMware Guest", "VMware Hypervisor"],
}


def load_h3c_templates(details_dir: Path) -> list[dict]:
    """加载所有华三模板 JSON 文件"""
    templates = []
    for json_file in sorted(details_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            templates.append(data)
        except Exception as e:
            print(f"  [WARN] 加载 {json_file.name} 失败: {e}", file=sys.stderr)
    return templates


def build_zabbix_item_index(items: list[dict], prototypes: list[dict]) -> dict:
    """
    构建 Zabbix item 索引: key -> item 信息
    返回: { "item_key": {name, type, value_type, units, is_prototype} }
    """
    index = {}
    for item in items:
        key = item["key_"]
        if key not in index:
            index[key] = {
                "name": item["name"],
                "type": ITEM_TYPE_NAMES.get(item["type"], item["type"]),
                "value_type": VALUE_TYPE_NAMES.get(
                    item["value_type"], item["value_type"]
                ),
                "units": item.get("units", "") or "",
                "is_prototype": False,
                "description": (item.get("description") or "")[:200],
            }
    for proto in prototypes:
        key = proto["key_"]
        if key not in index:
            index[key] = {
                "name": proto["name"],
                "type": ITEM_TYPE_NAMES.get(proto["type"], proto["type"]),
                "value_type": VALUE_TYPE_NAMES.get(
                    proto["value_type"], proto["value_type"]
                ),
                "units": proto.get("units", "") or "",
                "is_prototype": True,
                "description": (proto.get("description") or "")[:200],
            }
    return index


def match_h3c_field_to_zabbix(
    h3c_type: str,
    unit_key: str,
    field_key: str,
    field_name_zh: str,
    field_unit: str,
    zabbix_item_index: dict,
) -> dict | None:
    """
    尝试将华三字段映射到 Zabbix item key。
    返回匹配信息 dict，或 None（无法匹配）。
    """
    # 1. 精确映射表查找
    lookup_key = f"{h3c_type}.{unit_key}.{field_key}"
    if lookup_key in H3C_TO_ZABBIX_KEY_MAP:
        mapping = H3C_TO_ZABBIX_KEY_MAP[lookup_key]
        zabbix_key = mapping["key"]
        is_proto = mapping["proto"]
        # 查找 Zabbix item 是否存在
        zabbix_info = zabbix_item_index.get(zabbix_key)
        return {
            "match_type": "exact_map",
            "zabbix_key": zabbix_key,
            "is_prototype": is_proto,
            "zabbix_name": zabbix_info["name"]
            if zabbix_info
            else "(key defined, not in current templates)",
            "zabbix_type": zabbix_info["type"] if zabbix_info else "UNKNOWN",
            "zabbix_units": zabbix_info["units"] if zabbix_info else "",
            "confidence": "high",
        }

    # 2. 通用可用性字段
    if unit_key == "AvailableData" and field_key == "AvailabilityData":
        return {
            "match_type": "exact_map",
            "zabbix_key": "icmpping",
            "is_prototype": False,
            "zabbix_name": "ICMP ping",
            "zabbix_type": "SIMPLE",
            "zabbix_units": "",
            "confidence": "high",
        }

    # 3. 关键字模糊匹配（基于字段名称推断）
    name_lower = field_name_zh.lower()
    field_lower = field_key.lower()

    # CPU 利用率
    if ("cpu" in field_lower or "cpu" in name_lower) and (
        "util" in field_lower
        or "utiliz" in field_lower
        or "usage" in field_lower
        or "利用率" in field_name_zh
    ):
        return {
            "match_type": "keyword_infer",
            "zabbix_key": "system.cpu.util",
            "is_prototype": False,
            "zabbix_name": "CPU utilization",
            "zabbix_type": "ZABBIX_PASSIVE",
            "zabbix_units": "%",
            "confidence": "medium",
        }

    # 内存利用率
    if (
        "mem" in field_lower or "memory" in field_lower or "内存" in field_name_zh
    ) and (
        "util" in field_lower
        or "pused" in field_lower
        or "利用率" in field_name_zh
        or "usage" in field_lower
    ):
        return {
            "match_type": "keyword_infer",
            "zabbix_key": "vm.memory.size[pused]",
            "is_prototype": False,
            "zabbix_name": "Memory utilization",
            "zabbix_type": "ZABBIX_PASSIVE",
            "zabbix_units": "%",
            "confidence": "medium",
        }

    # 磁盘/文件系统利用率
    if (
        "disk" in field_lower
        or "filesystem" in field_lower
        or "磁盘" in field_name_zh
        or "文件系统" in field_name_zh
    ) and (
        "util" in field_lower
        or "pused" in field_lower
        or "利用率" in field_name_zh
        or "usage" in field_lower
    ):
        return {
            "match_type": "keyword_infer",
            "zabbix_key": "vfs.fs.size[{#FSNAME},pused]",
            "is_prototype": True,
            "zabbix_name": "Filesystem utilization",
            "zabbix_type": "ZABBIX_PASSIVE",
            "zabbix_units": "%",
            "confidence": "medium",
        }

    # 网络接口接收
    if (
        "rx" in field_lower or "receive" in field_lower or "接收" in field_name_zh
    ) and ("persec" in field_lower or "rate" in field_lower or "速率" in field_name_zh):
        return {
            "match_type": "keyword_infer",
            "zabbix_key": "net.if.in[{#IFNAME}]",
            "is_prototype": True,
            "zabbix_name": "Interface receive rate",
            "zabbix_type": "ZABBIX_PASSIVE",
            "zabbix_units": "bps",
            "confidence": "medium",
        }

    # 网络接口发送
    if (
        "tx" in field_lower or "transmit" in field_lower or "发送" in field_name_zh
    ) and ("persec" in field_lower or "rate" in field_lower or "速率" in field_name_zh):
        return {
            "match_type": "keyword_infer",
            "zabbix_key": "net.if.out[{#IFNAME}]",
            "is_prototype": True,
            "zabbix_name": "Interface transmit rate",
            "zabbix_type": "ZABBIX_PASSIVE",
            "zabbix_units": "bps",
            "confidence": "medium",
        }

    # 系统负载
    if "load" in field_lower or "负载" in field_name_zh:
        suffix = (
            "avg1" if "1" in field_lower else "avg5" if "5" in field_lower else "avg15"
        )
        return {
            "match_type": "keyword_infer",
            "zabbix_key": f"system.cpu.load[all,{suffix}]",
            "is_prototype": False,
            "zabbix_name": f"Load average ({suffix})",
            "zabbix_type": "ZABBIX_PASSIVE",
            "zabbix_units": "",
            "confidence": "medium",
        }

    # Ping 响应时间
    if "responsetime" in field_lower or "响应时间" in field_name_zh:
        if h3c_type in ("ping", "pingcmd", "general"):
            return {
                "match_type": "keyword_infer",
                "zabbix_key": "icmppingsec",
                "is_prototype": False,
                "zabbix_name": "ICMP ping response time",
                "zabbix_type": "SIMPLE",
                "zabbix_units": "s",
                "confidence": "medium",
            }

    return None


def analyze_h3c_template(
    tpl: dict,
    zabbix_item_index: dict,
    zabbix_templates_by_h3c: dict,
) -> dict:
    """
    分析单个华三模板，返回分析结果。
    """
    h3c_type = tpl.get("type", "")
    tpl_name = tpl.get("name", "")
    unit_list = tpl.get("unitList", [])

    result = {
        "h3c_template_id": str(tpl.get("templateId", "")),
        "h3c_type": h3c_type,
        "h3c_name": tpl_name,
        "h3c_name_en": tpl.get("nameEn", ""),
        "zabbix_templates": zabbix_templates_by_h3c.get(h3c_type, []),
        "convertible": False,
        "units": [],
        "stats": {
            "total_units": 0,
            "total_fields": 0,
            "matched_fields": 0,
            "high_confidence": 0,
            "medium_confidence": 0,
            "unmatched_fields": 0,
        },
    }

    for unit in unit_list:
        unit_key = unit.get("unit", "")
        unit_name_zh = unit.get("nameZh", "")
        data_type = unit.get("dataType", "")
        scope = unit.get("scope", 3)
        collect_time = unit.get("collectTime", 300)
        fields_raw = unit.get("fields", [])

        unit_result = {
            "unit_key": unit_key,
            "unit_name_zh": unit_name_zh,
            "unit_name_en": unit.get("nameEn", ""),
            "data_type": data_type,
            "scope": scope,
            "collect_time": collect_time,
            "is_lld": scope == 1 and data_type == "table",
            "fields": [],
        }

        result["stats"]["total_units"] += 1

        for field in fields_raw:
            field_key = field.get("field", "")
            field_name_zh = field.get("nameZh", "")
            field_unit = field.get("fieldUnit") or ""
            value_type = field.get("valueType", 0)
            alarm_inst = field.get("alarmInst", 0)
            enable_threshold = field.get("enableThreshold", True)

            result["stats"]["total_fields"] += 1

            # 尝试映射
            match = match_h3c_field_to_zabbix(
                h3c_type,
                unit_key,
                field_key,
                field_name_zh,
                field_unit,
                zabbix_item_index,
            )

            field_result = {
                "field_key": field_key,
                "field_name_zh": field_name_zh,
                "field_name_en": field.get("nameEn", ""),
                "field_unit": field_unit,
                "value_type": "string" if value_type == 1 else "numeric",
                "alarm_inst": alarm_inst,  # -1=实例标识字段, 0=普通, 1+=引用第N个标识
                "enable_threshold": enable_threshold,
                "explain_zh": (field.get("explainZh") or "")[:300],
                "zabbix_match": match,
            }

            if match:
                result["stats"]["matched_fields"] += 1
                if match["confidence"] == "high":
                    result["stats"]["high_confidence"] += 1
                else:
                    result["stats"]["medium_confidence"] += 1
            else:
                result["stats"]["unmatched_fields"] += 1

            unit_result["fields"].append(field_result)

        result["units"].append(unit_result)

    # 判断模板是否可转换
    total = result["stats"]["total_fields"]
    matched = result["stats"]["matched_fields"]
    has_zabbix_tpl = bool(result["zabbix_templates"])
    match_ratio = matched / total if total > 0 else 0

    result["convertible"] = has_zabbix_tpl and matched > 0
    result["match_ratio"] = round(match_ratio, 3)
    result["conversion_tier"] = (
        "full"
        if has_zabbix_tpl and match_ratio >= 0.6
        else "partial"
        if has_zabbix_tpl and matched > 0
        else "skeleton"
        if not has_zabbix_tpl and matched > 0
        else "none"
    )

    return result


def generate_conversion_report(results: list[dict]) -> dict:
    """生成汇总报告"""
    tier_counts = defaultdict(int)
    by_category = defaultdict(list)

    for r in results:
        tier_counts[r["conversion_tier"]] += 1
        by_category[r["h3c_type"]].append(
            {
                "name": r["h3c_name"],
                "tier": r["conversion_tier"],
                "match_ratio": r["match_ratio"],
                "total_fields": r["stats"]["total_fields"],
                "matched_fields": r["stats"]["matched_fields"],
                "zabbix_templates": r["zabbix_templates"],
            }
        )

    return {
        "summary": {
            "total_templates": len(results),
            "full_conversion": tier_counts["full"],
            "partial_conversion": tier_counts["partial"],
            "skeleton_only": tier_counts["skeleton"],
            "no_conversion": tier_counts["none"],
        },
        "by_h3c_type": dict(by_category),
        "tier_description": {
            "full": "Zabbix 有对应模板且字段匹配率 >= 60%，可直接生成可用模板",
            "partial": "Zabbix 有对应模板但字段匹配率 < 60%，可生成部分模板",
            "skeleton": "Zabbix 无对应模板但有字段匹配，仅能生成框架（需手动补充采集方式）",
            "none": "Zabbix 无法对应，华三私有采集，暂不支持转换",
        },
    }


def main():
    # 路径配置
    project_root = Path(__file__).parent.parent
    details_dir = project_root / "output" / "monitor-templates" / "details"
    output_dir = project_root / "output" / "zabbix-mapping"
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. 加载华三模板 ───────────────────────────────────────────────────────
    print("📂 加载华三监控模板数据...")
    h3c_templates = load_h3c_templates(details_dir)
    print(f"   共加载 {len(h3c_templates)} 个华三模板")

    # ── 2. 通过 Zabbix API 获取 items ────────────────────────────────────────
    print("\n🔌 连接 Zabbix API...")
    import urllib.request

    api_url = "http://localhost:8080/api_jsonrpc.php"
    headers = {"Content-Type": "application/json"}

    def zabbix_api(method: str, params: dict, auth: str | None = None) -> dict:
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        if auth:
            payload["auth"] = auth
        req = urllib.request.Request(
            api_url,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    # 登录
    login_resp = zabbix_api("user.login", {"username": "Admin", "password": "zabbix"})
    token = login_resp["result"]
    print(f"   登录成功，token: {token[:16]}...")

    # 获取目标模板列表
    target_template_names = list(TEMPLATE_TO_H3C.keys())
    tpl_resp = zabbix_api(
        "template.get",
        {
            "output": ["templateid", "name"],
            "filter": {"name": target_template_names},
        },
        auth=token,
    )
    zabbix_templates_raw = tpl_resp["result"]
    template_id_map = {t["name"]: t["templateid"] for t in zabbix_templates_raw}
    template_ids = [t["templateid"] for t in zabbix_templates_raw]
    print(
        f"   找到目标模板 {len(zabbix_templates_raw)} 个（共请求 {len(target_template_names)} 个）"
    )

    # 未找到的模板
    not_found = [n for n in target_template_names if n not in template_id_map]
    if not_found:
        print(f"   ⚠️  以下模板在 Zabbix 中不存在: {not_found}")

    # 获取 items
    print("\n📥 获取 Zabbix Items...")
    items_resp = zabbix_api(
        "item.get",
        {
            "output": [
                "itemid",
                "name",
                "key_",
                "type",
                "value_type",
                "units",
                "delay",
                "description",
                "hostid",
            ],
            "templateids": template_ids,
            "inherited": False,
            "limit": 10000,
        },
        auth=token,
    )
    all_items = items_resp["result"]
    print(f"   获取 Items: {len(all_items)} 条")

    # 获取 item prototypes
    print("📥 获取 Zabbix Item Prototypes (LLD)...")
    proto_resp = zabbix_api(
        "itemprototype.get",
        {
            "output": [
                "itemid",
                "name",
                "key_",
                "type",
                "value_type",
                "units",
                "delay",
                "description",
                "hostid",
            ],
            "templateids": template_ids,
            "inherited": False,
            "limit": 10000,
        },
        auth=token,
    )
    all_prototypes = proto_resp["result"]
    print(f"   获取 Item Prototypes: {len(all_prototypes)} 条")

    # ── 3. 构建索引 ───────────────────────────────────────────────────────────
    print("\n🔧 构建 Zabbix items 索引...")
    zabbix_item_index = build_zabbix_item_index(all_items, all_prototypes)
    print(f"   唯一 item key 数量: {len(zabbix_item_index)}")

    # 构建 hostid -> template_name 映射（用于后续输出）
    hostid_to_name = {v: k for k, v in template_id_map.items()}

    # 为 items 添加 template_name
    items_with_tpl = []
    for item in all_items:
        tpl_name = hostid_to_name.get(item["hostid"], f"unknown_{item['hostid']}")
        items_with_tpl.append(
            {
                "template_name": tpl_name,
                "h3c_type": TEMPLATE_TO_H3C.get(tpl_name, ""),
                "key": item["key_"],
                "name": item["name"],
                "type": ITEM_TYPE_NAMES.get(item["type"], item["type"]),
                "value_type": VALUE_TYPE_NAMES.get(
                    item["value_type"], item["value_type"]
                ),
                "units": item.get("units", "") or "",
                "delay": item.get("delay", ""),
                "is_prototype": False,
            }
        )
    for proto in all_prototypes:
        tpl_name = hostid_to_name.get(proto["hostid"], f"unknown_{proto['hostid']}")
        items_with_tpl.append(
            {
                "template_name": tpl_name,
                "h3c_type": TEMPLATE_TO_H3C.get(tpl_name, ""),
                "key": proto["key_"],
                "name": proto["name"],
                "type": ITEM_TYPE_NAMES.get(proto["type"], proto["type"]),
                "value_type": VALUE_TYPE_NAMES.get(
                    proto["value_type"], proto["value_type"]
                ),
                "units": proto.get("units", "") or "",
                "delay": proto.get("delay", ""),
                "is_prototype": True,
            }
        )

    # ── 4. 分析华三模板 ───────────────────────────────────────────────────────
    print("\n🔍 分析华三模板字段映射...")
    analysis_results = []
    convertible_count = 0

    for tpl in h3c_templates:
        result = analyze_h3c_template(
            tpl, zabbix_item_index, H3C_TYPE_TO_ZABBIX_TEMPLATE
        )
        analysis_results.append(result)
        if result["convertible"]:
            convertible_count += 1

    print(f"   分析完成: {len(analysis_results)} 个模板")
    print(f"   可转换模板: {convertible_count} 个")

    # ── 5. 生成报告 ───────────────────────────────────────────────────────────
    report = generate_conversion_report(analysis_results)

    print(f"\n📊 转换分级汇总:")
    for tier, count in [
        ("full", report["summary"]["full_conversion"]),
        ("partial", report["summary"]["partial_conversion"]),
        ("skeleton", report["summary"]["skeleton_only"]),
        ("none", report["summary"]["no_conversion"]),
    ]:
        desc = report["tier_description"][tier]
        print(f"   {tier:8} ({count:3}): {desc}")

    # ── 6. 输出文件 ───────────────────────────────────────────────────────────
    print("\n💾 输出分析结果...")

    # 6-1: Zabbix items 汇总（按模板分类）
    zabbix_items_output = output_dir / "zabbix_items_index.json"
    zabbix_items_output.write_text(
        json.dumps(
            {
                "generated_at": __import__("datetime").datetime.now().isoformat(),
                "total_items": len(items_with_tpl),
                "total_unique_keys": len(zabbix_item_index),
                "templates_found": len(zabbix_templates_raw),
                "items_by_template": _group_items_by_template(items_with_tpl),
                "all_items": items_with_tpl,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"   ✅ {zabbix_items_output}")

    # 6-2: 华三->Zabbix 字段映射分析（完整）
    full_analysis_output = output_dir / "h3c_to_zabbix_full_analysis.json"
    full_analysis_output.write_text(
        json.dumps(
            {
                "generated_at": __import__("datetime").datetime.now().isoformat(),
                "report": report,
                "templates": analysis_results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"   ✅ {full_analysis_output}")

    # 6-3: 可转换模板摘要（仅 full + partial，字段简化）
    convertible_templates = [
        {
            "h3c_template_id": r["h3c_template_id"],
            "h3c_type": r["h3c_type"],
            "h3c_name": r["h3c_name"],
            "conversion_tier": r["conversion_tier"],
            "match_ratio": r["match_ratio"],
            "zabbix_templates": r["zabbix_templates"],
            "stats": r["stats"],
            "units": [
                {
                    "unit_key": u["unit_key"],
                    "unit_name_zh": u["unit_name_zh"],
                    "is_lld": u["is_lld"],
                    "collect_time": u["collect_time"],
                    "fields": [
                        {
                            "field_key": f["field_key"],
                            "field_name_zh": f["field_name_zh"],
                            "field_unit": f["field_unit"],
                            "value_type": f["value_type"],
                            "alarm_inst": f["alarm_inst"],
                            "enable_threshold": f["enable_threshold"],
                            "zabbix_match": f["zabbix_match"],
                        }
                        for f in u["fields"]
                        if f["zabbix_match"] is not None
                    ],
                }
                for u in r["units"]
                if any(f["zabbix_match"] is not None for f in u["fields"])
            ],
        }
        for r in analysis_results
        if r["conversion_tier"] in ("full", "partial")
    ]

    convertible_output = output_dir / "h3c_convertible_templates.json"
    convertible_output.write_text(
        json.dumps(
            {
                "generated_at": __import__("datetime").datetime.now().isoformat(),
                "total_convertible": len(convertible_templates),
                "templates": convertible_templates,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"   ✅ {convertible_output}")

    # 6-4: 转换报告 Markdown
    md_lines = [
        "# 华三监控模板 → Zabbix 转换可行性分析报告\n",
        f"**生成时间**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        f"**Zabbix 版本**: 7.0.23\n\n",
        "## 转换分级汇总\n",
        "| 等级 | 数量 | 说明 |",
        "|------|------|------|",
        f"| 🟢 full     | {report['summary']['full_conversion']}  | {report['tier_description']['full']} |",
        f"| 🟡 partial  | {report['summary']['partial_conversion']}  | {report['tier_description']['partial']} |",
        f"| 🔵 skeleton | {report['summary']['skeleton_only']} | {report['tier_description']['skeleton']} |",
        f"| 🔴 none     | {report['summary']['no_conversion']}  | {report['tier_description']['none']} |",
        "",
        "## 可转换模板明细（full + partial）\n",
        "| 华三模板名 | 类型Key | 转换等级 | 字段匹配率 | 对应 Zabbix 模板 |",
        "|-----------|---------|---------|----------|----------------|",
    ]
    for tpl in sorted(
        convertible_templates, key=lambda x: (-x["match_ratio"], x["h3c_name"])
    ):
        tier_icon = "🟢" if tpl["conversion_tier"] == "full" else "🟡"
        zabbix_tpls = ", ".join(tpl["zabbix_templates"])
        md_lines.append(
            f"| {tpl['h3c_name']} | `{tpl['h3c_type']}` | {tier_icon} {tpl['conversion_tier']} | "
            f"{tpl['match_ratio'] * 100:.0f}% ({tpl['stats']['matched_fields']}/{tpl['stats']['total_fields']}) | {zabbix_tpls} |"
        )

    md_lines += [
        "",
        "## 不可转换模板（none）\n",
        "以下模板依赖华三私有采集引擎，Zabbix 暂无对应实现：\n",
        "| 华三模板名 | 类型Key | 原因 |",
        "|-----------|---------|------|",
    ]
    for r in analysis_results:
        if r["conversion_tier"] == "none":
            md_lines.append(
                f"| {r['h3c_name']} | `{r['h3c_type']}` | 华三私有 API / 无通用采集方式 |"
            )

    md_lines += [
        "",
        "## 字段映射规则说明\n",
        "- **exact_map**: 基于精确映射表，可直接生成 Zabbix Item",
        "- **keyword_infer**: 基于字段名关键词推断，置信度中等，建议人工确认",
        "- **LLD 标记**: `is_prototype=true` 表示该字段对应 Zabbix LLD 发现规则下的 Item Prototype",
    ]

    md_output = output_dir / "conversion_report.md"
    md_output.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"   ✅ {md_output}")

    # 6-5: 精确映射表 JSON（供转换器使用）
    mapping_table_output = output_dir / "field_mapping_table.json"
    mapping_table_output.write_text(
        json.dumps(
            {
                "h3c_to_zabbix_key": H3C_TO_ZABBIX_KEY_MAP,
                "h3c_type_to_zabbix_template": H3C_TYPE_TO_ZABBIX_TEMPLATE,
                "zabbix_item_type_names": ITEM_TYPE_NAMES,
                "zabbix_value_type_names": VALUE_TYPE_NAMES,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"   ✅ {mapping_table_output}")

    print(f"\n✨ 分析完成！输出目录: {output_dir}")
    return 0


def _group_items_by_template(items: list[dict]) -> dict:
    """按模板分组 items"""
    grouped = defaultdict(list)
    for item in items:
        grouped[item["template_name"]].append(
            {
                "key": item["key"],
                "name": item["name"],
                "type": item["type"],
                "value_type": item["value_type"],
                "units": item["units"],
                "is_prototype": item["is_prototype"],
            }
        )
    return dict(grouped)


if __name__ == "__main__":
    sys.exit(main())
