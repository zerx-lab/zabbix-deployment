#!/usr/bin/env python3
"""
verify_import.py
验证华三 SNMP 模板是否已成功导入 Zabbix，并输出详细信息。
"""

import json
import sys
import urllib.request
from pathlib import Path

API_URL = "http://localhost:8080/api_jsonrpc.php"
DEFAULT_USER = "Admin"
DEFAULT_PASSWORD = "zabbix"


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


def main() -> int:
    print("🔐 登录 Zabbix...")
    token = api_call(
        "user.login", {"username": DEFAULT_USER, "password": DEFAULT_PASSWORD}
    )
    print(f"   token: {token[:20]}...\n")

    # 1. 查询所有模板组
    print("📋 所有模板组:")
    groups = api_call(
        "templategroup.get",
        {"output": ["groupid", "name"], "sortfield": "name"},
        auth=token,
    )
    for g in groups:
        print(f"  [{g['groupid']:5}] {g['name']}")

    print()

    # 2. 按 templateid 倒序查最新 30 个模板
    print("📦 最新 30 个模板（按名称排序）:")
    templates = api_call(
        "template.get",
        {
            "output": ["templateid", "name"],
            "selectGroups": ["name"],
            "limit": 30,
            "sortfield": "name",
            "sortorder": "ASC",
        },
        auth=token,
    )
    if isinstance(templates, list):
        for t in templates:
            groups_str = ", ".join(g["name"] for g in t.get("groups", []))
            print(f"  [{t['templateid']:6}] {t['name']:<55} → {groups_str}")
    else:
        print(f"  (unexpected result type: {type(templates)})")

    print()

    # 3. 搜索 H3C 相关模板
    print("🔍 搜索 H3C 相关模板:")
    h3c_templates = api_call(
        "template.get",
        {
            "output": ["templateid", "name"],
            "selectGroups": ["name"],
            "selectItems": ["itemid", "name", "key_", "type"],
            "selectDiscoveries": ["itemid", "name", "key_"],
            "selectTriggers": ["triggerid", "description", "priority"],
            "search": {"name": "H3C"},
            "sortfield": "name",
        },
        auth=token,
    )
    if not h3c_templates:
        print("  ⚠ 未找到 H3C 模板")
    else:
        priority_names = {
            "0": "NOT_CLASSIFIED",
            "1": "INFO",
            "2": "WARNING",
            "3": "AVERAGE",
            "4": "HIGH",
            "5": "DISASTER",
        }
        for t in h3c_templates:
            groups_str = ", ".join(g["name"] for g in t.get("groups", []))
            items = t.get("items", [])
            discoveries = t.get("discoveries", [])
            triggers = t.get("triggers", [])
            print(f"\n  ✅ [{t['templateid']}] {t['name']}")
            print(f"     分组: {groups_str}")
            print(
                f"     Items: {len(items)}  LLD规则: {len(discoveries)}  Triggers: {len(triggers)}"
            )
            if items:
                item_type_map = {
                    "0": "Passive",
                    "2": "Trap",
                    "3": "Simple",
                    "7": "Active",
                    "20": "SNMP",
                }
                type_counter: dict[str, int] = {}
                for item in items:
                    itype = item_type_map.get(
                        item.get("type", "?"), item.get("type", "?")
                    )
                    type_counter[itype] = type_counter.get(itype, 0) + 1
                type_str = ", ".join(
                    f"{k}×{v}" for k, v in sorted(type_counter.items())
                )
                print(f"     Item 类型分布: {type_str}")
            if discoveries:
                for lld in discoveries:
                    print(f"     LLD: {lld['name']} (key={lld['key_']})")
            if triggers:
                for trig in triggers:
                    prio = priority_names.get(trig.get("priority", "0"), "?")
                    print(f"     Trigger [{prio}]: {trig['description']}")

    print()

    # 4. 统计总量
    total_templates = api_call(
        "template.get", {"output": "count", "countOutput": True}, auth=token
    )
    total_items = api_call(
        "item.get",
        {"output": "count", "countOutput": True, "templated": True},
        auth=token,
    )
    print(f"📊 当前 Zabbix 统计:")
    print(f"   模板总数: {total_templates}")
    print(f"   模板 Items 总数: {total_items}")

    # 5. 检查 H3C Converted 分组
    print()
    print("🗂  检查 'H3C Converted' 分组:")
    h3c_groups = api_call(
        "templategroup.get",
        {"output": ["groupid", "name"], "search": {"name": "H3C"}, "sortfield": "name"},
        auth=token,
    )
    if not h3c_groups:
        print("  ⚠ 未找到 'H3C Converted' 系列分组")
        print("    提示：导入时指定分组 'H3C Converted/Network devices' 等，")
        print("    如果 Zabbix 没有自动创建，可能是模板被导入到默认分组。")
    else:
        for g in h3c_groups:
            # 查该组下的模板
            tpls = api_call(
                "template.get",
                {"output": ["name"], "groupids": [g["groupid"]]},
                auth=token,
            )
            print(f"  [{g['groupid']}] {g['name']}: {len(tpls)} 个模板")
            for t in tpls:
                print(f"    - {t['name']}")

    print()
    print("✅ 验证完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
