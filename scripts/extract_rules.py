#!/usr/bin/env python3
"""Extract .spec from a PrometheusRule manifest into a plain Prometheus rules file.

The PrometheusRule in k8s/base is the single source of truth. CI runs this and then
`promtool check rules` and `promtool test rules` against the output, so the exact
rules deployed to the cluster are the ones that get unit tested.
"""

import sys
from pathlib import Path

import yaml


def main(src: str, dst: str) -> None:
    doc = yaml.safe_load(Path(src).read_text())
    if doc.get("kind") != "PrometheusRule":
        sys.exit(f"{src}: expected kind PrometheusRule, got {doc.get('kind')}")
    out = Path(dst)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(doc["spec"], sort_keys=False))
    print(f"wrote {len(doc['spec']['groups'])} rule groups to {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: extract_rules.py <prometheusrule.yaml> <out.rules.yml>")
    main(sys.argv[1], sys.argv[2])
