"""Pure parsing helpers for the custom iQIYI discover plugin."""

import re
from typing import Any, Dict, List, Optional, Tuple


CHANNEL_PARAMS = {
    "tv": {"Id": "2", "Name": "电视剧"},
    "movie": {"Id": "1", "Name": "电影"},
    "variety": {"Id": "6", "Name": "综艺"},
    "anime": {"Id": "4", "Name": "动漫"},
    "children": {"Id": "15", "Name": "少儿"},
}

APP_CHANNEL_PATHS = {
    "tv": "tv",
    "movie": "film",
    "variety": "variety",
    "anime": "cartoon",
    "children": "child",
}

APP_TV_REGION_OPTIONS = (
    ("内地", "内地"), ("中国香港", "中国香港"), ("中国台湾", "中国台湾"),
    ("美国", "美国"), ("韩国", "韩国"), ("泰国", "泰国"), ("英国", "英国"),
)
APP_TV_GENRE_OPTIONS = (
    ("古装", "古装"), ("战争", "战争"), ("谍战", "谍战"),
    ("爱情", "爱情"), ("罪案", "罪案"), ("悬疑", "悬疑"),
    ("家庭", "家庭"), ("都市", "都市"), ("青春", "青春"),
    ("喜剧", "喜剧"), ("军旅", "军旅"), ("奇幻", "奇幻"),
    ("武侠", "武侠"), ("历史", "历史"), ("年代", "年代"),
)
APP_TV_ACCESS_OPTIONS = (
    ("recent_free", "近期转免"), ("free", "免费"),
    ("limited_free", "限免"), ("vip", "VIP"),
)
APP_TV_HALL_OPTIONS = (
    ("honor", "荣誉殿堂"), ("national", "国民殿堂"),
    ("popular", "人气殿堂"), ("quality", "佳片殿堂"),
)
APP_TV_SPECIFICATION_OPTIONS = (
    ("produced", "自制"), ("exclusive", "独播"),
)
APP_TV_SORT_OPTIONS = (
    ("hot", "最热"), ("new", "最新"), ("score", "高分"),
)
APP_TV_THEATER_OPTIONS = (
    ("迷雾剧场", "迷雾剧场"), ("恋恋剧场", "恋恋剧场"),
    ("小逗剧场", "小逗剧场"), ("微尘剧场", "微尘剧场"),
    ("大家剧场", "大家剧场"),
)
APP_TV_AWARD_OPTIONS = (
    ("白玉兰奖", "白玉兰奖"), ("飞天奖", "飞天奖"),
    ("金鹰奖", "金鹰奖"),
)
APP_TV_ACTOR_OPTIONS = (
    ("张凌赫", "张凌赫"), ("黄景瑜", "黄景瑜"),
    ("田曦薇", "田曦薇"), ("白鹿", "白鹿"), ("杨志刚", "杨志刚"),
)
APP_TV_RECOMMEND_OPTIONS = (
    ("douban_high", "豆瓣高分"), ("heat_10000", "热度破10000"),
    ("comments_10000000", "评论破1000万"),
)

APP_SECTION_OPTIONS = {
    "tv": (("all", "全部"), ("banner", "焦点图"), ("hot", "热剧推荐"),
           ("online", "网剧热播"), ("rank_list_1", "热播榜"),
           ("rank_list_2", "飙升榜"), ("rank_list_3", "免费榜"),
           ("rank_list_4", "必看榜"), ("rank_list_5", "期待榜"),
           ("rank_list_6", "高分榜"), ("rank_list_7", "N刷榜")),
    "movie": (("all", "全部"), ("banner", "焦点图"), ("online", "热播电影"),
              ("rank_list_1", "热播榜"), ("rank_list_2", "飙升榜"),
              ("rank_list_3", "免费榜"), ("rank_list_4", "必看榜"),
              ("rank_list_5", "网络票房榜"), ("rank_list_6", "票房榜"),
              ("rank_list_7", "高分榜")),
    "variety": (("all", "全部"), ("banner", "焦点图"), ("hot", "热播综艺"),
                ("waterfall", "更多推荐"), ("rank_list_1", "热播榜"),
                ("rank_list_2", "飙升榜"), ("rank_list_3", "必看榜"),
                ("rank_list_4", "高分榜"), ("rank_list_5", "旅行榜"),
                ("rank_list_6", "访谈榜"), ("rank_list_7", "美食榜")),
    "anime": (("all", "全部"), ("banner", "焦点图"), ("hot", "C位动画"),
              ("schedule", "更新日历"), ("rank_list_1", "热播榜"),
              ("rank_list_2", "飙升榜"), ("rank_list_3", "免费榜"),
              ("rank_list_4", "期待榜"), ("rank_list_5", "日漫榜"),
              ("rank_list_6", "国漫榜"), ("rank_list_7", "必看榜")),
    "children": (("all", "全部"), ("banner", "焦点图"),
                 ("tracing", "为你推荐"), ("mytag_1", "推荐"),
                 ("mytag_2", "搞笑"), ("mytag_3", "动物"),
                 ("mytag_4", "英雄")),
}

def clamp_positive_int(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 1), maximum)


def normalize_url(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("//"):
        return f"https:{text}"
    if text.startswith("http://"):
        return f"https://{text[7:]}"
    return text


def _names(value: Any) -> Tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    names = []
    for entry in value:
        name = entry.get("name") if isinstance(entry, dict) else entry
        name = str(name or "").strip()
        if name:
            names.append(name)
    return tuple(dict.fromkeys(names))


def _integer(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _score(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _app_date(value: Any) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(value, dict):
        return None, None
    try:
        year = int(value.get("year"))
        month = int(value.get("month"))
        day = int(value.get("day"))
    except (TypeError, ValueError):
        return None, None
    if year < 1900 or not 1 <= month <= 12 or not 1 <= day <= 31:
        return None, None
    return str(year), f"{year:04d}-{month:02d}-{day:02d}"


def _app_episode_progress(value: Any) -> Tuple[Optional[int], Optional[int]]:
    text = str(value or "").strip()
    complete = re.search(r"(\d+)集全", text)
    if complete:
        count = _integer(complete.group(1))
        return count, count
    latest = re.search(r"更新至(\d+)集", text)
    return None, _integer(latest.group(1)) if latest else None


def _app_pay_mark(value: Any) -> Optional[int]:
    text = str(value or "").upper()
    if not text:
        return None
    if text == "NONE_MARK":
        return 0
    if "VIP" in text:
        return 1
    if "PAY" in text:
        return 2
    return None


def normalize_app_item(item: Any, expected_channel: str,
                       section_id: str, section_title: str) -> Dict[str, Any]:
    """Normalize one anonymous Mesh/App channel card."""
    if not isinstance(item, dict) or item.get("isAd"):
        return {}
    channel_id = str(item.get("channel_id") or "").strip()
    if channel_id != expected_channel:
        return {}
    media_id = str(item.get("album_id") or item.get("film_id") or "").strip()
    title = str(
        item.get("display_name") or item.get("album_name") or item.get("title") or ""
    ).strip()
    if not media_id or not title:
        return {}
    year, release_date = _app_date(item.get("date"))
    total, latest = _app_episode_progress(item.get("dq_updatestatus"))
    poster = normalize_url(
        item.get("image_url_normal") or item.get("image_cover") or item.get("image_url")
    )
    tags = tuple(dict.fromkeys(
        value.strip() for value in str(item.get("tag") or "").split(";")
        if value.strip()
    ))
    theaters = _app_labels(item.get("theaters"), "title")
    awards = _app_labels(item.get("awards"), "title", "text", "name")
    card_labels = _app_labels(item.get("tag3lines"), "text", "title")
    actors = tuple(dict.fromkeys((
        *_names(item.get("starring")),
        *_names(item.get("contributor")),
        *_names(item.get("actor")),
    )))
    return {
        "media_id": media_id,
        "title": title,
        "channel_id": channel_id,
        "poster": poster,
        "play_url": normalize_url(item.get("page_url") or item.get("play_url")),
        "description": str(item.get("description") or "").strip() or None,
        "focus": str(item.get("desc") or "").strip() or None,
        "year": year,
        "release_date": release_date,
        "categories": tags,
        "areas": (),
        "actors": actors,
        "score": _score(item.get("sns_score")),
        "total_episodes": total,
        "latest_episode": latest,
        "pay_mark": _app_pay_mark(item.get("pay_mark")),
        "update_status": str(item.get("dq_updatestatus") or "").strip() or None,
        "hot_score": _integer(item.get("hot_score")),
        "exclusive": str(item.get("cornerMark") or "").lower() == "exclusive",
        "produced": "自制" in tags,
        "theaters": theaters,
        "awards": awards,
        "card_labels": card_labels,
        "app_sections": (section_id,),
        "app_section_id": section_id,
        "app_section": section_title,
    }


def _app_labels(value: Any, *keys: str) -> Tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    labels = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        label = next((str(entry.get(key) or "").strip() for key in keys
                      if str(entry.get(key) or "").strip()), "")
        if label:
            labels.append(label)
    return tuple(dict.fromkeys(labels))


def _app_section_matches(section: Optional[str], block_id: str) -> bool:
    if not section or section == "all":
        return True
    if section == "schedule":
        return block_id.startswith("jmd_")
    return block_id == section


def extract_app_items(payload: Any, mtype: str,
                      section: Optional[str] = None) -> List[Dict[str, Any]]:
    """Extract and de-duplicate long-form cards from a Mesh/App channel payload."""
    if (not isinstance(payload, dict) or payload.get("code") != 0
            or mtype not in APP_CHANNEL_PATHS):
        return []
    expected_channel = CHANNEL_PARAMS[mtype]["Id"]
    results = []
    indexes = {}
    for group in payload.get("items") or []:
        if not isinstance(group, dict):
            continue
        for block in group.get("video") or []:
            if not isinstance(block, dict):
                continue
            block_id = str(block.get("block_id") or "").strip()
            if not block_id or not _app_section_matches(section, block_id):
                continue
            section_title = str(block.get("title") or "").strip() or block_id
            for raw in block.get("data") or []:
                item = normalize_app_item(raw, expected_channel, block_id, section_title)
                if not item:
                    continue
                index = indexes.get(item["media_id"])
                if index is None:
                    indexes[item["media_id"]] = len(results)
                    results.append(item)
                else:
                    results[index] = merge_app_item(results[index], item)
    return results


def merge_app_item(current: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """Merge duplicate channel cards without discarding richer waterfall labels."""
    merged = dict(current)
    for key in (
        "categories", "areas", "actors", "theaters", "awards", "card_labels",
        "app_sections",
    ):
        merged[key] = tuple(dict.fromkeys(
            (*current.get(key, ()), *incoming.get(key, ()))
        ))
    for key in ("exclusive", "produced"):
        merged[key] = bool(current.get(key) or incoming.get(key))
    for key in ("hot_score", "score"):
        values = [value for value in (current.get(key), incoming.get(key)) if value is not None]
        merged[key] = max(values) if values else None
    for key, value in incoming.items():
        if merged.get(key) in (None, "", (), []):
            merged[key] = value
    return merged


def _app_year_matches(item: Dict[str, Any], year: Optional[str]) -> bool:
    if not year:
        return True
    if year == "upcoming":
        return "即将上线" in str(item.get("update_status") or "")
    return str(item.get("year") or "") == year


def _app_award_matches(item: Dict[str, Any], award: Optional[str]) -> bool:
    if not award:
        return True
    labels = (*item.get("awards", ()), *item.get("card_labels", ()))
    return any(award in label for label in labels if "奖" in label)


def _app_hall_matches(item: Dict[str, Any], hall: Optional[str]) -> bool:
    if not hall:
        return True
    if hall == "honor":
        return bool(item.get("awards")) or any(
            "奖" in label for label in item.get("card_labels", ())
        )
    section = {
        "national": "rank_list_7",
        "popular": "rank_list_1",
        "quality": "rank_list_6",
    }.get(hall)
    return bool(section and section in item.get("app_sections", ()))


def _app_access_matches(item: Dict[str, Any], access: Optional[str]) -> bool:
    if not access:
        return True
    labels = item.get("card_labels", ())
    if access == "recent_free":
        return any("转免" in label for label in labels)
    if access == "limited_free":
        return any("限免" in label for label in labels)
    if access == "free":
        return item.get("pay_mark") == 0
    if access == "vip":
        return item.get("pay_mark") == 1
    return False


def _app_recommendation_matches(item: Dict[str, Any], recommendation: Optional[str]) -> bool:
    if not recommendation:
        return True
    labels = item.get("card_labels", ())
    if recommendation == "douban_high":
        return any("豆瓣高分" in label for label in labels)
    if recommendation == "heat_10000":
        return any(re.search(r"热度破(?:10000|1万|万)", label) for label in labels)
    if recommendation == "comments_10000000":
        return any(re.search(r"评论(?:数)?破(?:1000万|千万)", label) for label in labels)
    return False


def filter_app_tv_items(items: List[Dict[str, Any]],
                        region: Optional[str] = None,
                        genre: Optional[str] = None,
                        year: Optional[str] = None,
                        access: Optional[str] = None,
                        hall: Optional[str] = None,
                        specification: Optional[str] = None,
                        theater: Optional[str] = None,
                        award: Optional[str] = None,
                        actor: Optional[str] = None,
                        recommendation: Optional[str] = None,
                        mode: Optional[str] = None) -> List[Dict[str, Any]]:
    """Apply iQIYI card metadata filters used by the TV App-style catalog."""
    filtered = []
    for item in items:
        tags = item.get("categories", ())
        labels = item.get("card_labels", ())
        if region and region not in tags:
            continue
        if genre and genre not in tags:
            continue
        if not _app_year_matches(item, year):
            continue
        if not _app_access_matches(item, access):
            continue
        if not _app_hall_matches(item, hall):
            continue
        if specification == "exclusive" and not item.get("exclusive"):
            continue
        if specification == "produced" and not item.get("produced"):
            continue
        if theater and theater not in item.get("theaters", ()) and theater not in labels:
            continue
        if not _app_award_matches(item, award):
            continue
        if actor and actor not in item.get("actors", ()):
            continue
        if not _app_recommendation_matches(item, recommendation):
            continue
        filtered.append(item)
    if mode == "hot":
        filtered.sort(key=lambda item: item.get("hot_score") or 0, reverse=True)
    elif mode == "new":
        filtered.sort(key=lambda item: item.get("release_date") or "", reverse=True)
    elif mode == "score":
        filtered.sort(key=lambda item: item.get("score") or 0, reverse=True)
    return filtered


def media_overview(item: Dict[str, Any], mtype: str) -> Optional[str]:
    parts = []
    if item.get("app_section"):
        parts.append(f"App频道：{item['app_section']}")
    total = item.get("total_episodes")
    latest = item.get("latest_episode")
    if mtype in {"tv", "anime", "children"}:
        if total and latest:
            parts.append(f"共{total}集" if latest == total else f"更新至{latest}/共{total}集")
        elif latest:
            parts.append(f"更新至{latest}集")
        elif total:
            parts.append(f"共{total}集")
    elif mtype == "variety" and item.get("release_date"):
        parts.append(f"更新日期：{item['release_date']}")
    update_status = str(item.get("update_status") or "").strip()
    if update_status and not any(update_status in part for part in parts):
        parts.append(update_status)
    if item.get("hot_score"):
        parts.append(f"热度：{item['hot_score']}")
    labels = [*item.get("areas", ()), *item.get("categories", ())]
    labels = list(dict.fromkeys(labels))[:8]
    if labels:
        parts.append("分类：" + " · ".join(labels))
    rights = []
    if item.get("produced"):
        rights.append("爱奇艺自制")
    if item.get("exclusive"):
        rights.append("独播")
    if item.get("pay_mark") == 1:
        rights.append("VIP")
    elif item.get("pay_mark") == 2:
        rights.append("付费")
    elif item.get("pay_mark") == 0:
        rights.append("免费")
    if rights:
        parts.append("权益：" + " · ".join(rights))
    actors = item.get("actors", ())
    if actors:
        parts.append("主演：" + "、".join(actors[:6]))
    for value in (item.get("focus"), item.get("description")):
        text = str(value or "").strip()
        if text and text not in parts:
            parts.append(text)
    return "\n".join(parts) or None
