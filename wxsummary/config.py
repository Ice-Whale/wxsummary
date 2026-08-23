"""配置管理：从 .env 文件读取配置（v2）

v2 变化：微信数据库解密已由 chatlog-keeper 完成，
不再需要 WX_DB_KEY，只需要智谱 API 配置和导出 JSON 路径。
"""

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent


@dataclass
class Config:
    """程序运行需要的配置项"""
    export_json: Path        # chatlog-keeper 导出的 JSON 路径
    zhipuai_api_key: str     # GLM API Key
    zhipuai_model: str       # 模型名
    ai_api_base: str         # OpenAI 兼容接口的 base_url
    export_days: int         # 生成日报前自动导出最近多少天（0=不自动导出）


def load_config(require_ai: bool = True) -> Config:
    """加载配置。

    Args:
        require_ai: 是否必须有智谱 API Key（--no-ai 模式不需要）
    """
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    export_json = os.getenv("EXPORT_JSON", "").strip()
    if not export_json:
        # 默认用 chatlog-keeper 的默认导出位置（建议在 .env 里显式配置 EXPORT_JSON）
        export_json = str(Path.home() / "chatlog-keeper" / "export" / "wechat_messages.json")

    zhipuai_api_key = os.getenv("ZHIPUAI_API_KEY", "").strip()
    zhipuai_model = os.getenv("ZHIPUAI_MODEL", "DeepSeek-V4-Flash-0731").strip()
    ai_api_base = os.getenv("AI_API_BASE", "https://ai.paratera.com/v1").strip()

    export_days_raw = os.getenv("EXPORT_DAYS", "7").strip()
    try:
        export_days = int(export_days_raw)
    except ValueError:
        export_days = 7

    if require_ai and not zhipuai_api_key:
        raise SystemExit(
            "❌ 缺少 ZHIPUAI_API_KEY。\n"
            "   请在项目根目录 .env 里填入智谱 API Key，\n"
            "   或使用 --no-ai 只看原始消息。"
        )

    return Config(
        export_json=Path(export_json),
        zhipuai_api_key=zhipuai_api_key,
        zhipuai_model=zhipuai_model,
        ai_api_base=ai_api_base,
        export_days=export_days,
    )
