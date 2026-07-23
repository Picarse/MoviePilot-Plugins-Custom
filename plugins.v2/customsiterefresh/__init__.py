import time
from threading import Lock
from typing import Any, Dict, List, Tuple

from app import schemas
from app.chain.site import SiteChain
from app.core.config import settings
from app.core.event import eventmanager
from app.db.site_oper import SiteOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType
from app.utils.http import RequestUtils

from .core import find_site_config, parse_site_configs


class CustomSiteRefresh(_PluginBase):
    plugin_name = "站点自动更新（自用版）"
    plugin_desc = "使用浏览器模拟登录站点获取Cookie和UA。"
    plugin_icon = "Chrome_A.png"
    plugin_version = "1.5.2"
    plugin_author = "thsrite, Picarse"
    author_url = "https://github.com/thsrite"
    plugin_config_prefix = "customsiterefresh_"
    plugin_order = 2
    auth_level = 2

    _enabled: bool = False
    _notify: bool = False
    _siteconf: str = ""
    _site_configs: List[Dict[str, str]] = []

    _site_locks: Dict[int, Lock] = {}
    _last_attempts: Dict[int, float] = {}
    _test_results: Dict[int, Tuple[bool, str]] = {}
    _connectivity_results: Dict[int, Tuple[bool, str]] = {}
    _locks_guard = Lock()
    _cooldown_seconds = 60

    def init_plugin(self, config: dict = None):
        config = config or {}
        self._enabled = bool(config.get("enabled"))
        self._notify = bool(config.get("notify"))
        self._siteconf = str(config.get("siteconf") or "")
        self._site_configs, errors = parse_site_configs(self._siteconf)
        for error in errors:
            logger.error(
                f"站点自动更新配置{error}，已跳过；"
                "请使用 域名|用户名|密码(|2FA验证码或密钥) 格式"
            )

    def get_state(self) -> bool:
        return self._enabled

    @eventmanager.register(EventType.PluginAction)
    def site_refresh(self, event):
        """Handle the event emitted by the official AutoSignIn plugin."""
        if not self.get_state() or not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "site_refresh":
            return
        self._refresh_site(site_id=event_data.get("site_id"), source="自动签到")

    @classmethod
    def _get_site_lock(cls, site_id: int) -> Lock:
        with cls._locks_guard:
            if site_id not in cls._site_locks:
                cls._site_locks[site_id] = Lock()
            return cls._site_locks[site_id]

    def _refresh_site(self, site_id: int, source: str, force: bool = False) -> Tuple[bool, str]:
        try:
            site_id = int(site_id)
        except (TypeError, ValueError):
            message = "未获取到有效的站点ID"
            logger.error(message)
            return False, message

        site = SiteOper().get(site_id)
        if not site:
            message = f"未获取到站点ID {site_id} 对应的站点数据"
            logger.error(message)
            return False, message

        site_config = find_site_config(site.url, self._site_configs)
        if not site_config:
            message = f"站点 {site.name}（{site.url}）没有匹配的账号配置，已跳过"
            logger.warning(message)
            return False, message

        site_lock = self._get_site_lock(site_id)
        if not site_lock.acquire(blocking=False):
            message = f"站点 {site.name} 正在更新Cookie和UA，本次重复请求已忽略"
            logger.warning(message)
            return False, message

        try:
            now = time.monotonic()
            with self._locks_guard:
                last_attempt = self._last_attempts.get(site_id, 0)
                if not force and now - last_attempt < self._cooldown_seconds:
                    remaining = max(1, int(self._cooldown_seconds - (now - last_attempt)))
                    message = f"站点 {site.name} 在冷却期内，{remaining}秒后可再次尝试"
                    logger.warning(message)
                    return False, message
                self._last_attempts[site_id] = now

            logger.info(f"由{source}触发，开始登录站点 {site.name} 更新Cookie和UA")
            try:
                state, message = SiteChain().update_cookie(
                    site_info=site,
                    username=site_config["username"],
                    password=site_config["password"],
                    two_step_code=site_config["two_step_code"],
                )
            except Exception as error:
                state, message = False, f"调用浏览器登录失败：{error}"

            detail = message or ("更新成功" if state else "未知错误")
            if state:
                logger.info(f"站点 {site.name} 自动更新Cookie和UA成功：{detail}")
            else:
                logger.error(f"站点 {site.name} 自动更新Cookie和UA失败：{detail}")

            if self._notify:
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title=f"站点 {site.name} Cookie和UA更新{'成功' if state else '失败'}",
                    text=f"触发来源：{source}\n结果：{detail}",
                )
            return state, detail
        finally:
            site_lock.release()

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        return [{
            "path": "/test",
            "endpoint": self.test_site,
            "methods": ["POST"],
            "summary": "立即测试站点登录并更新Cookie和UA",
        }, {
            "path": "/connectivity",
            "endpoint": self.test_connectivity,
            "methods": ["POST"],
            "summary": "匿名测试站点网络连通性",
        }, {
            "path": "/login-page-check",
            "endpoint": self.check_login_page,
            "methods": ["POST"],
            "summary": "检查登录页是否可由浏览器加载",
        }]

    def test_site(self, payload: Dict[str, Any], apikey: str) -> schemas.Response:
        if apikey != settings.API_TOKEN:
            return schemas.Response(success=False, message="API密钥错误")
        site_id = payload.get("site_id") if isinstance(payload, dict) else None
        state, message = self._refresh_site(site_id=site_id, source="手动测试", force=True)
        try:
            self._test_results[int(site_id)] = (state, message)
        except (TypeError, ValueError):
            pass
        return schemas.Response(success=state, message=message)

    def test_connectivity(self, payload: Dict[str, Any], apikey: str) -> schemas.Response:
        if apikey != settings.API_TOKEN:
            return schemas.Response(success=False, message="API密钥错误")

        site_id = payload.get("site_id") if isinstance(payload, dict) else None
        try:
            site_id = int(site_id)
        except (TypeError, ValueError):
            return schemas.Response(success=False, message="未获取到有效的站点ID")

        site = SiteOper().get(site_id)
        if not site:
            return schemas.Response(
                success=False,
                message=f"未获取到站点ID {site_id} 对应的站点数据",
            )

        site_lock = self._get_site_lock(site_id)
        if not site_lock.acquire(blocking=False):
            message = f"站点 {site.name} 正在执行站点操作，请稍后重试"
            self._connectivity_results[site_id] = (False, message)
            return schemas.Response(success=False, message=message)

        proxy_config = settings.PROXY if site.proxy else None
        if site.proxy and not proxy_config:
            route = "站点代理未配置，实际直连"
        else:
            route = "站点代理" if proxy_config else "直连"
        timeout = max(1, min(int(site.timeout or 10), 10))
        started_at = time.monotonic()
        response = None
        try:
            response = RequestUtils(
                headers={
                    "User-Agent": "MoviePilot-Connectivity-Test/1.0",
                    "Accept": "*/*",
                    "Connection": "close",
                },
                proxies=proxy_config,
                timeout=timeout,
            ).request(
                method="head",
                url=site.url,
                allow_redirects=False,
                stream=True,
                raise_exception=True,
            )
            elapsed = time.monotonic() - started_at
            if response is not None:
                message = (
                    f"网络连通成功（{route}，HTTP {response.status_code}，"
                    f"耗时 {elapsed:.1f} 秒）"
                )
                state = True
                logger.info(f"站点 {site.name} {message}")
            else:
                message = (
                    f"网络请求未获得响应"
                    f"（{route}，耗时 {elapsed:.1f} 秒）"
                )
                state = False
                logger.error(f"站点 {site.name} {message}")
        except Exception as error:
            elapsed = time.monotonic() - started_at
            state = False
            message = (
                f"网络连通失败（{route}，最长等待 {timeout} 秒，"
                f"耗时 {elapsed:.1f} 秒，错误类型 {type(error).__name__}）"
            )
            logger.error(f"站点 {site.name} {message}")
        finally:
            if response is not None:
                response.close()
            site_lock.release()

        self._connectivity_results[site_id] = (state, message)
        return schemas.Response(success=state, message=message)

    def check_login_page(self, payload: Dict[str, Any], apikey: str) -> schemas.Response:
        """Load one site in a disposable direct browser session without credentials."""
        if apikey != settings.API_TOKEN:
            return schemas.Response(success=False, message="API密钥错误")
        site_id = payload.get("site_id") if isinstance(payload, dict) else None
        try:
            site_id = int(site_id)
        except (TypeError, ValueError):
            return schemas.Response(success=False, message="未获取到有效的站点ID")
        site = SiteOper().get(site_id)
        if not site:
            return schemas.Response(success=False, message=f"站点ID {site_id} 不存在")

        from app.helper.browser import BrowserSessionHelper

        helper = BrowserSessionHelper(headless=False)
        session_key = f"custom-site-refresh-check-{site_id}-{time.monotonic_ns()}"
        started_at = time.monotonic()
        try:
            def inspect(session):
                page = session.active_page
                response = helper.goto(page, site.url, timeout=8)
                snapshot = BrowserSessionHelper.build_snapshot(
                    page, status=getattr(response, "status", None), max_text_chars=1000
                )
                elements = snapshot.get("interactive_elements") or []
                input_types = sorted({
                    str(element.get("type") or "").lower()
                    for element in elements if element.get("type")
                })
                return {
                    "url": snapshot.get("url"),
                    "title": snapshot.get("title"),
                    "status": snapshot.get("status"),
                    "input_types": input_types,
                    "has_password": "password" in input_types,
                }

            result = helper.with_session(
                session_key=session_key,
                callback=inspect,
                timeout=8,
            )
            elapsed = time.monotonic() - started_at
            title = str(result.get("title") or "")
            has_password = bool(result.get("has_password"))
            state = has_password
            message = (
                f"登录页检查完成（直连，耗时 {elapsed:.1f} 秒，"
                f"标题 {title[:80] or '无'}，密码框 {'存在' if has_password else '不存在'}）"
            )
            return schemas.Response(success=state, message=message, data=result)
        except Exception as error:
            elapsed = time.monotonic() - started_at
            return schemas.Response(
                success=False,
                message=(
                    f"登录页检查失败（直连，耗时 {elapsed:.1f} 秒，"
                    f"错误类型 {type(error).__name__}）"
                ),
            )
        finally:
            BrowserSessionHelper.close_session(session_key)

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [{
            "component": "VForm",
            "content": [{
                "component": "VRow",
                "content": [{
                    "component": "VCol",
                    "props": {"cols": 12, "md": 6},
                    "content": [{
                        "component": "VSwitch",
                        "props": {"model": "enabled", "label": "启用插件"},
                    }],
                }, {
                    "component": "VCol",
                    "props": {"cols": 12, "md": 6},
                    "content": [{
                        "component": "VSwitch",
                        "props": {"model": "notify", "label": "开启通知"},
                    }],
                }],
            }, {
                "component": "VRow",
                "content": [{
                    "component": "VCol",
                    "props": {"cols": 12},
                    "content": [{
                        "component": "VTextarea",
                        "props": {
                            "model": "siteconf",
                            "label": "站点配置",
                            "rows": 5,
                            "placeholder": "每行一个站点：\n域名|用户名|密码(|TOTP密钥或当前验证码)",
                        },
                    }],
                }],
            }, {
                "component": "VRow",
                "content": [{
                    "component": "VCol",
                    "props": {"cols": 12},
                    "content": [{
                        "component": "VAlert",
                        "props": {
                            "type": "info",
                            "variant": "tonal",
                            "text": "官方自动签到提示Cookie失效时自动触发。"
                                    "自动更新的第四段应填写固定Base32 TOTP密钥；"
                                    "当前6位验证码只适合立即测试。"
                                    "账号配置会保存在MoviePilot数据库中，请保护数据库和备份。"
                                    "不是所有站点都支持浏览器模拟登录。",
                        },
                    }],
                }],
            }],
        }], {
            "enabled": False,
            "notify": False,
            "siteconf": "",
        }

    def get_page(self) -> List[dict]:
        rows = []
        for site in SiteOper().list():
            if not find_site_config(site.url, self._site_configs):
                continue
            last_result = self._test_results.get(site.id)
            connectivity_result = self._connectivity_results.get(site.id)
            subtitle = site.url
            if last_result:
                subtitle += f"｜登录：{'成功' if last_result[0] else '失败'} - {last_result[1]}"
            if connectivity_result:
                subtitle += (
                    f"｜连通性：{'成功' if connectivity_result[0] else '失败'}"
                    f" - {connectivity_result[1]}"
                )
            rows.append({
                "component": "VListItem",
                "props": {
                    "title": site.name,
                    "subtitle": subtitle,
                    "prepend-icon": "mdi-web-refresh",
                },
                "content": [{
                    "component": "VBtn",
                    "props": {
                        "color": "info",
                        "variant": "tonal",
                        "size": "small",
                        "class": "mr-2",
                    },
                    "text": "测试连通性",
                    "events": {
                        "click": {
                            "api": f"plugin/{self.__class__.__name__}/connectivity?apikey={settings.API_TOKEN}",
                            "method": "post",
                            "params": {"site_id": site.id},
                        }
                    },
                }, {
                    "component": "VBtn",
                    "props": {
                        "color": "primary",
                        "variant": "tonal",
                        "size": "small",
                    },
                    "text": "立即测试",
                    "events": {
                        "click": {
                            "api": f"plugin/{self.__class__.__name__}/test?apikey={settings.API_TOKEN}",
                            "method": "post",
                            "params": {"site_id": site.id},
                        }
                    },
                }],
            })

        if not rows:
            return [{
                "component": "VAlert",
                "props": {
                    "type": "info",
                    "variant": "tonal",
                    "text": "没有找到与账号配置匹配的MoviePilot站点，请先保存插件配置。",
                },
            }]

        return [{
            "component": "VAlert",
            "props": {
                "type": "warning",
                "variant": "tonal",
                "class": "mb-4",
                "text": "测试连通性仅发送匿名HEAD请求，不使用浏览器、账号或2FA，"
                        "不读取站点已存Cookie/UA；"
                        "立即测试会真实登录，并在成功后覆盖当前Cookie和UA。",
            },
        }, {
            "component": "VList",
            "content": rows,
        }]

    def stop_service(self):
        pass
