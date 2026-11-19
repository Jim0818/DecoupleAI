"""Retired bulk competitor distiller; keep the old CLI explicit and harmless.

The former implementation depended on removed directories, imported a paid
model client at startup, and could report completion after analysing nothing.
Current topic research belongs to research/discover with deliberately selected
sample references and the target account's L1/L2. Competitor observations are
reference material, not a replacement for those account policies.

Consumer: scripts/topic-optimizer/optimizer.py (compatibility entry). Remove
this module with that entry once external/manual users have migrated. No source
directories, model APIs, account files or output files are touched here.
"""
from __future__ import annotations

import argparse
import json
import sys


class LegacyTopicOptimizerError(RuntimeError):
    """The retired bulk workflow cannot be run against the current layout."""


MESSAGE = (
    "旧批量竞品蒸馏入口已停用：它依赖的目录已迁移。"
    "请把明确选定的样本文件交给 research/discover，并指定目标账号 "
    "studio、intellifuture 或 decoupleai。竞品观察只作参考，"
    "不能自动改写账号 L1/L2，也不要求模仿对抗性标题或结构钩子。"
)


def run(account_filter=None, type_filter=None):
    """Fail explicitly for existing Python callers; never emit an empty pack."""
    raise LegacyTopicOptimizerError(MESSAGE)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=MESSAGE)
    parser.add_argument("--account", help="旧参数：竞品名称；不再启动批量分析")
    parser.add_argument("--type", choices=["media", "creator"], help="旧参数：竞品类型")
    parser.parse_args(argv)
    print(json.dumps({
        "status": "not_available",
        "error": "LEGACY_TOPIC_OPTIMIZER_RETIRED",
        "message": MESSAGE,
        "replacement": {
            "role": "research", "mode": "discover",
            "inputs": "explicit selected sample files and target account L1/L2",
        },
    }, ensure_ascii=False), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
