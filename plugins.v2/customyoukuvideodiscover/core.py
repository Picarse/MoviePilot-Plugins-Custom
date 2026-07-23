import json
import re
from typing import Any, Dict, Iterable, List, Optional


CHANNEL_PARAMS = {
    "tv": {"Path": "webtv", "Name": "电视剧", "Node": "WEBTV"},
    "movie": {"Path": "webmovie", "Name": "电影", "Node": "WEBMOVIE"},
    "variety": {"Path": "webvariety", "Name": "综艺", "Node": "WEBVARIETY"},
    "anime": {"Path": "webcomic", "Name": "动漫", "Node": "WEBCOMIC"},
    "children": {
        "Path": "webchild",
        "Name": "少儿",
        "Node": "WEBCHILD",
        "Api": "mtop.youku.huluwa.dispatcher.columbus.query",
        "Code": "2019101800",
    },
    "documentary": {
        "Path": "webdocumentary",
        "Name": "纪录片",
        "Node": "WEBDOCUMENTARY",
    },
}

GENRE_OPTIONS = {
    "tv": (
        "爱情", "古装", "剧情", "悬疑", "喜剧", "都市",
        "农村", "校园", "青春", "历史", "战争", "罪案",
        "奇幻", "谍战", "情感", "刑侦", "武侠", "家庭",
    ),
    "movie": (
        "剧情", "喜剧", "动作", "犯罪", "冒险", "战争",
        "历史", "爱情", "科幻", "悬疑", "动画", "奇幻",
        "家庭", "魔幻", "运动", "警匪", "惊悚", "恐怖",
    ),
    "variety": (
        "真人秀", "游戏", "舞蹈", "音乐", "竞技",
        "喜剧", "脱口秀", "情感", "文化", "旅游",
        "相声", "晚会", "明星访谈",
    ),
    "anime": (
        "玄幻", "热血", "古风", "推理", "都市",
        "校园", "搞笑", "格斗", "冒险", "恋爱",
        "剧情", "青春", "新国风", "神魔", "运动", "轻松",
    ),
    "children": (
        "动画", "冒险", "亲子", "益智", "幽默",
        "启蒙教育", "友情", "课程辅导", "神话传说", "推理",
        "科普", "动画电影", "玩具", "安全教育", "思维逻辑",
    ),
    "documentary": (
        "自然", "历史", "人物", "文化", "美食",
        "探险", "竞技", "旅游", "知识",
    ),
}

SECTION_OPTIONS = (
    ("banner", "轮播精选"),
    ("hot", "热播推荐"),
    ("upcoming", "即将上线"),
    ("ranking", "热度榜单"),
    ("feed", "更多推荐"),
)

INITIAL_DATA_MARKER = "window.__INITIAL_DATA__ ="
DEFAULT_POSTER = (
    "https://img.alicdn.com/imgextra/i2/"
    "O1CN01BeAcgL1ywY0G5nSn8_!!6000000006643-2-tps-195-195.png"
)


def clamp_positive_int(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 1), maximum)


def parse_initial_data(html: Any) -> Dict[str, Any]:
    """Parse Youku's server-rendered channel data without executing scripts."""
    if not isinstance(html, str):
        return {}
    marker_index = html.find(INITIAL_DATA_MARKER)
    if marker_index < 0:
        return {}
    start = marker_index + len(INITIAL_DATA_MARKER)
    end = html.find("</script>", start)
    if end < 0:
        return {}
    source = html[start:end].strip().rstrip(";")
    source = re.sub(
        r"([:,\[])\s*undefined(?=\s*[,}\]])",
        r"\1null",
        source,
    )
    try:
        payload = json.loads(source)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _component_items(module: Any) -> Iterable[tuple]:
    if not isinstance(module, dict):
        return
    for component in module.get("components") or []:
        if not isinstance(component, dict):
            continue
        if "SHORT_VIDEO" in str(component.get("typeName") or ""):
            continue
        component_data = (
            component.get("data") if isinstance(component.get("data"), dict) else {}
        )
        module_title = str(
            component.get("title") or component_data.get("title") or ""
        ).strip()
        type_name = str(component.get("typeName") or module.get("typeName") or "")
        for item in component.get("itemList") or []:
            if isinstance(item, dict):
                yield item, type_name, module_title


def _section(type_name: str, title: str = "") -> str:
    value = f"{type_name} {title}".upper()
    if "LUNBO" in value or "SWIPER" in value:
        return "banner"
    if "BILLBOARD" in value or "榜" in title:
        return "ranking"
    if "RESERVE" in value or "即将" in title:
        return "upcoming"
    if "V_SCROLL" in value and "FEED" not in value:
        return "hot"
    return "feed"


def normalize_poster_url(value: Any) -> str:
    poster = str(value or "").strip()
    if poster.startswith("//"):
        poster = f"https:{poster}"
    elif poster.startswith("http://"):
        poster = f"https://{poster[7:]}"
    if not poster.startswith("https://"):
        return DEFAULT_POSTER
    return poster


def _media_id(item: Dict[str, Any]) -> str:
    action = item.get("action") if isinstance(item.get("action"), dict) else {}
    track_show = (
        item.get("trackShow") if isinstance(item.get("trackShow"), dict) else {}
    )
    for candidate in (
        item.get("action_value"),
        action.get("value"),
        track_show.get("id"),
        item.get("id"),
    ):
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _year(item: Dict[str, Any]) -> Optional[str]:
    for key in ("year", "releaseYear", "publishYear"):
        value = str(item.get(key) or "").strip()
        if re.fullmatch(r"(?:19|20)\d{2}", value):
            return value
    return None


def _tag_values(item: Dict[str, Any]) -> tuple:
    tags = []
    genres = []
    for tag in item.get("tags") or []:
        if not isinstance(tag, dict):
            continue
        text = tag.get("text") if isinstance(tag.get("text"), dict) else {}
        title = str(text.get("title") or "").strip()
        if not title:
            continue
        tags.append(title)
        if tag.get("uiType") == 2:
            genres.extend(
                part.strip()
                for part in re.split(r"\s*[·/]\s*", title)
                if part.strip()
            )
    return tuple(dict.fromkeys(tags)), tuple(dict.fromkeys(genres))


def _media_item(
    item: Dict[str, Any],
    section: str = "feed",
    module_title: str = "",
) -> Optional[Dict[str, Any]]:
    if item.get("isYkAd") or item.get("ad_flag") or item.get("rawAdData"):
        return None
    action = item.get("action") if isinstance(item.get("action"), dict) else {}
    action_type = str(item.get("action_type") or action.get("type") or "")
    if action_type and action_type not in {"JUMP_TO_SHOW", "JUMP_TO_VIDEO"}:
        return None
    if item.get("shortShow") is True:
        return None
    title = str(item.get("title") or "").strip()
    media_id = _media_id(item)
    if not title or not media_id:
        return None
    tags, genres = _tag_values(item)
    return {
        "title": title,
        "year": _year(item),
        "media_id": media_id,
        "poster": normalize_poster_url(item.get("img") or item.get("hImg")),
        "tags": tags,
        "genres": genres,
        "section": section,
        "module_title": module_title,
    }


def extract_media_items(payload: Any) -> List[Dict[str, Any]]:
    """Extract unique long-form media cards from every SSR module."""
    if not isinstance(payload, dict):
        return []
    modules = payload.get("moduleList")
    if not isinstance(modules, list):
        return []
    results = []
    seen = set()
    for module in modules:
        for item, type_name, module_title in _component_items(module):
            media = _media_item(
                item,
                section=_section(type_name, module_title),
                module_title=module_title,
            )
            if not media or media["media_id"] in seen:
                continue
            seen.add(media["media_id"])
            results.append(media)
    return results


def extract_feed_state(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "items": [], "session": {}, "more": False,
            "feed_page": 1, "page_num_max": 1,
        }
    page_map = payload.get("pageMap")
    page_map = page_map if isinstance(page_map, dict) else {}
    session = page_map.get("feedSession")
    return {
        "items": extract_media_items(payload),
        "session": session if isinstance(session, dict) else {},
        "more": bool(page_map.get("feedHasMore")),
        "feed_page": clamp_positive_int(page_map.get("feedPageNo"), 1, 1000),
        "page_num_max": clamp_positive_int(page_map.get("pageNumMax"), 1, 1000),
    }


def extract_mtop_state(payload: Any, code: str) -> Dict[str, Any]:
    """Extract cards and the continuation cursor from a Columbus response."""
    empty = {"items": [], "session": {}, "more": False}
    if not isinstance(payload, dict):
        return empty
    data = payload.get("data")
    block = data.get(code) if isinstance(data, dict) else None
    if not isinstance(block, dict) or block.get("success") is not True:
        return empty
    results = []
    seen = set()

    def visit(value: Any, section: str = "feed", module_title: str = ""):
        if isinstance(value, dict):
            node_data = value.get("data")
            node_data = node_data if isinstance(node_data, dict) else {}
            children = value.get("nodes") or []
            type_name = str(value.get("typeName") or "")
            next_title = module_title
            if children:
                next_title = str(node_data.get("title") or module_title or "").strip()
            next_section = _section(type_name, next_title) if children else section
            if isinstance(node_data, dict):
                media = _media_item(
                    node_data,
                    section=section,
                    module_title=module_title,
                )
                if media and media["media_id"] not in seen:
                    seen.add(media["media_id"])
                    results.append(media)
            for child in children:
                visit(child, next_section, next_title)
        elif isinstance(value, list):
            for child in value:
                visit(child, section, module_title)

    root = block.get("data")
    visit(root)
    root = root if isinstance(root, dict) else {}
    root_data = root.get("data")
    root_data = root_data if isinstance(root_data, dict) else {}
    session = root_data.get("session")
    return {
        "items": results,
        "session": session if isinstance(session, dict) else {},
        "more": bool(root.get("more")),
    }


def extract_mtop_items(payload: Any, code: str) -> List[Dict[str, Any]]:
    """Compatibility wrapper returning only cards from a Columbus response."""
    return extract_mtop_state(payload, code)["items"]


def filter_media_items(
    items: Iterable[Dict[str, Any]],
    genre: Optional[str] = None,
    access: Optional[str] = None,
    progress: Optional[str] = None,
    section: Optional[str] = None,
) -> List[Dict[str, Any]]:
    results = []
    access_tag = {
        "vip": "VIP",
        "exclusive": "独播",
        "premiere": "首播",
    }.get(access)
    for item in items:
        tags = tuple(item.get("tags") or ())
        genres = tuple(item.get("genres") or ())
        if genre and genre not in genres:
            continue
        if section and item.get("section") != section:
            continue
        if access_tag and access_tag not in tags:
            continue
        if progress == "complete" and not any(
            re.search(r"(?:集|期|话)全$", tag) for tag in tags
        ):
            continue
        if progress == "updating" and not any(
            tag.startswith("更新至") for tag in tags
        ):
            continue
        results.append(item)
    return results


def page_items(
    items: Iterable[Dict[str, Any]], page: int, count: int
) -> List[Dict[str, Any]]:
    values = list(items)
    start = (page - 1) * count
    return values[start:start + count]
