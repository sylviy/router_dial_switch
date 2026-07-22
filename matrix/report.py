"""把一轮矩阵结果写成人可读的报告:自包含 HTML + 一份 CSV。

取代旧 Dial.py 那套"写死路径的 Excel 模板 + 魔法行号 + 注释掉的错误日志"。
HTML 无外部依赖、亮/暗自适应,一眼看清每个 拨号方式×频段×方向×协议 的吞吐、
是否稳定、以及那一档模式切换是否成功。CSV 供导入表格用。
"""
from __future__ import annotations

import csv
import datetime
import html
import os
from typing import Dict, List


def _fmt(mbps) -> str:
    return "%.1f" % mbps if isinstance(mbps, (int, float)) else "—"


def write_csv(rows: List[dict], path: str) -> str:
    cols = ["mode", "switched", "read_back", "band", "direction", "proto",
            "mbps", "stable", "error"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


_CSS = """
:root{--bg:#fff;--fg:#1c1d21;--muted:#6b7280;--line:#e5e7eb;--card:#f9fafb;
--ok:#0f8a4f;--bad:#c0392b;--head:#111827;--accent:#2563eb}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--fg:#e6e7ea;
--muted:#9aa0aa;--line:#262a33;--card:#161922;--ok:#37d67a;--bad:#ff6b6b;
--head:#e6e7ea;--accent:#5b8cff}}
*{box-sizing:border-box}
body{margin:0;padding:32px;background:var(--bg);color:var(--fg);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 10px;color:var(--head)}
.sub{color:var(--muted);margin:0 0 20px;font-size:13px}
.meta{display:flex;flex-wrap:wrap;gap:10px 22px;background:var(--card);
border:1px solid var(--line);border-radius:10px;padding:14px 18px;margin-bottom:8px;font-size:13px}
.meta b{color:var(--head)}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px;margin-bottom:6px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:9px 14px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
thead th{background:var(--card);color:var(--head);font-weight:600;position:sticky;top:0}
tbody tr:last-child td{border-bottom:none}
.mode{font-weight:600}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600}
.ok{color:var(--ok)}.bad{color:var(--bad)}
.pill-ok{background:color-mix(in srgb,var(--ok) 16%,transparent);color:var(--ok)}
.pill-bad{background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad)}
.num{font-variant-numeric:tabular-nums}
footer{margin-top:26px;color:var(--muted);font-size:12px}
"""


def _pill(ok: bool, ok_txt="OK", bad_txt="FAIL") -> str:
    cls = "pill-ok" if ok else "pill-bad"
    return '<span class="pill %s">%s</span>' % (cls, ok_txt if ok else bad_txt)


def _band_table(band: str, rows: List[dict], directions, protocols) -> str:
    # 表头:方向 × 协议
    heads = "".join('<th>%s / %s<br><span style="font-weight:400;color:var(--muted)">Mbps</span></th>'
                    % (html.escape(d), html.escape(p))
                    for p in protocols for d in directions)
    out = ['<div class="wrap"><table><thead><tr><th>拨号方式</th>%s</tr></thead><tbody>' % heads]
    # 按 mode 聚合(保持出现顺序)
    modes: List[str] = []
    for r in rows:
        if r["mode"] not in modes:
            modes.append(r["mode"])
    cell = {(r["mode"], r["direction"], r["proto"]): r for r in rows}
    for m in modes:
        tds = []
        for p in protocols:
            for d in directions:
                r = cell.get((m, d, p))
                if not r:
                    tds.append('<td>—</td>')
                elif r.get("error"):
                    tds.append('<td class="bad" title="%s">err</td>'
                               % html.escape(str(r["error"])[:200]))
                else:
                    mark = "" if r.get("stable", True) else ' <span class="bad" title="吞吐不稳(min<0.9·max)">⚠</span>'
                    tds.append('<td class="num">%s%s</td>' % (_fmt(r.get("mbps")), mark))
        out.append('<tr><td class="mode">%s</td>%s</tr>'
                   % (html.escape(m), "".join(tds)))
    out.append("</tbody></table></div>")
    return "".join(out)


def write_html(ctx: dict, path: str) -> str:
    rows: List[dict] = ctx["rows"]
    directions = ctx["directions"]
    protocols = ctx["protocols"]
    bands = ctx["bands"]

    switch = ctx["switch"]  # list of {mode, switched, read_back, message}
    sw_ok = sum(1 for s in switch if s["switched"])
    meas_rows = [r for r in rows if r.get("band")]
    meas_ok = sum(1 for r in meas_rows if not r.get("error"))
    unstable = sum(1 for r in meas_rows
                   if not r.get("error") and r.get("stable") is False)

    parts = ['<!doctype html><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             "<title>%s</title><style>%s</style>" % (html.escape(ctx["title"]), _CSS),
             "<h1>%s</h1>" % html.escape(ctx["title"]),
             '<p class="sub">%s · 型号 <b>%s</b> · 后端 <b>%s</b></p>'
             % (html.escape(ctx["timestamp"]), html.escape(ctx["model"] or "?"),
                html.escape(ctx["backend"]))]

    parts.append('<div class="meta">'
                 '<span>拨号方式切换 <b>%d/%d</b> 成功</span>'
                 '<span>吞吐测量 <b>%d/%d</b> 完成</span>'
                 '<span>不稳定格 <b class="%s">%d</b></span>'
                 '<span>频段 <b>%s</b> · 方向 <b>%s</b> · 协议 <b>%s</b></span>'
                 '</div>'
                 % (sw_ok, len(switch), meas_ok, len(meas_rows),
                    "bad" if unstable else "ok", unstable,
                    html.escape("/".join(bands)),
                    html.escape("/".join(directions)),
                    html.escape("/".join(protocols))))

    # 切换状态一览
    parts.append("<h2>拨号方式切换</h2><div class='wrap'><table><thead><tr>"
                 "<th>模式</th><th>结果</th><th>界面回读</th><th>备注</th>"
                 "</tr></thead><tbody>")
    for s in switch:
        parts.append("<tr><td class='mode'>%s</td><td>%s</td>"
                     "<td style='text-align:left'>%s</td>"
                     "<td style='text-align:left;color:var(--muted)'>%s</td></tr>"
                     % (html.escape(s["mode"]), _pill(s["switched"]),
                        html.escape(s.get("read_back") or "—"),
                        html.escape(s.get("message") or "")))
    parts.append("</tbody></table></div>")

    # 每个频段一张吞吐表
    for band in bands:
        band_rows = [r for r in meas_rows if r.get("band") == band]
        if not band_rows:
            continue
        parts.append("<h2>吞吐 · %s</h2>" % html.escape(band))
        parts.append(_band_table(band, band_rows, directions, protocols))

    parts.append("<footer>数值为 Chariot 吞吐(Mbps);⚠ = 该格中段采样不稳"
                 "(min &lt; 0.9·max)。simulate 后端为离线模拟值,非真机实测。"
                 "</footer>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("".join(parts))
    return path


def write_reports(ctx: dict, out_dir: str) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = (ctx.get("model") or "matrix").replace(" ", "_")
    html_path = os.path.join(out_dir, "wanperf_%s_%s.html" % (slug, stamp))
    csv_path = os.path.join(out_dir, "wanperf_%s_%s.csv" % (slug, stamp))
    write_html(ctx, html_path)
    write_csv(ctx["rows"], csv_path)
    return {"html": html_path, "csv": csv_path}
