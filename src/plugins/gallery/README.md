# nonebot_plugin_gallery

移植自 [kanade-bot](https://github.com/njdldkl666699/kanade-bot) 的画廊插件，已剥离全部宿主框架依赖，可直接用于任意 NoneBot2 + OneBot v11 项目。

## 功能

- 画廊分组管理 + 别名系统 + 画廊级开放模式（可读写 / 只读 / 关闭）
- 随机抽图（同一批内不重复）、按全局图片 ID 取图（可一次取多张，负数取最新入库）
- 添加图片自动查重（MD5 精确 + dHash/pHash/aHash 感知哈希，透明图统一按白底比较），重复图渲染对比图返回
- 全库补扫已存在的重复图片，可强制重算全部哈希
- 支持引用消息 / 随命令发图 / 合并转发三种入库方式
- PIL 渲染画廊总览与缩略图墙（带磁盘缓存），封面可指定
- 按群/用户的黑白名单读写控制（读写/只读/禁用），配置文件热更新
- 打包画廊为 zip 上传群文件

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

`gallery_name_indices.json` 保存画廊名到别名、模式、封面的映射以及图片 id 自增计数。`name_to_mode` 与 `name_to_cover` 缺省即默认值（可读写、以 id 最小的图作封面）；手工把模式改成无法识别的值只会让该画廊回退默认，不会导致整份索引加载失败。

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
| 看 \<画廊\> [xN] | 所有人 | 随机抽图，同一批内不重复 |
| 看 \<图片id...\> | 所有人 | 按 id 取图，可一次给多个；`-1` 为最新入库的一张，`-2` 次新 |
| 添加图片 \<画廊\> [force] | 所有人 | force 跳过查重强制入库 |
| 删除图片 \<图片id\> | 超级用户 | |
| 图片信息 \<图片id\> | 所有人 | 查看上传者/时间/标签等元数据 |
| 打标签 \<图片id\> \<#标签...\> | 所有人 | 替换式设置标签，留空即清空 |
| 搜标签 \<#标签...\> [数量] | 所有人 | 按标签（AND 语义）随机抽图 |
| 画廊模式 [画廊] [模式] | 超级用户 | 查看或设置画廊开放模式，见下节 |
| 设置封面 \<画廊\> \<图片id\|清除\> | 超级用户 | 指定总览图使用的封面 |
| 画廊查重 \<画廊\> [rehash] | 超级用户 | 补扫库内已存在的重复图片 |
| 导出画廊 \<画廊\> | 超级用户（仅群聊） | 打包 zip 上传到群文件 |
| 画廊权限 ... | 超级用户 | 黑白名单读写控制，见下节 |

画廊名称与别名的限制：长度 ≤ 32；不能含空白字符（命令按空白分割参数）、控制字符、`<>:"/\|?*`；不能是纯数字（否则与图片 id 冲突）；不能以 `.` 结尾或撞上 Windows 保留设备名（CON/NUL/COM1…）。

## 画廊模式

与黑白名单**正交**：黑白名单管"谁能操作"，画廊模式管"这个画廊能被怎么操作"。超级用户不受模式限制。

| 模式 | 含义 |
|---|---|
| `edit`（可读写） | 默认；全部命令可用 |
| `view`（只读） | 禁止添加/删除图片、打标签、添加别名；查看类命令照常 |
| `off`（已关闭） | 对非超级用户完全不可见：不出现在总览，按名称或图片 id 访问一律回"未找到" |

```
画廊模式                    # 列出所有非默认模式的画廊
画廊模式 表情包              # 查看单个画廊的模式
画廊模式 表情包 只读         # 设置
```

模式词支持中英文：`edit`/`读写`/`正常`/`可写`/`开放`、`view`/`只读`/`查看`/`锁定`、`off`/`关闭`/`隐藏`/`下架`。

`off` 画廊只对超级用户可见，因此总览图按可见范围缓存两份（`overview.png` 与 `overview_all.png`），任何画廊改动都会同时清掉两份。

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

## 查重与哈希索引

入库查重先比 MD5（文件完全一致），再比 dHash/pHash/aHash 三种感知哈希，阈值 `(8, 2, 2)` 中至少两项达标才判定重复；纯色等低方差图片会放弃感知比较，避免把所有纯色图判成同一张。

计算指纹前会把带透明通道的图片（含 `P` 模式的透明 GIF）合成到**纯白背景**——PIL 的 RGBA→L 转换会丢弃 alpha 并把透明像素当成黑色，同一张表情包的透明 PNG 与白底 JPG 会因此得到完全不同的指纹而漏判重复。

哈希缓存在缓存目录的 `image_index_v2.json`，按文件大小与 mtime 自动失效。**改动哈希算法时必须递增文件名里的版本号**，否则旧指纹会与新指纹混在同一次比较里；插件加载时会自动删除旧版本的索引文件。

`画廊查重 <画廊>` 用同一套阈值补扫库内已经存在的重复（force 强制入库、阈值调整、算法升级都会留下漏网的），输出按最早入库的一张分组；加 `rehash` 会先丢弃该画廊的哈希缓存强制重算。

## 测试

```
cd src/plugins/gallery/tests && python run_tests.py
```

先在本进程跑纯逻辑用例（名称校验、权限策略、查重指纹），再以子进程方式跑需要 NoneBot 运行时的状态用例与插件加载冒烟。

不要用 pytest 直接收集这个目录：插件包带 `__init__.py`，pytest 会为构造模块名而导入 `src.plugins.gallery`，触发尚未初始化的 NoneBot 依赖，整批用例在 collect 阶段就失败。

## 二次开发对接点

核心 API 全部在 `gallery.py`，与适配器解耦，可在自己插件中直接 import：

```python
import asyncio
from nonebot_plugin_gallery.gallery import (
    add_pictures,            # 入库（含查重）-> AddPicturesResult
    find_duplicate_pictures, # 纯查重
    find_duplicate_groups,   # 全库补扫重复 -> list[list[图片id]]
    get_picture_by_id,       # id -> Path
    get_gallery_name,        # 名称/别名解析
    get_gallery_mode,        # -> "edit" | "view" | "off"
    set_gallery_mode,
    list_picture_ids,        # 升序全部图片 id
    resolve_picture_index,   # 负数索引 -> 真实图片 id
    invalidate_gallery_render_cache,
)

result = await asyncio.to_thread(add_pictures, "画廊名", [Path("x.png")])
```

注意事项：
- 这些函数是同步阻塞 IO，务必经 `asyncio.to_thread` 调用
- `gallery_name_data.instance` 写入无锁，避免并发任务同时写注册表
- 图片 ID 为全局自增（跨画廊唯一），文件名为 `{id}{后缀}`；画廊目录里不以图片 id 命名的文件会被忽略
- 校验画廊名/别名请用 `names.validate_gallery_name`，识别图片 id 请用 `names.INTEGER_PATTERN`——两边共用同一套形式，才不会出现"画廊名遮蔽图片 id"
- `list_picture_ids` / `resolve_picture_index` 默认排除 `off` 画廊，给超级用户取图时传 `include_hidden=True`
