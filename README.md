# paper-reading-skill

把一篇英文论文变成**保结构中文精读**：目录层级与图表和原文一一对应，图表用原图不变，正文大段英文总结为中文，输出**自包含单文件 HTML**。

给 AI Agent（Claude Code / Codex / Trae 等支持 SKILL.md 的宿主）用的技能包。

## 为什么需要它

现成的论文翻译插件（如 zotero-pdf-translate）做的是**逐段翻译**——篇幅和原文一样长，读起来还是英文的节奏；AI 聊天工具做的是**摘要**——丢掉章节结构和图表位置。两者都不能给你"像读中文版原文一样"的体验。

这个 skill 的取舍是：

| | 逐段翻译插件 | 通用摘要 | 本 skill |
|---|---|---|---|
| 目录结构 | 保持（PDF 内） | 丢失 | **保持** |
| 图表 | 保留 | 丢失 | **保留原图 + 中文译注** |
| 正文 | 全文翻译，篇幅不减 | 压成一段 | **逐节总结为中文，约 1/3 篇幅** |
| 交付物 | PDF 批注 | 对话文本 | **单文件 HTML，可分享/离线** |

## 安装

作为 Agent Skill 使用（推荐）：

```bash
git clone https://github.com/<你的用户名>/paper-reading-skill.git
# 放进宿主的 skills 目录，或直接用 npx skills add 指向本仓库
```

依赖：

```bash
pip install pymupdf
```

## 使用

对 Agent 说：

> 帮我把这篇论文做成保结构中文精读：`/path/to/paper.pdf`

或（需 Zotero 在运行 + [zotero-mcp](https://github.com/54yyyu/zotero-mcp) 已授权）：

> 把 Zotero 里条目 `ABC123XY` 做成保结构中文精读

Agent 会执行四步（详见 [SKILL.md](SKILL.md)）：

```bash
# 1. 提取结构、正文、图表原图
python3 scripts/extract.py --pdf paper.pdf --out ./paper-out
#    Zotero 方式： python3 scripts/extract.py --zotero-item ABC123XY --out ./paper-out
#    -> content.json（骨架）+ pages/*.txt（正文）+ assets/*.png（图表原图）

# 2. Agent 逐节读正文，把中文总结写进 content.json 的 sections[].zh
#    （这一步是 LLM 的活，脚本做不了）

# 3. 渲染
python3 scripts/render.py --content ./paper-out/content.json --out ./paper-out/paper-zh.html
```

## 产出长什么样

- 左侧栏目录，层级与原文一致（`level` 决定缩进）
- 正文全部为中文总结，保留关键数字、模型名、指标名
- 图 1–4 / 表 1–4 等图表按**原文所在章节**插入，为原图裁切，不做修改；原文图注保留并附中文译注
- 单文件 HTML，图片 base64 内嵌，可直接分享或离线打开

## 目录结构

```
.
├── SKILL.md              # 技能定义与流程说明（Agent 读这个）
├── scripts/
│   ├── extract.py        # PDF/Zotero -> content.json + pages/ + assets/
│   └── render.py         # content.json -> 自包含 HTML
└── examples/
    └── content.example.json
```

## 已知限制

- 图表定位依赖论文里的 `Figure N:` / `Table N:` 英文图注；**没有英文图注的图会漏掉**，需要在 `content.json` 里手工补。
- 图表裁切按 caption 上下方最近的图形区块推断，个别排版（图表跨栏、图注在图上方）可能需要手工微调。
- PDF 无内嵌书签时，章节靠字号启发式推断，准确性有限，建议人工校正。
- 中文总结质量取决于宿主 Agent 的模型能力，脚本只负责结构与渲染。

## 约束

- 只处理你有权使用的文献，产出物仅供个人阅读。
- 图表原图版权归原作者/出版方所有，请勿再分发原始图片。

## License

MIT（见 [LICENSE](LICENSE)）
