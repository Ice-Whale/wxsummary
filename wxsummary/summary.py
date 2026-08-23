"""消息拉取和聚合模块（数据源：chatlog-keeper 导出的 JSON）

从 chatlog-keeper 导出的 wechat_messages.json 读取聊天记录，
按日期 + 群/会话聚合，复用 GroupMessages / Message 结构，下游 AI / 日报逻辑不变。

字段对照（chatlog 导出的每条记录 → 本模块 Message）：
  ts               → timestamp / time_str（北京时间）
  sender           → sender_name（显示名）
  sender_wxid      → sender（wxid）
  chat_room        → group_name（群名）
  conversation_id  → talker / group_id（群ID，形如 xxx@chatroom）
  content          → content（文字直接保留；图片/表情等已被 chatlog 标成 [图片]/[表情]）
  msg_type         → msg_type（1=文字，其余为非文字）
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta, timezone

# 微信时间戳是 Unix 时间戳（秒），UTC+8 是中国时间
CHINA_TZ = timezone(timedelta(hours=8))


@dataclass
class Message:
    """一条微信消息"""
    timestamp: int            # Unix 时间戳（秒）
    date_str: str             # 日期 "MM-DD"（跨天聚合时用于区分）
    time_str: str             # 可读时间 "HH:MM:SS"
    sender: str               # 发送者 wxid
    sender_name: str          # 发送者昵称（显示名）
    content: str              # 消息内容（文字或类型标注，如 [图片]）
    msg_type: int             # 微信消息类型
    is_text: bool             # 是否是文字消息
    talker: str               # 会话ID（群聊的 chatroomID）


@dataclass
class GroupMessages:
    """一个群（或会话）的消息集合"""
    group_id: str             # 群ID（如 xxxxx@chatroom）
    group_name: str          # 群名 / 会话名
    messages: list[Message] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.messages)

    @property
    def text_count(self) -> int:
        """文字消息数（可喂给AI的）"""
        return sum(1 for m in self.messages if m.is_text)


# 微信文字消息类型（与 chatlog 导出一致）
MSG_TYPE_TEXT = 1


def load_export(path) -> list[dict]:
    """读取 chatlog 导出的 JSON 文件，返回消息记录列表。

    每条记录形如：
    {"ts":..., "sender":..., "sender_wxid":..., "chat_room":...,
     "conversation_id":..., "content":..., "msg_type":..., ...}
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _date_to_timestamps(target_date: date) -> tuple[int, int]:
    """把日期转成当天的起止 Unix 时间戳（中国时区）"""
    start_dt = datetime.combine(target_date, time.min).replace(tzinfo=CHINA_TZ)
    end_dt = start_dt + timedelta(days=1)
    return int(start_dt.timestamp()), int(end_dt.timestamp())


def fetch_groups_for_date(export_path, target_date: date,
                          include_direct: bool = False) -> list[GroupMessages]:
    """拉取指定日期的群聊（或会话）消息，按会话分组。

    Args:
        export_path: chatlog 导出的 JSON 文件路径
        target_date: 要生成的日期
        include_direct: 是否也包含私聊（默认只统计群聊）
    """
    records = load_export(export_path)
    start_ts, end_ts = _date_to_timestamps(target_date)

    all_groups: dict[str, GroupMessages] = {}

    for rec in records:
        # 默认只处理群聊；include_direct=True 时才把私聊也纳入
        is_group = rec.get("is_group_chat", False) or rec.get("conversation_type") == "group"
        if not is_group and not include_direct:
            continue

        ts = int(float(rec.get("ts", 0) or 0))
        if ts < start_ts or ts >= end_ts:
            continue

        msg_type = int(rec.get("msg_type", 0) or 0)
        content = rec.get("content", "") or ""
        # chatlog 已经把图片/表情/视频等转成可读标签（如 "[图片]"、"[表情: 谢谢]"），
        # 只有 type==1 才是真正的文字消息。
        is_text = (msg_type == MSG_TYPE_TEXT)

        talker = rec.get("conversation_id") or rec.get("chat_room") or ""
        dt = datetime.fromtimestamp(ts, CHINA_TZ)
        time_str = dt.strftime("%H:%M:%S")

        msg = Message(
            timestamp=ts,
            date_str=dt.strftime("%m-%d"),
            time_str=time_str,
            sender=rec.get("sender_wxid", "") or "",
            sender_name=rec.get("sender", "") or "未知",
            content=content,
            msg_type=msg_type,
            is_text=is_text,
            talker=talker,
        )

        if talker not in all_groups:
            all_groups[talker] = GroupMessages(
                group_id=talker,
                group_name=rec.get("chat_room", talker),
            )
        all_groups[talker].messages.append(msg)

    # 按消息数从多到少排序，日报里最活跃的群排最前
    return sorted(all_groups.values(), key=lambda g: g.count, reverse=True)


def fetch_groups_for_range(export_path, start_date: date, end_date: date,
                           include_direct: bool = False) -> list[GroupMessages]:
    """聚合一段时间（含首尾两天）的群聊消息，跨天合并到同一批 GroupMessages。"""
    merged: dict[str, GroupMessages] = {}

    d = start_date
    while d <= end_date:
        for g in fetch_groups_for_date(export_path, d, include_direct=include_direct):
            if g.group_id not in merged:
                merged[g.group_id] = GroupMessages(group_id=g.group_id,
                                                   group_name=g.group_name)
            merged[g.group_id].messages.extend(g.messages)
        d += timedelta(days=1)

    return sorted(merged.values(), key=lambda g: g.count, reverse=True)


def format_group_for_ai(group: GroupMessages) -> str:
    """把一个群的消息格式化成文本，准备喂给 AI"""
    lines = [f"群名：{group.group_name}"]
    lines.append(f"消息数：{group.count}（其中文字 {group.text_count} 条）")
    lines.append("")

    for msg in group.messages:
        lines.append(f"[{msg.date_str} {msg.time_str}] {msg.sender_name}：{msg.content}")

    return "\n".join(lines)


def format_all_groups_for_human(groups: list[GroupMessages], label: str,
                                kind: str = "日报") -> str:
    """生成人类可读的 Markdown 汇总（不带AI总结）"""
    lines = [f"# {label} 群聊{kind}"]
    lines.append("")
    lines.append(f"共 {len(groups)} 个会话有消息。")
    lines.append("")

    for group in groups:
        lines.append(f"## {group.group_name}（{group.count} 条消息）")
        lines.append("")

        show_count = min(20, len(group.messages))
        for msg in group.messages[:show_count]:
            lines.append(f"- [{msg.date_str} {msg.time_str}] {msg.sender_name}：{msg.content}")

        if len(group.messages) > show_count:
            lines.append(f"- ... 还有 {len(group.messages) - show_count} 条消息")

        lines.append("")

    return "\n".join(lines)
