"""AI 日报生成模块

调用 OpenAI 兼容接口（如 paratera 聚合平台 / 智谱 GLM），
为每个群的消息生成一段总结。

性能说明（针对多会话慢的问题）：
- 复用单个 OpenAI client，避免每次请求都重建连接。
- 各群的总结用线程池并行发起（默认 8 路并发），总耗时 ≈ 最慢那一路，
  而不是 28 路串行之和。
- 并发数可用环境变量 WXSUMMARY_MAX_WORKERS 调整（遇限流就调小）。
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from wxsummary.summary import GroupMessages, format_group_for_ai


# 每个群的总结提示词
GROUP_SUMMARY_PROMPT = """你是一个群聊消息总结助手。下面是微信群"{group_name}"（共{msg_count}条消息）的聊天记录。
请用简洁的中文总结这个群在这段时间讨论了什么，要求：
1. 用 2-4 句话概括主要内容
2. 如果有人提出了问题或做了决定，重点提到
3. 如果有重要链接或文件，提到一下
4. 不要逐条复述消息，要提炼总结
5. 如果消息太少（<5条），简单一句话带过即可

聊天记录：
---
{messages}
---

请直接输出总结，不要加"总结："之类的前缀。"""


# 整体日报的总览提示词
OVERVIEW_PROMPT = """你是一个群聊总结编辑。下面是 {label} 各个群聊的总结。
请写一段简短的总览（2-3句话），概括这段时间整体最值得关注的事情。
不要逐个群复述，要提炼跨群的共同主题或重点。

各群总结：
---
{group_summaries}
---

请直接输出总览。"""


def _make_client(config):
    """创建 OpenAI 兼容客户端（整个报告只创建一次，多线程复用）"""
    try:
        from openai import OpenAI
    except ImportError:
        raise SystemExit(
            "❌ 没安装 openai SDK。\n"
            "   请运行：pip install openai\n"
            "   或：pip install -e . （项目根目录）"
        )

    timeout = float(os.environ.get("WXSUMMARY_API_TIMEOUT", "180"))
    max_retries = int(os.environ.get("WXSUMMARY_API_MAX_RETRIES", "2"))
    return OpenAI(
        api_key=config.zhipuai_api_key,
        base_url=config.ai_api_base,
        timeout=timeout,
        max_retries=max_retries,
    )


def _chat(client, config, prompt: str, max_tokens: int) -> str:
    """统一聊天调用（复用传入的 client）"""
    response = client.chat.completions.create(
        model=config.zhipuai_model,
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content
    if not content:
        return "（模型在 token 上限内未给出答复，可能是推理过程过长，已用到上限。）"
    return content.strip()


def summarize_group(client, config, group: GroupMessages) -> str:
    """用 AI 总结一个群的消息（不自己建 client，复用传入的）"""
    # 准备消息文本
    messages_text = format_group_for_ai(group)

    # 如果文字消息太少，直接返回简单提示，不浪费 API 调用
    if group.text_count < 3:
        return f"这段时间消息较少（{group.count}条），无重要内容。"

    # 大群只保留最近的字符（时间顺序靠后更相关），
    # 控制 prompt 长度、避免单个大请求把整体并行拖慢。
    max_chars = int(os.environ.get("WXSUMMARY_MAX_CHARS", "12000"))
    if len(messages_text) > max_chars:
        messages_text = messages_text[-max_chars:] + "\n...(消息过长，已截断)"

    prompt = GROUP_SUMMARY_PROMPT.format(
        group_name=group.group_name,
        msg_count=group.count,
        messages=messages_text,
    )

    # Flash 类模型不是推理模型，总结只需几句话，512 足够；
    # 上限越低模型越早停、生成越快。
    return _chat(client, config, prompt, max_tokens=512)


def generate_overview(client, config, label: str, group_summaries: list[tuple[str, str]]) -> str:
    """生成整篇汇总的总览（依赖全部群总结，故在并行之后串行执行）"""
    if not group_summaries:
        return "这段时间没有群聊消息。"

    summaries_text = "\n\n".join(
        f"【{name}】\n{summary}" for name, summary in group_summaries
    )

    prompt = OVERVIEW_PROMPT.format(label=label, group_summaries=summaries_text)

    return _chat(client, config, prompt, max_tokens=1024)


def generate_daily_report(config, groups: list[GroupMessages], label: str,
                          kind: str = "日报") -> str:
    """生成完整的 Markdown 日报（各群总结并行，总览串行）

    Args:
        config: Config 对象（含 api_key、model、base_url）
        groups: 所有群的消息列表
        label: 标题标签（如 "2026-08-22" 或 "2026-08-17 ~ 2026-08-23"）
        kind: 报告类型（"日报" 或 "周报"，影响标题与总览措辞）

    Returns:
        Markdown 格式的报告文本
    """
    client = _make_client(config)
    total = len(groups)

    # 先放标题占位，最后再插总览
    lines = [f"# {label} 群聊{kind}", "", f"共 {total} 个群有消息。", ""]

    # ---- 并行生成各群总结 ----
    # 结果按原始顺序存回 results[idx]，保证日报章节顺序稳定
    results: list[tuple[str, str] | None] = [None] * total
    done = 0

    def _work(idx: int, group: GroupMessages):
        try:
            summary = summarize_group(client, config, group)
        except Exception as e:
            summary = f"（AI 总结失败：{e}）"
        return idx, group, summary

    max_workers = int(os.environ.get("WXSUMMARY_MAX_WORKERS", "8"))
    print(
        f"🚀 并行发起 {total} 个群的 AI 总结（{max_workers} 路并发）...",
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_work, i, g) for i, g in enumerate(groups)]
        for fut in as_completed(futures):
            idx, group, summary = fut.result()
            results[idx] = (group.group_name, summary)
            done += 1
            print(f"✅ 完成 [{done}/{total}] {group.group_name}", flush=True)

    group_summaries: list[tuple[str, str]] = [r for r in results if r is not None]

    # ---- 组装各群章节（保持原始顺序）----
    for group, (name, summary) in zip(groups, group_summaries):
        lines.append(f"## {name}（{group.count} 条消息）")
        lines.append("")
        lines.append(summary)
        lines.append("")

        # 附上部分原始消息（前5条文字消息）
        text_msgs = [m for m in group.messages if m.is_text][:5]
        if text_msgs:
            lines.append("<details>")
            lines.append(f"<summary>查看前 {len(text_msgs)} 条原始消息</summary>")
            lines.append("")
            for msg in text_msgs:
                lines.append(f"- [{msg.time_str}] {msg.sender_name}：{msg.content}")
            lines.append("")
            lines.append("</details>")
            lines.append("")

    # ---- 生成总览（放在最前面）----
    print("\n🤖 正在生成总览...", flush=True)
    try:
        overview = generate_overview(client, config, label, group_summaries)
        overview_lines = [
            f"# {label} 群聊{kind}",
            "",
            f"> {overview}",
            "",
            f"共 {total} 个群有消息。",
            "",
        ]
        lines = overview_lines + lines[4:]
    except Exception as e:
        print(f"   ⚠️ 总览生成失败：{e}")

    return "\n".join(lines)
