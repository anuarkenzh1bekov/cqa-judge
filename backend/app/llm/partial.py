"""Tolerant parser for JSON that is still being generated (streaming): returns what is readable so far."""
import json


def _closers(s: str) -> str:
    """Closing quote / brackets needed to finish `s` as if it ended here."""
    stack, in_str, esc = [], False, False
    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()
    tail = '"' if in_str else ""
    if in_str and esc:  # a lone backslash at the very end
        tail = "\\" + tail
    return tail + "".join(reversed(stack))


def parse_partial(text: str):
    """Best-effort parse of a JSON prefix. Strings are returned as far as they were written; an unfinished key or
    value is dropped. Returns None when nothing is readable yet."""
    s = (text or "").strip()
    if not s:
        return None
    for _ in range(8):
        try:
            return json.loads(s + _closers(s))
        except ValueError:
            pass
        # drop the last incomplete member: cut at the last comma, or at the last opening bracket
        cut = max(s.rfind(","), s.rfind("{"), s.rfind("["))
        if cut <= 0:
            return None
        s = s[:cut + 1] if s[cut] in "{[" else s[:cut]
    return None
