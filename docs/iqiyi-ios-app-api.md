# 爱奇艺 iOS App 公开频道接口研究

验证日期：2026-07-23。研究用途是为 `CustomIqiyiVideoDiscover` 提供公开、匿名的视频目录数据，不涉及登录态、动态签名、证书锁定绕过、DRM、播放地址解密或会员权限绕过。

## 已验证域名

| 域名 | 用途 | 插件是否使用 |
| --- | --- | --- |
| `mesh.if.iqiyi.com` | App/网页共享的频道首页聚合数据 | 是，可选 App 频道来源 |
| `pcw-api.iqiyi.com` | 匿名分类目录与节目详情 | 是，默认来源 |
| `pic0.iqiyipic.com` 至 `pic9.iqiyipic.com` | 海报、横图及频道素材 | 是，仅加载节目海报 |
| `www.iqiyi.com`、`pages.iqiyi.com` | 返回数据中的官方节目页面 | 仅作为字段保留，不抓取播放流 |

接口响应里还包含 `qips://` App 内部跳转串。插件不解析该串，也不把它用于播放鉴权。

## Mesh 频道接口

基础路径：

```text
GET https://mesh.if.iqiyi.com/portal/lw/v7/channel/{channel}
```

当前已验证的频道映射：

| 插件频道 | `{channel}` | 响应频道名 | 首屏响应规模（验证时） |
| --- | --- | --- | ---: |
| 电视剧 | `tv` | `电视剧-v7` | 约 2.4 MB，去重约 404 个节目 |
| 电影 | `film` | `电影-v7` | 约 0.67 MB，去重约 137 个节目 |
| 综艺 | `variety` | `综艺-v7` | 约 0.79 MB，去重约 140 个节目 |
| 动漫 | `cartoon` | `动漫-v7` | 约 1.24 MB，去重约 253 个节目 |
| 少儿 | `child` | `少儿-v7` | 约 0.26 MB，去重约 69 个节目 |

响应顶层状态为 `code: 0`。节目位于 `items[].video[].data[]`，模块由 `block_id`、`title` 和 `card_source` 描述。验证到的模块包括：

- `banner`：焦点图；
- `hot`、`online`、`tracing`、`waterfall`：频道推荐或瀑布流；
- `jmd_Mon` 至 `jmd_Sun`：动漫更新日历；
- `rank_list_1` 至 `rank_list_7`：频道榜单；
- `mytag_1` 至 `mytag_4`：少儿分类推荐。

主要节目字段：

| 字段 | 含义/处理 |
| --- | --- |
| `album_id` | 电视剧、综艺、动漫、少儿的节目 ID |
| `film_id` | 电影节目 ID；电影频道不能假定存在 `album_id` |
| `channel_id` | 用于排除跨频道推广卡片 |
| `display_name`、`album_name`、`title` | 依次选择节目标题，避免把单集标题当作节目名 |
| `image_url_normal`、`image_cover` | 优先选择现成竖版海报，不猜测不存在的 CDN 尺寸 |
| `description`、`desc` | 节目简介和模块文案 |
| `date`、`showDate` | 上线日期 |
| `dq_updatestatus` | `更新至 N 集`、`N 集全` 或综艺期数状态 |
| `sns_score`、`hot_score` | 评分和频道热度 |
| `pay_mark` | 免费、VIP 或付费标记 |
| `page_url` | 爱奇艺官方节目页面 |

请求在无 Cookie、无设备 ID、无时间戳和无签名时可用；普通 Safari UA、标有 App `17.7.2` 的 UA 以及不主动设置 UA 均验证返回 `code: 0`。响应的部分 `pingback.rpage` 值带有 `pcw` 标记，说明 Mesh 服务至少与网页频道共享，不能仅凭域名把它认定为 iOS 独占接口。插件发送明确的 iOS App 研究 UA，但不依赖固定凭据或 App 专属鉴权。

## 分页与限制

`?page=2` 会返回后续频道数据；`page_id`、`pg_num`、`channel_id` 和仅声明版本号不会产生相同分页效果。插件当前缓存完整首屏频道响应 30 分钟，再按 MoviePilot 请求的页码本地切片。这样可以稳定展示模块榜单并避免每次翻页重复下载大响应。

以下路径验证为 404，不能当作可用频道：数字频道 ID，以及 `movie`、`anime`、`children`、`documentary` 等直译名称。`knowledge` 返回的是“知识-v7-PCW”，不是纪录片频道，插件没有把它错误映射为纪录片。

Mesh 是频道首页聚合接口，不提供 PC Web 分类目录那套地区、题材和年份筛选。插件因此保留两种独立来源：

- “分类目录”继续负责六频道、地区、题材、年份和资费筛选；
- “App频道”负责五频道焦点、推荐、更新日历和榜单浏览。

接口属于爱奇艺可随时调整的公开服务。代码会校验 HTTP 状态、顶层 `code`、频道 ID、节目 ID 和标题；异常时返回空结果，不跨频道回退或伪造内容。
