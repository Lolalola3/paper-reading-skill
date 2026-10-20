---
name: paper-reading
description: 把学术论文（本地 PDF，或 Zotero 条目键）转成「保结构中文精读」——完整保留原文目录层级与图表原图，把正文大段英文总结为中文呈现，输出自包含单文件 HTML。当用户提出论文精读、中文总结、英文文献翻译总结、paper reading、文献速读、把论文翻译成中文等需求时使用。
---

# 论文保结构中文精读

把一篇论文变成一份**结构与原文一致、图表保持原样、正文为中文总结**的单文件 HTML。

## 何时使用

- "帮我把这篇论文总结成中文""论文精读""英文文献翻译总结"
- "保持目录结构和图表不变，正文换成中文"
- 输入是本地 PDF 路径，或 Zotero 里的条目/附件键

## 输入

| 输入 | 说明 |
|---|---|
| PDF 路径 | `--pdf /path/to/paper.pdf` |
| Zotero 条目键 | `--zotero-item ABC123XY`（父条目或 PDF 附件键都可以，自动经 Zotero 本地 API 取回 PDF） |

依赖：`pip install pymupdf`。Zotero 方式额外要求 Zotero 客户端在运行，且已通过 zotero-mcp 完成本地写入授权（配置在 `~/.config/zotero-mcp/config.json`）。

## 流程

### 第 1 步：提取结构（脚本，不要手写）

```bash
python3 scripts/extract.py --pdf "<PDF路径>" --out ./paper-out
# 或
python3 scripts/extract.py --zotero-item <条目键> --out ./paper-out
```

产出：

- `paper-out/content.json` — 结构骨架：章节树（含页码区间）、图表清单（含图注）、待填字段
- `paper-out/pages/0001.txt …` — 逐页正文纯文本
- `paper-out/assets/*.png` — 按 caption 定位裁切的图表**原图**（3x 缩放，不做任何修改）

若提示"未检出目录结构"，说明 PDF 没有内嵌书签；改用字号推断结果，并**人工校正 `content.json` 的 sections**（章节是这份交付物的骨架，值得花时间对齐）。

### 第 2 步：读正文，写中文总结（这一步是 Agent 的活，脚本做不了）

按 `sections[]` 逐节读 `pages/NNNN.txt` 里对应页码范围，把**大段英文正文总结为中文**，写入该节的 `zh` 数组：

```json
{
  "id": "s-3", "level": 1, "title_en": "PatientAgentBench", "title_zh": "3 PatientAgentBench 框架",
  "page_start": 5, "page_end": 7,
  "zh": [
    "框架端到端分为三个阶段（见图 2）：……",
    {"fig": "figure2"},
    "阶段 1 基准生成……"
  ]
}
```

- `zh` 元素是**字符串**（一个段落）或 **`{"fig": "figure1"}`**（在此处插入图表，`fig` 与 `table` 等价）
- `title_zh` 留空则用 `title_en` 原文标题
- 图表的 `caption_zh` 填写图注中文译注（`caption_en` 为原文图注，会一并保留）

**写作规范**：

1. **总结，不是逐句翻译**。压缩到原文的 1/3 左右篇幅，保留论证链与关键细节。
2. **数字、模型名、指标名一律保留原文**（如 "1,200 条"、"Claude Opus 4.8"、"4.25/5"、"79%–93%"）。这是精读最有价值的部分，不要模糊成"表现良好"。
3. **术语首次出现保留英文**：如"LLM 陪审团（LLM-as-a-Jury）"。
4. **补齐代词指涉**：把 "this method" 之类还原成具体名词，中文里才读得通。
5. **不要编造**。正文没说的不要补。附录、致谢、参考文献可只做清单化概述。
6. 用 `**粗体**` 强调关键结论，渲染时会转成 `<strong>`。

### 第 3 步：渲染

```bash
python3 scripts/render.py --content ./paper-out/content.json --out ./paper-out/paper-zh.html
```

输出自包含单文件 HTML（图表 base64 内嵌，离线可开）。脚本会提示还有哪些章节 `zh` 为空。

### 第 4 步：验收

用浏览器实际打开，确认：目录层级与原文一致、图表都在正确章节且清晰可读、无破图、无控制台报错。图表若裁切不准（缺边、混入正文），回到 `content.json` 手工调整对应图表，或在 `extract.py` 里调整 `--zoom`。

## content.json 字段速查

| 字段 | 含义 |
|---|---|
| `title` / `subtitle` | 文档标题 / 副标题 |
| `sections[]` | 章节数组，`level` 决定 `<h2>/<h3>/<h4>` 与目录缩进 |
| `sections[].page_start/end` | 该节对应的 PDF 页码区间（1-based） |
| `sections[].zh` | **待填**：中文总结段落与图表插入点 |
| `sections[].figures` | 自动归属到该节的图表 id；若已在 `zh` 里显式引用则不会重复 |
| `figures[]` | 图表：`id` / `kind` / `num` / `page` / `image` / `caption_en` / `caption_zh` |

## 可选：写回 Zotero 笔记

若要把结果存成 Zotero 笔记，有两个**必须避开的坑**（都是实际踩过的）：

1. **笔记内容必须以块级标签开头**（`div` / `p` / `h1`-`h6` / `ul` / `ol` / `table` / `pre` / `blockquote`）。zotero-mcp 的 `to_note_html()` 用这个规则判断输入是 HTML 还是 Markdown；若以 `<header>`、`<section>` 之类开头，会被当成 Markdown 处理，导致这些标签被**转义成可见文本**（笔记里出现 `</section>` 字样）。同时只使用笔记编辑器允许的标签，去掉 `class`/`id`。
2. **图片必须用 `data-attachment-key` 指向 Zotero 库内的 stored 附件**，不能用 base64 `data:` URI（渲染尺寸会异常），也不能用 linked_file 附件（不显示，只剩 alt 文字）。而 `zotero_attach_file` 只接受文档类型、拒绝图片，所以图片要走 Zotero 本地 API 的三阶段上传：

```
1) POST /api/users/0/items/<attachKey>/file   If-None-Match: *
   表单体 md5=&filename=&filesize=&mtime=(毫秒)      -> {url, uploadKey, prefix, suffix}
2) POST <url>   (prefix + 文件字节 + suffix)
3) POST /api/users/0/items/<attachKey>/file   表单体 upload=<uploadKey>   -> 204
```

鉴权头：`Zotero-API-Version: 3`、`Zotero-Server-ID`、`Zotero-API-Key`（后两个取自 `~/.config/zotero-mcp/config.json` 的 `local_api`）。

注意：Zotero 笔记**不渲染自定义 CSS、不支持锚点跳转**，所以网页版那套侧栏目录在笔记里会退化成普通文本列表——若不接受，就不要把精读版写回笔记，直接交付 HTML。
