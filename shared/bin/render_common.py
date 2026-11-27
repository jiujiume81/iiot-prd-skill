# -*- coding: utf-8 -*-
"""HTML / Word 两条产出线共用的行内格式与工具函数。"""
import html
import re
import os

RE_CODE = re.compile(r'`([^`]+?)`')
RE_BOLD = re.compile(r'\*\*(.+?)\*\*')
RE_ITAL = re.compile(r'(?<!\*)\*([^*\n]+?)\*(?!\*)')
RE_LINK = re.compile(r'\[([^\]]+)\]\(([^)\s]+)\)')


def inline(t):
    """Markdown 行内 → HTML 片段。"""
    t = html.escape(t, quote=False)
    t = RE_CODE.sub(r'<code>\1</code>', t)
    t = RE_BOLD.sub(r'<strong>\1</strong>', t)
    t = RE_ITAL.sub(r'<em>\1</em>', t)
    t = RE_LINK.sub(r'<a href="\2">\1</a>', t)
    return t


def plain(t):
    """去掉行内标记，返回纯文本（用于 Word 的 runs 拆分前的兜底）。"""
    t = RE_CODE.sub(r'\1', t)
    t = RE_BOLD.sub(r'\1', t)
    t = RE_ITAL.sub(r'\1', t)
    t = RE_LINK.sub(r'\1', t)
    return t


def split_runs(t):
    """把行内文本拆成 [(text, {bold/italic/code}), ...]，供 python-docx 逐段写样式。"""
    t = html.unescape(t)
    out = []
    i = 0
    pat = re.compile(r'(`[^`]+?`|\*\*[^*]+?\*\*|(?<!\*)\*[^*\n]+?\*(?!\*)|\[[^\]]+\]\([^)\s]+\))')
    for m in pat.finditer(t):
        if m.start() > i:
            out.append((t[i:m.start()], {}))
        s = m.group(0)
        if s.startswith('`'):
            out.append((s[1:-1], {'code': True}))
        elif s.startswith('**'):
            out.append((s[2:-2], {'bold': True}))
        elif s.startswith('*'):
            out.append((s[1:-1], {'italic': True}))
        else:
            lm = RE_LINK.match(s)
            out.append((lm.group(1), {'link': lm.group(2)}))
        i = m.end()
    if i < len(t):
        out.append((t[i:], {}))
    return [r for r in out if r[0]]


def slug(s):
    s = re.sub(r'[^\w\u4e00-\u9fff]+', '-', s).strip('-')
    return s or 'sec'


def b64(path):
    import base64
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('ascii')


def data_uri(path, mime=None):
    if mime is None:
        ext = os.path.splitext(path)[1].lower()
        mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.svg': 'image/svg+xml', '.gif': 'image/gif'}.get(ext, 'application/octet-stream')
    return 'data:%s;base64,%s' % (mime, b64(path))


def ensure_jpeg(png_path, jpg_path):
    """原型图 JPEG 缓存缺失时自动用 sips 生成（1500px / q82）。

    历史上新增模块常忘补 work/build/img/*.jpg，导致 HTML/Word 里图片位置空白。
    这里做一次自愈，返回是否可用。
    """
    if os.path.exists(jpg_path):
        return True
    if not os.path.exists(png_path):
        return False
    import subprocess
    try:
        subprocess.run(['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', '82',
                        '-Z', '1500', png_path, '--out', jpg_path],
                       check=False, capture_output=True)
    except Exception:
        return False
    return os.path.exists(jpg_path)
