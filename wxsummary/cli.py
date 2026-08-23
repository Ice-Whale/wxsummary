"""命令行入口（v2：读取 chatlog-keeper 导出的 JSON）

使用方式：
  wxsummary today                    # 生成今天的群聊 AI 日报
  wxsummary yesterday                # 生成昨天的群聊 AI 日报
  wxsummary date 2026-08-22          # 生成指定日期的 AI 日报
  wxsummary week --start 2026-08-17 --end 2026-08-23   # 生成周报告
  wxsummary today --no-ai            # 只输出原始消息（不调 AI）
  wxsummary today --include-direct   # 也包含私聊
  wxsummary info                     # 显示导出文件统计信息
"""

import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import click

from wxsummary.config import load_config
from wxsummary.summary import (
    CHINA_TZ, load_export, fetch_groups_for_date, fetch_groups_for_range,
    format_all_groups_for_human,
)
from wxsummary.ai import generate_daily_report
from wxsummary.chatlog import export_wechat

# 日报输出目录
REPORTS_DIR = Path(__file__).parent.parent / "reports"


@click.group()
@click.version_option(package_name="wxsummary")
def main():
    """微信群聊日报生成器（基于 chatlog-keeper 导出数据）

    流程：chatlog-keeper 导出 JSON → 本工具按日期/群聚合 → DeepSeek 总结
    """


@main.command()
@click.option("--no-ai", is_flag=True, help="不调用 AI，只输出原始消息列表")
@click.option("--include-direct", is_flag=True, help="也包含私聊（默认只统计群聊）")
@click.option("--output", "-o", type=click.Path(), help="输出文件路径（默认 reports/日期.md）")
@click.option("--force", "-f", is_flag=True, help="强制重新导出（即使导出文件已是最新）")
def today(no_ai: bool, include_direct: bool, output: str, force: bool):
    """生成今天的群聊日报"""
    d = date.today()
    run_report(d, d, f"{d.isoformat()}", "日报", no_ai, include_direct, output,
               output_name=f"{d.isoformat()}", force=force)


@main.command(name="date")
@click.argument("date_str")
@click.option("--no-ai", is_flag=True, help="不调用 AI，只输出原始消息列表")
@click.option("--include-direct", is_flag=True, help="也包含私聊")
@click.option("--output", "-o", type=click.Path(), help="输出文件路径")
@click.option("--force", is_flag=True, help="强制重新导出（即使导出文件已是最新）")
def date_cmd(date_str: str, no_ai: bool, include_direct: bool, output: str, force: bool):
    """生成指定日期的群聊日报（DATE 格式 YYYY-MM-DD）"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        click.echo(f"❌ 日期格式错误：{date_str}，请用 YYYY-MM-DD", err=True)
        sys.exit(1)
    run_report(d, d, f"{d.isoformat()}", "日报", no_ai, include_direct, output,
               output_name=f"{d.isoformat()}", force=force)


@main.command(name="yesterday")
@click.option("--no-ai", is_flag=True, help="不调用 AI，只输出原始消息列表")
@click.option("--include-direct", is_flag=True, help="也包含私聊")
@click.option("--output", "-o", type=click.Path(), help="输出文件路径")
@click.option("--force", is_flag=True, help="强制重新导出（即使导出文件已是最新）")
def yesterday_cmd(no_ai: bool, include_direct: bool, output: str, force: bool):
    """生成昨天的群聊日报"""
    d = date.today() - timedelta(days=1)
    run_report(d, d, f"{d.isoformat()}", "日报", no_ai, include_direct, output,
               output_name=f"{d.isoformat()}", force=force)


@main.command()
@click.option("--start", "start_str", default=None, help="开始日期 YYYY-MM-DD")
@click.option("--end", "end_str", default=None, help="结束日期 YYYY-MM-DD（默认今天）")
@click.option("--no-ai", is_flag=True, help="不调用 AI，只输出原始消息列表")
@click.option("--include-direct", is_flag=True, help="也包含私聊")
@click.option("--output", "-o", type=click.Path(), help="输出文件路径")
@click.option("--force", is_flag=True, help="强制重新导出（即使导出文件已是最新）")
def week(start_str: str, end_str: str, no_ai: bool, include_direct: bool, output: str,
         force: bool):
    """生成一段时间（如本周）的群聊周报。

    不指定 --start 时，默认从本周一开始；--end 默认今天。
    """
    today_d = date.today()
    start = _parse_date(start_str) if start_str else today_d - timedelta(days=today_d.weekday())
    end = _parse_date(end_str) if end_str else today_d

    if start > end:
        click.echo(f"❌ 开始日期 {start} 晚于结束日期 {end}", err=True)
        sys.exit(1)

    label = f"{start.isoformat()} ~ {end.isoformat()}"
    run_report(start, end, label, "周报", no_ai, include_direct, output,
               output_name=f"{start.isoformat()}_{end.isoformat()}",
               min_export_days=(end - start).days + 2, force=force)


@main.command()
@click.option("--days", "-d", type=int, default=None,
              help="回溯天数（默认取 .env 的 EXPORT_DAYS，再不行用 7）")
@click.option("--force", is_flag=True, help="强制重新导出（即使导出文件已是最新）")
def sync(days: int, force: bool):
    """只导出微信数据到 JSON，不调用 AI（可先用它刷新导出文件）"""
    config = load_config(require_ai=False)

    if days is None:
        days = config.export_days or 7

    if not force and _is_export_fresh(config.export_json, date.today()):
        click.echo(f"✅ 导出文件已是最新，跳过导出（{config.export_json.name}）")
        return

    click.echo(f"📥 从微信导出最近 {days} 天聊天记录...")
    result = export_wechat(days, config.export_json.parent)
    click.echo(f"✅ 导出完成：{result.get('n_messages', 0)} 条消息，"
               f"耗时 {result.get('elapsed_s', 0)}s")
    click.echo(f"   JSON：{result.get('out_json')}")
    click.echo(f"   HTML：{result.get('out_html')}")


def _parse_date(s: str) -> date:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError:
        click.echo(f"❌ 日期格式错误：{s}，请用 YYYY-MM-DD", err=True)
        sys.exit(1)


def _is_export_fresh(export_json: Path, target_date: date) -> bool:
    """导出文件是否存在且足够新（mtime 不早于 target_date 当天零点，中国时区）。"""
    if not export_json.exists():
        return False
    threshold = datetime.combine(target_date, time.min, tzinfo=CHINA_TZ)
    mtime = datetime.fromtimestamp(export_json.stat().st_mtime, CHINA_TZ)
    return mtime >= threshold


def ensure_export(config, target_date: date, min_days: int | None = None,
                  force: bool = False) -> None:
    """按需先导出微信数据，保证喂 AI 前数据是最新的。

    若导出文件已存在且足够新（mtime 不早于 target_date 当天零点），且未强制，
    则打印提示并跳过导出。
    """
    days = min_days if min_days is not None else config.export_days
    if days <= 0:
        return

    if not force and _is_export_fresh(config.export_json, target_date):
        click.echo(f"✅ 导出文件已是最新，跳过导出（{config.export_json.name}）")
        click.echo("")
        return

    click.echo(f"📥 先从微信导出最近 {days} 天聊天记录...")
    result = export_wechat(days, config.export_json.parent)
    click.echo(
        f"   导出完成：{result.get('n_messages', 0)} 条消息，"
        f"耗时 {result.get('elapsed_s', 0)}s"
    )
    click.echo("")


def run_report(start: date, end: date, label: str, kind: str,
               no_ai: bool, include_direct: bool, output: str,
               output_name: str, min_export_days: int | None = None,
               force: bool = False):
    """生成日报/周报的核心流程"""
    click.echo(f"📅 生成 {label} 的群聊{kind}")
    click.echo("")

    config = load_config(require_ai=not no_ai)

    # 先导出最新数据，再拉取（"先导出数据、再喂 AI"的一键流程）
    ensure_export(config, target_date=end, min_days=min_export_days, force=force)

    # 拉取消息（单日直接取当天，跨天则聚合）
    if start == end:
        groups = fetch_groups_for_date(config.export_json, start,
                                       include_direct=include_direct)
    else:
        groups = fetch_groups_for_range(config.export_json, start, end,
                                        include_direct=include_direct)

    if not groups:
        click.echo(f"✅ {label} 没有匹配的消息")
        click.echo("   提示：导出数据的时间范围可能没覆盖该日期，")
        click.echo("   可用 wxsummary sync --days N 重新导出更多天")
        return

    total_msgs = sum(g.count for g in groups)
    click.echo(f"📊 共 {len(groups)} 个会话，{total_msgs} 条消息")

    # 生成报告
    if no_ai:
        click.echo("\n📝 生成原始消息列表（--no-ai 模式）...")
        report = format_all_groups_for_human(groups, label, kind)
    else:
        click.echo(f"\n🤖 调用 AI 模型生成群聊{kind}...")
        report = generate_daily_report(config, groups, label, kind)

    # 输出
    if output:
        output_path = Path(output)
    else:
        REPORTS_DIR.mkdir(exist_ok=True)
        suffix = "raw" if no_ai else "report"
        output_path = REPORTS_DIR / f"{output_name}_{suffix}.md"

    output_path.write_text(report, encoding="utf-8")
    click.echo(f"\n✅ {kind}已生成：{output_path}")
    click.echo(f"   文件大小：{max(1, output_path.stat().st_size // 1024)} KB")


@main.command()
def info():
    """显示导出文件的统计信息"""
    config = load_config(require_ai=False)
    path = config.export_json

    click.echo(f"📄 导出文件：{path}")
    if not path.exists():
        click.echo("❌ 文件不存在，请先运行 wxsummary sync")
        sys.exit(1)

    data = load_export(path)
    click.echo(f"📊 总消息数：{len(data)}")

    tss = [m["ts"] for m in data if m.get("ts")]
    if tss:
        click.echo(f"🕘 时间范围：{datetime.fromtimestamp(min(tss), CHINA_TZ):%Y-%m-%d %H:%M} "
                   f"~ {datetime.fromtimestamp(max(tss), CHINA_TZ):%Y-%m-%d %H:%M}")

    n_group = sum(1 for m in data if m.get("is_group_chat"))
    click.echo(f"👥 群聊消息：{n_group}（私聊 {len(data) - n_group}）")

    days = {}
    for m in data:
        if m.get("ts"):
            d = datetime.fromtimestamp(m["ts"], CHINA_TZ).strftime("%Y-%m-%d")
            days[d] = days.get(d, 0) + 1
    click.echo("\n📅 按天分布：")
    for d, c in sorted(days.items()):
        click.echo(f"   {d}: {c} 条")

    click.echo(f"\n🔑 AI API Key：{'✅ 已配置' if config.zhipuai_api_key else '❌ 未配置（.env 的 ZHIPUAI_API_KEY）'}")


if __name__ == "__main__":
    main()