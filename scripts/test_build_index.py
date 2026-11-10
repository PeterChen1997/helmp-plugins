"""scripts/build-index.py 的测试：在临时目录里造一个注册表，按 CI 的方式运行脚本。

运行：python3 -I -m unittest discover -s scripts -p 'test_*.py'
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build-index.py")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

FLOMO_LIKE = {
    "schemaVersion": 1,
    "id": "com.example.memo",
    "name": {"en": "Memo", "zh-Hans": "备忘"},
    "description": "Save a memo.",
    "version": "1.0.0",
    "author": "Ada",
    "license": "MIT",
    "icon": "feather",
    "tint": "green",
    "preferences": [
        {"id": "hook", "type": "secret", "title": "Webhook", "allowedHosts": ["memo.example.com"]}
    ],
    "commands": [
        {
            "id": "post",
            "title": "Post",
            "keywords": ["memo", "note"],
            "form": [{"id": "text", "type": "textarea", "label": "Text", "default": "{{query}}"}],
            "action": {"type": "http", "method": "POST", "url": "{{pref.hook}}", "json": {"content": "{{form.text}}"}},
        },
        {
            "id": "open",
            "title": "Open",
            "keywords": ["note", "obs"],
            "action": {"type": "open", "url": "obsidian://new?content={{query|url}}"},
        },
        {
            "id": "web",
            "title": "Web",
            "action": {"type": "open", "url": "https://memo.example.com/?q={{query|url}}"},
        },
    ],
}


def git(cwd, *args):
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="Test",
        GIT_AUTHOR_EMAIL="test@example.com",
        GIT_COMMITTER_NAME="Test",
        GIT_COMMITTER_EMAIL="test@example.com",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
    )
    subprocess.run(["git", "-C", cwd] + list(args), check=True, capture_output=True, env=env)


class Registry(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="helmp-registry-")
        self.addCleanup(shutil.rmtree, self.root)
        os.makedirs(os.path.join(self.root, "plugins"))

    # ---------------------------------------------------------- 工具

    def plugin(self, manifest=None, files=None, folder=None):
        manifest = json.loads(json.dumps(manifest or FLOMO_LIKE))
        folder = folder or manifest["id"]
        directory = os.path.join(self.root, "plugins", folder)
        os.makedirs(directory, exist_ok=True)
        self.write(folder, "plugin.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        self.write(folder, "README.md", "# %s\n" % folder)
        for path, content in (files or {}).items():
            self.write(folder, path, content)
        return directory

    def write(self, folder, path, content, mode=None):
        full = os.path.join(self.root, "plugins", folder, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        data = content.encode("utf-8") if isinstance(content, str) else content
        with open(full, "wb") as f:
            f.write(data)
        if mode is not None:
            os.chmod(full, mode)
        return full

    def run_script(self, *args):
        result = subprocess.run(
            [sys.executable, "-I", SCRIPT, "--root", self.root] + list(args),
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout + result.stderr

    def assert_fails(self, needle, *args):
        code, out = self.run_script("--check", *args)
        self.assertEqual(code, 1, out)
        self.assertIn(needle, out)

    def index(self):
        with open(os.path.join(self.root, "index.json"), encoding="utf-8") as f:
            return json.load(f)

    def commit_all(self, message="c"):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", message)

    def init_git(self):
        git(self.root, "init", "-q", "-b", "main")
        self.commit_all("base")

    # ---------------------------------------------------------- 正常路径

    def test_valid_plugin_builds_the_index_helmp_expects(self):
        # Helmp 按 index.json 下载文件并逐个核对 sha256/size，权限文案直接展示给用户；任何一项算错都会让安装失败或误导用户。
        self.plugin(files={"icon.png": PNG})
        script = self.write("com.example.memo", "bin/run.sh", "#!/bin/sh\necho hi\n", mode=0o755)
        code, out = self.run_script()
        self.assertEqual(code, 0, out)
        index = self.index()
        self.assertEqual(index["schema"], 1)
        self.assertIsNone(index["commit"])  # 不是 git 仓库：没有 HEAD
        self.assertRegex(index["generated_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        entry = index["plugins"][0]
        self.assertEqual(entry["id"], "com.example.memo")
        self.assertEqual(entry["name"], {"en": "Memo", "zh-Hans": "备忘"})
        self.assertEqual(entry["description"], {"en": "Save a memo.", "zh-Hans": "Save a memo."})
        self.assertIsNone(entry["homepage"])
        self.assertEqual(entry["license"], "MIT")
        self.assertEqual(entry["icon"], "icon.png")
        self.assertEqual(entry["keywords"], ["memo", "note", "obs"])
        self.assertEqual(entry["commands"], 3)
        self.assertEqual(entry["permissions"], ["network:memo.example.com", "open:https", "open:obsidian"])
        self.assertEqual(
            entry["permissions_text"],
            {
                "en": [
                    "Network access: memo.example.com (URL comes from preference hook)",
                    "Open web pages in your browser",
                    "Open obsidian:// links (launches the matching app)",
                ],
                "zh-Hans": [
                    "访问网络：memo.example.com（地址来自偏好设置 hook）",
                    "在浏览器中打开网页",
                    "打开 obsidian:// 链接（会启动对应的 App）",
                ],
            },
        )
        self.assertEqual(entry["source"], "https://github.com/PeterChen1997/helmp-plugins/tree/main/plugins/com.example.memo")
        self.assertEqual([f["path"] for f in entry["files"]], ["README.md", "bin/run.sh", "icon.png", "plugin.json"])
        with open(script, "rb") as f:
            data = f.read()
        run_sh = entry["files"][1]
        self.assertEqual(run_sh["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(run_sh["size"], len(data))
        self.assertTrue(run_sh["executable"])
        self.assertFalse(entry["files"][0]["executable"])
        # 可执行文件即使没被命令引用，也要交给人看。
        self.assertIn("executable file: bin/run.sh", entry["review"])

    def test_permission_keys_and_descriptions_mirror_helmp(self):
        # 用户在插件中心看到的权限必须和 Helmp 启用时让他确认的一模一样，否则「确认过的权限」就对不上。
        manifest = json.loads(json.dumps(FLOMO_LIKE))
        manifest["permissions"] = ["clipboard.read"]
        manifest["commands"] = [
            {"id": "a", "title": "A", "action": {"type": "paste", "text": "{{clipboard|upper}}"}},
            {"id": "b", "title": "B", "list": {"script": {"path": "list.sh"}}},
            {"id": "c", "title": "C", "action": {"type": "open", "url": "obsidian://x"}},
            {"id": "d", "title": "D", "action": {"type": "open", "url": "things://x"}},
        ]
        self.plugin(manifest, files={"list.sh": "#!/bin/sh\n"})
        code, out = self.run_script()
        self.assertEqual(code, 0, out)
        entry = self.index()["plugins"][0]
        self.assertEqual(
            entry["permissions"],
            ["clipboard:read", "clipboard:write", "exec", "keystrokes", "open:*", "open:obsidian", "open:things"],
        )
        self.assertEqual(
            entry["permissions_text"]["zh-Hans"],
            [
                "打开 obsidian://、things:// 链接（会启动对应的 App）",
                "打开任意链接或文件",
                "读取剪贴板",
                "写入剪贴板",
                "向前台应用发送 ⌘V（需要辅助功能权限）",
                "运行插件目录里的脚本（以你的用户身份，不受沙盒限制）",
            ],
        )
        self.assertEqual(
            entry["permissions_text"]["en"][0], "Open obsidian://, things:// links (launches the matching app)"
        )

    def test_scripts_are_listed_for_human_review(self):
        # 脚本以用户身份、不受沙盒运行，机器校验看不出它做了什么，必须让维护者逐行读过。
        manifest = json.loads(json.dumps(FLOMO_LIKE))
        manifest["commands"].append(
            {"id": "run", "title": "Run", "action": {"type": "script", "path": "bin/run.sh"}}
        )
        self.plugin(manifest, files={"bin/run.sh": "#!/bin/sh\necho hi\n"})
        code, out = self.run_script("--check")
        self.assertEqual(code, 0, out)
        self.assertIn("Needs human review", out)
        self.assertIn("commands[3] runs a script: bin/run.sh (exec)", out)

    def test_unchanged_content_does_not_rewrite_index(self):
        # index.yml 只在 index.json 变化时提交；如果每次都刷新时间戳，main 上会出现无意义的机器人提交。
        self.plugin()
        self.assertEqual(self.run_script()[0], 0)
        path = os.path.join(self.root, "index.json")
        with open(path, "rb") as f:
            before = f.read()
        os.utime(path, (1, 1))
        code, out = self.run_script()
        self.assertEqual(code, 0, out)
        self.assertIn("index.json unchanged", out)
        with open(path, "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(os.stat(path).st_mtime, 1)

    def test_commit_is_head_sha(self):
        # Helmp 用 commit 固定下载的文件版本，必须是构建时的 HEAD。
        self.plugin()
        self.init_git()
        self.assertEqual(self.run_script()[0], 0)
        head = subprocess.run(["git", "-C", self.root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        self.assertEqual(self.index()["commit"], head)

    # ---------------------------------------------------------- 失败路径

    def test_folder_name_must_match_id(self):
        # 文件夹名就是 id：Helmp 和 jsDelivr 都按 plugins/<id>/ 找文件，不一致就会下载到别的插件。
        self.plugin(folder="com.example.other")
        self.assert_fails("doesn't match the folder name")

    def test_duplicate_ids_fail(self):
        # 同一个 id 出现两次时，用户装到哪个取决于偶然的顺序；必须拒绝。
        manifest = json.loads(json.dumps(FLOMO_LIKE))
        manifest["id"] = "com.example.memo"
        self.plugin(manifest)
        self.plugin(manifest, folder="com.example.memo2")
        self.assert_fails("id com.example.memo is already used by plugins/com.example.memo")

    def test_unknown_top_level_field_fails(self):
        # Helmp 用 deny_unknown_fields 解析清单：注册表放行的拼写错误，用户那边会装不上。
        manifest = json.loads(json.dumps(FLOMO_LIKE))
        manifest["permision"] = []
        self.plugin(manifest)
        self.assert_fails('unknown field "permision"')

    def test_mcp_servers_are_allowed_but_reviewed(self):
        # mcpServers 是 Helmp 正在开发的字段：先放行，但它会启动进程，必须人工看过。
        manifest = json.loads(json.dumps(FLOMO_LIKE))
        manifest["mcpServers"] = {"x": {"command": "node"}}
        self.plugin(manifest)
        code, out = self.run_script("--check")
        self.assertEqual(code, 0, out)
        self.assertIn("declares mcpServers", out)

    def test_missing_license_fails(self):
        # 没有协议的代码别人不能合法地用；注册表要求每个插件声明 license。
        manifest = json.loads(json.dumps(FLOMO_LIKE))
        del manifest["license"]
        self.plugin(manifest)
        self.assert_fails("requires a license")

    def test_symlink_fails(self):
        # 符号链接可以指向插件目录以外的任意文件（如 ~/.ssh），安装器不跟随，注册表也不收。
        self.plugin()
        os.symlink("/etc/hosts", os.path.join(self.root, "plugins", "com.example.memo", "hosts"))
        self.assert_fails("symbolic links aren't allowed")

    def test_binary_file_fails(self):
        # 只有 PNG 可以是二进制：其余文件都要能在 PR diff 里读到，不能藏可执行程序。
        self.plugin(files={"tool.bin": b"\x7fELF\x00\x01\x02"})
        self.assert_fails("binary files aren't allowed")

    def test_fake_png_fails(self):
        # 改个扩展名就能绕过「只收文本」，所以 .png 要检查文件头。
        self.plugin(files={"icon.png": b"not a png"})
        self.assert_fails("not a PNG file")

    def test_hidden_file_fails(self):
        # 隐藏文件在 Finder 和多数 diff 视图里看不见，容易夹带东西（.DS_Store 也顺手拦掉）。
        self.plugin(files={".env": "SECRET=1\n"})
        self.assert_fails("hidden files and folders aren't allowed")

    def test_oversized_file_fails(self):
        # 与 Helmp 安装器的上限一致（单文件 512 KiB）：注册表放行而安装器拒绝，用户只会看到下载失败。
        self.plugin(files={"big.txt": "a" * (512 * 1024 + 1)})
        self.assert_fails("limit 524288 per file")

    def test_script_path_with_dotdot_fails(self):
        # 脚本路径跳出插件目录就能运行用户机器上的任意程序。
        manifest = json.loads(json.dumps(FLOMO_LIKE))
        manifest["commands"].append(
            {"id": "run", "title": "Run", "action": {"type": "script", "path": "../evil.sh"}}
        )
        self.plugin(manifest)
        self.assert_fails("script path must be relative")

    def test_templated_http_host_fails(self):
        # 主机名是模板时，启用前就无法告诉用户插件会连到哪里。
        manifest = json.loads(json.dumps(FLOMO_LIKE))
        manifest["commands"][0]["action"]["url"] = "https://{{query}}.example.com/"
        self.plugin(manifest)
        self.assert_fails("the host can't be a template")

    # ---------------------------------------------------------- --base-ref

    def test_update_without_version_bump_fails(self):
        # 已安装的用户靠版本号发现更新；内容变了版本不变，他们永远拿不到新文件（或 sha256 校验失败）。
        self.plugin()
        self.init_git()
        self.write("com.example.memo", "README.md", "# changed\n")
        self.assert_fails("the version wasn't raised", "--base-ref", "main")

    def test_update_with_version_bump_passes(self):
        # 提升版本号是正确的更新方式，必须放行，并在输出里标明是更新。
        self.plugin()
        self.init_git()
        manifest = json.loads(json.dumps(FLOMO_LIKE))
        manifest["version"] = "1.0.1"
        self.plugin(manifest)
        self.commit_all("bump")
        code, out = self.run_script("--check", "--base-ref", "HEAD~1")
        self.assertEqual(code, 0, out)
        self.assertIn("updated 1.0.0 → 1.0.1", out)

    def test_untouched_plugin_needs_no_bump(self):
        # 没改动的插件不应该因为别的 PR 被要求升版本。
        self.plugin()
        self.init_git()
        code, out = self.run_script("--check", "--base-ref", "main")
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
