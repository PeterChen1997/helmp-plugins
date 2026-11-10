#!/usr/bin/env python3
"""Helmp 插件中心注册表：校验 plugins/ 下的全部插件并生成 index.json。

用法（只用标准库，用 `python3 -I` 运行）：
  python3 -I scripts/build-index.py                     校验并写 index.json
  python3 -I scripts/build-index.py --check             只校验，不写
  python3 -I scripts/build-index.py --check --base-ref origin/main
                                                        另外对比 base：改过的插件必须提升版本号
  python3 -I scripts/build-index.py --helmp /path/to/helmp
                                                        另外用 Helmp 自己的校验器核对权限推导

校验规则镜像 Helmp 的 src/providers/plugins/manifest.rs，权限推导与文案逐字镜像
src/providers/plugins/permissions.rs（两边改动要同步；--helmp 用来发现不一致）。
模板变量（{{form.x}} 是否存在等）不在这里复刻，以 `helmp plugins validate` 为准。

退出码：0 = 全部通过；1 = 有问题（全部列出后才退出）；2 = 用法 / 环境错误。
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------- 常量

REPO = "PeterChen1997/helmp-plugins"
SOURCE_URL = "https://github.com/" + REPO + "/tree/main/plugins/{id}"
INDEX_SCHEMA = 1

# 与 Helmp 安装器一致的文件限制。
MAX_FILE_BYTES = 512 * 1024
MAX_PLUGIN_BYTES = 2 * 1024 * 1024
MAX_PLUGIN_FILES = 64
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

SCHEMA_VERSION = 1
CLIPBOARD_READ = "clipboard.read"
MAX_HTTP_TIMEOUT_MS = 30_000
MAX_SCRIPT_TIMEOUT_MS = 120_000
MAX_LIST_TIMEOUT_MS = 3_000
TINTS = ("blue", "indigo", "purple", "orange", "teal", "green", "red", "gray", "graphite")
LANGS = ("en", "zh-Hans")
HEADER_TOKEN_EXTRA = "!#$%&'*+-.^_`|~"
LUCIDE_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
U16_MAX = 2**16 - 1
U32_MAX = 2**32 - 1
U64_MAX = 2**64 - 1


class ManifestError(Exception):
    pass


# ---------------------------------------------------------------- 基础判断（镜像 Rust）


def ascii_lower(text):
    # Rust 的 to_ascii_lowercase 只改 A-Z；Python 的 lower() 会把 K（开尔文符号）之类变成 ASCII。
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in text)


def is_ascii_alnum(c):
    return ("a" <= c <= "z") or ("A" <= c <= "Z") or ("0" <= c <= "9")


def valid_id(plugin_id):
    """反向域名：至少两段，每段小写字母数字和 -，不以 - 开头结尾，总长 ≤ 100。"""
    segments = plugin_id.split(".")
    return (
        len(plugin_id.encode("utf-8")) <= 100
        and len(segments) >= 2
        and all(
            segment
            and not segment.startswith("-")
            and not segment.endswith("-")
            and all(("a" <= c <= "z") or ("0" <= c <= "9") or c == "-" for c in segment)
            for segment in segments
        )
    )


def valid_host(host):
    return (
        bool(host)
        and len(host.encode("utf-8")) <= 253
        and all(is_ascii_alnum(c) or c in "-." for c in host)
        and not host.startswith(".")
        and not host.endswith(".")
    )


def is_key(key):
    return bool(key) and is_ascii_alnum(key[0]) and all(is_ascii_alnum(c) or c in "_-" for c in key[1:])


def valid_scheme(scheme):
    return (
        bool(scheme)
        and (("a" <= scheme[0] <= "z") or ("A" <= scheme[0] <= "Z"))
        and all(is_ascii_alnum(c) or c in "+.-" for c in scheme[1:])
    )


def valid_version(version):
    """Helmp 只接受 x.y.z（三段纯数字）。"""
    parts = version.split(".")
    return len(parts) == 3 and all(part and part.isascii() and part.isdigit() for part in parts)


def version_tuple(version):
    return tuple(int(part) for part in version.split("."))


def safe_relative(path):
    """相对插件目录、不跳出插件目录的路径；注册表另外要求只用 / 分隔。"""
    if not path or "\\" in path or path.startswith("/"):
        return False
    return all(part != ".." for part in path.split("/"))


def normalize_relative(path):
    # 去掉 . 和空段（Rust 的 Path::components 也会这样规整），用于在文件清单里精确查找（大小写敏感）。
    return "/".join(part for part in path.split("/") if part not in ("", "."))


def split_url(url):
    if "://" not in url:
        return None
    scheme, rest = url.split("://", 1)
    end = len(rest)
    for ch in "/?#":
        index = rest.find(ch)
        if index != -1:
            end = min(end, index)
    return scheme, rest[:end]


def host_of(authority):
    authority = authority.rsplit("@", 1)[-1]
    return authority.split(":", 1)[0]


def find_pref(manifest, pref_id):
    for pref in manifest.get("preferences") or []:
        if isinstance(pref, dict) and pref.get("id") == pref_id:
            return pref
    return None


def http_url_source(url, manifest):
    """返回 ("static", host) / ("pref", pref_id, hosts)；不合法时抛 ManifestError（文案同 Rust 英文版）。"""
    if url.startswith("{{"):
        name = url[2:].split("}}", 1)[0].strip()
        pref_id = name[len("pref."):] if name.startswith("pref.") else ""
        pref = find_pref(manifest, pref_id)
        if pref is None:
            raise ManifestError(
                "the host can't be a template; when the whole URL comes from a preference, start with {{pref.<id>}}"
            )
        hosts = pref.get("allowedHosts") or []
        if not hosts:
            raise ManifestError(
                "the URL comes from preference %s, which must declare allowedHosts" % json.dumps(pref_id)
            )
        return ("pref", pref_id, list(hosts))
    parts = split_url(url)
    if parts is None or parts[0] not in ("https", "http"):
        raise ManifestError("must start with https:// or http://")
    authority = parts[1]
    if "{{" in authority:
        raise ManifestError("the host can't be a template (network access must be known before enabling)")
    host = ascii_lower(host_of(authority))
    if not valid_host(host):
        raise ManifestError("invalid host %s" % json.dumps(host))
    return ("static", host)


# ---------------------------------------------------------------- 权限推导（逐字镜像 permissions.rs）


class Permissions:
    def __init__(self):
        self.hosts = set()  # (主机名, 来自哪个偏好设置 或 None)
        self.schemes = set()
        self.open_any = False
        self.clipboard_read = False
        self.clipboard_write = False
        self.keystrokes = False
        self.exec = False

    @classmethod
    def derive(cls, manifest):
        permissions = cls()
        permissions.clipboard_read = CLIPBOARD_READ in (manifest.get("permissions") or [])
        for command in manifest.get("commands") or []:
            action = command.get("action")
            if action is not None:
                permissions._add(action, manifest)
            listing = command.get("list")
            if listing is not None:
                permissions.exec = True
                if listing.get("action") is not None:
                    permissions._add(listing["action"], manifest)
                else:
                    # 缺省动作：打开列表项的 arg（网址或路径）。
                    permissions.open_any = True
        return permissions

    def _add(self, action, manifest):
        kind = action.get("type")
        if kind == "open":
            url = action["url"]
            if ":" in url and not url.startswith("{{"):
                self.schemes.add(ascii_lower(url.split(":", 1)[0]))
            else:
                self.open_any = True
        elif kind == "http":
            try:
                source = http_url_source(action["url"], manifest)
            except ManifestError:
                # 校验阶段已经报错，走不到这里。
                return
            if source[0] == "static":
                self.hosts.add((source[1], None))
            else:
                for host in source[2]:
                    self.hosts.add((host, source[1]))
        elif kind == "script":
            self.exec = True
            output = action.get("output", "message")
            if output == "copy":
                self.clipboard_write = True
            elif output == "paste":
                self.clipboard_write = True
                self.keystrokes = True
        elif kind == "copy":
            self.clipboard_write = True
        elif kind == "paste":
            self.clipboard_write = True
            self.keystrokes = True

    def _sorted_hosts(self):
        # Rust 的 BTreeSet<(String, Option<String>)>：先按主机名，再 None 在 Some 前。
        return sorted(self.hosts, key=lambda hp: (hp[0], hp[1] is not None, hp[1] or ""))

    def keys(self):
        keys = ["network:" + host for host, _ in self._sorted_hosts()]
        keys.extend("open:" + scheme for scheme in sorted(self.schemes))
        if self.open_any:
            keys.append("open:*")
        if self.clipboard_read:
            keys.append("clipboard:read")
        if self.clipboard_write:
            keys.append("clipboard:write")
        if self.keystrokes:
            keys.append("keystrokes")
        if self.exec:
            keys.append("exec")
        return sorted(set(keys))

    def describe(self, lang):
        zh = lang == "zh-Hans"
        lines = []
        for host, pref in self._sorted_hosts():
            if pref is None:
                lines.append("访问网络：%s" % host if zh else "Network access: %s" % host)
            else:
                lines.append(
                    "访问网络：%s（地址来自偏好设置 %s）" % (host, pref)
                    if zh
                    else "Network access: %s (URL comes from preference %s)" % (host, pref)
                )
        schemes = sorted(self.schemes)
        if any(s in ("http", "https") for s in schemes):
            lines.append("在浏览器中打开网页" if zh else "Open web pages in your browser")
        apps = [s + "://" for s in schemes if s not in ("http", "https")]
        if apps:
            if zh:
                lines.append("打开 %s 链接（会启动对应的 App）" % "、".join(apps))
            else:
                lines.append("Open %s links (launches the matching app)" % ", ".join(apps))
        if self.open_any:
            lines.append("打开任意链接或文件" if zh else "Open any link or file")
        if self.clipboard_read:
            lines.append("读取剪贴板" if zh else "Read the clipboard")
        if self.clipboard_write:
            lines.append("写入剪贴板" if zh else "Write to the clipboard")
        if self.keystrokes:
            lines.append(
                "向前台应用发送 ⌘V（需要辅助功能权限）"
                if zh
                else "Send ⌘V to the front app (needs Accessibility permission)"
            )
        if self.exec:
            lines.append(
                "运行插件目录里的脚本（以你的用户身份，不受沙盒限制）"
                if zh
                else "Run scripts from the plugin folder (as you, not sandboxed)"
            )
        return lines


# ---------------------------------------------------------------- 清单结构（镜像 serde 的 deny_unknown_fields）

# 字段类型标记：
#   "str" / "bool" / "u16" / "u32" / "u64" / "text" / "any"
#   ("list", T) / ("map", T) / 结构名（下面 STRUCTS 的键）
# 第三项为 True 表示必填；Option 字段（第四项 True）允许 null。
STRUCTS = {
    "Manifest": {
        "$comment": ("any", False, True),
        "$schema": ("any", False, True),
        "schemaVersion": ("u32", True, False),
        "id": ("str", True, False),
        "name": ("text", True, False),
        "description": ("text", False, True),
        "version": ("str", True, False),
        "author": ("str", True, False),
        "homepage": ("str", False, True),
        "icon": ("str", False, True),
        "tint": ("str", False, True),
        "permissions": (("list", "str"), False, False),
        "preferences": (("list", "Preference"), False, False),
        "commands": (("list", "Command"), True, False),
        # 注册表要求（Helmp 本身可选）。
        "license": ("str", False, True),
        # Helmp 正在开发的字段：允许，但一律人工审核。
        "mcpServers": ("any", False, True),
    },
    "Preference": {
        "$comment": ("any", False, True),
        "id": ("str", True, False),
        "type": ("str", True, False),
        "title": ("text", True, False),
        "description": ("text", False, True),
        "placeholder": ("text", False, True),
        "required": ("bool", False, False),
        "default": ("str", False, True),
        "options": (("list", "Choice"), False, False),
        "allowedHosts": (("list", "str"), False, False),
    },
    "Choice": {
        "title": ("text", True, False),
        "value": ("str", True, False),
    },
    "Command": {
        "$comment": ("any", False, True),
        "id": ("str", True, False),
        "title": ("text", True, False),
        "subtitle": ("text", False, True),
        "keywords": (("list", "str"), False, False),
        "icon": ("str", False, True),
        "tint": ("str", False, True),
        "argument": ("Argument", False, True),
        "form": (("list", "FormField"), False, False),
        "action": ("Action", False, True),
        "list": ("ListSpec", False, True),
    },
    "Argument": {
        "placeholder": ("text", False, True),
        "required": ("bool", False, False),
    },
    "FormField": {
        "$comment": ("any", False, True),
        "id": ("str", True, False),
        "type": ("str", True, False),
        "label": ("text", True, False),
        "placeholder": ("text", False, True),
        "required": ("bool", False, False),
        "default": ("str", False, True),
        "options": (("list", "Choice"), False, False),
    },
    "open": {"type": ("str", True, False), "url": ("str", True, False)},
    "copy": {"type": ("str", True, False), "text": ("str", True, False)},
    "paste": {"type": ("str", True, False), "text": ("str", True, False)},
    "http": {
        "type": ("str", True, False),
        "method": ("str", True, False),
        "url": ("str", True, False),
        "headers": (("map", "str"), False, False),
        "json": ("any", False, True),
        "body": ("str", False, True),
        "timeoutMs": ("u64", False, True),
        "success": ("Success", False, False),
        "message": ("text", False, True),
        "errorPath": ("str", False, True),
    },
    "Success": {
        "status": (("list", "u16"), False, False),
        "jsonPath": ("str", False, True),
        "equals": ("any", False, True),
        "optional": ("bool", False, False),
    },
    "script": {
        "type": ("str", True, False),
        "path": ("str", True, False),
        "args": (("list", "str"), False, False),
        "env": (("map", "str"), False, False),
        "stdin": ("str", False, True),
        "timeoutMs": ("u64", False, True),
        "output": ("str", False, False),
    },
    "ListSpec": {
        "script": ("ListScript", True, False),
        "action": ("Action", False, True),
        "minQueryLength": ("u64", False, False),
        "cacheSeconds": ("u64", False, False),
    },
    "ListScript": {
        "path": ("str", True, False),
        "args": (("list", "str"), False, False),
        "env": (("map", "str"), False, False),
        "timeoutMs": ("u64", False, True),
    },
}
ACTION_TYPES = ("open", "http", "script", "copy", "paste")
ENUMS = {
    ("Preference", "type"): ("text", "secret", "select", "checkbox"),
    ("FormField", "type"): ("text", "textarea", "select"),
    ("http", "method"): ("GET", "POST", "PUT", "PATCH", "DELETE"),
    ("script", "output"): ("message", "silent", "copy", "paste"),
}


def type_errors(value, kind, at, errors):
    """按类型标记检查结构；返回值是否可以继续做语义检查。"""
    if kind == "any":
        return True
    if kind == "str":
        if not isinstance(value, str):
            errors.append("%s: must be a string" % at)
            return False
        return True
    if kind == "bool":
        if not isinstance(value, bool):
            errors.append("%s: must be true or false" % at)
            return False
        return True
    if kind in ("u16", "u32", "u64"):
        limit = {"u16": U16_MAX, "u32": U32_MAX, "u64": U64_MAX}[kind]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= limit:
            errors.append("%s: must be a non-negative integer" % at)
            return False
        return True
    if kind == "text":
        if isinstance(value, str):
            return True
        if isinstance(value, dict) and all(isinstance(v, str) for v in value.values()):
            return True
        errors.append('%s: must be a string or {"en": "…", "zh-Hans": "…"}' % at)
        return False
    if isinstance(kind, tuple):
        container, inner = kind
        if container == "list":
            if not isinstance(value, list):
                errors.append("%s: must be an array" % at)
                return False
            ok = True
            for index, item in enumerate(value):
                ok = type_errors(item, inner, "%s[%d]" % (at, index), errors) and ok
            return ok
        if not isinstance(value, dict):
            errors.append("%s: must be an object" % at)
            return False
        ok = True
        for key, item in value.items():
            ok = type_errors(item, inner, "%s.%s" % (at, key), errors) and ok
        return ok
    if kind == "Action":
        if not isinstance(value, dict):
            errors.append("%s: must be an object" % at)
            return False
        action_type = value.get("type")
        if action_type not in ACTION_TYPES:
            errors.append(
                "%s.type: must be one of %s" % (at, ", ".join(ACTION_TYPES))
            )
            return False
        kind = action_type
    if not isinstance(value, dict):
        errors.append("%s: must be an object" % at)
        return False
    fields = STRUCTS[kind]
    ok = True
    for key in value:
        if key not in fields:
            errors.append("%s: unknown field %s" % (at or "(top level)", json.dumps(key)))
            ok = False
    for key, (field_kind, required, nullable) in fields.items():
        prefix = "%s.%s" % (at, key) if at else key
        if key not in value:
            if required:
                errors.append("%s: missing required field" % prefix)
                ok = False
            continue
        item = value[key]
        if item is None and nullable:
            continue
        if not type_errors(item, field_kind, prefix, errors):
            ok = False
            continue
        allowed = ENUMS.get((kind, key))
        if allowed and item not in allowed:
            errors.append("%s: must be one of %s" % (prefix, ", ".join(allowed)))
            ok = False
    return ok


# ---------------------------------------------------------------- 语义校验（镜像 manifest.rs::validate）


class Checker:
    def __init__(self, manifest, files):
        self.manifest = manifest
        self.files = files  # 插件目录里的文件（规整后的相对路径集合）
        self.errors = []

    def error(self, at, message):
        self.errors.append("%s: %s" % (at, message))

    def text(self, at, value):
        if value is None:
            return
        if isinstance(value, str):
            if not value.strip():
                self.error(at, "must not be empty")
            return
        if "en" not in value:
            self.error(at, 'localized text needs an "en" entry (the fallback)')
        for lang, item in sorted(value.items()):
            if lang not in LANGS:
                self.error(at, "unsupported language %s (use en or zh-Hans)" % json.dumps(lang))
            if not item.strip():
                self.error("%s.%s" % (at, lang), "must not be empty")

    def key(self, at, key):
        if not is_key(key):
            self.error(
                at,
                "id %s may only contain letters, digits, _ and -, starting with a letter or digit" % json.dumps(key),
            )

    def file_exists(self, path):
        return normalize_relative(path) in self.files

    def icon(self, at, icon):
        if icon is None:
            return
        if icon.endswith(".png"):
            if not safe_relative(icon):
                self.error(at, "icon path must be relative to the plugin folder without .. (use / as separator)")
            elif not self.file_exists(icon):
                self.error(at, "icon file %s not found" % icon)
        elif not LUCIDE_NAME.match(icon):
            self.error(
                at,
                "%s isn't a Lucide icon name (lowercase letters, digits and -, e.g. notebook-pen) or a .png in the plugin folder"
                % json.dumps(icon),
            )

    def tint(self, at, tint):
        if tint is not None and tint not in TINTS:
            self.error(at, "unknown tint %s (use %s)" % (json.dumps(tint), ", ".join(TINTS)))

    def choices(self, at, options):
        if not options:
            self.error(at, "a select needs at least one option")
        seen = set()
        for index, option in enumerate(options):
            self.text("%s[%d].title" % (at, index), option["title"])
            if option["value"] in seen:
                self.error("%s[%d].value" % (at, index), "duplicate option value %s" % json.dumps(option["value"]))
            seen.add(option["value"])

    def timeout(self, at, value, maximum):
        if value is not None and not 1 <= value <= maximum:
            self.error(at, "must be between 1 and %d milliseconds" % maximum)

    def script_path(self, at, path):
        if not safe_relative(path):
            self.error(at, "script path must be relative to the plugin folder, not absolute, without .. and with / as separator")
            return
        if not self.file_exists(path):
            self.error(at, "script %s not found" % path)

    def env(self, at, env):
        for name in env or {}:
            ok = (
                bool(name)
                and (("a" <= name[0] <= "z") or ("A" <= name[0] <= "Z") or name[0] == "_")
                and all(is_ascii_alnum(c) or c == "_" for c in name)
            )
            if not ok:
                self.error("%s.%s" % (at, name), "environment variable names may only use letters, digits and _")

    def action(self, at, action):
        kind = action["type"]
        if kind == "open":
            url = action["url"]
            scheme_static = ":" in url and valid_scheme(url.split(":", 1)[0])
            if not scheme_static and not url.startswith("{{"):
                self.error(at + ".url", "must start with a scheme (https:, obsidian: …) or be a template")
        elif kind == "http":
            self.http(at, action)
        elif kind == "script":
            self.script_path(at + ".path", action["path"])
            self.env(at + ".env", action.get("env"))
            self.timeout(at + ".timeoutMs", action.get("timeoutMs"), MAX_SCRIPT_TIMEOUT_MS)

    def http(self, at, spec):
        try:
            http_url_source(spec["url"], self.manifest)
        except ManifestError as err:
            self.error(at + ".url", str(err))
        has_json = spec.get("json") is not None
        has_body = spec.get("body") is not None
        if has_json and has_body:
            self.error(at, "use either json or body, not both")
        if (has_json or has_body) and spec["method"] not in ("POST", "PUT", "PATCH"):
            self.error(at, "%s requests can't have a body" % spec["method"])
        for name in spec.get("headers") or {}:
            if not name or not all(is_ascii_alnum(c) or c in HEADER_TOKEN_EXTRA for c in name):
                self.error(at + ".headers", "invalid header name %s" % json.dumps(name))
        self.timeout(at + ".timeoutMs", spec.get("timeoutMs"), MAX_HTTP_TIMEOUT_MS)
        success = spec.get("success") or {}
        for index, status in enumerate(success.get("status") or []):
            if not 100 <= status <= 599:
                self.error("%s.success.status[%d]" % (at, index), "%d isn't an HTTP status code" % status)
        if (success.get("equals") is not None) != (success.get("jsonPath") is not None):
            self.error(at + ".success", "jsonPath and equals go together")
        self.text(at + ".message", spec.get("message"))

    def run(self):
        m = self.manifest
        if m["schemaVersion"] != SCHEMA_VERSION:
            self.error("schemaVersion", "this version of Helmp only supports %d" % SCHEMA_VERSION)
        if not valid_id(m["id"]):
            self.error(
                "id",
                "%s isn't a reverse-DNS id (e.g. com.example.my-plugin: lowercase letters, digits, -)" % json.dumps(m["id"]),
            )
        self.text("name", m["name"])
        self.text("description", m.get("description"))
        if not valid_version(m["version"]):
            self.error("version", "%s isn't an x.y.z version" % json.dumps(m["version"]))
        if not m["author"].strip():
            self.error("author", "must not be empty")
        if m.get("license") is None or not m["license"].strip():
            self.error("license", "the registry requires a license (e.g. \"MIT\")")
        self.icon("icon", m.get("icon"))
        self.tint("tint", m.get("tint"))
        for index, permission in enumerate(m.get("permissions") or []):
            if permission != CLIPBOARD_READ:
                self.error(
                    "permissions[%d]" % index,
                    'unknown permission %s. Only "clipboard.read" can be declared; network, open and script permissions are derived from the manifest'
                    % json.dumps(permission),
                )

        pref_ids = set()
        for index, pref in enumerate(m.get("preferences") or []):
            at = "preferences[%d]" % index
            self.key(at + ".id", pref["id"])
            if pref["id"] in pref_ids:
                self.error(at + ".id", "duplicate id %s" % json.dumps(pref["id"]))
            pref_ids.add(pref["id"])
            self.text(at + ".title", pref["title"])
            kind = pref["type"]
            options = pref.get("options") or []
            default = pref.get("default")
            if kind == "select":
                self.choices(at + ".options", options)
                if default is not None and not any(o["value"] == default for o in options):
                    self.error(at + ".default", "default must be one of the option values")
            elif kind == "checkbox":
                if default is not None and default not in ("true", "false"):
                    self.error(at + ".default", 'a checkbox default must be "true" or "false"')
            elif kind == "secret" and default is not None:
                self.error(at + ".default", "secrets can't have a default (keys don't belong in the manifest)")
            if options and kind != "select":
                self.error(at + ".options", "only selects have options")
            hosts = pref.get("allowedHosts") or []
            if hosts and kind not in ("text", "secret"):
                self.error(at + ".allowedHosts", "only text and secret preferences can declare allowedHosts")
            for host_index, host in enumerate(hosts):
                if not valid_host(host) or ascii_lower(host) != host:
                    self.error(
                        "%s.allowedHosts[%d]" % (at, host_index),
                        "%s isn't a lowercase host name (no scheme or port)" % json.dumps(host),
                    )

        commands = m["commands"]
        if not commands:
            self.error("commands", "needs at least one command")
        command_ids = set()
        for index, command in enumerate(commands):
            at = "commands[%d]" % index
            self.key(at + ".id", command["id"])
            if command["id"] in command_ids:
                self.error(at + ".id", "duplicate id %s" % json.dumps(command["id"]))
            command_ids.add(command["id"])
            self.text(at + ".title", command["title"])
            self.text(at + ".subtitle", command.get("subtitle"))
            self.icon(at + ".icon", command.get("icon"))
            self.tint(at + ".tint", command.get("tint"))
            for k, keyword in enumerate(command.get("keywords") or []):
                if not keyword.strip():
                    self.error("%s.keywords[%d]" % (at, k), "must not be empty")
            field_ids = set()
            form = command.get("form") or []
            for f, field in enumerate(form):
                field_at = "%s.form[%d]" % (at, f)
                self.key(field_at + ".id", field["id"])
                if field["id"] in field_ids:
                    self.error(field_at + ".id", "duplicate id %s" % json.dumps(field["id"]))
                field_ids.add(field["id"])
                self.text(field_at + ".label", field["label"])
                if field["type"] == "select":
                    self.choices(field_at + ".options", field.get("options") or [])
                elif field.get("options"):
                    self.error(field_at + ".options", "only selects have options")
            action = command.get("action")
            listing = command.get("list")
            if action is not None and listing is not None:
                self.error(at, "use either action or list, not both")
            elif action is None and listing is None:
                self.error(at, "needs an action or a list")
            elif action is not None:
                self.action(at + ".action", action)
            else:
                if form:
                    self.error(at + ".form", "list commands can't have a form")
                script = listing["script"]
                self.script_path(at + ".list.script.path", script["path"])
                self.env(at + ".list.script.env", script.get("env"))
                self.timeout(at + ".list.script.timeoutMs", script.get("timeoutMs"), MAX_LIST_TIMEOUT_MS)
                if listing.get("action") is not None:
                    self.action(at + ".list.action", listing["action"])
        return self.errors


def review_items(manifest, permissions, executables):
    """需要人工审核的原因（不算失败），英文。"""
    items = []
    for index, command in enumerate(manifest.get("commands") or []):
        at = "commands[%d]" % index
        action = command.get("action")
        if action is not None and action.get("type") == "script":
            items.append("%s runs a script: %s (exec)" % (at, action["path"]))
        listing = command.get("list")
        if listing is not None:
            items.append("%s runs a list script: %s (exec)" % (at, listing["script"]["path"]))
            list_action = listing.get("action")
            if list_action is not None and list_action.get("type") == "script":
                items.append("%s.list.action runs a script: %s (exec)" % (at, list_action["path"]))
    for path in executables:
        items.append("executable file: %s" % path)
    if "mcpServers" in manifest:
        items.append("declares mcpServers: check every server command, argument and environment variable")
    if permissions.clipboard_read:
        items.append("reads the clipboard (clipboard.read)")
    if permissions.keystrokes:
        items.append("sends keystrokes (⌘V) to the front app")
    return items


# ---------------------------------------------------------------- 文件检查


def reject_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ManifestError("duplicate key %s" % json.dumps(key))
        seen[key] = value
    return seen


def reject_constant(name):
    raise ManifestError("%s is not valid JSON" % name)


def parse_json(data):
    """严格 JSON：拒绝重复键和 NaN/Infinity（serde_json 也不接受后者）。"""
    return json.loads(data, object_pairs_hook=reject_duplicate_keys, parse_constant=reject_constant)


def scan_plugin(plugin_dir, errors):
    """列出插件目录里的文件：{相对路径: (完整路径, lstat)}。符号链接、隐藏文件等直接报错。"""
    files = {}

    def walk(directory, prefix):
        try:
            entries = sorted(os.scandir(directory), key=lambda e: e.name)
        except OSError as err:
            errors.append("%s: can't read folder (%s)" % (prefix or ".", err.strerror))
            return
        for entry in entries:
            name = entry.name
            rel = prefix + name
            try:
                name.encode("utf-8")
            except UnicodeEncodeError:
                errors.append("%r: file names must be valid UTF-8" % rel)
                continue
            if name.startswith("."):
                errors.append("%s: hidden files and folders aren't allowed" % rel)
                continue
            if "\\" in name:
                errors.append("%s: file names must not contain a backslash" % rel)
                continue
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                errors.append("%s: symbolic links aren't allowed" % rel)
            elif stat.S_ISDIR(info.st_mode):
                walk(entry.path, rel + "/")
            elif stat.S_ISREG(info.st_mode):
                files[rel] = (entry.path, info)
            else:
                errors.append("%s: only regular files and folders are allowed" % rel)

    walk(plugin_dir, "")
    return files


def check_files(files, errors):
    """大小、数量、内容类型。返回 {相对路径: bytes}。"""
    contents = {}
    total = 0
    if len(files) > MAX_PLUGIN_FILES:
        errors.append("plugin has %d files (limit %d)" % (len(files), MAX_PLUGIN_FILES))
    for rel, (path, info) in sorted(files.items()):
        size = info.st_size
        total += size
        if size > MAX_FILE_BYTES:
            errors.append("%s: %d bytes (limit %d per file)" % (rel, size, MAX_FILE_BYTES))
            continue
        with open(path, "rb") as f:
            data = f.read()
        contents[rel] = data
        if rel.lower().endswith(".png"):
            if not data.startswith(PNG_MAGIC):
                errors.append("%s: not a PNG file" % rel)
            continue
        if b"\x00" in data:
            errors.append("%s: binary files aren't allowed (NUL byte; only .png images may be binary)" % rel)
            continue
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            errors.append("%s: not valid UTF-8 text (only .png images may be binary)" % rel)
    if total > MAX_PLUGIN_BYTES:
        errors.append("plugin is %d bytes in total (limit %d)" % (total, MAX_PLUGIN_BYTES))
    return contents


# ---------------------------------------------------------------- 单个插件


class Plugin:
    def __init__(self, folder):
        self.folder = folder
        self.errors = []
        self.review = []
        self.manifest = None
        self.permissions = None
        self.entry = None
        self.files = {}  # 相对路径 → (完整路径, lstat)
        self.contents = {}


def text_pair(value):
    if value is None:
        return None
    if isinstance(value, str):
        return {"en": value, "zh-Hans": value}
    return {"en": value["en"], "zh-Hans": value.get("zh-Hans", value["en"])}


def load_plugin(plugins_dir, folder):
    plugin = Plugin(folder)
    plugin_dir = os.path.join(plugins_dir, folder)
    plugin.files = scan_plugin(plugin_dir, plugin.errors)
    plugin.contents = check_files(plugin.files, plugin.errors)
    if "README.md" not in plugin.files:
        plugin.errors.append("README.md: missing (every plugin needs a README)")
    if "plugin.json" not in plugin.files:
        plugin.errors.append("plugin.json: missing")
        return plugin
    data = plugin.contents.get("plugin.json")
    if data is None:
        return plugin  # 已经因为大小等原因报错
    try:
        manifest = parse_json(data.decode("utf-8"))
    except (ManifestError, ValueError) as err:
        plugin.errors.append("plugin.json: %s" % err)
        return plugin
    if not isinstance(manifest, dict):
        plugin.errors.append("plugin.json: must be a JSON object")
        return plugin
    structure = []
    if not type_errors(manifest, "Manifest", "", structure):
        plugin.errors.extend("plugin.json " + e for e in structure)
        return plugin
    plugin.manifest = manifest
    if manifest["id"] != folder:
        plugin.errors.append(
            "plugin.json id: %s doesn't match the folder name %s" % (json.dumps(manifest["id"]), json.dumps(folder))
        )
    normalized = {normalize_relative(rel) for rel in plugin.files}
    plugin.errors.extend("plugin.json " + e for e in Checker(manifest, normalized).run())
    if plugin.errors:
        return plugin

    plugin.permissions = Permissions.derive(manifest)
    executables = [rel for rel, (_, info) in sorted(plugin.files.items()) if info.st_mode & 0o111]
    plugin.review = review_items(manifest, plugin.permissions, executables)
    plugin.entry = index_entry(plugin)
    return plugin


def index_entry(plugin):
    m = plugin.manifest
    icon = None
    if isinstance(m.get("icon"), str) and m["icon"].endswith(".png"):
        icon = normalize_relative(m["icon"])
    elif "icon.png" in plugin.files:
        icon = "icon.png"
    keywords = []
    for command in m["commands"]:
        for keyword in command.get("keywords") or []:
            if keyword not in keywords:
                keywords.append(keyword)
    files = []
    for rel in sorted(plugin.files):
        _, info = plugin.files[rel]
        data = plugin.contents[rel]
        files.append(
            {
                "path": rel,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "executable": bool(info.st_mode & 0o111),
            }
        )
    return {
        "id": m["id"],
        "version": m["version"],
        "name": text_pair(m["name"]),
        "description": text_pair(m.get("description")),
        "author": m["author"],
        "homepage": m.get("homepage"),
        "license": m.get("license"),
        "icon": icon,
        "keywords": keywords,
        "commands": len(m["commands"]),
        "permissions": plugin.permissions.keys(),
        "permissions_text": {
            "en": plugin.permissions.describe("en"),
            "zh-Hans": plugin.permissions.describe("zh-Hans"),
        },
        "review": plugin.review,
        "source": SOURCE_URL.format(id=m["id"]),
        "files": files,
    }


# ---------------------------------------------------------------- git


def git(root, *args):
    result = subprocess.run(
        ["git", "-C", root] + list(args), capture_output=True, check=False
    )
    return result.returncode, result.stdout, result.stderr.decode("utf-8", "replace").strip()


def head_commit(root):
    code, out, _ = git(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    if code != 0:
        return None
    sha = out.decode().strip()
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


def git_blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def base_tree(root, ref):
    """base ref 里 plugins/ 下的文件：{插件文件夹: {相对路径: (mode, blob sha)}}。"""
    code, out, err = git(root, "ls-tree", "-r", "-z", ref, "--", "plugins/")
    if code != 0:
        raise SystemExit("error: can't read --base-ref %s: %s" % (ref, err))
    tree = {}
    for record in out.split(b"\0"):
        if not record:
            continue
        meta, path = record.split(b"\t", 1)
        mode, _, sha = meta.decode().split(" ")
        parts = path.decode("utf-8", "replace").split("/", 2)
        if len(parts) < 3:
            continue
        tree.setdefault(parts[1], {})[parts[2]] = (mode, sha)
    return tree


def compare_with_base(root, ref, plugins, errors_by_plugin, notes):
    code, _, err = git(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
    if code != 0:
        raise SystemExit("error: --base-ref %s isn't a commit in %s" % (ref, root))
    base = base_tree(root, ref)
    base_ids_lower = {folder.lower(): folder for folder in base}
    current = {p.folder for p in plugins}
    for plugin in plugins:
        old = base.get(plugin.folder)
        if old is None:
            clash = base_ids_lower.get(plugin.folder.lower())
            if clash is not None and clash not in current:
                errors_by_plugin.setdefault(plugin.folder, []).append(
                    "id clashes with existing plugin %s" % clash
                )
            notes.append("%s: new plugin" % plugin.folder)
            continue
        now = {}
        for rel, data in plugin.contents.items():
            mode = "100755" if plugin.files[rel][1].st_mode & 0o111 else "100644"
            now[rel] = (mode, git_blob_sha(data))
        if now == old or plugin.manifest is None:
            continue
        code, out, _ = git(root, "show", "%s:plugins/%s/plugin.json" % (ref, plugin.folder))
        try:
            old_version = parse_json(out.decode("utf-8")).get("version") if code == 0 else None
        except (ManifestError, ValueError, AttributeError):
            old_version = None
        new_version = plugin.manifest["version"]
        if isinstance(old_version, str) and valid_version(old_version) and valid_version(new_version):
            if version_tuple(new_version) <= version_tuple(old_version):
                errors_by_plugin.setdefault(plugin.folder, []).append(
                    "version: files changed but the version wasn't raised (base %s, now %s)" % (old_version, new_version)
                )
            else:
                notes.append("%s: updated %s → %s" % (plugin.folder, old_version, new_version))
    for folder in sorted(set(base) - current):
        notes.append("%s: removed" % folder)


# ---------------------------------------------------------------- 与 Helmp 核对


def check_with_helmp(helmp, plugin_dir, plugin):
    problems = []
    with tempfile.TemporaryDirectory(prefix="helmp-data-") as data_dir:
        env = dict(os.environ, HELMP_DATA_DIR=data_dir)
        try:
            result = subprocess.run(
                [helmp, "plugins", "validate", plugin_dir, "--json"],
                capture_output=True,
                env=env,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as err:
            return ["helmp: couldn't run %s (%s)" % (helmp, err)]
    try:
        report = json.loads(result.stdout.decode("utf-8"))
        if not isinstance(report, dict):
            raise ValueError("not an object")
    except (ValueError, UnicodeDecodeError) as err:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        return ["helmp: `plugins validate --json` didn't print JSON (%s) %s" % (err, stderr)]
    if not report.get("ok"):
        for error in report.get("errors") or ["(no details)"]:
            problems.append("helmp: %s" % error)
        return problems
    if report.get("permissions") != plugin.permissions.keys():
        problems.append(
            "helmp: permissions differ from this script's mirror (helmp %s, script %s)"
            % (report.get("permissions"), plugin.permissions.keys())
        )
    texts = report.get("permissions_text")
    if texts not in (plugin.permissions.describe("en"), plugin.permissions.describe("zh-Hans")):
        problems.append("helmp: permission descriptions differ from this script's mirror: %s" % texts)
    if report.get("version") != plugin.manifest["version"] or report.get("commands") != len(plugin.manifest["commands"]):
        problems.append("helmp: version / command count differ: %s" % report)
    return problems


# ---------------------------------------------------------------- index.json


def render_index(entries, commit, generated_at):
    index = {
        "schema": INDEX_SCHEMA,
        "generated_at": generated_at,
        "commit": commit,
        "plugins": entries,
    }
    return json.dumps(index, indent=2, ensure_ascii=False) + "\n"


def write_index(path, entries, commit):
    """内容（除 generated_at 外）没变就不改写文件，返回是否写了。"""
    try:
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        old = None
    if isinstance(old, dict):
        previous = dict(old)
        previous.pop("generated_at", None)
        fresh = {"schema": INDEX_SCHEMA, "commit": commit, "plugins": entries}
        # 经过一次序列化再比较，避免 Python 对象与 JSON 解析结果的细微差异。
        if json.loads(json.dumps(fresh, ensure_ascii=False)) == previous:
            return False
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_index(entries, commit, now))
    return True


# ---------------------------------------------------------------- 入口


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate Helmp registry plugins and build index.json.")
    parser.add_argument("--root", help="registry root (default: the folder above scripts/)")
    parser.add_argument("--check", action="store_true", help="validate only, don't write index.json")
    parser.add_argument("--base-ref", help="git ref to compare with: changed plugins must raise their version")
    parser.add_argument("--helmp", help="Helmp executable: cross-check with `helmp plugins validate --json`")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root or os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
    plugins_dir = os.path.join(root, "plugins")
    if not os.path.isdir(plugins_dir):
        print("error: %s has no plugins/ folder" % root, file=sys.stderr)
        return 2

    errors_by_plugin = {}
    top_errors = []
    plugins = []
    for entry in sorted(os.scandir(plugins_dir), key=lambda e: e.name):
        name = entry.name
        if name.startswith("."):
            top_errors.append("plugins/%s: hidden files and folders aren't allowed" % name)
            continue
        if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
            top_errors.append("plugins/%s: every entry in plugins/ must be a plugin folder" % name)
            continue
        if not valid_id(name):
            top_errors.append("plugins/%s: folder name must be the plugin id (reverse-DNS, lowercase)" % name)
        plugin = load_plugin(plugins_dir, name)
        plugins.append(plugin)
        if plugin.errors:
            errors_by_plugin.setdefault(name, []).extend(plugin.errors)

    # 文件夹名 == id，所以 id 天然唯一；这里再防一手（例如大小写不同的文件夹在 Linux 上可以并存）。
    seen = {}
    for plugin in plugins:
        if plugin.manifest is None:
            continue
        key = plugin.manifest["id"].lower()
        if key in seen:
            errors_by_plugin.setdefault(plugin.folder, []).append(
                "id %s is already used by plugins/%s" % (plugin.manifest["id"], seen[key])
            )
        seen[key] = plugin.folder

    notes = []
    if args.base_ref:
        compare_with_base(root, args.base_ref, plugins, errors_by_plugin, notes)

    if args.helmp:
        for plugin in plugins:
            if plugin.entry is None:
                continue
            problems = check_with_helmp(args.helmp, os.path.join(plugins_dir, plugin.folder), plugin)
            if problems:
                errors_by_plugin.setdefault(plugin.folder, []).extend(problems)

    for error in top_errors:
        print("✗ " + error)
    for plugin in plugins:
        problems = errors_by_plugin.get(plugin.folder)
        if problems:
            print("✗ %s" % plugin.folder)
            for problem in problems:
                print("    - " + problem)
        else:
            print("✓ %s %s" % (plugin.folder, plugin.manifest["version"]))

    reviews = [(p.folder, p.review) for p in plugins if p.review]
    if reviews:
        print("\nNeeds human review (not failures):")
        for folder, items in reviews:
            print("  %s" % folder)
            for item in items:
                print("    - " + item)
    if notes:
        print("\nChanges compared with %s:" % args.base_ref)
        for note in notes:
            print("  - " + note)

    failed = bool(top_errors) or any(errors_by_plugin.values())
    count = sum(len(v) for v in errors_by_plugin.values()) + len(top_errors)
    if failed:
        print("\nFAILED: %d problem(s) in %d plugin(s)" % (count, len(plugins)))
        return 1
    print("\nOK: %d plugin(s)" % len(plugins))
    if args.check:
        return 0
    entries = sorted((p.entry for p in plugins), key=lambda e: e["id"])
    index_path = os.path.join(root, "index.json")
    if write_index(index_path, entries, head_commit(root)):
        print("wrote %s" % index_path)
    else:
        print("index.json unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
