# MoviePilot 自用插件库

这是 Picarse 的 MoviePilot V2 自用插件仓库。

## 自动删种（自用版）

- 插件 ID：`CustomTorrentRemover`
- 源码基础：MoviePilot 官方 `TorrentRemover` v2.3
- 支持：qBittorrent、Transmission
- 动作：暂停、删除种子、删除种子和文件
- 条件：大小、分享率、做种时间、平均上传速度、标签、路径、Tracker、任务状态和分类等
- 空间补充删种：低于目标可用空间时，按做种时间从长到短删除；每轮至少 5 个主种，辅种随主种移除但不计数
- 仅预览：常规处理和空间补充删种均只输出计划，不实际暂停或删除

自用版采用独立插件 ID 和配置前缀，可与官方版同时安装，官方插件升级不会覆盖本插件。

## 站点自动更新（自用版）

- 插件 ID：`CustomSiteRefresh`
- 源码基础：MoviePilot 官方 `SiteRefresh` v1.2
- 功能：站点签到检测到 Cookie 失效时，使用配置的账号模拟登录并更新 Cookie 和 UA
- 配置格式：每行 `域名|用户名|密码`；自动更新使用 2FA 时可在末尾追加固定 Base32 TOTP 密钥
- 手动测试：在插件详情页选择已匹配站点，立即执行一次真实登录测试
- 连通性测试：发送匿名 HEAD 请求，仅检查 DNS、TCP、TLS、站点代理和 HTTP 响应，不使用浏览器、账号或 2FA，也不读取站点已存 Cookie/UA；最长等待 10 秒，避免前端误报重连
- 安全保护：严格域名匹配、同站点并发锁和 60 秒自动触发冷却
- Cloudflare 兼容：仅在站点现有 Cookie 含 `cf_clearance` 时复用旧会话与对应 UA 通过挑战；旧会话有效时不重复提交密码，挑战未通过时也不会提交

自用版采用独立插件 ID 和配置前缀，可与官方版同时安装，方便后续单独检查和修改。
请勿同时启用官方版和自用版站点自动更新插件，否则两者都会响应自动签到事件。

## 腾讯视频探索（自用版）

- 插件 ID：`CustomTencentVideoDiscover`
- 源码基础：[DDSRem-Dev/MoviePilot-Plugins](https://github.com/DDSRem-Dev/MoviePilot-Plugins) 的 `TencentVideoDiscover` v1.0.3
- 功能：向 MoviePilot“探索”注册腾讯视频数据源，支持电视剧、电影、综艺、动漫、少儿和纪录片分类及动态筛选项
- 可靠性：请求超时保护、频道和分页校验、筛选接口失败降级、启用后才加载腾讯筛选项
- 独立性：使用独立插件 ID、配置前缀、API 路径、缓存区域和媒体 ID 前缀

自用版可以与上游插件同时安装，但不建议同时启用，否则探索页会出现两套腾讯视频入口。

## 添加插件库

在 MoviePilot V2 的插件市场设置中添加以下仓库：

```text
https://github.com/Picarse/MoviePilot-Plugins-Custom
```

刷新插件市场后，可搜索“自动删种（自用版）”“站点自动更新（自用版）”或“腾讯视频探索（自用版）”。

## 安全测试建议

1. 首次使用保持默认开启“仅预览”。
2. 选择测试下载器，并先配置较严格的筛选条件。
3. 使用“立即运行一次”，核对日志和被暂停的任务。
4. 确认条件准确后，再关闭“仅预览”，并考虑切换到“删除种子”。
5. 空间补充删种固定删除主种文件；关闭“仅预览”前务必确认候选和辅种关系。
6. “删除种子和文件”会删除实际数据，启用前务必确认筛选结果。

插件默认关闭、默认动作是暂停、默认开启仅预览；安装后不会自动删除任务或文件。

## 来源与许可

本仓库插件基于 [jxxghp/MoviePilot-Plugins](https://github.com/jxxghp/MoviePilot-Plugins) 和 [DDSRem-Dev/MoviePilot-Plugins](https://github.com/DDSRem-Dev/MoviePilot-Plugins) 中对应插件修改，保留原作者信息，并按照 GNU GPL v3 许可证发布。详见 [LICENSE](LICENSE)。
