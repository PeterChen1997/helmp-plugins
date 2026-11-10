<!-- One plugin per pull request, please. / 每个 PR 只提交一个插件。 -->

## Plugin / 插件

- **ID**: `com.example.my-plugin`
- **Version / 版本**: `1.0.0`
- **Type / 类型**: New plugin / 新增 — Update / 更新 <!-- keep one / 保留一个 -->

## What it does / 用途

<!-- One or two sentences. / 一两句话说明插件做什么。 -->

## Permissions / 权限

<!-- Paste the "Permissions" lines printed by `helmp plugins validate <dir>`. / 粘贴 `helmp plugins validate <目录>` 打印的权限。 -->

- 

## Files / 文件

<!-- Every file in plugins/<id>/ and what it is for. / 列出 plugins/<id>/ 下的每个文件及用途。 -->

- `plugin.json`
- `README.md`
- `icon.png`

## Reviewer checklist / 审核清单

<!-- For the maintainer. Contributors: leave these unchecked. / 维护者填写，提交者请勿勾选。 -->

- [ ] Permissions are reasonable and match what the plugin is for / 权限合理，且与插件用途相符
- [ ] Every host it contacts is expected / 访问的主机都在预期之内
- [ ] Scripts are not obfuscated, don't download and run remote code, and don't read or write sensitive paths outside the plugin folder / 脚本没有混淆、没有下载执行远程代码、没有读写插件目录以外的敏感路径
- [ ] Tested by following its README, and it works / 按 README 实测可用
- [ ] `license` is declared / 已声明 `license`
- [ ] Version is raised (updates only) / 版本号已提升（更新时）
