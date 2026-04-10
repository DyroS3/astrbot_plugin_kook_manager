"""
KOOK 群管理插件
提供 KOOK 平台的群管理功能, 包括欢迎新成员等
"""

import json
import aiohttp
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register


@register("kook_manager", "YWY", "KOOK 群管理工具", "1.0.0")
class KookManagerPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context

    def _get_config(self, key: str, default=None):
        """获取配置项"""
        return self.context.get_config(key, default)

    async def _get_user_info(self, user_id: str, guild_id: str, token: str) -> dict:
        """通过 KOOK API 获取用户信息"""
        url = "https://www.kookapp.cn/api/v3/user/view"
        headers = {"Authorization": f"Bot {token}"}
        params = {"user_id": user_id, "guild_id": guild_id}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("code") == 0:
                            return data.get("data", {})
        except Exception as e:
            logger.error(f"[KookWelcome] 获取用户信息失败: {e}")
        return {}

    async def _send_card_message(self, channel_id: str, card_content: list, token: str):
        """发送卡片消息到指定频道"""
        url = "https://www.kookapp.cn/api/v3/message/create"
        headers = {
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "target_id": channel_id,
            "type": 10,
            "content": json.dumps(card_content)
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    result = await resp.json()
                    if result.get("code") != 0:
                        logger.error(f"[KookWelcome] 发送卡片消息失败: {result}")
                    else:
                        logger.info(f"[KookWelcome] 欢迎卡片发送成功")
                    return result
        except Exception as e:
            logger.error(f"[KookWelcome] 发送卡片消息异常: {e}")
            return None

    def _build_welcome_card(self, user_id: str, username: str, avatar_url: str) -> list:
        """构建欢迎卡片消息"""
        server_name = self._get_config("server_name", "[FiveM] 夜未央")
        welcome_title = self._get_config("welcome_title", "🎉 欢迎新成员加入!")
        welcome_message = self._get_config(
            "welcome_message",
            "欢迎加入 **{server}** 服务器!\n希望您能在这里体验到不同的游戏快乐 🚗"
        )
        button1_text = self._get_config("button1_text", "📝 申请白名单")
        button1_link = self._get_config("button1_link", "")
        button2_text = self._get_config("button2_text", "🎮 连接服务器")
        button2_link = self._get_config("button2_link", "")
        show_guide = self._get_config("show_guide_links", True)
        guide_text = self._get_config(
            "guide_text",
            "📌 新人必看 👉 (chn)规则一览(chn) 👉 (chn)公告通知(chn)\n(chn)角色请求(chn)\n💡 如有问题请联系管理员 | 祝您游戏愉快!"
        )
        card_theme = self._get_config("card_theme", "none")
        card_color = self._get_config("card_color", "#7CFC00")

        welcome_text = welcome_message.replace("{server}", server_name).replace("{user}", f"(met){user_id}(met)")

        modules = [
            {
                "type": "header",
                "text": {
                    "type": "plain-text",
                    "content": welcome_title
                }
            },
            {
                "type": "section",
                "mode": "right",
                "text": {
                    "type": "kmarkdown",
                    "content": f"(met){user_id}(met)\n\n{welcome_text}"
                },
                "accessory": {
                    "type": "image",
                    "src": avatar_url,
                    "size": "lg",
                    "circle": True
                }
            }
        ]

        buttons = []
        if button1_link:
            buttons.append({
                "type": "button",
                "theme": "success",
                "text": {
                    "type": "plain-text",
                    "content": button1_text
                },
                "value": button1_link,
                "click": "link"
            })
        if button2_link:
            buttons.append({
                "type": "button",
                "theme": "primary",
                "text": {
                    "type": "plain-text",
                    "content": button2_text
                },
                "value": button2_link,
                "click": "link"
            })

        if buttons:
            modules.append({
                "type": "action-group",
                "elements": buttons
            })

        if show_guide and guide_text:
            modules.append({"type": "divider"})
            modules.append({
                "type": "context",
                "elements": [
                    {
                        "type": "kmarkdown",
                        "content": guide_text
                    }
                ]
            })

        card = {
            "type": "card",
            "theme": card_theme,
            "size": "lg",
            "modules": modules
        }

        if card_color and card_theme == "none":
            card["color"] = card_color

        return [card]

    def _is_kook_platform(self, event: AstrMessageEvent) -> bool:
        """判断是否为 KOOK 平台事件"""
        try:
            platform_name = getattr(event, "platform_name", "")
            if platform_name and "kook" in platform_name.lower():
                return True

            adapter = getattr(event, "adapter", None)
            if adapter:
                adapter_name = getattr(adapter, "name", "") or type(adapter).__name__
                if "kook" in adapter_name.lower():
                    return True

            raw = getattr(event.message_obj, "raw_message", {})
            if isinstance(raw, dict):
                if "verify_token" in raw or raw.get("channel_type") in ["GROUP", "PERSON"]:
                    return True
        except Exception:
            pass
        return False

    def _extract_bot_token(self, event: AstrMessageEvent) -> str:
        """从事件中提取 Bot Token"""
        try:
            client = getattr(event, "bot", None)
            if client and hasattr(client, "token"):
                return client.token

            adapter = getattr(event, "adapter", None)
            if adapter:
                if hasattr(adapter, "token"):
                    return adapter.token
                if hasattr(adapter, "config") and hasattr(adapter.config, "token"):
                    return adapter.config.token
                if hasattr(adapter, "_token"):
                    return adapter._token

            raw = getattr(event.message_obj, "raw_message", {})
            if isinstance(raw, dict):
                token = raw.get("_bot_token") or raw.get("bot_token")
                if token:
                    return token
        except Exception as e:
            logger.debug(f"[KookWelcome] 提取 token 异常: {e}")
        return ""

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_event(self, event: AstrMessageEvent):
        """监听所有事件, 筛选新成员加入事件"""
        try:
            raw = getattr(event.message_obj, "raw_message", None)
            if not raw or not isinstance(raw, dict):
                return

            if not self._is_kook_platform(event):
                return

            msg_type = raw.get("type")
            if msg_type != 255:
                return

            extra = raw.get("extra", {})
            event_type = extra.get("type", "")

            if event_type != "joined_guild":
                return

            body = extra.get("body", {})
            user_id = body.get("user_id", "")
            guild_id = raw.get("target_id", "")

            if not user_id:
                logger.warning("[KookWelcome] 无法获取新成员用户ID")
                return

            channel_id = self._get_config("welcome_channel_id", "")
            if not channel_id:
                logger.warning("[KookWelcome] 未配置欢迎频道ID, 请在插件配置中设置 welcome_channel_id")
                return

            token = self._extract_bot_token(event)
            if not token:
                logger.error("[KookWelcome] 无法获取 Bot Token, 请检查适配器配置")
                return

            user_info = await self._get_user_info(user_id, guild_id, token)
            username = user_info.get("nickname") or user_info.get("username", f"用户{user_id}")
            avatar_url = user_info.get("avatar", "https://img.kookapp.cn/assets/avatar.png")

            logger.info(f"[KookWelcome] 新成员加入: {username} ({user_id})")

            card = self._build_welcome_card(user_id, username, avatar_url)
            await self._send_card_message(channel_id, card, token)

        except Exception as e:
            logger.error(f"[KookWelcome] 处理事件异常: {e}")
