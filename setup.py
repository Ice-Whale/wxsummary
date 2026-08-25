#!/usr/bin/env python3
"""wxsummary 一键安装脚本（跨平台，当前重点支持 macOS）。

自动完成：
  1. 预检环境（Python / git）
  2. 安装 chatlog-keeper（微信数据库解密与导出）
  3. 安装本项目 wxsummary
  4. probe 探测微信状态
  5. 密钥提取（active 方式，需先退出微信）
  6. 首次导出验证
  7. 引导填写 API Key
  8. 生成 .env

全程只写本地文件，不预置任何第三方 API Key。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

CHATLOG_KEEPER_REPO = "https://github.com/labazhou2024/chatlog-keeper.git"
CHATLOG_KEEPER_DIR = Path.home() / ".chatlog-keeper"

DEFAULT_EXPORT_DIR = Path.home() / "chatlog-keeper" / "export"
DEFAULT_EXPORT_JSON = DEFAULT_EXPORT_DIR / "wechat_messages.json"

# 与 .env.example 保持一致的默认值
DEFAULT_MODEL = "DeepSeek-V4-Flash-0731"
DEFAULT_API_BASE = "https://ai.paratera.com/v1"
DEFAULT_EXPORT_DAYS = "7"

ENV_TEMPLATE = """# ===== 微信群聊日报配置（由 setup.py 自动生成）=====

# chatlog-keeper 导出的 JSON 路径
EXPORT_JSON={export_json}

# 生成日报前自动导出最近多少天的微信数据（0=跳过自动导出）
EXPORT_DAYS={export_days}

# 你的 API Key（paratera / 智谱等平台申请）
ZHIPUAI_API_KEY={api_key}

# 模型名
ZHIPUAI_MODEL={model}

# OpenAI 兼容接口的 base_url
AI_API_BASE={api_base}
"""


# ────────────────────────────────────────────────────────────
# 基础工具
# ────────────────────────────────────────────────────────────

def info(msg: str) -> None:
    print(msg, flush=True)


def ok(msg: str) -> None:
    print(f"✅ {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"⚠️  {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"❌ {msg}", flush=True)


def run(cmd: list[str], cwd=None, timeout=None) -> tuple[int, str, str]:
    """运行命令，返回 (returncode, stdout, stderr)，强制 UTF-8 解码。"""
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", f"找不到命令：{cmd[0]}"
    except subprocess.TimeoutExpired as exc:
        return 124, "", f"命令超时：{' '.join(cmd)}\n{exc}"


def parse_json(text: str):
    """从输出里尽力解析一个 JSON 对象（容错：允许前后有杂讯）。"""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


def input_confirm(prompt: str) -> None:
    """等待用户回车继续（用于「退出微信」等需要手动操作的引导）。"""
    try:
        input(prompt)
    except EOFError:
        pass


# ────────────────────────────────────────────────────────────
# 各安装步骤
# ────────────────────────────────────────────────────────────

def step_preflight() -> bool:
    """预检 Python / git。"""
    info("\n[1/8] 预检环境")
    if sys.version_info < (3, 9):
        fail(f"Python 版本过低（{sys.version.split()[0]}），需要 >= 3.9")
        info("   建议：brew install python@3.11")
        return False
    ok(f"Python {sys.version.split()[0]}")

    if shutil.which("git") is None:
        fail("未检测到 git")
        info("   建议：brew install git")
        return False
    ok("git 可用")
    return True


def step_chatlog_keeper() -> bool:
    """安装 chatlog-keeper（若尚未安装）。"""
    info("\n[2/8] 检查 chatlog-keeper")

    if importlib.util.find_spec("chatlog_keeper") is not None:
        ok("chatlog-keeper 已安装，跳过")
        return True

    info("未检测到 chatlog-keeper，开始安装...")

    if not CHATLOG_KEEPER_DIR.exists():
        info(f"  克隆仓库：{CHATLOG_KEEPER_REPO}")
        rc, _, err = run(["git", "clone", "--depth", "1", CHATLOG_KEEPER_REPO, str(CHATLOG_KEEPER_DIR)])
        if rc != 0:
            fail("克隆 chatlog-keeper 失败，请检查网络")
            info(err.strip())
            return False

    rc, _, err = run([sys.executable, "-m", "pip", "install", "-e", str(CHATLOG_KEEPER_DIR)])
    if rc != 0:
        if "externally-managed" in err:
            fail("pip 拒绝安装到系统 Python（externally-managed）")
            info("   请改用 Homebrew Python：brew install python@3.11")
            info("   然后用 Homebrew 的 python3 重新运行本脚本")
        else:
            fail("安装 chatlog-keeper 失败")
            info(err.strip()[-2000:])
        return False

    ok("chatlog-keeper 安装完成")
    return True


def step_wxsummary() -> bool:
    """安装本项目 wxsummary。"""
    info("\n[3/8] 安装 wxsummary")

    if importlib.util.find_spec("wxsummary") is not None:
        ok("wxsummary 已安装，跳过")
        return True

    rc, _, err = run([sys.executable, "-m", "pip", "install", "-e", str(PROJECT_ROOT)])
    if rc != 0:
        if "externally-managed" in err:
            fail("pip 拒绝安装到系统 Python（externally-managed）")
            info("   请改用 Homebrew Python：brew install python@3.11")
        else:
            fail("安装 wxsummary 失败")
            info(err.strip()[-2000:])
        return False

    ok("wxsummary 安装完成")
    return True


def step_probe() -> dict | None:
    """probe 探测微信状态，返回解析后的 dict（顶层含 wechat）。

    注意：chatlog-keeper 的 wechat probe 中 ``available`` 实际表示「已有可用
    密钥」，而不是「检测到微信数据」。无密钥但存在数据库时会是
    ``available=False`` + ``needs_key=True``，这正是需要引导提取密钥的场景，
    不能据此中止。
    """
    info("\n[4/8] 探测微信状态")
    rc, out, err = run([sys.executable, "-m", "chatlog_keeper.cli", "probe"], timeout=120)
    data = parse_json(out)
    if data is None:
        fail("probe 无有效输出")
        info(err.strip()[-2000:])
        return None

    w = data.get("wechat", {})
    if w.get("error") == "probe_failed":
        fail("微信探测失败")
        info("   请确认已安装并登录过 macOS 版微信（WeChat）。")
        return None

    # 有密钥(available=True) 或 有数据库但缺密钥(needs_key=True) 都算「检测到微信数据」。
    if not (w.get("available") or w.get("needs_key")):
        fail("未检测到微信数据")
        info("   请确认已安装并登录过 macOS 版微信（WeChat）。")
        return None
    return data


def _explain_extract_error(error: str) -> str:
    """把 chatlog-keeper 的常见错误映射为中文指引。"""
    e = (error or "").lower()
    if "quit wechat" in e or "still running" in e or "daily wechat" in e or e == "client_running":
        return "微信仍在运行。请从微信菜单正常退出，等它彻底关闭后再试（不要强制退出）。"
    if e == "cancelled" or "cancel" in e:
        return "提取被取消或窗口超时。请重新执行，并在弹出的微信登录窗口及时扫码确认。"
    if "signature" in e or "signed" in e or "identity" in e:
        return "macOS 签名校验失败。请尝试用 `chatlog-keeper set-key --source wechat` 手动填入密钥。"
    if "login window" in e or "qr" in e:
        return "登录窗口超时或未扫码。请在弹出的微信登录窗口用手机扫码并确认登录。"
    if "no key" in e:
        return "未能提取到密钥。请确认微信已登录，并用手机扫码完成隔离客户端的登录。"
    return f"提取失败：{error}"


def step_key(probe: dict) -> bool:
    """密钥提取（active 方式）。"""
    info("\n[5/8] 检查并准备微信密钥")

    w = probe.get("wechat", {})
    if w.get("enc_keys_present") and not w.get("needs_key"):
        ok("已检测到可用密钥，跳过提取")
        return True

    info("需要提取微信数据库密钥（新版微信必须用 active 方式）。")

    if w.get("client_running"):
        warn("请先【完全退出微信】：")
        info("   1. 在微信菜单栏点「微信」→「退出微信」")
        info("   2. 等它彻底关闭（Dock 图标消失）")
        info("   3. 不要用强制退出（Command+Option+Esc）")
        input_confirm("   → 已退出微信后，按回车继续... ")
    else:
        info("微信当前未运行，直接提取。")

    info("   → 即将启动隔离的官方微信客户端自动登录提取密钥。")
    info("   → 如果弹出登录窗口，请用手机微信扫码并确认登录。")
    info("   → 正在提取（约需 1-3 分钟）...")

    last_error = ""
    for attempt in range(1, 4):
        rc, out, err = run(
            [sys.executable, "-m", "chatlog_keeper.cli", "extract-key",
             "--source", "wechat", "--method", "active"],
            timeout=600,
        )
        data = parse_json(out)
        if data and data.get("ok"):
            ok("密钥提取成功")
            return True

        if data:
            last_error = (
                data.get("error")
                or data.get("_key_recovery_error_code")
                or data.get("key_recovery_flow", {}).get("source", "")
                or ""
            )
        else:
            last_error = err.strip()[-500:]
        fail(f"第 {attempt} 次提取未成功")
        info("   " + _explain_extract_error(last_error))
        if attempt < 3:
            input_confirm("   → 解决后按回车重试（Ctrl+C 跳过）... ")
        else:
            info("   多次失败可稍后手动执行：")
            info("   python -m chatlog_keeper.cli extract-key --source wechat --method active")
            return False
    return False


def step_export(export_dir: Path) -> bool:
    """首次导出验证（微信需重新打开并登录）。"""
    info("\n[6/8] 首次导出验证")
    export_dir.mkdir(parents=True, exist_ok=True)

    warn("密钥提取完成后，请重新打开微信并登录（日常客户端即可）。")
    input_confirm("   → 微信已重新打开并登录后，按回车继续... ")

    info("   正在导出最近 7 天的聊天记录（约需 1-3 分钟）...")
    rc, out, err = run(
        [sys.executable, "-m", "chatlog_keeper.cli", "wechat",
         "--days", "7", "--out", str(export_dir)],
        timeout=600,
    )
    data = parse_json(out)
    if data and data.get("available") and not data.get("error"):
        n = data.get("n_messages", 0)
        ok(f"导出成功，共 {n} 条消息")
        return True

    # 导出失败不中止（可能只是当前微信未登录等），给出指引即可。
    error = (data or {}).get("error", "") if data else ""
    hint = (data or {}).get("hint", "") if data else ""
    warn("首次导出未成功，可稍后手动重试。")
    info(f"   error: {error}")
    if hint:
        info(f"   hint: {hint}")
    info("   稍后可运行：wxsummary sync --days 7")
    return True


def step_api_key() -> str:
    """引导填写 API Key（getpass 不回显，允许留空稍后填）。"""
    info("\n[7/8] 配置 AI 接口")
    info("请粘贴你的 API Key（paratera / 智谱等平台申请）。")
    info("Key 只写入本地 .env，不会被提交或上传。")
    key = ""
    try:
        import getpass
        raw = getpass.getpass("  API Key（留空则跳过，稍后手动填）：")
        key = (raw or "").strip()
    except Exception:
        raw = input("  API Key（留空则跳过，稍后手动填）：")
        key = (raw or "").strip()
    if not key:
        warn("未填写 API Key，稍后请在项目根目录 .env 里补填 ZHIPUAI_API_KEY")
    return key


def step_env(export_json: Path, api_key: str) -> bool:
    """生成 .env（保留已存在的用户配置，仅更新必要项）。"""
    info("\n[8/8] 生成 .env")

    env_path = PROJECT_ROOT / ".env"
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()

    api_key_final = api_key or existing.get("ZHIPUAI_API_KEY", "")
    model = existing.get("ZHIPUAI_MODEL") or DEFAULT_MODEL
    api_base = existing.get("AI_API_BASE") or DEFAULT_API_BASE
    export_days = existing.get("EXPORT_DAYS") or DEFAULT_EXPORT_DAYS

    content = ENV_TEMPLATE.format(
        export_json=str(export_json),
        export_days=export_days,
        api_key=api_key_final,
        model=model,
        api_base=api_base,
    )
    env_path.write_text(content, encoding="utf-8")
    ok(f"已写入 {env_path}")
    info(f"   EXPORT_JSON = {export_json}")
    info(f"   ZHIPUAI_API_KEY = {'已填写' if api_key_final else '（空，请稍后补填）'}")
    return True


def step_done() -> None:
    info("\n" + "=" * 56)
    info("🎉 全部配置完成！")
    info("=" * 56)
    info("常用命令：")
    info("  wxsummary today                # 今天的 AI 日报")
    info("  wxsummary yesterday            # 昨天的 AI 日报")
    info("  wxsummary today --no-ai        # 只看原始消息，不调 AI")
    info("  wxsummary info                 # 查看导出数据统计")
    info("")
    info("如果命令未注册，可用：python -m wxsummary.cli today")
    info("")


# ────────────────────────────────────────────────────────────
# 主流程
# ────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="wxsummary 一键安装脚本")
    parser.add_argument(
        "--export-dir",
        type=str,
        default=str(DEFAULT_EXPORT_DIR),
        help=f"微信导出目录（默认 {DEFAULT_EXPORT_DIR}）",
    )
    args = parser.parse_args()

    export_dir = Path(args.export_dir).expanduser()
    export_json = export_dir / "wechat_messages.json"

    print("=" * 56, flush=True)
    print("  wxsummary · 微信群聊日报一键安装", flush=True)
    print("=" * 56, flush=True)

    if not step_preflight():
        return 1
    if not step_chatlog_keeper():
        return 1
    if not step_wxsummary():
        return 1

    probe = step_probe()
    if probe is None:
        return 1

    if not step_key(probe):
        return 1

    if not step_export(export_dir):
        return 1

    api_key = step_api_key()
    if not step_env(export_json, api_key):
        return 1

    step_done()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n已取消。", flush=True)
        sys.exit(130)