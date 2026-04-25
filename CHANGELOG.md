# 更新日志

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/),
版本号遵循 [SemVer 2.0.0](https://semver.org/lang/zh-CN/).

## [1.7.2] - 2026-04-26

### 新增

- 欢迎卡片模板升级为图文混排版式: 标题 + 用户头像 (右侧圆形) + 服务器欢迎语 +
  双按钮 (申请白名单 / 连接服务器) + 频道导航 context + 底部小贴士 context
- 加入服务器后异步反查 KOOK `/user/view` 接口拿到真实头像 URL 与昵称, 反查失败
  时退化为仅显示 user_id (不阻断卡片渲染)
- 新增 4 个配置项:
  - `welcome_server_name`: 卡片中突出显示的服务器名 (默认 `[FiveM] 夜未央`)
  - `welcome_apply_whitelist_url`: 申请白名单按钮跳转 URL
  - `welcome_connect_server_url`: 连接服务器按钮跳转 URL (一般填 cfx.re/join 链接)
  - `welcome_navigation_text`: 底部导航行 KMarkdown 文本, 可改为
    `(chn)channel_id(chn)` 形成可点击频道引用
- 新增占位符: `{user_avatar}` (头像 URL), `{server_name}`,
  `{apply_whitelist_url}`, `{connect_server_url}`, `{navigation_text}`

### 变更

- `_apply_placeholders` 升级为支持 `json_safe` 模式, 对卡片 JSON 模板的占位符
  值做 `json.dumps` 转义, 避免昵称/URL 中的双引号、反斜杠、控制字符破坏 JSON 结构
- 兜底 KMarkdown 文本与告别消息保持原行为, 不做 JSON 转义

## [1.7.1] - 2026-04-26

### 修复

- 修复 `kook_lifecycle` 伴生适配器在 AstrBot WebUI「创建机器人」下拉列表中
  不显示的问题. 根因是装饰器原本传入空 dict 作为 `default_config_tmpl`,
  AstrBot dashboard 的 `_get_astrbot_config` 通过 `if platform.default_config_tmpl:`
  过滤, 空 dict 被判为 False 从而跳过注入, 现改为显式提供 `id` / `type` /
  `enable` 三个字段确保下拉列表能列出该适配器
- 同步新增 `adapter_display_name="KOOK 生命周期事件 (伴生)"`, 让用户在
  WebUI 看到中文友好名称

## [1.7.0] - 2026-04-25

### 新增

- 随包发布伴生平台适配器 `kook_lifecycle`, 用于把官方 KOOK 适配器忽略的
  `joined_guild` / `exited_guild` 等 SYSTEM 类型事件转换为 AstrBot 标准
  `OTHER_MESSAGE` 事件
- 新成员加入欢迎卡片功能, 支持自定义 KOOK Card 模板
  (`lifecycle/cards/welcome.json`)
- 成员离开告别消息功能 (实验, 默认关闭)
- 新增配置项: `enable_welcome`, `welcome_channel_id`, `welcome_card_path`,
  `welcome_text_fallback`, `enable_farewell`, `farewell_channel_id`,
  `farewell_text`
- 卡片 / 文本模板支持占位符 `{user_id}`, `{user_name}`, `{guild_id}`

### 变更

- `metadata.yaml.astrbot_version` 改为 PEP 440 严格格式 (`>=4.20.0`)
- 文档与 README 增加 "新成员欢迎 / 告别" 章节, 详细说明伴生适配器启用步骤
- `display_name` 与说明更新, 反映欢迎/告别能力

### 兼容性

- 保持向下兼容: 已有的关键词回复 / `kooksendmd` / `kooksendcard` /
  `kooksendcardfile` / 角色权限判定均不受影响
- 不开启伴生适配器时, 插件行为与 1.6.0 完全一致, 不会因新增代码导致额外开销
- 不引入新的 Python 依赖, `requirements.txt` 仍仅包含 `aiohttp`

## [1.6.0] - 2026 之前

- 关键词自动回复
- 主动发送 KMarkdown / Card / 卡片文件到任意 KOOK 频道
- 基于 KOOK 角色 ID 的指令权限判定
