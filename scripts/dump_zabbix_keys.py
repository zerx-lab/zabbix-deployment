#!/usr/bin/env python3
"""
dump_zabbix_keys.py
从 Zabbix API 拉取关键模板的所有 item key，输出到 output/zabbix-mapping/zabbix_keys_dump.json
同时打印人类可读的摘要到 stdout。
"""

import json
import urllib.request
from collections import defaultdict
from pathlib import Path

API_URL = "http://localhost:8080/api_jsonrpc.php"

# 目标模板名列表（与 analyze_zabbix_items.py 保持一致）
TARGET_TEMPLATES = [
    # OS
    "Linux by Zabbix agent",
    "Linux by Zabbix agent active",
    "Linux by SNMP",
    "Windows by Zabbix agent",
    "Windows by Zabbix agent active",
    "Windows by SNMP",
    "AIX by Zabbix agent",
    "FreeBSD by Zabbix agent",
    "HP-UX by Zabbix agent",
    "Solaris by Zabbix agent",
    "macOS by Zabbix agent",
    # 网络
    "Network Generic Device by SNMP",
    "ICMP Ping",
    "Brocade FC by SNMP",
    "HP Comware HH3C by SNMP",
    "Huawei VRP by SNMP",
    # 数据库
    "MySQL by Zabbix agent 2",
    "MySQL by Zabbix agent",
    "MySQL by ODBC",
    "PostgreSQL by Zabbix agent 2",
    "PostgreSQL by Zabbix agent",
    "Redis by Zabbix agent 2",
    "MongoDB node by Zabbix agent 2",
    "Elasticsearch Cluster by HTTP",
    "MSSQL by Zabbix agent 2",
    "Oracle by Zabbix agent 2",
    "Oracle by ODBC",
    "Memcached by Zabbix agent 2",
    # 应用/中间件
    "Apache Tomcat by JMX",
    "Nginx by HTTP",
    "Nginx by Zabbix agent",
    "Apache by HTTP",
    "RabbitMQ node by HTTP",
    "RabbitMQ cluster by HTTP",
    "Apache Kafka by JMX",
    "Zookeeper by HTTP",
    "IIS by Zabbix agent",
    "PHP-FPM by HTTP",
    "Hadoop by HTTP",
    "Etcd by HTTP",
    "Generic Java JMX",
    "WildFly Server by JMX",
    # 容器/K8s
    "Docker by Zabbix agent 2",
    "Kubernetes cluster state by HTTP",
    "Kubernetes nodes by HTTP",
    "Kubernetes API server by HTTP",
    "Kubernetes Kubelet by HTTP",
    # 虚拟化
    "VMware",
    "VMware Guest",
    "VMware Hypervisor",
]

ITEM_TYPE_MAP = {
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

VALUE_TYPE_MAP = {
    "0": "FLOAT",
    "1": "CHAR",
    "2": "LOG",
    "3": "UNSIGNED",
    "4": "TEXT",
    "5": "BINARY",
}


def api_call(method: str, params: dict, auth: str | None = None) -> dict:
    payload: dict = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    if auth:
        payload["auth"] = auth
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if "error" in result:
        raise RuntimeError(f"API error: {result['error']}")
    return result["result"]


def main() -> None:
    output_dir = Path(__file__).parent.parent / "output" / "zabbix-mapping"
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 登录 ──────────────────────────────────────────────────────────────────
    print("🔐 登录 Zabbix API...")
    token = api_call("user.login", {"username": "Admin", "password": "zabbix"})
    print(f"   token: {token[:20]}...\n")

    # ── 获取目标模板 ───────────────────────────────────────────────────────────
    print("📋 查找目标模板...")
    templates_raw = api_call(
        "template.get",
        {
            "output": ["templateid", "name", "description"],
            "filter": {"name": TARGET_TEMPLATES},
            "sortfield": "name",
        },
        auth=token,
    )
    tpl_id_to_name = {t["templateid"]: t["name"] for t in templates_raw}
    tpl_ids = list(tpl_id_to_name.keys())
    found_names = set(tpl_id_to_name.values())
    not_found = [n for n in TARGET_TEMPLATES if n not in found_names]
    print(f"   找到: {len(templates_raw)} 个模板")
    if not_found:
        print(f"   ⚠ 未找到: {not_found}\n")

    # ── 获取 Items ─────────────────────────────────────────────────────────────
    print("📥 获取 Items (普通)...")
    items_raw = api_call(
        "item.get",
        {
            "output": [
                "itemid",
                "hostid",
                "name",
                "key_",
                "type",
                "value_type",
                "units",
                "delay",
                "description",
                "status",
            ],
            "templateids": tpl_ids,
            "inherited": False,
            "limit": 20000,
        },
        auth=token,
    )
    print(f"   获取: {len(items_raw)} 条\n")

    # ── 获取 Item Prototypes (LLD) ─────────────────────────────────────────────
    print("📥 获取 Item Prototypes (LLD)...")
    protos_raw = api_call(
        "itemprototype.get",
        {
            "output": [
                "itemid",
                "hostid",
                "name",
                "key_",
                "type",
                "value_type",
                "units",
                "delay",
                "description",
                "status",
            ],
            "templateids": tpl_ids,
            "inherited": False,
            "limit": 20000,
        },
        auth=token,
    )
    print(f"   获取: {len(protos_raw)} 条\n")

    # ── 获取 Discovery Rules ───────────────────────────────────────────────────
    print("📥 获取 Discovery Rules (LLD)...")
    lld_rules_raw = api_call(
        "discoveryrule.get",
        {
            "output": [
                "itemid",
                "hostid",
                "name",
                "key_",
                "type",
                "delay",
                "description",
            ],
            "templateids": tpl_ids,
            "inherited": False,
            "limit": 5000,
        },
        auth=token,
    )
    print(f"   获取: {len(lld_rules_raw)} 条\n")

    # ── 获取 Triggers ──────────────────────────────────────────────────────────
    print("📥 获取 Triggers...")
    triggers_raw = api_call(
        "trigger.get",
        {
            "output": [
                "triggerid",
                "hostid",
                "description",
                "expression",
                "priority",
                "status",
                "recovery_expression",
            ],
            "templateids": tpl_ids,
            "inherited": False,
            "limit": 20000,
        },
        auth=token,
    )
    print(f"   获取: {len(triggers_raw)} 条\n")

    # ── 整理数据 ───────────────────────────────────────────────────────────────
    def norm_item(raw: dict, is_prototype: bool) -> dict:
        return {
            "name": raw["name"],
            "key": raw["key_"],
            "type": ITEM_TYPE_MAP.get(raw["type"], raw["type"]),
            "value_type": VALUE_TYPE_MAP.get(raw["value_type"], raw["value_type"]),
            "units": raw.get("units") or "",
            "delay": raw.get("delay") or "",
            "description": (raw.get("description") or "").strip()[:300],
            "is_prototype": is_prototype,
        }

    def norm_lld(raw: dict) -> dict:
        return {
            "name": raw["name"],
            "key": raw["key_"],
            "type": ITEM_TYPE_MAP.get(raw["type"], raw["type"]),
            "delay": raw.get("delay") or "",
            "description": (raw.get("description") or "").strip()[:300],
        }

    def norm_trigger(raw: dict) -> dict:
        priority_map = {
            "0": "NOT_CLASSIFIED",
            "1": "INFO",
            "2": "WARNING",
            "3": "AVERAGE",
            "4": "HIGH",
            "5": "DISASTER",
        }
        return {
            "name": raw["description"],
            "expression": raw["expression"],
            "priority": priority_map.get(raw["priority"], raw["priority"]),
            "recovery_expression": raw.get("recovery_expression") or "",
            "status": "ENABLED" if raw["status"] == "0" else "DISABLED",
        }

    # 按模板分组
    by_template: dict[str, dict] = {
        name: {
            "template_name": name,
            "items": [],
            "item_prototypes": [],
            "lld_rules": [],
            "triggers": [],
        }
        for name in tpl_id_to_name.values()
    }

    for raw in items_raw:
        tname = tpl_id_to_name.get(raw["hostid"])
        if tname:
            by_template[tname]["items"].append(norm_item(raw, False))

    for raw in protos_raw:
        tname = tpl_id_to_name.get(raw["hostid"])
        if tname:
            by_template[tname]["item_prototypes"].append(norm_item(raw, True))

    for raw in lld_rules_raw:
        tname = tpl_id_to_name.get(raw["hostid"])
        if tname:
            by_template[tname]["lld_rules"].append(norm_lld(raw))

    for raw in triggers_raw:
        tname = tpl_id_to_name.get(raw.get("hostid", ""))
        if tname:
            by_template[tname]["triggers"].append(norm_trigger(raw))

    # 全局唯一 key 索引
    all_keys: dict[str, dict] = {}
    for raw in items_raw:
        k = raw["key_"]
        if k not in all_keys:
            all_keys[k] = norm_item(raw, False)
    for raw in protos_raw:
        k = raw["key_"]
        if k not in all_keys:
            all_keys[k] = norm_item(raw, True)

    # ── 打印摘要 ───────────────────────────────────────────────────────────────
    print("=" * 72)
    print("模板 Items 摘要")
    print("=" * 72)
    for tname in sorted(by_template.keys()):
        d = by_template[tname]
        n_items = len(d["items"])
        n_protos = len(d["item_prototypes"])
        n_lld = len(d["lld_rules"])
        n_trig = len(d["triggers"])
        print(f"\n{'─' * 68}")
        print(f"  {tname}")
        print(
            f"  items={n_items}  prototypes={n_protos}  lld={n_lld}  triggers={n_trig}"
        )
        print(f"  {'─' * 60}")
        if d["items"]:
            print("  [Items]")
            for it in sorted(d["items"], key=lambda x: x["key"]):
                print(
                    f"    [{it['type']:20}] {it['key'][:60]:<60} units={it['units']:<8} {it['value_type']}"
                )
        if d["lld_rules"]:
            print("  [LLD Discovery Rules]")
            for lld in sorted(d["lld_rules"], key=lambda x: x["key"]):
                print(f"    [{lld['type']:20}] {lld['key']}")
        if d["item_prototypes"]:
            print("  [Item Prototypes]")
            for pr in sorted(d["item_prototypes"], key=lambda x: x["key"]):
                print(
                    f"    [{pr['type']:20}] {pr['key'][:60]:<60} units={pr['units']:<8} {pr['value_type']}"
                )

    print(f"\n{'=' * 72}")
    print(f"汇总:")
    print(f"  模板数: {len(by_template)}")
    print(f"  Items: {len(items_raw)}")
    print(f"  Item Prototypes (LLD): {len(protos_raw)}")
    print(f"  LLD Discovery Rules: {len(lld_rules_raw)}")
    print(f"  Triggers: {len(triggers_raw)}")
    print(f"  唯一 key 总数: {len(all_keys)}")

    # ── 输出 JSON ──────────────────────────────────────────────────────────────
    import datetime

    output = {
        "generated_at": datetime.datetime.now().isoformat(),
        "zabbix_version": "7.0.23",
        "api_url": API_URL,
        "stats": {
            "templates": len(by_template),
            "items": len(items_raw),
            "item_prototypes": len(protos_raw),
            "lld_rules": len(lld_rules_raw),
            "triggers": len(triggers_raw),
            "unique_keys": len(all_keys),
        },
        "templates_not_found": not_found,
        "by_template": by_template,
        "all_keys_index": all_keys,
    }

    out_path = output_dir / "zabbix_keys_dump.json"
    out_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n💾 JSON 输出: {out_path}")

    # 同时输出一份纯 key 列表（按模板，方便查阅）
    keys_only: dict[str, list[str]] = {}
    for tname, d in by_template.items():
        keys_only[tname] = sorted(
            [it["key"] for it in d["items"]]
            + [pr["key"] for pr in d["item_prototypes"]]
        )
    keys_only_path = output_dir / "zabbix_keys_only.json"
    keys_only_path.write_text(
        json.dumps(keys_only, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"💾 Keys only: {keys_only_path}")
    print("\n✅ 完成")


if __name__ == "__main__":
    main()
