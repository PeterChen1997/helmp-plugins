# Helmp Plugins

The registry behind the **Helmp Plugin Center**. [Helmp](https://github.com/PeterChen1997/helmp) is a macOS launcher; this repository holds the community plugins you can browse and install from inside Helmp or on the landing page: <https://blog.peterchen97.cn/helmp/plugins/>.

[简体中文](#简体中文)

## What's here

```
plugins/<plugin id>/     one folder per plugin
  plugin.json            the manifest (format: Helmp's docs/plugins.md)
  README.md              what it does, commands, permissions, setup
  icon.png               optional, shown in the Plugin Center
  ...                    scripts, if any
index.json               generated: do not edit by hand
scripts/build-index.py   validates every plugin and builds index.json
```

`index.json` lists every plugin with its version, permissions and the SHA-256 of each file. Helmp downloads the files and checks them against it. It is rebuilt automatically when `main` changes; pull requests don't need to (and shouldn't) touch it.

The three plugins in this repository today (flomo, Quick Search, Obsidian) also ship inside Helmp; their folders here are the source and public version, and a good starting point for your own.

## Installing a plugin

Open **Settings › Plugins › Plugin Center** in Helmp, or the [landing page](https://blog.peterchen97.cn/helmp/plugins/). Helmp shows a plugin's permissions (network hosts, links it opens, scripts it runs…) before you turn it on.

## Submitting a plugin

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: `helmp plugins validate <dir>`, then `helmp plugins submit <dir>`, which opens a pull request from your own GitHub account. Every pull request is reviewed by hand before it's merged.

## License

The registry itself (scripts, docs, workflows) is [MIT](LICENSE). **Each plugin declares its own license in the `license` field of its `plugin.json`**; that license applies to the plugin's folder.

---

## 简体中文

这是 **Helmp 插件中心**的注册表。[Helmp](https://github.com/PeterChen1997/helmp) 是一个 macOS 启动器；这个仓库存放可以在 Helmp 里或落地页上浏览、安装的社区插件：<https://blog.peterchen97.cn/helmp/plugins/>。

### 目录结构

```
plugins/<插件 id>/        每个插件一个文件夹
  plugin.json            清单（格式见 Helmp 的 docs/plugins.zh-CN.md）
  README.md              用途、命令、权限、配置方法
  icon.png               可选，插件中心展示用
  ...                    脚本（如果有）
index.json               自动生成，不要手改
scripts/build-index.py   校验全部插件并生成 index.json
```

`index.json` 列出每个插件的版本、权限和每个文件的 SHA-256，Helmp 下载文件后按它校验。`main` 有变化时会自动重建；PR 不需要（也不应该）改它。

目前仓库里的三个插件（flomo、快捷搜索、Obsidian）Helmp 也自带；这里是它们的源码与公开版本，适合作为写插件的起点。

### 安装插件

在 Helmp 里打开「设置 › 插件 › 插件中心」，或访问[落地页](https://blog.peterchen97.cn/helmp/plugins/)。启用前 Helmp 会列出插件的权限（访问哪些主机、打开哪些链接、是否运行脚本……）让你确认。

### 提交插件

见 [CONTRIBUTING.md](CONTRIBUTING.md#简体中文)。简单说：先 `helmp plugins validate <目录>`，再 `helmp plugins submit <目录>`，它会用你自己的 GitHub 账号开 PR。每个 PR 都由维护者人工审核后才合并。

### 协议

注册表本身（脚本、文档、工作流）使用 [MIT](LICENSE) 协议。**每个插件在自己 `plugin.json` 的 `license` 字段声明协议**，该协议适用于插件文件夹里的内容。
