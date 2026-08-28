"""黑白名单读写权限的纯逻辑层（不依赖 NoneBot 运行时，可独立测试）"""

from pathlib import Path
from typing import Generic, Literal, TypeVar

from loguru import logger
from pydantic import BaseModel

from ._atomic import atomic_write_text

Policy = Literal["rw", "ro", "deny"]

POLICY_LABELS: dict[str, str] = {"rw": "读写", "ro": "只读", "deny": "禁用"}

_POLICY_TOKENS: dict[str, Policy] = {
    "rw": "rw",
    "readwrite": "rw",
    "读写": "rw",
    "正常": "rw",
    "ro": "ro",
    "readonly": "ro",
    "只读": "ro",
    "deny": "deny",
    "ban": "deny",
    "禁用": "deny",
    "拉黑": "deny",
    "黑名单": "deny",
}

_REMOVE_TOKENS = {"移除", "删除", "清除", "remove", "del"}


def parse_policy_token(token: str) -> Policy | None:
    """解析策略词（支持中英文别名），无法识别返回 None"""
    return _POLICY_TOKENS.get(token.strip().lower())


def is_remove_token(token: str) -> bool:
    return token.strip().lower() in _REMOVE_TOKENS


class AccessConfig(BaseModel):
    """读写权限（黑白名单）配置

    策略取值：rw=读写，ro=只读，deny=禁用。
    判定顺序：超级用户豁免 > users > groups > default_policy。
    default_policy 设为 deny 即白名单模式。
    """

    default_policy: Policy = "rw"
    users: dict[str, Policy] = {}
    groups: dict[str, Policy] = {}


def resolve_policy(
    config: AccessConfig,
    user_id: str,
    group_id: str | None,
    *,
    is_superuser: bool = False,
) -> Policy:
    """按 用户 > 群 > 默认策略 的顺序解析生效策略；超级用户恒为 rw"""
    if is_superuser:
        return "rw"
    if (policy := config.users.get(user_id)) is not None:
        return policy
    if group_id is not None and (policy := config.groups.get(group_id)) is not None:
        return policy
    return config.default_policy


TModel = TypeVar("TModel", bound=BaseModel)


class HotReloadJsonModelFile(Generic[TModel]):
    """带热重载的 JSON 模型文件容器

    每次读取 current 时比对文件签名（mtime_ns + size），外部编辑即时生效。
    解析失败时保留上一份有效配置；文件被删除时回退默认值。
    """

    def __init__(self, cls: type[TModel], path: Path):
        self._cls = cls
        self.path = path
        self._model = cls()
        self._sig: tuple[int, int] | None = None
        if (sig := self._stat_sig()) is not None:
            self._reload(sig)
        else:
            logger.warning(f"数据文件 {path} 不存在，使用默认值并创建")
            self.save()

    @property
    def current(self) -> TModel:
        sig = self._stat_sig()
        if sig != self._sig:
            self._reload(sig)
        return self._model

    def save(self) -> None:
        atomic_write_text(
            self.path,
            self._model.model_dump_json(indent=2, ensure_ascii=False),
        )
        self._sig = self._stat_sig()

    def _stat_sig(self) -> tuple[int, int] | None:
        try:
            stat = self.path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def _reload(self, sig: tuple[int, int] | None) -> None:
        if sig is None:
            logger.warning(f"数据文件 {self.path} 已不存在，回退默认值")
            self._model = self._cls()
            self._sig = None
            return
        try:
            self._model = self._cls.model_validate_json(
                self.path.read_text(encoding="utf-8")
            )
            logger.info(f"数据文件 {self.path} 已热重载")
        except (OSError, ValueError) as e:
            logger.error(f"数据文件 {self.path} 热重载失败，保留原配置：{e}")
        # 失败也记录签名，避免文件再次变化前反复解析报错
        self._sig = sig
