"""
KOOK 群管理插件
提供 KOOK 平台的群管理功能, 包括关键词自动回复, 主动消息发送, 以及新成员欢迎/告别等
"""

import asyncio
import json
from pathlib import Path
import re
from typing import Any

import aiohttp
from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Plain, Reply

from .lifecycle.kook_lifecycle_adapter import KookLifecycleAdapter  # noqa: F401

LIFECYCLE_EVENT_TYPES = {
    "joined_guild",
    "exited_guild",
}
"""当前关注的 KOOK 系统事件子类型, 详见 KOOK 事件结构文档"""

LIFECYCLE_HOOK_MAX_WAIT_SECONDS = 120
"""等待官方 KOOK 适配器就绪的最长时间, 超过则放弃 hook"""


@register("kook_manager", "YWY", "KOOK 群管理工具", "1.7.2")
class KookManagerPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._lifecycle_hook_task: asyncio.Task | None = None
        try:
            loop = asyncio.get_running_loop()
            self._lifecycle_hook_task = loop.create_task(
                self._install_kook_lifecycle_hook(),
                name="kook_manager_lifecycle_hook",
            )
        except RuntimeError:
            logger.warning(
                "[KookManager] 当前无运行中的事件循环, 跳过 lifecycle hook 安装. "
                "如需新成员欢迎功能, 请确认 AstrBot 已启动事件循环",
            )

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

    def _get_allowed_role_ids(self) -> set[str]:
        """获取允许执行管理命令的 KOOK 角色 ID 列表"""
        raw_value = self._get_config("allowed_role_ids", "")
        if isinstance(raw_value, list):
            items = raw_value
        else:
            items = str(raw_value).replace("\n", ",").split(",")
        return {str(item).strip() for item in items if str(item).strip()}

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

    def _is_astr_admin(self, event: AstrMessageEvent) -> bool:
        """兼容不同 AstrBot 版本的管理员判定字段"""
        role = str(getattr(event, "role", "")).lower()
        if role == "admin":
            return True

        permission_type = getattr(filter, "PermissionType", None)
        if permission_type is not None:
            admin_value = getattr(permission_type, "ADMIN", None)
            event_permission = getattr(event, "permission_type", None)
            if admin_value is not None and event_permission == admin_value:
                return True
        return False

    def _get_message_attr(self, event: AstrMessageEvent, attr_name: str) -> str:
        """从消息对象中安全提取字段"""
        message_obj = getattr(event, "message_obj", None)
        if message_obj is None:
            return ""

        value = getattr(message_obj, attr_name, "")
        if value:
            return str(value).strip()

        if isinstance(message_obj, dict):
            raw_value = message_obj.get(attr_name, "")
            if raw_value:
                return str(raw_value).strip()

        raw_message = getattr(message_obj, "raw_message", None)
        if raw_message is not None:
            raw_value = getattr(raw_message, attr_name, "")
            if raw_value:
                return str(raw_value).strip()
            if isinstance(raw_message, dict):
                raw_value = raw_message.get(attr_name, "")
                if raw_value:
                    return str(raw_value).strip()

        return ""

    def _get_event_guild_id(self, event: AstrMessageEvent) -> str:
        """尽量从当前消息上下文提取 guild_id"""
        for attr_name in ("guild_id", "target_guild_id"):
            value = self._get_message_attr(event, attr_name)
            if value:
                return value
        return ""

    def _get_event_channel_id(self, event: AstrMessageEvent) -> str:
        """尽量从当前消息上下文提取 channel_id"""
        for attr_name in ("channel_id", "target_id", "session_id", "conversation_id", "group_id"):
            value = self._get_message_attr(event, attr_name)
            if value:
                return value

        message_str = str(getattr(event, "message_str", "")).strip()
        if message_str:
            match = re.match(r"^/?\S+\s+(\S+)", message_str)
            if match:
                return match.group(1).strip()
        return ""

    async def _get_guild_id_by_channel_id(self, channel_id: str) -> str:
        """通过频道 ID 反查 guild_id"""
        params = {
            "target_id": channel_id,
        }
        data = await self._request_kook_api("GET", "/channel/view", params=params)
        guild_id = str(data.get("guild_id", "")).strip()
        if not guild_id:
            raise ValueError(f"频道 {channel_id} 未返回 guild_id")
        return guild_id

    async def _get_kook_guild_member_roles(self, guild_id: str, user_id: str) -> set[str]:
        """查询用户在指定服务器中的角色 ID 集合"""
        params = {
            "guild_id": guild_id,
            "filter_user_id": user_id,
            "page": 1,
            "page_size": 1,
        }
        data = await self._request_kook_api("GET", "/guild/user-list", params=params)
        items = data.get("items", [])
        if not items:
            return set()
        roles = items[0].get("roles", [])
        return {str(role_id).strip() for role_id in roles if str(role_id).strip()}

    async def _ensure_manage_permission(self, event: AstrMessageEvent) -> str | None:
        """检查管理命令权限, 返回错误信息或 None"""
        if self._is_astr_admin(event):
            return None

        allowed_role_ids = self._get_allowed_role_ids()
        if not allowed_role_ids:
            return "您未被授予该指令权限. 请让管理员将您的 UID 加入 AstrBot 管理员名单, 或在插件配置中添加 allowed_role_ids."

        guild_id = self._get_event_guild_id(event)
        if not guild_id:
            channel_id = self._get_event_channel_id(event)
            if not channel_id:
                return "当前消息上下文无法识别 guild_id 或 channel_id, 不能按 KOOK 角色判权. 请在服务器频道内使用该指令, 或让管理员将您的 UID 加入 AstrBot 管理员名单."
            try:
                guild_id = await self._get_guild_id_by_channel_id(channel_id)
            except Exception as exc:
                logger.error(f"[KookManager] 通过频道反查 guild_id 失败: {exc}")
                return f"当前消息上下文无法识别 guild_id, 且通过 channel_id={channel_id} 反查失败: {exc}"

        user_id = str(event.get_sender_id()).strip()
        if not user_id:
            return "当前消息上下文无法识别发送者 ID, 无法完成权限检查."

        try:
            member_roles = await self._get_kook_guild_member_roles(guild_id, user_id)
        except Exception as exc:
            logger.error(f"[KookManager] 查询 KOOK 角色失败: {exc}")
            return f"权限检查失败: 无法查询您在当前服务器中的 KOOK 角色. {exc}"

        if member_roles.intersection(allowed_role_ids):
            return None

        return (
            "您未被授予该指令权限. "
            f"当前服务器未命中允许角色, allowed_role_ids={sorted(allowed_role_ids)}, user_roles={sorted(member_roles)}"
        )

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

    async def _request_kook_api(
        self,
        method: str,
        api_path: str,
        *,
        json_payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """统一调用 KOOK HTTP API"""
        token = self._get_kook_bot_token()
        if not token:
            raise ValueError("未配置 kook_bot_token")

        headers = {
            "Authorization": f"Bot {token}",
        }
        if json_payload is not None:
            headers["Content-Type"] = "application/json"

        url = f"{self._get_kook_api_base()}{api_path}"

        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method=method.upper(),
                url=url,
                headers=headers,
                json=json_payload,
                params=params,
            ) as response:
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

    async def _send_kook_channel_message(self, channel_id: str, content: str, message_type: int) -> dict[str, Any]:
        """调用 KOOK HTTP API 向指定频道发送消息"""
        payload = {
            "target_id": channel_id,
            "content": content,
            "type": message_type,
        }
        return await self._request_kook_api("POST", "/message/create", json_payload=payload)

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

    @filter.command("kooksendmd")
    async def send_kmarkdown(self, event: AstrMessageEvent):
        """向指定 KOOK 频道发送 KMarkdown, 用法: /kooksendmd <channel_id> <content>"""
        permission_error = await self._ensure_manage_permission(event)
        if permission_error:
            yield event.plain_result(permission_error)
            return

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

    @filter.command("kooksendcard")
    async def send_card(self, event: AstrMessageEvent):
        """向指定 KOOK 频道发送卡片消息, 用法: /kooksendcard <channel_id> <card_json>"""
        permission_error = await self._ensure_manage_permission(event)
        if permission_error:
            yield event.plain_result(permission_error)
            return

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

    @filter.command("kooksendcardfile")
    async def send_card_from_file(self, event: AstrMessageEvent):
        """从文件读取卡片 JSON 并发送, 用法: /kooksendcardfile <channel_id> <file_path>"""
        permission_error = await self._ensure_manage_permission(event)
        if permission_error:
            yield event.plain_result(permission_error)
            return

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

    async def terminate(self) -> None:
        """插件停止时清理 lifecycle hook 任务并恢复官方 KOOK 客户端原始回调"""
        if self._lifecycle_hook_task and not self._lifecycle_hook_task.done():
            self._lifecycle_hook_task.cancel()
            try:
                await self._lifecycle_hook_task
            except (asyncio.CancelledError, Exception):
                pass
        self._uninstall_kook_lifecycle_hook()

    async def _install_kook_lifecycle_hook(self) -> None:
        """循环查找官方 KOOK 适配器并 hook 其 client.event_callback"""
        deadline = asyncio.get_event_loop().time() + LIFECYCLE_HOOK_MAX_WAIT_SECONDS
        while True:
            kook_adapter = self._find_kook_adapter()
            lifecycle_adapter = KookLifecycleAdapter.get_instance()
            if kook_adapter is not None and lifecycle_adapter is not None:
                client = getattr(kook_adapter, "client", None)
                if client is not None and not getattr(client, "_lifecycle_hooked", False):
                    self._wrap_client_callback(client, lifecycle_adapter)
                    logger.info(
                        "[KookManager] 已 hook 官方 KOOK 适配器, 开始监听生命周期事件",
                    )
                    return

            if asyncio.get_event_loop().time() > deadline:
                logger.warning(
                    "[KookManager] 等待官方 KOOK 适配器或 kook_lifecycle 伴生适配器超时, "
                    "生命周期事件 (新成员欢迎/告别) 不会被触发. "
                    "请在 AstrBot 后台同时启用 kook 与 kook_lifecycle 平台适配器",
                )
                return

            await asyncio.sleep(2)

    def _find_kook_adapter(self):
        """在 platform_manager 已加载的实例中查找官方 KOOK 适配器"""
        try:
            platform_manager = getattr(self.context, "platform_manager", None)
            if platform_manager is None:
                return None
            for inst in platform_manager.get_insts():
                try:
                    if inst.meta().name == "kook":
                        return inst
                except Exception:
                    continue
        except Exception as exc:
            logger.debug(f"[KookManager] 查找 KOOK 适配器异常: {exc}")
        return None

    def _wrap_client_callback(self, client, lifecycle_adapter: KookLifecycleAdapter) -> None:
        """把官方 KookClient.event_callback 包装一层, 拦截关注的系统事件"""
        original_callback = client.event_callback
        plugin_self = self

        async def wrapped_callback(event_data):
            try:
                bot_id = str(getattr(client, "bot_id", "")).strip()
                plugin_self._maybe_emit_lifecycle_event(
                    event_data, bot_id, lifecycle_adapter,
                )
            except Exception as exc:
                logger.error(f"[KookManager] 转发生命周期事件失败: {exc}")
            await original_callback(event_data)

        client._lifecycle_original_callback = original_callback
        client._lifecycle_hooked = True
        client.event_callback = wrapped_callback

    def _uninstall_kook_lifecycle_hook(self) -> None:
        """恢复官方 KOOK 客户端的原始 event_callback (插件 terminate 时调用)"""
        kook_adapter = self._find_kook_adapter()
        if kook_adapter is None:
            return
        client = getattr(kook_adapter, "client", None)
        if client is None or not getattr(client, "_lifecycle_hooked", False):
            return
        original_callback = getattr(client, "_lifecycle_original_callback", None)
        if original_callback is not None:
            client.event_callback = original_callback
            try:
                delattr(client, "_lifecycle_original_callback")
            except AttributeError:
                pass
        client._lifecycle_hooked = False
        logger.info("[KookManager] 已恢复官方 KOOK 适配器原始 event_callback")

    def _maybe_emit_lifecycle_event(
        self,
        event_data: Any,
        bot_id: str,
        lifecycle_adapter: KookLifecycleAdapter,
    ) -> None:
        """判断是否为关注的 KOOK 系统事件, 若是则提交到伴生适配器"""
        if event_data is None:
            return

        # KOOK SYSTEM 消息类型为 255, 兼容 IntEnum 与 int
        type_value = getattr(event_data, "type", None)
        type_value = getattr(type_value, "value", type_value)
        try:
            if int(type_value) != 255:
                return
        except (TypeError, ValueError):
            return

        extra = getattr(event_data, "extra", None)
        if extra is None:
            return
        sub_type = str(getattr(extra, "type", "")).strip()
        if sub_type not in LIFECYCLE_EVENT_TYPES:
            return

        # 把 pydantic 模型转成 dict, 让插件层不依赖具体类型
        raw_dict = self._event_data_to_dict(event_data)
        if not raw_dict:
            logger.debug("[KookManager] 无法将事件序列化为 dict, 跳过")
            return
        lifecycle_adapter.commit_lifecycle_event(raw_dict, bot_id)

    @staticmethod
    def _event_data_to_dict(event_data: Any) -> dict[str, Any]:
        """尽量把 KOOK 适配器内部的事件对象转成原生 dict"""
        if isinstance(event_data, dict):
            return event_data
        for attr in ("to_dict", "model_dump"):
            method = getattr(event_data, attr, None)
            if callable(method):
                try:
                    if attr == "model_dump":
                        result = method(mode="json", by_alias=True)
                    else:
                        result = method()
                except Exception:
                    continue
                if isinstance(result, dict):
                    return result
        return {}

    @filter.event_message_type(filter.EventMessageType.OTHER_MESSAGE)
    async def on_kook_lifecycle_event(self, event: AstrMessageEvent):
        """处理由 kook_lifecycle 伴生适配器投递的 KOOK 生命周期事件"""
        platform_meta = getattr(event, "platform_meta", None)
        platform_name = getattr(platform_meta, "name", "") if platform_meta else ""
        if platform_name != "kook_lifecycle":
            return

        raw = getattr(event.message_obj, "raw_message", None)
        if not isinstance(raw, dict):
            return
        sub_type = str(raw.get("extra", {}).get("type", "")).strip()
        try:
            if sub_type == "joined_guild":
                await self._handle_member_joined(raw)
            elif sub_type == "exited_guild":
                await self._handle_member_exited(raw)
        except Exception as exc:
            logger.error(f"[KookManager] 处理 KOOK 生命周期事件失败: sub_type={sub_type}, {exc}")

    async def _handle_member_joined(self, raw: dict[str, Any]) -> None:
        """处理 joined_guild 事件: 加载欢迎卡片模板并发送到欢迎频道"""
        if not bool(self._get_config("enable_welcome", False)):
            return

        channel_id = str(self._get_config("welcome_channel_id", "")).strip()
        if not channel_id:
            logger.warning(
                "[KookManager] 已启用 enable_welcome 但 welcome_channel_id 为空, 跳过欢迎",
            )
            return

        body = raw.get("extra", {}).get("body", {}) or {}
        guild_id = str(raw.get("target_id", "")).strip()
        user_id = str(body.get("user_id", "")).strip()

        # 反查 KOOK 用户头像与昵称, 失败不会阻断后续渲染
        user_avatar, user_name = await self._fetch_kook_user_info(guild_id, user_id)

        placeholders = {
            "user_id": user_id,
            "user_name": user_name,
            "user_avatar": user_avatar,
            "guild_id": guild_id,
            "server_name": str(self._get_config("welcome_server_name", "")).strip(),
            "apply_whitelist_url": str(self._get_config("welcome_apply_whitelist_url", "")).strip(),
            "connect_server_url": str(self._get_config("welcome_connect_server_url", "")).strip(),
            "navigation_text": str(self._get_config(
                "welcome_navigation_text",
                "📢 新人必看  |  📖 规则一览  |  📢 公告通知  |  📋 角色请求",
            )),
        }

        card_payload = self._load_welcome_card_payload(placeholders)
        if card_payload is not None:
            try:
                await self._send_kook_channel_message(channel_id, card_payload, 10)
                logger.info(
                    f"[KookManager] 已发送欢迎卡片: channel_id={channel_id}, user_id={user_id}",
                )
                return
            except Exception as exc:
                logger.error(f"[KookManager] 发送欢迎卡片失败, 改用兜底文本: {exc}")

        fallback_template = str(self._get_config(
            "welcome_text_fallback",
            "(met){user_id}(met) 欢迎加入本服务器! 祝您游戏愉快.",
        ))
        fallback_text = self._apply_placeholders(fallback_template, placeholders)
        try:
            await self._send_kook_channel_message(
                channel_id,
                self._normalize_text_content(fallback_text),
                9,
            )
            logger.info(
                f"[KookManager] 已发送欢迎兜底文本: channel_id={channel_id}, user_id={user_id}",
            )
        except Exception as exc:
            logger.error(f"[KookManager] 发送欢迎兜底文本失败: {exc}")

    async def _handle_member_exited(self, raw: dict[str, Any]) -> None:
        """处理 exited_guild 事件: 发送告别消息 (实验功能, 默认关闭)"""
        if not bool(self._get_config("enable_farewell", False)):
            return

        channel_id = str(self._get_config("farewell_channel_id", "")).strip()
        if not channel_id:
            logger.warning(
                "[KookManager] 已启用 enable_farewell 但 farewell_channel_id 为空, 跳过告别",
            )
            return

        body = raw.get("extra", {}).get("body", {}) or {}
        placeholders = {
            "user_id": str(body.get("user_id", "")).strip(),
            "user_name": str(body.get("user_id", "")).strip(),
            "guild_id": str(raw.get("target_id", "")).strip(),
        }
        template = str(self._get_config(
            "farewell_text",
            "👋 (met){user_id}(met) 已离开服务器, 期待下次再见.",
        ))
        text = self._apply_placeholders(template, placeholders)
        try:
            await self._send_kook_channel_message(
                channel_id,
                self._normalize_text_content(text),
                9,
            )
            logger.info(
                f"[KookManager] 已发送告别消息: channel_id={channel_id}, user_id={placeholders['user_id']}",
            )
        except Exception as exc:
            logger.error(f"[KookManager] 发送告别消息失败: {exc}")

    def _load_welcome_card_payload(self, placeholders: dict[str, str]) -> str | None:
        """读取欢迎卡片模板, 替换占位符并返回标准化后的 KOOK Card JSON 字符串"""
        raw_path = str(self._get_config("welcome_card_path", "lifecycle/cards/welcome.json")).strip()
        if not raw_path:
            return None
        try:
            file_path = self._resolve_card_file_path(raw_path)
            if not file_path.exists() or not file_path.is_file():
                logger.warning(f"[KookManager] 欢迎卡片模板不存在: {file_path}")
                return None
            template = file_path.read_text(encoding="utf-8")
            # 卡片模板走 JSON, 需对占位符值做 JSON 字符串转义, 避免昵称/URL 中的
            # 双引号、反斜杠、控制字符破坏 JSON 结构
            replaced = self._apply_placeholders(template, placeholders, json_safe=True)
            return self._load_card_payload(replaced, f"欢迎卡片 {file_path.name}")
        except Exception as exc:
            logger.error(f"[KookManager] 加载欢迎卡片模板失败: {exc}")
            return None

    async def _fetch_kook_user_info(self, guild_id: str, user_id: str) -> tuple[str, str]:
        """反查 KOOK 用户头像与昵称

        Args:
            guild_id: 服务器 ID, 为空时仅查询全局用户信息
            user_id: KOOK 用户 ID

        Returns:
            tuple[str, str]: (avatar_url, display_name). 反查失败时返回 ("", user_id).
        """
        if not user_id:
            return "", user_id
        params: dict[str, Any] = {"user_id": user_id}
        if guild_id:
            params["guild_id"] = guild_id
        try:
            data = await self._request_kook_api("GET", "/user/view", params=params)
            avatar = str(data.get("avatar", "")).strip()
            nickname = (
                str(data.get("nickname", "")).strip()
                or str(data.get("username", "")).strip()
            )
            return avatar, nickname or user_id
        except Exception as exc:
            logger.warning(
                f"[KookManager] 反查 KOOK 用户信息失败 user_id={user_id}: {exc}",
            )
            return "", user_id

    @staticmethod
    def _apply_placeholders(
        text: str,
        placeholders: dict[str, str],
        json_safe: bool = False,
    ) -> str:
        """对模板做最简占位符替换, 不依赖 str.format 以避免 KMarkdown/JSON 中的花括号干扰

        Args:
            text: 原始模板字符串
            placeholders: 占位符名 -> 值的映射
            json_safe: 若为 True, 则对值做 JSON 字符串转义后再插入模板, 适用于卡片 JSON
        """
        result = text
        for key, value in placeholders.items():
            if json_safe:
                # json.dumps 返回带外层双引号的字符串, 去掉外层双引号后即为合法的 JSON 字符串字面量
                replaced_value = json.dumps(value, ensure_ascii=False)[1:-1]
            else:
                replaced_value = value
            result = result.replace("{" + key + "}", replaced_value)
        return result
