"""
Mango TV Discover custom edition.

Derived from DDSRem-Dev/MoviePilot-Plugins MangGuoDiscover v1.0.4.
Original author: DDSRem. Modified by Picarse. Licensed under GNU GPL v3.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

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
    CHANNEL_PARAMS,
    FILTER_PARAM_NAMES,
    clamp_positive_int,
    extract_filter_groups,
    extract_hit_docs,
    media_items,
)


CONFIG_URL = "https://pianku.api.mgtv.com/rider/config/channel/v1"
LIST_URL = "https://pianku.api.mgtv.com/rider/list/pcweb/v3"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.mgtv.com/",
}
REQUEST_TIMEOUT = 12


class CustomMangGuoDiscover(_PluginBase):
    plugin_name = "芒果TV探索（自用版）"
    plugin_desc = "让探索支持芒果TV的数据浏览。"
    plugin_icon = (
        "https://raw.githubusercontent.com/DDSRem-Dev/"
        "MoviePilot-Plugins/main/icons/mangguo_A.jpg"
    )
    plugin_version = "1.0.0"
    plugin_author = "DDSRem, Picarse"
    author_url = "https://github.com/DDSRem"
    plugin_config_prefix = "custommangguodiscover_"
    plugin_order = 99
    auth_level = 1

    _enabled = False
    _filter_rows: List[dict] = []

    def init_plugin(self, config: dict = None):
        self._enabled = bool((config or {}).get("enabled"))
        self._filter_rows = []
        if "hitv.com" not in settings.SECURITY_IMAGE_DOMAINS:
            settings.SECURITY_IMAGE_DOMAINS.append("hitv.com")
        if self._enabled:
            self._filter_rows = self._load_filter_rows()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [{
            "path": "/mangguo_discover",
            "endpoint": self.mangguo_discover,
            "methods": ["GET"],
            "summary": "芒果TV探索数据源（自用版）",
            "description": "获取芒果TV探索数据",
        }]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [{
            "component": "VForm",
            "content": [{
                "component": "VRow",
                "content": [{
                    "component": "VCol",
                    "props": {"cols": 12, "md": 4},
                    "content": [{
                        "component": "VSwitch",
                        "props": {"model": "enabled", "label": "启用插件"},
                    }],
                }],
            }],
        }], {"enabled": False}

    @staticmethod
    def get_page() -> List[dict]:
        return []

    @staticmethod
    def _base_params(channel_id: str) -> Dict[str, str]:
        return {
            "platform": "pcweb",
            "allowedRC": "1",
            "channelId": channel_id,
            "_support": "10000000",
        }

    @staticmethod
    def _fetch_filter_groups(channel_id: str) -> List[Dict[str, Any]]:
        try:
            response = requests.get(
                CONFIG_URL,
                params=CustomMangGuoDiscover._base_params(channel_id),
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return extract_filter_groups(response.json())
        except (requests.RequestException, ValueError) as error:
            logger.warning(
                f"芒果TV筛选接口请求失败：频道={channel_id}，"
                f"错误类型={type(error).__name__}"
            )
            return []

    def _load_filter_rows(self) -> List[dict]:
        groups_by_channel = {}
        with ThreadPoolExecutor(max_workers=len(CHANNEL_PARAMS)) as executor:
            futures = {
                executor.submit(self._fetch_filter_groups, channel_id): name
                for name, channel_id in CHANNEL_PARAMS.items()
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    groups_by_channel[name] = future.result()
                except Exception as error:
                    logger.warning(
                        f"芒果TV筛选项解析失败：频道={name}，"
                        f"错误类型={type(error).__name__}"
                    )
                    groups_by_channel[name] = []
        return [
            {
                "component": "div",
                "props": {
                    "class": "flex justify-start items-center",
                    "show": "{{mtype == '" + channel_name + "'}}",
                },
                "content": [
                    {
                        "component": "div",
                        "props": {"class": "mr-5"},
                        "content": [{"component": "VLabel", "text": group["label"]}],
                    },
                    {
                        "component": "VChipGroup",
                        "props": {"model": group["key"]},
                        "content": [
                            {
                                "component": "VChip",
                                "props": {
                                    "filter": True,
                                    "tile": True,
                                    "value": option["value"],
                                },
                                "text": option["text"],
                            }
                            for option in group["options"]
                        ],
                    },
                ],
            }
            for channel_name in CHANNEL_PARAMS
            for group in groups_by_channel.get(channel_name, [])
        ]

    @staticmethod
    @cached(region="custom_mangguo_discover", ttl=1800, skip_none=True)
    def _request(page: int, count: int, mtype: str, **filters) -> List[Dict[str, Any]]:
        params = {
            **CustomMangGuoDiscover._base_params(CHANNEL_PARAMS[mtype]),
            "pn": str(page),
            "pc": str(count),
            "hudong": "1",
            **{key: value for key, value in filters.items() if value is not None},
        }
        try:
            response = requests.get(
                LIST_URL, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return extract_hit_docs(response.json())
        except (requests.RequestException, ValueError) as error:
            logger.warning(
                f"芒果TV列表接口请求失败：频道={mtype}，"
                f"错误类型={type(error).__name__}"
            )
            return []

    def mangguo_discover(
        self,
        mtype: str = "电视剧",
        chargeInfo: Optional[str] = None,
        sort: Optional[str] = None,
        kind: Optional[str] = None,
        edition: Optional[str] = None,
        area: Optional[str] = None,
        fitAge: Optional[str] = None,
        year: Optional[str] = None,
        feature: Optional[str] = None,
        page: int = 1,
        count: int = 80,
    ) -> List[schemas.MediaInfo]:
        if not self._enabled:
            return []
        if mtype not in CHANNEL_PARAMS:
            logger.warning(f"芒果TV探索收到未知频道：{mtype}")
            return []
        page = clamp_positive_int(page, default=1, maximum=1000)
        count = clamp_positive_int(count, default=80, maximum=100)
        supplied = locals()
        filters = {
            name: supplied[name]
            for name in FILTER_PARAM_NAMES
            if supplied.get(name) is not None
        }
        items = media_items(self._request(page, count, mtype, **filters), count)
        media_type = "电影" if mtype == "电影" else "电视剧"
        return [
            schemas.MediaInfo(
                type=media_type,
                title=item["title"],
                year=item.get("year"),
                title_year=(
                    f"{item['title']} ({item.get('year')})"
                    if item.get("year")
                    else item["title"]
                ),
                mediaid_prefix="custommangguo",
                media_id=item["clipId"],
                poster_path=item.get("img"),
            )
            for item in items
        ]

    def mangguo_filter_ui(self) -> List[dict]:
        category_row = {
            "component": "div",
            "props": {"class": "flex justify-start items-center"},
            "content": [
                {
                    "component": "div",
                    "props": {"class": "mr-5"},
                    "content": [{"component": "VLabel", "text": "种类"}],
                },
                {
                    "component": "VChipGroup",
                    "props": {"model": "mtype"},
                    "content": [
                        {
                            "component": "VChip",
                            "props": {"filter": True, "tile": True, "value": name},
                            "text": name,
                        }
                        for name in CHANNEL_PARAMS
                    ],
                },
            ],
        }
        return [category_row, *self._filter_rows]

    @eventmanager.register(ChainEventType.DiscoverSource)
    def discover_source(self, event: Event):
        if not self._enabled or not event or not event.event_data:
            return
        event_data: DiscoverSourceEventData = event.event_data
        source = schemas.DiscoverMediaSource(
            name="芒果TV（自用版）",
            mediaid_prefix="custommangguo",
            api_path=(
                "plugin/CustomMangGuoDiscover/mangguo_discover"
                f"?apikey={settings.API_TOKEN}"
            ),
            filter_params={
                "mtype": "电视剧",
                **{name: None for name in FILTER_PARAM_NAMES},
            },
            filter_ui=self.mangguo_filter_ui(),
            depends={name: ["mtype"] for name in FILTER_PARAM_NAMES},
        )
        if event_data.extra_sources is None:
            event_data.extra_sources = []
        if not any(
            getattr(existing, "mediaid_prefix", None) == "custommangguo"
            for existing in event_data.extra_sources
        ):
            event_data.extra_sources.append(source)

    @staticmethod
    def stop_service():
        return None
