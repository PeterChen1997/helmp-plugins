# Lighter (灵感园丁)

Jot an idea down into [Lighter (灵感园丁)](https://blog.peterchen97.cn/lighter/) from Helmp. The gardener in the app picks it up from there.

## Commands

| Command | Keywords | What it does |
|---|---|---|
| Save to Lighter | `lg`, `lighter`, `灵感`, `灵感园丁`, `想法`, `idea` | Find it by keyword and press Tab to open its form, then `POST`s `{"content": "…"}` to `https://lighter-sync.fly.dev/v1/ideas` with your API Key |

Example: type `lg`, press Tab, write `a launcher plugin for my notes app`, and press Return. The idea shows up in the app on its next sync.

## Permissions

- Network access: `lighter-sync.fly.dev`

## Setup

1. In the Lighter app, open **Settings › API Key** and generate a key (it starts with `lk_` and is shown only once).
2. In Helmp, open **Settings › Plugins › Lighter** and paste it into **API Key**. It is stored in the macOS Keychain only.

The key can only add ideas: it cannot read, change or delete anything in your account. If it leaks, revoke it in the app; Helmp then shows "API Key 无效或已吊销".

---

## 简体中文

在 Helmp 里随手把一个想法记到[灵感园丁](https://blog.peterchen97.cn/lighter/)，园丁接着替你跟踪。

### 命令

| 命令 | 关键词 | 作用 |
|---|---|---|
| 记到灵感园丁 | `lg`、`lighter`、`灵感`、`灵感园丁`、`想法`、`idea` | 用关键词找到后按 Tab 打开表单，带着你的 API Key 把 `{"content": "…"}` POST 到 `https://lighter-sync.fly.dev/v1/ideas` |

例：输入 `lg`，按 Tab，写下 `给记事 App 做个启动器插件`，回车。App 下次同步就能看到。

### 权限

- 访问网络：`lighter-sync.fly.dev`

### 配置

1. 在灵感园丁 App「设置 › API Key」里生成一个 Key（`lk_` 开头，只显示一次）。
2. 在 Helmp「设置 › 插件 › 灵感园丁」里粘贴到「API Key」。它只存在 macOS 钥匙串里。

这个 Key 只能新建想法，不能读、改、删账号里的任何内容。泄露了就在 App 里吊销，之后 Helmp 会提示「API Key 无效或已吊销」。
