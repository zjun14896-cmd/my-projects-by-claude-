#!/usr/bin/env python3
"""用公众号官方接口把第 8 期正文直接存进「草稿箱」（备选发布方式，无需复制粘贴）。

适用：已认证、具备素材管理与草稿箱接口权限的公众号。
准备：公众号后台 → 设置与开发 → 基本配置，拿到 AppID / AppSecret，并把运行本脚本电脑的公网 IP 加入「IP 白名单」。

用法：
  export WX_APPID=wx...  WX_SECRET=...
  python3 publish_draft.py              # 上传图片 + 封面，新建草稿
  python3 publish_draft.py --dry-run    # 只检查文件，不调用接口

流程：获取 access_token → 正文图片逐张 uploadimg（得到 mmbiz 地址）→ 封面 add_material（得到 media_id）
     → 替换正文图片地址 → draft/add。完成后到后台「草稿箱」预览并发送到手机验证。
仅依赖 Python 标准库。注意：本脚本未在真实公众号上运行过，首次使用请留意输出的接口报错信息。
"""
import argparse
import json
import mimetypes
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request
import uuid

ROOT = pathlib.Path(__file__).resolve().parent
API = "https://api.weixin.qq.com/cgi-bin"

TITLE = "第 8 期线下实操课结束了：五天，把路走通"
DIGEST = "网上的东西看了不少，真要自己动手，还是不知道该怎么做。这五天，我们就从这里开始。"
AUTHOR = "云拓会"


def call(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read().decode("utf-8"))
    if out.get("errcode"):
        raise SystemExit(f"接口报错 {out.get('errcode')}：{out.get('errmsg')}（{url.split('?')[0]}）")
    return out


def post_json(url, obj):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return call(url, body, {"Content-Type": "application/json; charset=utf-8"})


def post_file(url, path):
    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"media\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    return call(url, body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cover", default="cover/cover-235.jpg")
    args = ap.parse_args()

    template = (ROOT / "dist" / "article.template.html").read_text(encoding="utf-8")
    names = sorted(set(re.findall(r"\{\{IMG\}\}([\w.-]+)", template)))
    files = [ROOT / "img" / n for n in names] + [ROOT / args.cover]
    for f in files:
        if not f.exists():
            raise SystemExit(f"缺少文件：{f}")
        if f.stat().st_size > 1024 * 1024:
            raise SystemExit(f"{f.name} 超过 1MB，uploadimg 不接受，请先压缩")
    print(f"正文图片 {len(names)} 张，封面 {args.cover}")
    if args.dry_run:
        print("检查通过（未调用接口）。")
        return

    appid, secret = os.environ.get("WX_APPID"), os.environ.get("WX_SECRET")
    if not appid or not secret:
        raise SystemExit("请先设置环境变量 WX_APPID 与 WX_SECRET")
    token = post_json(f"{API}/stable_token",
                      {"grant_type": "client_credential", "appid": appid, "secret": secret})["access_token"]

    content = template
    for n in names:
        url = post_file(f"{API}/media/uploadimg?access_token={token}", ROOT / "img" / n)["url"]
        content = content.replace("{{IMG}}" + n, url)
        print(f"  已上传 {n}")
    thumb = post_file(f"{API}/material/add_material?access_token={token}&type=image", ROOT / args.cover)["media_id"]
    print("  已上传封面")

    draft = post_json(f"{API}/draft/add?access_token={token}", {"articles": [{
        "title": TITLE, "author": AUTHOR, "digest": DIGEST, "content": content,
        "thumb_media_id": thumb, "need_open_comment": 0, "only_fans_can_comment": 0,
    }]})
    print(f"草稿已创建：media_id = {draft['media_id']}。请到公众号后台「草稿箱」预览并发送到手机验证。")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as e:
        sys.exit(f"网络错误：{e}")
