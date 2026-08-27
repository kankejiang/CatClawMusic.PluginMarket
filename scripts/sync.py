#!/usr/bin/env python3
"""CatClawMusic 插件市场同步器：从 GitHub API 补全动态字段，重生成 md5 边车。

对照 AstrBot_Plugins_Collection 的 CI 行为，全 GitHub 托管、零服务器：
  1. 拉取各插件仓库元信息（stars、pushed_at）
  2. 拉取最新 Release（版本号、发布时间、.ccp 资产直链 + sha256 + 体积）
  3. 仓库 404 → 移入 unreachable-plugins.json（恢复可达后自动移回）
  4. 重写 index.json（内容无变化时不落盘，保持 git diff 干净）
  5. 生成 index.md5.json 边车（客户端先比哈希再决定是否拉全量清单）

由 .github/workflows/sync.yml 每日定时触发，变更时由工作流提交推送。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

INDEX_PATH = "index.json"
MD5_PATH = "index.md5.json"
UNREACHABLE_PATH = "unreachable-plugins.json"
REPO_RE = re.compile(
    r"^https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+?)(?:\.git|/tree/[A-Za-z0-9_.-]+)?$"
)
UA = "CatClawMusic-PluginMarket-Sync"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _write_json_if_changed(path: str, data, changes: list[str]) -> bool:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return True


def _http_json(url: str, token: str | None):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json",
                                               "User-Agent": UA})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_bytes(url: str, token: str | None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def _pick_ccp_asset(assets: list[dict], repo_name: str) -> dict | None:
    ccp_assets = [a for a in assets if str(a.get("name", "")).endswith(".ccp")]
    if not ccp_assets:
        return None
    # 优先与仓库同名的资产，否则取第一个
    return next((a for a in ccp_assets if a.get("name") == f"{repo_name}.ccp"), ccp_assets[0])


def sync() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    data = _read_json(INDEX_PATH, None)
    if not isinstance(data, dict):
        print(f"{INDEX_PATH} 缺失或不是对象，中止", file=sys.stderr)
        return 1

    unreachable: dict = _read_json(UNREACHABLE_PATH, {})
    if not isinstance(unreachable, dict):
        unreachable = {}
    unreachable_changed = False
    now = _now_iso()

    for key, record in data.items():
        if key == "$meta" or not isinstance(record, dict):
            continue
        match = REPO_RE.match(str(record.get("repo", "")))
        if not match:
            print(f"warn: {key} repo URL 无法解析，跳过")
            continue
        owner, repo_name = match.group(1), match.group(2)

        # 1. 仓库存活检查（404 → 移入不可达名单；恢复 → 自动移回）
        try:
            info = _http_json(f"https://api.github.com/repos/{owner}/{repo_name}", token)
        except urllib.error.HTTPError as ex:
            if ex.code == 404:
                if key not in unreachable:
                    unreachable[key] = {"repo": record["repo"],
                                        "reason": "仓库不存在或已删除（404）",
                                        "since": now}
                    unreachable_changed = True
                    print(f"info: {key} 仓库 404，移入 unreachable-plugins.json")
                else:
                    print(f"info: {key} 仍在不可达名单中，跳过")
            else:
                print(f"warn: {key} 仓库信息请求失败 HTTP {ex.code}")
            continue
        except (urllib.error.URLError, TimeoutError) as ex:
            print(f"warn: {key} 仓库信息请求失败: {ex}")
            continue
        if key in unreachable:
            del unreachable[key]
            unreachable_changed = True
            print(f"info: {key} 仓库恢复可达，移出 unreachable-plugins.json")

        if isinstance(info.get("stargazers_count"), int):
            record["stars"] = info["stargazers_count"]

        # 2. 最新 Release：版本号 + .ccp 资产直链 + sha256 + 体积
        try:
            release = _http_json(
                f"https://api.github.com/repos/{owner}/{repo_name}/releases/latest", token)
        except urllib.error.HTTPError as ex:
            if ex.code == 404:
                print(f"warn: {key} 尚无 Release，保留提交时版本 {record.get('version')}")
            else:
                print(f"warn: {key} Release 请求失败 HTTP {ex.code}")
            continue
        except (urllib.error.URLError, TimeoutError) as ex:
            print(f"warn: {key} Release 请求失败: {ex}")
            continue

        tag = str(release.get("tag_name") or "").lstrip("vV")
        if tag:
            record["version"] = tag
        if release.get("published_at"):
            record["updated_at"] = release["published_at"]

        asset = _pick_ccp_asset(release.get("assets") or [], repo_name)
        if asset:
            record["download_url"] = asset["browser_download_url"]
            try:
                blob = _http_bytes(asset["browser_download_url"], token)
                record["sha256"] = hashlib.sha256(blob).hexdigest()
                record["download_size"] = len(blob)
            except (urllib.error.URLError, TimeoutError) as ex:
                print(f"warn: {key} 资产下载失败（跳过 sha256）: {ex}")

    # 3. 落盘（内容无变化时不写）
    index_changed = _write_json_if_changed(INDEX_PATH, data, [])
    if index_changed:
        data["$meta"]["updated_at"] = now
        _write_json_if_changed(INDEX_PATH, data, [])
    if unreachable_changed:
        _write_json_if_changed(UNREACHABLE_PATH, unreachable, [])

    # 4. md5 边车：始终基于最终 index.json 内容重新计算
    with open(INDEX_PATH, "rb") as f:
        blob = f.read()
    sidecar = {"md5": hashlib.md5(blob).hexdigest(),
               "size": len(blob),
               "generated_at": now}
    md5_changed = _write_json_if_changed(MD5_PATH, sidecar, [])

    print(f"index.json {'已更新' if index_changed else '无变化'}，"
          f"index.md5.json {'已更新' if md5_changed else '无变化'}")
    # 变更与否交给工作流用 git diff 判断；脚本本身始终成功
    return 0


if __name__ == "__main__":
    sys.exit(sync())
