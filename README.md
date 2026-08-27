# CatClawMusic.PluginMarket

猫爪音乐（CatClawMusic）官方插件市场，**全 GitHub 托管、零服务器**（架构对照 AstrBot 插件市场）。

本仓库只存插件元数据，不存任何插件本体——插件 `.ccp` 包托管在各作者自己仓库的 Release 中。

## 仓库结构

| 文件 | 作用 | 维护方式 |
|------|------|----------|
| `index.json` | 市场主清单（含 `$meta` 与全部插件条目） | PR 提交静态字段 + 每日 CI 自动补全动态字段 |
| `index.md5.json` | 主清单 MD5 边车（客户端先比哈希，未变不拉全量） | CI 自动生成 |
| `del-plugins.json` | 下架墓碑（客户端据此提示卸载） | PR 提交 |
| `unreachable-plugins.json` | 不可达仓库追踪（死链自动隔离，恢复自动回归） | CI 自动维护 |
| `scripts/validate.py` | 清单校验器（PR 阻断） | 手动 |
| `scripts/sync.py` | GitHub API 同步器（版本/下载直链/sha256/stars） | CI 每日运行 |
| `tests/` | 校验器单元测试 | 手动 |

## 客户端接入端点

| 通道 | URL |
|------|-----|
| 原始（GitHub） | `https://raw.githubusercontent.com/kankejiang/CatClawMusic.PluginMarket/main/index.json` |
| CDN（推荐，国内可达） | `https://cdn.jsdelivr.net/gh/kankejiang/CatClawMusic.PluginMarket@main/index.json` |
| MD5 边车 | 同上路径，把 `index.json` 换成 `index.md5.json` |

## 如何上架插件

1. 把插件源码推送到你自己的 GitHub 仓库，并发布 Release（tag 建议 `v{版本号}`，资产为 `.ccp` 文件）
2. Fork 本仓库
3. 在 `index.json` 中添加条目（根键为 `作者/插件ID`）：

```json
"你的作者名/你的插件ID": {
  "author": "你的作者名",
  "name": "你的插件ID",
  "display_name": "插件显示名称",
  "short_desc": "一句话简介",
  "version": "1.0.0",
  "repo": "https://github.com/你的用户名/你的插件仓库",
  "desc": "详细描述",
  "tags": ["lyrics"],
  "platforms": ["android", "windows"],
  "host_version": ">=1.8.0"
}
```

4. 提交 PR，CI 自动校验，通过后合并即上架生效

### 字段规范（schema 1）

**必填：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `author` | string | 作者命名空间，必须与插件包内 `IPlugin.Author` 一致 |
| `name` | string | 插件 ID，必须与插件包内 `IPlugin.PluginId` 一致 |
| `version` | string | 版本号，必须与插件包内 `IPlugin.Version` 一致 |
| `repo` | string | HTTPS GitHub 仓库地址（`https://github.com/用户名/仓库名`，可带 `.git` 或 `/tree/分支`） |
| `desc` | string | 默认描述 |

**可选：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `display_name` | string | 人类可读名称 |
| `short_desc` | string | 紧凑 UI 用的短描述 |
| `download_url` | string | `.ccp` 直链（缺省时客户端走 `repo` 的 `releases/latest`） |
| `sha256` | string | `.ccp` 包 SHA-256（CI 自动填充） |
| `download_size` | integer | 包体积字节数（CI 自动填充） |
| `tags` | string[] | 标签 |
| `platforms` | string[] | 支持平台，取值限 `android` / `windows` |
| `host_version` | string | 宿主版本范围（如 `>=1.8.0`） |
| `stars` | integer | 星标数（CI 自动填充） |
| `updated_at` | string | ISO 8601 时间戳（CI 自动填充） |
| `pinned` | boolean | 市场推荐位 |

### 身份与安装规则（对照 AstrBot 规范）

- **plugin_id = `author/name`**，全局唯一，大小写归一化后不得与其他条目冲突；`repo` 不得作为身份标识
- 根键必须等于 `author/name`（或仅 `name` 的兼容写法，此时 `name` 字段可省略）
- 安装后宿主回验插件包内的 `Author`/`PluginId`/`Version`，与所选条目不一致即安装失败（防清单篡改）
- `del-plugins.json` 中的插件**永久下架**，同名 plugin_id 不得重新上架（CI 阻断）
- 安装、更新始终按安装时记录的市场源 + plugin_id 解析条目

## 如何下架插件

向 `del-plugins.json` 添加条目并提交 PR：

```json
"作者名/插件ID": {
  "reason": "下架原因",
  "since": "2026-08-27T00:00:00Z"
}
```

## CI 自动同步

`sync.yml` 每日 UTC 02:00 运行：

- 从 GitHub API 拉取每个插件仓库的 stars、最新 Release（版本号、`.ccp` 资产直链、sha256、体积、发布时间）
- 仓库 404 的条目自动移入 `unreachable-plugins.json`（恢复可达后自动移回）
- 重算 `index.md5.json` 边车，有变化才提交

## License

[MIT](LICENSE)
