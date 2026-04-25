# KOOK 群管理插件

AstrBot 插件 - KOOK 平台群管理工具

## 功能

- 关键词自动回复 (支持引用回复)
- 支持正则表达式匹配
- 多种匹配模式: 包含/完全匹配/开头/结尾
- 管理员主动发送 KMarkdown 到任意 KOOK 频道
- 管理员主动发送 Card 消息到任意 KOOK 频道
- 支持多行 KMarkdown 和多行 Card JSON 输入
- 支持从文件发送 Card 消息
- 支持使用 KOOK 角色白名单进行指令权限判定
- 新成员加入欢迎卡片 (基于 `kook_lifecycle` 伴生适配器)
- 成员离开告别消息 (实验功能, 默认关闭)
- 更多功能开发中...

## 安装

在 AstrBot WebUI 中, 选择 "从链接安装", 输入本仓库地址。

## 更新

AstrBot 通过比较远程仓库 `metadata.yaml` 中的 `version` 字段判断是否有新版本.
若 WebUI 提示 "未检测到新版本":

1. 首先确认远程仓库 (`metadata.yaml.repo` 字段指向的 GitHub 仓库) 已经推送了
   最新提交, 且其 `metadata.yaml.version` 已经升到本地预期版本
2. 在 AstrBot 后台「插件」-> 找到本插件 -> 选择 `更新`. 若仍提示无新版本, 可点击
   `强制更新` 直接拉取远程仓库最新代码覆盖安装
3. 更新后请在「插件」中点击 `重载插件` 让新代码生效, 否则 AstrBot 仍按旧代码运行

## 配置

### 关键词规则格式

每行一条规则, 格式为: `关键词 => 回复内容`

```
# 这是注释
你好 => 你好呀! 有什么可以帮助你的?
帮助 => 发送 /help 查看帮助信息
服务器地址 => 服务器连接地址: cfx.re/join/xxx
r:签到|打卡 => 签到成功! (正则匹配示例)
```

### 特殊语法

- `#` 开头的行为注释
- `r:` 开头表示使用正则表达式
- `\n` 在回复内容中表示换行

### 匹配模式说明

| 模式 | 说明 |
|------|------|
| contains | 消息包含关键词即匹配 |
| exact | 消息完全等于关键词才匹配 |
| startswith | 消息以关键词开头才匹配 |
| endswith | 消息以关键词结尾才匹配 |

### 主动发送配置

- `kook_bot_token`: KOOK Bot Token. 用于主动调用 KOOK HTTP API 发送消息
- `kook_api_base`: KOOK API 根地址. 默认值为 `https://www.kookapp.cn/api/v3`
- `allowed_role_ids`: 允许执行管理指令的 KOOK 角色 ID 列表. 支持逗号分隔或每行一个

### 权限模型

- 满足以下任一条件即可使用发送类指令
- 已被配置为 AstrBot 管理员
- 在当前 KOOK 服务器中拥有 `allowed_role_ids` 里的任一角色

示例:

```text
702
703
```

或:

```text
702,703,888
```

## 指令

以下指令默认仅 AstrBot 管理员或命中 KOOK 角色白名单的用户可用.

### 发送 KMarkdown

```text
/kooksendmd <channel_id> <content>
```

示例:

```text
/kooksendmd 123456789 **公告**\n这是一个 KMarkdown 消息
```

也支持直接输入多行内容:

```text
/kooksendmd 123456789 **公告**
这是第二行
这是第三行
```

### 发送 Card 消息

```text
/kooksendcard <channel_id> <card_json>
```

示例:

```text
/kooksendcard 123456789 [{"type":"card","theme":"primary","size":"lg","modules":[{"type":"section","text":{"type":"kmarkdown","content":"**Hello** from AstrBot"}}]}]
```

也支持多行 JSON:

```text
/kooksendcard 123456789 [
  {
    "type": "card",
    "theme": "primary",
    "modules": [
      {
        "type": "section",
        "text": {
          "type": "kmarkdown",
          "content": "**Hello** from AstrBot"
        }
      }
    ]
  }
]
```

### 从文件发送 Card 消息

```text
/kooksendcardfile <channel_id> <file_path>
```

示例:

```text
/kooksendcardfile 123456789 cards/welcome.json
/kooksendcardfile 123456789 "C:/kook/cards/announce.json"
```

## 新成员欢迎 / 告别

AstrBot 官方 KOOK 适配器目前只把 KMarkdown / Card 类型的聊天消息推送给插件,
对 `joined_guild` / `exited_guild` 这类 SYSTEM 类型事件会直接忽略.
本插件通过随包发布的 `kook_lifecycle` 伴生适配器把这些事件转换为 AstrBot 标准
`OTHER_MESSAGE`, 让插件能够监听并触发欢迎卡片或告别消息.

### 启用步骤

1. 确保 `kook` 平台适配器已在 AstrBot 后台启用并正常运行 (照常配置 Bot Token)
2. 在 AstrBot 后台 -> `机器人` -> `+ 创建机器人`, 平台选择 `kook_lifecycle`,
   勾选 `启用` 即可保存. 该适配器**不需要任何 Token 或 API 配置**, 它不会建立独立
   WebSocket, 仅作为事件入口与 `kook` 适配器协同工作
3. 重新加载 `kook_manager` 插件 (或重启 AstrBot)
4. 进入 `kook_manager` 插件配置, 打开 `enable_welcome` 并填写 `welcome_channel_id`
5. 让一个测试账号加入服务器, 验证欢迎卡片是否在指定频道发出

如未同时启用 `kook` 与 `kook_lifecycle`, 插件会在日志中给出告警, 欢迎/告别功能不会触发.

### 配置项

| key | 类型 | 默认 | 说明 |
|-----|------|------|------|
| `enable_welcome` | bool | `false` | 启用新成员加入欢迎 |
| `welcome_channel_id` | string | `""` | 欢迎卡片发送频道 ID, 必填 |
| `welcome_card_path` | string | `lifecycle/cards/welcome.json` | 欢迎卡片模板路径, 支持相对插件目录或绝对路径 |
| `welcome_text_fallback` | text | (短文本) | 模板加载失败时的兜底 KMarkdown |
| `enable_farewell` | bool | `false` | 启用成员离开告别 (实验) |
| `farewell_channel_id` | string | `""` | 告别消息发送频道 ID |
| `farewell_text` | text | (短文本) | 告别消息模板, 仅在 `enable_farewell` 为 `true` 时生效 |

### 卡片模板占位符

模板内容会先做最简字符串替换再做 JSON 解析, 当前支持以下占位符:

- `{user_id}`: 新成员 KOOK 用户 ID
- `{user_name}`: 新成员名称, 当前与 `user_id` 一致 (KOOK joined_guild 事件原生只携带 user_id, 后续可扩展为反查昵称)
- `{guild_id}`: 服务器 ID

可以参照默认模板 `lifecycle/cards/welcome.json` 自行修改, 或在配置中改用其他文件.

### 自定义欢迎卡片示例

`lifecycle/cards/welcome.json` 默认是一张包含标题, 正文 (含 `(met){user_id}(met)` 提及),
以及底部提示的简洁卡片. 可以通过修改这个文件直接换文案/换主题/加按钮, 修改后无需重启
插件 (下一次新成员加入时自动重新加载模板).

## 说明

- 该功能直接调用 KOOK `message/create` 接口发送频道消息
- 角色权限检查会调用 KOOK `guild/user-list` 接口
- KMarkdown 使用消息类型 `9`
- CardMessage 使用消息类型 `10`
- `kooksendcardfile` 支持相对插件目录路径和绝对路径
- KOOK 角色判权依赖当前消息能识别 `guild_id`, 请尽量在服务器频道中使用这些指令
- 若发送失败, 请先检查 Bot 是否在目标频道所在服务器内, 且具备发言权限
- 欢迎/告别功能依赖 hook 官方 `KookClient.event_callback`, 是非侵入式的合作机制,
  不会建立第二条 KOOK WebSocket 连接, 也不会影响关键词回复和主动发送功能
