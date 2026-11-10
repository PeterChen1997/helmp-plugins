# flomo

Save a memo to [flomo](https://flomoapp.com) through your personal webhook (a flomo PRO feature). `#tags` in the text become flomo tags.

> Helmp already ships this plugin. This folder is its source and public version: use it as a reference for your own plugins.

## Commands

| Command | Keywords | What it does |
|---|---|---|
| Save to flomo | `flomo`, `浮墨`, `memo`, `记一笔` | Opens a form with the text you typed after the keyword, then `POST`s `{"content": "…"}` to your webhook |

Example: type `flomo read a great book #reading` and press Return.

## Permissions

- Network access: `flomoapp.com` (the URL comes from the `webhook` preference, and Helmp only lets it point to `flomoapp.com`)

## Setup

1. In flomo on the web, open **Account › API** ([flomoapp.com/mine?source=incoming_webhook](https://flomoapp.com/mine?source=incoming_webhook)) and copy the webhook URL.
2. In Helmp, open **Settings › Plugins › flomo** and paste it into **Webhook URL**. It is stored in the macOS Keychain only.

---

## 简体中文

用 flomo 的「记录 API」（会员功能）把一段文字记到 [flomo](https://flomoapp.com)，正文里的 `#标签` 就是 flomo 标签。

> Helmp 已自带此插件，这里是它的源码与公开版本，可以作为写插件的参考。

### 命令

| 命令 | 关键词 | 作用 |
|---|---|---|
| 记到 flomo | `flomo`、`浮墨`、`memo`、`记一笔` | 打开表单（预填关键词后面输入的文字），然后把 `{"content": "…"}` POST 到你的记录 API |

例：输入 `flomo 读完一本好书 #阅读` 后回车。

### 权限

- 访问网络：`flomoapp.com`（地址来自偏好设置 `webhook`，Helmp 只允许它指向 `flomoapp.com`）

### 配置

1. 在 flomo 网页版打开「账号详情 › 记录 API」（[flomoapp.com/mine?source=incoming_webhook](https://flomoapp.com/mine?source=incoming_webhook)），复制地址。
2. 在 Helmp「设置 › 插件 › flomo」里粘贴到「记录 API 地址」。它只存在 macOS 钥匙串里。
