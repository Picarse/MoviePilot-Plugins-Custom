"""iQIYI Video Discover custom edition for MoviePilot V2."""

import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from app import schemas
from app.core.cache import cached
from app.core.config import settings
from app.core.event import Event, eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import DiscoverSourceEventData
from app.schemas.types import ChainEventType

from .core import (
    APP_CHANNEL_PATHS,
    APP_SECTION_OPTIONS,
    APP_TV_ACCESS_OPTIONS,
    APP_TV_ACTOR_OPTIONS,
    APP_TV_AWARD_OPTIONS,
    APP_TV_GENRE_OPTIONS,
    APP_TV_HALL_OPTIONS,
    APP_TV_RECOMMEND_OPTIONS,
    APP_TV_REGION_OPTIONS,
    APP_TV_SORT_OPTIONS,
    APP_TV_SPECIFICATION_OPTIONS,
    APP_TV_THEATER_OPTIONS,
    CHANNEL_PARAMS,
    clamp_positive_int,
    extract_app_items,
    filter_app_tv_items,
    media_overview,
    merge_app_item,
)


APP_CHANNEL_API = "https://mesh.if.iqiyi.com/portal/lw/v7/channel/{channel}"
API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) "
        "AppleWebKit/605.1.15 Mobile/15E148 iqiyi/17.7.2"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.iqiyi.com/",
}
REQUEST_TIMEOUT = 15
MAX_PAGE_SIZE = 48
IMAGE_DOMAINS = ("iqiyipic.com", *(f"pic{index}.iqiyipic.com" for index in range(10)))


class CustomIqiyiVideoDiscover(_PluginBase):
    plugin_name = "爱奇艺视频探索（自用版）"
    plugin_desc = "让探索支持爱奇艺视频的数据浏览。"
    plugin_icon = "https://www.iqiyi.com/favicon.ico"
    plugin_version = "1.5.0"
    plugin_author = "Picarse"
    author_url = "https://github.com/Picarse"
    plugin_config_prefix = "customiqiyivideodiscover_"
    plugin_order = 99
    auth_level = 1

    _enabled = False
    def init_plugin(self, config: dict = None):
        config = config or {}
        self._enabled = bool(config.get("enabled"))
        for domain in IMAGE_DOMAINS:
            if domain not in settings.SECURITY_IMAGE_DOMAINS:
                settings.SECURITY_IMAGE_DOMAINS.append(domain)

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [{
            "path": "/iqiyivideo_discover",
            "endpoint": self.iqiyivideo_discover,
            "methods": ["GET"],
            "summary": "爱奇艺视频探索数据源（自用版）",
            "description": "获取爱奇艺视频探索数据",
        }]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [{
            "component": "VForm",
            "content": [{
                "component": "VRow",
                "content": [{
                    "component": "VCol", "props": {"cols": 12, "md": 4},
                    "content": [{"component": "VSwitch", "props": {
                        "model": "enabled", "label": "启用插件"}}],
                }],
            }],
        }], {"enabled": False}

    @staticmethod
    def get_page() -> List[dict]:
        return []

    @staticmethod
    def _fetch_app_payload(mtype: str, page: int = 1) -> Optional[Dict[str, Any]]:
        channel = APP_CHANNEL_PATHS.get(mtype)
        if not channel:
            return None
        try:
            response = requests.get(
                APP_CHANNEL_API.format(channel=channel),
                params={"page": page} if page > 1 else None,
                headers=API_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("code") != 0:
                raise ValueError("unexpected iQIYI App response status")
            return payload
        except (requests.RequestException, TypeError, ValueError) as error:
            logger.warning(
                f"爱奇艺 App 频道请求失败：频道={mtype}，页码={page}，"
                f"错误类型={type(error).__name__}"
            )
            return None

    @cached(region="custom_iqiyivideo_app_channel", ttl=1800, skip_none=True)
    def _request_app_payload(self, mtype: str, page: int = 1) -> Optional[Dict[str, Any]]:
        return self._fetch_app_payload(mtype, page)

    def iqiyivideo_discover(self, mtype: str = "tv",
                            section: Optional[str] = None, mode: Optional[str] = None,
                            year: Optional[str] = None, access: Optional[str] = None,
                            region: Optional[str] = None, genre: Optional[str] = None,
                            specification: Optional[str] = None,
                            hall: Optional[str] = None,
                            theater: Optional[str] = None,
                            award: Optional[str] = None,
                            actor: Optional[str] = None,
                            recommendation: Optional[str] = None,
                            page: int = 1, count: int = 10) -> List[schemas.MediaInfo]:
        if not self._enabled or mtype not in APP_CHANNEL_PATHS:
            return []
        page = clamp_positive_int(page, 1, 1000)
        count = clamp_positive_int(count, 10, MAX_PAGE_SIZE)
        allowed_sections = {value for value, _label in APP_SECTION_OPTIONS[mtype]}
        selected_section = section if section in allowed_sections else "all"
        items = []
        indexes = {}
        app_pages = (1, 2) if mtype == "tv" else (1,)
        for app_page in app_pages:
            for item in extract_app_items(
                self._request_app_payload(mtype, app_page), mtype, selected_section
            ):
                index = indexes.get(item["media_id"])
                if index is None:
                    indexes[item["media_id"]] = len(items)
                    items.append(item)
                else:
                    items[index] = merge_app_item(items[index], item)
        if mtype == "tv":
            allowed_app = {
                "region": {value for value, _label in APP_TV_REGION_OPTIONS},
                "genre": {value for value, _label in APP_TV_GENRE_OPTIONS},
                "access": {value for value, _label in APP_TV_ACCESS_OPTIONS},
                "hall": {value for value, _label in APP_TV_HALL_OPTIONS},
                "specification": {
                    value for value, _label in APP_TV_SPECIFICATION_OPTIONS
                },
                "mode": {value for value, _label in APP_TV_SORT_OPTIONS},
                "theater": {value for value, _label in APP_TV_THEATER_OPTIONS},
                "award": {value for value, _label in APP_TV_AWARD_OPTIONS},
                "actor": {value for value, _label in APP_TV_ACTOR_OPTIONS},
                "recommendation": {
                    value for value, _label in APP_TV_RECOMMEND_OPTIONS
                },
            }
            selected = {
                name: value if value in allowed_app[name] else None
                for name, value in {
                    "region": region, "genre": genre, "access": access,
                    "hall": hall, "specification": specification,
                    "mode": mode, "theater": theater, "award": award,
                    "actor": actor, "recommendation": recommendation,
                }.items()
            }
            selected_year = year if year == "upcoming" or str(year or "").isdigit() else None
            items = filter_app_tv_items(items, year=selected_year, **selected)
        start = (page - 1) * count
        items = items[start:start + count]
        media_type = "电影" if mtype == "movie" else "电视剧"
        return [schemas.MediaInfo(
            type=media_type,
            title=item["title"],
            year=item.get("year"),
            title_year=(f"{item['title']} ({item['year']})" if item.get("year") else item["title"]),
            mediaid_prefix="customiqiyivideo",
            media_id=item["media_id"],
            poster_path=item.get("poster"),
            overview=media_overview(item, mtype),
            release_date=item.get("release_date"),
            vote_average=item.get("score") or 0.0,
        ) for item in items]

    @staticmethod
    def _filter_row(label: str, model: str, options: Iterable[Tuple[str, str]],
                    show: Optional[str] = None) -> dict:
        props = {"class": "flex justify-start items-center"}
        if show:
            props["show"] = show
        return {"component": "div", "props": props, "content": [
            {"component": "div", "props": {"class": "mr-5"},
             "content": [{"component": "VLabel", "text": label}]},
            {"component": "VChipGroup", "props": {"model": model},
             "content": [{"component": "VChip", "props": {
                 "filter": True, "tile": True, "value": value}, "text": text}
                 for value, text in options]},
        ]}

    def iqiyivideo_filter_ui(self) -> List[dict]:
        current_year = time.localtime().tm_year
        rows = [self._filter_row(
            "种类", "mtype", (
                (key, CHANNEL_PARAMS[key]["Name"]) for key in APP_CHANNEL_PATHS
            )
        )]
        app_tv_show = "{{mtype == 'tv'}}"
        rows.extend([
            self._filter_row("类型", "genre", APP_TV_GENRE_OPTIONS, app_tv_show),
            self._filter_row("地区", "region", APP_TV_REGION_OPTIONS, app_tv_show),
            self._filter_row("时间", "year", (
                (("upcoming", "即将上线"),)
                + tuple((str(value), str(value)) for value in range(current_year, 2009, -1))
            ), app_tv_show),
            self._filter_row("资费", "access", APP_TV_ACCESS_OPTIONS, app_tv_show),
            self._filter_row("殿堂", "hall", APP_TV_HALL_OPTIONS, app_tv_show),
            self._filter_row(
                "规格", "specification", APP_TV_SPECIFICATION_OPTIONS, app_tv_show
            ),
            self._filter_row("奖项", "award", APP_TV_AWARD_OPTIONS, app_tv_show),
            self._filter_row("剧场", "theater", APP_TV_THEATER_OPTIONS, app_tv_show),
            self._filter_row("演员", "actor", APP_TV_ACTOR_OPTIONS, app_tv_show),
            self._filter_row(
                "推荐", "recommendation", APP_TV_RECOMMEND_OPTIONS, app_tv_show
            ),
            self._filter_row("排序", "mode", APP_TV_SORT_OPTIONS, app_tv_show),
        ])
        for channel, options in APP_SECTION_OPTIONS.items():
            if channel == "tv":
                continue
            rows.append(self._filter_row(
                "栏目", "section", options,
                "{{mtype == '" + channel + "'}}",
            ))
        return rows

    @eventmanager.register(ChainEventType.DiscoverSource)
    def discover_source(self, event: Event):
        if not self._enabled or not event or not event.event_data:
            return
        event_data: DiscoverSourceEventData = event.event_data
        names = (
            "section", "mode", "year", "access", "region", "genre",
            "specification", "hall", "theater", "award", "actor",
            "recommendation",
        )
        source = schemas.DiscoverMediaSource(
            name="爱奇艺视频（自用版）",
            mediaid_prefix="customiqiyivideo",
            api_path=("plugin/CustomIqiyiVideoDiscover/iqiyivideo_discover"
                      f"?apikey={settings.API_TOKEN}"),
            filter_params={
                "mtype": "tv", **{name: None for name in names},
            },
            filter_ui=self.iqiyivideo_filter_ui(),
            depends={name: ["mtype"] for name in names},
        )
        if event_data.extra_sources is None:
            event_data.extra_sources = []
        if not any(getattr(item, "mediaid_prefix", None) == "customiqiyivideo"
                   for item in event_data.extra_sources):
            event_data.extra_sources.append(source)

    @staticmethod
    def stop_service():
        return None
