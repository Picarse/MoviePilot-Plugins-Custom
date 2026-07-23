"""iQIYI Video Discover custom edition for MoviePilot V2."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    ACCESS_OPTIONS,
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
    CATALOG_OPTIONS,
    CHANNEL_PARAMS,
    EXTRA_FILTER_OPTIONS,
    GENRE_OPTIONS,
    PRODUCTION_OPTIONS,
    REGION_OPTIONS,
    SORT_OPTIONS,
    category_value,
    clamp_positive_int,
    extract_detail,
    extract_app_items,
    extract_items,
    filter_app_tv_items,
    media_overview,
    merge_app_item,
    merge_detail,
)


LIST_API = "https://pcw-api.iqiyi.com/search/recommend/list"
DETAIL_API = "https://pcw-api.iqiyi.com/video/video/videoinfowithuser/{media_id}"
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
DEFAULT_DETAIL_LIMIT = 12
MAX_DETAIL_LIMIT = 30
DETAIL_WORKERS = 6
IMAGE_DOMAINS = ("iqiyipic.com", *(f"pic{index}.iqiyipic.com" for index in range(10)))
CATEGORY_FILTER_NAMES = (
    "region", "genre", "specification", "theme", "version",
    "adaptation", "producer", "subtype", "duration", "format",
)


class CustomIqiyiVideoDiscover(_PluginBase):
    plugin_name = "爱奇艺视频探索（自用版）"
    plugin_desc = "让探索支持爱奇艺视频的数据浏览。"
    plugin_icon = "https://www.iqiyi.com/favicon.ico"
    plugin_version = "1.3.0"
    plugin_author = "Picarse"
    author_url = "https://github.com/Picarse"
    plugin_config_prefix = "customiqiyivideodiscover_"
    plugin_order = 99
    auth_level = 1

    _enabled = False
    _detail_limit = DEFAULT_DETAIL_LIMIT

    def init_plugin(self, config: dict = None):
        config = config or {}
        self._enabled = bool(config.get("enabled"))
        self._detail_limit = clamp_positive_int(
            config.get("detail_limit"), DEFAULT_DETAIL_LIMIT, MAX_DETAIL_LIMIT
        )
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
                "content": [
                    {"component": "VCol", "props": {"cols": 12, "md": 4},
                     "content": [{"component": "VSwitch", "props": {
                         "model": "enabled", "label": "启用插件"}}]},
                    {"component": "VCol", "props": {"cols": 12, "md": 4},
                     "content": [{"component": "VTextField", "props": {
                         "model": "detail_limit", "label": "每页详情补全上限",
                         "type": "number", "min": 1, "max": MAX_DETAIL_LIMIT,
                         "hint": "默认12条；只补当前页并缓存6小时",
                         "persistent-hint": True}}]},
                ],
            }],
        }], {"enabled": False, "detail_limit": DEFAULT_DETAIL_LIMIT}

    @staticmethod
    def get_page() -> List[dict]:
        return []

    @staticmethod
    def _fetch_page(mtype: str, page: int, count: int, mode: Optional[str],
                    year: Optional[str], access: Optional[str],
                    region: Optional[str], genre: Optional[str],
                    specification: Optional[str] = None, theme: Optional[str] = None,
                    version: Optional[str] = None, adaptation: Optional[str] = None,
                    producer: Optional[str] = None, subtype: Optional[str] = None,
                    duration: Optional[str] = None, format: Optional[str] = None,
                    production: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        params = {
            "channel_id": CHANNEL_PARAMS[mtype]["Id"],
            "data_type": "1",
            "page_id": page,
            "ret_num": count,
            "mode": mode or "11",
        }
        if year:
            params["market_release_date_level"] = year
        if access not in (None, ""):
            params["is_purchase"] = access
        if production in {"0", "1"}:
            params["is_qiyi_produced"] = production
        category = category_value(
            region, genre, specification, theme, version,
            adaptation, producer, subtype, duration, format,
        )
        if category:
            params["three_category_id"] = category
        try:
            response = requests.get(
                LIST_API, params=params, headers=API_HEADERS, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("code") != "A00000":
                raise ValueError("unexpected iQIYI response status")
            return extract_items(payload, mtype)
        except (requests.RequestException, TypeError, ValueError) as error:
            logger.warning(
                f"爱奇艺列表请求失败：频道={mtype}，页码={page}，"
                f"错误类型={type(error).__name__}"
            )
            return None

    @cached(region="custom_iqiyivideo_page", ttl=1800, skip_none=True)
    def _request_page(self, mtype: str, page: int, count: int,
                      mode: Optional[str], year: Optional[str], access: Optional[str],
                      region: Optional[str], genre: Optional[str],
                      specification: Optional[str] = None, theme: Optional[str] = None,
                      version: Optional[str] = None, adaptation: Optional[str] = None,
                      producer: Optional[str] = None, subtype: Optional[str] = None,
                      duration: Optional[str] = None, format: Optional[str] = None,
                      production: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        return self._fetch_page(
            mtype, page, count, mode, year, access, region, genre,
            specification, theme, version, adaptation, producer, subtype, duration,
            format, production,
        )

    @staticmethod
    def _fetch_detail(mtype: str, media_id: str) -> Optional[Dict[str, Any]]:
        try:
            response = requests.get(
                DETAIL_API.format(media_id=media_id),
                params={"agent_type": "1", "authcookie": "",
                        "subkey": media_id, "subscribe": "1"},
                headers=API_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return extract_detail(response.json(), mtype) or None
        except (requests.RequestException, TypeError, ValueError):
            return None

    @cached(region="custom_iqiyivideo_detail", ttl=21600, skip_none=True)
    def _request_detail(self, mtype: str, media_id: str) -> Optional[Dict[str, Any]]:
        return self._fetch_detail(mtype, media_id)

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

    def _enrich_items(self, mtype: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        bounded = items[:self._detail_limit]
        details: Dict[str, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=min(DETAIL_WORKERS, len(bounded) or 1)) as executor:
            futures = {
                executor.submit(self._request_detail, mtype, item["media_id"]): item["media_id"]
                for item in bounded
            }
            for future in as_completed(futures):
                media_id = futures[future]
                try:
                    detail = future.result()
                except Exception:
                    detail = None
                if detail:
                    details[media_id] = detail
        enriched = [merge_detail(item, details.get(item["media_id"])) for item in bounded]
        return [*enriched, *items[len(bounded):]]

    def iqiyivideo_discover(self, mtype: str = "tv", catalog: str = "app",
                            section: Optional[str] = None, mode: Optional[str] = None,
                            year: Optional[str] = None, access: Optional[str] = None,
                            region: Optional[str] = None, genre: Optional[str] = None,
                            specification: Optional[str] = None,
                            theme: Optional[str] = None, version: Optional[str] = None,
                            adaptation: Optional[str] = None,
                            producer: Optional[str] = None,
                            subtype: Optional[str] = None,
                            duration: Optional[str] = None,
                            format: Optional[str] = None,
                            production: Optional[str] = None,
                            hall: Optional[str] = None,
                            theater: Optional[str] = None,
                            award: Optional[str] = None,
                            actor: Optional[str] = None,
                            recommendation: Optional[str] = None,
                            page: int = 1, count: int = 10) -> List[schemas.MediaInfo]:
        if not self._enabled or mtype not in CHANNEL_PARAMS:
            return []
        page = clamp_positive_int(page, 1, 1000)
        count = clamp_positive_int(count, 10, MAX_PAGE_SIZE)
        if catalog == "app" and mtype in APP_CHANNEL_PATHS:
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
        else:
            catalog = "web"
            supplied = locals()
            allowed = {
                "region": {value for value, _label in REGION_OPTIONS[mtype]},
                "genre": {value for value, _label in GENRE_OPTIONS[mtype]},
            }
            allowed.update({
                name: {value for value, _label in options}
                for name, (_label, options) in EXTRA_FILTER_OPTIONS[mtype].items()
            })
            category_filters = {
                name: supplied.get(name) if supplied.get(name) in allowed.get(name, set()) else None
                for name in CATEGORY_FILTER_NAMES
            }
            selected_mode = mode if mode in {value for value, _label in SORT_OPTIONS} else None
            selected_access = access if access in {value for value, _label in ACCESS_OPTIONS} else None
            selected_production = (
                production if mtype == "tv"
                and production in {value for value, _label in PRODUCTION_OPTIONS}
                else None
            )
            items = self._enrich_items(mtype, self._request_page(
                mtype, page, count, selected_mode, year, selected_access,
                *(category_filters[name] for name in CATEGORY_FILTER_NAMES),
                selected_production,
            ) or [])
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
            "种类", "mtype", ((key, value["Name"]) for key, value in CHANNEL_PARAMS.items())
        )]
        rows.append(self._filter_row(
            "来源", "catalog", CATALOG_OPTIONS, "{{mtype != 'documentary'}}"
        ))
        app_tv_show = "{{catalog == 'app' && mtype == 'tv'}}"
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
                "{{catalog == 'app' && mtype == '" + channel + "'}}",
            ))
        for channel in CHANNEL_PARAMS:
            show = (
                "{{(catalog != 'app' || mtype == 'documentary') && mtype == '"
                + channel + "'}}"
            )
            if REGION_OPTIONS[channel]:
                rows.append(self._filter_row("地区", "region", REGION_OPTIONS[channel], show))
            if GENRE_OPTIONS[channel]:
                rows.append(self._filter_row("类型", "genre", GENRE_OPTIONS[channel], show))
            for model, (label, options) in EXTRA_FILTER_OPTIONS[channel].items():
                rows.append(self._filter_row(label, model, options, show))
        rows.extend([
            self._filter_row("年份", "year", (
                (("即将上线", "即将上线"),)
                + tuple((str(value), str(value)) for value in range(current_year, 2009, -1))
            ), "{{catalog != 'app' || mtype == 'documentary'}}"),
            self._filter_row(
                "权益", "access", ACCESS_OPTIONS,
                "{{catalog != 'app' || mtype == 'documentary'}}",
            ),
            self._filter_row(
                "制作", "production", PRODUCTION_OPTIONS,
                "{{catalog != 'app' && mtype == 'tv'}}",
            ),
            self._filter_row(
                "排序", "mode", SORT_OPTIONS,
                "{{catalog != 'app' || mtype == 'documentary'}}",
            ),
        ])
        return rows

    @eventmanager.register(ChainEventType.DiscoverSource)
    def discover_source(self, event: Event):
        if not self._enabled or not event or not event.event_data:
            return
        event_data: DiscoverSourceEventData = event.event_data
        names = (
            "catalog", "section", "mode", "year", "access", "production",
            "hall", "theater", "award", "actor", "recommendation",
            *CATEGORY_FILTER_NAMES,
        )
        source = schemas.DiscoverMediaSource(
            name="爱奇艺视频（自用版）",
            mediaid_prefix="customiqiyivideo",
            api_path=("plugin/CustomIqiyiVideoDiscover/iqiyivideo_discover"
                      f"?apikey={settings.API_TOKEN}"),
            filter_params={
                "mtype": "tv", "catalog": "app",
                **{name: None for name in names if name != "catalog"},
            },
            filter_ui=self.iqiyivideo_filter_ui(),
            depends={
                name: (["mtype"] if name == "catalog" else ["mtype", "catalog"])
                for name in names
            },
        )
        if event_data.extra_sources is None:
            event_data.extra_sources = []
        if not any(getattr(item, "mediaid_prefix", None) == "customiqiyivideo"
                   for item in event_data.extra_sources):
            event_data.extra_sources.append(source)

    @staticmethod
    def stop_service():
        return None
