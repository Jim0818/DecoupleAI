"""
Style Analyst Mode 4 — Viral Score 预处理脚本
==============================================
形态：离线工具脚本（Style Analyst Mode 4 的前置步骤，手动触发）

职能：
1. 读取 reference_materials/wechat/{account_name}/ 下的所有 .md 文章
2. 解析 YAML frontmatter（read_count / like_count / zan_count / comment_count / publish_time）
3. 计算 viral_score = normalize((read + like×5 + zan×3 + comment×10) / age_days)
4. 将 viral_score 写回每篇文章的 frontmatter
5. 生成 .track_report.json（供 Style Analyst Mode 4 直接加载）

用法：
    # 分析单个账号
    python scripts/style-analyst/compute_viral_scores.py --account 夕小瑶科技说

    # 指定自定义目录
    python scripts/style-analyst/compute_viral_scores.py \\
        --account 夕小瑶科技说 \\
        --data-dir reference_materials/wechat/

    # 指定爆款阈值（默认 Top 20%）
    python scripts/style-analyst/compute_viral_scores.py \\
        --account 夕小瑶科技说 \\
        --top-pct 0.15

    # 只输出报告，不写回 frontmatter
    python scripts/style-analyst/compute_viral_scores.py \\
        --account 夕小瑶科技说 \\
        --dry-run

输出：
    - 每篇文章 frontmatter 中的 viral_score 字段（float 0.0-1.0 或 null）
    - reference_materials/wechat/{account_name}/.track_report.json

依赖：
    pip install pyyaml
    （autogen 环境已包含）
"""

from __future__ import annotations
from textpicos.paths import ProjectPaths as _ProjectPaths

import argparse
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import yaml

# ── 路径常量 ────────────────────────────────────────────────────────────────
ROOT = _ProjectPaths.discover().root          # DecoupleAI/
REFERENCE_DIR = ROOT / "reference_materials" / "wechat"

TZ_CST = timezone(timedelta(hours=8))


# ── 日期解析 ────────────────────────────────────────────────────────────────
def parse_publish_time(val) -> Optional[datetime]:
    """
    解析 frontmatter 中 publish_time 字段为 datetime（带时区）。
    支持格式：
      - "2025-01-15 09:30:00"
      - "2025-01-15 09:30"
      - "2025-01-15"
      - datetime 对象（pyyaml 自动解析）
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=TZ_CST)
        return val
    s = str(val).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=TZ_CST)
        except ValueError:
            continue
    return None


def compute_age_days(publish_time: Optional[datetime]) -> float:
    """从发布时间到今天的天数（最小值 1，防止除零）。"""
    if publish_time is None:
        return 365.0   # 未知发布时间 → 假设 1 年前
    now = datetime.now(tz=TZ_CST)
    delta = (now - publish_time).total_seconds() / 86400.0
    return max(delta, 1.0)


# ── frontmatter 解析 / 写入 ──────────────────────────────────────────────────
def parse_frontmatter(text: str) -> tuple[dict, str]:
    """分离 YAML frontmatter 和正文。返回 (fm_dict, body)。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, parts[2]


def serialize_frontmatter(fm: dict) -> str:
    """将 frontmatter dict 序列化为 YAML 块（含首尾 ---）。"""
    lines = ["---"]
    for key, value in fm.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in value:
                    if isinstance(item, dict):
                        first = True
                        for k, v in item.items():
                            v_str = str(v).replace('"', "'").replace("\n", " ")
                            if first:
                                lines.append(f'  - {k}: "{v_str}"')
                                first = False
                            else:
                                lines.append(f'    {k}: "{v_str}"')
                    else:
                        lines.append(f"  - {item}")
        elif isinstance(value, str):
            escaped = value.replace('"', '\\"')
            lines.append(f'{key}: "{escaped}"')
        elif value is None:
            lines.append(f"{key}: null")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def write_viral_score(md_path: Path, viral_score: Optional[float], dry_run: bool) -> bool:
    """将 viral_score 写入文章 frontmatter（精确到小数点后 4 位）。"""
    text = md_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    if not fm:
        return False

    if viral_score is None:
        fm["viral_score"] = None
    else:
        fm["viral_score"] = round(viral_score, 4)

    if not dry_run:
        new_text = serialize_frontmatter(fm) + body
        md_path.write_text(new_text, encoding="utf-8")
    return True


# ── viral_score 计算 ────────────────────────────────────────────────────────
def compute_raw_score(fm: dict) -> Optional[float]:
    """
    raw = (read_count + like_count×5 + zan_count×3 + comment_count×10) / age_days
    任意必需字段（read_count）为 null → 返回 None（降级处理）。
    """
    read = fm.get("read_count")
    if read is None:
        return None

    like    = fm.get("like_count")    or 0
    zan     = fm.get("zan_count")     or 0
    comment = fm.get("comment_count") or 0

    publish_time = parse_publish_time(fm.get("publish_time"))
    age_days = compute_age_days(publish_time)

    raw = (read + like * 5 + zan * 3 + comment * 10) / age_days
    return raw


def normalize_scores(raw_scores: list[Optional[float]]) -> list[Optional[float]]:
    """
    min-max 归一化（仅对非 None 值）。
    结果范围 [0.0, 1.0]。全部为 null → 全部返回 null。
    """
    valid = [s for s in raw_scores if s is not None]
    if not valid:
        return raw_scores
    min_s, max_s = min(valid), max(valid)
    if max_s == min_s:
        # 所有有效值相同 → 全部设为 0.5
        return [0.5 if s is not None else None for s in raw_scores]
    return [
        (s - min_s) / (max_s - min_s) if s is not None else None
        for s in raw_scores
    ]


# ── 文章扫描 ────────────────────────────────────────────────────────────────
def load_articles(account_dir: Path) -> list[dict]:
    """
    扫描 account_dir 下所有 .md（递归），解析 frontmatter + 路径。
    目录结构：{account_name}/{title}/{title}.md
    """
    articles = []
    for md_file in sorted(account_dir.rglob("*.md")):
        # 跳过隐藏文件
        if any(part.startswith(".") for part in md_file.parts):
            continue
        text = md_file.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(text)
        if not fm:
            continue
        articles.append({
            "path": md_file,
            "title": fm.get("title", md_file.stem),
            "fm": fm,
        })
    return articles


# ── track_report 生成 ────────────────────────────────────────────────────────
def build_track_report(account_name: str, articles: list[dict], top_pct: float) -> dict:
    """
    生成赛道竞品分析报告 dict，结构与 output.schema.json 的 track_report 一致。
    """
    total = len(articles)
    with_engagement = sum(1 for a in articles if a["fm"].get("read_count") is not None)
    scores = [a.get("viral_score") for a in articles]
    valid_scores = [s for s in scores if s is not None]

    if valid_scores:
        threshold = sorted(valid_scores, reverse=True)[
            max(0, int(len(valid_scores) * top_pct) - 1)
        ]
        top_articles = [
            a for a in articles
            if a.get("viral_score") is not None and a["viral_score"] >= threshold
        ]
    else:
        threshold = 0.0
        top_articles = []

    # 简单特征聚合（基于标题关键词模式）
    top_features = _extract_top_features(top_articles)
    diff_space = _compute_differentiation_space(articles, top_articles)

    # Top sample paths（按 viral_score 降序）
    top_paths = sorted(
        [(a.get("viral_score", 0) or 0, str(a["path"].relative_to(ROOT)))
         for a in top_articles],
        reverse=True,
    )

    return {
        "topic": account_name,
        "article_count": total,
        "articles_with_engagement": with_engagement,
        "viral_threshold": round(threshold, 4),
        "top_features": top_features,
        "differentiation_space": diff_space,
        "top_sample_paths": [p for _, p in top_paths],
    }


def _extract_top_features(top_articles: list[dict]) -> list[str]:
    """
    从爆款文章的标题中提取结构性特征（简单启发式规则）。
    真正的深度分析交给 Style Analyst Agent 做 NLP 层面的提取。
    """
    if not top_articles:
        return ["（无 engagement 数据，请先导入阅读量后重新运行）"]

    features = []
    titles = [a["fm"].get("title", "") for a in top_articles]

    # 检测问句标题
    question_count = sum(1 for t in titles if "？" in t or "?" in t or t.endswith("吗"))
    if question_count / max(len(titles), 1) > 0.3:
        features.append(f"标题偏好问句结构（{question_count}/{len(titles)} 篇含疑问词）")

    # 检测数字列表标题
    number_count = sum(1 for t in titles if re.search(r"[0-9０-９]+\s*[个种条款]", t))
    if number_count / max(len(titles), 1) > 0.2:
        features.append(f"常用数字量化标题（如 'X 个…'）（{number_count}/{len(titles)} 篇）")

    # 检测字数（短标题 ≤ 20 字）
    short_title_count = sum(1 for t in titles if len(t) <= 20)
    if short_title_count / max(len(titles), 1) > 0.5:
        features.append(f"爆款多为短标题（≤20字，{short_title_count}/{len(titles)} 篇）")

    # 均值阅读量
    reads = [a["fm"].get("read_count") for a in top_articles if a["fm"].get("read_count")]
    if reads:
        avg_read = int(sum(reads) / len(reads))
        features.append(f"爆款平均阅读量：{avg_read:,}")

    if not features:
        features.append("样本量不足，建议补充更多文章后重新分析")

    return features[:5]


def _compute_differentiation_space(all_articles: list[dict], top_articles: list[dict]) -> str:
    """
    比较爆款 vs 全量的平均阅读量，找出最大差异维度作为差异化空间提示。
    """
    if not top_articles:
        return "缺乏 engagement 数据，无法计算差异化空间。请先导入阅读量数据（--engagement-mode crawler）。"

    all_reads = [a["fm"].get("read_count") or 0 for a in all_articles]
    top_reads = [a["fm"].get("read_count") or 0 for a in top_articles]

    avg_all = sum(all_reads) / max(len(all_reads), 1)
    avg_top = sum(top_reads) / max(len(top_reads), 1)
    ratio = avg_top / max(avg_all, 1)

    return (
        f"爆款平均阅读量（{int(avg_top):,}）是全量均值（{int(avg_all):,}）的 {ratio:.1f}x。"
        f"差距集中在「标题冲击力 + 开头前 3 句」——这是 TextPicOS 可发力的核心差异化方向。"
    )


# ── 主流程 ─────────────────────────────────────────────────────────────────
def run(account_name: str, data_dir: Path, top_pct: float, dry_run: bool) -> int:
    account_dir = data_dir / account_name
    if not account_dir.exists():
        print(f"[ERROR] 账号目录不存在：{account_dir}")
        print(f"        请先使用 WeChat Importer 采集文章：")
        print(f"        python skills/wechat-article-importer/scripts/batch_fetch.py --mode account --name '{account_name}'")
        return 1

    print(f"[INFO] 扫描账号目录：{account_dir}")
    articles = load_articles(account_dir)
    if not articles:
        print(f"[ERROR] 未找到 .md 文章，目录为空或格式不正确。")
        return 1

    print(f"[INFO] 发现文章：{len(articles)} 篇")

    # 计算 raw scores
    raw_scores = [compute_raw_score(a["fm"]) for a in articles]
    with_data = sum(1 for s in raw_scores if s is not None)
    print(f"[INFO] 含 engagement 数据：{with_data}/{len(articles)} 篇")

    if with_data == 0:
        print(f"[WARN] 所有文章 read_count 均为 null。")
        print(f"       viral_score 将全部设为 null，track_report 降级为纯结构描述。")
        print(f"       建议补充 engagement 数据：--engagement-mode crawler")

    # 归一化
    normalized = normalize_scores(raw_scores)

    # 写回 frontmatter + 更新 articles 列表
    written, skipped = 0, 0
    for article, score in zip(articles, normalized):
        article["viral_score"] = score
        ok = write_viral_score(article["path"], score, dry_run)
        if ok:
            written += 1
        else:
            skipped += 1

    mode_label = "[DRY-RUN] " if dry_run else ""
    print(f"{mode_label}写回 viral_score：{written} 篇成功，{skipped} 篇跳过（无 frontmatter）")

    # 生成 track_report
    report = build_track_report(account_name, articles, top_pct)

    report_path = account_dir / ".track_report.json"
    if not dry_run:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"[DONE] track_report 写入：{report_path}")
    else:
        print(f"[DRY-RUN] track_report 预览：")
        print(json.dumps(report, ensure_ascii=False, indent=2))

    # 打印摘要
    print("\n── 竞品分析摘要 ──────────────────────────────────────")
    print(f"  账号：{report['topic']}")
    print(f"  文章总数：{report['article_count']}")
    print(f"  含 engagement 数据：{report['articles_with_engagement']}")
    print(f"  爆款阈值（Top {int(top_pct*100)}%）：viral_score ≥ {report['viral_threshold']}")
    print(f"  爆款样本数：{len(report['top_sample_paths'])} 篇")
    print(f"\n  爆款共性特征：")
    for feat in report["top_features"]:
        print(f"    • {feat}")
    print(f"\n  差异化空间：{report['differentiation_space']}")
    print("\n  Top 爆款样本：")
    for i, path in enumerate(report["top_sample_paths"][:5], 1):
        article = next((a for a in articles if str(a["path"].relative_to(ROOT)) == path), None)
        score = f"{article['viral_score']:.4f}" if article and article.get("viral_score") else "N/A"
        print(f"    {i}. {Path(path).name}  (viral_score: {score})")

    print(f"\n[NEXT] Style Analyst Mode 4 可直接加载：{report_path.relative_to(ROOT)}")
    print(f"       或运行选题逻辑蒸馏：")
    print("       选题研究：将明确选定的样本交给 research/discover，并指定目标账号；竞品观察不自动改写账号策略。")

    return 0


# ── CLI ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Style Analyst Mode 4 — Viral Score 预处理脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 分析夕小瑶科技说（使用默认目录）
  python scripts/style-analyst/compute_viral_scores.py --account 夕小瑶科技说

  # 使用 Top 15% 作为爆款阈值
  python scripts/style-analyst/compute_viral_scores.py --account 夕小瑶科技说 --top-pct 0.15

  # 只预览，不写入文件
  python scripts/style-analyst/compute_viral_scores.py --account 夕小瑶科技说 --dry-run
        """,
    )
    parser.add_argument(
        "--account", type=str, required=True,
        help="公众号名称（与 target_accounts_list.csv 的 account_name 一致，支持中文）",
    )
    parser.add_argument(
        "--data-dir", type=Path,
        default=REFERENCE_DIR,
        help=f"账号文章根目录（默认：reference_materials/wechat/）",
    )
    parser.add_argument(
        "--top-pct", type=float, default=0.2,
        help="爆款阈值百分比（默认 0.2 = Top 20%%）",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只输出预览，不写回 frontmatter 也不保存 track_report.json",
    )
    args = parser.parse_args()

    if not 0.01 <= args.top_pct <= 0.5:
        print(f"[ERROR] --top-pct 必须在 0.01–0.50 之间，当前值：{args.top_pct}")
        sys.exit(1)

    exit_code = run(
        account_name=args.account,
        data_dir=args.data_dir,
        top_pct=args.top_pct,
        dry_run=args.dry_run,
    )
    sys.exit(exit_code)
