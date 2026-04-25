"""
KOOK 生命周期事件子模块

通过伴生适配器 (kook_lifecycle) 把官方 KOOK 适配器忽略的成员加入/离开等系统事件
转换为 AstrBot 的 OTHER_MESSAGE 事件, 让插件可以用标准事件 API 进行处理.
"""

from .kook_lifecycle_adapter import KookLifecycleAdapter
from .kook_lifecycle_event import KookLifecycleEvent

__all__ = ["KookLifecycleAdapter", "KookLifecycleEvent"]
