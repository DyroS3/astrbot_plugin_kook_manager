"""
KOOK 群管理插件
提供 KOOK 平台的群管理功能, 包括关键词自动回复等
"""

import json
from pathlib import Path
import re
from typing import Any

import aiohttp
from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Plain, Reply


@register("kook_manager", "YWY", "KOOK 群管理工具", "1.5.0")
class KookManagerPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    def _get_config(self, key: str, default=None):
        """获取配置项"""
        return self.config.get(key, default)

    def _get_kook_api_base(self) -> str:
        """获取 KOOK API 根地址"""
        api_base = str(self._get_config("kook_api_base", "https://www.kookapp.cn/api/v3")).strip()
        return api_base.rstrip("/")

    def _get_kook_bot_token(self) -> str:
        """获取 KOOK Bot Token"""
        return str(self._get_config("kook_bot_token", "")).strip()

    def _extract_command_payload(self, message: str) -> tuple[str | None, str | None]:
        """从指令文本中提取频道 ID 和剩余内容"""
        normalized = message.strip()
        match = re.match(r"^/?\S+\s+(\S+)\s+([\s\S]+)$", normalized)
        if not match:
            return None, None
        channel_id = match.group(1).strip()
        payload = match.group(2).strip()
        if not channel_id or not payload:
            return None, None
        return channel_id, payload

    def _normalize_text_content(self, content: str) -> str:
        """兼容实际换行和转义换行"""
        return content.replace("\\n", "\n").strip()

    def _resolve_card_file_path(self, raw_path: str) -> Path:
        """解析卡片文件路径, 支持绝对路径和相对插件目录路径"""
        file_path = Path(raw_path.strip().strip("\"'"))
        if not file_path.is_absolute():
            file_path = Path(__file__).resolve().parent / file_path
        return file_path.resolve()

    def _load_card_payload(self, content: str, source: str) -> str:
        """校验并标准化卡片 JSON"""
        try:
            card_payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source} JSON 解析失败: {exc}") from exc

        if not isinstance(card_payload, (dict, list)):
            raise ValueError(f"{source} JSON 必须是 object 或 array")

        return json.dumps(card_payload, ensure_ascii=False)

    async def _send_kook_channel_message(self, channel_id: str, content: str, message_type: int) -> dict[str, Any]:
        """调用 KOOK HTTP API 向指定频道发送消息"""
        token = self._get_kook_bot_token()
        if not token:
            raise ValueError("未配置 kook_bot_token")

        payload = {
            "target_id": channel_id,
            "content": content,
            "type": message_type,
        }
        headers = {
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
        }
        url = f"{self._get_kook_api_base()}/message/create"

        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response_text = await response.text()
                if response.status != 200:
                    raise RuntimeError(
                        f"KOOK API 请求失败, status={response.status}, body={response_text}"
                    )
                try:
                    data = json.loads(response_text)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"KOOK API 返回了无法解析的响应: {response_text}") from exc

        if data.get("code") != 0:
            raise RuntimeError(
                f"KOOK API 返回错误, code={data.get('code')}, message={data.get('message')}"
            )
        return data.get("data", {})

    def _parse_keyword_rules(self) -> list[dict]:
        """解析关键词规则配置"""
        rules_text = self._get_config("keyword_rules", "")
        if not rules_text:
            return []

        rules = []
        for line in rules_text.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if "=>" in line:
                parts = line.split("=>", 1)
                if len(parts) == 2:
                    keyword = parts[0].strip()
                    response = parts[1].strip()
                    if keyword and response:
                        rules.append({
                            "keyword": keyword,
                            "response": response,
                            "is_regex": keyword.startswith("r:"),
                        })
        return rules

    def _match_keyword(self, message: str, rule: dict) -> bool:
        """检查消息是否匹配关键词"""
        keyword = rule["keyword"]
        match_mode = self._get_config("match_mode", "contains")

        if rule["is_regex"]:
            pattern = keyword[2:]
            try:
                return bool(re.search(pattern, message, re.IGNORECASE))
            except re.error:
                logger.error(f"[KookManager] 正则表达式错误: {pattern}")
                return False

        message_lower = message.lower()
        keyword_lower = keyword.lower()

        if match_mode == "exact":
            return message_lower == keyword_lower
        elif match_mode == "startswith":
            return message_lower.startswith(keyword_lower)
        elif match_mode == "endswith":
            return message_lower.endswith(keyword_lower)
        else:
            return keyword_lower in message_lower

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("kooksendmd")
    async def send_kmarkdown(self, event: AstrMessageEvent):
        """向指定 KOOK 频道发送 KMarkdown, 用法: /kooksendmd <channel_id> <content>"""
        channel_id, content = self._extract_command_payload(event.message_str)
        if not channel_id or not content:
            yield event.plain_result("用法: /kooksendmd <channel_id> <content>")
            return

        try:
            normalized_content = self._normalize_text_content(content)
            result = await self._send_kook_channel_message(channel_id, normalized_content, 9)
            msg_id = result.get("msg_id", "unknown")
            yield event.plain_result(f"发送成功, channel_id={channel_id}, msg_id={msg_id}")
        except Exception as exc:
            logger.error(f"[KookManager] 发送 KMarkdown 失败: {exc}")
            yield event.plain_result(f"发送失败: {exc}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("kooksendcard")
    async def send_card(self, event: AstrMessageEvent):
        """向指定 KOOK 频道发送卡片消息, 用法: /kooksendcard <channel_id> <card_json>"""
        channel_id, content = self._extract_command_payload(event.message_str)
        if not channel_id or not content:
            yield event.plain_result("用法: /kooksendcard <channel_id> <card_json>")
            return

        try:
            normalized_content = self._load_card_payload(content, "卡片")
            result = await self._send_kook_channel_message(channel_id, normalized_content, 10)
            msg_id = result.get("msg_id", "unknown")
            yield event.plain_result(f"发送成功, channel_id={channel_id}, msg_id={msg_id}")
        except Exception as exc:
            logger.error(f"[KookManager] 发送卡片消息失败: {exc}")
            yield event.plain_result(f"发送失败: {exc}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("kooksendcardfile")
    async def send_card_from_file(self, event: AstrMessageEvent):
        """从文件读取卡片 JSON 并发送, 用法: /kooksendcardfile <channel_id> <file_path>"""
        channel_id, raw_path = self._extract_command_payload(event.message_str)
        if not channel_id or not raw_path:
            yield event.plain_result("用法: /kooksendcardfile <channel_id> <file_path>")
            return

        try:
            file_path = self._resolve_card_file_path(raw_path)
            if not file_path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")
            if not file_path.is_file():
                raise ValueError(f"目标不是文件: {file_path}")

            content = file_path.read_text(encoding="utf-8")
            normalized_content = self._load_card_payload(content, f"文件 {file_path}")
            result = await self._send_kook_channel_message(channel_id, normalized_content, 10)
            msg_id = result.get("msg_id", "unknown")
            yield event.plain_result(f"发送成功, channel_id={channel_id}, msg_id={msg_id}, file={file_path.name}")
        except Exception as exc:
            logger.error(f"[KookManager] 从文件发送卡片消息失败: {exc}")
            yield event.plain_result(f"发送失败: {exc}")

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """监听群消息, 匹配关键词并回复"""
        try:
            enable_keyword = self._get_config("enable_keyword_reply", True)
            if not enable_keyword:
                return

            message = event.message_str.strip()
            if not message:
                return

            rules = self._parse_keyword_rules()
            if not rules:
                return

            enable_reply_quote = self._get_config("enable_reply_quote", True)
            enable_mention_user = self._get_config("enable_mention_user", True)

            for rule in rules:
                if self._match_keyword(message, rule):
                    response_text = rule["response"]
                    response_text = response_text.replace("\\n", "\n")

                    logger.info(f"[KookManager] 关键词匹配: '{rule['keyword']}' -> 回复")

                    if enable_mention_user:
                        sender_id = event.get_sender_id()
                        response_text = f"(met){sender_id}(met) {response_text}"

                    chain = []
                    if enable_reply_quote:
                        chain.append(Reply(id=event.message_obj.message_id))
                    chain.append(Plain(text=response_text))

                    yield event.chain_result(chain)

                    only_first = self._get_config("only_first_match", True)
                    if only_first:
                        break

        except Exception as e:
            logger.error(f"[KookManager] 处理消息异常: {e}")
