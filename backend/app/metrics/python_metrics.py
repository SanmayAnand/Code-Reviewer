"""Python metrics using the standard-library ast module (no regex heuristics)."""
import ast
import builtins
from . import ParseError, FunctionMetrics, ClassMetrics, Metrics

_BUILTINS = set(dir(builtins))
_NEST = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match)
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _children(node):
    """Child nodes, not descending into nested functions/classes (they are measured separately)."""
    for c in ast.iter_child_nodes(node):
        if not isinstance(c, _SCOPES):
            yield c


def _cyclomatic(fn) -> int:
    total, stack = 1, list(_children(fn))
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.match_case)):
            total += 1
        elif isinstance(n, ast.BoolOp):
            total += len(n.values) - 1
        elif isinstance(n, ast.comprehension):
            total += 1 + len(n.ifs)
        stack.extend(_children(n))
    return total


def _nesting(node, depth=0, is_elif=False) -> int:
    best = depth
    for c in _children(node):
        if isinstance(c, _NEST):
            # an `elif` is an If nested in orelse; do not count it as deeper nesting
            elif_chain = isinstance(node, ast.If) and isinstance(c, ast.If) and c in node.orelse and len(node.orelse) == 1
            best = max(best, _nesting(c, depth if elif_chain else depth + 1))
        else:
            best = max(best, _nesting(c, depth))
    return best


def _params(fn, in_class: bool) -> int:
    a = fn.args
    names = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
    if a.vararg:
        names.append(a.vararg.arg)
    if a.kwarg:
        names.append(a.kwarg.arg)
    if in_class and names and names[0] in ("self", "cls"):
        names = names[1:]
    return len(names)


def _fn_metrics(fn, owner: str) -> FunctionMetrics:
    start = min([fn.lineno] + [d.lineno for d in fn.decorator_list])
    end = fn.end_lineno or fn.lineno
    return FunctionMetrics(fn.name, start, end, end - start + 1, _params(fn, bool(owner)),
                           _cyclomatic(fn), _nesting(fn), owner)


def _class_metrics(cls: ast.ClassDef, imported: set) -> ClassMetrics:
    methods, fields, coupled = 0, set(), set()
    for item in cls.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods += 1
        elif isinstance(item, ast.Assign):
            fields.update(t.id for t in item.targets if isinstance(t, ast.Name))
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            fields.add(item.target.id)
    for n in ast.walk(cls):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self" \
                and isinstance(n.ctx, ast.Store):
            fields.add(n.attr)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            nm = n.id
            if nm == cls.name or nm in _BUILTINS or nm in ("self", "cls"):
                continue
            is_type_like = nm[:1].isupper() and not nm.isupper()
            if is_type_like or nm in imported:
                coupled.add(nm)
    for b in cls.bases:  # base classes are coupling too
        if isinstance(b, ast.Name) and b.id not in _BUILTINS:
            coupled.add(b.id)
    return ClassMetrics(cls.name, cls.lineno, cls.end_lineno or cls.lineno, methods, len(fields),
                        len(coupled), sorted(coupled))


def extract(code: str) -> Metrics:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ParseError(f"Python syntax error on line {e.lineno}: {e.msg}") from e
    except (ValueError, RecursionError) as e:
        raise ParseError(f"Could not parse Python code: {e}") from e

    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported.update((a.asname or a.name).split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            imported.update(a.asname or a.name for a in n.names)

    funcs, classes = [], []

    def visit(node, owner=""):
        for c in ast.iter_child_nodes(node):
            if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.append(_fn_metrics(c, owner))
                visit(c, "")  # nested functions
            elif isinstance(c, ast.ClassDef):
                classes.append(_class_metrics(c, imported))
                visit(c, c.name)
            else:
                visit(c, owner)

    visit(tree)
    return Metrics("python", len(code.splitlines()), funcs, classes)
