#!/usr/bin/env python3
"""
show_template_keys.py
读取已保存的 zabbix_keys_dump.json，打印指定模板的所有 item key 详情。
用法: python3 show_template_keys.py [模板名关键词]
"""

import json
import sys
from pathlib import Path

DUMP_FILE = (
    Path(__file__).parent.parent / "output" / "zabbix-mapping" / "zabbix_keys_dump.json"
)


def main():
    if not DUMP_FILE.exists():
        print(f"[ERROR] 找不到数据文件: {DUMP_FILE}")
        print("请先运行: python3 scripts/dump_zabbix_keys.py")
        sys.exit(1)

    data = json.loads(DUMP_FILE.read_text(encoding="utf-8"))
    by_template = data["by_template"]

    # 解析过滤关键词
    keyword = " ".join(sys.argv[1:]).strip().lower() if len(sys.argv) > 1 else ""

    matched = {
        name: d
        for name, d in by_template.items()
        if not keyword or keyword in name.lower()
    }

    if not matched:
        print(f"未找到包含 '{keyword}' 的模板")
        print("\n可用模板列表:")
        for name in sorted(by_template.keys()):
            n_items = len(by_template[name]["items"])
            n_protos = len(by_template[name]["item_prototypes"])
            n_lld = len(by_template[name]["lld_rules"])
            print(f"  {name}  (items={n_items}, protos={n_protos}, lld={n_lld})")
        sys.exit(0)

    for tname, d in sorted(matched.items()):
        n_items = len(d["items"])
        n_protos = len(d["item_prototypes"])
        n_lld = len(d["lld_rules"])
        n_trig = len(d["triggers"])

        print(f"\n{'=' * 80}")
        print(f"  {tname}")
        print(
            f"  items={n_items}  prototypes={n_protos}  lld_rules={n_lld}  triggers={n_trig}"
        )
        print(f"{'=' * 80}")

        if d["items"]:
            print(
                f"\n  ── Items ({n_items}) ──────────────────────────────────────────────"
            )
            for it in sorted(d["items"], key=lambda x: x["key"]):
                units = it.get("units") or ""
                delay = it.get("delay") or ""
                print(
                    f"  [{it['type']:20}] "
                    f"{it['key'][:65]:<65} "
                    f"units={units:<8} "
                    f"vtype={it['value_type']:<10} "
                    f"delay={delay}"
                )

        if d["lld_rules"]:
            print(
                f"\n  ── LLD Discovery Rules ({n_lld}) ─────────────────────────────────"
            )
            for lld in sorted(d["lld_rules"], key=lambda x: x["key"]):
                delay = lld.get("delay") or ""
                print(f"  [{lld['type']:20}] {lld['key']:<65} delay={delay}")

        if d["item_prototypes"]:
            print(
                f"\n  ── Item Prototypes (LLD) ({n_protos}) ───────────────────────────"
            )
            for pr in sorted(d["item_prototypes"], key=lambda x: x["key"]):
                units = pr.get("units") or ""
                delay = pr.get("delay") or ""
                print(
                    f"  [{pr['type']:20}] "
                    f"{pr['key'][:65]:<65} "
                    f"units={units:<8} "
                    f"vtype={pr['value_type']:<10} "
                    f"delay={delay}"
                )

        if d["triggers"]:
            print(
                f"\n  ── Triggers ({n_trig}) ──────────────────────────────────────────"
            )
            priority_icon = {
                "NOT_CLASSIFIED": "⚪",
                "INFO": "🔵",
                "WARNING": "🟡",
                "AVERAGE": "🟠",
                "HIGH": "🔴",
                "DISASTER": "💥",
            }
            for trig in sorted(d["triggers"], key=lambda x: x["name"]):
                icon = priority_icon.get(trig["priority"], "?")
                status = "" if trig["status"] == "ENABLED" else " [DISABLED]"
                print(f"  {icon} [{trig['priority']:<14}]{status} {trig['name'][:70]}")


if __name__ == "__main__":
    main()
