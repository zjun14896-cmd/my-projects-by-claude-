#!/usr/bin/env python3
"""云拓会 · 第 8 期线下实操课 —— 公众号正文构建脚本（第三版）。

一份源，三个产物：
  dist/article.html            粘贴进公众号编辑器的正文片段（图片用 CDN 绝对地址）
  dist/article.template.html   同一正文，图片为占位符，供 publish_draft.py 使用
  preview.html / artifact/     审稿 + 一键复制工具页

正文只用公众号会保留的写法：内联 style、<section>/<p>/<span>/<img>、内联 <svg> + SMIL。
不用 id / class / <style> / <script> / position:absolute / url(#…)。
交互模块的属性基值写成「完成态」，SMIL 被过滤时画面停在完整可读的状态。

用法：python3 build.py [--ref 提交号]
"""
import argparse
import html
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
IMG = "{{IMG}}"  # 图片前缀占位符：预览时换成 img/，复制时换成 CDN 地址
REPO = "zjun14896-cmd/my-projects-by-claude-"
IMG_PATH = "wechat/vol08/img/"

TITLE = "第 8 期线下实操课结束了：五天，把路走通"
DIGEST = "网上的东西看了不少，真要自己动手，还是不知道该怎么做。这五天，我们就从这里开始。"

# ── 设计令牌 ─────────────────────────────────────────────
# 白底长文 + 午夜蓝模块。品牌蓝负责结构（序号、标签、图形），品牌黄只做强调（荧光笔、进度、亮点）。
BLUE = "#003CAC"       # 品牌蓝（logo）
BLUE_SOFT = "#EEF3FF"  # 品牌蓝 6% 浅底
YELLOW = "#FFC833"     # 品牌黄（logo）
INK = "#111318"        # 标题、强调
BODY = "#3B3F48"       # 正文
MUTED = "#8B909A"      # 注释
LINE = "#E6E8EE"       # 细分隔线
TILE = "#F3F5F8"       # 浅色模块底
NIGHT = "#050A18"      # 午夜蓝模块底
NIGHT_TEXT = "#A3AABB"
FONT = ("-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB',"
        "'Microsoft YaHei','Helvetica Neue',Arial,sans-serif")
SVG_NS = 'xmlns="http://www.w3.org/2000/svg"'
MARK = "background-image:linear-gradient(transparent 60%,rgba(255,200,51,0.6) 60%);"


# ── 文字组件 ─────────────────────────────────────────────
def p(text, style=""):
    return f'<p style="margin:0;padding:0;{style}">{text}</p>'


def body(*lines, top=18, align="justify"):
    """叙述段落两端对齐；短句、回答句用 center()。"""
    return p("<br>".join(lines), f"margin-top:{top}px;font-size:16px;line-height:1.9;color:{BODY};"
                                 f"letter-spacing:0.3px;text-align:{align};")


def center(*lines, top=18):
    return body(*lines, top=top, align="center")


def answer(*lines, top=18):
    """「所以……」这一类回答句：居中、加粗。"""
    return p("<br>".join(lines), f"margin-top:{top}px;font-size:16px;line-height:1.9;color:{INK};"
                                 "font-weight:600;letter-spacing:0.3px;text-align:center;")


def strong(t):
    return f'<span style="color:{INK};font-weight:600;">{t}</span>'


def mark(t):
    """荧光笔：每节最多一处，标出这一节最想让读者记住的事实。"""
    return f'<span style="color:{INK};font-weight:600;{MARK}">{t}</span>'


def opener(n, question):
    """章节开头：居中的细体大序号 + 一行读者原话。"""
    return (p(f'<span style="font-size:50px;line-height:1;font-weight:200;color:{BLUE};letter-spacing:-1px;">{n:02d}</span>'
              f'<span style="font-size:12px;line-height:1;color:{MUTED};letter-spacing:1px;margin-left:6px;">/ 05</span>',
              "line-height:1;text-align:center;")
            + p(question, f"margin-top:16px;font-size:18px;line-height:1.6;font-weight:700;color:{INK};"
                          "letter-spacing:0;text-align:center;"))


def caption(text, align="center"):
    return p(text, f"margin-top:10px;font-size:12px;line-height:1.6;color:{MUTED};letter-spacing:1px;text-align:{align};")


def img(name, alt):
    return (f'<img src="{IMG}{name}" alt="{alt}" '
            'style="display:block;width:100%;height:auto;margin:0;padding:0;border:0;">')


def photo(name, alt, cap=None, top=26, radius=16):
    out = (f'<section style="margin-top:{top}px;"><section style="border-radius:{radius}px;overflow:hidden;'
           f'line-height:0;font-size:0;">{img(name, alt)}</section>')
    return out + (caption(cap) if cap else "") + "</section>"


def chapter(*parts, top=88):
    return f'<section style="margin-top:{top}px;">{"".join(parts)}</section>'


def rows(items):
    """细线分隔的居中列表。items: [(小标签, 正文)]；正文为空时标签与文字同行显示。"""
    out = ""
    for i, (lab, txt) in enumerate(items):
        bb = f"border-bottom:1px solid {LINE};" if i == len(items) - 1 else ""
        out += f'<section style="padding:15px 0;border-top:1px solid {LINE};{bb}text-align:center;">'
        if txt:
            out += (p(lab, f"font-size:12px;line-height:1.4;color:{BLUE};font-weight:600;letter-spacing:2px;text-align:center;")
                    + p(txt, f"margin-top:6px;font-size:15px;line-height:1.8;color:{BODY};letter-spacing:0.2px;text-align:center;"))
        else:
            out += p(lab, f"font-size:16px;line-height:1.6;color:{INK};font-weight:500;text-align:center;")
        out += "</section>"
    return out


# ── SMIL 片段 ────────────────────────────────────────────
# 公众号会删掉 id，无法用 "xx.click" 跨元素触发。做法：透明热区放在最深层，
# 点击事件冒泡经过每一层祖先 <g>，每层用 begin="click" 驱动自己的可继承属性
# （fill-opacity / stroke-dashoffset / transform），一次轻点触发一整套编排。
def fade(start, end, begin="click", dur="0.45s"):
    """属性基值（写在 <g> 上）= 完成态兜底；加载即 <set> 到初始态；轻点后动画到完成态。"""
    return (f'<set attributeName="fill-opacity" to="{start}" begin="0s"/>'
            f'<animate attributeName="fill-opacity" values="{start};{end}" dur="{dur}" '
            f'begin="{begin}" fill="freeze" restart="never"/>')


def hit():
    return ('<rect x="-400" y="-400" width="1200" height="1400" fill="#000000" fill-opacity="0" '
            'pointer-events="all" style="cursor:pointer;"/>')


def svg_open(w, h, style=""):
    return (f'<svg {SVG_NS} viewBox="0 0 {w} {h}" width="100%" '
            f'style="display:block;width:100%;{style}" font-family="{FONT}">')


def t(x, y, s, size, fill, weight=400, anchor="start", ls=0, extra=""):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    w = f' font-weight="{weight}"' if weight != 400 else ""
    l = f' letter-spacing="{ls}"' if ls else ""
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}"{w}{a}{l}{extra}>{s}</text>'


def module(svg, top=26):
    return f'<section style="margin-top:{top}px;line-height:0;font-size:0;">{svg}</section>'


# ── 模块 ─────────────────────────────────────────────────
def hero_numeral():
    """「08」先以黄色描边画出，再填成白色。打开文章时播放一次。"""
    return (svg_open(300, 140, "margin-top:26px;pointer-events:none;")
            + '<text x="150" y="132" font-size="160" font-weight="700" letter-spacing="-6" text-anchor="middle" '
              f'fill="#FFFFFF" fill-opacity="1" stroke="{YELLOW}" stroke-width="1.2" stroke-opacity="0" '
              'stroke-dasharray="560" stroke-dashoffset="0">08'
              '<set attributeName="fill-opacity" to="0" begin="0s"/>'
              '<set attributeName="stroke-opacity" to="1" begin="0s"/>'
              '<set attributeName="stroke-dashoffset" to="560" begin="0s"/>'
              '<animate attributeName="stroke-dashoffset" values="560;0" dur="1.8s" begin="0.2s" fill="freeze" '
              'calcMode="spline" keyTimes="0;1" keySplines="0.45 0 0.25 1"/>'
              '<animate attributeName="fill-opacity" values="0;1" dur="0.8s" begin="1.6s" fill="freeze"/>'
              '<animate attributeName="stroke-opacity" values="1;0" dur="0.6s" begin="2.2s" fill="freeze"/>'
              '</text></svg>')


def glow_panel(svg, bg, top=26, radius=22):
    """深色/品牌蓝模块：底色用 CSS 渐变铺在外层（被过滤时退回 background-color），SVG 透明叠在上面。"""
    return (f'<section style="margin-top:{top}px;border-radius:{radius}px;overflow:hidden;line-height:0;font-size:0;'
            f'{bg}">{svg}</section>')


def loop_diagram():
    """课堂节奏：讲一步 → 跟着做 → 逐个查看 → 一起解决。发光轨道 + 带拖尾的黄点循环，外圈虚线缓慢旋转。"""
    W, H, cx, cy, r = 343, 330, 171.5, 172, 80
    lt = "#8FB0FF"
    nodes = [(cx, cy - r, "讲一步", cx, cy - r - 20, "middle"),
             (cx + r, cy, "跟着做", cx + r + 18, cy + 5, "start"),
             (cx, cy + r, "逐个查看", cx, cy + r + 30, "middle"),
             (cx - r, cy, "一起解决", cx - r - 18, cy + 5, "end")]
    out = (svg_open(W, H, "pointer-events:none;")
           + t(22, 38, "课堂节奏", 12, YELLOW, 600, ls=3)
           + t(321, 38, "一步一循环", 12, lt, anchor="end", ls=1)
           # 外圈虚线，40 秒转一圈
           + f'<g><animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" to="360 {cx} {cy}" '
             'dur="40s" repeatCount="indefinite"/>'
           + f'<circle cx="{cx}" cy="{cy}" r="{r + 36}" fill="none" stroke="#FFFFFF" stroke-opacity="0.16" '
             'stroke-width="1" stroke-dasharray="2 7"/></g>'
           + f'<circle cx="{cx}" cy="{cy}" r="{r - 30}" fill="none" stroke="#FFFFFF" stroke-opacity="0.08" stroke-width="1"/>'
           # 发光轨道：三层描边叠出光晕
           + f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{lt}" stroke-opacity="0.07" stroke-width="16"/>'
           + f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{lt}" stroke-opacity="0.14" stroke-width="7"/>'
           + f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{lt}" stroke-opacity="0.85" stroke-width="1.2"/>'
           + t(cx, cy - 4, "每一步", 13, lt, anchor="middle", ls=2)
           + t(cx, cy + 20, "都这样走一遍", 16, "#FFFFFF", 700, "middle", 1))
    for i, (x, y, label, lx, ly, anchor) in enumerate(nodes):
        b = f"{1.5 * i}s"
        out += (f'<circle cx="{x}" cy="{y}" r="14" fill="{YELLOW}" opacity="0">'
                f'<animate attributeName="opacity" values="0;0.35;0;0" keyTimes="0;0.06;0.22;1" dur="6s" begin="{b}" repeatCount="indefinite"/>'
                f'<animate attributeName="r" values="8;18;22;22" keyTimes="0;0.06;0.22;1" dur="6s" begin="{b}" repeatCount="indefinite"/>'
                "</circle>"
                f'<circle cx="{x}" cy="{y}" r="7" fill="#0B1A44" stroke="{lt}" stroke-width="1.5">'
                f'<animate attributeName="fill" values="{YELLOW};{YELLOW};#0B1A44;#0B1A44" keyTimes="0;0.1;0.22;1" dur="6s" begin="{b}" repeatCount="indefinite"/>'
                "</circle>"
                + t(lx, ly, label, 14, "#FFFFFF", 600, anchor, 1))
    path = f"M0,0 A{r},{r} 0 0 1 0,{2 * r} A{r},{r} 0 0 1 0,0"
    for k, (rad, op) in enumerate([(5.5, 1), (4.4, 0.55), (3.6, 0.35), (2.8, 0.2), (2, 0.1)]):
        out += (f'<circle cx="{cx}" cy="{cy - r}" r="{rad}" fill="{YELLOW}" opacity="{op}">'
                f'<animateMotion path="{path}" dur="6s" begin="{0.07 * k:.2f}s" repeatCount="indefinite"/></circle>')
    bg = (f"background-color:#071233;background-image:radial-gradient(60% 50% at 50% 52%,rgba(43,108,255,0.45) 0%,"
          "rgba(43,108,255,0) 70%),radial-gradient(70% 45% at 0% 100%,rgba(111,155,255,0.22) 0%,rgba(111,155,255,0) 70%),"
          "linear-gradient(160deg,#0B2A86 0%,#061033 58%,#050A18 100%);")
    return glow_panel(out + "</svg>", bg)


def persona_card(label, question, a1, a2):
    """三种情况之一：轻点卡片，看到这种情况在课上怎么被对待。完成态兜底 = 直接显示答案。"""
    W, H = 343, 136
    return (svg_open(W, H, "margin-top:10px;")
            # L1 完成态
            + '<g fill-opacity="1">' + fade(0, 1, "click+0.12s", "0.45s")
            + f'<rect x="0" y="0" width="{W}" height="{H}" rx="18" fill="{BLUE_SOFT}" pointer-events="none"/>'
            # L2 初始态（含热区）
            + '<g fill-opacity="0">' + fade(1, 0, "click", "0.3s")
            + f'<rect x="0" y="0" width="{W}" height="{H}" rx="18" fill="{TILE}" pointer-events="none"/>'
            + t(20, 104, "轻点，看看课上怎么做", 13, MUTED, ls=1, extra=' pointer-events="none"')
            + f'<circle cx="311" cy="34" r="13" fill="{BLUE}"/>'
            + '<rect x="305" y="33.25" width="12" height="1.5" fill="#FFFFFF"/>'
            + '<rect x="310.25" y="28" width="1.5" height="12" fill="#FFFFFF"/>'
            + hit() + "</g>"
            + t(20, 34, label, 12, BLUE, 600, ls=2, extra=' fill-opacity="1" pointer-events="none"')
            + t(20, 66, question, 18, INK, 700, ls=0.5, extra=' fill-opacity="1" pointer-events="none"')
            + t(20, 100, a1, 15, BODY, ls=0.3, extra=' pointer-events="none"')
            + t(20, 122, a2, 15, BODY, ls=0.3, extra=' pointer-events="none"')
            + "</g></svg>")


def pipeline():
    """一条视频的完整流程：轻点后黄线自上而下走完六步，最后落到「自己上手」。"""
    W, H, x0, y0, gap = 343, 482, 40, 132, 50
    steps = ["挑选商品", "构思内容", "布置灯光", "拍摄", "剪辑", "发布"]
    span = gap * (len(steps) - 1)
    out = (svg_open(W, H)
           + t(24, 44, "一条视频的完整流程", 12, YELLOW, 600, ls=3)
           + t(24, 84, "从挑选商品，到最后发布。", 22, "#FFFFFF", 700, ls=0.5)
           + f'<rect x="{x0 - 0.75}" y="{y0}" width="1.5" height="{span}" fill="#26304A"/>')
    for i, s in enumerate(steps):
        y = y0 + gap * i
        out += (f'<circle cx="{x0}" cy="{y}" r="6" fill="{NIGHT}" stroke="#3A4562" stroke-width="1.5"/>'
                + t(66, y + 6, s, 17, "#4E5873", 600, ls=1)
                + t(319, y + 5, f"0{i + 1}", 12, "#3A4562", ls=1))
    # 进度线（stroke-dashoffset 可继承，写在 Lp 上）
    out += (f'<g stroke-dashoffset="0"><set attributeName="stroke-dashoffset" to="{span}" begin="0s"/>'
            f'<animate attributeName="stroke-dashoffset" values="{span};0" dur="3s" begin="click" fill="freeze" restart="never"/>'
            f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0 + span}" stroke="{YELLOW}" stroke-width="2" stroke-dasharray="{span}"/>')
    for i, s in enumerate(steps):
        y = y0 + gap * i
        out += ('<g fill-opacity="1">' + fade(0, 1, f"click+{0.6 * i:.1f}s", "0.3s")
                + f'<circle cx="{x0}" cy="{y}" r="13" fill="{YELLOW}" opacity="0.22"/>'
                + f'<circle cx="{x0}" cy="{y}" r="6" fill="{YELLOW}"/>'
                + t(66, y + 6, s, 17, "#FFFFFF", 600, ls=1)
                + t(319, y + 5, f"0{i + 1}", 12, YELLOW, ls=1))
    out += ('<g fill-opacity="1">' + fade(0, 1, "click+3.3s", "0.5s")
            + t(24, 420, "看完之后，同学们用现场的商品和设备，", 14, "#C9CFDD", ls=0.5)
            + t(24, 444, "自己上手拍、自己剪。", 14, "#FFFFFF", 600, ls=0.5)
            + '<g fill-opacity="0">' + fade(1, 0, "click", "0.3s")
            + '<rect x="24" y="406" width="295" height="46" rx="23" fill="#FFFFFF" opacity="0.08"/>'
            + f'<path d="M44 421 L56 429 L44 437 Z" fill="{YELLOW}"/>'
            + t(68, 434, "轻点，把流程走一遍", 15, "#FFFFFF", 600, ls=1)
            + hit() + "</g></g>"
            + "</g>" * len(steps) + "</g></svg>")
    return (f'<section style="margin-top:26px;border-radius:22px;overflow:hidden;line-height:0;font-size:0;'
            f'background-color:{NIGHT};background-image:radial-gradient(90% 60% at 100% 0%,'
            f'rgba(0,60,172,0.6) 0%,rgba(0,60,172,0) 70%);">{out}</section>')


def after_timeline():
    """五天之后：品牌蓝面板。实线是线下五天，虚线一直往后流，下面是课后一直保留的三样东西。"""
    W, H = 343, 268
    soft = "#C3D3FF"
    xs = [30 + 33.5 * i for i in range(5)]
    out = (svg_open(W, H, "pointer-events:none;")
           + t(24, 40, "线下 5 天", 12, YELLOW, 600, ls=2)
           + t(190, 40, "之后", 12, soft, 600, ls=2)
           + f'<line x1="{xs[0]}" y1="76" x2="{xs[-1]}" y2="76" stroke="#FFFFFF" stroke-width="3" stroke-linecap="round"/>'
           + f'<line x1="{xs[-1] + 12}" y1="76" x2="320" y2="76" stroke="#FFFFFF" stroke-width="2" '
             'stroke-linecap="round" stroke-dasharray="1 7" stroke-opacity="0.75">'
             '<animate attributeName="stroke-dashoffset" values="0;-8" dur="0.7s" repeatCount="indefinite"/></line>')
    for i, x in enumerate(xs):
        out += (f'<circle cx="{x}" cy="76" r="4.5" fill="#FFFFFF"/>'
                + t(x, 102, str(12 + i), 11, soft, anchor="middle"))
    out += (f'<circle cx="{xs[-1]}" cy="76" r="8" fill="{YELLOW}" opacity="0.5">'
            '<animate attributeName="r" values="6;16" dur="1.8s" repeatCount="indefinite"/>'
            '<animate attributeName="opacity" values="0.6;0" dur="1.8s" repeatCount="indefinite"/></circle>'
            + f'<circle cx="{xs[-1]}" cy="76" r="5.5" fill="{YELLOW}"/>')
    for i, (a, b) in enumerate([("线上课程", "一直保留"), ("学员答疑群", "随时提问，持续解答"),
                                ("专题讲解", "针对大家普遍关心的问题")]):
        y = 148 + 40 * i
        out += ('<rect x="24" y="{0}" width="295" height="1" fill="#FFFFFF" opacity="0.18"/>'.format(y - 26)
                + t(24, y, a, 15, "#FFFFFF", 600, ls=0.5) + t(319, y, b, 13, soft, anchor="end", ls=0.3))
    bg = ("background-color:#003CAC;background-image:radial-gradient(70% 60% at 0% 0%,rgba(255,255,255,0.16) 0%,"
          "rgba(255,255,255,0) 70%),radial-gradient(50% 45% at 50% 28%,rgba(255,200,51,0.16) 0%,rgba(255,200,51,0) 70%),"
          "linear-gradient(140deg,#1257E6 0%,#003CAC 45%,#06246E 100%);")
    return glow_panel(out + "</svg>", bg)


# ── 正文 ─────────────────────────────────────────────────
def article():
    # 对齐规则：标题、引言、回答句、列表、图注居中；叙述性长段落两端对齐。
    hero = (f'<section style="border-radius:28px;overflow:hidden;background-color:{NIGHT};'
            'background-image:radial-gradient(90% 55% at 50% 30%,rgba(0,60,172,0.6) 0%,rgba(0,60,172,0) 70%);'
            'padding:30px 22px 22px;text-align:center;">'
            f'<img src="{IMG}logo-white.png" alt="云拓会" style="display:block;width:92px;height:auto;margin:0 auto;">'
            + hero_numeral()
            + p("2026.10.12 — 10.16", f"margin-top:8px;font-size:12px;line-height:1.4;color:{YELLOW};"
                                      "font-weight:600;letter-spacing:3px;text-align:center;")
            + p("五天，把路走通。", "margin-top:14px;font-size:32px;line-height:1.3;color:#FFFFFF;"
                                  "font-weight:700;letter-spacing:1px;text-align:center;")
            + p("TikTok 跨境电商 · 第 8 期线下实操课回顾",
                f"margin-top:10px;font-size:13px;line-height:1.6;color:{NIGHT_TEXT};letter-spacing:1px;text-align:center;")
            + photo("00-hero.jpg", "第 8 期课堂，老师在写满的白板前讲解", top=26, radius=14)
            + "</section>")

    intro = chapter(
        p("10 月 12 日到 16 日，<br>第 8 期线下实操课结束了。",
          f"font-size:20px;line-height:1.7;color:{INK};font-weight:700;letter-spacing:0.5px;text-align:center;"),
        center("这期来的同学，情况各不相同。", top=20),
        f'<section style="margin-top:18px;">' + rows([
            ("从零开始", "有人之前没接触过跨境电商，想从零开始了解；"),
            ("已经开店", "有人店已经开了一段时间，但一直没有起色；"),
            ("工厂 · 品牌方", "也有工厂和品牌方，带着自家产品过来，<br>希望团队能尽快把 TikTok 这条路跑通。"),
        ]) + "</section>",
        center("大家来的原因不一样，", "但遇到的问题很相似：", top=26),
        p(f"网上的东西看了不少，<br>真要自己动手，<br>{mark('还是不知道该怎么做。')}",
          f"margin-top:14px;font-size:21px;line-height:1.7;color:{INK};font-weight:700;letter-spacing:0.5px;text-align:center;"),
        center("这五天，我们就从这里开始。", top=18),
        top=44)

    ch1 = chapter(
        opener(1, "看了那么多教程，怎么还是理不清？"),
        photo("01-whiteboard.jpg", "老师在白板前讲解", "课堂 · 10.12"),
        body("网上的内容很多，但大多是零散的。",
             "今天看一个选品技巧，明天看一个上架教程，始终串不成一条完整的路。", top=24),
        answer("所以课上没有急着讲技巧，", "而是把整件事从头到尾梳理一遍："),
        f'<section style="margin-top:14px;">' + rows([
            (f'<span style="color:{BLUE};font-size:13px;font-weight:600;margin-right:10px;">01</span>这门生意是怎么运转的', ""),
            (f'<span style="color:{BLUE};font-size:13px;font-weight:600;margin-right:10px;">02</span>每一步在做什么', ""),
            (f'<span style="color:{BLUE};font-size:13px;font-weight:600;margin-right:10px;">03</span>前后怎么衔接', ""),
        ]) + "</section>",
        center("讲解过程中随时可以提问，", "有不清楚的地方当场讲明白再往下走。", top=20))

    ch2 = chapter(
        opener(2, "看的时候都懂，自己一做就出问题"),
        photo("02-hands-on.jpg", "学员在自己的电脑上实操，老师在旁指导", "课堂 · 10.16"),
        body("看别人操作很顺，轮到自己，往往不是这里填错，就是那里找不到入口。", top=24),
        answer(f"所以这五天里，{mark('大部分时间')}", f"{mark('是同学们在自己的电脑上实际操作。')}"),
        body("老师讲完一步，大家跟着做一步，老师逐个查看每个人的操作，有报错、有卡住的地方，就过去一起看、一起解决。"),
        loop_diagram(),
        answer("每一步都自己亲手做过，", "回去再操作时会顺很多。", top=22))

    ch3 = chapter(
        opener(3, "我的情况，跟别人不太一样"),
        p("左右滑动 →", f"margin-top:26px;font-size:12px;line-height:1;color:{MUTED};letter-spacing:2px;text-align:right;"),
        f'<section style="margin-top:10px;overflow-x:auto;overflow-y:hidden;white-space:nowrap;'
        f'-webkit-overflow-scrolling:touch;font-size:0;line-height:0;">'
        + "".join(
            f'<section style="display:inline-block;width:74%;vertical-align:top;margin-right:{mr};white-space:normal;">'
            f'<section style="border-radius:16px;overflow:hidden;line-height:0;font-size:0;">{img(n, a)}</section>'
            + caption(c) + "</section>"
            for n, a, c, mr in [("03-table.jpg", "老师与学员围桌一对一交流", "一对一 · 10.14", "10px"),
                                ("03-phone.jpg", "老师与学员对着手机交流", "一对一 · 10.15", "0")])
        + "</section>",
        center("刚起步的人和已经开店的人，", "需要的答案不一样；", "工厂关心的问题，", "和个人卖家也不一样。", top=24),
        answer("所以除了集体授课，", f"课程中也安排了{mark('一对一的交流时间')}。"),
        p("你是哪一种？轻点看看。",
          f"margin-top:30px;font-size:13px;line-height:1.4;color:{BLUE};font-weight:600;letter-spacing:2px;text-align:center;"),
        f'<section style="margin-top:6px;line-height:0;font-size:0;">'
        + persona_card("从零开始", "我该从哪儿开始？", "先把整件事从头到尾梳理一遍：", "怎么运转，每一步做什么，前后怎么衔接。")
        + persona_card("已经开店", "店开了，为什么一直没起色？", "打开自己的店铺后台，", "和老师一起看数据、找问题。")
        + persona_card("工厂 · 品牌方", "我的产品，适合怎么卖？", "带来自家产品，聊这个产品", "适合怎么卖、卖给谁。")
        + "</section>",
        answer("针对每个人的实际情况，给出具体的建议。", top=22))

    ch4 = chapter(
        opener(4, "真正在做的团队，平时是怎么做内容的？"),
        photo("04-studio.jpg", "公司内容团队的拍摄现场", "拍摄间 · 10.14"),
        center("我们的每一期线下课，都在公司里上。", "同学们上课、实操的地方，",
               f"{mark('也是公司团队每天工作的地方。')}", top=24),
        answer("所以除了听课，大家还能直接看到", "一家 TikTok 跨境电商公司日常是怎么运转的。"),
        body("以内容为例，我们带大家完整看了一遍员工平时的工作流程：每个环节怎么做、用什么工具、需要注意什么。"),
        pipeline(),
        center("有问题可以直接问身边正在做这件事的同事。", top=22))

    ch5 = chapter(
        opener(5, "五天，只是一个开始"),
        photo("05-classroom.jpg", "第 8 期课堂全景", "课堂 · 10.12"),
        body("五天能解决的问题是有限的。",
             "真正开始做店以后，还会遇到选品、运营、内容、数据等各种新情况，很多问题要在实际操作中才会出现。", top=24),
        answer("所以课程结束并不是结束。"),
        body(f"{mark('线上课程和学员答疑群会一直保留')}，同学们回去实操中遇到的问题，可以随时在群里提出，我们会持续解答。",
             "对于大家普遍关心的问题，后续也会安排专门的讲解。"),
        after_timeline())

    outro = (f'<section style="margin-top:88px;border-radius:28px;overflow:hidden;background-color:{NIGHT};'
             'background-image:radial-gradient(90% 60% at 50% 100%,rgba(0,60,172,0.65) 0%,rgba(0,60,172,0) 70%);'
             'padding:44px 24px 30px;text-align:center;">'
             + p("线下的五天，<br>是帮大家把路走通；<br>"
                 f'<span style="color:{YELLOW};">之后的路，<br>我们继续一起走。</span>',
                 "font-size:26px;line-height:1.55;color:#FFFFFF;font-weight:700;letter-spacing:1px;text-align:center;")
             + '<section style="margin:34px auto 0;width:48px;height:1px;line-height:1px;font-size:0;'
               'background-color:rgba(255,255,255,0.3);">&nbsp;</section>'
             + p(f'<span style="display:inline-block;padding:7px 14px;border-radius:999px;background-color:{YELLOW};'
                 f'color:{INK};font-size:12px;line-height:1;font-weight:700;letter-spacing:2px;">第 9 期 · 招生中</span>',
                 "margin-top:28px;line-height:1;text-align:center;")
             + p("第 9 期线下实操课正在招生中，<br>想了解的朋友，<br>欢迎后台留言或私信我们。",
                 "margin-top:16px;font-size:15px;line-height:1.8;color:#FFFFFF;letter-spacing:0.5px;text-align:center;")
             + f'<img src="{IMG}logo-white.png" alt="云拓会" style="display:block;width:84px;height:auto;margin:40px auto 0;">'
             + p("森拓旗下 · 跨境电商实操培训",
                 f"margin-top:12px;font-size:11px;line-height:1;color:{NIGHT_TEXT};letter-spacing:2px;text-align:center;")
             + "</section>")

    foot = p("本文照片均摄于云拓会第 8 期线下实操课",
             f"margin-top:18px;font-size:12px;line-height:1.6;color:{MUTED};text-align:center;letter-spacing:1px;")

    return (f'<section style="margin:0;padding:0;font-family:{FONT};color:{BODY};'
            'font-size:16px;line-height:1.9;word-wrap:break-word;-webkit-font-smoothing:antialiased;">'
            + hero + intro + ch1 + ch2 + ch3 + ch4 + ch5 + outro + foot + "</section>")


def compact(s):
    return re.sub(r">\s+<", "><", s.strip())


# ── 检查：公众号会过滤或不支持的写法 ───────────────────────
FORBIDDEN = {
    r"\sid=": "id 属性会被公众号删除",
    r"\sclass=": "class 无样式表可用",
    r"<style": "<style> 会被删除",
    r"<script": "<script> 会被删除",
    r"position:\s*(absolute|fixed)": "绝对/固定定位不可靠",
    r"url\(#": "url(#id) 引用会失效",
    r"href=": "SVG 引用 / 外链不可用",
    r"<(foreignObject|filter|mask|clipPath|linearGradient|radialGradient)": "依赖 id 的 SVG 特性",
}


def lint(fragment):
    problems = [f"{msg}：{pat}" for pat, msg in FORBIDDEN.items() if re.search(pat, fragment)]
    text = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<svg.*?</svg>", "", fragment, flags=re.S)))
    return problems, len(text)


# ── 工具页 ───────────────────────────────────────────────
def tool_page(fragment, img_bases, full_doc):
    preview = fragment.replace(IMG, "img/")
    payload = json.dumps({"html": fragment, "bases": img_bases}, ensure_ascii=False).replace("</", "<\\/")
    page = (TOOL_HEAD.replace("{{CSS}}", TOOL_CSS)
            + TOOL_BODY.replace("{{ARTICLE}}", preview).replace("{{TITLE}}", TITLE).replace("{{DIGEST}}", DIGEST)
            + f"<script>const PAYLOAD = {payload};</script>" + TOOL_JS)
    if full_doc:
        return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
                + page.replace("<!--/head-->", "</head><body>", 1) + "</body></html>")
    return page.replace("<!--/head-->", "", 1)


TOOL_HEAD = """<title>第 8 期实操课回顾</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>{{CSS}}</style>
<!--/head-->"""

TOOL_CSS = """
/* 布局：左侧 375 宽手机屏还原公众号正文，右侧为发布控制台；窄屏上下堆叠。单一深色审稿台主题。 */
:root{--bg:#0D0F13;--panel:#15181E;--line:#262A32;--fg:#ECEDEF;--muted:#959AA5;--accent:#FFC833;--blue-lt:#6F9BFF;--ok:#4CD38A;--warn:#FFB547;--screen:#FFFFFF;
--sans:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",sans-serif;--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;color-scheme:dark}
*{box-sizing:border-box}
html,body{background:var(--bg);color:var(--fg)}
body{margin:0;font:14px/1.6 var(--sans);-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding-block:28px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
header.top{padding-bottom:22px;border-bottom:1px solid var(--line)}
.kicker{font:600 11px/1 var(--mono);letter-spacing:.18em;color:var(--accent);text-transform:uppercase}
h1{margin:10px 0 0;font-size:26px;line-height:1.2;font-weight:700;letter-spacing:-.01em;text-wrap:balance}
.sub{color:var(--muted);margin:6px 0 0}
.grid{display:grid;grid-template-columns:minmax(0,420px) minmax(0,1fr);gap:40px;margin-top:32px;align-items:start}
.phone{background:#000;border-radius:46px;padding:14px;box-shadow:0 0 0 1px #2a2d35,0 30px 80px rgba(0,0,0,.55);max-width:403px;margin:0 auto;width:100%}
.screen{background:var(--screen);border-radius:34px;overflow:hidden}
.bar{display:flex;justify-content:space-between;align-items:center;padding:14px 22px 8px;font:600 13px/1 var(--sans);color:#111}
.bar i{display:block;width:96px;height:26px;background:#000;border-radius:14px}
.wx{padding:6px 16px 10px;border-bottom:1px solid #eee}
.wx b{display:block;font-size:20px;line-height:1.4;color:#111;margin-top:8px}
.wx span{display:block;font-size:13px;color:#576B95;margin-top:6px}
.scroll{height:min(78vh,760px);overflow-y:auto;overscroll-behavior:contain}
.article{padding:20px 16px 40px;background:#fff}
.panel{position:sticky;top:calc(env(safe-area-inset-top,0px) + 20px);display:grid;gap:18px;min-width:0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:20px;min-width:0}
.card h2{margin:0 0 4px;font-size:15px;font-weight:600}
.card p{margin:0;color:var(--muted)}
.btn{appearance:none;border:0;border-radius:12px;padding:13px 18px;font:600 15px/1 var(--sans);cursor:pointer;transition:transform .12s ease}
.btn:active{transform:scale(.98)}
.btn:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.primary{background:var(--accent);color:#111;width:100%}
.ghost{background:transparent;color:var(--fg);border:1px solid var(--line);padding:10px 14px;font-size:13px}
.row{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
label.f{display:block;font-size:12px;color:var(--muted);margin:16px 0 6px}
select,input[type=text]{width:100%;background:#0F1116;color:var(--fg);border:1px solid var(--line);border-radius:10px;padding:10px 12px;font:13px/1.4 var(--mono);min-width:0}
.status{margin-top:12px;font-size:13px;min-height:1.6em}
.status.ok{color:var(--ok)}.status.err{color:var(--warn)}
ol.steps{margin:10px 0 0;padding-left:18px;color:var(--muted)}
ol.steps li{margin:6px 0}
ol.steps b{color:var(--fg);font-weight:600}
.matrix{display:grid;gap:10px;margin-top:10px}
.m{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;padding:10px 0;border-top:1px solid var(--line)}
.m:first-child{border-top:0}
.m strong{font-weight:600;font-size:13px}
.m em{font-style:normal;color:var(--muted);font-size:12px;grid-column:1/-1}
.chip{font:600 10px/1 var(--mono);letter-spacing:.08em;padding:5px 7px;border-radius:6px;white-space:nowrap;align-self:start}
.c-ok{background:rgba(76,211,138,.14);color:var(--ok)}
.c-wx{background:rgba(111,155,255,.16);color:var(--blue-lt)}
.c-dev{background:rgba(255,181,71,.15);color:var(--warn)}
.meta{display:grid;gap:8px;margin-top:10px}
.meta div{display:flex;gap:10px;align-items:flex-start;justify-content:space-between}
.meta span{color:var(--fg);min-width:0}
@media (max-width:860px){.grid{grid-template-columns:minmax(0,1fr)}.panel{position:static}}
@media (max-width:480px){.phone{padding:0;border-radius:0;box-shadow:none;background:transparent;width:auto;max-width:none;margin:0 calc(-1 * max(16px,env(safe-area-inset-left,0px)))}.screen{border-radius:0}.bar{display:none}.scroll{height:auto;overflow:visible}}
@media (prefers-reduced-motion:reduce){.btn{transition:none}}
"""

TOOL_BODY = """<div class="wrap">
<header class="top">
  <div class="kicker">云拓会 · 第 8 期线下实操课 · 公众号正文</div>
  <h1>{{TITLE}}</h1>
  <p class="sub">左侧是正文在手机上的样子，交互可以直接点；右侧负责复制进公众号。</p>
</header>
<div class="grid">
  <section aria-label="手机预览">
    <div class="phone"><div class="screen">
      <div class="bar"><span>9:41</span><i></i><span>●●●</span></div>
      <div class="scroll">
        <div class="wx"><b>{{TITLE}}</b><span>云拓会</span></div>
        <div class="article" id="article">{{ARTICLE}}</div>
      </div>
    </div></div>
  </section>
  <aside class="panel">
    <div class="card">
      <h2>复制到公众号</h2>
      <p>在公众号后台新建文章，光标放进正文区，粘贴即可。</p>
      <label class="f" for="base">图片地址（粘贴后公众号会自动转存）</label>
      <select id="base"></select>
      <input type="text" id="custom" placeholder="自定义前缀，例如 https://你的图床/vol08/" hidden>
      <div class="row"><button class="btn primary" id="copy" type="button">复制正文</button></div>
      <div class="row">
        <button class="btn ghost" id="copySrc" type="button">复制 HTML 源码</button>
        <button class="btn ghost" id="reset" type="button">重置交互</button>
      </div>
      <div class="status" id="status" role="status" aria-live="polite"></div>
    </div>
    <div class="card">
      <h2>标题与摘要</h2>
      <div class="meta">
        <div><span id="t1">{{TITLE}}</span><button class="btn ghost" data-copy="t1" type="button">复制</button></div>
        <div><span id="t2">{{DIGEST}}</span><button class="btn ghost" data-copy="t2" type="button">复制</button></div>
      </div>
    </div>
    <div class="card">
      <h2>发布步骤</h2>
      <ol class="steps">
        <li>公众号后台 → <b>新的创作 → 文章</b>，填入上面的标题与摘要。</li>
        <li>点 <b>复制正文</b>，在编辑器正文区 <b>Ctrl/⌘ + V</b>。</li>
        <li>等图片转存完成；若有破图，点该图 → <b>替换</b>，从 <b>img/</b> 选同名图片。</li>
        <li><b>保存为草稿 → 预览 → 发送到手机</b>，按下方清单在 iPhone 与安卓各点一遍。</li>
      </ol>
    </div>
    <div class="card">
      <h2>效果与验证</h2>
      <div class="matrix">
        <div class="m"><strong>开头「08」描边后填色</strong><span class="chip c-wx">打开时播放</span><em>SMIL 自动动画，位于首屏。</em></div>
        <div class="m"><strong>02 课堂节奏环：黄点循环经过四步</strong><span class="chip c-wx">持续动画</span><em>animateMotion，不需要点击。</em></div>
        <div class="m"><strong>03 三种情况卡片：轻点看课上怎么做</strong><span class="chip c-wx">轻点 × 3</span><em>每张卡独立；被过滤时直接显示答案。</em></div>
        <div class="m"><strong>04 一条视频的流程：轻点走一遍六步</strong><span class="chip c-wx">轻点播放</span><em>被过滤时直接显示六步全亮。</em></div>
        <div class="m"><strong>05 五天之后：虚线一直往后流</strong><span class="chip c-wx">持续动画</span><em>不需要点击。</em></div>
        <div class="m"><strong>版式、横滑照片、荧光笔强调</strong><span class="chip c-ok">本地已演示</span><em>纯内联样式。荧光笔用渐变背景，被过滤时只剩加粗。</em></div>
        <div class="m"><strong>粘贴后结构与交互是否保留</strong><span class="chip c-dev">需真机验证</span><em>iPhone、安卓、深色模式各看一遍。</em></div>
        <div class="m"><strong>图片自动转存</strong><span class="chip c-dev">需后台验证</span><em>失败时用「替换图片」，或用 publish_draft.py 上传。</em></div>
      </div>
    </div>
  </aside>
</div>
</div>"""

TOOL_JS = """<script>
(function(){
  var $ = function(id){ return document.getElementById(id); };
  var sel = $('base'), custom = $('custom'), status = $('status');
  PAYLOAD.bases.forEach(function(b){ var o = document.createElement('option'); o.value = b.url; o.textContent = b.name; sel.appendChild(o); });
  var o = document.createElement('option'); o.value = '__custom'; o.textContent = '自定义前缀…'; sel.appendChild(o);
  try { var saved = localStorage.getItem('vol08-base'); if (saved && [].some.call(sel.options, function(x){ return x.value === saved; })) sel.value = saved; } catch (e) {}
  function syncCustom(){ custom.hidden = sel.value !== '__custom'; }
  sel.addEventListener('change', function(){ syncCustom(); try { localStorage.setItem('vol08-base', sel.value); } catch (e) {} });
  syncCustom();
  function base(){ var v = sel.value === '__custom' ? custom.value.trim() : sel.value; if (v && !/\\/$/.test(v)) v += '/'; return v; }
  function payload(){ return PAYLOAD.html.split('{{IMG}}').join(base()); }
  function plain(h){ var d = document.createElement('div'); d.innerHTML = h; return d.textContent; }
  function say(msg, ok){ status.textContent = msg; status.className = 'status ' + (ok ? 'ok' : 'err'); }
  function viaEvent(data){
    var done = false;
    function h(e){ Object.keys(data).forEach(function(k){ e.clipboardData.setData(k, data[k]); }); e.preventDefault(); done = true; }
    document.addEventListener('copy', h);
    try { document.execCommand('copy'); } catch (e) {}
    document.removeEventListener('copy', h);
    return done;
  }
  async function copyRich(){
    if (sel.value === '__custom' && !custom.value.trim()) { say('请先填写自定义图片前缀。', false); custom.focus(); return; }
    var h = payload(), t = plain(h);
    if (viaEvent({'text/html': h, 'text/plain': t})) { say('已复制正文。到公众号编辑器正文区粘贴即可。', true); return; }
    try {
      await navigator.clipboard.write([new ClipboardItem({'text/html': new Blob([h], {type: 'text/html'}), 'text/plain': new Blob([t], {type: 'text/plain'})})]);
      say('已复制正文。到公众号编辑器正文区粘贴即可。', true);
    } catch (e) { say('浏览器拒绝了复制。请在电脑版 Chrome / Edge 中打开本页再试。', false); }
  }
  async function copyText(s, okMsg){
    try { await navigator.clipboard.writeText(s); say(okMsg, true); return; } catch (e) {}
    if (viaEvent({'text/plain': s})) say(okMsg, true); else say('浏览器拒绝了复制。', false);
  }
  $('copy').addEventListener('click', copyRich);
  $('copySrc').addEventListener('click', function(){ copyText(payload(), '已复制 HTML 源码，可粘贴到支持源码模式的编辑器。'); });
  $('reset').addEventListener('click', function(){ var a = $('article'); a.innerHTML = a.innerHTML; say('交互已重置。', true); });
  document.querySelectorAll('[data-copy]').forEach(function(b){ b.addEventListener('click', function(){ copyText($(b.dataset.copy).textContent, '已复制。'); }); });
})();
</script>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="e429b17c583059272917b2c4bc7d96db39396e37", help="图片所在的 git 提交（用于 CDN 地址）")
    args = ap.parse_args()
    bases = [
        {"name": "jsDelivr CDN（推荐）", "url": f"https://cdn.jsdelivr.net/gh/{REPO}@{args.ref}/{IMG_PATH}"},
        {"name": "GitHub Raw", "url": f"https://raw.githubusercontent.com/{REPO}/{args.ref}/{IMG_PATH}"},
    ]
    frag = compact(article())
    problems, n_text = lint(frag)
    if problems:
        raise SystemExit("正文包含公众号不兼容写法：\n  " + "\n  ".join(problems))

    (ROOT / "dist").mkdir(exist_ok=True)
    (ROOT / "dist" / "article.html").write_text(frag.replace(IMG, bases[0]["url"]), encoding="utf-8")
    (ROOT / "dist" / "article.template.html").write_text(frag, encoding="utf-8")
    (ROOT / "preview.html").write_text(tool_page(frag, bases, True), encoding="utf-8")
    (ROOT / "artifact").mkdir(exist_ok=True)
    (ROOT / "artifact" / "index.html").write_text(tool_page(frag, bases, False), encoding="utf-8")
    print(f"正文 {len(frag.encode('utf-8')) / 1024:.1f} KB，可见文字约 {n_text} 字，兼容性检查通过。")


if __name__ == "__main__":
    main()
