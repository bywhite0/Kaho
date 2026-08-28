from nonebot.plugin import PluginMetadata

from . import handler as handler
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="gallery",
    description="画廊：分组图库，支持别名、随机抽图、感知哈希查重、缩略图渲染",
    usage=(
        "添加画廊 <名称>（超级用户）\n"
        "删除画廊 <名称>（超级用户）\n"
        "添加画廊别名 <名称> <别名>\n"
        "删除画廊别名 <别名>（超级用户）\n"
        "看所有：画廊总览；看所有 <画廊>：该画廊图片列表\n"
        "看 <画廊> [数量] / 看 <图片id>：随机抽图或按 id 取图\n"
        "添加图片 <画廊> [force]：（引用消息/随命令发图/合并转发）入库并自动查重\n"
        "删除图片 <图片id>（超级用户）\n"
        "图片信息 <图片id>：查看图片元数据\n"
        "打标签 <图片id> <#标签...>：设置标签（替换式，留空清空）\n"
        "搜标签 <#标签...> [数量]：按标签随机抽图\n"
        "画廊权限 [默认|群|用户] ...（超级用户）：黑白名单读写控制，支持热更新"
    ),
    config=Config,
)
