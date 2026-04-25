"""
KOOK 生命周期事件

伴生适配器只负责把 KOOK 系统事件 (joined_guild/exited_guild 等) 转换为
AstrBot 的 AstrMessageEvent, 不处理消息发送回执.
"""

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata


class KookLifecycleEvent(AstrMessageEvent):
    """KOOK 生命周期事件 (成员加入/离开等)

    业务侧通过 ``event.message_obj.raw_message`` 拿到原始 KOOK 系统事件 dict,
    例如:

    .. code-block:: python

        {
            "type": 255,
            "channel_type": "GROUP",
            "target_id": "<guild_id>",
            "extra": {
                "type": "joined_guild",
                "body": {"user_id": "<user_id>", "joined_at": 1700000000000},
            },
        }

    该事件不支持通过 ``event.send`` 回执, 业务请自行调用 KOOK HTTP API
    (例如插件内的 ``_send_kook_channel_message``) 主动向目标频道发送消息.
    """

    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)

    async def send(self, message: MessageChain) -> None:
        """生命周期事件不支持直接回执, 显式拦截避免上层误用"""
        raise NotImplementedError(
            "KookLifecycleEvent 不支持 event.send, 请直接调用 KOOK HTTP API 主动发送消息"
        )
