#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract.py — 从 PDF（或 Zotero 条目键）提取论文结构、正文与图表，产出 content.json + assets/ + pages/

用法:
  python3 extract.py --pdf /path/to/paper.pdf --out ./out
  python3 extract.py --zotero-item ABC123XY --out ./out

产出:
  out/content.json      结构骨架（章节、页码区间、图表清单、图表图注），供 Agent 填写中文总结
  out/pages/0001.txt    逐页正文纯文本，供 Agent 按章节读取
  out/assets/*.png      图表按 caption 自动裁切的原图（保持原样，不翻译）
"""
import argparse, json, os, re, sys, urllib.request, urllib.error

try:
    import pymupdf as fitz
except ImportError:  # 兼容旧包名
    import fitz

CAP_RE = re.compile(r'^(Figure|Fig\.?|Table)\s+(\d+)\s*[:.]', re.I)
ZOTERO_CFG = os.environ.get("ZOTERO_MCP_CONFIG", "~/.config/zotero-mcp/config.json")


# ────────────────────────────── Zotero 取 PDF ──────────────────────────────
def zotero_fetch_pdf(item_key, out_dir):
    """通过 Zotero 本地 API 把 PDF 取到本地（条目键可以是父条目，也可以是 PDF 附件本身）。"""
    cfg_file = os.path.expanduser(ZOTERO_CFG)
    if not os.path.exists(cfg_file):
        sys.exit(f"找不到 Zotero MCP 配置: {cfg_file}")
    cfg = json.load(open(cfg_file))["local_api"]
    base = "http://127.0.0.1:23119/api/users/0"
    hdr = {"Zotero-API-Version": "3", "Zotero-Server-ID": cfg["server_id"],
           "Zotero-API-Key": cfg["key"]}

    def get(path):
        req = urllib.request.Request(base + path, headers=hdr)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            sys.exit(f"Zotero 本地 API {path} 失败: {e.code} {e.read().decode()[:200]}")
        except urllib.error.URLError as e:
            sys.exit(f"无法连接 Zotero 本地 API，请确认 Zotero 正在运行: {e}")

    data = json.loads(get(f"/items/{item_key}").decode())["data"]
    key = item_key
    if data.get("itemType") != "attachment" or data.get("contentType") != "application/pdf":
        kids = json.loads(get(f"/items/{item_key}/children?limit=100").decode())
        pdfs = [k for k in kids if k["data"].get("contentType") == "application/pdf"]
        if not pdfs:
            sys.exit(f"Zotero 条目 {item_key} 下没有 PDF 附件")
        key = pdfs[0]["key"]
    path = os.path.join(out_dir, "source.pdf")
    with open(path, "wb") as f:
        f.write(get(f"/items/{key}/file"))
    return path


# ────────────────────────────── 结构提取 ──────────────────────────────
def detect_headings(doc):
    """无内嵌书签时，按字号启发式识别标题。"""
    sizes = {}
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for line in b["lines"]:
                for s in line["spans"]:
                    t = s["text"].strip()
                    if t:
                        sizes.setdefault(round(s["size"], 1), 0)
                        sizes[round(s["size"], 1)] += len(t)
    if not sizes:
        return []
    body = max(sizes, key=sizes.get)
    heads = sorted([s for s in sizes if s > body + 0.5], reverse=True)[:2]
    if not heads:
        return []
    toc = []
    for i, page in enumerate(doc, start=1):
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for line in b["lines"]:
                txt = "".join(s["text"] for s in line["spans"]).strip()
                if len(txt) < 3 or len(txt) > 90:
                    continue
                sz = round(max(s["size"] for s in line["spans"]), 1)
                if sz in heads:
                    toc.append([1 if sz == heads[0] else 2, txt, i])
    return toc


def build_sections(doc, toc):
    secs = []
    for i, (lvl, title, page) in enumerate(toc):
        nxt = toc[i + 1][2] if i + 1 < len(toc) else doc.page_count
        end = max(page, nxt - 1) if nxt > page else page
        secs.append({
            "id": f"s-{i + 1}", "level": int(lvl), "title_en": title.strip(),
            "title_zh": "", "page_start": int(page), "page_end": int(end),
            "figures": [], "zh": [],
        })
    return secs


# ────────────────────────────── 图表裁切 ──────────────────────────────
def _clusters(boxes, gap=14):
    merged = [fitz.Rect(b) for b in boxes]
    changed = True
    while changed:
        changed, out = False, []
        for r in merged:
            hit = next((m for m in out if not (r.y1 < m.y0 - gap or r.y0 > m.y1 + gap
                                              or r.x1 < m.x0 - gap or r.x0 > m.x1 + gap)), None)
            if hit:
                hit.include_rect(r); changed = True
            else:
                out.append(r)
        merged = out
    return merged


def _graphics(page):
    boxes = [fitz.Rect(im["bbox"]) for im in page.get_image_info()]
    for d in page.get_drawings():
        r = d["rect"]
        if r.width > 3 and r.height > 3:
            boxes.append(fitz.Rect(r))
    return boxes


def _grow(blocks, seed, direction, gap, xrange):
    """从 seed 出发，按行距连续性向 up/down 吞并相邻文本块；出现明显空档即停止。

    纯文本表格（没有位图/矢量图形）无法靠图形区块定位，只能靠行距连续性推断。
    """
    region = fitz.Rect(seed)
    cur = seed.y0 if direction == "up" else seed.y1
    for b in sorted(blocks, key=lambda r: r.y0, reverse=(direction == "up")):
        if b.x1 < xrange[0] or b.x0 > xrange[1]:
            continue
        if direction == "up":
            if b.y1 > cur + 2:
                continue
            if cur - b.y1 > gap:
                break
            region.include_rect(b); cur = b.y0
        else:
            if b.y0 < cur - 2:
                continue
            if b.y0 - cur > gap:
                break
            region.include_rect(b); cur = b.y1
    return region


def crop_figures(doc, out_dir, zoom=3.0):
    """按 caption 定位并裁切所有 Figure/Table 区域，保持原图不做任何改动。"""
    assets = os.path.join(out_dir, "assets")
    os.makedirs(assets, exist_ok=True)
    found = []
    for pno in range(doc.page_count):
        page = doc[pno]
        caps = []
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            txt = " ".join(s["text"] for l in b["lines"] for s in l["spans"]).strip()
            m = CAP_RE.match(txt)
            if m:
                caps.append((("Figure" if m.group(1).lower().startswith("fig") else "Table"),
                             int(m.group(2)), fitz.Rect(b["bbox"]), re.sub(r"\s+", " ", txt).strip()))
        if not caps:
            continue
        clusters = _clusters(_graphics(page))
        blocks = [fitz.Rect(b["bbox"]) for b in page.get_text("dict")["blocks"]]
        for kind, num, crect, txt in caps:
            best = None
            for c in clusters:
                if kind == "Figure" and c.y1 <= crect.y0 + 4:
                    d = crect.y0 - c.y1
                    if d < 240 and (best is None or d < best[0]):
                        best = (d, c)
                elif kind == "Table" and c.y0 >= crect.y1 - 6:
                    d = c.y0 - crect.y1
                    if d < 140 and (best is None or d < best[0]):
                        best = (d, c)
            if best:
                region = fitz.Rect(best[1])
                region.include_rect(crect)
            else:
                region = None
            # 纯文本表格、或图形区块缺失/过薄（只抓到一条表格线）时，按行距连续性生长补全
            if region is None or region.height < 60:
                grown = _grow(blocks, crect, "up" if kind == "Figure" else "down",
                              gap=26 if kind == "Figure" else 15,
                              xrange=(crect.x0 - 6, crect.x1 + 6))
                region = grown if region is None else (region | grown)
            region = fitz.Rect(region.x0 - 6, region.y0 - 6, region.x1 + 6, region.y1 + 6) & page.rect
            name = f"{kind.lower()}{num}_p{pno + 1}.png"
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=region, alpha=False)
            pix.save(os.path.join(assets, name))
            found.append({
                "id": f"{kind.lower()}{num}", "kind": kind, "num": num, "page": pno + 1,
                "image": f"assets/{name}", "width": pix.width, "height": pix.height,
                "caption_en": txt, "caption_zh": "",
            })
    # 去重（同一编号出现在多页时取首次出现）
    dedup = {}
    for f in found:
        dedup.setdefault(f["id"], f)
    return sorted(dedup.values(), key=lambda f: (f["kind"], f["num"]))


# ────────────────────────────── 主流程 ──────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pdf", help="PDF 文件路径")
    src.add_argument("--zotero-item", help="Zotero 条目键（父条目或 PDF 附件键均可）")
    ap.add_argument("--out", default="./paper-reading-out", help="输出目录")
    ap.add_argument("--no-figures", action="store_true", help="跳过图表裁切")
    ap.add_argument("--zoom", type=float, default=3.0, help="图表导出缩放（默认 3x）")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    pdf = zotero_fetch_pdf(args.zotero_item, out) if args.zotero_item else args.pdf
    doc = fitz.open(pdf)

    # 元数据 + 逐页正文
    meta = doc.metadata or {}
    pages_dir = os.path.join(out, "pages")
    os.makedirs(pages_dir, exist_ok=True)
    for i, page in enumerate(doc, start=1):
        open(os.path.join(pages_dir, f"{i:04d}.txt"), "w", encoding="utf-8").write(page.get_text())

    toc = doc.get_toc(simple=True) or detect_headings(doc)
    sections = build_sections(doc, toc)
    figs = [] if args.no_figures else crop_figures(doc, out, args.zoom)

    # 图表按页码归入所属章节
    for f in figs:
        for s in sections:
            if s["page_start"] <= f["page"] <= s["page_end"]:
                s["figures"].append(f["id"])
                break

    content = {
        "source": os.path.basename(pdf),
        "title": meta.get("title") or os.path.splitext(os.path.basename(pdf))[0],
        "page_count": doc.page_count,
        "toc_detected": bool(toc),
        "sections": sections,
        "figures": figs,
        "note": ("sections[].zh 为待填字段：数组元素可为段落字符串，或 {\"fig\": \"figure1\"} 表示在此处插入该图。"
                 "图表原图位于 assets/，caption_en 为原文图注。正文见 pages/NNNN.txt。"),
    }
    json.dump(content, open(os.path.join(out, "content.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"PDF: {pdf}")
    print(f"页数: {doc.page_count} | 目录: {'内嵌书签' if doc.get_toc() else ('字号推断' if toc else '未检出')} | 章节: {len(sections)}")
    print(f"图表: {len(figs)} -> {', '.join(f['id'] for f in figs) if figs else '无'}")
    print(f"输出: {out}/content.json, pages/, assets/")
    if not toc:
        print("⚠ 未检出目录结构，sections 仅含单节；可在 content.json 中手动拆分章节。")


if __name__ == "__main__":
    main()
