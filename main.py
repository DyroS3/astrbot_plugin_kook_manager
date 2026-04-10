"""
KOOK 群管理插件
提供 KOOK 平台的群管理功能, 包括关键词自动回复等
"""

import re
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Plain, Reply


@register("kook_manager", "YWY", "KOOK 群管理工具", "1.1.0")
class KookManagerPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context

    def _get_config(self, key: str, default=None):
        """获取配置项"""
        return self.context.get_config(key, default)

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

            for rule in rules:
                if self._match_keyword(message, rule):
                    response_text = rule["response"]
                    response_text = response_text.replace("\\n", "\n")

                    logger.info(f"[KookManager] 关键词匹配: '{rule['keyword']}' -> 回复")

                    if enable_reply_quote:
                        message_id = event.message_obj.message_id
                        yield event.chain_result([
                            Reply(id=message_id),
                            Plain(text=response_text)
                        ])
                    else:
                        yield event.plain_result(response_text)

                    only_first = self._get_config("only_first_match", True)
                    if only_first:
                        break

        except Exception as e:
            logger.error(f"[KookManager] 处理消息异常: {e}")
