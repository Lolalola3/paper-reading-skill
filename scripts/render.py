#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render.py — 把 content.json（含 Agent 填好的中文总结）渲染成单文件 HTML 精读版

用法:
  python3 render.py --content ./out/content.json --out ./out/paper-zh.html

规则:
  - 目录层级、章节顺序完全来自 content.json（即原文目录结构）
  - 图表为 assets/ 下的原图，按 sections[].zh 中 {"fig": "figure1"} 的位置插入，保持原文位置
  - 输出为自包含单文件（图片 base64 内嵌），可直接分享/离线打开
"""
import argparse, base64, html, json, os, re

KIND_ZH = {"Figure": "图", "Table": "表"}


def esc(t):
    """转义 HTML，并支持 **粗体** 与换行。"""
    t = html.escape(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return t.replace("\n", "<br>")


def figure_html(fig, assets, num_label):
    p = os.path.join(assets, os.path.basename(fig["image"]))
    if not os.path.exists(p):
        return f'<figure class="fig"><figcaption><span class="tag">{num_label}</span> 原图缺失（{fig["image"]}）</figcaption></figure>'
    b64 = base64.b64encode(open(p, "rb").read()).decode()
    cap_en = esc(fig.get("caption_en", "")).replace("**", "")
    cap_zh = esc(fig.get("caption_zh", "")).strip()
    zh_part = f'<br><span class="cap-zh">译注：{cap_zh}</span>' if cap_zh else ""
    return (f'<figure class="fig">\n  <img src="data:image/png;base64,{b64}" alt="{num_label}">\n'
            f'  <figcaption><span class="tag">{num_label}</span> <span class="cap-en">{cap_en}</span>{zh_part}</figcaption>\n</figure>')


def build(content, assets):
    figs = {f["id"]: f for f in content.get("figures", [])}
    secs = content["sections"]

    nav = ""
    for s in secs:
        lvl = max(0, min(2, int(s.get("level", 1)) - 1))
        label = s.get("title_zh") or s.get("title_en", "")
        en = s.get("title_en", "")
        if s.get("title_zh") and en and en not in label:
            label = f'{label} <span class="nav-en">{esc(en)}</span>'
        nav += f'<a class="lvl{lvl}" href="#{s["id"]}">{label}</a>\n'

    body = ""
    for s in secs:
        lvl = max(0, min(2, int(s.get("level", 1)) - 1))
        tag = ["h2", "h3", "h4"][lvl]
        title = s.get("title_zh") or s.get("title_en", "")
        en = s.get("title_en", "")
        en_span = f' <span class="en">{esc(en)}</span>' if en and en not in title else ""
        body += f'<section id="{s["id"]}">\n<{tag}>{esc(title)}{en_span}</{tag}>\n'
        used = set()
        for item in s.get("zh", []):
            if isinstance(item, dict):
                fid = item.get("fig") or item.get("table") or item.get("image")
                fig = figs.get(fid)
                if fig:
                    used.add(fid)
                    body += figure_html(fig, assets,
                                        f'{KIND_ZH.get(fig["kind"], fig["kind"])} {fig["num"]}') + "\n"
            else:
                body += f"<p>{esc(item)}</p>\n"
        for fid in s.get("figures", []):          # 未被显式引用的图表补在本节末尾
            if fid in figs and fid not in used:
                f = figs[fid]
                body += figure_html(f, assets, f'{KIND_ZH.get(f["kind"], f["kind"])} {f["num"]}') + "\n"
        body += "</section>\n\n"

    sub = esc(content.get("subtitle", "保结构中文精读 · 正文英文已总结为中文，章节层级与图表保持原文"))
    meta_bits = [f'<span>源文件：{esc(content.get("source", ""))}</span>',
                 f'<span>共 {content.get("page_count", "?")} 页</span>',
                 f'<span>章节 {len(secs)}</span>',
                 f'<span>图表 {len(content.get("figures", []))}</span>']
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(content.get("title", "论文中文精读"))}</title>
<style>
:root{{--ink:#1c1c1e;--muted:#6b6b70;--line:#e3e3e6;--accent:#8b3a2f;--accent2:#1f5c4a;--bg:#fbfaf8;}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",serif;
color:var(--ink);background:var(--bg);line-height:1.85;font-size:16px}}
.layout{{display:flex;align-items:flex-start;max-width:1180px;margin:0 auto}}
nav{{position:sticky;top:0;flex:0 0 268px;height:100vh;overflow-y:auto;padding:28px 18px 40px;
border-right:1px solid var(--line);background:#fff}}
nav .brand{{font-size:12px;letter-spacing:.14em;color:var(--muted);text-transform:uppercase;margin-bottom:14px}}
nav a{{display:block;text-decoration:none;color:#3a3a3e;padding:5px 10px;border-radius:6px;font-size:13.5px;line-height:1.5}}
nav a:hover{{background:#f2efec;color:var(--accent)}}
nav a.lvl0{{font-weight:600;margin-top:9px}}
nav a.lvl1{{padding-left:22px;color:#4a4a50}}
nav a.lvl2{{padding-left:34px;font-size:12.8px;color:var(--muted)}}
.nav-en{{color:#a9a9ae;font-size:11.5px}}
main{{flex:1;min-width:0;background:#fff;padding:44px 56px 90px}}
header.doc{{border-bottom:2px solid var(--accent);padding-bottom:20px;margin-bottom:30px}}
header.doc h1{{font-size:26px;line-height:1.4;margin:0 0 8px}}
header.doc .sub{{color:var(--muted);font-size:14px;margin-bottom:16px}}
.meta{{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:12.5px;color:var(--muted)}}
h2{{font-size:21px;margin:44px 0 14px;padding-bottom:7px;border-bottom:1px solid var(--line);color:var(--accent)}}
h3{{font-size:17.5px;margin:30px 0 10px;color:var(--accent2)}}
h4{{font-size:15.5px;margin:22px 0 8px;color:#3d3d42}}
h2 .en,h3 .en,h4 .en{{font-size:12.5px;color:#a9a9ae;font-weight:400}}
p{{margin:0 0 13px;text-align:justify}}
figure.fig{{margin:22px 0;padding:12px;background:#faf9f7;border:1px solid var(--line);border-radius:8px}}
figure.fig img{{display:block;width:100%;height:auto;border-radius:5px;background:#fff}}
figure.fig figcaption{{margin-top:10px;font-size:12.6px;color:var(--muted);line-height:1.7}}
.tag{{display:inline-block;background:var(--accent);color:#fff;border-radius:4px;padding:1px 7px;
font-size:11.5px;margin-right:6px}}
.cap-en{{color:#5a5a60}}
.cap-zh{{color:var(--accent2)}}
@media(max-width:900px){{.layout{{flex-direction:column}}nav{{position:static;height:auto;flex:none;width:100%;border-right:0;border-bottom:1px solid var(--line)}}main{{padding:28px 20px 60px}}}}
</style>
</head>
<body>
<div class="layout">
<nav>
  <div class="brand">目录 · Contents</div>
  {nav}
</nav>
<main>
<header class="doc">
  <h1>{esc(content.get("title", "论文中文精读"))}</h1>
  <div class="sub">{sub}</div>
  <div class="meta">{"".join(meta_bits)}</div>
</header>
{body}
</main>
</div>
</body>
</html>'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    content = json.load(open(args.content, encoding="utf-8"))
    assets = os.path.join(os.path.dirname(os.path.abspath(args.content)), "assets")
    html_out = build(content, assets)
    open(args.out, "w", encoding="utf-8").write(html_out)

    filled = sum(1 for s in content["sections"] if s.get("zh"))
    print(f"输出: {args.out}  ({len(html_out.encode())/1024:.0f} KB)")
    print(f"章节: {len(content['sections'])}（已填中文总结 {filled}）| 图表: {len(content.get('figures', []))}")
    if filled < len(content["sections"]):
        print(f"⚠ 仍有 {len(content['sections']) - filled} 个章节的 zh 为空")


if __name__ == "__main__":
    main()
