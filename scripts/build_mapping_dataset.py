#!/usr/bin/env python3
"""
build_mapping_dataset.py
基于已有的 zabbix_keys_dump.json 和华三模板 JSON，
构建完整的字段映射数据集，输出到 output/zabbix-mapping/。

运行前提：已执行 python3 scripts/dump_zabbix_keys.py
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
H3C_DETAILS_DIR = ROOT / "output" / "monitor-templates" / "details"
ZABBIX_DUMP = ROOT / "output" / "zabbix-mapping" / "zabbix_keys_dump.json"
OUTPUT_DIR = ROOT / "output" / "zabbix-mapping"

# ── 华三 type key → 对应 Zabbix 模板名 ──────────────────────────────────────
H3C_TYPE_TO_ZABBIX_TEMPLATES: dict[str, list[str]] = {
    # ── OS ──
    "linux": ["Linux by Zabbix agent", "Linux by Zabbix agent active", "Linux by SNMP"],
    "kylin": ["Linux by Zabbix agent"],
    "kylinos": ["Linux by Zabbix agent"],
    "uos": ["Linux by Zabbix agent"],
    "rocky": ["Linux by Zabbix agent"],
    "suse": ["Linux by Zabbix agent"],
    "winsvr": [
        "Windows by Zabbix agent",
        "Windows by Zabbix agent active",
        "Windows by SNMP",
    ],
    "aix": ["AIX by Zabbix agent"],
    "freebsd": ["FreeBSD by Zabbix agent"],
    "hpux": ["HP-UX by Zabbix agent"],
    "solaris": ["Solaris by Zabbix agent"],
    "macos": ["macOS by Zabbix agent"],
    # ── 网络设备 ──
    "network": ["Network Generic Device by SNMP"],
    "ping": ["ICMP Ping"],
    "pingcmd": ["ICMP Ping"],
    "brocade": ["Brocade FC by SNMP"],
    # ── 数据库 ──
    "mysql": ["MySQL by Zabbix agent 2", "MySQL by Zabbix agent"],
    "mysql8": ["MySQL by Zabbix agent 2"],
    "psql": ["PostgreSQL by Zabbix agent 2", "PostgreSQL by Zabbix agent"],
    "redis": ["Redis by Zabbix agent 2"],
    "mongo": ["MongoDB node by Zabbix agent 2"],
    "es": ["Elasticsearch Cluster by HTTP"],
    "mssql": ["MSSQL by Zabbix agent 2"],
    "oracle": ["Oracle by Zabbix agent 2"],
    "memch": ["Memcached by Zabbix agent 2"],
    # ── 应用/中间件 ──
    "nginx": ["Nginx by HTTP", "Nginx by Zabbix agent"],
    "apache": ["Apache by HTTP"],
    "tomcat": ["Apache Tomcat by JMX"],
    "rabbit": ["RabbitMQ node by HTTP", "RabbitMQ cluster by HTTP"],
    "kafka": ["Apache Kafka by JMX"],
    "zk": ["Zookeeper by HTTP"],
    "iis": ["IIS by Zabbix agent"],
    "php": ["PHP-FPM by HTTP"],
    "hadoop": ["Hadoop by HTTP"],
    "etcd": ["Etcd by HTTP"],
    "jrt": ["Generic Java JMX"],
    "wildfly": ["WildFly Server by JMX"],
    # ── 容器/K8s ──
    "docker": ["Docker by Zabbix agent 2"],
    "k8s": ["Kubernetes cluster state by HTTP", "Kubernetes nodes by HTTP"],
    "kubemaster": ["Kubernetes API server by HTTP"],
    "kubecon": ["Kubernetes Kubelet by HTTP"],
    # ── 虚拟化 ──
    "vcenter": ["VMware"],
    "vmware": ["VMware Guest", "VMware Hypervisor"],
}

# ── 精确字段映射表 ────────────────────────────────────────────────────────────
# key 格式: "{h3c_type}.{unit_key}.{field_key}"
# value: { zabbix_key, is_prototype, confidence, notes }
EXACT_FIELD_MAP: dict[str, dict] = {
    # ════════════════════════════════════════════════════════
    # Linux / 通用 OS（Zabbix agent 采集）
    # ════════════════════════════════════════════════════════
    # ── 可用性 ──
    "linux.AvailableData.AvailabilityData": {
        "zabbix_key": "agent.ping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Linux agent 可用性用 agent.ping 检测",
    },
    "general.AvailableData.AvailabilityData": {
        "zabbix_key": "icmpping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "通用可用性探测",
    },
    # ── CPU ──
    "linux.cpu.CpuUtilization": {
        "zabbix_key": "system.cpu.util",
        "is_prototype": False,
        "confidence": "high",
        "notes": "CPU 总利用率，Dependent item 由 system.cpu.util[,*] 计算得出",
    },
    "linux.cpuinfo_stat.IdlePercentage": {
        "zabbix_key": "system.cpu.util[,idle]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "CPU 空闲时间百分比",
    },
    "linux.cpuinfo_stat.IOwaitPercentage": {
        "zabbix_key": "system.cpu.util[,iowait]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "CPU IO 等待时间百分比",
    },
    "linux.cpuinfo_stat.UserPercentage": {
        "zabbix_key": "system.cpu.util[,user]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "用户态 CPU 时间",
    },
    "linux.cpuinfo_stat.SystemPercentage": {
        "zabbix_key": "system.cpu.util[,system]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "内核态 CPU 时间",
    },
    "linux.cpuinfo_stat.NicePercentage": {
        "zabbix_key": "system.cpu.util[,nice]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "nice CPU 时间",
    },
    "linux.cpuinfo_stat.SoftirqPercentage": {
        "zabbix_key": "system.cpu.util[,softirq]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "软中断 CPU 时间",
    },
    "linux.cpuinfo_stat.StealPercentage": {
        "zabbix_key": "system.cpu.util[,steal]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "steal CPU 时间（虚拟机环境）",
    },
    "linux.cpuinfo_stat.GuestPercentage": {
        "zabbix_key": "system.cpu.util[,guest]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "guest CPU 时间",
    },
    "linux.cpuinfo_stat.CpuCoreNumber": {
        "zabbix_key": "system.cpu.num",
        "is_prototype": False,
        "confidence": "high",
        "notes": "CPU 核心数",
    },
    "linux.cpuinfo_stat.InterruptPerSecond": {
        "zabbix_key": "system.cpu.intr",
        "is_prototype": False,
        "confidence": "high",
        "notes": "每秒中断次数",
    },
    "linux.cpuinfo_stat.ContextSwitchPerSecond": {
        "zabbix_key": "system.cpu.switches",
        "is_prototype": False,
        "confidence": "high",
        "notes": "每秒上下文切换次数",
    },
    # ── 系统负载 ──
    "linux.load.CpuLoad1": {
        "zabbix_key": "system.cpu.load[all,avg1]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "1 分钟平均负载",
    },
    "linux.load.CpuLoad5": {
        "zabbix_key": "system.cpu.load[all,avg5]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "5 分钟平均负载",
    },
    "linux.load.CpuLoad15": {
        "zabbix_key": "system.cpu.load[all,avg15]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "15 分钟平均负载",
    },
    # ── 内存 ──
    "linux.memory.MemTotal": {
        "zabbix_key": "vm.memory.size[total]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "总内存",
    },
    "linux.memory.MemFree": {
        "zabbix_key": "vm.memory.size[available]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "可用内存（Zabbix 用 available，含 buffers/cache）",
    },
    "linux.memory.MemUtilization": {
        "zabbix_key": "vm.memory.utilization",
        "is_prototype": False,
        "confidence": "high",
        "notes": "内存利用率百分比（Dependent item）",
    },
    "linux.memory.MemAvailable": {
        "zabbix_key": "vm.memory.size[pavailable]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "可用内存百分比",
    },
    "linux.memory.SwapTotal": {
        "zabbix_key": "system.swap.size[,total]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Swap 总大小",
    },
    "linux.memory.SwapFree": {
        "zabbix_key": "system.swap.size[,free]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Swap 剩余",
    },
    "linux.memory.SwapUtilization": {
        "zabbix_key": "system.swap.size[,pfree]",
        "is_prototype": False,
        "confidence": "medium",
        "notes": "Swap 利用率（Zabbix 为 pfree=剩余百分比，需转换）",
    },
    # ── 文件系统（LLD） ──
    "linux.filesystem.TotalSpace": {
        "zabbix_key": "vfs.fs.dependent.size[{#FSNAME},total]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "文件系统总空间（LLD）",
    },
    "linux.filesystem.FreeSpace": {
        "zabbix_key": "vfs.fs.dependent.size[{#FSNAME},free]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "文件系统剩余空间（LLD）",
    },
    "linux.filesystem.UsedSpace": {
        "zabbix_key": "vfs.fs.dependent.size[{#FSNAME},used]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "文件系统已用空间（LLD）",
    },
    "linux.filesystem.Utilization": {
        "zabbix_key": "vfs.fs.dependent.size[{#FSNAME},pused]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "文件系统利用率（LLD）",
    },
    "linux.filesystem.FsName": {
        "zabbix_key": "vfs.fs.dependent.discovery",
        "is_prototype": False,
        "confidence": "high",
        "notes": "文件系统名称（LLD 发现规则本身）",
    },
    # ── Inode ──
    "linux.inode.InodesUsed": {
        "zabbix_key": "vfs.fs.dependent.inode[{#FSNAME},pfree]",
        "is_prototype": True,
        "confidence": "medium",
        "notes": "Zabbix 存 inode 剩余百分比，华三存已用；含义相反但同一数据",
    },
    # ── 网络接口（LLD） ──
    "linux.interface.InterfaceName": {
        "zabbix_key": "net.if.discovery",
        "is_prototype": False,
        "confidence": "high",
        "notes": "网络接口发现规则，对应接口名称标识字段",
    },
    "linux.interface.rxPerSec": {
        "zabbix_key": 'net.if.in["{#IFNAME}"]',
        "is_prototype": True,
        "confidence": "high",
        "notes": "接口接收速率（bps）",
    },
    "linux.interface.txPerSec": {
        "zabbix_key": 'net.if.out["{#IFNAME}"]',
        "is_prototype": True,
        "confidence": "high",
        "notes": "接口发送速率（bps）",
    },
    "linux.interface.rxErrors": {
        "zabbix_key": 'net.if.in["{#IFNAME}",errors]',
        "is_prototype": True,
        "confidence": "high",
        "notes": "接口接收错误",
    },
    "linux.interface.txErrors": {
        "zabbix_key": 'net.if.out["{#IFNAME}",errors]',
        "is_prototype": True,
        "confidence": "high",
        "notes": "接口发送错误",
    },
    "linux.interface.rxDropped": {
        "zabbix_key": 'net.if.in["{#IFNAME}",dropped]',
        "is_prototype": True,
        "confidence": "high",
        "notes": "接口接收丢包",
    },
    "linux.interface.txDropped": {
        "zabbix_key": 'net.if.out["{#IFNAME}",dropped]',
        "is_prototype": True,
        "confidence": "high",
        "notes": "接口发送丢包",
    },
    "linux.interface.InterfaceSpeed": {
        "zabbix_key": 'vfs.file.contents["/sys/class/net/{#IFNAME}/speed"]',
        "is_prototype": True,
        "confidence": "high",
        "notes": "接口速率",
    },
    "linux.interface.InterfaceStatus": {
        "zabbix_key": 'vfs.file.contents["/sys/class/net/{#IFNAME}/operstate"]',
        "is_prototype": True,
        "confidence": "high",
        "notes": "接口状态（up/down）",
    },
    # ── 磁盘 I/O（LLD） ──
    "linux.disk.DiskReadRate": {
        "zabbix_key": "vfs.dev.read.rate[{#DEVNAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "磁盘读速率",
    },
    "linux.disk.DiskWriteRate": {
        "zabbix_key": "vfs.dev.write.rate[{#DEVNAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "磁盘写速率",
    },
    "linux.disk.DiskReadAwait": {
        "zabbix_key": "vfs.dev.read.await[{#DEVNAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "磁盘读等待时间（ms）",
    },
    "linux.disk.DiskWriteAwait": {
        "zabbix_key": "vfs.dev.write.await[{#DEVNAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "磁盘写等待时间（ms）",
    },
    "linux.disk.DiskUtilization": {
        "zabbix_key": "vfs.dev.util[{#DEVNAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "磁盘利用率",
    },
    # ── 系统信息 ──
    "linux.hostname.HostName": {
        "zabbix_key": "system.hostname",
        "is_prototype": False,
        "confidence": "high",
        "notes": "主机名",
    },
    "linux.version.OsVersion": {
        "zabbix_key": "system.sw.os",
        "is_prototype": False,
        "confidence": "high",
        "notes": "操作系统版本",
    },
    "linux.ntp.NtpOffset": {
        "zabbix_key": "system.localtime",
        "is_prototype": False,
        "confidence": "medium",
        "notes": "NTP 时间（Zabbix 获取本地时间，需外部计算偏差）",
    },
    "linux.process.ProcessNum": {
        "zabbix_key": "proc.num",
        "is_prototype": False,
        "confidence": "high",
        "notes": "进程总数",
    },
    "linux.process.RunningProcessNum": {
        "zabbix_key": "proc.num[,,run]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "运行中进程数",
    },
    # ════════════════════════════════════════════════════════
    # Windows（Zabbix agent 采集）
    # ════════════════════════════════════════════════════════
    "winsvr.AvailableData.AvailabilityData": {
        "zabbix_key": "agent.ping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Windows agent 可用性",
    },
    "winsvr.cpu.CpuUtilization": {
        "zabbix_key": "system.cpu.util",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Windows CPU 总利用率",
    },
    "winsvr.cpu.CpuLoad1": {
        "zabbix_key": "system.cpu.load[all,avg1]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "1 分钟负载",
    },
    "winsvr.memory.MemTotal": {
        "zabbix_key": "vm.memory.size[total]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "总内存",
    },
    "winsvr.memory.MemUtilization": {
        "zabbix_key": "vm.memory.utilization",
        "is_prototype": False,
        "confidence": "high",
        "notes": "内存利用率",
    },
    "winsvr.disk.DiskName": {
        "zabbix_key": "vfs.fs.discovery",
        "is_prototype": False,
        "confidence": "high",
        "notes": "磁盘分区发现规则",
    },
    "winsvr.disk.DiskUtilization": {
        "zabbix_key": "vfs.fs.size[{#FSNAME},pused]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "磁盘分区利用率（LLD）",
    },
    "winsvr.disk.DiskFreeSpace": {
        "zabbix_key": "vfs.fs.size[{#FSNAME},free]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "磁盘剩余空间（LLD）",
    },
    "winsvr.disk.DiskTotalSpace": {
        "zabbix_key": "vfs.fs.size[{#FSNAME},total]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "磁盘总空间（LLD）",
    },
    "winsvr.interface.InterfaceName": {
        "zabbix_key": "net.if.discovery",
        "is_prototype": False,
        "confidence": "high",
        "notes": "网络接口发现",
    },
    "winsvr.interface.rxPerSec": {
        "zabbix_key": 'net.if.in["{#IFNAME}"]',
        "is_prototype": True,
        "confidence": "high",
        "notes": "接口接收速率",
    },
    "winsvr.interface.txPerSec": {
        "zabbix_key": 'net.if.out["{#IFNAME}"]',
        "is_prototype": True,
        "confidence": "high",
        "notes": "接口发送速率",
    },
    "winsvr.hostname.HostName": {
        "zabbix_key": "system.hostname",
        "is_prototype": False,
        "confidence": "high",
        "notes": "主机名",
    },
    "winsvr.process.ProcessName": {
        "zabbix_key": "proc.num[{#PROCNAME}]",
        "is_prototype": True,
        "confidence": "medium",
        "notes": "进程监控（LLD）",
    },
    # ════════════════════════════════════════════════════════
    # AIX（Zabbix agent）
    # ════════════════════════════════════════════════════════
    "aix.AvailableData.AvailabilityData": {
        "zabbix_key": "agent.ping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "AIX agent 可用性",
    },
    "aix.cpu.CpuUtilization": {
        "zabbix_key": "system.stat[cpu,us]",
        "is_prototype": False,
        "confidence": "medium",
        "notes": "AIX CPU 利用率，Zabbix 用 system.stat[cpu,us] 代表用户态",
    },
    "aix.cpu.AppCpuUtilization": {
        "zabbix_key": "system.stat[cpu,app]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "AIX 应用 CPU 时间",
    },
    "aix.cpu.SysCpuUtilization": {
        "zabbix_key": "system.stat[cpu,sy]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "AIX 系统态 CPU 时间",
    },
    "aix.cpu.WaitCpuUtilization": {
        "zabbix_key": "system.stat[cpu,wa]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "AIX 等待 CPU 时间",
    },
    "aix.cpu.IdleCpuUtilization": {
        "zabbix_key": "system.stat[cpu,id]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "AIX 空闲 CPU 时间",
    },
    "aix.memory.MemTotal": {
        "zabbix_key": "vm.memory.size[total]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "AIX 总内存",
    },
    "aix.memory.MemFree": {
        "zabbix_key": "system.stat[memory,fre]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "AIX 空闲内存",
    },
    "aix.load.CpuLoad1": {
        "zabbix_key": "system.cpu.load[percpu,avg1]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "AIX 1 分钟平均负载（per CPU）",
    },
    "aix.load.CpuLoad5": {
        "zabbix_key": "system.cpu.load[percpu,avg5]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "AIX 5 分钟平均负载",
    },
    "aix.load.CpuLoad15": {
        "zabbix_key": "system.cpu.load[percpu,avg15]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "AIX 15 分钟平均负载",
    },
    "aix.interface.rxPerSec": {
        "zabbix_key": 'net.if.in["{#IFNAME}"]',
        "is_prototype": True,
        "confidence": "high",
        "notes": "AIX 接口接收速率（LLD）",
    },
    "aix.interface.txPerSec": {
        "zabbix_key": 'net.if.out["{#IFNAME}"]',
        "is_prototype": True,
        "confidence": "high",
        "notes": "AIX 接口发送速率（LLD）",
    },
    "aix.filesystem.Utilization": {
        "zabbix_key": "vfs.fs.dependent.size[{#FSNAME},pused]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "AIX 文件系统利用率（LLD）",
    },
    # ════════════════════════════════════════════════════════
    # 通用 UNIX：FreeBSD / HP-UX / Solaris / macOS
    # ════════════════════════════════════════════════════════
    "freebsd.AvailableData.AvailabilityData": {
        "zabbix_key": "agent.ping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "freebsd.cpu.CpuUtilization": {
        "zabbix_key": "system.cpu.util",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "freebsd.memory.MemUtilization": {
        "zabbix_key": "vm.memory.utilization",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "freebsd.load.CpuLoad1": {
        "zabbix_key": "system.cpu.load[all,avg1]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "freebsd.filesystem.Utilization": {
        "zabbix_key": "vfs.fs.dependent.size[{#FSNAME},pused]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "",
    },
    "hpux.AvailableData.AvailabilityData": {
        "zabbix_key": "agent.ping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "hpux.cpu.CpuUtilization": {
        "zabbix_key": "system.cpu.util",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "hpux.memory.MemUtilization": {
        "zabbix_key": "vm.memory.utilization",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "hpux.load.CpuLoad1": {
        "zabbix_key": "system.cpu.load[all,avg1]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "hpux.filesystem.Utilization": {
        "zabbix_key": "vfs.fs.dependent.size[{#FSNAME},pused]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "",
    },
    "solaris.AvailableData.AvailabilityData": {
        "zabbix_key": "agent.ping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "solaris.cpu.CpuUtilization": {
        "zabbix_key": "system.cpu.util",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "solaris.memory.MemUtilization": {
        "zabbix_key": "vm.memory.utilization",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "solaris.hostname.HostName": {
        "zabbix_key": "system.hostname",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "solaris.filesystem.Utilization": {
        "zabbix_key": "vfs.fs.dependent.size[{#FSNAME},pused]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "",
    },
    "solaris.interface.rxPerSec": {
        "zabbix_key": 'net.if.in["{#IFNAME}"]',
        "is_prototype": True,
        "confidence": "high",
        "notes": "",
    },
    "solaris.interface.txPerSec": {
        "zabbix_key": 'net.if.out["{#IFNAME}"]',
        "is_prototype": True,
        "confidence": "high",
        "notes": "",
    },
    "macos.AvailableData.AvailabilityData": {
        "zabbix_key": "agent.ping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "macos.cpu.CpuUtilization": {
        "zabbix_key": "system.cpu.util",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "macos.memory.MemUtilization": {
        "zabbix_key": "vm.memory.utilization",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    # ════════════════════════════════════════════════════════
    # 网络设备（SNMP）
    # ════════════════════════════════════════════════════════
    "network.AvailableData.AvailabilityData": {
        "zabbix_key": "icmpping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "网络设备可用性用 ICMP ping",
    },
    "network.cpu.cpuUtilization": {
        "zabbix_key": "system.cpu.util",
        "is_prototype": False,
        "confidence": "high",
        "notes": "SNMP 获取 CPU 利用率（通用 ifXTable 或厂商 MIB）",
    },
    "network.memory.memUtilization": {
        "zabbix_key": "vm.memory.size[pused]",
        "is_prototype": False,
        "confidence": "medium",
        "notes": "通用 SNMP 内存利用率",
    },
    "network.interface.InterfaceName": {
        "zabbix_key": "net.if.discovery",
        "is_prototype": False,
        "confidence": "high",
        "notes": "接口发现（SNMP ifTable）",
    },
    "network.interface.rxPerSec": {
        "zabbix_key": "net.if.in[{#SNMPINDEX}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "接口接收速率（SNMP）",
    },
    "network.interface.txPerSec": {
        "zabbix_key": "net.if.out[{#SNMPINDEX}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "接口发送速率（SNMP）",
    },
    "network.interface.rxErrors": {
        "zabbix_key": "net.if.in[{#SNMPINDEX},errors]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "接口接收错误",
    },
    "network.interface.txErrors": {
        "zabbix_key": "net.if.out[{#SNMPINDEX},errors]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "接口发送错误",
    },
    "network.interface.rxUtilization": {
        "zabbix_key": "net.if.in[{#SNMPINDEX}]",
        "is_prototype": True,
        "confidence": "medium",
        "notes": "接口带宽利用率需在 Zabbix 中通过计算 item 实现",
    },
    "network.interface.txUtilization": {
        "zabbix_key": "net.if.out[{#SNMPINDEX}]",
        "is_prototype": True,
        "confidence": "medium",
        "notes": "同上",
    },
    "network.interface.interfaceNegotiationRate": {
        "zabbix_key": 'vfs.file.contents["/sys/class/net/{#IFNAME}/speed"]',
        "is_prototype": True,
        "confidence": "low",
        "notes": "接口协商速率，SNMP 设备通过 ifSpeed OID 获取",
    },
    # ── Ping 探测 ──
    "ping.AvailableData.AvailabilityData": {
        "zabbix_key": "icmpping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "ICMP ping 可用性",
    },
    "ping.ping.responseTime": {
        "zabbix_key": "icmppingsec",
        "is_prototype": False,
        "confidence": "high",
        "notes": "ICMP ping 响应时间（秒）",
    },
    "ping.ping.packetLoss": {
        "zabbix_key": "icmppingloss",
        "is_prototype": False,
        "confidence": "high",
        "notes": "ICMP ping 丢包率",
    },
    "ping.ping.responseTimeMs": {
        "zabbix_key": "icmppingsec",
        "is_prototype": False,
        "confidence": "high",
        "notes": "ICMP ping 响应时间（Zabbix 单位 s，需换算）",
    },
    "pingcmd.AvailableData.AvailabilityData": {
        "zabbix_key": "icmpping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "本地 Ping 可用性",
    },
    "pingcmd.ping.responseTime": {
        "zabbix_key": "icmppingsec",
        "is_prototype": False,
        "confidence": "high",
        "notes": "本地 Ping 响应时间",
    },
    "pingcmd.ping.packetLoss": {
        "zabbix_key": "icmppingloss",
        "is_prototype": False,
        "confidence": "high",
        "notes": "本地 Ping 丢包率",
    },
    # ════════════════════════════════════════════════════════
    # MySQL / MySQL8（Zabbix agent 2）
    # ════════════════════════════════════════════════════════
    "mysql.AvailableData.AvailabilityData": {
        "zabbix_key": "mysql.ping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "MySQL 可用性探测",
    },
    "mysql.status.Uptime": {
        "zabbix_key": "mysql.status[Uptime]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "MySQL 运行时长",
    },
    "mysql.status.Threads_connected": {
        "zabbix_key": "mysql.status[Threads_connected]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "当前连接数",
    },
    "mysql.status.Threads_running": {
        "zabbix_key": "mysql.status[Threads_running]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "运行中线程数",
    },
    "mysql.status.Max_used_connections": {
        "zabbix_key": "mysql.status[Max_used_connections]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "历史最大连接数",
    },
    "mysql.status.Queries": {
        "zabbix_key": "mysql.status[Queries]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "查询总数",
    },
    "mysql.status.Slow_queries": {
        "zabbix_key": "mysql.status[Slow_queries]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "慢查询数",
    },
    "mysql.status.Bytes_received": {
        "zabbix_key": "mysql.status[Bytes_received]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "接收字节数",
    },
    "mysql.status.Bytes_sent": {
        "zabbix_key": "mysql.status[Bytes_sent]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "发送字节数",
    },
    "mysql.status.Innodb_buffer_pool_read_requests": {
        "zabbix_key": "mysql.status[Innodb_buffer_pool_read_requests]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "InnoDB 缓冲池读请求",
    },
    "mysql.status.Innodb_buffer_pool_reads": {
        "zabbix_key": "mysql.status[Innodb_buffer_pool_reads]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "InnoDB 缓冲池物理读",
    },
    "mysql.version.Version": {
        "zabbix_key": "mysql.version",
        "is_prototype": False,
        "confidence": "high",
        "notes": "MySQL 版本",
    },
    "mysql.database.dbSize": {
        "zabbix_key": "mysql.dbsize[{#DBNAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "单个数据库大小（LLD）",
    },
    # mysql8 继承 mysql（复用相同映射）
    "mysql8.AvailableData.AvailabilityData": {
        "zabbix_key": "mysql.ping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "mysql8.status.Uptime": {
        "zabbix_key": "mysql.status[Uptime]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "mysql8.status.Threads_connected": {
        "zabbix_key": "mysql.status[Threads_connected]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "mysql8.status.Threads_running": {
        "zabbix_key": "mysql.status[Threads_running]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "mysql8.status.Queries": {
        "zabbix_key": "mysql.status[Queries]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "mysql8.status.Slow_queries": {
        "zabbix_key": "mysql.status[Slow_queries]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "mysql8.status.Bytes_received": {
        "zabbix_key": "mysql.status[Bytes_received]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "mysql8.status.Bytes_sent": {
        "zabbix_key": "mysql.status[Bytes_sent]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "mysql8.status.Innodb_buffer_pool_read_requests": {
        "zabbix_key": "mysql.status[Innodb_buffer_pool_read_requests]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "mysql8.status.Innodb_buffer_pool_reads": {
        "zabbix_key": "mysql.status[Innodb_buffer_pool_reads]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "mysql8.version.Version": {
        "zabbix_key": "mysql.version",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "mysql8.database.dbSize": {
        "zabbix_key": "mysql.dbsize[{#DBNAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "",
    },
    "mysql8.conn.maxConnections": {
        "zabbix_key": "mysql.status[Max_used_connections]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "",
    },
    "mysql8.conn.connectionUsage": {
        "zabbix_key": "mysql.status[Threads_connected]",
        "is_prototype": False,
        "confidence": "medium",
        "notes": "连接使用率需结合 max_connections 计算",
    },
    # ════════════════════════════════════════════════════════
    # PostgreSQL（Zabbix agent 2）
    # ════════════════════════════════════════════════════════
    "psql.AvailableData.AvailabilityData": {
        "zabbix_key": "pgsql.ping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "PostgreSQL 可用性",
    },
    "psql.conn.numConnections": {
        "zabbix_key": "pgsql.connections[{#DBNAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "当前连接数（LLD 按数据库）",
    },
    "psql.conn.maxConnections": {
        "zabbix_key": "pgsql.settings.max_connections",
        "is_prototype": False,
        "confidence": "high",
        "notes": "最大连接数配置",
    },
    "psql.status.uptime": {
        "zabbix_key": "pgsql.uptime",
        "is_prototype": False,
        "confidence": "high",
        "notes": "PostgreSQL 运行时长",
    },
    "psql.database.dbSize": {
        "zabbix_key": "pgsql.db.size[{#DBNAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "单个数据库大小（LLD）",
    },
    "psql.database.dbName": {
        "zabbix_key": "pgsql.db.discovery",
        "is_prototype": False,
        "confidence": "high",
        "notes": "数据库发现规则",
    },
    "psql.version.Version": {
        "zabbix_key": "pgsql.version",
        "is_prototype": False,
        "confidence": "high",
        "notes": "PostgreSQL 版本",
    },
    "psql.stat.commits": {
        "zabbix_key": "pgsql.dbstat.sum.xact_commit",
        "is_prototype": False,
        "confidence": "high",
        "notes": "提交事务数",
    },
    "psql.stat.rollbacks": {
        "zabbix_key": "pgsql.dbstat.sum.xact_rollback",
        "is_prototype": False,
        "confidence": "high",
        "notes": "回滚事务数",
    },
    "psql.stat.blksRead": {
        "zabbix_key": "pgsql.dbstat.sum.blks_read",
        "is_prototype": False,
        "confidence": "high",
        "notes": "磁盘块读取数",
    },
    "psql.stat.blksHit": {
        "zabbix_key": "pgsql.dbstat.sum.blks_hit",
        "is_prototype": False,
        "confidence": "high",
        "notes": "缓存命中块数",
    },
    # ════════════════════════════════════════════════════════
    # Redis（Zabbix agent 2）
    # ════════════════════════════════════════════════════════
    "redis.AvailableData.AvailabilityData": {
        "zabbix_key": "redis.ping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Redis 可用性",
    },
    "redis.server.redis_version": {
        "zabbix_key": "redis.info[Server,redis_version]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Redis 版本",
    },
    "redis.server.uptime_in_seconds": {
        "zabbix_key": "redis.info[Server,uptime_in_seconds]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Redis 运行时长",
    },
    "redis.memory.used_memory": {
        "zabbix_key": "redis.info[Memory,used_memory]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Redis 已用内存（字节）",
    },
    "redis.memory.used_memory_rss": {
        "zabbix_key": "redis.info[Memory,used_memory_rss]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Redis RSS 内存",
    },
    "redis.memory.maxmemory": {
        "zabbix_key": "redis.info[Memory,maxmemory]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Redis 最大内存配置",
    },
    "redis.clients.connected_clients": {
        "zabbix_key": "redis.info[Clients,connected_clients]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "当前连接客户端数",
    },
    "redis.clients.blocked_clients": {
        "zabbix_key": "redis.info[Clients,blocked_clients]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "阻塞客户端数",
    },
    "redis.stats.total_commands_processed": {
        "zabbix_key": "redis.info[Stats,total_commands_processed]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "已处理命令总数",
    },
    "redis.stats.total_connections_received": {
        "zabbix_key": "redis.info[Stats,total_connections_received]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "已接受连接总数",
    },
    "redis.stats.instantaneous_ops_per_sec": {
        "zabbix_key": "redis.info[Stats,instantaneous_ops_per_sec]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "每秒操作数（OPS）",
    },
    "redis.stats.rejected_connections": {
        "zabbix_key": "redis.info[Stats,rejected_connections]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "被拒绝连接数",
    },
    "redis.replication.connected_slaves": {
        "zabbix_key": "redis.info[Replication,connected_slaves]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "已连接从库数",
    },
    "redis.keyspace.db0.keys": {
        "zabbix_key": "redis.info[Keyspace,db0]",
        "is_prototype": False,
        "confidence": "medium",
        "notes": "DB0 键数量",
    },
    # ════════════════════════════════════════════════════════
    # MongoDB（Zabbix agent 2）
    # ════════════════════════════════════════════════════════
    "mongo.AvailableData.AvailabilityData": {
        "zabbix_key": "mongodb.ping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "MongoDB 可用性",
    },
    "mongo.conn.currentConnections": {
        "zabbix_key": "mongodb.connpool.stats.current",
        "is_prototype": False,
        "confidence": "high",
        "notes": "当前连接数",
    },
    "mongo.conn.totalCreated": {
        "zabbix_key": "mongodb.connpool.stats.totalCreated",
        "is_prototype": False,
        "confidence": "high",
        "notes": "已创建连接总数",
    },
    "mongo.server.version": {
        "zabbix_key": "mongodb.version",
        "is_prototype": False,
        "confidence": "high",
        "notes": "MongoDB 版本",
    },
    "mongo.server.uptime": {
        "zabbix_key": "mongodb.uptime",
        "is_prototype": False,
        "confidence": "high",
        "notes": "MongoDB 运行时长",
    },
    "mongo.database.dbName": {
        "zabbix_key": "mongodb.db.discovery",
        "is_prototype": False,
        "confidence": "high",
        "notes": "数据库发现规则",
    },
    "mongo.database.dbSize": {
        "zabbix_key": "mongodb.db.stats.dataSize[{#DBNAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "单个数据库大小（LLD）",
    },
    "mongo.ops.insertPerSec": {
        "zabbix_key": "mongodb.opscounters.insert",
        "is_prototype": False,
        "confidence": "high",
        "notes": "每秒插入操作",
    },
    "mongo.ops.queryPerSec": {
        "zabbix_key": "mongodb.opscounters.query",
        "is_prototype": False,
        "confidence": "high",
        "notes": "每秒查询操作",
    },
    "mongo.ops.updatePerSec": {
        "zabbix_key": "mongodb.opscounters.update",
        "is_prototype": False,
        "confidence": "high",
        "notes": "每秒更新操作",
    },
    "mongo.ops.deletePerSec": {
        "zabbix_key": "mongodb.opscounters.delete",
        "is_prototype": False,
        "confidence": "high",
        "notes": "每秒删除操作",
    },
    # ════════════════════════════════════════════════════════
    # Elasticsearch（HTTP）
    # ════════════════════════════════════════════════════════
    "es.AvailableData.AvailabilityData": {
        "zabbix_key": "es.nodes.get",
        "is_prototype": False,
        "confidence": "high",
        "notes": "ES 可用性（通过 HTTP 获取节点信息）",
    },
    "es.cluster.cluster_status": {
        "zabbix_key": "es.cluster.health",
        "is_prototype": False,
        "confidence": "high",
        "notes": "ES 集群健康状态",
    },
    "es.cluster.number_of_nodes": {
        "zabbix_key": "es.cluster.health[number_of_nodes]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "集群节点数",
    },
    "es.cluster.active_shards": {
        "zabbix_key": "es.cluster.health[active_shards]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "活跃分片数",
    },
    "es.cluster.unassigned_shards": {
        "zabbix_key": "es.cluster.health[unassigned_shards]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "未分配分片数",
    },
    "es.node.heap_used_percent": {
        "zabbix_key": "es.nodes.stats[nodes.{#NODE_ID}.jvm.mem.heap_used_percent]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "节点 JVM 堆内存使用率（LLD）",
    },
    # ════════════════════════════════════════════════════════
    # Memcached（Zabbix agent 2）
    # ════════════════════════════════════════════════════════
    "memch.AvailableData.AvailabilityData": {
        "zabbix_key": "memcached.ping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Memcached 可用性",
    },
    "memch.status.version": {
        "zabbix_key": "memcached.stats[version]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Memcached 版本",
    },
    "memch.status.uptime": {
        "zabbix_key": "memcached.stats[uptime]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Memcached 运行时长",
    },
    "memch.status.curr_connections": {
        "zabbix_key": "memcached.stats[curr_connections]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "当前连接数",
    },
    "memch.status.cmd_get": {
        "zabbix_key": "memcached.stats[cmd_get]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "get 命令数",
    },
    "memch.status.cmd_set": {
        "zabbix_key": "memcached.stats[cmd_set]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "set 命令数",
    },
    "memch.status.get_hits": {
        "zabbix_key": "memcached.stats[get_hits]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "cache 命中数",
    },
    "memch.status.get_misses": {
        "zabbix_key": "memcached.stats[get_misses]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "cache 未命中数",
    },
    "memch.status.bytes": {
        "zabbix_key": "memcached.stats[bytes]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "已用内存字节数",
    },
    "memch.status.limit_maxbytes": {
        "zabbix_key": "memcached.stats[limit_maxbytes]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "最大内存限制",
    },
    # ════════════════════════════════════════════════════════
    # Nginx（HTTP）
    # ════════════════════════════════════════════════════════
    "nginx.AvailableData.AvailabilityData": {
        "zabbix_key": "nginx.status",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Nginx 可用性",
    },
    "nginx.status.active": {
        "zabbix_key": "nginx.active_connections",
        "is_prototype": False,
        "confidence": "high",
        "notes": "活跃连接数",
    },
    "nginx.status.requests": {
        "zabbix_key": "nginx.requests.total",
        "is_prototype": False,
        "confidence": "high",
        "notes": "总请求数",
    },
    "nginx.status.reading": {
        "zabbix_key": "nginx.reading",
        "is_prototype": False,
        "confidence": "high",
        "notes": "读请求数",
    },
    "nginx.status.writing": {
        "zabbix_key": "nginx.writing",
        "is_prototype": False,
        "confidence": "high",
        "notes": "写请求数",
    },
    "nginx.status.waiting": {
        "zabbix_key": "nginx.waiting",
        "is_prototype": False,
        "confidence": "high",
        "notes": "等待连接数",
    },
    "nginx.version.Version": {
        "zabbix_key": "nginx.version",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Nginx 版本",
    },
    # ════════════════════════════════════════════════════════
    # Apache（HTTP）
    # ════════════════════════════════════════════════════════
    "apache.AvailableData.AvailabilityData": {
        "zabbix_key": "apache.get_status",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Apache 可用性",
    },
    "apache.status.totalAccesses": {
        "zabbix_key": "apache.requests",
        "is_prototype": False,
        "confidence": "high",
        "notes": "总请求数",
    },
    "apache.status.busyWorkers": {
        "zabbix_key": "apache.connections[writing]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "繁忙工作线程数",
    },
    "apache.status.idleWorkers": {
        "zabbix_key": "apache.connections[keepalive]",
        "is_prototype": False,
        "confidence": "medium",
        "notes": "空闲工作线程数",
    },
    "apache.version.Version": {
        "zabbix_key": "apache.version",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Apache 版本",
    },
    # ════════════════════════════════════════════════════════
    # Apache Tomcat（JMX）
    # ════════════════════════════════════════════════════════
    "tomcat.AvailableData.AvailabilityData": {
        "zabbix_key": 'jmx["Catalina:type=Server",serverInfo]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "Tomcat 可用性（JMX 连通性）",
    },
    "tomcat.version.Version": {
        "zabbix_key": 'jmx["Catalina:type=Server",serverInfo]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "Tomcat 服务器信息含版本",
    },
    "tomcat.thread.currentThreadCount": {
        "zabbix_key": "jmx[{#JMXOBJ},currentThreadCount]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "当前线程数（LLD by 连接器）",
    },
    "tomcat.thread.currentThreadsBusy": {
        "zabbix_key": "jmx[{#JMXOBJ},currentThreadsBusy]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "繁忙线程数",
    },
    "tomcat.thread.maxThreads": {
        "zabbix_key": "jmx[{#JMXOBJ},maxThreads]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "最大线程数",
    },
    "tomcat.request.requestCount": {
        "zabbix_key": "jmx[{#JMXOBJ},requestCount]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "请求总数（LLD by 连接器）",
    },
    "tomcat.request.errorCount": {
        "zabbix_key": "jmx[{#JMXOBJ},errorCount]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "错误请求数",
    },
    "tomcat.request.bytesReceived": {
        "zabbix_key": "jmx[{#JMXOBJ},bytesReceived]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "接收字节数",
    },
    "tomcat.request.bytesSent": {
        "zabbix_key": "jmx[{#JMXOBJ},bytesSent]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "发送字节数",
    },
    "tomcat.session.activeSessions": {
        "zabbix_key": "jmx[{#JMXOBJ},activeSessions]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "活跃 Session 数",
    },
    # ════════════════════════════════════════════════════════
    # RabbitMQ（HTTP）
    # ════════════════════════════════════════════════════════
    "rabbit.AvailableData.AvailabilityData": {
        "zabbix_key": "rabbitmq.get",
        "is_prototype": False,
        "confidence": "high",
        "notes": "RabbitMQ 可用性",
    },
    "rabbit.overview.total_queues": {
        "zabbix_key": "rabbitmq.overview.queue_totals.messages",
        "is_prototype": False,
        "confidence": "medium",
        "notes": "队列消息总数",
    },
    "rabbit.overview.total_consumers": {
        "zabbix_key": "rabbitmq.overview.object_totals.consumers",
        "is_prototype": False,
        "confidence": "high",
        "notes": "消费者总数",
    },
    "rabbit.overview.total_connections": {
        "zabbix_key": "rabbitmq.overview.object_totals.connections",
        "is_prototype": False,
        "confidence": "high",
        "notes": "连接总数",
    },
    "rabbit.queue.messages": {
        "zabbix_key": "rabbitmq.queue.messages[{#VHOST}/{#QUEUE}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "队列消息数（LLD）",
    },
    "rabbit.queue.messages_ready": {
        "zabbix_key": "rabbitmq.queue.messages_ready[{#VHOST}/{#QUEUE}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "队列就绪消息数（LLD）",
    },
    "rabbit.queue.messages_unacknowledged": {
        "zabbix_key": "rabbitmq.queue.messages_unacknowledged[{#VHOST}/{#QUEUE}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "未确认消息数（LLD）",
    },
    # ════════════════════════════════════════════════════════
    # Kafka（JMX）
    # ════════════════════════════════════════════════════════
    "kafka.AvailableData.AvailabilityData": {
        "zabbix_key": 'jmx["kafka.server:type=app-info","version"]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "Kafka 可用性（JMX 连通）",
    },
    "kafka.broker.version": {
        "zabbix_key": 'jmx["kafka.server:type=app-info","version"]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "Kafka 版本",
    },
    "kafka.broker.bytesInPerSec": {
        "zabbix_key": 'jmx["kafka.server:type=BrokerTopicMetrics,name=BytesInPerSec","OneMinuteRate"]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "Kafka Broker 流入字节率",
    },
    "kafka.broker.bytesOutPerSec": {
        "zabbix_key": 'jmx["kafka.server:type=BrokerTopicMetrics,name=BytesOutPerSec","OneMinuteRate"]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "Kafka Broker 流出字节率",
    },
    "kafka.broker.messagesInPerSec": {
        "zabbix_key": 'jmx["kafka.server:type=BrokerTopicMetrics,name=MessagesInPerSec","OneMinuteRate"]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "每秒流入消息数",
    },
    "kafka.broker.leaderCount": {
        "zabbix_key": 'jmx["kafka.server:type=ReplicaManager,name=LeaderCount","Value"]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "Leader 分区数",
    },
    "kafka.broker.partitionCount": {
        "zabbix_key": 'jmx["kafka.server:type=ReplicaManager,name=PartitionCount","Value"]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "总分区数",
    },
    "kafka.broker.underReplicatedPartitions": {
        "zabbix_key": 'jmx["kafka.server:type=ReplicaManager,name=UnderReplicatedPartitions","Value"]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "欠复制分区数",
    },
    "kafka.broker.activeControllerCount": {
        "zabbix_key": 'jmx["kafka.controller:type=KafkaController,name=ActiveControllerCount","Value"]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "活跃 Controller 数",
    },
    "kafka.broker.offlinePartitions": {
        "zabbix_key": 'jmx["kafka.controller:type=KafkaController,name=OfflinePartitionsCount","Value"]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "离线分区数",
    },
    # ════════════════════════════════════════════════════════
    # Zookeeper（HTTP）
    # ════════════════════════════════════════════════════════
    "zk.AvailableData.AvailabilityData": {
        "zabbix_key": "zookeeper.mntr",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Zookeeper 可用性",
    },
    "zk.zk.zk_avg_latency": {
        "zabbix_key": "zookeeper.avg_latency",
        "is_prototype": False,
        "confidence": "high",
        "notes": "平均延迟",
    },
    "zk.zk.zk_max_latency": {
        "zabbix_key": "zookeeper.max_latency",
        "is_prototype": False,
        "confidence": "high",
        "notes": "最大延迟",
    },
    "zk.zk.zk_min_latency": {
        "zabbix_key": "zookeeper.min_latency",
        "is_prototype": False,
        "confidence": "high",
        "notes": "最小延迟",
    },
    "zk.zk.zk_outstanding_requests": {
        "zabbix_key": "zookeeper.outstanding_requests",
        "is_prototype": False,
        "confidence": "high",
        "notes": "待处理请求数",
    },
    "zk.zk.zk_watch_count": {
        "zabbix_key": "zookeeper.watch_count",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Watch 数量",
    },
    "zk.zk.zk_server_state": {
        "zabbix_key": "zookeeper.server_state",
        "is_prototype": False,
        "confidence": "high",
        "notes": "服务器角色（leader/follower/standalone）",
    },
    "zk.zk.zk_num_alive_connections": {
        "zabbix_key": "zookeeper.num_alive_connections",
        "is_prototype": False,
        "confidence": "high",
        "notes": "活跃连接数",
    },
    "zk.zk.zk_znode_count": {
        "zabbix_key": "zookeeper.znode_count",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Znode 数量",
    },
    "zk.zk.zk_heap_size": {
        "zabbix_key": "zookeeper.heap_size",
        "is_prototype": False,
        "confidence": "high",
        "notes": "JVM 堆内存大小",
    },
    "zk.version.Version": {
        "zabbix_key": "zookeeper.version",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Zookeeper 版本",
    },
    # ════════════════════════════════════════════════════════
    # Etcd（HTTP）
    # ════════════════════════════════════════════════════════
    "etcd.AvailableData.AvailabilityData": {
        "zabbix_key": "etcd.health",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Etcd 健康检查",
    },
    "etcd.health.health": {
        "zabbix_key": "etcd.health",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Etcd 健康状态",
    },
    "etcd.state.state": {
        "zabbix_key": "etcd.self.state",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Etcd 节点状态（leader/follower）",
    },
    "etcd.state.leader": {
        "zabbix_key": "etcd.self.leader",
        "is_prototype": False,
        "confidence": "high",
        "notes": "是否为 Leader",
    },
    # ════════════════════════════════════════════════════════
    # Generic Java JMX
    # ════════════════════════════════════════════════════════
    "jrt.AvailableData.AvailabilityData": {
        "zabbix_key": 'jmx["java.lang:type=Runtime",Uptime]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "JVM 可用性（JMX 连通性）",
    },
    "jrt.heap.HeapUsed": {
        "zabbix_key": 'jmx["java.lang:type=Memory",HeapMemoryUsage.used]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "堆内存已用",
    },
    "jrt.heap.HeapCommitted": {
        "zabbix_key": 'jmx["java.lang:type=Memory",HeapMemoryUsage.committed]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "堆内存已提交",
    },
    "jrt.heap.HeapMax": {
        "zabbix_key": 'jmx["java.lang:type=Memory",HeapMemoryUsage.max]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "堆内存最大值",
    },
    "jrt.nonheap.NonHeapUsed": {
        "zabbix_key": 'jmx["java.lang:type=Memory",NonHeapMemoryUsage.used]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "非堆内存已用",
    },
    "jrt.class.LoadedClassCount": {
        "zabbix_key": 'jmx["java.lang:type=ClassLoading",LoadedClassCount]',
        "is_prototype": False,
        "confidence": "high",
        "notes": "已加载类数量",
    },
    # ════════════════════════════════════════════════════════
    # Docker（Zabbix agent 2）
    # ════════════════════════════════════════════════════════
    "docker.AvailableData.AvailabilityData": {
        "zabbix_key": "docker.data_usage",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Docker 可用性（通过 socket 获取磁盘使用）",
    },
    "docker.info.Containers": {
        "zabbix_key": "docker.info[Containers]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "容器总数",
    },
    "docker.info.ContainersRunning": {
        "zabbix_key": "docker.info[ContainersRunning]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "运行中容器数",
    },
    "docker.info.ContainersPaused": {
        "zabbix_key": "docker.info[ContainersPaused]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "暂停容器数",
    },
    "docker.info.ContainersStopped": {
        "zabbix_key": "docker.info[ContainersStopped]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "停止容器数",
    },
    "docker.info.Images": {
        "zabbix_key": "docker.info[Images]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "镜像总数",
    },
    "docker.info.MemTotal": {
        "zabbix_key": "docker.info[MemTotal]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Docker 宿主机内存总量",
    },
    "docker.container.Name": {
        "zabbix_key": "docker.containers.discovery",
        "is_prototype": False,
        "confidence": "high",
        "notes": "容器发现规则",
    },
    "docker.container.Status": {
        "zabbix_key": "docker.container_info[{#NAME},State,Status]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "容器状态（LLD）",
    },
    "docker.container.Running": {
        "zabbix_key": "docker.container_info[{#NAME},State,Running]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "容器是否运行（LLD）",
    },
    "docker.stats.CpuPercentage": {
        "zabbix_key": "docker.container_stats[{#NAME},cpu_percent]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "容器 CPU 使用率（LLD）",
    },
    "docker.stats.MemoryUsed": {
        "zabbix_key": "docker.container_stats[{#NAME},memory_usage]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "容器内存使用（LLD）",
    },
    # ════════════════════════════════════════════════════════
    # Kubernetes cluster state（HTTP）
    # ════════════════════════════════════════════════════════
    "k8s.AvailableData.AvailabilityData": {
        "zabbix_key": "kube.api.version",
        "is_prototype": False,
        "confidence": "high",
        "notes": "K8s API 可用性",
    },
    "k8s.detail.version": {
        "zabbix_key": "kube.api.version",
        "is_prototype": False,
        "confidence": "high",
        "notes": "K8s API 版本",
    },
    "k8s.namespace.NamespaceName": {
        "zabbix_key": "kube.namespace.discovery",
        "is_prototype": False,
        "confidence": "high",
        "notes": "命名空间发现规则",
    },
    "k8s.node.NodeName": {
        "zabbix_key": "kube.nodes.discovery",
        "is_prototype": False,
        "confidence": "high",
        "notes": "节点发现规则",
    },
    "k8s.node.CpuAllocatable": {
        "zabbix_key": "kube.node.cpu_allocatable[{#NAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "节点可分配 CPU（LLD）",
    },
    "k8s.node.MemAllocatable": {
        "zabbix_key": "kube.node.memory_allocatable[{#NAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "节点可分配内存（LLD）",
    },
    "k8s.pod.PodName": {
        "zabbix_key": "kube.pod.discovery",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Pod 发现规则",
    },
    "k8s.pod.PodStatus": {
        "zabbix_key": "kube.pod.phase.running[{#NAMESPACE}/{#NAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "Pod 运行状态（LLD）",
    },
    "k8s.pod.ContainersReady": {
        "zabbix_key": "kube.pod.containers_ready[{#NAMESPACE}/{#NAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "Pod 容器就绪数（LLD）",
    },
    "k8s.pod.ContainerRestarts": {
        "zabbix_key": "kube.pod.containers_restarts[{#NAMESPACE}/{#NAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "Pod 容器重启次数（LLD）",
    },
    "k8s.deployment.Replicas": {
        "zabbix_key": "kube.deployment.replicas[{#NAMESPACE}/{#NAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "Deployment 副本数（LLD）",
    },
    "k8s.deployment.ReplicasAvailable": {
        "zabbix_key": "kube.deployment.replicas_available[{#NAMESPACE}/{#NAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "Deployment 可用副本数（LLD）",
    },
    "k8s.pv.PvName": {
        "zabbix_key": "kube.pv.discovery",
        "is_prototype": False,
        "confidence": "high",
        "notes": "PV 发现规则",
    },
    "k8s.pv.capacity": {
        "zabbix_key": "kube.pv.capacity.bytes[{#NAME}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "PV 容量（LLD）",
    },
    # ════════════════════════════════════════════════════════
    # VMware（SIMPLE check via Zabbix server）
    # ════════════════════════════════════════════════════════
    "vcenter.AvailableData.AvailabilityData": {
        "zabbix_key": "vmware.fullname[{$VMWARE.URL}]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "VMware vCenter 可用性",
    },
    "vmware.AvailableData.AvailabilityData": {
        "zabbix_key": "vmware.hv.status[{$VMWARE.URL},{$VMWARE.HV.UUID}]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "VMware ESX 主机可用性",
    },
    "vmware.cpu.CpuUtilization": {
        "zabbix_key": "vmware.hv.cpu.usage[{$VMWARE.URL},{$VMWARE.HV.UUID}]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "ESX 主机 CPU 使用率",
    },
    "vmware.memory.MemUsed": {
        "zabbix_key": "vmware.hv.memory.used[{$VMWARE.URL},{$VMWARE.HV.UUID}]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "ESX 主机内存使用量",
    },
    "vmware.memory.MemSize": {
        "zabbix_key": "vmware.hv.memory.size.ballooned[{$VMWARE.URL},{$VMWARE.HV.UUID}]",
        "is_prototype": False,
        "confidence": "medium",
        "notes": "ESX 主机内存大小",
    },
    "vmware.vm.CpuUtilization": {
        "zabbix_key": "vmware.vm.cpu.num[{$VMWARE.URL},{$VMWARE.VM.UUID}]",
        "is_prototype": False,
        "confidence": "medium",
        "notes": "VM CPU 数量（利用率由 vmware.vm.cpu.usage 获取）",
    },
    "vmware.vm.MemUsed": {
        "zabbix_key": "vmware.vm.memory.size.consumed[{$VMWARE.URL},{$VMWARE.VM.UUID}]",
        "is_prototype": False,
        "confidence": "high",
        "notes": "VM 已使用内存",
    },
    # ════════════════════════════════════════════════════════
    # IIS（Zabbix agent）
    # ════════════════════════════════════════════════════════
    "iis.AvailableData.AvailabilityData": {
        "zabbix_key": "iis.get",
        "is_prototype": False,
        "confidence": "high",
        "notes": "IIS 可用性",
    },
    "iis.site.requestsPerSec": {
        "zabbix_key": 'web.service.perf.counter["Web Service(*)/Total Method Requests/sec"]',
        "is_prototype": False,
        "confidence": "medium",
        "notes": "IIS 每秒请求数（Windows 性能计数器）",
    },
    # ════════════════════════════════════════════════════════
    # Brocade FC（SNMP）
    # ════════════════════════════════════════════════════════
    "brocade.AvailableData.AvailabilityData": {
        "zabbix_key": "icmpping",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Brocade 设备可用性",
    },
    "brocade.basic.MemUtilization": {
        "zabbix_key": "brocade.fc.mem.usage",
        "is_prototype": False,
        "confidence": "high",
        "notes": "内存利用率",
    },
    "brocade.basic.CpuUtilization": {
        "zabbix_key": "brocade.fc.cpu.usage",
        "is_prototype": False,
        "confidence": "high",
        "notes": "CPU 利用率",
    },
    "brocade.port.txPerSec": {
        "zabbix_key": "brocade.fc.port.tx[{#SNMPINDEX}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "FC 端口发送速率（LLD）",
    },
    "brocade.port.rxPerSec": {
        "zabbix_key": "brocade.fc.port.rx[{#SNMPINDEX}]",
        "is_prototype": True,
        "confidence": "high",
        "notes": "FC 端口接收速率（LLD）",
    },
    # ════════════════════════════════════════════════════════
    # Hadoop（HTTP）
    # ════════════════════════════════════════════════════════
    "hadoop.AvailableData.AvailabilityData": {
        "zabbix_key": "hadoop.namenode.jmx",
        "is_prototype": False,
        "confidence": "high",
        "notes": "Hadoop NameNode 可用性",
    },
    "hadoop.dfs.DfsCapacity": {
        "zabbix_key": "hadoop.namenode.blocks_total",
        "is_prototype": False,
        "confidence": "medium",
        "notes": "HDFS 总容量",
    },
    "hadoop.dfs.DfsUsed": {
        "zabbix_key": "hadoop.namenode.capacity_used",
        "is_prototype": False,
        "confidence": "high",
        "notes": "HDFS 已用容量",
    },
    "hadoop.dfs.DfsUtilization": {
        "zabbix_key": "hadoop.namenode.capacity_remaining_pc",
        "is_prototype": False,
        "confidence": "medium",
        "notes": "HDFS 利用率（Zabbix 存剩余百分比）",
    },
    "hadoop.namenode.liveDataNodes": {
        "zabbix_key": "hadoop.namenode.num_live_data_nodes",
        "is_prototype": False,
        "confidence": "high",
        "notes": "活跃 DataNode 数",
    },
    "hadoop.namenode.deadDataNodes": {
        "zabbix_key": "hadoop.namenode.num_dead_data_nodes",
        "is_prototype": False,
        "confidence": "high",
        "notes": "死亡 DataNode 数",
    },
    # ════════════════════════════════════════════════════════
    # PHP-FPM（HTTP）
    # ════════════════════════════════════════════════════════
    "php.AvailableData.AvailabilityData": {
        "zabbix_key": "php-fpm.get_status",
        "is_prototype": False,
        "confidence": "high",
        "notes": "PHP-FPM 可用性",
    },
    "php.status.active_processes": {
        "zabbix_key": "php-fpm.processes.active",
        "is_prototype": False,
        "confidence": "high",
        "notes": "活跃进程数",
    },
    "php.status.idle_processes": {
        "zabbix_key": "php-fpm.processes.idle",
        "is_prototype": False,
        "confidence": "high",
        "notes": "空闲进程数",
    },
    "php.status.total_processes": {
        "zabbix_key": "php-fpm.processes.total",
        "is_prototype": False,
        "confidence": "high",
        "notes": "总进程数",
    },
    "php.status.accepted_conn": {
        "zabbix_key": "php-fpm.connections.accepted",
        "is_prototype": False,
        "confidence": "high",
        "notes": "已接受连接数",
    },
    "php.pool.pool_name": {
        "zabbix_key": "php-fpm.discovery",
        "is_prototype": False,
        "confidence": "high",
        "notes": "PHP-FPM 进程池发现",
    },
    # ════════════════════════════════════════════════════════
    # Kylin / KylinOS / UOS / Rocky / Suse（复用 Linux 映射）
    # ════════════════════════════════════════════════════════
}

# 为 kylin/kylinos/uos/rocky/suse 复制 linux 的映射
_LINUX_LIKE = ["kylin", "kylinos", "uos", "rocky", "suse"]
_linux_entries = {k: v for k, v in EXACT_FIELD_MAP.items() if k.startswith("linux.")}
for _os in _LINUX_LIKE:
    for _lk, _lv in _linux_entries.items():
        _new_key = _lk.replace("linux.", f"{_os}.", 1)
        if _new_key not in EXACT_FIELD_MAP:
            EXACT_FIELD_MAP[_new_key] = _lv.copy()


# ── 告警级别映射 ──────────────────────────────────────────────────────────────
H3C_LEVEL_TO_ZABBIX_SEVERITY: dict[int, str] = {
    1: "INFO",  # 提示 → Information
    2: "WARNING",  # 一般 → Warning
    3: "AVERAGE",  # 次要 → Average
    4: "HIGH",  # 重要 → High
    5: "DISASTER",  # 紧急 → Disaster
}

# ── 告警运算符映射 ────────────────────────────────────────────────────────────
H3C_OPERATOR_TO_ZABBIX: dict[str, str] = {
    "GT": ">",
    "GE": ">=",
    "LT": "<",
    "LE": "<=",
    "EQ": "=",
    "NEQ": "<>",
    "IC": "like",  # 包含（字符串 find like）
    "EC": "not like",  # 不包含
    "RULE": "regexp",  # 正则/多值匹配
    "CHG": "change",  # 值变化
    "CT": ">=",  # 持续超阈值（结合 trigger 次数）
    "DC": "<=",  # 持续低于阈值
}


# ═════════════════════════════════════════════════════════════════════════════
# 核心逻辑
# ═════════════════════════════════════════════════════════════════════════════


def load_h3c_templates() -> list[dict]:
    """加载所有华三模板 JSON"""
    templates = []
    for f in sorted(H3C_DETAILS_DIR.glob("*.json")):
        try:
            templates.append(json.loads(f.read_text("utf-8")))
        except Exception as e:
            print(f"  [WARN] 读取 {f.name} 失败: {e}", file=sys.stderr)
    return templates


def load_zabbix_dump() -> dict:
    """加载 Zabbix keys dump"""
    if not ZABBIX_DUMP.exists():
        print(f"[ERROR] 找不到 {ZABBIX_DUMP}", file=sys.stderr)
        print("请先运行: python3 scripts/dump_zabbix_keys.py", file=sys.stderr)
        sys.exit(1)
    return json.loads(ZABBIX_DUMP.read_text("utf-8"))


def build_zabbix_key_index(dump: dict) -> dict[str, dict]:
    """
    构建全局 key 索引: key_str -> item_info
    合并 items 和 item_prototypes
    """
    index: dict[str, dict] = {}
    for tname, tdata in dump["by_template"].items():
        for item in tdata["items"] + tdata["item_prototypes"]:
            k = item["key"]
            if k not in index:
                index[k] = {
                    "name": item["name"],
                    "type": item["type"],
                    "value_type": item["value_type"],
                    "units": item.get("units") or "",
                    "is_prototype": item.get("is_prototype", False),
                    "template": tname,
                }
    return index


def match_field(
    h3c_type: str,
    unit_key: str,
    field_key: str,
    field_name_zh: str,
    field_unit: str,
    zabbix_key_index: dict,
) -> dict | None:
    """
    匹配华三字段到 Zabbix item key。
    优先使用精确映射表，其次尝试关键词推断。
    """
    # 1. 精确映射
    exact_key = f"{h3c_type}.{unit_key}.{field_key}"
    if exact_key in EXACT_FIELD_MAP:
        m = EXACT_FIELD_MAP[exact_key]
        zk = m["zabbix_key"]
        zi = zabbix_key_index.get(zk)
        return {
            "match_method": "exact",
            "zabbix_key": zk,
            "is_prototype": m["is_prototype"],
            "confidence": m["confidence"],
            "notes": m.get("notes", ""),
            "zabbix_item_name": zi["name"]
            if zi
            else "(key defined in mapping, not found in current Zabbix templates)",
            "zabbix_item_type": zi["type"] if zi else "UNKNOWN",
            "zabbix_units": zi["units"] if zi else "",
        }

    # 2. 可用性通用兜底
    if unit_key == "AvailableData" and field_key == "AvailabilityData":
        return {
            "match_method": "fallback_availability",
            "zabbix_key": "icmpping",
            "is_prototype": False,
            "confidence": "high",
            "notes": "通用可用性 ICMP ping",
            "zabbix_item_name": "ICMP ping",
            "zabbix_item_type": "SIMPLE",
            "zabbix_units": "",
        }

    # 3. 关键词推断
    fl = field_key.lower()
    nl = field_name_zh.lower()

    # CPU 利用率
    if ("cpu" in fl or "cpu" in nl) and (
        "util" in fl or "usage" in fl or "利用率" in nl or "percent" in fl
    ):
        return {
            "match_method": "keyword_infer",
            "zabbix_key": "system.cpu.util",
            "is_prototype": False,
            "confidence": "medium",
            "notes": "CPU 利用率关键词推断",
            "zabbix_item_name": "CPU utilization",
            "zabbix_item_type": "DEPENDENT",
            "zabbix_units": "%",
        }

    # 内存利用率
    if ("mem" in fl or "memory" in fl or "内存" in nl) and (
        "util" in fl or "pused" in fl or "利用率" in nl or "usage" in fl
    ):
        return {
            "match_method": "keyword_infer",
            "zabbix_key": "vm.memory.utilization",
            "is_prototype": False,
            "confidence": "medium",
            "notes": "内存利用率关键词推断",
            "zabbix_item_name": "Memory utilization",
            "zabbix_item_type": "DEPENDENT",
            "zabbix_units": "%",
        }

    # 磁盘/文件系统利用率
    if ("disk" in fl or "filesystem" in fl or "磁盘" in nl or "文件系统" in nl) and (
        "util" in fl or "pused" in fl or "利用率" in nl or "usage" in fl
    ):
        return {
            "match_method": "keyword_infer",
            "zabbix_key": "vfs.fs.dependent.size[{#FSNAME},pused]",
            "is_prototype": True,
            "confidence": "medium",
            "notes": "文件系统利用率关键词推断（LLD）",
            "zabbix_item_name": "Filesystem utilization",
            "zabbix_item_type": "DEPENDENT",
            "zabbix_units": "%",
        }

    # 系统负载
    if "load" in fl or "负载" in nl:
        suffix = (
            "avg1"
            if "1" in fl and "15" not in fl
            else "avg15"
            if "15" in fl
            else "avg5"
        )
        return {
            "match_method": "keyword_infer",
            "zabbix_key": f"system.cpu.load[all,{suffix}]",
            "is_prototype": False,
            "confidence": "medium",
            "notes": f"系统负载关键词推断 ({suffix})",
            "zabbix_item_name": f"Load average ({suffix})",
            "zabbix_item_type": "ZABBIX_PASSIVE",
            "zabbix_units": "",
        }

    # 接口接收
    if ("rx" in fl or "receive" in fl or "接收" in nl) and (
        "sec" in fl or "rate" in fl or "速率" in nl
    ):
        return {
            "match_method": "keyword_infer",
            "zabbix_key": 'net.if.in["{#IFNAME}"]',
            "is_prototype": True,
            "confidence": "medium",
            "notes": "接口接收速率关键词推断（LLD）",
            "zabbix_item_name": "Interface receive rate",
            "zabbix_item_type": "ZABBIX_PASSIVE",
            "zabbix_units": "bps",
        }

    # 接口发送
    if ("tx" in fl or "transmit" in fl or "发送" in nl) and (
        "sec" in fl or "rate" in fl or "速率" in nl
    ):
        return {
            "match_method": "keyword_infer",
            "zabbix_key": 'net.if.out["{#IFNAME}"]',
            "is_prototype": True,
            "confidence": "medium",
            "notes": "接口发送速率关键词推断（LLD）",
            "zabbix_item_name": "Interface transmit rate",
            "zabbix_item_type": "ZABBIX_PASSIVE",
            "zabbix_units": "bps",
        }

    # Ping 响应时间
    if h3c_type in ("ping", "pingcmd") and ("response" in fl or "响应" in nl):
        return {
            "match_method": "keyword_infer",
            "zabbix_key": "icmppingsec",
            "is_prototype": False,
            "confidence": "medium",
            "notes": "Ping 响应时间推断",
            "zabbix_item_name": "ICMP ping response time",
            "zabbix_item_type": "SIMPLE",
            "zabbix_units": "s",
        }

    return None


def build_trigger_expression(
    operator: str,
    field_key: str,
    value: str,
    trigger_count: int,
    collect_time: int,
    is_prototype: bool,
    zabbix_key: str,
) -> str:
    """
    根据华三阈值配置，生成 Zabbix Trigger 表达式字符串（仅示意，实际需替换 host/key）。
    """
    zop = H3C_OPERATOR_TO_ZABBIX.get(operator, ">=")
    host_key = f"{{HOSTNAME}}:{zabbix_key}"

    if operator in ("IC", "EC"):
        # 字符串包含/不包含
        op_func = "like" if operator == "IC" else "not like"
        return f'find(/{host_key},,"{op_func}","{value}")=1'

    if operator == "RULE":
        # 正则/多值
        return f'find(/{host_key},,"regexp","{value}")=1'

    if operator == "CHG":
        return f"change(/{host_key})<>0"

    if trigger_count > 1 and collect_time > 0:
        # 持续 N 次触发：使用 count 函数
        window_sec = collect_time * trigger_count
        return f'count(/{host_key},{window_sec}s,"{zop}","{value}")>={trigger_count}'

    return f"last(/{host_key}){zop}{value}"


def analyze_template(tpl: dict, zabbix_key_index: dict) -> dict:
    """分析单个华三模板，输出映射分析结果"""
    h3c_type = tpl.get("type", "")
    tpl_name = tpl.get("name", "")
    unit_list = tpl.get("unitList", [])
    thresholds = tpl.get("thresholds", [])

    result: dict = {
        "h3c_template_id": str(tpl.get("templateId", "")),
        "h3c_type": h3c_type,
        "h3c_name": tpl_name,
        "h3c_name_en": tpl.get("nameEn", ""),
        "zabbix_templates": H3C_TYPE_TO_ZABBIX_TEMPLATES.get(h3c_type, []),
        "units": [],
        "triggers_converted": [],
        "stats": {
            "total_units": 0,
            "total_fields": 0,
            "exact_matched": 0,
            "keyword_matched": 0,
            "unmatched": 0,
            "lld_units": 0,
        },
    }

    # ── 分析 unitList ──
    for unit in unit_list:
        unit_key = unit.get("unit", "")
        unit_name_zh = unit.get("nameZh", "")
        data_type = unit.get("dataType", "")
        scope = unit.get("scope", 3)
        collect_time = unit.get("collectTime", 300)
        is_lld = scope == 1 and data_type == "table"

        unit_result: dict = {
            "unit_key": unit_key,
            "unit_name_zh": unit_name_zh,
            "unit_name_en": unit.get("nameEn", ""),
            "data_type": data_type,
            "scope": scope,
            "collect_time": collect_time,
            "is_lld": is_lld,
            "fields": [],
        }

        result["stats"]["total_units"] += 1
        if is_lld:
            result["stats"]["lld_units"] += 1

        for field in unit.get("fields", []):
            fkey = field.get("field", "")
            fname_zh = field.get("nameZh", "")
            funit = field.get("fieldUnit") or ""
            value_type_raw = field.get("valueType", 0)
            alarm_inst = field.get("alarmInst", 0)
            enable_thr = field.get("enableThreshold", True)
            explain_zh = (field.get("explainZh") or "").strip()[:300]

            result["stats"]["total_fields"] += 1

            match = match_field(
                h3c_type, unit_key, fkey, fname_zh, funit, zabbix_key_index
            )

            if match:
                if match["match_method"] == "exact":
                    result["stats"]["exact_matched"] += 1
                else:
                    result["stats"]["keyword_matched"] += 1
            else:
                result["stats"]["unmatched"] += 1

            field_result: dict = {
                "field_key": fkey,
                "field_name_zh": fname_zh,
                "field_name_en": field.get("nameEn", ""),
                "field_unit": funit,
                "value_type": "string" if value_type_raw == 1 else "numeric",
                "alarm_inst": alarm_inst,
                "enable_threshold": enable_thr,
                "explain_zh": explain_zh,
                "zabbix_match": match,
            }
            unit_result["fields"].append(field_result)

        result["units"].append(unit_result)

    # ── 转换 thresholds ──
    for thr in thresholds:
        conditions = thr.get("conditions", [])
        value_type_str = thr.get("valueType", "Multistage")

        for cond in conditions:
            unit_k = cond.get("unit", "")
            field_k = cond.get("field", "")
            operator = cond.get("operator", "GE")
            threshold_levels = cond.get("threshold", [])

            # 找对应的 zabbix key
            exact_lookup = f"{h3c_type}.{unit_k}.{field_k}"
            zabbix_key_ref = None
            is_proto = False
            if exact_lookup in EXACT_FIELD_MAP:
                zabbix_key_ref = EXACT_FIELD_MAP[exact_lookup]["zabbix_key"]
                is_proto = EXACT_FIELD_MAP[exact_lookup]["is_prototype"]

            if not zabbix_key_ref:
                continue

            for level_entry in threshold_levels:
                if not level_entry.get("enable", False):
                    continue
                level_num = level_entry.get("level", 5)
                threshold_val = str(level_entry.get("value", ""))
                trigger_count = level_entry.get("trigger", 1)

                # 找对应单元的采集间隔
                collect_t = 300
                for u in result["units"]:
                    if u["unit_key"] == unit_k:
                        collect_t = u["collect_time"]
                        break

                expr = build_trigger_expression(
                    operator,
                    field_k,
                    threshold_val,
                    trigger_count,
                    collect_t,
                    is_proto,
                    zabbix_key_ref,
                )

                result["triggers_converted"].append(
                    {
                        "unit_key": unit_k,
                        "field_key": field_k,
                        "zabbix_key": zabbix_key_ref,
                        "is_prototype": is_proto,
                        "h3c_operator": operator,
                        "h3c_level": level_num,
                        "zabbix_severity": H3C_LEVEL_TO_ZABBIX_SEVERITY.get(
                            level_num, "AVERAGE"
                        ),
                        "threshold_value": threshold_val,
                        "trigger_count": trigger_count,
                        "collect_time": collect_t,
                        "zabbix_expression_template": expr,
                    }
                )

    # ── 计算转换等级 ──
    total = result["stats"]["total_fields"]
    matched = result["stats"]["exact_matched"] + result["stats"]["keyword_matched"]
    exact = result["stats"]["exact_matched"]
    has_zabbix = bool(result["zabbix_templates"])
    exact_ratio = exact / total if total > 0 else 0
    match_ratio = matched / total if total > 0 else 0

    result["match_ratio"] = round(match_ratio, 3)
    result["exact_ratio"] = round(exact_ratio, 3)
    result["matched_fields"] = matched

    if has_zabbix and exact_ratio >= 0.5:
        tier = "full"
    elif has_zabbix and matched > 0:
        tier = "partial"
    elif not has_zabbix and matched > 0:
        tier = "skeleton"
    else:
        tier = "none"
    result["conversion_tier"] = tier

    return result


def compute_report(results: list[dict]) -> dict:
    tier_counts: dict[str, int] = defaultdict(int)
    type_summary: dict[str, dict] = {}

    for r in results:
        tier_counts[r["conversion_tier"]] += 1
        h3c_type = r["h3c_type"]
        if h3c_type not in type_summary:
            type_summary[h3c_type] = {
                "templates": [],
                "zabbix_templates": r["zabbix_templates"],
            }
        type_summary[h3c_type]["templates"].append(
            {
                "name": r["h3c_name"],
                "tier": r["conversion_tier"],
                "match_ratio": r["match_ratio"],
                "exact_ratio": r["exact_ratio"],
                "matched_fields": r["matched_fields"],
                "total_fields": r["stats"]["total_fields"],
                "triggers_converted": len(r["triggers_converted"]),
            }
        )

    return {
        "generated_at": datetime.now().isoformat(),
        "zabbix_version": "7.0.23",
        "totals": {
            "h3c_templates": len(results),
            "full": tier_counts["full"],
            "partial": tier_counts["partial"],
            "skeleton": tier_counts["skeleton"],
            "none": tier_counts["none"],
        },
        "by_h3c_type": type_summary,
    }


def write_outputs(results: list[dict], report: dict, zabbix_dump: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. 完整分析 JSON ──
    full_path = OUTPUT_DIR / "h3c_to_zabbix_full_analysis.json"
    full_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(),
                "report": report,
                "templates": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )
    print(f"  ✅ {full_path}")

    # ── 2. 可转换模板（full + partial）精简版 ──
    convertible = [
        {
            "h3c_template_id": r["h3c_template_id"],
            "h3c_type": r["h3c_type"],
            "h3c_name": r["h3c_name"],
            "conversion_tier": r["conversion_tier"],
            "match_ratio": r["match_ratio"],
            "exact_ratio": r["exact_ratio"],
            "zabbix_templates": r["zabbix_templates"],
            "stats": r["stats"],
            "triggers_count": len(r["triggers_converted"]),
            "units": [
                {
                    "unit_key": u["unit_key"],
                    "unit_name_zh": u["unit_name_zh"],
                    "is_lld": u["is_lld"],
                    "collect_time": u["collect_time"],
                    "matched_fields": [
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
                    "unmatched_fields": [
                        {
                            "field_key": f["field_key"],
                            "field_name_zh": f["field_name_zh"],
                            "field_unit": f["field_unit"],
                        }
                        for f in u["fields"]
                        if f["zabbix_match"] is None
                    ],
                }
                for u in r["units"]
            ],
            "triggers_converted": r["triggers_converted"],
        }
        for r in results
        if r["conversion_tier"] in ("full", "partial")
    ]
    conv_path = OUTPUT_DIR / "h3c_convertible_templates.json"
    conv_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(),
                "total_convertible": len(convertible),
                "templates": convertible,
            },
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )
    print(f"  ✅ {conv_path}")

    # ── 3. 字段映射表（供转换器直接引用）──
    mapping_path = OUTPUT_DIR / "field_mapping_table.json"
    mapping_path.write_text(
        json.dumps(
            {
                "exact_field_map": EXACT_FIELD_MAP,
                "h3c_type_to_zabbix_templates": H3C_TYPE_TO_ZABBIX_TEMPLATES,
                "h3c_level_to_zabbix_severity": {
                    str(k): v for k, v in H3C_LEVEL_TO_ZABBIX_SEVERITY.items()
                },
                "h3c_operator_to_zabbix": H3C_OPERATOR_TO_ZABBIX,
            },
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )
    print(f"  ✅ {mapping_path}")

    # ── 4. Markdown 报告 ──
    md: list[str] = [
        "# 华三监控模板 → Zabbix 转换可行性分析",
        "",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"**Zabbix 版本**: {report['zabbix_version']}  ",
        f"**华三模板总数**: {report['totals']['h3c_templates']}",
        "",
        "## 转换等级说明",
        "",
        "| 等级 | 含义 |",
        "|------|------|",
        "| 🟢 **full** | Zabbix 有对应模板且精确字段匹配率 ≥ 50%，可自动生成大部分 Items 和 Triggers |",
        "| 🟡 **partial** | Zabbix 有对应模板但精确匹配率 < 50%，可生成部分 Items |",
        "| 🔵 **skeleton** | Zabbix 无直接对应模板，但有通用字段匹配（如 CPU、内存），可生成框架 |",
        "| 🔴 **none** | 未归类或华三私有 API，暂无 Zabbix 对应实现 |",
        "",
        "## 汇总统计",
        "",
        f"- 🟢 **full**:    {report['totals']['full']} 个模板",
        f"- 🟡 **partial**: {report['totals']['partial']} 个模板",
        f"- 🔵 **skeleton**: {report['totals']['skeleton']} 个模板",
        f"- 🔴 **none**:    {report['totals']['none']} 个模板",
        "",
        "## 可转换模板明细",
        "",
        "| 华三模板名 | 类型 | 等级 | 精确匹配率 | 总匹配率 | 匹配字段 / 总字段 | 可转触发器 | 对应 Zabbix 模板 |",
        "|-----------|------|------|-----------|---------|----------------|-----------|----------------|",
    ]
    full_partial = sorted(
        [r for r in results if r["conversion_tier"] in ("full", "partial")],
        key=lambda x: (-x["exact_ratio"], -x["match_ratio"], x["h3c_name"]),
    )
    for r in full_partial:
        icon = "🟢" if r["conversion_tier"] == "full" else "🟡"
        ztpls = ", ".join(r["zabbix_templates"])
        md.append(
            f"| {r['h3c_name']} | `{r['h3c_type']}` | {icon} {r['conversion_tier']} "
            f"| {r['exact_ratio'] * 100:.0f}% "
            f"| {r['match_ratio'] * 100:.0f}% "
            f"| {r['matched_fields']}/{r['stats']['total_fields']} "
            f"| {len(r['triggers_converted'])} "
            f"| {ztpls} |"
        )

    md += [
        "",
        "## 精确字段映射表统计",
        "",
        f"- 精确映射条目数: **{len(EXACT_FIELD_MAP)}**",
        f"- 覆盖华三类型: **{len(H3C_TYPE_TO_ZABBIX_TEMPLATES)}** 种",
        "",
        "## 告警级别对照",
        "",
        "| 华三级别 | 华三名称 | Zabbix Severity |",
        "|---------|---------|----------------|",
    ]
    for num, name in [(1, "提示"), (2, "一般"), (3, "次要"), (4, "重要"), (5, "紧急")]:
        md.append(f"| {num} | {name} | {H3C_LEVEL_TO_ZABBIX_SEVERITY[num]} |")

    md += [
        "",
        "## 告警运算符对照",
        "",
        "| 华三运算符 | 含义 | Zabbix 表达式 |",
        "|-----------|------|-------------|",
    ]
    for op, zop in H3C_OPERATOR_TO_ZABBIX.items():
        md.append(f"| `{op}` | | `{zop}` |")

    md += [
        "",
        "## 骨架模板（skeleton）",
        "",
        "以下模板 Zabbix 无直接对应，但有通用指标（CPU/内存等）字段匹配，可生成监控框架：",
        "",
        "| 华三模板名 | 类型 | 匹配字段数 |",
        "|-----------|------|-----------|",
    ]
    skeleton_sorted = sorted(
        [r for r in results if r["conversion_tier"] == "skeleton"],
        key=lambda x: -x["matched_fields"],
    )
    for r in skeleton_sorted:
        md.append(f"| {r['h3c_name']} | `{r['h3c_type']}` | {r['matched_fields']} |")

    md_path = OUTPUT_DIR / "conversion_report.md"
    md_path.write_text("\n".join(md), "utf-8")
    print(f"  ✅ {md_path}")

    # ── 5. Zabbix keys 索引（精简版，去掉 Zabbix dump 原始数据）──
    keys_index_path = OUTPUT_DIR / "zabbix_items_index.json"
    keys_by_tpl: dict[str, list[dict]] = {}
    all_unique: dict[str, dict] = {}
    for tname, tdata in zabbix_dump["by_template"].items():
        keys_by_tpl[tname] = []
        for item in tdata["items"] + tdata["item_prototypes"]:
            entry = {
                "key": item["key"],
                "name": item["name"],
                "type": item["type"],
                "value_type": item["value_type"],
                "units": item.get("units") or "",
                "is_prototype": item.get("is_prototype", False),
            }
            keys_by_tpl[tname].append(entry)
            if item["key"] not in all_unique:
                all_unique[item["key"]] = entry
    keys_index_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(),
                "stats": zabbix_dump["stats"],
                "items_by_template": keys_by_tpl,
                "unique_keys_index": all_unique,
            },
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )
    print(f"  ✅ {keys_index_path}")


# ═════════════════════════════════════════════════════════════════════════════
# 入口
# ═════════════════════════════════════════════════════════════════════════════


def main() -> int:
    print("=" * 68)
    print("华三监控模板 → Zabbix 字段映射数据集构建")
    print("=" * 68)

    # 1. 加载数据
    print("\n📂 加载华三模板数据...")
    h3c_templates = load_h3c_templates()
    print(f"   共加载 {len(h3c_templates)} 个华三模板")

    print("\n📂 加载 Zabbix keys dump...")
    zabbix_dump = load_zabbix_dump()
    print(f"   Zabbix 模板: {zabbix_dump['stats']['templates']}")
    print(f"   Items: {zabbix_dump['stats']['items']}")
    print(f"   Item Prototypes (LLD): {zabbix_dump['stats']['item_prototypes']}")
    print(f"   唯一 keys: {zabbix_dump['stats']['unique_keys']}")

    # 2. 构建 Zabbix key 索引
    print("\n🔧 构建 Zabbix key 索引...")
    zabbix_key_index = build_zabbix_key_index(zabbix_dump)
    print(f"   索引条目: {len(zabbix_key_index)}")

    print(f"\n🗺️  精确字段映射表条目: {len(EXACT_FIELD_MAP)}")

    # 3. 分析所有华三模板
    print("\n🔍 逐模板分析字段映射...")
    results = []
    for tpl in h3c_templates:
        r = analyze_template(tpl, zabbix_key_index)
        results.append(r)

    # 4. 汇总报告
    report = compute_report(results)
    totals = report["totals"]

    print(f"\n{'─' * 60}")
    print("📊 转换分级汇总:")
    print(
        f"   🟢 full     : {totals['full']:4} 个  (精确匹配率 ≥ 50%，Zabbix 有对应模板)"
    )
    print(f"   🟡 partial  : {totals['partial']:4} 个  (有对应模板，精确匹配率 < 50%)")
    print(
        f"   🔵 skeleton : {totals['skeleton']:4} 个  (无直接对应模板，有通用字段匹配)"
    )
    print(f"   🔴 none     : {totals['none']:4} 个  (无法映射)")
    print(f"{'─' * 60}")

    # 打印 full 模板明细
    full_list = sorted(
        [r for r in results if r["conversion_tier"] == "full"],
        key=lambda x: -x["exact_ratio"],
    )
    if full_list:
        print(f"\n🟢 full 等级模板（共 {len(full_list)} 个）:")
        for r in full_list:
            ztpls = ", ".join(r["zabbix_templates"])
            print(
                f"   ✅ {r['h3c_name']:30} exact={r['exact_ratio'] * 100:.0f}%"
                f"  total={r['match_ratio'] * 100:.0f}%"
                f"  fields={r['matched_fields']}/{r['stats']['total_fields']}"
                f"  triggers={len(r['triggers_converted'])}"
            )
            print(f"      → {ztpls}")

    # 打印 partial 模板明细
    partial_list = sorted(
        [r for r in results if r["conversion_tier"] == "partial"],
        key=lambda x: -x["match_ratio"],
    )
    if partial_list:
        print(f"\n🟡 partial 等级模板（共 {len(partial_list)} 个）:")
        for r in partial_list:
            ztpls = ", ".join(r["zabbix_templates"])
            print(
                f"   ⚠  {r['h3c_name']:30} exact={r['exact_ratio'] * 100:.0f}%"
                f"  total={r['match_ratio'] * 100:.0f}%"
                f"  fields={r['matched_fields']}/{r['stats']['total_fields']}"
                f"  triggers={len(r['triggers_converted'])}"
            )
            print(f"      → {ztpls}")

    # 5. 写出文件
    print("\n💾 写出分析结果...")
    write_outputs(results, report, zabbix_dump)

    print(f"\n✨ 完成！输出目录: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
