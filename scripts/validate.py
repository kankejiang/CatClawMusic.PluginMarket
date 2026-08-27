#!/usr/bin/env python3
"""CatClawMusic 插件市场 index.json 校验器。

规范版本：2026-08-27（对照 AstrBot Plugin Market JSON Specification 移植适配）
清单 schema 版本：1

用法：
    python scripts/validate.py index.json

校验规则（返回错误列表，空列表即通过）：
    1.  根节点必须是 JSON 对象
    2.  必须包含保留键 $meta
    3.  $meta 必须是对象
    4.  $meta.schema_version 必须是整数 1
    5.  $meta 之外的根键必须是 plugin_id（author/name）或 name（兼容例外）
    6.  $meta 之外的根值必须是对象（PluginRecord）
    7.  每条记录必须包含全部必填字段（name 在 name 键下可省略）
    8.  必填字符串字段 trim 后非空
    9.  author 与 name 不含 "/"
    10. author 与 name 不含 ASCII 控制字符
    11. 根键必须等于 author/name（或 name 键兼容例外）
    12. 大小写归一化后 plugin_id 不得重复
    13. repo 必须是 HTTPS GitHub 仓库 URL
    14. download_url 若存在必须是 HTTPS URL
    15. tags 若存在必须是字符串数组
    16. platforms 若存在必须是字符串数组且取值限 {android, windows}
    17. stars 若存在必须是非负整数
    18. download_count 若存在必须是非负整数
    19. updated_at 若存在必须是 ISO 8601 时间戳
    20. $meta.homepage 若存在必须是 HTTPS URL
    21. $meta.repository 若存在必须是 HTTPS URL
    22. $meta.updated_at 若存在必须是 ISO 8601 时间戳
    23. PluginRecord 内不得使用保留字段（运行时字段）
    24. host_version 若存在必须是非空字符串
    25. 墓碑文件 del-plugins.json 中的 plugin_id 不得出现在 index.json

包身份一致性（metadata.author/name/version 与包内插件元数据一致）由宿主
安装后回验（对照 AstrBot 规范第 12 节安装规则第 5 条）。
"""

from __future__ import annotations

import json
import re
import sys

REPO_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9-]+/[A-Za-z0-9_.-]+?"
    r"(?:\.git|/tree/[A-Za-z0-9_.-]+)?$"
)
ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

VALID_PLATFORMS = {"android", "windows"}

# AstrBot 规范第 8 节保留字段（运行时/本地安装字段不得出现在市场数据中）
RESERVED_FIELDS = {
    "plugin_id",
    "market_plugin_id",
    "market_plugin_identifier",
    "root_dir_name",
    "local_plugin_name",
    "install_method",
    "registry_url",
    "registry_name",
    "installed_at",
}

REQUIRED_FIELDS = ("author", "version", "repo", "desc")


def _is_nonempty_str(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_int(value) -> bool:
    # bool 是 int 的子类，需排除
    return isinstance(value, int) and not isinstance(value, bool)


def _is_https(value) -> bool:
    return isinstance(value, str) and value.startswith("https://")


def validate_meta(meta, errors: list[str]) -> None:
    if not isinstance(meta, dict):
        errors.append("$meta 必须是对象")
        return
    if meta.get("schema_version") != 1 or isinstance(meta.get("schema_version"), bool):
        errors.append("$meta.schema_version 必须是整数 1")
    for field in ("homepage", "repository"):
        if field in meta and not _is_https(meta.get(field)):
            errors.append(f"$meta.{field} 若存在必须是 HTTPS URL")
    if "updated_at" in meta and not (
        isinstance(meta.get("updated_at"), str) and ISO_RE.match(meta["updated_at"])
    ):
        errors.append("$meta.updated_at 若存在必须是 ISO 8601 时间戳")


def validate_record(key: str, record, errors: list[str], seen_ids: dict[str, str]) -> None:
    if not isinstance(record, dict):
        errors.append(f"条目 {key}: 根值必须是对象（PluginRecord）")
        return

    author = record.get("author")
    name = record.get("name")

    # 规则 5/11：根键 = author/name 或 name 兼容例外
    if "/" in key:
        if not _is_nonempty_str(author) or not _is_nonempty_str(name):
            errors.append(f"条目 {key}: plugin_id 键下 author 与 name 均为必填")
        elif key != f"{author}/{name}":
            errors.append(f"条目 {key}: 根键必须等于 author/name（实际为 {author}/{name}）")
    else:
        if not _is_nonempty_str(author):
            errors.append(f"条目 {key}: name 键兼容例外下 author 仍为必填")
        if name is not None and name != key:
            errors.append(f"条目 {key}: name 字段存在时必须等于根键")

    # 规则 7/8：必填字段
    for field in REQUIRED_FIELDS:
        if not _is_nonempty_str(record.get(field)):
            errors.append(f"条目 {key}: 必填字段 {field} 缺失或为空")

    # 规则 9/10：author/name 字符约束
    for field, value in (("author", author), ("name", name)):
        if isinstance(value, str) and value:
            if "/" in value:
                errors.append(f"条目 {key}: {field} 不得包含 \"/\"")
            if CONTROL_RE.search(value):
                errors.append(f"条目 {key}: {field} 不得包含 ASCII 控制字符")

    # 规则 12：大小写归一化唯一性
    if _is_nonempty_str(author) and (_is_nonempty_str(name) or "/" not in key):
        plugin_id = f"{author}/{name if _is_nonempty_str(name) else key}"
        normalized = plugin_id.lower()
        if normalized in seen_ids:
            errors.append(
                f"条目 {key}: plugin_id {plugin_id} 与 {seen_ids[normalized]} "
                f"大小写归一化后重复"
            )
        else:
            seen_ids[normalized] = key

    # 规则 13：repo URL 形态
    repo = record.get("repo")
    if _is_nonempty_str(repo) and not REPO_RE.match(repo):
        errors.append(f"条目 {key}: repo 必须是 HTTPS GitHub 仓库 URL（"
                      f"https://github.com/用户名/仓库名[.git][/tree/分支]）")

    # 规则 14-19、24：可选字段类型
    if "download_url" in record and not _is_https(record.get("download_url")):
        errors.append(f"条目 {key}: download_url 若存在必须是 HTTPS URL")
    for field in ("tags", "platforms"):
        if field in record:
            value = record.get(field)
            if not (isinstance(value, list) and all(isinstance(t, str) for t in value)):
                errors.append(f"条目 {key}: {field} 若存在必须是字符串数组")
            elif field == "platforms":
                invalid = [p for p in value if p not in VALID_PLATFORMS]
                if invalid:
                    errors.append(
                        f"条目 {key}: platforms 取值非法 {invalid}（"
                        f"仅允许 {sorted(VALID_PLATFORMS)}）"
                    )
    for field in ("stars", "download_count"):
        if field in record:
            value = record.get(field)
            if not (_is_int(value) and value >= 0):
                errors.append(f"条目 {key}: {field} 若存在必须是非负整数")
    if "updated_at" in record and not (
        isinstance(record.get("updated_at"), str) and ISO_RE.match(record["updated_at"])
    ):
        errors.append(f"条目 {key}: updated_at 若存在必须是 ISO 8601 时间戳")
    if "host_version" in record and not _is_nonempty_str(record.get("host_version")):
        errors.append(f"条目 {key}: host_version 若存在必须是非空字符串")

    # 规则 23：保留字段
    used_reserved = RESERVED_FIELDS & set(record.keys())
    if used_reserved:
        errors.append(f"条目 {key}: 不得使用保留字段 {sorted(used_reserved)}")


def validate(data, tombstone_ids: set[str] | None = None) -> list[str]:
    """校验 index.json 数据，返回错误列表（空列表即通过）。"""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["根节点必须是 JSON 对象"]

    # 规则 2/3/4 + $meta 可选字段
    if "$meta" not in data:
        errors.append("缺少保留键 $meta")
    else:
        validate_meta(data["$meta"], errors)

    seen_ids: dict[str, str] = {}
    for key, record in data.items():
        if key == "$meta":
            continue
        validate_record(key, record, errors, seen_ids)

    # 规则 25：墓碑检查——已下架插件不得复活
    if tombstone_ids:
        for key in data:
            if key == "$meta":
                continue
            normalized = key.lower()
            if normalized in tombstone_ids:
                errors.append(f"条目 {key}: 已在 del-plugins.json 墓碑中，不得重新上架")

    return errors


def load_tombstone_ids(path: str) -> set[str]:
    """读取 del-plugins.json 的 plugin_id 集合（大小写归一化）。"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, dict):
        return set()
    return {str(k).lower() for k in data.keys()}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("用法: python scripts/validate.py index.json [del-plugins.json]", file=sys.stderr)
        return 2

    index_path = argv[1]
    tombstone_path = argv[2] if len(argv) > 2 else "del-plugins.json"

    try:
        with open(index_path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as ex:
        print(f"无法读取 {index_path}: {ex}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as ex:
        print(f"{index_path} 不是合法 JSON: {ex}", file=sys.stderr)
        return 2

    import os
    if os.path.exists(tombstone_path):
        errors = validate(data, load_tombstone_ids(tombstone_path))
    else:
        errors = validate(data)

    if errors:
        print(f"校验失败，共 {len(errors)} 处错误：")
        for e in errors:
            print(f"  - {e}")
        return 1

    count = sum(1 for k in data if k != "$meta")
    print(f"校验通过：{count} 个插件条目")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
