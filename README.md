# MoviePilot 自用插件库

这是 Picarse 的 MoviePilot V2 自用插件仓库。

## 自动删种（自用版）

- 插件 ID：`CustomTorrentRemover`
- 源码基础：MoviePilot 官方 `TorrentRemover` v2.3
- 支持：qBittorrent、Transmission
- 动作：暂停、删除种子、删除种子和文件
- 条件：大小、分享率、做种时间、平均上传速度、标签、路径、Tracker、任务状态和分类等

自用版采用独立插件 ID 和配置前缀，可与官方版同时安装，官方插件升级不会覆盖本插件。

## 添加插件库

在 MoviePilot V2 的插件市场设置中添加以下仓库：

```text
https://github.com/Picarse/MoviePilot-Plugins-Custom
```

刷新插件市场后，搜索“自动删种（自用版）”。

## 安全测试建议

1. 首次使用保持默认动作“暂停”。
2. 选择测试下载器，并先配置较严格的筛选条件。
3. 使用“立即运行一次”，核对日志和被暂停的任务。
4. 确认条件准确后，再考虑切换到“删除种子”。
5. “删除种子和文件”会删除实际数据，启用前务必确认筛选结果。

插件默认关闭，默认动作是暂停；安装后不会自动删除任务或文件。

## 来源与许可

本插件基于 [jxxghp/MoviePilot-Plugins](https://github.com/jxxghp/MoviePilot-Plugins) 中的 `TorrentRemover` 修改，保留原作者信息，并按照 GNU GPL v3 许可证发布。详见 [LICENSE](LICENSE)。
