"""
Boolean query parser, validator, and analyser.

Main entry point: validate_query(input_str) -> dict
  status:     'empty' | 'error' | 'warn' | 'valid'
  issues:     list of {message: str}
  ast:        ASTNode | None
  stats:      dict | None
  highlights: list of Highlight
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


# ─────────────────────────────────────────────
#  Data types
# ─────────────────────────────────────────────

@dataclass
class Token:
    type: str   # LP | RP | AND | OR | NOT | NEAR | TERM | NOTE
    start: int
    end: int
    value: Optional[str] = None
    quoted: bool = False


@dataclass
class ASTNode:
    type: str
    value:    Optional[str]       = None
    quoted:   bool                = False
    op:       Optional[str]       = None   # for NEAR nodes
    children: List["ASTNode"]     = field(default_factory=list)
    child:    Optional["ASTNode"] = None   # for GROUP / NOT


@dataclass
class Highlight:
    start: int
    end:   int
    type:  str   # 'error' | 'warn'
    title: str


# ─────────────────────────────────────────────
#  Tokeniser
# ─────────────────────────────────────────────

def tokenize(s: str) -> List[Token]:
    tokens: List[Token] = []
    i = 0
    while i < len(s):
        if s[i].isspace():
            i += 1
            continue
        start = i

        if s[i] == '(':
            tokens.append(Token('LP', start, i + 1))
            i += 1
            continue
        if s[i] == ')':
            tokens.append(Token('RP', start, i + 1))
            i += 1
            continue

        # <<<note>>> annotation
        if s[i:i+3] == '<<<':
            j = i + 3
            while j < len(s) and s[j:j+3] != '>>>':
                j += 1
            if j >= len(s):
                raise ValueError('Unclosed <<< note — add >>> to close it')
            tokens.append(Token('NOTE', start, j + 3, value=s[i+3:j].strip()))
            i = j + 3
            continue

        # Quoted phrase (with optional ~n proximity)
        if s[i] == '"':
            j = i + 1
            while j < len(s) and s[j] != '"':
                j += 1
            if j >= len(s):
                raise ValueError(f'Unclosed quote at character {i + 1}')
            end = j + 1
            if end < len(s) and s[end] == '~' and end + 1 < len(s) and s[end+1].isdigit():
                k = end + 1
                while k < len(s) and s[k].isdigit():
                    k += 1
                end = k
            tokens.append(Token('TERM', start, end, value=s[i:end], quoted=True))
            i = end
            continue

        # Unquoted word — read through [...] range and {...} exact brackets
        j = i
        while j < len(s):
            if s[j] == '[':
                while j < len(s) and s[j] != ']':
                    j += 1
                if j < len(s):
                    j += 1
            elif s[j] == '{':
                while j < len(s) and s[j] != '}':
                    j += 1
                if j < len(s):
                    j += 1
            elif s[j] in ' \t\n\r\f\v()"<':
                break
            else:
                j += 1

        if j == i:
            i += 1
            continue

        end = j
        base = s[i:j]

        # field:"value" (e.g. url:"bbc.com/news")
        if base.endswith(':') and end < len(s) and s[end] == '"':
            k = end + 1
            while k < len(s) and s[k] != '"':
                k += 1
            if k < len(s):
                end = k + 1

        word = s[i:end]
        bu   = base.upper()

        if   bu == 'AND': tokens.append(Token('AND',  start, end))
        elif bu == 'OR':  tokens.append(Token('OR',   start, end))
        elif bu == 'NOT': tokens.append(Token('NOT',  start, end))
        elif re.match(r'^(NEAR|W|PRE|ONEAR)/\d+[fb]?$', base, re.I):
            tokens.append(Token('NEAR', start, end, value=bu))
        else:
            tokens.append(Token('TERM', start, end, value=word))

        i = end
    return tokens


# ─────────────────────────────────────────────
#  Parser  →  AST
# ─────────────────────────────────────────────

def parse(tokens: List[Token]) -> ASTNode:
    pos = [0]

    def peek() -> Optional[Token]:
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def eat(t: str = None) -> Token:
        if pos[0] >= len(tokens):
            raise ValueError(f'Expected {t} but input ended')
        tok = tokens[pos[0]]
        if t and tok.type != t:
            raise ValueError(f'Expected {t}, got {tok.type}')
        pos[0] += 1
        return tok

    def done()   -> bool: return pos[0] >= len(tokens)
    def at_end() -> bool: return done() or peek().type == 'RP'

    def expr():     return parse_or()
    def parse_or():
        ch = [parse_and()]
        while not at_end() and peek().type == 'OR':
            eat('OR'); ch.append(parse_and())
        return ch[0] if len(ch) == 1 else ASTNode('OR', children=ch)

    def parse_and():
        ch = [parse_near()]
        while not at_end() and peek().type != 'OR':
            if peek().type == 'AND':
                eat('AND')
            elif peek().type not in ('NOT', 'LP', 'TERM', 'NOTE'):
                break
            ch.append(parse_near())
        return ch[0] if len(ch) == 1 else ASTNode('AND', children=ch)

    def parse_near():
        left = parse_not()
        while not at_end() and peek().type == 'NEAR':
            op = eat('NEAR').value
            left = ASTNode('NEAR', op=op, children=[left, parse_not()])
        return left

    def parse_not():
        if not done() and peek().type == 'NOT':
            eat('NOT')
            return ASTNode('NOT', child=parse_not())
        return primary()

    def primary():
        if done():
            raise ValueError('Unexpected end of query — are all parentheses closed?')
        if peek().type == 'LP':
            eat('LP')
            node = expr()
            if done() or peek().type != 'RP':
                raise ValueError('Missing closing parenthesis )')
            eat('RP')
            return ASTNode('GROUP', child=node)
        if peek().type == 'TERM':
            t = eat('TERM')
            return ASTNode('TERM', value=t.value, quoted=t.quoted)
        if peek().type == 'NOTE':
            t = eat('NOTE')
            return ASTNode('NOTE', value=t.value)
        raise ValueError(f'Unexpected token: {peek().type}')

    items = []
    while not done():
        if peek().type == 'NOTE':
            t = eat('NOTE')
            items.append(ASTNode('NOTE', value=t.value))
        else:
            items.append(expr())

    if not items:
        raise ValueError('Empty query')
    return items[0] if len(items) == 1 else ASTNode('PROGRAM', children=items)


# ─────────────────────────────────────────────
#  Structural analysis  (parens / quotes / notes)
# ─────────────────────────────────────────────

def analyze_structure(s: str):
    issues, highlights = [], []
    in_quote = False; quote_start = -1
    in_note  = False; note_start  = -1
    open_parens = []   # [{pos, idx}]

    i = 0
    while i < len(s):
        if in_note:
            if s[i:i+3] == '>>>': in_note = False; i += 3; continue
            i += 1; continue
        if in_quote:
            if s[i] == '"': in_quote = False
            i += 1; continue
        if s[i:i+3] == '<<<':
            in_note = True; note_start = i; i += 3; continue
        if s[i] == '"':
            in_quote = True; quote_start = i; i += 1; continue
        if s[i] == '(':
            open_parens.append({'pos': i + 1, 'idx': i})
        elif s[i] == ')':
            if open_parens:
                open_parens.pop()
            else:
                msg = f'Extra ) at position {i + 1} — no opening ( to match it'
                highlights.append(Highlight(i, i+1, 'error', msg))
                issues.append({'message': msg})
        i += 1

    if in_note:
        msg = 'Unclosed <<<note>>> — add >>> to close it'
        highlights.append(Highlight(note_start, note_start+3, 'error', msg))
        issues.append({'message': msg})
    if in_quote:
        msg = f'Unclosed quote at position {quote_start + 1} — add a closing "'
        highlights.append(Highlight(quote_start, quote_start+1, 'error', msg))
        issues.append({'message': msg})
    if open_parens:
        n = len(open_parens)
        pos_str = ', '.join(f'pos {p["pos"]}' for p in open_parens)
        closes  = 'a closing )' if n == 1 else f'{n} closing )'
        msg = f'{n} unclosed opening parenthes{"is" if n == 1 else "es"} ({pos_str}) — add {closes}'
        for p in open_parens:
            highlights.append(Highlight(p['idx'], p['idx']+1, 'error', 'Unclosed opening parenthesis'))
        issues.append({'message': msg})

    return issues, highlights


# ─────────────────────────────────────────────
#  Token-level analysis
# ─────────────────────────────────────────────

def analyze_tokens(s: str):
    issues, highlights = [], []
    try:
        tokens = tokenize(s)
    except Exception:
        return issues, highlights
    if not tokens:
        return issues, highlights

    first, last = tokens[0], tokens[-1]

    def _hl(t): highlights.append(Highlight(t.start, t.end, 'error', msg))
    def _lbl(t): return t.value if t.type == 'NEAR' else t.type

    if first.type in ('AND', 'OR'):
        msg = f'Query starts with {first.type} — add a term or group before it'
        _hl(first); issues.append({'message': msg})

    if last.type in ('AND', 'OR'):
        msg = f'Query ends with {last.type} — add a term or group after it, or remove the operator'
        _hl(last); issues.append({'message': msg})
    elif last.type == 'NOT':
        msg = 'Query ends with NOT — add a term or group after it'
        _hl(last); issues.append({'message': msg})
    elif last.type == 'NEAR':
        msg = f'Query ends with {last.value} — add a term or group after it'
        _hl(last); issues.append({'message': msg})

    for i in range(len(tokens) - 1):
        a, b = tokens[i], tokens[i+1]
        a_op = a.type in ('AND', 'OR', 'NEAR')
        b_op = b.type in ('AND', 'OR', 'NEAR')

        if a_op and b_op:
            msg = f'{_lbl(a)} followed immediately by {_lbl(b)} — remove one operator'
            _hl(a); _hl(b); issues.append({'message': msg})

        if a_op and b.type == 'RP':
            msg = f'{_lbl(a)} before ) with no term after it — remove the operator or add a term'
            _hl(a); issues.append({'message': msg})

        if a.type == 'LP' and b_op:
            msg = f'( immediately followed by {_lbl(b)} — add a term before the operator'
            _hl(b); issues.append({'message': msg})

        if a.type == 'LP' and b.type == 'RP':
            msg = 'Empty parentheses () — add at least one term inside'
            _hl(a); _hl(b); issues.append({'message': msg})

        if a.type == 'NOT' and b.type in ('AND', 'OR', 'RP'):
            msg = f'NOT followed by {")" if b.type == "RP" else b.type} — add a term or group after NOT'
            _hl(a); issues.append({'message': msg})

        # Implicit AND (no operator between adjacent terms/groups)
        prev_val = a.type in ('TERM', 'RP')
        next_val = b.type in ('TERM', 'LP')
        handled  = (a.type == 'LP' and b.type == 'RP') or (a_op and b.type == 'RP') or (a.type == 'LP' and b_op)

        if prev_val and next_val and not handled:
            if a.type == 'TERM' and b.type == 'TERM' and not a.quoted and not b.quoted:
                msg = f'"{a.value} {b.value}" looks like a phrase but has no quotes — did you mean AND, OR, NEAR/n, or "{a.value} {b.value}"?'
            elif a.type == 'TERM' and b.type == 'TERM':
                msg = f'No operator between {a.value} and {b.value} — add AND, OR, or NEAR/n'
            elif a.type == 'TERM':
                msg = f'No operator after "{a.value}" before the next group — add AND, OR, or NEAR/n'
            elif b.type == 'TERM':
                msg = f'No operator before "{b.value}" after the group — add AND, OR, or NEAR/n'
            else:
                msg = 'No operator between these two groups — add AND, OR, or NEAR/n'
            _hl(a); _hl(b); issues.append({'message': msg})

    return issues, highlights


# ─────────────────────────────────────────────
#  Bare-term detection
# ─────────────────────────────────────────────

def find_bare_terms(node: ASTNode, inside_group: bool = False) -> List[str]:
    if node.type == 'PROGRAM':
        return [t for c in node.children for t in find_bare_terms(c, inside_group)]
    if node.type == 'TERM':
        return [] if inside_group else [node.value]
    if node.type in ('NOTE',):
        return []
    if node.type == 'GROUP':
        return find_bare_terms(node.child, True)
    if node.type == 'NOT':
        return find_bare_terms(node.child, inside_group)
    if node.type in ('AND', 'OR', 'NEAR'):
        return [t for c in node.children for t in find_bare_terms(c, inside_group)]
    return []


def find_bare_term_highlights(s: str) -> List[Highlight]:
    highlights = []
    try:
        tokens = tokenize(s)
    except Exception:
        return highlights
    depth = 0
    for tok in tokens:
        if tok.type == 'LP':   depth += 1
        elif tok.type == 'RP': depth -= 1
        elif tok.type == 'TERM' and depth == 0:
            highlights.append(Highlight(tok.start, tok.end, 'warn', f'"{tok.value}" is outside parentheses'))
    return highlights


# ─────────────────────────────────────────────
#  Statistics
# ─────────────────────────────────────────────

def collect_stats(ast: ASTNode) -> Dict[str, Any]:
    s: Dict[str, Any] = {'terms': 0, 'quoted_terms': 0, 'groups': 0, 'max_depth': 0, 'ops': {}}

    def walk(n: ASTNode, d: int):
        s['max_depth'] = max(s['max_depth'], d)
        if   n.type == 'PROGRAM': [walk(c, d)     for c in n.children]
        elif n.type == 'TERM':
            s['terms'] += 1
            if n.quoted: s['quoted_terms'] += 1
        elif n.type == 'GROUP':
            s['groups'] += 1; walk(n.child, d + 1)
        elif n.type in ('AND', 'OR'):
            s['ops'][n.type] = s['ops'].get(n.type, 0) + 1
            [walk(c, d) for c in n.children]
        elif n.type == 'NEAR':
            s['ops'][n.op] = s['ops'].get(n.op, 0) + 1
            [walk(c, d) for c in n.children]
        elif n.type == 'NOT':
            s['ops']['NOT'] = s['ops'].get('NOT', 0) + 1; walk(n.child, d)

    walk(ast, 0)
    return s


def stats_line(s: Dict[str, Any]) -> str:
    parts = []
    if s['terms']        > 0: parts.append(f'{s["terms"]} term{"s" if s["terms"] != 1 else ""}')
    if s['quoted_terms'] > 0: parts.append(f'{s["quoted_terms"]} quoted')
    if s['groups']       > 0: parts.append(f'{s["groups"]} group{"s" if s["groups"] != 1 else ""}')
    if s['max_depth']    > 0: parts.append(f'depth {s["max_depth"]}')
    for op, n in s['ops'].items():
        if n > 0: parts.append(f'{op}×{n}')
    return ' · '.join(parts)


# ─────────────────────────────────────────────
#  Main entry point
# ─────────────────────────────────────────────

def validate_query(s: str) -> Dict[str, Any]:
    """
    Validate and parse a boolean query string.

    Returns a dict:
      status     — 'empty' | 'error' | 'warn' | 'valid'
      issues     — list of {'message': str}
      ast        — ASTNode | None
      stats      — dict | None  (terms, quoted_terms, groups, max_depth, ops)
      highlights — list of Highlight  (for annotating the raw query text)
    """
    if not s.strip():
        return {'status': 'empty', 'issues': [], 'ast': None, 'stats': None, 'highlights': []}

    struct_issues, struct_hl = analyze_structure(s)
    token_issues,  token_hl  = analyze_tokens(s)

    if struct_issues or token_issues:
        seen, errors = set(), []
        for e in struct_issues + token_issues:
            if e['message'] not in seen:
                seen.add(e['message']); errors.append(e)
        return {'status': 'error', 'issues': errors, 'ast': None, 'stats': None,
                'highlights': struct_hl + token_hl}

    try:
        ast = parse(tokenize(s))
    except Exception as exc:
        return {'status': 'error', 'issues': [{'message': str(exc)}],
                'ast': None, 'stats': None, 'highlights': []}

    bare  = find_bare_terms(ast)
    stats = collect_stats(ast)

    if bare:
        shown = ', '.join(f'"{t}"' for t in bare[:5])
        extra = f' and {len(bare) - 5} more' if len(bare) > 5 else ''
        msg   = (f'{len(bare)} term{"s" if len(bare) > 1 else ""} outside parentheses: '
                 f'{shown}{extra} — these may not be grouped as intended')
        return {'status': 'warn', 'issues': [{'message': msg}], 'ast': ast,
                'stats': stats, 'highlights': find_bare_term_highlights(s)}

    return {'status': 'valid', 'issues': [], 'ast': ast, 'stats': stats, 'highlights': []}
