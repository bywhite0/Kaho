from nonebot import on_command
from nonebot.permission import SUPERUSER

from .access import GALLERY_ADMIN, gallery_readable, gallery_writable

add_gallery = on_command(
    "添加画廊",
    aliases={"add_gallery"},
    rule=gallery_writable,
    priority=2,
    permission=GALLERY_ADMIN,
    block=True,
)

remove_gallery = on_command(
    "删除画廊",
    aliases={"remove_gallery"},
    rule=gallery_writable,
    priority=2,
    permission=SUPERUSER,
    block=True,
)

add_gallery_alias = on_command(
    "添加画廊别名",
    aliases={"add_gallery_alias", "添加别名"},
    rule=gallery_writable,
    priority=2,
    block=True,
)

remove_gallery_alias = on_command(
    "删除画廊别名",
    aliases={"remove_gallery_alias", "删除别名"},
    rule=gallery_writable,
    priority=2,
    permission=GALLERY_ADMIN,
    block=True,
)

gallery_pictures = on_command(
    "看所有",
    aliases={"gallery_pictures", "画廊图片列表", "图片一览"},
    rule=gallery_readable,
    priority=2,
    block=True,
)

get_picture = on_command(
    "获取图片",
    aliases={"get_picture", "看"},
    rule=gallery_readable,
    priority=3,
    block=True,
)

add_picture = on_command(
    "添加图片",
    aliases={"add_picture", "上传图片", "上传"},
    rule=gallery_writable,
    priority=2,
    block=True,
)

remove_picture = on_command(
    "删除图片",
    aliases={"remove_picture"},
    rule=gallery_writable,
    priority=2,
    permission=GALLERY_ADMIN,
    block=True,
)

pic_info = on_command(
    "图片信息",
    aliases={"pic_info", "图片详情"},
    rule=gallery_readable,
    priority=3,
    block=True,
)

set_tags = on_command(
    "打标签",
    aliases={"set_tags"},
    rule=gallery_writable,
    priority=2,
    block=True,
)

tag_search = on_command(
    "搜标签",
    aliases={"tag_search"},
    rule=gallery_readable,
    priority=3,
    block=True,
)

gallery_access_ctrl = on_command(
    "画廊权限",
    aliases={"gallery_access"},
    priority=2,
    permission=SUPERUSER,
    block=True,
)

gallery_mode_ctrl = on_command(
    "画廊模式",
    aliases={"gallery_mode"},
    rule=gallery_writable,
    priority=2,
    permission=SUPERUSER,
    block=True,
)

set_gallery_cover_cmd = on_command(
    "设置封面",
    aliases={"gallery_cover", "画廊封面"},
    rule=gallery_writable,
    priority=2,
    permission=GALLERY_ADMIN,
    block=True,
)

gallery_dedupe = on_command(
    "画廊查重",
    aliases={"gallery_dedupe"},
    rule=gallery_writable,
    priority=2,
    permission=GALLERY_ADMIN,
    block=True,
)

export_gallery = on_command(
    "导出画廊",
    aliases={"gallery_export"},
    rule=gallery_writable,
    priority=2,
    permission=SUPERUSER,
    block=True,
)
