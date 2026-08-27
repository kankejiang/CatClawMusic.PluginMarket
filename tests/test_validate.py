#!/usr/bin/env python3
"""validate.py 校验规则单元测试（unittest，CI 直接 python -m unittest 运行）。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from validate import validate  # noqa: E402


def make_index(entries: dict, schema_version: int = 1) -> dict:
    return {
        "$meta": {
            "schema_version": schema_version,
            "name": "test market",
            "version": "2026-08-27",
            "repository": "https://github.com/kankejiang/CatClawMusic.PluginMarket",
        },
        **entries,
    }


def make_entry(**overrides) -> dict:
    entry = {
        "author": "CatClawMusic",
        "name": "lrclib",
        "version": "1.2.0",
        "repo": "https://github.com/kankejiang/CatClawMusic.Plugins.Lrclib",
        "desc": "测试插件",
    }
    entry.update(overrides)
    return entry


class MetaRules(unittest.TestCase):
    def test_valid_minimal(self):
        errors = validate(make_index({"CatClawMusic/lrclib": make_entry()}))
        self.assertEqual(errors, [])

    def test_missing_meta(self):
        errors = validate({"CatClawMusic/lrclib": make_entry()})
        self.assertTrue(any("$meta" in e for e in errors))

    def test_wrong_schema_version(self):
        errors = validate(make_index({"CatClawMusic/lrclib": make_entry()}, schema_version=2))
        self.assertTrue(any("schema_version" in e for e in errors))

    def test_meta_homepage_must_be_https(self):
        index = make_index({"CatClawMusic/lrclib": make_entry()})
        index["$meta"]["homepage"] = "http://example.com"
        errors = validate(index)
        self.assertTrue(any("homepage" in e for e in errors))

    def test_root_not_object(self):
        errors = validate([1, 2, 3])
        self.assertEqual(len(errors), 1)


class RecordRules(unittest.TestCase):
    def test_key_must_equal_author_slash_name(self):
        errors = validate(make_index({"CatClawMusic/other": make_entry()}))
        self.assertTrue(any("根键必须等于 author/name" in e for e in errors))

    def test_bare_name_compat_exception(self):
        entry = make_entry()
        del entry["name"]  # name 键下可省略 name
        errors = validate(make_index({"lrclib": entry}))
        self.assertEqual(errors, [])

    def test_bare_name_with_wrong_name_field(self):
        entry = make_entry()
        entry["name"] = "not-lrclib"
        errors = validate(make_index({"lrclib": entry}))
        self.assertTrue(any("name 字段存在时必须等于根键" in e for e in errors))

    def test_missing_required_field(self):
        entry = make_entry()
        del entry["desc"]
        errors = validate(make_index({"CatClawMusic/lrclib": entry}))
        self.assertTrue(any("desc" in e for e in errors))

    def test_empty_required_field(self):
        errors = validate(make_index({"CatClawMusic/lrclib": make_entry(version="   ")}))
        self.assertTrue(any("version" in e for e in errors))

    def test_author_must_not_contain_slash(self):
        errors = validate(make_index({"a/b/lrclib": make_entry(author="a/b")}))
        self.assertTrue(any("不得包含" in e for e in errors))

    def test_case_insensitive_duplicate(self):
        entries = {
            "CatClawMusic/lrclib": make_entry(),
            "catclawmusic/lrclib": make_entry(),
        }
        errors = validate(make_index(entries))
        self.assertTrue(any("重复" in e for e in errors))

    def test_repo_must_be_github_https(self):
        for bad in ("http://github.com/a/b", "git@github.com:a/b.git",
                    "https://gitlab.com/a/b", "https://github.com/a/b/tree/main/x"):
            errors = validate(make_index({"CatClawMusic/lrclib": make_entry(repo=bad)}))
            self.assertTrue(any("repo" in e for e in errors), bad)

    def test_repo_tree_branch_is_valid(self):
        errors = validate(make_index({
            "CatClawMusic/lrclib": make_entry(
                repo="https://github.com/kankejiang/CatClawMusic.Plugins.Lrclib/tree/main")
        }))
        self.assertEqual(errors, [])

    def test_download_url_must_be_https(self):
        errors = validate(make_index({"CatClawMusic/lrclib": make_entry(
            download_url="http://example.com/x.ccp")}))
        self.assertTrue(any("download_url" in e for e in errors))

    def test_platforms_value_restricted(self):
        errors = validate(make_index({"CatClawMusic/lrclib": make_entry(platforms=["ios"])}))
        self.assertTrue(any("platforms" in e for e in errors))

    def test_platforms_valid(self):
        errors = validate(make_index({"CatClawMusic/lrclib": make_entry(
            platforms=["android", "windows"])}))
        self.assertEqual(errors, [])

    def test_stars_must_be_non_negative_int(self):
        for bad in (-1, "5", 1.5, True):
            errors = validate(make_index({"CatClawMusic/lrclib": make_entry(stars=bad)}))
            self.assertTrue(any("stars" in e for e in errors), repr(bad))

    def test_updated_at_iso(self):
        errors = validate(make_index({"CatClawMusic/lrclib": make_entry(
            updated_at="2026-08-27 00:00:00")}))
        self.assertTrue(any("updated_at" in e for e in errors))

    def test_reserved_field_rejected(self):
        errors = validate(make_index({"CatClawMusic/lrclib": make_entry(install_method="git")}))
        self.assertTrue(any("保留字段" in e for e in errors))


class TombstoneRules(unittest.TestCase):
    def test_tombstoned_plugin_cannot_return(self):
        index = make_index({"CatClawMusic/lrclib": make_entry()})
        errors = validate(index, tombstone_ids={"catclawmusic/lrclib"})
        self.assertTrue(any("墓碑" in e for e in errors))

    def test_tombstone_other_plugin_passes(self):
        index = make_index({"CatClawMusic/lrclib": make_entry()})
        errors = validate(index, tombstone_ids={"someone/dead"})
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
