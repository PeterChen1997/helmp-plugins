# Obsidian

Capture a new note into an [Obsidian](https://obsidian.md) vault with the [`obsidian://new`](https://help.obsidian.md/Extending+Obsidian/Obsidian+URI) URL scheme. Nothing leaves your Mac.

> Helmp already ships this plugin. This folder is its source and public version: use it as a reference for your own plugins.

## Commands

| Command | Keywords | What it does |
|---|---|---|
| Quick Capture to Obsidian | `obsidian`, `ob`, `quick capture`, `速记` | Find it by keyword and press Tab to open its form (title defaults to the current date and time), then opens `obsidian://new?vault=…&name=…&content=…` |

Example: type `ob`, press Tab, write `call the dentist`, and press Return.

## Permissions

- Open `obsidian://` links (launches the matching app)

## Setup

In Helmp, open **Settings › Plugins › Obsidian** and fill in **Vault name**: the vault's name as shown in Obsidian's vault switcher.

---

## 简体中文

用 [`obsidian://new`](https://help.obsidian.md/Extending+Obsidian/Obsidian+URI) 链接在 [Obsidian](https://obsidian.md) 仓库里新建一条笔记，内容不经过网络。

> Helmp 已自带此插件，这里是它的源码与公开版本，可以作为写插件的参考。

### 命令

| 命令 | 关键词 | 作用 |
|---|---|---|
| Obsidian 快速记录 | `obsidian`、`ob`、`quick capture`、`速记` | 用关键词找到后按 Tab 打开表单（标题默认是当前日期时间），然后打开 `obsidian://new?vault=…&name=…&content=…` |

例：输入 `ob`，按 Tab，写下 `记得约牙医`，回车。

### 权限

- 打开 `obsidian://` 链接（会启动对应的 App）

### 配置

在 Helmp「设置 › 插件 › Obsidian」里填「仓库名」：Obsidian 仓库切换器里显示的名字。
