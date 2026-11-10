# Contributing a plugin

[简体中文](#简体中文)

Thanks for sharing a plugin! The manifest format is documented in Helmp's [docs/plugins.md](https://github.com/PeterChen1997/helmp/blob/main/docs/plugins.md).

## Before you submit

Your plugin folder needs:

- `plugin.json` with `id` equal to the folder name (reverse-DNS such as `com.yourname.my-plugin`, not `dev.helmp.*`), an `x.y.z` `version`, and a `license` (for example `"MIT"`).
- `README.md` that explains what the plugin does, its commands and keywords, its permissions and how to set it up. English, ideally with a Chinese section too.
- Optionally `icon.png` (256×256 recommended), shown in the Plugin Center.

## Recommended: let Helmp submit it

1. **With an AI agent.** In Claude Code or Codex, connect Helmp's MCP server and ask the agent to validate and submit your plugin folder. It runs the same steps as below.
2. **From the terminal.**

   ```bash
   helmp plugins validate path/to/com.yourname.my-plugin
   helmp plugins submit path/to/com.yourname.my-plugin
   ```

   `submit` first explains what it will do (fork this repository with your own `gh` account, copy the folder to `plugins/<id>/`, open a pull request) and does nothing until you run it again with `--yes`. You need the [GitHub CLI](https://cli.github.com) signed in (`gh auth login`).

## Manual submission

1. Fork `PeterChen1997/helmp-plugins` and create a branch.
2. Copy your folder to `plugins/<id>/`. Don't edit `index.json`.
3. Run the checks below.
4. Open a pull request and fill in the template (one plugin per pull request).

To update a plugin, change its files **and raise `version`**; CI rejects changes without a version bump.

## Review

CI validates the plugin, and lists anything that needs a human look (scripts, executable files, `mcpServers`, clipboard reading, keystrokes) in the job summary. The maintainer, @PeterChen1997, then reviews **every** pull request by hand: permissions, hosts, every line of every script, and a real run following your README. Expect questions; plugins that run scripts take longer.

## Running the checks locally

Python 3.10 or newer, standard library only:

```bash
python3 -I scripts/build-index.py --check                         # validate every plugin
python3 -I scripts/build-index.py --check --base-ref origin/main  # also require version bumps
python3 -I -m unittest discover -s scripts -p 'test_*.py'         # tests for the validator itself
```

`--helmp <path to helmp>` additionally runs `helmp plugins validate --json` on each plugin and fails if Helmp's derived permissions differ from the script's.

## Limits

- At most **64 files** per plugin, **512 KiB** per file, **2 MiB** per plugin.
- Text files must be UTF-8 without NUL bytes. The only binary files allowed are `.png` images.
- No symbolic links, no hidden files or folders (names starting with `.`, including `.DS_Store`), no backslashes in file names.
- Scripts must be readable source. No obfuscation, no downloading and running remote code, no reading or writing sensitive paths outside the plugin folder.

---

## 简体中文

感谢分享插件！清单格式见 Helmp 的 [docs/plugins.zh-CN.md](https://github.com/PeterChen1997/helmp/blob/main/docs/plugins.zh-CN.md)。

### 提交前

插件文件夹里需要：

- `plugin.json`：`id` 与文件夹名相同（反向域名，如 `com.yourname.my-plugin`，不要用 `dev.helmp.*`），`version` 为 `x.y.z`，并声明 `license`（如 `"MIT"`）。
- `README.md`：说明用途、命令和关键词、权限、配置方法。英文为主，最好附中文段落。
- 可选 `icon.png`（建议 256×256），插件中心展示用。

### 推荐：让 Helmp 帮你提交

1. **用 AI agent。** 在 Claude Code 或 Codex 里接入 Helmp 的 MCP，让 agent 校验并提交你的插件文件夹，步骤与下面相同。
2. **用终端。**

   ```bash
   helmp plugins validate path/to/com.yourname.my-plugin
   helmp plugins submit path/to/com.yourname.my-plugin
   ```

   `submit` 会先说明它要做什么（用你自己的 `gh` 账号 fork 本仓库、把文件夹复制到 `plugins/<id>/`、开 PR），加上 `--yes` 再运行一次才会真正执行。需要先装好并登录 [GitHub CLI](https://cli.github.com)（`gh auth login`）。

### 手动提交

1. fork `PeterChen1997/helmp-plugins` 并新建分支。
2. 把插件文件夹复制到 `plugins/<id>/`。不要改 `index.json`。
3. 按下文在本地跑校验。
4. 开 PR，填写模板（每个 PR 一个插件）。

更新插件时改文件**并提升 `version`**；版本号没变的改动 CI 会拒绝。

### 审核流程

CI 先校验插件，并把需要人工审核的项（脚本、可执行文件、`mcpServers`、读剪贴板、模拟按键）写进任务摘要。之后维护者 @PeterChen1997 会人工审核**每一个** PR：权限、访问的主机、每个脚本的每一行，并按 README 实际跑一遍。可能会有提问；带脚本的插件审核时间更长。

### 本地校验

需要 Python 3.10 及以上，只用标准库：

```bash
python3 -I scripts/build-index.py --check                         # 校验全部插件
python3 -I scripts/build-index.py --check --base-ref origin/main  # 另外检查版本号是否提升
python3 -I -m unittest discover -s scripts -p 'test_*.py'         # 校验脚本自身的测试
```

加 `--helmp <helmp 可执行文件>` 会再对每个插件运行 `helmp plugins validate --json`，Helmp 推导出的权限与脚本不一致时失败。

### 限制

- 每个插件最多 **64 个文件**，单文件 **512 KiB**，整个插件 **2 MiB**。
- 文本文件必须是 UTF-8，不含 NUL 字节；唯一允许的二进制文件是 `.png` 图片。
- 不允许符号链接、隐藏文件或文件夹（以 `.` 开头，包括 `.DS_Store`），文件名不能含反斜杠。
- 脚本必须是可读的源码：不得混淆、不得下载并执行远程代码、不得读写插件目录以外的敏感路径。
