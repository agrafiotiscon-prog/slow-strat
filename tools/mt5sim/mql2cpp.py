#!/usr/bin/env python3
"""Mechanical MQL5 -> C++ translation for compile-checking and simulating an EA.

Handles the MQL5 constructs used by SlowStrat.mq5: input/sinput/input group,
#property, dynamic arrays (declarations, initializers, reference params),
forward declarations (MQL5 allows calling functions defined later), and
default-argument placement.  The result is compiled against mql5rt.h.
"""
import re
import sys

TYPES = r"(?:bool|char|uchar|short|ushort|int|uint|long|ulong|float|double|string|datetime|color|void|" \
        r"Mql\w+|ENUM_\w+|CTrade)"


def input_setter(src: str) -> str:
    """Generate rt_set_input(name, value) so the simulator can override EA inputs."""
    lines = ["bool rt_set_input(const std::string& n, const std::string& v) {"]
    for m in re.finditer(r"^\s*s?input\s+(\w+)\s+(\w+)\s*=", src, re.M):
        typ, name = m.groups()
        if typ == "group":
            continue
        if typ == "string":
            conv = "string(v)"
        elif typ == "bool":
            conv = '(v == "true" || v == "1")'
        elif typ in ("double", "float"):
            conv = "atof(v.c_str())"
        else:
            conv = f"({typ})atoll(v.c_str())"
        lines.append(f'  if (n == "{name}") {{ {name} = {conv}; return true; }}')
    lines.append("  return false;\n}")
    return "\n".join(lines)


def translate(src: str) -> str:
    out = []
    for line in src.splitlines():
        s = line
        if re.match(r"\s*#property\b", s):
            continue
        if re.match(r"\s*#include\s*<", s):
            continue
        if re.match(r"\s*(s?input)\s+group\b", s):
            continue
        s = re.sub(r"^(\s*)s?input\s+", r"\1", s)
        # reference array parameters:  const string &cands[]  ->  const MqlArr<string> &cands
        s = re.sub(r"(const\s+)?(\w+)\s*&\s*(\w+)\s*\[\s*\]", r"\1MqlArr<\2> &\3", s)
        # dynamic array declarations (possibly several on one line, optional initializer)
        m = re.match(r"^(\s*)((?:static\s+)?)(\w+)\s+((?:\w+\s*\[\s*\]\s*,\s*)*\w+\s*\[\s*\])\s*(=\s*\{.*\})?\s*;(.*)$", s)
        if m and m.group(3) not in ("return", "else", "delete"):
            ind, st, typ, names, init, rest = m.groups()
            names = [n.strip().replace("[", "").replace("]", "").strip() for n in names.split(",")]
            decl = ", ".join(names)
            s = f"{ind}{st}MqlArr<{typ}> {decl}{(' ' + init) if init else ''};{rest}"
        out.append(s)
    code = "\n".join(out)
    code = add_prototypes(code)
    return '#include "mql5rt.h"\n' + code + "\n" + input_setter(src) + "\n"


def add_prototypes(code: str) -> str:
    """Insert prototypes (with default args) after the last global before the first
    function, and strip default args from the definitions."""
    sig_re = re.compile(r"^(" + TYPES + r")\s+(\w+)\s*\(([^;{}]*)\)\s*$", re.M)
    protos = []
    for m in sig_re.finditer(code):
        typ, name, params = m.groups()
        if name in ("OnInit", "OnDeinit", "OnTick", "OnTimer", "OnTester", "OnTradeTransaction"):
            continue
        protos.append(f"{typ} {name}({params});")
    def strip_defaults(m):
        typ, name, params = m.groups()
        if "=" not in params:
            return m.group(0)
        parts = [re.sub(r"\s*=\s*[^,]+$", "", p) for p in split_params(params)]
        return f"{typ} {name}({', '.join(p.strip() for p in parts)})"
    code = sig_re.sub(strip_defaults, code)
    first = sig_re.search(code)
    pos = first.start() if first else len(code)
    # insert before the comment block that precedes the first function
    return code[:pos] + "// ---- prototypes (generated) ----\n" + "\n".join(protos) + "\n\n" + code[pos:]


def split_params(p: str):
    depth, cur, res = 0, "", []
    for ch in p:
        if ch in "(<{":
            depth += 1
        elif ch in ")>}":
            depth -= 1
        if ch == "," and depth == 0:
            res.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        res.append(cur)
    return res


if __name__ == "__main__":
    src = open(sys.argv[1], encoding="utf-8").read()
    open(sys.argv[2], "w").write(translate(src))
