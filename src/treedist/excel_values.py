"""A workbook saved with its formulas and their values, so that every viewer shows the numbers.

openpyxl writes a formula without its value. Excel computes it when the file is opened for editing, but a preview
does not: Outlook, Mail, a phone, Quick Look and Excel's own protected view show 0 in every formula cell until the
file is computed. Here the formulas the appendix uses (SUMIFS, SUM, IF, OR, arithmetic and comparisons over cells and
ranges) are computed from the workbook itself and written beside each formula as its cached value. Excel still
recomputes everything when the file opens, so a value here can never override a formula.
"""

from __future__ import annotations

import operator
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape, unescape

import numpy as np

_REF = re.compile(r"^(?:(?P<sheet>'(?:[^']|'')+'|[^'!]+)!)?\$?(?P<c1>[A-Z]+)\$?(?P<r1>\d+)(?::\$?(?P<c2>[A-Z]+)\$?(?P<r2>\d+))?$")
_CRITERION = re.compile(r"^(<=|>=|<>|<|>|=)?(.*)$", re.S)
_COMPARE = {"=": operator.eq, "<>": operator.ne, "<": operator.lt, ">": operator.gt, "<=": operator.le,
            ">=": operator.ge}


class ExcelError(str):
    """An Excel error value such as #DIV/0!."""


class Unsupported(Exception):
    """A formula outside what this evaluator knows; the cell is left for Excel to compute."""


class _Range:
    def __init__(self, key: tuple, values: list):
        self.key, self.values = key, values


class _Column:
    """A criteria range read once, so that each SUMIFS criterion is one comparison over arrays, not one per cell."""

    def __init__(self, values: list):
        n = len(values)
        self.values = values
        self.boolean = np.fromiter((isinstance(v, bool) for v in values), bool, n)
        self.number = np.fromiter((isinstance(v, (int, float)) for v in values), bool, n) & ~self.boolean
        self.text = np.fromiter((isinstance(v, str) for v in values), bool, n)
        self.empty = np.fromiter((v is None or (isinstance(v, str) and v == "") for v in values), bool, n)
        self.numbers = np.array([float(v) if isinstance(v, (int, float)) else np.nan for v in values], dtype=float)
        read = [_as_float(v) if isinstance(v, str) else None for v in values]
        self.readable = np.fromiter((r is not None for r in read), bool, n)
        self.read = np.array([np.nan if r is None else r for r in read], dtype=float)
        self.lower = np.array([v.lower() if isinstance(v, str) else None for v in values], dtype=object)

    def mask(self, criterion) -> np.ndarray:
        """The same answer as `_matches` for every cell."""
        if criterion is None:
            criterion = ""
        if isinstance(criterion, bool):
            return self.boolean & (self.numbers == float(criterion))
        if isinstance(criterion, (int, float)):
            op, wanted = "=", float(criterion)
        else:
            match = _CRITERION.match(str(criterion))
            op, rest = match.group(1) or "=", match.group(2)
            number = _as_float(rest)
            wanted = number if number is not None else rest
        compare = _COMPARE[op]
        with np.errstate(invalid="ignore"):
            if isinstance(wanted, float):
                if op == "=":
                    return (((self.number | self.boolean) & (self.numbers == wanted))
                            | (self.readable & (self.read == wanted)))
                if op == "<>":
                    return np.where(self.number, self.numbers != wanted, np.where(self.readable, self.read != wanted, True))
                return self.number & compare(self.numbers, wanted)
            if wanted == "":
                return self.empty.copy() if op == "=" else ~(self.empty | self.boolean)
            if op in ("=", "<>"):
                same = self.text & (self.lower == wanted.lower())
                return same if op == "=" else ~same
        # Text in order is rare and Excel's rules for it are Python's here: one cell at a time.
        return np.array([_matches(v, criterion) for v in self.values], dtype=bool)


def _number(value):
    """A value as Excel's arithmetic reads it."""
    if value is None or value == "":
        return 0.0 if value is None else ExcelError("#VALUE!")
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, ExcelError):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return ExcelError("#VALUE!")


def _as_float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _compare(op: str, left, right) -> bool:
    if left is None:
        left = "" if isinstance(right, str) else 0.0
    if right is None:
        right = "" if isinstance(left, str) else 0.0
    if isinstance(left, bool) or isinstance(right, bool):
        left, right = (float(left) if isinstance(left, bool) else left), (float(right) if isinstance(right, bool) else right)
    numeric = isinstance(left, (int, float)), isinstance(right, (int, float))
    if all(numeric):
        return _COMPARE[op](float(left), float(right))
    if not any(numeric):
        return _COMPARE[op](str(left).lower(), str(right).lower())
    # Excel orders every number before every text.
    rank = (0 if numeric[0] else 1), (0 if numeric[1] else 1)
    return _COMPARE[op](*rank)


class Evaluator:
    """Computes the formulas of an openpyxl workbook from its own cells."""

    def __init__(self, book):
        self.book = book
        self.sheets = {s.title: s for s in book.worksheets}
        self.memo: dict[tuple[str, str], object] = {}
        self.ranges: dict[tuple, list] = {}
        self.masks: dict[tuple, np.ndarray] = {}
        self.columns: dict[tuple, _Column] = {}
        self.arrays: dict[tuple, np.ndarray] = {}

    # Cells and ranges.
    def cell(self, sheet: str, coordinate: str):
        key = (sheet, coordinate)
        if key not in self.memo:
            self.memo[key] = None  # a circular reference reads as empty
            value = self.sheets[sheet][coordinate].value
            if isinstance(value, str) and value.startswith("="):
                value = self.formula(sheet, value)
            self.memo[key] = value
        return self.memo[key]

    def _reference(self, text: str, sheet: str):
        match = _REF.match(text)
        if not match:
            raise Unsupported(text)
        name = match["sheet"]
        if name:
            name = name[1:-1].replace("''", "'") if name.startswith("'") else name
        else:
            name = sheet
        if name not in self.sheets:
            raise Unsupported(text)
        if not match["c2"]:
            return self.cell(name, f"{match['c1']}{match['r1']}")
        key = (name, match["c1"], int(match["r1"]), match["c2"], int(match["r2"]))
        if key not in self.ranges:
            from openpyxl.utils import column_index_from_string, get_column_letter

            first, last = column_index_from_string(key[1]), column_index_from_string(key[3])
            self.ranges[key] = [self.cell(name, f"{get_column_letter(c)}{r}")
                                for r in range(key[2], key[4] + 1) for c in range(first, last + 1)]
        return _Range(key, self.ranges[key])

    # Formulas.
    def formula(self, sheet: str, text: str):
        from openpyxl.formula.tokenizer import Token, Tokenizer

        tokens = [t for t in Tokenizer(text).items if t.type != Token.WSPACE]
        parser = _Parser(tokens)
        tree = parser.expression()
        if parser.position != len(tokens):
            raise Unsupported(text)
        value = self._evaluate(tree, sheet)
        return value.values[0] if isinstance(value, _Range) and len(value.values) == 1 else value

    def _evaluate(self, node, sheet: str):
        kind = node[0]
        if kind == "value":
            return node[1]
        if kind == "ref":
            return self._reference(node[1], sheet)
        if kind == "neg":
            value = _number(self._scalar(node[1], sheet))
            return value if isinstance(value, ExcelError) else -value
        if kind == "op":
            return self._operate(node[1], self._scalar(node[2], sheet), self._scalar(node[3], sheet))
        if kind == "call":
            return self._call(node[1], node[2], sheet)
        raise Unsupported(kind)

    def _scalar(self, node, sheet: str):
        value = self._evaluate(node, sheet)
        if isinstance(value, _Range):
            if len(value.values) != 1:
                raise Unsupported("a range where one value is wanted")
            return value.values[0]
        return value

    def _operate(self, op: str, left, right):
        for value in (left, right):
            if isinstance(value, ExcelError):
                return value
        if op in _COMPARE:
            return _compare(op, left, right)
        if op == "&":
            return "".join("" if v is None else (f"{v:g}" if isinstance(v, float) else str(v)) for v in (left, right))
        a, b = _number(left), _number(right)
        for value in (a, b):
            if isinstance(value, ExcelError):
                return value
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return ExcelError("#DIV/0!") if b == 0 else a / b
        if op == "^":
            return a ** b
        raise Unsupported(op)

    def _call(self, name: str, arguments: list, sheet: str):
        name = name.upper()
        if name == "IF":
            test = self._scalar(arguments[0], sheet)
            if isinstance(test, ExcelError):
                return test
            chosen = arguments[1] if _truth(test) else (arguments[2] if len(arguments) > 2 else ("value", False))
            return self._scalar(chosen, sheet)
        if name == "OR":
            values = [self._evaluate(a, sheet) for a in arguments]
            flat = [v for value in values for v in (value.values if isinstance(value, _Range) else [value])]
            return any(_truth(v) for v in flat if v is not None)
        if name == "SUM":
            total = 0.0
            for argument in arguments:
                value = self._evaluate(argument, sheet)
                if isinstance(value, _Range):
                    total += sum(float(v) for v in value.values if isinstance(v, (int, float)) and not isinstance(v, bool))
                else:
                    number = _number(value)
                    if isinstance(number, ExcelError):
                        return number
                    total += number
            return total
        if name == "SUMIFS":
            return self._sumifs([self._evaluate(a, sheet) for a in arguments])
        raise Unsupported(name)

    def _sumifs(self, values: list):
        target, pairs = values[0], values[1:]
        if not isinstance(target, _Range) or len(pairs) % 2:
            raise Unsupported("SUMIFS")
        if target.key not in self.arrays:
            self.arrays[target.key] = np.array(
                [float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0 for v in target.values])
        mask = np.ones(len(target.values), dtype=bool)
        for where, criterion in zip(pairs[::2], pairs[1::2]):
            if not isinstance(where, _Range) or len(where.values) != len(target.values):
                raise Unsupported("SUMIFS")
            if isinstance(criterion, _Range):
                criterion = criterion.values[0] if len(criterion.values) == 1 else None
            mask &= self._mask(where, criterion)
        return float(self.arrays[target.key][mask].sum())

    def _mask(self, where: _Range, criterion) -> np.ndarray:
        key = (where.key, type(criterion).__name__, criterion)
        if key not in self.masks:
            if where.key not in self.columns:
                self.columns[where.key] = _Column(where.values)
            self.masks[key] = self.columns[where.key].mask(criterion)
        return self.masks[key]


def _truth(value) -> bool:
    if isinstance(value, str):
        return value.upper() == "TRUE"
    return bool(value)


def _matches(value, criterion) -> bool:
    """Whether a cell meets a SUMIFS criterion, as Excel reads it (without wildcards)."""
    if criterion is None:
        criterion = ""
    if isinstance(criterion, bool):
        return isinstance(value, bool) and value == criterion
    if isinstance(criterion, (int, float)):
        op, wanted = "=", float(criterion)
    else:
        match = _CRITERION.match(str(criterion))
        op, rest = match.group(1) or "=", match.group(2)
        number = _as_float(rest)
        wanted = number if number is not None else rest
    if isinstance(value, bool):
        value = None if op != "=" else value
    if isinstance(wanted, float):
        if isinstance(value, (int, float)):
            return _COMPARE[op](float(value), wanted)
        number = _as_float(value) if isinstance(value, str) and op in ("=", "<>") else None
        if number is not None:
            return _COMPARE[op](number, wanted)
        return op == "<>"
    if wanted == "":
        empty = value is None or value == ""
        return empty if op == "=" else not empty
    if not isinstance(value, str):
        return op == "<>"
    return _COMPARE[op](value.lower(), wanted.lower())


class _Parser:
    """Excel's operator precedence, for the operators the appendix uses: comparison, &, + -, * /, ^, unary minus."""

    def __init__(self, tokens):
        self.tokens, self.position = tokens, 0

    def _peek(self):
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def _next(self):
        token = self._peek()
        self.position += 1
        return token

    def _binary(self, operators, lower):
        node = lower()
        while (token := self._peek()) is not None and token.type == "OPERATOR-INFIX" and token.value in operators:
            self._next()
            node = ("op", token.value, node, lower())
        return node

    def expression(self):
        return self._binary(set(_COMPARE), self._concat)

    def _concat(self):
        return self._binary({"&"}, self._sum)

    def _sum(self):
        return self._binary({"+", "-"}, self._product)

    def _product(self):
        return self._binary({"*", "/"}, self._power)

    def _power(self):
        return self._binary({"^"}, self._unary)

    def _unary(self):
        token = self._peek()
        if token is not None and token.type == "OPERATOR-PREFIX":
            self._next()
            inner = self._unary()
            return ("neg", inner) if token.value == "-" else inner
        return self._primary()

    def _primary(self):
        token = self._next()
        if token is None:
            raise Unsupported("end of formula")
        if token.type == "OPERAND":
            if token.subtype == "NUMBER":
                return ("value", float(token.value))
            if token.subtype == "TEXT":
                return ("value", token.value[1:-1].replace('""', '"'))
            if token.subtype == "LOGICAL":
                return ("value", token.value.upper() == "TRUE")
            if token.subtype == "RANGE":
                return ("ref", token.value)
            raise Unsupported(token.value)
        if token.type == "FUNC" and token.subtype == "OPEN":
            name, arguments = token.value[:-1], []
            if (close := self._peek()) is not None and close.type == "FUNC" and close.subtype == "CLOSE":
                self._next()
                return ("call", name, arguments)
            while True:
                arguments.append(self.expression())
                token = self._next()
                if token is None:
                    raise Unsupported("unclosed function")
                if token.type == "SEP" and token.subtype == "ARG":
                    continue
                if token.type == "FUNC" and token.subtype == "CLOSE":
                    return ("call", name, arguments)
                raise Unsupported(token.value)
        if token.type == "PAREN" and token.subtype == "OPEN":
            node = self.expression()
            close = self._next()
            if close is None or close.type != "PAREN":
                raise Unsupported("unclosed parenthesis")
            return node
        raise Unsupported(token.value)


def computed(book) -> dict[str, dict[str, object]]:
    """Every formula cell's value, per sheet and coordinate; a formula this cannot compute is left out."""
    evaluator, found = Evaluator(book), {}
    for sheet in book.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    try:
                        found.setdefault(sheet.title, {})[cell.coordinate] = evaluator.cell(sheet.title, cell.coordinate)
                    except (Unsupported, KeyError, IndexError, ValueError, TypeError):
                        continue
    return found


_FORMULA_CELL = re.compile(r'<c r="([A-Z]+\d+)"([^>]*)><f>([^<]*)</f><v\s*/></c>')


def _cached(value) -> tuple[str | None, str]:
    """The cell type and <v> text for a computed value."""
    if isinstance(value, ExcelError):
        return "e", escape(str(value))
    if isinstance(value, bool):
        return "b", "1" if value else "0"
    if isinstance(value, (int, float)):
        number = float(value)
        return (None, repr(number)) if np.isfinite(number) else ("e", "#NUM!")
    if value is None:
        return None, "0"
    return "str", escape(str(value))


def save(book, path: Path) -> None:
    """Save the workbook, then write each formula's computed value into the file beside the formula."""
    values = computed(book)
    book.save(path)
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    workbook = parts["xl/workbook.xml"].decode("utf-8")
    links = parts["xl/_rels/workbook.xml.rels"].decode("utf-8")
    attribute = lambda text, name: re.search(rf'\b{name}="([^"]*)"', text)  # noqa: E731
    targets = {}
    for m in re.finditer(r"<Relationship\b([^>]*)>", links):
        rid, target = attribute(m.group(1), "Id"), attribute(m.group(1), "Target")
        if rid and target:
            targets[rid.group(1)] = target.group(1)
    for m in re.finditer(r"<sheet\b([^>]*)>", workbook):
        name, rid = attribute(m.group(1), "name"), attribute(m.group(1), "r:id")
        if not name or not rid:
            continue
        name, target = unescape(name.group(1), {"&quot;": '"', "&apos;": "'"}), targets.get(rid.group(1), "")
        part = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
        if name not in values or part not in parts:
            continue
        sheet_values = values[name]

        def fill(match, sheet_values=sheet_values):
            if match.group(1) not in sheet_values:
                return match.group(0)
            kind, text = _cached(sheet_values[match.group(1)])
            attributes = re.sub(r'\s+t="[^"]*"', "", match.group(2)) + (f' t="{kind}"' if kind else "")
            return f'<c r="{match.group(1)}"{attributes}><f>{match.group(3)}</f><v>{text}</v></c>'

        parts[part] = _FORMULA_CELL.sub(fill, parts[part].decode("utf-8")).encode("utf-8")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
