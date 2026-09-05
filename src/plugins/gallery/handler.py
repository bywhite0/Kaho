import asyncio
import random
import re
import zipfile
from datetime import datetime
from pathlib import Path

from nonebot import logger
from nonebot.adapters import Message
from nonebot.adapters.onebot.v11 import ActionFailed, GroupMessageEvent
from nonebot.adapters.onebot.v11 import Bot as OneBot
from nonebot.adapters.onebot.v11 import Message as OneBotMessage
from nonebot.adapters.onebot.v11 import MessageEvent as OneBotMessageEvent
from nonebot.adapters.onebot.v11 import MessageSegment as OneBotMessageSegment
from nonebot.exception import NetworkError
from nonebot.matcher import Matcher
from nonebot.params import CommandArg, EventMessage
from nonebot.typing import T_State
from send2trash import send2trash

from .access import access_data, format_access_config, is_superuser
from .access_core import POLICY_LABELS, is_remove_token, parse_policy_token
from .compat import (
    HTTPX_CLIENT,
    get_forward_message_events,
    meme_image_segment,
    parse_arg_message,
)
from .config import cfg, gallery_name_data
from .gallery import (
    add_pictures,
    clear_gallery_cover,
    find_duplicate_groups,
    get_gallery_mode,
    get_gallery_name,
    get_picture_by_id,
    invalidate_gallery_render_cache,
    is_gallery_hidden,
    is_gallery_writable,
    remove_gallery_from_index,
    remove_picture_from_index,
    render_gallery_overview,
    render_gallery_thumbnails,
    resolve_picture_index,
    set_gallery_cover,
    set_gallery_mode,
)
from .matcher import (
    add_gallery,
    add_gallery_alias,
    add_picture,
    export_gallery,
    gallery_access_ctrl,
    gallery_dedupe,
    gallery_mode_ctrl,
    gallery_pictures,
    get_picture,
    pic_info,
    remove_gallery,
    remove_gallery_alias,
    remove_picture,
    set_gallery_cover_cmd,
    set_tags,
    tag_search,
)
from .meta import PictureMeta, get_picture_meta_index
from .names import (
    INTEGER_PATTERN,
    MODE_LABELS,
    parse_hash_picture_ids,
    parse_mode_token,
    validate_gallery_alias,
    validate_gallery_name,
)


async def _ensure_gallery_visible(
    matcher: type[Matcher],
    bot: OneBot,
    event: OneBotMessageEvent,
    name: str,
) -> None:
    """off 画廊对非超级用户一律按"不存在"回复，避免泄露它的存在"""
    if is_gallery_hidden(name) and not await is_superuser(bot, event):
        await matcher.finish(f"未找到画廊：{name}")


async def _ensure_gallery_editable(
    matcher: type[Matcher],
    bot: OneBot,
    event: OneBotMessageEvent,
    name: str,
) -> None:
    """只有 edit 模式的画廊允许非超级用户改动"""
    if is_gallery_writable(name) or await is_superuser(bot, event):
        return
    if is_gallery_hidden(name):
        await matcher.finish(f"未找到画廊：{name}")
    await matcher.finish(f"画廊 {name} 当前为只读，无法修改。")


@add_gallery.handle()
async def _(arg_msg: Message = CommandArg()):
    name = arg_msg.extract_plain_text().strip()
    if not name:
        await add_gallery.finish("请提供画廊名称。")
    if reason := validate_gallery_name(name):
        # 画廊名会直接作为数据目录下的子目录名，必须在落盘前拦住非法名称
        await add_gallery.finish(f"画廊名称无效：{reason}")

    v = gallery_name_data.instance
    if name in v.name_to_aliases:
        await add_gallery.finish(f"画廊 {name} 已存在。")

    # 创建画廊目录
    gallery_dir = cfg.data_dir_path / name
    try:
        gallery_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        await add_gallery.finish(f"画廊目录 {gallery_dir} 已存在，无法创建。")
    except OSError as e:
        logger.exception(f"创建画廊目录 {gallery_dir} 失败：{e}")
        await add_gallery.finish(f"创建画廊目录失败：{e}")

    # 更新索引
    v.name_to_aliases[name] = []
    gallery_name_data.save_to_file()
    invalidate_gallery_render_cache()
    await add_gallery.finish(f"成功添加画廊：{name}")


@remove_gallery.handle()
async def _(arg_msg: Message = CommandArg()):
    name = arg_msg.extract_plain_text().strip()
    if not name:
        await remove_gallery.finish("请提供画廊名称。")

    v = gallery_name_data.instance
    if name not in v.name_to_aliases:
        await remove_gallery.finish(f"画廊 {name} 不存在。")

    # 将画廊目录移至废纸篓
    gallery_dir = cfg.data_dir_path / name
    try:
        send2trash(gallery_dir)
    except OSError as e:
        logger.exception(f"删除画廊目录 {gallery_dir} 失败：{e}")
        await remove_gallery.finish(f"删除画廊目录失败：{e}")

    # 更新索引
    aliases = v.name_to_aliases.pop(name, [])
    for alias in aliases:
        v.alias_to_name.pop(alias, None)
    v.name_to_mode.pop(name, None)
    v.name_to_cover.pop(name, None)
    gallery_name_data.save_to_file()
    remove_gallery_from_index(name)
    get_picture_meta_index().remove_gallery(name)
    invalidate_gallery_render_cache()
    invalidate_gallery_render_cache(name)
    await remove_gallery.finish(f"成功删除画廊：{name}")


@add_gallery_alias.handle()
async def _(
    bot: OneBot,
    event: OneBotMessageEvent,
    arg_msg: Message = CommandArg(),
):
    args = parse_arg_message(
        arg_msg.extract_plain_text().strip(),
        {"name": str, "alias": str},
        maxsplit=1,
    )
    name: str | None = args["name"]
    alias: str | None = args["alias"]

    if not name or not alias:
        await add_gallery_alias.finish("请提供画廊名称和别名，格式：<画廊名称> <别名>")
    if reason := validate_gallery_alias(alias):
        await add_gallery_alias.finish(f"别名无效：{reason}")
    v = gallery_name_data.instance
    if name not in v.name_to_aliases:
        await add_gallery_alias.finish(f"画廊 {name} 不存在。")
    await _ensure_gallery_editable(add_gallery_alias, bot, event, name)
    if alias in v.name_to_aliases:
        # 别名不能与现有画廊名称冲突
        await add_gallery_alias.finish(f"{alias} 已被画廊名称使用。")
    if alias in v.alias_to_name:
        await add_gallery_alias.finish(f"别名 {alias} 已被画廊 {v.alias_to_name[alias]} 使用。")

    # 添加别名
    v.alias_to_name[alias] = name
    v.name_to_aliases[name].append(alias)
    gallery_name_data.save_to_file()
    invalidate_gallery_render_cache()
    tip = ""
    if INTEGER_PATTERN.match(alias):
        # iota 只增不减：该 id 要么已有图片，要么将来会有，提示无需先查存在性
        tip = f"\n注意：「看 {alias}」今后会命中本画廊；要取图片 {alias} 请用「看 #{alias}」。"
    await add_gallery_alias.finish(f"成功为画廊 {name} 添加别名：{alias}{tip}")


@remove_gallery_alias.handle()
async def _(arg_msg: Message = CommandArg()):
    alias = arg_msg.extract_plain_text().strip()
    if not alias:
        await remove_gallery_alias.finish("请提供要删除的别名。")

    v = gallery_name_data.instance
    if alias not in v.alias_to_name:
        await remove_gallery_alias.finish(f"别名 {alias} 不存在。")

    # 删除别名
    name = v.alias_to_name.pop(alias)
    v.name_to_aliases[name].remove(alias)
    gallery_name_data.save_to_file()
    invalidate_gallery_render_cache()
    await remove_gallery_alias.finish(f"成功删除画廊 {name} 的别名：{alias}")


@gallery_pictures.handle()
async def _(
    bot: OneBot,
    event: OneBotMessageEvent,
    arg_msg: Message = CommandArg(),
):
    name_or_alias = arg_msg.extract_plain_text().strip()
    if not name_or_alias:
        include_hidden = await is_superuser(bot, event)
        image = await asyncio.to_thread(
            render_gallery_overview,
            include_hidden=include_hidden,
        )
        if not image:
            await gallery_pictures.finish("当前没有画廊。")
        await gallery_pictures.finish(OneBotMessageSegment.image(image))

    name = get_gallery_name(name_or_alias)
    if not name:
        await gallery_pictures.finish(f"未找到画廊：{name_or_alias}")
    await _ensure_gallery_visible(gallery_pictures, bot, event, name)

    gallery_dir = cfg.data_dir_path / name
    if not gallery_dir.is_dir():
        logger.warning(f"画廊索引中存在画廊名称 {name}，但对应的目录不存在：{gallery_dir}")
        await gallery_pictures.finish(f"画廊 {name} 的目录不存在。")

    pic_files = _gallery_picture_files(name)
    if not pic_files:
        await gallery_pictures.finish(f"画廊 {name} 中没有图片。")

    image = await asyncio.to_thread(render_gallery_thumbnails, name, pic_files)
    if not image:
        await gallery_pictures.finish(f"画廊 {name} 中没有可读取的图片。")
    await gallery_pictures.finish(OneBotMessageSegment.image(image))


@get_picture.handle()
async def _(
    bot: OneBot,
    event: OneBotMessageEvent,
    arg_msg: Message = CommandArg(),
):
    arg_str = arg_msg.extract_plain_text().strip()
    if not arg_str:
        await get_picture.finish("请提供画廊名称或图片id。")

    # 「看 #5」显式按 id 取图：纯数字别名遮蔽同号图片时，这是精确取图的通路
    if forced_ids := parse_hash_picture_ids(arg_str):
        await _finish_pictures_by_ids(bot, event, forced_ids)

    tokens = arg_str.split()
    # 画廊名优先：纯数字别名与历史遗留的纯数字画廊名都不能被 id 解析抢走
    is_gallery = len(tokens) == 1 and get_gallery_name(tokens[0]) is not None
    if not is_gallery and all(INTEGER_PATTERN.match(token) for token in tokens):
        await _finish_pictures_by_ids(bot, event, [int(token) for token in tokens])

    args = re.split(r"[x*×\s]+", arg_str, maxsplit=1)
    arg1: str = args[0]
    name = get_gallery_name(arg1)
    if not name:
        await get_picture.finish(f"未找到画廊：{arg1}")
    await _ensure_gallery_visible(get_picture, bot, event, name)

    num = 1
    if len(args) > 1 and INTEGER_PATTERN.match(args[1]):
        num = int(args[1])
    if num < 1:
        await get_picture.finish("请提供有效的图片数量。")
    if num > cfg.send_pic_limit:
        await get_picture.finish(f"每次最多发送 {cfg.send_pic_limit} 张图片。")

    pic_files = _gallery_picture_files(name)
    if not pic_files:
        await get_picture.finish(f"画廊 {name} 中没有图片。")

    await get_picture.finish(await asyncio.to_thread(_build_pic_message, pic_files, num))


async def _finish_pictures_by_ids(
    bot: OneBot,
    event: OneBotMessageEvent,
    pic_ids: list[int],
) -> None:
    """按图片 id 取图；负数表示倒数第几张入库的图片（-1 即最新一张）"""
    if len(pic_ids) > cfg.send_pic_limit:
        await get_picture.finish(f"每次最多发送 {cfg.send_pic_limit} 张图片。")

    include_hidden = await is_superuser(bot, event)
    message = OneBotMessage()
    missing: list[int] = []
    for raw_id in pic_ids:
        resolved = await asyncio.to_thread(
            resolve_picture_index,
            raw_id,
            include_hidden=include_hidden,
        )
        pic_file = get_picture_by_id(resolved) if resolved is not None else None
        if pic_file is None or not _is_visible_picture(pic_file, include_hidden):
            missing.append(raw_id)
            continue
        message += await asyncio.to_thread(_pic_seg, pic_file)

    if not message:
        wanted = "、".join(str(pic_id) for pic_id in missing)
        await get_picture.finish(f"未找到图片id {wanted} 对应的图片。")
    if missing:
        wanted = "、".join(str(pic_id) for pic_id in missing)
        message += OneBotMessageSegment.text(f"（未找到图片id {wanted}）")
    await get_picture.finish(message)


def _normalize_tags(raw: str) -> list[str]:
    """归一化标签：去掉 # 前缀，去空去重，保持顺序"""
    normalized: list[str] = []
    for token in raw.split():
        tag = token.strip().lstrip("#").strip()
        if tag and tag not in normalized:
            normalized.append(tag)
    return normalized


def _pic_seg(pic_file: Path) -> OneBotMessageSegment:
    """构造图片消息段：base64 模式内联字节（协议端异机可用），path 模式直发本地路径（需同机）"""
    file = pic_file if cfg.send_pic_mode == "path" else pic_file.read_bytes()
    if cfg.send_pic_as_meme:
        return meme_image_segment(file)
    return OneBotMessageSegment.image(file)


def _build_pic_message(pic_files: list[Path], num: int) -> OneBotMessage:
    """从候选图片中不重复地随机抽取至多 num 张组装成消息"""
    message = OneBotMessage()
    for pic_file in random.sample(pic_files, min(num, len(pic_files))):
        message += _pic_seg(pic_file)
    return message


def _gallery_name_of(pic_file: Path) -> str:
    """图片所属的画廊名（数据根目录下的一级目录名）"""
    return pic_file.parent.relative_to(cfg.data_dir_path).as_posix()


def _gallery_picture_files(name: str) -> list[Path]:
    """画廊目录内以图片 id 命名的文件，过滤掉子目录与手工放入的杂项文件"""
    gallery_dir = cfg.data_dir_path / name
    if not gallery_dir.is_dir():
        return []
    return [
        path
        for path in gallery_dir.iterdir()
        if path.is_file() and INTEGER_PATTERN.match(path.stem)
    ]


def _is_visible_picture(pic_file: Path, include_hidden: bool) -> bool:
    """判断图片是否对当前用户可见；无法归属到画廊的路径按不可见处理"""
    if include_hidden:
        return True
    try:
        return not is_gallery_hidden(_gallery_name_of(pic_file))
    except ValueError:
        return False


def _image_cache_dir() -> Path:
    """图片下载缓存目录"""
    # 延迟导入：require("nonebot_plugin_localstore") 必须先于本插件的任何直接导入
    from nonebot_plugin_localstore import get_plugin_cache_dir

    cache_dir = get_plugin_cache_dir() / "images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


async def _get_image_local(bot: OneBot, file: str) -> Path | None:
    """调用bot.get_image()获取file对应的图片，返回本机可读的图片路径

    协议实现可能返回网络路径（下载到缓存后返回），也可能返回协议端机器上的
    本地路径——协议端与 bot 不同机时该路径不可读，返回 None 交由调用方回退
    """
    r = await bot.get_image(file=file)
    file_url = r["file"]
    if file_url.startswith(("http://", "https://")):
        pic_path = _image_cache_dir() / file
        resp = await HTTPX_CLIENT.get(file_url)
        resp.raise_for_status()
        pic_path.write_bytes(resp.content)
        return pic_path

    path = Path(file_url)
    return path if path.is_file() else None


async def _get_image_from_url(url: str, file: str) -> Path | None:
    """从URL获取图片文件，返回图片文件路径"""
    r = await HTTPX_CLIENT.get(url)
    if r.status_code != 200:
        return None

    # 将图片保存到缓存目录
    pic_path = _image_cache_dir() / file
    pic_path.write_bytes(r.content)
    return pic_path


async def _get_pictures_from_message(
    bot: OneBot,
    message: OneBotMessage,
    *,
    forward_image: bool = False,
) -> list[Path]:
    """从消息中提取图片文件

    :param forward_image: 当前message是否为转发消息
        如果是，则使用http client获取图片附件，否则使用bot.get_image获取图片附件
    """
    pictures: list[Path] = []
    for seg in message:
        if seg.type == "image":
            p: Path | None = None
            file: str = seg.data["file"]
            if forward_image:
                # 转发消息中的图片，直接使用http client获取图片附件
                p = await _get_image_from_url(seg.data["url"], file)
            else:
                # 普通消息中的图片，使用bot.get_image获取图片附件
                try:
                    p = await _get_image_local(bot, file)
                except (ActionFailed, NetworkError) as e:
                    logger.warning(f"bot.get_image获取图片附件失败: {file}, {e}")
                    p = None
                if p is None and (url := seg.data.get("url")):
                    # 协议端不在本机或 get_image 失败，回退到 http 直接下载
                    p = await _get_image_from_url(url, file)
            if p:
                pictures.append(p)
            else:
                logger.warning(f"获取图片附件失败，消息段：{seg}")

        elif seg.type == "forward":
            _, fwd_msg_events = await get_forward_message_events(bot, seg)
            for e in fwd_msg_events:
                pictures.extend(
                    await _get_pictures_from_message(bot, e.message, forward_image=True)
                )
    return pictures


@add_picture.handle()
async def _(
    state: T_State,
    bot: OneBot,
    event: OneBotMessageEvent,
    arg_msg: Message = CommandArg(),
):
    args = parse_arg_message(
        arg_msg.extract_plain_text(),
        {"name_or_alias": str, "force": str},
        maxsplit=1,
    )
    name_or_alias: str | None = args["name_or_alias"]
    force_arg: str | None = args["force"]
    if not name_or_alias:
        await add_picture.finish("请提供画廊名称。")
    if force_arg is not None and force_arg.lower() != "force":
        await add_picture.finish("第二个参数仅支持 force，格式：<画廊名称> [force]")
    force = force_arg is not None
    name = get_gallery_name(name_or_alias)
    if not name:
        await add_picture.finish(f"未找到画廊：{name_or_alias}")
    await _ensure_gallery_editable(add_picture, bot, event, name)

    meta = PictureMeta(
        uploader_id=str(event.user_id),
        uploader_name=event.sender.nickname,
        added_at=datetime.now(),
    )

    # 获取引用的图片
    if event.reply:
        pic_paths = await _get_pictures_from_message(bot, event.reply.message)
        await _finish_add_pictures(name, pic_paths, force=force, meta=meta)

    # 获取消息中的图片
    pic_paths = await _get_pictures_from_message(bot, event.message)
    if pic_paths:
        await _finish_add_pictures(name, pic_paths, force=force, meta=meta)

    # pause，要求用户发送图片
    state["gallery_name"] = name
    state["gallery_force"] = force
    state["gallery_meta"] = meta
    await add_picture.pause(f"请发送要添加到画廊 {name} 的图片：")


@add_picture.handle()
async def _(
    state: T_State,
    bot: OneBot,
    event: OneBotMessageEvent,
    message: OneBotMessage = EventMessage(),
):
    pic_paths = await _get_pictures_from_message(bot, message)
    name = state["gallery_name"]
    meta: PictureMeta | None = state.get("gallery_meta")
    await _finish_add_pictures(
        name,
        pic_paths,
        force=state.get("gallery_force", False),
        meta=meta,
    )


async def _finish_add_pictures(
    name: str,
    pic_paths: list[Path],
    *,
    force: bool,
    meta: PictureMeta | None = None,
) -> None:
    result = await asyncio.to_thread(add_pictures, name, pic_paths, force=force)
    if result.saved_paths and meta is not None:
        # 只为成功入库（未被查重跳过）的图片记录元数据
        await asyncio.to_thread(
            get_picture_meta_index().record_many,
            result.saved_paths,
            meta,
        )
    response = OneBotMessage()
    if result.duplicate_image:
        response += OneBotMessageSegment.image(result.duplicate_image)
    response += OneBotMessageSegment.text(result.summary(name))
    await add_picture.finish(response)


@remove_picture.handle()
async def _(arg_msg: Message = CommandArg()):
    arg_str = arg_msg.extract_plain_text().strip()
    if not INTEGER_PATTERN.match(arg_str) or int(arg_str) < 0:
        await remove_picture.finish("请提供有效的图片id。")

    pic_id = int(arg_str)
    pic_path = get_picture_by_id(pic_id)
    if pic_path is None:
        await remove_picture.finish(f"未找到图片id {pic_id} 对应的图片文件。")

    # 将图片文件移至废纸篓
    try:
        send2trash(pic_path)
    except OSError as e:
        logger.exception(f"删除图片文件 {pic_path} 失败：{e}")
        await remove_picture.finish(f"删除图片文件失败：{e}")
    remove_picture_from_index(pic_path)
    get_picture_meta_index().remove(pic_path)
    gallery_name = _gallery_name_of(pic_path)
    invalidate_gallery_render_cache()
    invalidate_gallery_render_cache(gallery_name)
    await remove_picture.finish(f"成功删除图片 {pic_id}。")


@pic_info.handle()
async def _(
    bot: OneBot,
    event: OneBotMessageEvent,
    arg_msg: Message = CommandArg(),
):
    arg_str = arg_msg.extract_plain_text().strip()
    if not INTEGER_PATTERN.match(arg_str):
        await pic_info.finish("请提供有效的图片id。")
    include_hidden = await is_superuser(bot, event)
    resolved = await asyncio.to_thread(
        resolve_picture_index,
        int(arg_str),
        include_hidden=include_hidden,
    )
    pic_path = get_picture_by_id(resolved) if resolved is not None else None
    if pic_path is None or not _is_visible_picture(pic_path, include_hidden):
        await pic_info.finish(f"未找到图片id {arg_str} 对应的图片。")

    meta = await asyncio.to_thread(get_picture_meta_index().get, pic_path)
    gallery_name = _gallery_name_of(pic_path)
    lines = [f"图片 #{arg_str}（画廊 {gallery_name}）"]
    if meta.uploader_name or meta.uploader_id:
        lines.append(f"上传者：{meta.uploader_name or '未知'}({meta.uploader_id or '未知'})")
    if meta.added_at:
        lines.append(f"入库时间:{meta.added_at.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"标签：{' '.join('#' + t for t in meta.tags) or '无'}")
    if meta.source:
        lines.append(f"来源：{meta.source}")
    if meta.note:
        lines.append(f"备注：{meta.note}")
    await pic_info.finish("\n".join(lines))


@set_tags.handle()
async def _(
    bot: OneBot,
    event: OneBotMessageEvent,
    arg_msg: Message = CommandArg(),
):
    args = parse_arg_message(
        arg_msg.extract_plain_text(),
        {"pic_id": str, "tags": str},
        maxsplit=1,
    )
    pic_id_str: str | None = args["pic_id"]
    raw_tags: str | None = args["tags"]
    if not pic_id_str or not INTEGER_PATTERN.match(pic_id_str) or int(pic_id_str) < 0:
        await set_tags.finish("请提供有效的图片id，格式：打标签 <图片id> <标签1> <标签2> ...")
    include_hidden = await is_superuser(bot, event)
    pic_path = get_picture_by_id(int(pic_id_str))
    if pic_path is None or not _is_visible_picture(pic_path, include_hidden):
        await set_tags.finish(f"未找到图片id {pic_id_str} 对应的图片。")
    await _ensure_gallery_editable(set_tags, bot, event, _gallery_name_of(pic_path))

    tags = _normalize_tags(raw_tags or "")

    def apply(meta: PictureMeta) -> PictureMeta:
        meta.tags = tags
        return meta

    updated = await asyncio.to_thread(get_picture_meta_index().update, pic_path, apply)
    tag_text = " ".join("#" + t for t in updated.tags)
    await set_tags.finish(f"图片 #{pic_id_str} 标签已更新：{tag_text or '（已清空）'}")


@tag_search.handle()
async def _(
    bot: OneBot,
    event: OneBotMessageEvent,
    arg_msg: Message = CommandArg(),
):
    tokens = arg_msg.extract_plain_text().split()
    if not tokens:
        await tag_search.finish("请提供要搜索的标签，格式：搜标签 <标签1> [标签2...] [数量]")

    num = 1
    if len(tokens) > 1 and tokens[-1].isdigit() and int(tokens[-1]) >= 1:
        num = int(tokens[-1])
        tokens = tokens[:-1]
    tags = _normalize_tags(" ".join(tokens))
    if not tags:
        await tag_search.finish("请提供有效的标签。")
    if num > cfg.send_pic_limit:
        await tag_search.finish(f"每次最多发送 {cfg.send_pic_limit} 张图片。")

    matched = await asyncio.to_thread(get_picture_meta_index().find_by_tags, tags)
    include_hidden = await is_superuser(bot, event)
    matched = [path for path in matched if _is_visible_picture(path, include_hidden)]
    if not matched:
        wanted = " ".join("#" + t for t in tags)
        await tag_search.finish(f"没有找到带有标签 {wanted} 的图片。")

    message = await asyncio.to_thread(_build_pic_message, matched, min(num, len(matched)))
    await tag_search.finish(message)


_ACCESS_USAGE = (
    "用法：\n"
    "画廊权限：查看当前配置\n"
    "画廊权限 默认 <读写|只读|禁用>\n"
    "画廊权限 群 <群号|本群> <读写|只读|禁用|移除>\n"
    "画廊权限 用户 <QQ号|@某人> <读写|只读|禁用|移除>\n"
    "默认策略设为“禁用”即白名单模式；直接编辑数据目录下的权限 JSON 文件同样即时生效"
)


@gallery_access_ctrl.handle()
async def _(event: OneBotMessageEvent, arg_msg: Message = CommandArg()):
    tokens = arg_msg.extract_plain_text().split()
    config = access_data.current
    if not tokens:
        await gallery_access_ctrl.finish(format_access_config(config))

    kind = tokens[0]
    if kind in ("默认", "default"):
        policy = parse_policy_token(tokens[1]) if len(tokens) > 1 else None
        if policy is None:
            await gallery_access_ctrl.finish(_ACCESS_USAGE)
        config.default_policy = policy
        access_data.save()
        await gallery_access_ctrl.finish(f"默认策略已设为：{POLICY_LABELS[policy]}")

    target: str | None = None
    level_token: str | None = None
    if kind in ("群", "group"):
        table, kind_label = config.groups, "群"
        if len(tokens) > 2:
            target, level_token = tokens[1], tokens[2]
        if target == "本群":
            if not isinstance(event, GroupMessageEvent):
                await gallery_access_ctrl.finish("“本群”仅能在群聊中使用。")
            target = str(event.group_id)
    elif kind in ("用户", "user"):
        table, kind_label = config.users, "用户"
        at_ids = [str(seg.data["qq"]) for seg in arg_msg if seg.type == "at"]
        if at_ids:
            target = at_ids[0]
            level_token = tokens[1] if len(tokens) > 1 else None
        elif len(tokens) > 2:
            target, level_token = tokens[1], tokens[2]
    else:
        await gallery_access_ctrl.finish(_ACCESS_USAGE)

    if not target or not target.isdigit() or not level_token:
        await gallery_access_ctrl.finish(_ACCESS_USAGE)

    if is_remove_token(level_token):
        if table.pop(target, None) is None:
            await gallery_access_ctrl.finish(f"{kind_label} {target} 不在名单中。")
        access_data.save()
        await gallery_access_ctrl.finish(f"已将{kind_label} {target} 移出名单。")

    policy = parse_policy_token(level_token)
    if policy is None:
        await gallery_access_ctrl.finish(f"无法识别的策略：{level_token}\n{_ACCESS_USAGE}")
    table[target] = policy
    access_data.save()
    await gallery_access_ctrl.finish(
        f"已设置{kind_label} {target} 的画廊权限为：{POLICY_LABELS[policy]}"
    )


FOLD_LINE_THRESHOLD = 8
"""超过这个行数就在群聊里改用合并转发，避免长回复刷屏"""


async def _finish_long_text(
    matcher: type[Matcher],
    bot: OneBot,
    event: OneBotMessageEvent,
    text: str,
) -> None:
    lines = text.splitlines()
    if not isinstance(event, GroupMessageEvent) or len(lines) <= FOLD_LINE_THRESHOLD:
        await matcher.finish(text)

    node = OneBotMessageSegment.node_custom(
        user_id=int(bot.self_id),
        nickname="画廊",
        content=OneBotMessage(text),
    )
    try:
        await bot.send_group_forward_msg(group_id=event.group_id, messages=[node])
    except (ActionFailed, NetworkError, ValueError) as e:
        logger.warning(f"发送合并转发消息失败，回退为普通消息：{e}")
        await matcher.finish(text)
    await matcher.finish()


_MODE_USAGE = (
    "用法：\n"
    "画廊模式：列出所有非默认模式的画廊\n"
    "画廊模式 <画廊>：查看该画廊的模式\n"
    "画廊模式 <画廊> <读写|只读|关闭>\n"
    "只读：禁止非超级用户增删图片与别名；关闭：画廊对非超级用户完全不可见"
)


@gallery_mode_ctrl.handle()
async def _(
    bot: OneBot,
    event: OneBotMessageEvent,
    arg_msg: Message = CommandArg(),
):
    tokens = arg_msg.extract_plain_text().split()
    if not tokens:
        v = gallery_name_data.instance
        lines = [
            f"{name}：{MODE_LABELS[get_gallery_mode(name)]}"
            for name in v.name_to_aliases
            if get_gallery_mode(name) != "edit"
        ]
        if not lines:
            await gallery_mode_ctrl.finish(f"所有画廊均为默认模式（可读写）。\n{_MODE_USAGE}")
        await _finish_long_text(
            gallery_mode_ctrl,
            bot,
            event,
            "非默认模式的画廊：\n" + "\n".join(lines),
        )

    name = get_gallery_name(tokens[0])
    if not name:
        await gallery_mode_ctrl.finish(f"未找到画廊：{tokens[0]}")
    if len(tokens) == 1:
        await gallery_mode_ctrl.finish(
            f"画廊 {name} 当前模式：{MODE_LABELS[get_gallery_mode(name)]}"
        )

    mode = parse_mode_token(tokens[1])
    if mode is None:
        await gallery_mode_ctrl.finish(f"无法识别的模式：{tokens[1]}\n{_MODE_USAGE}")
    old_mode = get_gallery_mode(name)
    await asyncio.to_thread(set_gallery_mode, name, mode)
    await gallery_mode_ctrl.finish(
        f"画廊 {name} 模式：{MODE_LABELS[old_mode]} → {MODE_LABELS[mode]}"
    )


@set_gallery_cover_cmd.handle()
async def _(arg_msg: Message = CommandArg()):
    args = parse_arg_message(
        arg_msg.extract_plain_text(),
        {"name": str, "pic_id": str},
        maxsplit=1,
    )
    name_or_alias: str | None = args["name"]
    pic_id_str: str | None = args["pic_id"]
    if not name_or_alias or not pic_id_str:
        await set_gallery_cover_cmd.finish(
            "请提供画廊名称和图片id，格式：设置封面 <画廊> <图片id|清除>"
        )
    name = get_gallery_name(name_or_alias)
    if not name:
        await set_gallery_cover_cmd.finish(f"未找到画廊：{name_or_alias}")

    if pic_id_str in ("清除", "默认", "clear"):
        await asyncio.to_thread(clear_gallery_cover, name)
        await set_gallery_cover_cmd.finish(f"已清除画廊 {name} 的封面，将回退为 id 最小的图片。")

    if not INTEGER_PATTERN.match(pic_id_str) or int(pic_id_str) < 0:
        await set_gallery_cover_cmd.finish("请提供有效的图片id。")
    pic_id = int(pic_id_str)
    pic_path = get_picture_by_id(pic_id)
    if pic_path is None:
        await set_gallery_cover_cmd.finish(f"未找到图片id {pic_id} 对应的图片。")
    if _gallery_name_of(pic_path) != name:
        await set_gallery_cover_cmd.finish(f"图片 {pic_id} 不属于画廊 {name}。")

    await asyncio.to_thread(set_gallery_cover, name, pic_id)
    await set_gallery_cover_cmd.finish(f"已将图片 {pic_id} 设为画廊 {name} 的封面。")


@gallery_dedupe.handle()
async def _(
    bot: OneBot,
    event: OneBotMessageEvent,
    arg_msg: Message = CommandArg(),
):
    args = parse_arg_message(
        arg_msg.extract_plain_text(),
        {"name": str, "flag": str},
        maxsplit=1,
    )
    name_or_alias: str | None = args["name"]
    flag: str | None = args["flag"]
    if not name_or_alias:
        await gallery_dedupe.finish("请提供画廊名称，格式：画廊查重 <画廊> [rehash]")
    if flag is not None and flag.lower() != "rehash":
        await gallery_dedupe.finish(
            "第二个参数仅支持 rehash（强制重算全部哈希），格式：画廊查重 <画廊> [rehash]"
        )
    name = get_gallery_name(name_or_alias)
    if not name:
        await gallery_dedupe.finish(f"未找到画廊：{name_or_alias}")

    rehash = flag is not None
    await gallery_dedupe.send(
        f"正在扫描画廊 {name} 的重复图片{'（重算哈希，耗时较长）' if rehash else ''}……"
    )
    groups = await asyncio.to_thread(find_duplicate_groups, name, rehash=rehash)
    if not groups:
        await gallery_dedupe.finish(f"画廊 {name} 中没有检测到重复图片。")

    lines = [f"画廊 {name} 检测到 {len(groups)} 组重复图片（每组首个为最早入库的一张）："]
    lines += [" ".join(str(pic_id) for pic_id in group) for group in groups]
    lines.append("确认后可用「删除图片 <图片id>」逐个清理。")
    await _finish_long_text(gallery_dedupe, bot, event, "\n".join(lines))


def _write_gallery_archive(archive_path: Path, pic_files: list[Path]) -> float:
    """打包画廊图片并返回压缩包体积（MB）

    图片本身已是压缩格式，再做 deflate 只会白耗 CPU，因此用存储模式。
    """
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_STORED) as archive:
        for pic_file in sorted(pic_files):
            archive.write(pic_file, pic_file.name)
    return archive_path.stat().st_size / (1024 * 1024)


@export_gallery.handle()
async def _(
    bot: OneBot,
    event: OneBotMessageEvent,
    arg_msg: Message = CommandArg(),
):
    if not isinstance(event, GroupMessageEvent):
        await export_gallery.finish("导出画廊仅支持在群聊中使用。")
    name_or_alias = arg_msg.extract_plain_text().strip()
    if not name_or_alias:
        await export_gallery.finish("请提供画廊名称，格式：导出画廊 <画廊>")
    name = get_gallery_name(name_or_alias)
    if not name:
        await export_gallery.finish(f"未找到画廊：{name_or_alias}")
    pic_files = _gallery_picture_files(name)
    if not pic_files:
        await export_gallery.finish(f"画廊 {name} 中没有图片。")

    export_dir = cfg.cache_dir_path / "exports"
    archive_path = export_dir / f"{name}-{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    try:
        export_dir.mkdir(parents=True, exist_ok=True)
        # 先清理历史导出：协议端可能仍在读取本次文件，故只删旧的、留当前这份
        for stale in export_dir.glob("*.zip"):
            stale.unlink(missing_ok=True)
        size_mb = await asyncio.to_thread(_write_gallery_archive, archive_path, pic_files)
    except OSError as e:
        logger.exception(f"打包画廊 {name} 失败：{e}")
        await export_gallery.finish(f"打包画廊失败：{e}")

    await export_gallery.send(
        f"正在发送画廊 {name} 的 {len(pic_files)} 张图片（{size_mb:.2f} MB）……"
    )
    try:
        await bot.upload_group_file(
            group_id=event.group_id,
            file=str(archive_path),
            name=archive_path.name,
        )
    except (ActionFailed, NetworkError) as e:
        logger.exception(f"上传画廊 {name} 压缩包失败：{e}")
        await export_gallery.finish(
            f"上传压缩包失败：{e}\n协议端需与 bot 同机才能读取本地文件：{archive_path}"
        )
    await export_gallery.finish(f"画廊 {name} 已导出。")
