# -*- coding: utf-8 -*-
"""极简 Markdown -> 块级 AST。只覆盖本项目需求设计文档实际用到的构件：
标题 / 段落 / 表格 / 列表(含一级嵌套) / 引用 / 分隔线 / 图片 / 围栏代码(mermaid|yaml)。
HTML 与 DOCX 两条产出线共用本解析器，保证内容一致。
"""
import re

RE_HEAD = re.compile(r'^(#{1,6})\s+(.*)$')
RE_FENCE = re.compile(r'^```([A-Za-z0-9_+-]*)\s*$')
RE_HR = re.compile(r'^\s*(?:-{3,}|\*{3,}|_{3,})\s*$')
RE_TABLE_SEP = re.compile(r'^\s*\|[\s:|-]+\|\s*$')
RE_LIST = re.compile(r'^(\s*)([-*+]|\d+[.)])\s+(.*)$')
RE_IMG = re.compile(r'^!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)\s*$')
# 表格分行：只认未被反斜杠转义的竖线（单元格内的 `\|` 是字面竖线，
# 常见于 `grep A\|B` 这类正则写法，按裸 | 切会把后面所有列挤错位）
RE_ROW_SPLIT = re.compile(r'(?<!\\)\|')


def split_row(line):
    s = line.strip()
    if s.startswith('|'):
        s = s[1:]
    if s.endswith('|') and not s.endswith('\\|'):
        s = s[:-1]
    return [c.strip().replace('\\|', '|') for c in RE_ROW_SPLIT.split(s)]


def parse(text):
    """返回 block 列表。每个 block 是 dict，含 type 与内容。"""
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    blocks = []
    i, n = 0, len(lines)

    while i < n:
        raw = lines[i]
        s = raw.rstrip()

        # --- 围栏代码 ---
        fm = RE_FENCE.match(s)
        if fm:
            lang = fm.group(1) or 'text'
            i += 1
            buf = []
            while i < n and not RE_FENCE.match(lines[i].rstrip()):
                buf.append(lines[i])
                i += 1
            i += 1  # 跳过结束围栏
            blocks.append({'type': 'fence', 'lang': lang, 'code': '\n'.join(buf)})
            continue

        # --- 标题 ---
        hm = RE_HEAD.match(s)
        if hm:
            blocks.append({'type': 'head', 'level': len(hm.group(1)), 'text': hm.group(2).strip()})
            i += 1
            continue

        # --- 分隔线（必须在列表之前判断，避免 --- 被当列表） ---
        if RE_HR.match(s) and not s.strip().startswith('|'):
            blocks.append({'type': 'hr'})
            i += 1
            continue

        # --- 表格 ---
        if s.strip().startswith('|') and i + 1 < n and RE_TABLE_SEP.match(lines[i + 1]):
            header = split_row(s)
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith('|'):
                cells = split_row(lines[i])
                # 补齐/截断到表头列数
                if len(cells) < len(header):
                    cells += [''] * (len(header) - len(cells))
                rows.append(cells[:len(header)])
                i += 1
            blocks.append({'type': 'table', 'header': header, 'rows': rows})
            continue

        # --- 引用块 ---
        if s.lstrip().startswith('>'):
            buf = []
            while i < n and lines[i].lstrip().startswith('>'):
                buf.append(lines[i].lstrip()[1:].strip())
                i += 1
            blocks.append({'type': 'quote', 'lines': buf})
            continue

        # --- 列表 ---
        lm = RE_LIST.match(raw)
        if lm:
            items = []
            while i < n:
                m = RE_LIST.match(lines[i])
                if not m:
                    # 列表项内的续行（缩进且非空）
                    if items and lines[i].strip() and lines[i].startswith('  ') and not RE_HEAD.match(lines[i].rstrip()):
                        items[-1]['text'] += ' ' + lines[i].strip()
                        i += 1
                        continue
                    break
                indent = len(m.group(1))
                ordered = m.group(2).endswith('.') or m.group(2).endswith(')')
                items.append({'indent': indent, 'ordered': ordered, 'text': m.group(3).strip()})
                i += 1
            ordered = items[0]['ordered'] if items else False
            blocks.append({'type': 'list', 'ordered': ordered, 'items': items})
            continue

        # --- 空行 ---
        if not s.strip():
            i += 1
            continue

        # --- 段落（含独占一行的图片） ---
        buf = []
        while i < n:
            t = lines[i]
            if not t.strip():
                break
            if RE_HEAD.match(t.rstrip()) or RE_FENCE.match(t.rstrip()):
                break
            if t.lstrip().startswith('>'):
                break
            if t.strip().startswith('|'):
                break
            if RE_LIST.match(t):
                break
            if RE_HR.match(t) and not t.strip().startswith('|'):
                break
            buf.append(t)
            i += 1
        if buf:
            im = RE_IMG.match(buf[0]) if len(buf) == 1 else None
            if im:
                blocks.append({'type': 'image', 'alt': im.group(1), 'src': im.group(2)})
            else:
                # Markdown 硬换行（行尾两个以上空格）→ '\n'；软换行 → 空格
                parts = []
                for k, ln in enumerate(buf):
                    hard = ln.endswith('  ')
                    parts.append(ln.strip())
                    if k < len(buf) - 1:
                        parts.append('\n' if hard else ' ')
                blocks.append({'type': 'para', 'text': ''.join(parts)})
        else:
            # 兜底：首行即命中 break 条件（如孤立的 '|' 行、无表头的表格行），
            # 若不放行会原地打转导致构建假死。按普通段落吞掉该行，保证 i 前进。
            blocks.append({'type': 'para', 'text': s.strip()})
            i += 1

    return blocks


def outline(blocks):
    """返回 (level, text) 列表，供生成目录。"""
    return [(b['level'], b['text']) for b in blocks if b['type'] == 'head']


if __name__ == '__main__':
    import sys, json
    for p in sys.argv[1:]:
        bs = parse(open(p, encoding='utf-8').read())
        from collections import Counter
        c = Counter(b['type'] for b in bs)
        print(p, dict(c))
