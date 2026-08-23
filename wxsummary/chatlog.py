"""封装 chatlog-keeper 的微信导出能力，实现"先导出数据、再喂 AI"的一键流程。

chatlog_keeper 已通过 `pip install -e .` 装进当前环境，这里直接复用它的导出函数，
避免重复实现数据库解密逻辑。导出产物写入 EXPORT_JSON 指向的目录，
wxsummary 随后从那里读取并喂给 AI。
"""

from pathlib import Path


def export_wechat(days: int, out_dir: Path) -> dict:
    """调用 chatlog-keeper 导出最近 `days` 天的微信聊天记录。

    Args:
        days: 回溯天数（往前 N 天）
        out_dir: 输出目录，会写入 wechat_messages.json / wechat_messages.html

    Returns:
        chatlog-keeper 返回的结果 dict，含 n_messages / out_json / elapsed_s 等。
    """
    try:
        from chatlog_keeper.cli import _export_wechat
    except ImportError as e:
        raise SystemExit(
            "❌ 找不到 chatlog-keeper。\n"
            "   请先安装：pip install -e <chatlog-keeper 项目路径>\n"
            f"   原始错误：{e}"
        )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    result = _export_wechat(days=days, out_dir=str(out_dir))

    if not result.get("available"):
        error = result.get("error", "unknown")
        hint = result.get("hint", "")
        raise SystemExit(
            f"❌ 微信导出失败（{error}）\n"
            f"   {hint}\n"
            f"   请确保微信已登录且正在运行，密钥已提取（可先跑 chatlog-keeper probe 检查）。"
        )

    return result