# nonebot_plugin_gallery

移植自 [kanade-bot](https://github.com/njdldkl666699/kanade-bot) 的画廊插件，已剥离全部宿主框架依赖，可直接用于任意 NoneBot2 + OneBot v11 项目。

## 功能

- 画廊分组管理 + 别名系统
- 随机抽图、按全局图片 ID 取图
- 添加图片自动查重（MD5 精确 + dHash/pHash/aHash 感知哈希），重复图渲染对比图返回
- 支持引用消息 / 随命令发图 / 合并转发三种入库方式
- PIL 渲染画廊总览与缩略图墙（带磁盘缓存）
- 按群/用户的黑白名单读写控制（读写/只读/禁用），配置文件热更新

## 依赖安装

```
pip install nonebot-plugin-localstore pillow emoji httpx send2trash
```

另需项目中已装好 `nonebot2` 与 `nonebot-adapter-onebot`。

## 接入方式

把整个 `nonebot_plugin_gallery` 文件夹复制进你项目的插件目录（如 `src/plugins/`），或在 `.env.*` 的 `PLUGIN_DIRS` 能覆盖到的位置即可。无需在 `pyproject.toml` 注册。

## 配置（可选）

在 `.env.*` 中：

```yaml
GALLERY__SEND_PIC_LIMIT: 10        # 单次抽图上限
GALLERY__SEND_PIC_AS_MEME: true    # 以表情包形式发图
GALLERY__SEND_PIC_MODE: base64     # 发图方式：base64 内联字节（协议端异机可用）/ path 直发本地路径（需协议端同机，开销更低）
GALLERY__NAME_DATA_FILE: gallery_name_indices.json
GALLERY__ACCESS_DATA_FILE: gallery_access.json   # 黑白名单数据文件名
```

数据存储于 localstore 目录：`.data/plugins/nonebot_plugin_gallery/`（每个画廊一个子目录），缓存于 `.cache/plugins/nonebot_plugin_gallery/`。

**从 kanade-bot 迁移旧数据**：把旧项目 `.data/plugins/gallery/` 下内容整体拷入上述数据目录即可；缓存目录不用迁（哈希索引与渲染图均可自动重建）。

## 命令

命令受 NoneBot `COMMAND_START` 配置影响（如配置了 `/` 则需加前缀）。

| 命令 | 权限 | 说明 |
|---|---|---|
| 添加画廊 \<名称\> | 超级用户 | 创建画廊 |
| 删除画廊 \<名称\> | 超级用户 | 删除（移入回收站） |
| 添加画廊别名 \<名称\> \<别名\> | 所有人 | |
| 删除画廊别名 \<别名\> | 超级用户 | |
| 看所有 [画廊] | 所有人 | 无参=总览图；带名=该画廊图片墙 |
| 看 \<画廊\> [数量] / 看 \<图片id\> | 所有人 | 随机抽图 / 按 id 取图 |
| 添加图片 \<画廊\> [force] | 所有人 | force 跳过查重强制入库 |
| 删除图片 \<图片id\> | 超级用户 | |
| 图片信息 \<图片id\> | 所有人 | 查看上传者/时间/标签等元数据 |
| 打标签 \<图片id\> \<#标签...\> | 所有人 | 替换式设置标签，留空即清空 |
| 搜标签 \<#标签...\> [数量] | 所有人 | 按标签（AND 语义）随机抽图 |
| 画廊权限 ... | 超级用户 | 黑白名单读写控制，见下节 |

## 黑白名单 / 读写权限（热更新）

按**用户**与**群聊**控制画廊的使用权限，三档策略：

| 策略 | 含义 |
|---|---|
| `rw`（读写） | 全部命令可用（默认） |
| `ro`（只读） | 仅可用读命令：看所有、看、图片信息、搜标签 |
| `deny`（禁用） | 所有画廊命令静默不响应 |

判定顺序：**超级用户豁免 → 用户名单 → 群名单 → 默认策略**。把默认策略设为 `deny` 即白名单模式（只有名单中的群/用户可用）。命中限制时插件不回复任何消息（防刷屏）。

两种修改方式，均**即时生效、无需重启**：

1. **超级用户命令**：

   ```
   画廊权限                      # 查看当前配置
   画廊权限 默认 只读             # 设置默认策略（读写/只读/禁用）
   画廊权限 群 123456 只读        # 群内所有人只读；群聊中可用 "本群" 指代
   画廊权限 用户 888888 拉黑      # 拉黑用户（也可直接 @某人）
   画廊权限 群 123456 移除        # 移出名单，恢复默认策略
   ```

   策略词支持中英文：`rw`/`读写`/`正常`、`ro`/`只读`、`deny`/`禁用`/`拉黑`/`黑名单`、`移除`/`删除`/`remove`。

2. **直接编辑数据文件**：数据目录下 `gallery_access.json`（文件名可经 `GALLERY__ACCESS_DATA_FILE` 配置），保存后下一条消息即按新配置判定（基于 mtime 检测热重载）：

   ```json
   {
     "default_policy": "rw",
     "users": { "888888": "deny" },
     "groups": { "123456": "ro" }
   }
   ```

   JSON 写坏时保留上一份有效配置并在日志报错；删除文件则回退为全默认（全部可读写）。

## 图片元数据

入库时自动记录**上传者 ID/昵称**与**入库时间**；标签、备注、来源可通过命令维护。

存储位置：数据目录下 `picture_meta_v1.json`（相对路径做键）。它与缓存目录中可重建的哈希索引完全独立——清空缓存不会丢失任何元数据。删除图片/画廊时会同步清理对应条目。

扩展自定义字段只需给 `PictureMeta` 增加带默认值的字段（`meta.py`），旧 JSON 文件可直接加载，无需迁移：

```python
from nonebot_plugin_gallery.meta import (
    PictureMeta, get_picture_meta_index,
)

idx = get_picture_meta_index()
idx.get(pic_path)                       # -> PictureMeta
idx.record_many([path], PictureMeta(uploader_id="123", added_at=datetime.now()))
idx.update(path, lambda m: (setattr(m, "note", "好图"), m)[1])
paths = idx.find_by_tags(["猫", "memes"])  # AND 语义
```

## 二次开发对接点

核心 API 全部在 `gallery.py`，与适配器解耦，可在自己插件中直接 import：

```python
import asyncio
from nonebot_plugin_gallery.gallery import (
    add_pictures,            # 入库（含查重）-> AddPicturesResult
    find_duplicate_pictures, # 纯查重
    get_picture_by_id,       # id -> Path
    get_gallery_name,        # 名称/别名解析
    invalidate_gallery_render_cache,
)

result = await asyncio.to_thread(add_pictures, "画廊名", [Path("x.png")])
```

注意事项：
- 这些函数是同步阻塞 IO，务必经 `asyncio.to_thread` 调用
- `gallery_name_data.instance` 写入无锁，避免并发任务同时写注册表
- 图片 ID 为全局自增（跨画廊唯一），文件名为 `{id}{后缀}`
