"""Java metrics using javalang. Method end lines are found by brace-matching the token stream."""
import javalang
from javalang import tree as T
from . import ParseError, FunctionMetrics, ClassMetrics, Metrics

_IGNORED_TYPES = {"String", "Integer", "Long", "Double", "Float", "Boolean", "Character", "Byte", "Short",
                  "Object", "Math", "System", "Override", "Exception", "RuntimeException", "Void", "Number"}
_WRAPPER = "_Snippet"


def _parse(code: str):
    """Parse as a compilation unit; if that fails, retry wrapped in a class (bare methods).
    The wrapper opens on the SAME line so reported line numbers stay correct."""
    try:
        return javalang.parse.parse(code), code, False
    except (javalang.parser.JavaSyntaxError, javalang.tokenizer.LexerError, IndexError, TypeError) as first:
        wrapped = f"class {_WRAPPER} {{ " + code + "\n}"
        try:
            return javalang.parse.parse(wrapped), wrapped, True
        except Exception:
            pass
        pos = getattr(getattr(first, "at", None), "position", None)
        where = f" near line {pos.line}" if pos else ""
        raise ParseError(f"Java syntax error{where}: {getattr(first, 'description', first)}") from first


def _end_lines(tokens, start_line: int, start_col: int, has_body: bool) -> int:
    """Line of the closing brace (or ';' for abstract methods) of the declaration starting here."""
    idx = next((i for i, t in enumerate(tokens)
                if (t.position.line, t.position.column) >= (start_line, start_col)), None)
    if idx is None:
        return start_line
    depth, started = 0, False
    for t in tokens[idx:]:
        v = t.value
        if v == "{":
            depth, started = depth + 1, True
        elif v == "}":
            depth -= 1
            if started and depth == 0:
                return t.position.line
        elif v == ";" and not started and not has_body:
            return t.position.line
    return tokens[-1].position.line


_BRANCH = (T.IfStatement, T.ForStatement, T.WhileStatement, T.DoStatement, T.CatchClause, T.TernaryExpression)


def _cyclomatic(body) -> int:
    total = 1
    for _, n in (body_iter(body)):
        if isinstance(n, _BRANCH):
            total += 1
        elif isinstance(n, T.SwitchStatementCase) and n.case:  # default has an empty case list
            total += len(n.case)
        elif isinstance(n, T.BinaryOperation) and n.operator in ("&&", "||"):
            total += 1
    return total


def body_iter(body):
    for stmt in body or []:
        if isinstance(stmt, javalang.ast.Node):
            yield from stmt
        elif isinstance(stmt, list):
            yield from body_iter(stmt)


def _nesting(node, depth=0, else_if=False) -> int:
    """Max depth of nested control structures."""
    if isinstance(node, list):
        return max([_nesting(n, depth) for n in node] or [depth])
    if not isinstance(node, javalang.ast.Node):
        return depth
    if isinstance(node, T.IfStatement):
        d = depth if else_if else depth + 1
        best = max(_nesting(node.then_statement, d), d)
        e = node.else_statement
        if e is not None:
            best = max(best, _nesting(e, depth, else_if=isinstance(e, T.IfStatement)) if isinstance(e, T.IfStatement)
                       else _nesting(e, d))
        return best
    nests = (T.ForStatement, T.WhileStatement, T.DoStatement, T.TryStatement, T.SwitchStatement,
             T.SynchronizedStatement)
    d = depth + 1 if isinstance(node, nests) else depth
    best = d
    for child in node.children:
        best = max(best, _nesting(child, d))
    return best


def _coupled_types(cls_node, own: str) -> set:
    found = set()
    for _, n in cls_node:
        name = None
        if isinstance(n, T.ReferenceType):
            name = n.name
        elif isinstance(n, T.ClassCreator):
            name = n.type.name
        elif isinstance(n, (T.MethodInvocation, T.MemberReference)) and n.qualifier:
            q = n.qualifier.split(".")[0]
            name = q if q[:1].isupper() else None
        if name and name != own and name not in _IGNORED_TYPES and name != _WRAPPER and name[:1].isupper():
            found.add(name)
    return found


def extract(code: str) -> Metrics:
    tree, src, wrapped = _parse(code)
    tokens = list(javalang.tokenizer.tokenize(src))
    funcs, classes = [], []

    for _, cls in tree.filter(T.ClassDeclaration):
        is_wrapper = wrapped and cls.name == _WRAPPER
        if not is_wrapper:
            end = _end_lines(tokens, cls.position.line, cls.position.column, True)
            coupled = _coupled_types(cls, cls.name)
            for sup in ([cls.extends] if cls.extends else []) + list(cls.implements or []):
                nm = getattr(sup, "name", None)
                if nm and nm not in _IGNORED_TYPES:
                    coupled.add(nm)
            fields = sum(len(f.declarators) for f in cls.fields)
            classes.append(ClassMetrics(cls.name, cls.position.line, end, len(cls.methods) + len(cls.constructors),
                                        fields, len(coupled), sorted(coupled)))
        members = list(cls.methods) + list(cls.constructors)
        for m in members:
            start = m.position.line
            has_body = m.body is not None
            end = _end_lines(tokens, start, m.position.column, has_body)
            funcs.append(FunctionMetrics(
                m.name, start, end, end - start + 1, len(m.parameters or []),
                _cyclomatic(m.body), _nesting(m.body) if m.body else 0,
                "" if is_wrapper else cls.name))
    return Metrics("java", len(code.splitlines()), funcs, classes)
