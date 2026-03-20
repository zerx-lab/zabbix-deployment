#!/usr/bin/env python3
"""
check_h3c_templates.py
检查华三 SNMP 模板是否已成功导入 Zabbix。
"""

import json
import urllib.request

API_URL = "http://localhost:8080/api_jsonrpc.php"


def api_call(method: str, params: dict, auth: str | None = None) -> object:
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
    token = api_call("user.login", {"username": "Admin", "password": "zabbix"})
    assert isinstance(token, str)

    # 获取所有模板
    templates = api_call(
        "template.get",
        {
            "output": ["templateid", "name"],
            "selectGroups": ["name"],
            "selectItems": ["itemid", "name", "key_", "type"],
            "selectDiscoveries": ["itemid", "name", "key_"],
            "selectTriggers": ["triggerid", "description", "priority"],
            "limit": 500,
            "sortfield": "name",
        },
        auth=token,
    )
    assert isinstance(templates, list)

    # 筛选含中文字符的模板（华三导入的）
    chinese_tpls = [
        t for t in templates if any(ord(c) > 127 for c in t.get("name", ""))
    ]

    # 筛选模板名含 "H3C" 的
    h3c_tpls = [t for t in templates if "H3C" in t.get("name", "")]

    # 所有分组
    groups = api_call(
        "templategroup.get",
        {"output": ["groupid", "name"], "sortfield": "name"},
        auth=token,
    )
    assert isinstance(groups, list)

    h3c_groups = [g for g in groups if "H3C" in g.get("name", "")]

    # 输出
    print(f"模板总数: {len(templates)}")
    print(f"含中文名称模板: {len(chinese_tpls)}")
    print(f"含 'H3C' 名称模板: {len(h3c_tpls)}")
    print(f"含 'H3C' 名称分组: {len(h3c_groups)}")
    print()

    if h3c_groups:
        print("H3C 相关分组:")
        for g in h3c_groups:
            print(f"  [{g['groupid']}] {g['name']}")
        print()

    if h3c_tpls:
        priority_names = {
            "0": "NC",
            "1": "INFO",
            "2": "WARN",
            "3": "AVG",
            "4": "HIGH",
            "5": "DISASTER",
        }
        item_type_names = {
            "0": "Passive",
            "2": "Trap",
            "3": "Simple",
            "5": "Internal",
            "7": "Active",
            "10": "External",
            "15": "Calculated",
            "16": "JMX",
            "18": "Dependent",
            "19": "HTTP",
            "20": "SNMP",
            "21": "Script",
        }
        print(f"H3C 相关模板 ({len(h3c_tpls)} 个):")
        for t in h3c_tpls:
            grp_names = ", ".join(g["name"] for g in t.get("groups", []))
            items = t.get("items", [])
            discoveries = t.get("discoveries", [])
            triggers = t.get("triggers", [])
            print(f"\n  [{t['templateid']:6}] {t['name']}")
            print(f"           分组: {grp_names}")
            print(
                f"           Items={len(items)}  LLD={len(discoveries)}  Triggers={len(triggers)}"
            )

            # Item 类型统计
            if items:
                type_cnt: dict[str, int] = {}
                for item in items:
                    itype = item_type_names.get(
                        item.get("type", "?"), item.get("type", "?")
                    )
                    type_cnt[itype] = type_cnt.get(itype, 0) + 1
                type_str = "  ".join(f"{k}×{v}" for k, v in sorted(type_cnt.items()))
                print(f"           Item类型: {type_str}")

            # LLD 规则
            for lld in discoveries:
                print(f"           LLD: {lld['key_']}")

            # Triggers
            for trig in triggers:
                prio = priority_names.get(str(trig.get("priority", "0")), "?")
                print(f"           [{prio}] {trig['description']}")
    else:
        print("未找到含 'H3C' 名称的模板。")

    print()

    if chinese_tpls:
        print(f"含中文名称的模板 ({len(chinese_tpls)} 个):")
        for t in chinese_tpls:
            grp_names = ", ".join(g["name"] for g in t.get("groups", []))
            items = t.get("items", [])
            discoveries = t.get("discoveries", [])
            triggers = t.get("triggers", [])
            print(
                f"  [{t['templateid']:6}] {t['name']:<45}"
                f"  items={len(items):3}  lld={len(discoveries):2}  triggers={len(triggers):3}"
                f"  → {grp_names}"
            )
    else:
        print("未找到含中文名称的模板。")


if __name__ == "__main__":
    main()
