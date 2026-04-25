"""
KOOK 生命周期事件伴生适配器

设计目标:
- 不连接任何外部服务, 不持有 KOOK Token, 不与官方 KOOK 适配器争用 WebSocket.
- 仅作为 AstrBot 平台事件入口, 把官方 KOOK 适配器忽略的成员加入/离开等系统事件,
  统一以 ``MessageType.OTHER_MESSAGE`` 推送到事件队列, 让插件可以用标准
  ``@filter.event_message_type(EventMessageType.OTHER_MESSAGE)`` 监听.

集成方式:
- 用户在 AstrBot 后台启用 ``kook_lifecycle`` 适配器即可, 无需任何额外配置.
- 实际的 hook (替换官方 KOOK 适配器的 client.event_callback) 由 KookManagerPlugin
  在自己的 __init__ 中安装, 并在拦截到生命周期事件时调用本适配器的
  :meth:`commit_lifecycle_event`.
"""

import asyncio
import time
from typing import Any

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.platform.astr_message_event import MessageSesion

from .kook_lifecycle_event import KookLifecycleEvent

ADAPTER_NAME = "kook_lifecycle"
ADAPTER_DESC = "KOOK 生命周期事件伴生适配器 (joined_guild / exited_guild 等, 需配合 kook_manager 插件)"


@register_platform_adapter(
    ADAPTER_NAME,
    ADAPTER_DESC,
    default_config_tmpl={
        "id": ADAPTER_NAME,
        "type": ADAPTER_NAME,
        "enable": False,
    },
    adapter_display_name="KOOK 生命周期事件 (伴生)",
)
class KookLifecycleAdapter(Platform):
    """KOOK 生命周期事件伴生适配器, 详见模块文档字符串"""

    _instance: "KookLifecycleAdapter | None" = None
    """模块级单例, 由插件通过 :meth:`get_instance` 取回"""

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.platform_settings = platform_settings
        self._stop_event = asyncio.Event()
        KookLifecycleAdapter._instance = self
        logger.info("[KookLifecycle] 伴生适配器实例已创建, 等待插件安装 KOOK 客户端 hook")

    @classmethod
    def get_instance(cls) -> "KookLifecycleAdapter | None":
        """返回当前已加载的伴生适配器实例, 若未启用则为 None"""
        return cls._instance

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name=ADAPTER_NAME,
            description=ADAPTER_DESC,
            id=self.config.get("id", ADAPTER_NAME),
        )

    async def run(self) -> None:
        """伴生适配器不主动连接任何服务, 只在事件队列被外部 commit 时工作"""
        try:
            await self._stop_event.wait()
        except asyncio.CancelledError:
            logger.info("[KookLifecycle] 适配器运行任务被取消")
            raise
        finally:
            logger.info("[KookLifecycle] 伴生适配器已停止")

    async def terminate(self) -> None:
        self._stop_event.set()
        if KookLifecycleAdapter._instance is self:
            KookLifecycleAdapter._instance = None

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ) -> None:
        """生命周期适配器不承担消息发送职责, 业务方请直接调用 KOOK HTTP API"""
        logger.warning(
            "[KookLifecycle] send_by_session 调用被忽略, 该适配器不负责消息发送, "
            "请使用官方 kook 适配器或直接调用 KOOK HTTP API",
        )
        await super().send_by_session(session, message_chain)

    def commit_lifecycle_event(
        self,
        raw_event_data: dict[str, Any],
        kook_bot_id: str = "",
    ) -> None:
        """把 KOOK 系统事件包装成 AstrBotMessage 推到 AstrBot 事件队列

        Args:
            raw_event_data: KOOK WebSocket 推送的事件原始结构, 必须是 dict, 形如::

                {
                    "type": 255,
                    "channel_type": "GROUP",
                    "target_id": "<guild_id>",
                    "extra": {
                        "type": "joined_guild",
                        "body": {"user_id": "...", "joined_at": 1700000000000},
                    },
                }

            kook_bot_id: 当前 KOOK Bot 的 user id, 写入 ``self_id`` 便于业务侧使用.
        """

        if not isinstance(raw_event_data, dict):
            logger.warning("[KookLifecycle] commit_lifecycle_event 收到非 dict 数据, 已忽略")
            return

        extra = raw_event_data.get("extra") or {}
        body = extra.get("body") or {}
        sub_type = str(extra.get("type", "")).strip()
        guild_id = str(raw_event_data.get("target_id", "")).strip()
        user_id = str(body.get("user_id", "")).strip()

        if not sub_type:
            logger.debug("[KookLifecycle] 事件缺少 extra.type, 已忽略")
            return

        abm = AstrBotMessage()
        abm.type = MessageType.OTHER_MESSAGE
        abm.self_id = kook_bot_id or ""
        abm.session_id = guild_id or sub_type
        abm.message_id = (
            f"kook_lifecycle:{sub_type}:{user_id or 'unknown'}:{int(time.time() * 1000)}"
        )
        abm.group_id = guild_id
        abm.sender = MessageMember(user_id=user_id, nickname="")
        abm.message = []
        abm.message_str = f"<kook_lifecycle:{sub_type}>"
        abm.raw_message = raw_event_data

        event = KookLifecycleEvent(
            message_str=abm.message_str,
            message_obj=abm,
            platform_meta=self.meta(),
            session_id=abm.session_id,
        )
        self.commit_event(event)
        logger.debug(
            f"[KookLifecycle] 已提交事件: sub_type={sub_type}, guild_id={guild_id}, user_id={user_id}",
        )
