"""
Boolean Query Visualiser — Streamlit app.
Run with:  streamlit run app.py
"""

import streamlit as st
import streamlit.components.v1 as components
from boolean_query import validate_query, ASTNode, Highlight, stats_line
from typing import List

# ─────────────────────────────────────────────
#  Colour palette (matches original)
# ─────────────────────────────────────────────

PALETTE = [
    {'bg': 'rgba(219,234,254,0.55)', 'border': '#93c5fd'},
    {'bg': 'rgba(220,252,231,0.55)', 'border': '#86efac'},
    {'bg': 'rgba(254,243,199,0.55)', 'border': '#fcd34d'},
    {'bg': 'rgba(243,232,255,0.55)', 'border': '#d8b4fe'},
    {'bg': 'rgba(255,228,230,0.55)', 'border': '#fca5a5'},
    {'bg': 'rgba(204,251,241,0.55)', 'border': '#5eead4'},
]

def _col(d): return PALETTE[d % len(PALETTE)]

def _esc(s: str) -> str:
    return (s.replace('&', '&amp;').replace('<', '&lt;')
             .replace('>', '&gt;').replace('"', '&quot;'))

# ─────────────────────────────────────────────
#  Example queries
# ─────────────────────────────────────────────

EXAMPLES = [
    ('Basic', '(((brown OR black OR panda OR polar OR spectacle* OR grizzl* OR andean OR sloth) NEAR/3 (bear))\nAND\n(cub* OR bab* OR hibernat*))\nNOT (RT OR kill* OR die* OR attack*)'),
    ('Intermediate', '((((best OR favourit* OR superior) OR ((i OR me OR my OR we OR they OR he OR she) NEAR/4 (prefer* OR like* OR love* OR "only drink" OR "only drinks"))) NEAR/5 (tea NEAR/4(breakfast*)))\nAND\n(barry* OR lyon* OR mcgrath* OR twining* OR pukka* OR bewley*))\nNOT ((green NEAR/1 tea*) OR herbal)'),
    ('Advanced', '((<<<english>>>\n((donegal OR tirconnell OR tirconaill OR tyrconnell)\nAND\n(<<<birds>>>(corncrake* OR "corn crake" OR razorbill*) OR\n<<<wildflowers>>>\n("dog violet" OR chickweed* OR primrose* OR bluebell*))))\nOR\n<<<irish>>>\n(("dun na ngall" OR "dún na ngall")\nAND\n(<<<éin>>>(traonach OR crosán OR cruidín) OR\n<<<bláthanna>>>\n(Anamóine OR sailchuach OR sabhaircín OR "cloigín gorm"))))\nNOT RT'),
]

# ─────────────────────────────────────────────
#  CSS (verbatim from original, minus body/h1)
# ─────────────────────────────────────────────

CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
       background: #f8fafc; color: #1e293b; padding: 1rem; }
.op-list { display: flex; flex-direction: column; gap: 4px; }
.op-sep { font-size: 0.68rem; font-weight: 800; text-transform: uppercase;
          letter-spacing: 0.1em; color: #94a3b8; padding: 1px 2px; user-select: none; }
.near-sep { color: #0891b2; }
.not-sep  { color: #b91c1c; }
.group-box { border-radius: 7px; padding: 8px 14px; }
.group-content { display: flex; flex-direction: column; gap: 4px; }
.text-run { font-family: 'Courier New','Consolas',monospace; font-size: 0.9rem;
            color: #1e293b; line-height: 1.6; }
.inline-group { border-radius: 4px; padding: 1px 5px; }
.para-op { font-size: 0.72rem; font-weight: 800; text-transform: uppercase;
           letter-spacing: 0.06em; color: #6b7280; }
.near-op { color: #0891b2; }
.plain-text { font-family: 'Courier New','Consolas',monospace; font-size: 0.9rem; color: #374151; }
.not-badge { display: inline-block; font-size: 0.65rem; font-weight: 800;
             text-transform: uppercase; letter-spacing: 0.06em;
             background: #fee2e2; color: #b91c1c; border: 1.5px solid #fca5a5;
             border-radius: 4px; padding: 1px 5px; vertical-align: middle; line-height: 1; }
.block-not { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.note-box { display: flex; align-items: baseline; gap: 8px; border-radius: 6px;
            padding: 4px 10px; background: #f8fafc; border: 1.5px dashed #94a3b8; }
.note-label { font-size: 0.62rem; font-weight: 800; text-transform: uppercase;
              letter-spacing: 0.06em; color: #94a3b8; flex-shrink: 0; }
.note-text { font-family: 'Courier New','Consolas',monospace; font-size: 0.85rem;
             color: #64748b; font-style: italic; }
.tree-wrap { background: white; border: 1.5px solid #e2e8f0; border-radius: 10px;
             padding: 1.25rem 1.5rem; overflow-x: auto; }
.legend { display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 1rem;
          padding-top: 0.85rem; border-top: 1px solid #e2e8f0; }
.legend-item { display: flex; align-items: center; gap: 0.4rem;
               font-size: 0.78rem; color: #64748b; }
.legend-swatch { width: 14px; height: 14px; border-radius: 3px; flex-shrink: 0; }
.query-display { font-family: 'Courier New','Consolas',monospace; font-size: 0.88rem;
                 line-height: 1.85; white-space: pre-wrap; word-break: break-word;
                 padding: 0.85rem 1rem; background: white; border: 1.5px solid #e2e8f0;
                 border-radius: 8px; color: #1e293b; margin-bottom: 0.75rem; }
.query-display.has-errors  { border-color: #fca5a5; background: #fff8f8; }
.query-display.has-warnings{ border-color: #fcd34d; background: #fffef5; }
.hl-error { background: #fee2e2; color: #991b1b; border-radius: 3px;
            border-bottom: 2.5px solid #ef4444; padding: 0 2px; cursor: help; }
.hl-warn  { background: #fef9c3; color: #713f12; border-radius: 3px;
            border-bottom: 2.5px solid #eab308; padding: 0 2px; cursor: help; }
"""

# ─────────────────────────────────────────────
#  HTML tree renderer
# ─────────────────────────────────────────────

def _is_block(node: ASTNode) -> bool:
    if node.type in ('GROUP', 'NOTE'): return True
    if node.type == 'NOT':            return _is_block(node.child)
    if node.type in ('AND', 'OR', 'NEAR'):
        return any(_is_block(c) for c in node.children)
    return False


def _render_block(node: ASTNode, depth: int) -> str:
    if node.type == 'PROGRAM':
        inner = ''.join(_render_block(c, depth) for c in node.children)
        return f'<div style="display:flex;flex-direction:column;gap:8px;">{inner}</div>'

    if node.type == 'GROUP':
        c = _col(depth)
        inner = _render_group_content(node.child, depth + 1)
        return (f'<div class="group-box" '
                f'style="background:{c["bg"]};border:1.5px solid {c["border"]};">'
                f'{inner}</div>')

    if node.type in ('AND', 'OR', 'NEAR'):
        label = node.op if node.type == 'NEAR' else node.type
        parts, logic_idx = [], 0
        for child in node.children:
            if child.type == 'NOTE':
                parts.append(_render_block(child, depth)); continue
            is_not = child.type == 'NOT'
            if logic_idx > 0:
                sc  = 'op-sep not-sep' if is_not else ('op-sep near-sep' if node.type == 'NEAR' else 'op-sep')
                txt = 'NOT' if is_not else label
                parts.append(f'<div class="{sc}">{txt}</div>')
            parts.append(_render_block(child.child if is_not else child, depth))
            logic_idx += 1
        return f'<div class="op-list">{"".join(parts)}</div>'

    if node.type == 'NOT':
        return f'<div class="block-not"><span class="not-badge">NOT</span>{_render_block(node.child, depth)}</div>'

    if node.type == 'NOTE':
        return (f'<div class="note-box">'
                f'<span class="note-label">NOTE</span>'
                f'<span class="note-text">{_esc(node.value)}</span></div>')

    return f'<span class="plain-text">{_esc(node.value)}</span>'


def _render_group_content(node: ASTNode, depth: int) -> str:
    if node.type in ('GROUP', 'NOTE'):
        return f'<div class="group-content">{_render_block(node, depth)}</div>'

    if node.type not in ('AND', 'OR', 'NEAR'):
        return f'<div class="group-content"><div class="text-run">{_inline(node, depth)}</div></div>'

    op = node.op if node.type == 'NEAR' else node.type
    if not any(_is_block(c) for c in node.children):
        return f'<div class="group-content"><div class="text-run">{_inline(node, depth)}</div></div>'

    # Mixed block / inline segments
    segs, buf = [], []
    for ch in node.children:
        if _is_block(ch):
            if buf: segs.append(('text', list(buf))); buf = []
            segs.append(('block', ch))
        else:
            buf.append(ch)
    if buf: segs.append(('text', buf))

    parts, seg_idx = [], 0
    for kind, val in segs:
        if kind == 'block' and val.type == 'NOTE':
            parts.append(f'<div style="padding-left:10px">{_render_block(val, depth)}</div>'); continue
        if seg_idx > 0:
            is_not = kind == 'block' and val.type == 'NOT'
            sc  = 'op-sep not-sep' if is_not else ('op-sep near-sep' if node.type == 'NEAR' else 'op-sep')
            txt = 'NOT' if is_not else op
            parts.append(f'<div class="{sc}">{txt}</div>')
        seg_idx += 1
        if kind == 'block':
            n2 = val.child if val.type == 'NOT' else val
            parts.append(f'<div style="padding-left:10px">{_render_block(n2, depth)}</div>')
        else:
            row = []
            for j, item in enumerate(val):
                if j > 0:
                    oc = 'para-op near-op' if node.type == 'NEAR' else 'para-op'
                    row.append(f'<span class="{oc}"> {op} </span>')
                row.append(_inline(item, depth))
            parts.append(f'<div class="text-run">{"".join(row)}</div>')

    return f'<div class="group-content">{"".join(parts)}</div>'


def _inline(node: ASTNode, depth: int) -> str:
    if node.type == 'TERM':  return _esc(node.value)
    if node.type == 'NOTE':  return f'<span class="note-text">«{_esc(node.value)}»</span>'
    if node.type == 'NOT':
        return f'<span class="not-badge">NOT</span> {_inline(node.child, depth)}'
    if node.type == 'GROUP':
        c = _col(depth)
        return (f'<span class="inline-group" '
                f'style="background:{c["bg"]};border:1.5px solid {c["border"]};">'
                f'{_inline(node.child, depth + 1)}</span>')
    if node.type in ('AND', 'OR', 'NEAR'):
        label = node.op if node.type == 'NEAR' else node.type
        parts = []
        for i, ch in enumerate(node.children):
            if i > 0:
                oc = 'para-op near-op' if node.type == 'NEAR' else 'para-op'
                parts.append(f'<span class="{oc}"> {label} </span>')
            parts.append(_inline(ch, depth))
        return ''.join(parts)
    return ''


def _collect_depths(node: ASTNode, depth: int, out: set):
    if node.type == 'PROGRAM':
        for c in node.children: _collect_depths(c, depth, out)
    elif node.type == 'GROUP':
        out.add(depth); _collect_depths(node.child, depth + 1, out)
    elif node.type in ('AND', 'OR', 'NEAR'):
        for c in node.children: _collect_depths(c, depth, out)
    elif node.type == 'NOT':
        _collect_depths(node.child, depth, out)


def render_tree_html(ast: ASTNode) -> str:
    depths: set = set()
    _collect_depths(ast, 0, depths)
    tree = _render_block(ast, 0)
    legend = ''
    for d in sorted(depths):
        c = _col(d)
        legend += (f'<div class="legend-item">'
                   f'<div class="legend-swatch" style="background:{c["bg"]};border:1.5px solid {c["border"]};"></div>'
                   f'Group level {d + 1}</div>')
    if legend:
        legend = f'<div class="legend">{legend}</div>'
    return f'<div class="tree-wrap">{tree}{legend}</div>'


def render_annotated_html(s: str, highlights: List[Highlight], extra_class: str = '') -> str:
    cls = f'query-display{" " + extra_class if extra_class else ""}'
    if not highlights:
        return f'<div class="{cls}">{_esc(s)}</div>'

    sorted_hl = sorted([h for h in highlights if h.end > h.start],
                       key=lambda h: (h.start, -(h.end - h.start)))
    parts, pos = [], 0
    for h in sorted_hl:
        hs = max(h.start, pos)
        if hs >= h.end: continue
        if hs > pos: parts.append(_esc(s[pos:hs]))
        title = f' title="{_esc(h.title)}"' if h.title else ''
        parts.append(f'<span class="hl-{h.type}"{title}>{_esc(s[hs:h.end])}</span>')
        pos = h.end
    if pos < len(s): parts.append(_esc(s[pos:]))
    return f'<div class="{cls}">{"".join(parts)}</div>'


def _full_page(body_html: str, height: int) -> None:
    html = f'<html><head><style>{CSS}</style></head><body>{body_html}</body></html>'
    components.html(html, height=height, scrolling=True)


# ─────────────────────────────────────────────
#  Streamlit UI
# ─────────────────────────────────────────────

st.set_page_config(page_title='Boolean Query Visualiser', layout='centered')
st.title('Boolean Query Visualiser')
st.caption('Build a Boolean query — structure is clustered live as you type.')

# Example buttons
cols = st.columns([1, 1, 1, 4])
for i, (label, _) in enumerate(EXAMPLES):
    if cols[i].button(label, key=f'eg{i}'):
        st.session_state['query'] = EXAMPLES[i][1]

query = st.text_area(
    'Query',
    value=st.session_state.get('query', ''),
    height=120,
    placeholder='e.g. ("climate change" OR "global warming") AND (policy OR legislation) AND NOT satire',
    key='query',
)

if st.button('Clear'):
    st.session_state['query'] = ''
    st.rerun()

# ── Validation & display ──────────────────────
result = validate_query(query)

if result['status'] == 'empty':
    pass

elif result['status'] == 'error':
    st.error('\n'.join(f'▸ {e["message"]}' for e in result['issues']))
    _full_page(render_annotated_html(query, result['highlights'], 'has-errors'), 200)

elif result['status'] == 'warn':
    st.warning('\n'.join(f'▸ {e["message"]}' for e in result['issues']))
    if result['stats']:
        sl = stats_line(result['stats'])
        if sl: st.caption(sl)
    _full_page(render_annotated_html(query, result['highlights'], 'has-warnings'), 200)
    _full_page(render_tree_html(result['ast']), 600)

elif result['status'] == 'valid':
    if result['stats']:
        sl = stats_line(result['stats'])
        if sl: st.success(f'Valid — {sl}')
        else:  st.success('Valid')
    _full_page(render_tree_html(result['ast']), 600)
