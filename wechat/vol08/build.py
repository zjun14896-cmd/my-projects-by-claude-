#!/usr/bin/env python3
"""云拓会 · 实操现场 Vol.08 —— 公众号正文构建脚本。

一份源，三个产物：
  dist/article.html      粘贴进公众号编辑器的正文片段（图片用 CDN 绝对地址）
  preview.html           本地审稿 + 一键复制工具（完整 HTML 文档）
  artifact/index.html    同一工具页的在线版本（无文档骨架）

正文只用公众号会保留的写法：内联 style、<section>/<p>/<span>/<img>、内联 <svg> + SMIL。
不用 id / class / <style> / <script> / position:absolute / url(#…)。
所有交互动画都遵循「静态兜底」：SMIL 被过滤时，画面停在可读的完成态（勾选清单停在未勾选态）。

用法：python3 build.py [--img-base URL前缀]
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

# ── 设计令牌 ─────────────────────────────────────────────
BLUE = "#003CAC"      # 品牌蓝（取自 logo）
YELLOW = "#FFC833"    # 品牌黄（取自 logo）
INK = "#1D1D1F"       # 标题
BODY = "#3C3C43"      # 正文
GRAY = "#86868B"      # 图注 / 次要
DARK = "#07090F"      # 深色模块底
D_TEXT = "#F5F5F7"
D_MUTED = "#A1A1A8"
FONT = ("-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB',"
        "'Microsoft YaHei','Helvetica Neue',Arial,sans-serif")
SVG_NS = 'xmlns="http://www.w3.org/2000/svg"'


# ── 基础组件 ─────────────────────────────────────────────
def p(text, style=""):
    return f'<p style="margin:0;padding:0;{style}">{text}</p>'


def body(text, top=18):
    return p(text, f"margin-top:{top}px;font-size:16px;line-height:1.85;color:{BODY};"
                   "letter-spacing:0.4px;text-align:justify;")


def eyebrow(num, label, color=BLUE):
    return p(f'{num}<span style="color:#C7C7CC;margin:0 8px;">/</span>{label}',
             f"font-size:12px;line-height:1.4;letter-spacing:2.5px;color:{color};font-weight:600;")


def h2(text):
    return p(text, f"margin-top:14px;font-size:27px;line-height:1.34;color:{INK};"
                   "font-weight:700;letter-spacing:-0.2px;")


def caption(text):
    return p(text, f"margin-top:10px;font-size:12px;line-height:1.6;color:{GRAY};letter-spacing:0.5px;")


def img(name, alt):
    return (f'<img src="{IMG}{name}" alt="{alt}" '
            'style="display:block;width:100%;height:auto;margin:0;padding:0;border:0;">')


def photo(name, alt, cap=None, overlay="", radius=18, top=28):
    out = (f'<section style="margin-top:{top}px;">'
           f'<section style="border-radius:{radius}px;overflow:hidden;line-height:0;font-size:0;">'
           f'{img(name, alt)}{overlay}</section>')
    if cap:
        out += caption(cap)
    return out + "</section>"


def chapter(*parts, top=76):
    return f'<section style="margin-top:{top}px;">{"".join(parts)}</section>'


def dark_module(svg, top=28, radius=24, glow_at="50% 110%"):
    """深色交互模块：外层 section 负责圆角裁切与底色（品牌蓝柔光用 CSS 渐变，被过滤时退回纯色）。"""
    return (f'<section style="margin-top:{top}px;border-radius:{radius}px;overflow:hidden;'
            f'line-height:0;font-size:0;background-color:{DARK};'
            f'background-image:radial-gradient(90% 75% at {glow_at},rgba(0,60,172,0.62) 0%,rgba(0,60,172,0) 70%);">'
            f'{svg}</section>')


# ── SMIL 片段 ────────────────────────────────────────────
# 层级技巧：公众号会删掉 id，无法用 "xx.click" 跨元素触发。
# 因此把可点击的透明热区放在最深层，点击事件会冒泡到每一层祖先 <g>，
# 每层 <g> 用 begin="click" 驱动自己的 fill-opacity / transform（可继承属性），
# 各层的可见元素继承所在层的值，从而一次轻点触发一整套编排。
def fade(start, end, begin="click", dur="0.45s"):
    """属性基值写在 <g> 上作为兜底终态；加载即 <set> 到初始态；轻点后动画到终态。"""
    return (f'<set attributeName="fill-opacity" to="{start}" begin="0s"/>'
            f'<animate attributeName="fill-opacity" values="{start};{end}" dur="{dur}" '
            f'begin="{begin}" fill="freeze" restart="never"/>')


def slide(dx0, dy0, begin="click", dur="0.6s"):
    return (f'<animateTransform attributeName="transform" type="translate" from="{dx0} {dy0}" '
            f'to="{dx0} {dy0}" dur="0.001s" begin="0s" fill="freeze"/>'
            f'<animateTransform attributeName="transform" type="translate" values="{dx0} {dy0};0 0" '
            f'keyTimes="0;1" calcMode="spline" keySplines="0.2 0.8 0.2 1" dur="{dur}" '
            f'begin="{begin}" fill="freeze" restart="never"/>')


def hit(x=-400, y=-400, w=1200, h=1200):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#000000" fill-opacity="0" '
            'pointer-events="all" style="cursor:pointer;"/>')


def pulse(cx, cy, r0, r1, period="1.8s", op="0.55"):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r0}" fill="{YELLOW}" opacity="{op}">'
            f'<animate attributeName="r" values="{r0};{r1}" dur="{period}" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="{op};0" dur="{period}" repeatCount="indefinite"/>'
            '</circle>')


def svg_open(w, h, style=""):
    return (f'<svg {SVG_NS} viewBox="0 0 {w} {h}" width="100%" '
            f'style="display:block;width:100%;{style}" font-family="{FONT}">')


# ── 交互模块 ─────────────────────────────────────────────
def hero_timeline():
    """开班五天：加载时进度线划过，五个日期点依次亮起。"""
    xs = [6, 78, 150, 222, 294]
    dots = ""
    for i, x in enumerate(xs):
        b = 0.5 + 0.38 * i
        dots += (f'<circle cx="{x}" cy="40" r="4.5" fill="{YELLOW}" fill-opacity="1">'
                 f'<set attributeName="fill-opacity" to="0.18" begin="0s"/>'
                 f'<animate attributeName="fill-opacity" values="0.18;1" dur="0.35s" begin="{b:.2f}s" fill="freeze"/>'
                 '</circle>')
        dots += (f'<text x="{x}" y="64" font-size="11" fill="{D_MUTED}" text-anchor="middle" '
                 f'letter-spacing="0.5">{12 + i}</text>')
    return (svg_open(300, 70, "margin-top:30px;")
            + f'<text x="0" y="14" font-size="11" fill="{D_MUTED}" letter-spacing="1">10.12</text>'
            + f'<text x="150" y="14" font-size="11" fill="{D_TEXT}" text-anchor="middle" letter-spacing="2">五天 · 线下实操</text>'
            + f'<text x="300" y="14" font-size="11" fill="{D_MUTED}" text-anchor="end" letter-spacing="1">10.16</text>'
            + '<rect x="6" y="39.25" width="288" height="1.5" fill="#2C2F38"/>'
            + f'<line x1="6" y1="40" x2="294" y2="40" stroke="{YELLOW}" stroke-width="1.5" '
              'stroke-dasharray="288" stroke-dashoffset="0">'
              '<set attributeName="stroke-dashoffset" to="288" begin="0s"/>'
              '<animate attributeName="stroke-dashoffset" values="288;0" dur="1.6s" begin="0.5s" '
              'calcMode="spline" keyTimes="0;1" keySplines="0.4 0 0.2 1" fill="freeze"/></line>'
            + dots + "</svg>")


def switch_module():
    """「听懂 → 做到」开关：轻点后滑块右移、轨道变蓝、大字由「听懂了。」换成「做出来了。」"""
    W, H = 343, 300
    cx = W / 2
    return dark_module(
        svg_open(W, H)
        + f'<text x="24" y="44" font-size="12" font-weight="600" fill="{YELLOW}" letter-spacing="3">先试一下</text>'
        + f'<text x="117" y="195" font-size="13" fill="{D_MUTED}" text-anchor="end" letter-spacing="1">听懂</text>'
        + f'<text x="226" y="195" font-size="13" fill="{D_MUTED}" letter-spacing="1">做到</text>'
        # L1 终态层
        + '<g fill-opacity="1">' + fade(0, 1, "click+0.12s", "0.5s")
        + f'<rect x="131.5" y="168" width="80" height="44" rx="22" fill="{BLUE}"/>'
        + f'<text x="{cx}" y="128" font-size="38" font-weight="700" fill="{YELLOW}" text-anchor="middle" letter-spacing="1">做出来了。</text>'
        + f'<text x="{cx}" y="262" font-size="13" fill="#C7C7CC" text-anchor="middle" letter-spacing="0.5">中间这一步，就是课堂要陪你走完的路。</text>'
        # L2 初始态层
        + '<g fill-opacity="0">' + fade(1, 0, "click", "0.3s")
        + '<rect x="131.5" y="168" width="80" height="44" rx="22" fill="#3A3A3F"/>'
        + f'<text x="{cx}" y="128" font-size="38" font-weight="700" fill="{D_TEXT}" text-anchor="middle" letter-spacing="1">听懂了。</text>'
        + f'<text x="{cx}" y="262" font-size="13" fill="{D_MUTED}" text-anchor="middle" letter-spacing="1">轻点开关</text>'
        + pulse(153.5, 190, 18, 34)
        # L3 滑块层（含热区）
        + '<g transform="translate(36 0)">'
        + '<animateTransform attributeName="transform" type="translate" from="0 0" to="0 0" '
          'dur="0.001s" begin="0s" fill="freeze"/>'
        + '<animateTransform attributeName="transform" type="translate" values="0 0;36 0" '
          'keyTimes="0;1" calcMode="spline" keySplines="0.3 0 0.2 1" dur="0.38s" '
          'begin="click" fill="freeze" restart="never"/>'
        + '<circle cx="153.5" cy="192" r="18" fill="#000000" fill-opacity="1" opacity="0.35"/>'
        + '<circle cx="153.5" cy="190" r="18" fill="#FFFFFF" fill-opacity="1"/>'
        + hit()
        + "</g></g></g></svg>")


def hotspot(w, h, x, y, label, label_at="bottom"):
    """照片热点：脉冲点提示可点，轻点后出现一条注释。叠在 <img> 上（负 margin，不用绝对定位）。"""
    by = h - 62 if label_at == "bottom" else 12
    pill_x = x + 18 if x < w - 80 else x - 66
    return (svg_open(w, h, f"margin-top:-{h / w * 100:.4f}%;pointer-events:none;")
            # L1 注释层
            + '<g fill-opacity="1">' + fade(0, 1, "click+0.1s", "0.5s")
            + f'<rect x="12" y="{by}" width="{w - 24}" height="50" rx="12" fill="{DARK}" opacity="0.74"/>'
            + f'<circle cx="31" cy="{by + 25}" r="3.5" fill="{YELLOW}"/>'
            + f'<text x="44" y="{by + 30}" font-size="15" fill="#FFFFFF" letter-spacing="0.5">{label}</text>'
            # L2 提示层（含热区）
            + '<g fill-opacity="0">' + fade(1, 0, "click", "0.3s")
            + pulse(x, y, 10, 30)
            + f'<circle cx="{x}" cy="{y}" r="10" fill="#FFFFFF" opacity="0.95"/>'
            + f'<circle cx="{x}" cy="{y}" r="5" fill="{YELLOW}"/>'
            + f'<rect x="{pill_x}" y="{y - 11}" width="48" height="22" rx="11" fill="#FFFFFF" opacity="0.92"/>'
            + f'<text x="{pill_x + 24}" y="{y + 4.5}" font-size="12" fill="{INK}" text-anchor="middle" letter-spacing="1">轻点</text>'
            + f'<circle cx="{x}" cy="{y}" r="42" fill="#000000" fill-opacity="0" pointer-events="all" style="cursor:pointer;"/>'
            + "</g></g></svg>")


def question_card():
    """课堂上的一道题：轻点后四个问题依次浮现（文字取自第 8 期课堂屏幕）。"""
    W, H = 343, 404
    rows = ["产品是什么？", "谁可能会买？", "用户可能在什么情况下使用？", "这个产品有什么值得展示？"]
    out = (svg_open(W, H)
           + f'<text x="24" y="46" font-size="12" font-weight="600" fill="{YELLOW}" letter-spacing="3">课堂上的一道题</text>'
           + f'<text x="24" y="98" font-size="28" font-weight="700" fill="#FFFFFF" letter-spacing="0.5">这个产品</text>'
           + f'<text x="24" y="138" font-size="28" font-weight="700" fill="#FFFFFF" letter-spacing="0.5">到底有什么可以卖？</text>'
           + '<rect x="24" y="166" width="295" height="1" fill="#FFFFFF" fill-opacity="1" opacity="0.16"/>'
           # 提示层
           + '<g fill-opacity="0">' + fade(1, 0, "click", "0.25s")
           + pulse(W / 2, 240, 6, 22)
           + f'<circle cx="{W / 2}" cy="240" r="6" fill="{YELLOW}"/>'
           + f'<text x="{W / 2}" y="282" font-size="14" fill="#C7C7CC" text-anchor="middle" letter-spacing="1">轻点卡片，拆开这道题</text>')
    for i, t in enumerate(rows):
        y = 212 + 46 * i
        b = f"click+{0.12 + 0.16 * i:.2f}s"
        out += ('<g fill-opacity="1">' + fade(0, 1, b, "0.5s") + slide(0, 12, b, "0.7s")
                + f'<text x="24" y="{y}" font-size="13" font-weight="600" fill="{YELLOW}" letter-spacing="1">0{i + 1}</text>'
                + f'<text x="62" y="{y}" font-size="16" fill="#FFFFFF" letter-spacing="0.5">{t}</text>')
        if i < len(rows) - 1:
            out += f'<rect x="62" y="{y + 19}" width="257" height="1" fill="#FFFFFF" opacity="0.1"/>'
    out += hit() + "</g>" * len(rows) + "</g></svg>"
    return dark_module(out, glow_at="100% 0%")


def checklist():
    """自测清单：每行独立轻点打勾（静态兜底为未勾选）。"""
    rows = ["想做 TikTok 跨境电商，但还没真正上手",
            "看过不少教程，一到自己操作就卡住",
            "希望有人在旁边，看着你做、帮你找问题",
            "更想用真实的产品练，而不只听概念"]
    out = ""
    for i, t in enumerate(rows):
        W, H = 343, 60
        out += (svg_open(W, H)
                + f'<rect x="0" y="0" width="{W}" height="{H}" fill="{DARK}" fill-opacity="1"/>'
                + '<circle cx="34" cy="30" r="11" fill="none" stroke="#55555C" stroke-width="1.5"/>'
                + f'<text x="58" y="35" font-size="15" fill="{D_TEXT}" letter-spacing="0.3">{t}</text>'
                + ('' if i == len(rows) - 1 else
                   f'<rect x="58" y="59" width="{W - 58}" height="1" fill="#FFFFFF" opacity="0.08"/>')
                + '<g fill-opacity="0" stroke-dashoffset="20">'
                + '<animate attributeName="fill-opacity" values="0;1" dur="0.25s" begin="click" fill="freeze" restart="never"/>'
                + '<animate attributeName="stroke-dashoffset" values="20;0" dur="0.35s" begin="click+0.1s" fill="freeze" restart="never"/>'
                + f'<circle cx="34" cy="30" r="11.75" fill="{YELLOW}"/>'
                + f'<path d="M28.5 30.5 L32.5 34.5 L39.5 26.5" fill="none" stroke="{DARK}" stroke-width="2.2" '
                  'stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="20" pointer-events="none"/>'
                + f'<rect x="0" y="0" width="{W}" height="{H}" fill="#000000" fill-opacity="0" pointer-events="all" style="cursor:pointer;"/>'
                + "</g></svg>")
    return (f'<section style="margin-top:26px;border-radius:24px;overflow:hidden;line-height:0;'
            f'font-size:0;background-color:{DARK};padding:10px 0;">{out}</section>')


def swipe_hint():
    return p('左右滑动'
             + f'<svg {SVG_NS} viewBox="0 0 40 12" width="34" height="10" '
               'style="display:inline-block;width:34px;height:10px;vertical-align:middle;margin-left:8px;">'
             + '<g><animateTransform attributeName="transform" type="translate" values="0 0;6 0;0 0" '
               'dur="1.6s" repeatCount="indefinite"/>'
             + f'<rect x="0" y="5.25" width="30" height="1.5" fill="{GRAY}"/>'
             + f'<path d="M28 1.5 L34 6 L28 10.5" fill="none" stroke="{GRAY}" stroke-width="1.5" '
               'stroke-linecap="round" stroke-linejoin="round"/></g></svg>',
             f"margin-top:26px;font-size:12px;line-height:1;color:{GRAY};letter-spacing:2px;text-align:right;")


def gallery(items):
    """横滑相册（overflow-x 滚动，纯 HTML，无需交互脚本）。"""
    cards = ""
    for i, (name, alt, tag, line) in enumerate(items):
        mr = "0" if i == len(items) - 1 else "12px"
        cards += (f'<section style="display:inline-block;width:76%;vertical-align:top;margin-right:{mr};'
                  'white-space:normal;font-size:16px;line-height:1.6;">'
                  f'<section style="border-radius:18px;overflow:hidden;line-height:0;font-size:0;">{img(name, alt)}</section>'
                  + p(f'<span style="color:{BLUE};font-weight:600;">{tag}</span>',
                      "margin-top:12px;font-size:12px;letter-spacing:2px;")
                  + p(line, f"margin-top:4px;font-size:15px;line-height:1.6;color:{INK};")
                  + "</section>")
    return (swipe_hint()
            + '<section style="margin-top:12px;overflow-x:auto;overflow-y:hidden;white-space:nowrap;'
              f'-webkit-overflow-scrolling:touch;font-size:0;line-height:0;padding-bottom:6px;">{cards}</section>')


# ── 正文 ─────────────────────────────────────────────────
def article():
    hero = (f'<section style="border-radius:26px;overflow:hidden;background-color:{DARK};'
            'background-image:radial-gradient(120% 70% at 100% 0%,rgba(0,60,172,0.6) 0%,rgba(0,60,172,0) 62%);'
            'padding:28px 22px 22px;">'
            f'<img src="{IMG}logo-white.png" alt="云拓会" style="display:block;width:96px;height:auto;margin:0;">'
            + p("实操现场 · VOL.08",
                f"margin-top:44px;font-size:12px;line-height:1.4;letter-spacing:3px;color:{YELLOW};font-weight:600;")
            + p("从听懂，<br>到做出来。",
                "margin-top:12px;font-size:36px;line-height:1.22;color:#FFFFFF;font-weight:700;letter-spacing:-0.3px;")
            + p("TikTok 跨境电商线下实操班 · 第 8 期",
                f"margin-top:14px;font-size:14px;line-height:1.6;color:{D_MUTED};letter-spacing:0.5px;")
            + hero_timeline()
            + photo("01-hero.jpg", "第 8 期课堂，老师在白板前讲解", radius=16, top=22)
            + "</section>")

    intro = chapter(
        p("第 8 期，开班了。",
          f"font-size:21px;line-height:1.5;color:{INK};font-weight:700;letter-spacing:0.2px;"),
        body("从这一期起，每一期课程结束，我们都会在这里留一份记录。"),
        body("不写流程，不列课表。只把课堂里真实发生的事摊开给你看。"
             "如果你正在犹豫要不要来，你想知道的，大概都在下面。", 12),
        switch_module(),
        top=44)

    ch1 = chapter(
        eyebrow("01", "起点"),
        h2("基础不好，<br>跟得上吗？"),
        body("这是很多人报名前最担心的事。"),
        body("所以课堂不从结论讲起，而是从第一个概念讲起："
             f'<span style="color:{INK};font-weight:600;">屏幕上一步一步演示，白板上一笔一笔拆开。</span>', 12),
        body("哪一步没跟上，当场问，当场再讲一遍。", 12),
        photo("02-screen.jpg", "老师对照屏幕讲解，学员边听边记", "屏幕演示，一步一步来"),
        photo("03-whiteboard.jpg", "写满的白板与正在讲解的老师", "轻点照片上的黄点",
              overlay=hotspot(400, 300, 296, 172, "白板写满，是因为没有一步被跳过。"), top=14))

    ch2 = chapter(
        eyebrow("02", "上手"),
        h2("听懂了，<br>可一上手就卡住？"),
        body("这是最常见的问题，也是课堂上最花时间的地方。"),
        body(f'<span style="color:{INK};font-weight:600;">讲完，就动手。</span>'
             "电脑打开，手机拿出来，在自己的设备上，把刚才那一步完整走一遍。", 12),
        body("卡住的地方，正是老师要过来的地方。", 12),
        photo("04-hands-on.jpg", "学员在电脑和手机上实际操作", "轻点照片上的黄点",
              overlay=hotspot(400, 300, 196, 200, "讲完就动手，在自己的设备上做一遍。", "top")))

    quote = (f'<section style="margin-top:80px;text-align:center;">'
             + p(f'讲完就<span style="color:{BLUE};">做</span>，<br>做完再<span style="color:{BLUE};">讲</span>。',
                 f"font-size:31px;line-height:1.4;color:{INK};font-weight:700;letter-spacing:1px;")
             + p("这是课堂上反复发生的事。",
                 f"margin-top:14px;font-size:13px;line-height:1.6;color:{GRAY};letter-spacing:1px;")
             + "</section>")

    ch3 = chapter(
        eyebrow("03", "带教"),
        h2("现场，<br>到底怎么带？"),
        body("不是一个人站在台上讲到底。"),
        body("老师会坐到你对面，凑过来看你的手机屏幕，在灯前和你当面聊。"
             f'<span style="color:{INK};font-weight:600;">同一个问题，换一种说法再讲；同一个操作，看着你做完。</span>', 12),
        gallery([
            ("06-table.jpg", "老师与学员围桌交流", "围桌", "面对面，把问题摊开说。"),
            ("07-phone.jpg", "老师与学员对着手机交流", "手机前", "看着你的屏幕，指出卡在哪。"),
            ("08-light.jpg", "在柔光灯前现场交流", "灯前", "在现场，当面讲清楚。"),
        ]))

    ch4 = chapter(
        eyebrow("04", "落地"),
        h2("讲的东西，<br>能落到具体产品上吗？"),
        body("课堂上讲的每一个方法，最后都要回到一件具体的商品上。"),
        body("比如这一页。屏幕上放的是一台风扇，问题只有一个。", 12),
        photo("05-question.jpg", "课堂屏幕：这个产品到底有什么可以卖？", "课堂实拍 · 屏幕局部"),
        question_card(),
        body("四个问题，看起来都不难。可真把一件商品按这个顺序答一遍，"
             "你就会知道它该拍什么、写给谁、放进什么场景里讲。", 26),
        body(f'<span style="color:{INK};font-weight:600;">这就是落地。</span>', 12))

    ch5 = chapter(
        eyebrow("05", "判断"),
        h2("这种方式，<br>适合我吗？"),
        body("下面四句话，说中你的，就轻点勾上。"),
        checklist(),
        body("勾上了不止一条？那这样的课堂，值得你来现场看一看。", 22))

    outro = (f'<section style="margin-top:80px;border-radius:26px;overflow:hidden;background-color:{DARK};'
             'background-image:radial-gradient(110% 70% at 0% 100%,rgba(0,60,172,0.55) 0%,rgba(0,60,172,0) 60%);'
             'padding:38px 24px 26px;">'
             + p("VOL.08 · 2026.10.12 — 10.16",
                 f"font-size:12px;line-height:1.4;letter-spacing:2.5px;color:{YELLOW};font-weight:600;")
             + p("每一期，<br>都在这里。",
                 "margin-top:14px;font-size:30px;line-height:1.3;color:#FFFFFF;font-weight:700;")
             + p("云拓会是森拓旗下的 TikTok 跨境电商实操培训品牌。"
                 "从第 8 期开始，每一期课堂，我们都会在这里原样记录。",
                 f"margin-top:16px;font-size:15px;line-height:1.85;color:{D_MUTED};letter-spacing:0.4px;text-align:justify;")
             + '<section style="margin-top:26px;height:1px;line-height:1px;font-size:0;'
               'background-color:rgba(255,255,255,0.14);">&nbsp;</section>'
             + p("想了解课程，欢迎在公众号后台给我们留言。",
                 "margin-top:22px;font-size:15px;line-height:1.7;color:#FFFFFF;letter-spacing:0.4px;")
             + '<section style="margin-top:34px;display:flex;align-items:center;justify-content:space-between;">'
             + f'<img src="{IMG}logo-white.png" alt="云拓会" style="display:block;width:84px;height:auto;margin:0;">'
             + p("实操现场", f"font-size:12px;line-height:1;color:{D_MUTED};letter-spacing:3px;")
             + "</section></section>")

    foot = p("本文照片均摄于云拓会第 8 期线下课堂",
             f"margin-top:18px;font-size:12px;line-height:1.6;color:{GRAY};text-align:center;letter-spacing:0.5px;")

    return (f'<section style="margin:0;padding:0;font-family:{FONT};color:{BODY};'
            'font-size:16px;line-height:1.85;word-wrap:break-word;-webkit-font-smoothing:antialiased;">'
            + hero + intro + ch1 + ch2 + quote + ch3 + ch4 + ch5 + outro + foot + "</section>")


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
    head = (TOOL_HEAD.replace("{{CSS}}", TOOL_CSS))
    preview = fragment.replace(IMG, "img/")
    payload = json.dumps({"html": fragment, "bases": img_bases}, ensure_ascii=False).replace("</", "<\\/")
    page = (head + TOOL_BODY.replace("{{ARTICLE}}", preview)
            + f"<script>const PAYLOAD = {payload};</script>" + TOOL_JS)
    if full_doc:
        page = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
                + page.replace("<!--/head-->", "</head><body>", 1) + "</body></html>")
    else:
        page = page.replace("<!--/head-->", "", 1)
    return page


TOOL_HEAD = """<title>实操现场 Vol.08</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>{{CSS}}</style>
<!--/head-->"""

TOOL_CSS = """
/* 布局：左侧 375 宽手机屏还原公众号正文，右侧为发布控制台；窄屏上下堆叠。单一深色审稿台主题。 */
:root{--bg:#0D0F13;--panel:#15181E;--line:#262A32;--fg:#ECEDEF;--muted:#959AA5;--accent:#FFC833;--blue:#003CAC;--blue-lt:#6F9BFF;--ok:#4CD38A;--warn:#FFB547;--screen:#FFFFFF;
--sans:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",sans-serif;--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;color-scheme:dark}
*{box-sizing:border-box}
html,body{background:var(--bg);color:var(--fg)}
body{margin:0;font:14px/1.6 var(--sans);-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding-block:28px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
header.top{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap;padding-bottom:22px;border-bottom:1px solid var(--line)}
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
.btn{appearance:none;border:0;border-radius:12px;padding:13px 18px;font:600 15px/1 var(--sans);cursor:pointer;transition:transform .12s ease,filter .12s}
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
@media (max-width:480px){.phone{padding:0;border-radius:0;box-shadow:none;background:transparent}.screen{border-radius:18px}.bar{display:none}.scroll{height:auto;overflow:visible}}
@media (prefers-reduced-motion:reduce){.btn{transition:none}}
"""

TOOL_BODY = """<div class="wrap">
<header class="top">
  <div>
    <div class="kicker">云拓会 · 实操现场 · Vol.08</div>
    <h1>从听懂，到做出来。</h1>
    <p class="sub">公众号正文审稿与发布台。左侧是正文在手机上的样子，可以直接点交互；右侧负责复制进公众号。</p>
  </div>
</header>
<div class="grid">
  <section aria-label="手机预览">
    <div class="phone"><div class="screen">
      <div class="bar"><span>9:41</span><i></i><span>●●●</span></div>
      <div class="scroll" id="scroll">
        <div class="wx"><b>第 8 期｜从听懂，到做出来</b><span>云拓会 · 实操现场</span></div>
        <div class="article" id="article">{{ARTICLE}}</div>
      </div>
    </div></div>
  </section>
  <aside class="panel">
    <div class="card">
      <h2>复制到公众号</h2>
      <p>在公众号后台新建图文，光标放进正文区，粘贴即可。</p>
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
      <h2>发布步骤</h2>
      <ol class="steps">
        <li>公众号后台 → <b>新的创作 → 文章</b>，标题与摘要见下方。</li>
        <li>点 <b>复制正文</b>，在编辑器正文区 <b>Ctrl/⌘ + V</b>。</li>
        <li>等待图片转存完成；若有图片显示失败，点该图 → <b>替换</b>，从 <b>img/</b> 文件夹选同名图片。</li>
        <li><b>保存为草稿 → 预览 → 发送到手机</b>，按右下清单在 iPhone 与安卓各点一遍。</li>
        <li>交互全部正常后再群发。</li>
      </ol>
    </div>
    <div class="card">
      <h2>标题与摘要</h2>
      <div class="meta">
        <div><span id="t1">第 8 期｜从听懂，到做出来</span><button class="btn ghost" data-copy="t1" type="button">复制</button></div>
        <div><span id="t2">不写流程，不列课表。把第 8 期课堂里真实发生的事，摊开给你看。</span><button class="btn ghost" data-copy="t2" type="button">复制</button></div>
      </div>
    </div>
    <div class="card">
      <h2>效果与验证</h2>
      <div class="matrix">
        <div class="m"><strong>版式：字号层级、留白、圆角照片、深色模块</strong><span class="chip c-ok">本地已演示</span><em>纯内联样式，公众号正常保留。深色模块的底色画在 SVG 里，不受公众号深色模式改色影响。</em></div>
        <div class="m"><strong>开头：五天进度线依次点亮</strong><span class="chip c-wx">SMIL 自动播放</span><em>加载即播放，位于首屏。</em></div>
        <div class="m"><strong>开关：听懂 → 做到</strong><span class="chip c-wx">SMIL begin=click</span><em>热区放在最深层，点击冒泡驱动三层动画；不依赖 id。</em></div>
        <div class="m"><strong>照片热点注释（2 处）</strong><span class="chip c-wx">SVG 叠在图片上</span><em>用负 margin 叠放，不用绝对定位；热点外的区域仍可点开大图。</em></div>
        <div class="m"><strong>横滑相册</strong><span class="chip c-wx">overflow-x 滚动</span><em>纯 HTML，无脚本。</em></div>
        <div class="m"><strong>一道题：四问依次浮现</strong><span class="chip c-wx">SMIL 级联</span><em>静态兜底：动画被过滤时直接显示四个问题。</em></div>
        <div class="m"><strong>自测清单：轻点打勾</strong><span class="chip c-wx">SMIL 描边动画</span><em>每行独立。</em></div>
        <div class="m"><strong>粘贴后结构与交互是否保留</strong><span class="chip c-dev">需真机验证</span><em>重点：负 margin 叠放是否对齐、点击是否触发、安卓是否同样生效、深色模式观感。</em></div>
        <div class="m"><strong>图片自动转存</strong><span class="chip c-dev">需后台验证</span><em>取决于公众号能否拉取图片地址；失败时用「替换图片」，或用 API 脚本上传。</em></div>
      </div>
    </div>
  </aside>
</div>
</div>"""

TOOL_JS = """<script>
(function(){
  var $ = function(id){ return document.getElementById(id); };
  var sel = $('base'), custom = $('custom'), status = $('status');
  PAYLOAD.bases.forEach(function(b, i){ var o = document.createElement('option'); o.value = b.url; o.textContent = b.name; sel.appendChild(o); });
  var o = document.createElement('option'); o.value = '__custom'; o.textContent = '自定义前缀…'; sel.appendChild(o);
  try { var saved = localStorage.getItem('vol08-base'); if (saved) sel.value = saved; } catch (e) {}
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
    ap.add_argument("--ref", default="0f0fb78beb0afad70e992a1c4d38f1d6039066dc", help="图片所在的 git 提交或分支（用于 CDN 地址）")
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
    (ROOT / "dist" / "article.template.html").write_text(frag, encoding="utf-8")  # 供 publish_draft.py 替换图片
    (ROOT / "preview.html").write_text(tool_page(frag, bases, True), encoding="utf-8")
    (ROOT / "artifact").mkdir(exist_ok=True)
    (ROOT / "artifact" / "index.html").write_text(tool_page(frag, bases, False), encoding="utf-8")
    print(f"正文 {len(frag.encode('utf-8')) / 1024:.1f} KB，可见文字约 {n_text} 字，兼容性检查通过。")


if __name__ == "__main__":
    main()
