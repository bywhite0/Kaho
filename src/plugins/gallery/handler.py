import asyncio
import random
import re
from datetime import datetime
from pathlib import Path

from nonebot import logger
from nonebot.adapters import Message
from nonebot.adapters.onebot.v11 import Bot as OneBot
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.adapters.onebot.v11 import Message as OneBotMessage
from nonebot.adapters.onebot.v11 import MessageEvent as OneBotMessageEvent
from nonebot.adapters.onebot.v11 import MessageSegment as OneBotMessageSegment
from nonebot.exception import NetworkError
from nonebot.params import CommandArg, EventMessage
from nonebot.typing import T_State
from send2trash import send2trash

from .access import access_data, format_access_config
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
    get_gallery_name,
    get_picture_by_id,
    invalidate_gallery_render_cache,
    remove_gallery_from_index,
    remove_picture_from_index,
    render_gallery_overview,
    render_gallery_thumbnails,
)
from .matcher import (
    add_gallery,
    add_gallery_alias,
    add_picture,
    gallery_access_ctrl,
    gallery_pictures,
    get_picture,
    pic_info,
    remove_gallery,
    remove_gallery_alias,
    remove_picture,
    set_tags,
    tag_search,
)
from .meta import PictureMeta, get_picture_meta_index


@add_gallery.handle()
async def _(arg_msg: Message = CommandArg()):
    name = arg_msg.extract_plain_text().strip()
    if not name:
        await add_gallery.finish("请提供画廊名称。")

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
    gallery_name_data.save_to_file()
    remove_gallery_from_index(name)
    get_picture_meta_index().remove_gallery(name)
    invalidate_gallery_render_cache()
    invalidate_gallery_render_cache(name)
    await remove_gallery.finish(f"成功删除画廊：{name}")


@add_gallery_alias.handle()
async def _(arg_msg: Message = CommandArg()):
    args = parse_arg_message(
        arg_msg.extract_plain_text().strip(),
        {"name": str, "alias": str},
        maxsplit=1,
    )
    name: str | None = args["name"]
    alias: str | None = args["alias"]

    if not name or not alias:
        await add_gallery_alias.finish("请提供画廊名称和别名，格式：<画廊名称> <别名>")
    v = gallery_name_data.instance
    if name not in v.name_to_aliases:
        await add_gallery_alias.finish(f"画廊 {name} 不存在。")
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
    await add_gallery_alias.finish(f"成功为画廊 {name} 添加别名：{alias}")


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
async def _(arg_msg: Message = CommandArg()):
    name_or_alias = arg_msg.extract_plain_text().strip()
    if not name_or_alias:
        image = await asyncio.to_thread(render_gallery_overview)
        if not image:
            await gallery_pictures.finish("当前没有画廊。")
        await gallery_pictures.finish(OneBotMessageSegment.image(image))

    name = get_gallery_name(name_or_alias)
    if not name:
        await gallery_pictures.finish(f"未找到画廊：{name_or_alias}")

    gallery_dir = cfg.data_dir_path / name
    if not gallery_dir.is_dir():
        logger.warning(f"画廊索引中存在画廊名称 {name}，但对应的目录不存在：{gallery_dir}")
        await gallery_pictures.finish(f"画廊 {name} 的目录不存在。")

    pic_files = [path for path in gallery_dir.iterdir() if path.is_file()]
    if not pic_files:
        await gallery_pictures.finish(f"画廊 {name} 中没有图片。")

    image = await asyncio.to_thread(render_gallery_thumbnails, name, pic_files)
    if not image:
        await gallery_pictures.finish(f"画廊 {name} 中没有可读取的图片。")
    await gallery_pictures.finish(OneBotMessageSegment.image(image))


@get_picture.handle()
async def _(bot: OneBot, arg_msg: Message = CommandArg()):
    arg_str = arg_msg.extract_plain_text().strip()
    if not arg_str:
        await get_picture.finish("请提供画廊名称或图片id。")

    args = re.split(r"[x*×\s]+", arg_str, maxsplit=1)
    if not args or len(args) < 1:
        await get_picture.finish("请提供画廊名称。")
    arg1: str = args[0]

    name = get_gallery_name(arg1)
    if not name:
        if not arg1.isdigit():
            await get_picture.finish(f"未找到画廊：{arg1}")
        # 尝试按图片id获取图片
        if not (pic_file := get_picture_by_id(int(arg1))):
            await get_picture.finish(f"未找到图片id {arg1} 对应的图片。")
        if cfg.send_pic_as_meme:
            await get_picture.finish(meme_image_segment(pic_file))
        else:
            await get_picture.finish(OneBotMessageSegment.image(pic_file))

    num = 1
    if len(args) > 1 and args[1].isdigit():
        num = int(args[1])
    gallery_dir = cfg.data_dir_path / name
    pic_files = list(gallery_dir.glob("*"))
    if not pic_files:
        await get_picture.finish(f"画廊 {name} 中没有图片。")

    if num < 1:
        await get_picture.finish("请提供有效的图片数量。")
    if num > cfg.send_pic_limit:
        await get_picture.finish(f"每次最多发送 {cfg.send_pic_limit} 张图片。")

    await get_picture.finish(_build_pic_message(pic_files, num))


def _normalize_tags(raw: str) -> list[str]:
    """归一化标签：去掉 # 前缀，去空去重，保持顺序"""
    normalized: list[str] = []
    for token in raw.split():
        tag = token.strip().lstrip("#").strip()
        if tag and tag not in normalized:
            normalized.append(tag)
    return normalized


def _build_pic_message(pic_files: list[Path], num: int) -> OneBotMessage:
    """从候选图片中随机抽取 num 张组装成消息"""
    message = OneBotMessage()
    for _ in range(num):
        pic_file = random.choice(pic_files)
        if cfg.send_pic_as_meme:
            message += meme_image_segment(pic_file)
        else:
            message += OneBotMessageSegment.image(pic_file)
    return message


def _image_cache_dir() -> Path:
    """图片下载缓存目录"""
    # 延迟导入：require("nonebot_plugin_localstore") 必须先于本插件的任何直接导入
    from nonebot_plugin_localstore import get_plugin_cache_dir

    cache_dir = get_plugin_cache_dir() / "images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


async def _get_image_local(bot: OneBot, file: str) -> Path:
    """调用bot.get_image()获取file对应的本地图片路径

    部分协议实现可能返回网络路径，此函数会将其下载到本地缓存目录并返回本地路径
    """
    r = await bot.get_image(file=file)
    file_url = r["file"]
    if not file_url.startswith(("http://", "https://")):
        return Path(file_url)

    pic_path = _image_cache_dir() / file
    resp = await HTTPX_CLIENT.get(file_url)
    resp.raise_for_status()
    pic_path.write_bytes(resp.content)
    return pic_path


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
                except NetworkError as e:
                    logger.warning(f"bot.get_image获取图片附件失败: {file}, {e}")
                    # 回退到使用http client获取图片附件
                    p = await _get_image_from_url(seg.data["url"], file)
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
    if not arg_str.isdigit():
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
    gallery_name = str(pic_path.parent.relative_to(cfg.data_dir_path))
    invalidate_gallery_render_cache()
    invalidate_gallery_render_cache(gallery_name)
    await remove_picture.finish(f"成功删除图片 {pic_id}。")


@pic_info.handle()
async def _(arg_msg: Message = CommandArg()):
    arg_str = arg_msg.extract_plain_text().strip()
    if not arg_str.isdigit():
        await pic_info.finish("请提供有效的图片id。")
    pic_path = get_picture_by_id(int(arg_str))
    if pic_path is None:
        await pic_info.finish(f"未找到图片id {arg_str} 对应的图片。")

    meta = await asyncio.to_thread(get_picture_meta_index().get, pic_path)
    gallery_name = pic_path.parent.relative_to(cfg.data_dir_path).as_posix()
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
async def _(arg_msg: Message = CommandArg()):
    args = parse_arg_message(
        arg_msg.extract_plain_text(),
        {"pic_id": str, "tags": str},
        maxsplit=1,
    )
    pic_id_str: str | None = args["pic_id"]
    raw_tags: str | None = args["tags"]
    if not pic_id_str or not pic_id_str.isdigit():
        await set_tags.finish("请提供有效的图片id，格式：打标签 <图片id> <标签1> <标签2> ...")
    pic_path = get_picture_by_id(int(pic_id_str))
    if pic_path is None:
        await set_tags.finish(f"未找到图片id {pic_id_str} 对应的图片。")

    tags = _normalize_tags(raw_tags or "")

    def apply(meta: PictureMeta) -> PictureMeta:
        meta.tags = tags
        return meta

    updated = await asyncio.to_thread(get_picture_meta_index().update, pic_path, apply)
    tag_text = " ".join("#" + t for t in updated.tags)
    await set_tags.finish(f"图片 #{pic_id_str} 标签已更新：{tag_text or '（已清空）'}")


@tag_search.handle()
async def _(arg_msg: Message = CommandArg()):
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
    if not matched:
        wanted = " ".join("#" + t for t in tags)
        await tag_search.finish(f"没有找到带有标签 {wanted} 的图片。")

    message = _build_pic_message(matched, min(num, len(matched)))
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
