# KOOK 群管理插件

AstrBot 插件 - KOOK 平台群管理工具

## 功能

- 关键词自动回复 (支持引用回复)
- 支持正则表达式匹配
- 多种匹配模式: 包含/完全匹配/开头/结尾
- 管理员主动发送 KMarkdown 到任意 KOOK 频道
- 管理员主动发送 Card 消息到任意 KOOK 频道
- 支持多行 KMarkdown 和多行 Card JSON 输入
- 支持从文件发送 Card JSON
- 更多功能开发中...

## 安装

在 AstrBot WebUI 中, 选择 "从链接安装", 输入本仓库地址。

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

## 指令

以下指令默认仅管理员可用.

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

## 说明

- 该功能直接调用 KOOK `message/create` 接口发送频道消息
- KMarkdown 使用消息类型 `9`
- CardMessage 使用消息类型 `10`
- `kooksendcardfile` 支持相对插件目录路径和绝对路径
- 若发送失败, 请先检查 Bot 是否在目标频道所在服务器内, 且具备发言权限
