# -*- coding: utf-8 -*-
"""海豚（DolphinScheduler）Python 算子交付前自检：按 Spring 语义渲染占位符 + 编译 + 字符扫描。

背景
----
DolphinScheduler 3.2.2 的 Python 算子正文里，``${名字}`` 由 Spring
``PropertyPlaceholderHelper`` 替换：占位符的**名字**会再解析一遍，
取到的**值**也会再解析一遍；解析不出来的占位符原样保留，并从它结尾之后继续扫。
所以「脚本交付时会变成什么样」不能靠肉眼判断，必须在交付前本地渲染一遍再编译。

本工具做三件事（``--check``）：

1. 扫描**模板**里的 ``>`` ``<`` ``&`` —— 交付硬规则：脚本靠复制粘贴进平台，
   这三个字符在粘贴链路里会变成 HTML 实体，把语句截断成 SyntaxError。
2. 对**渲染结果**做 ``compile()`` —— 能抓住「注释里写了可解析的占位样例，
   多行参数值把注释撑断」这类肉眼与字符扫描都抓不到的问题。
3. 列出渲染后仍未解析的 ``${...}`` —— 只告警，不算失败（选填参数可能确实没配）。

用法
----
::

    python render_placeholders.py <脚本.py> [--params 参数.json] [--param 名字=值 ...]
                                  [--out 渲染后.py] [--check]
    python render_placeholders.py --self-test

    # 交付前自检（最常用）
    python render_placeholders.py 算子脚本.py --params 参数.json --check

参数来源
--------
* ``--params``：JSON 对象 ``{名字: 值}``，值建议都写字符串；多行值用 JSON 的
  ``\\n`` 转义，值里可以有引号、反斜杠、``=``。
* ``--param``：可重复，``名字=值``，按**第一个** ``=`` 切分；同名时覆盖
  ``--params`` 里的值。

退出码
------
* 0 ``--check`` 通过（或正常渲染成功）；
* 1 ``--check`` 发现结构性问题（禁用字符 / 渲染结果编译失败）；
* 2 参数或文件错误（用法问题，argparse 的报错也是 2）。

渲染语义与 Spring 的差异
------------------------
本工具按 Spring ``parseStringValue`` 的源码语义实现：嵌套 ``${`` 计深度找配对
``}``；名字先递归解析再查表；取到的值再递归解析后替换；查不到则原样保留、
并从该占位符结尾继续往后扫；替换后从插入值之后继续扫。

Spring 遇到**循环占位**（如 ``a=${a}``）会抛 ``IllegalArgumentException``；
本工具不抛异常，而是用最大递归深度 ``MAX_DEPTH``（默认 64）做软保护：
到顶后原样返回，保证本地自检不会因为一个循环占位就挂死。真实算子脚本不应
出现循环占位——``--check`` 会把残留的 ``${...}`` 列出来。
"""

import argparse
import io
import json
import os
import shutil
import sys
import tempfile

# 最大递归深度：占位符的名字、取到的值都可能再解析，循环占位靠它兜底。
MAX_DEPTH = 64

# 交付硬规则：以下字符经粘贴链路会被转成 HTML 实体（> 与 < 已实测）。
FORBIDDEN_CHARS = (">", "<", "&")

# 报告里单条文本的最大显示长度、每类问题最多列出多少条。
_DISPLAY_LIMIT = 160
_MAX_ITEMS = 50


# ---------------------------------------------------------------------------
# 渲染：忠实模拟 Spring PropertyPlaceholderHelper.parseStringValue
# ---------------------------------------------------------------------------
def _find_end(text, start):
    """从 ``start``（指向 ``$``）开始找配对的 ``}``；找不到返回 -1。

    嵌套的 ``${`` 会给深度 +1，因此 ``${${x}}`` 的外层配对的是最后一个 ``}``。
    """
    i = start + 2
    depth = 0
    while i != len(text):
        if text.startswith("}", i):
            if depth == 0:
                return i
            depth -= 1
            i += 1
        elif text.startswith("${", i):
            depth += 1
            i += 2
        else:
            i += 1
    return -1


def resolve(text, params, depth=0, max_depth=MAX_DEPTH):
    """按 Spring 语义解析 ``text``，返回替换后的字符串。

    params 是 ``{名字: 值}`` 的字典（值都是字符串）。解析顺序：

    1. 找到 ``${`` 到配对的 ``}``，中间文本就是**占位符名字**；
    2. 先把名字递归解析一遍（``${${x}}`` 能成立的原因）；
    3. 用解析后的名字查表；取到的值也递归解析一遍，再替换进去；
    4. 查不到就原样保留，并从该占位符结尾继续往后扫（后面的占位符照常替换）；
    5. 替换成功后从插入值之后继续扫。
    """
    if depth >= max_depth:
        return text
    out = text
    start = out.find("${")
    while start != -1:
        end = _find_end(out, start)
        if end == -1:
            break
        # ① 名字先递归解析（键级递归）
        name = resolve(out[start + 2:end], params, depth + 1, max_depth)
        value = params.get(name)
        if value is None:
            # ② 解析不出：原样保留，从该占位符结尾继续往后扫
            start = out.find("${", end + 1)
            continue
        # ③ 取到的值再递归解析（值级递归），然后替换
        value = resolve(value, params, depth + 1, max_depth)
        out = out[:start] + value + out[end + 1:]
        # ④ 替换后从插入值之后继续扫
        start = out.find("${", start + len(value))
    return out


def render(template, params):
    """把模板渲染成最终交付脚本。"""
    return resolve(template, params, 0)


# ---------------------------------------------------------------------------
# 定位与扫描
# ---------------------------------------------------------------------------
def _line_col(text, index):
    """把 0 基下标换成（1 基行号, 1 基列号）。"""
    line = text.count("\n", 0, index) + 1
    last_newline = text.rfind("\n", 0, index)
    column = index - last_newline
    return line, column


def _line_text(text, line_no):
    """取 1 基行号对应的整行文本（去掉行尾的 \\r）。"""
    lines = text.split("\n")
    if 1 <= line_no <= len(lines):
        return lines[line_no - 1].rstrip("\r")
    return ""


def _clip(text, limit=_DISPLAY_LIMIT):
    """把多行/超长文本压成报告里能显示的一行。"""
    shown = text.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
    if len(shown) > limit:
        shown = shown[:limit] + "...(截断 %d 字)" % (len(shown) - limit)
    return shown


def find_forbidden(template):
    """返回模板里禁用字符的位置列表：``[(下标, 字符), ...]``。"""
    return [(index, char) for index, char in enumerate(template)
            if char in FORBIDDEN_CHARS]


def find_placeholders(text):
    """返回文本里残留占位符的列表：``[(下标, 占位符原文, 是否配对), ...]``。

    与渲染使用同一套配对规则；没有配对 ``}`` 的残缺 ``${`` 会把到结尾的整段
    算作一个残留（和 Spring 的扫描语义一致：它后面的真占位符会被整段跳过）。
    """
    found = []
    index = text.find("${")
    while index != -1:
        end = _find_end(text, index)
        if end == -1:
            found.append((index, text[index:], False))
            break
        found.append((index, text[index:end + 1], True))
        index = text.find("${", end + 1)
    return found


def compile_source(source, filename="<渲染结果>"):
    """对渲染结果做 compile()：通过返回 None，失败返回问题字典。"""
    try:
        compile(source, filename, "exec")
        return None
    except SyntaxError as exc:
        return {
            "kind": "SyntaxError",
            "message": exc.msg,
            "line": exc.lineno,
            "offset": exc.offset,
            "text": exc.text,
        }
    except ValueError as exc:
        # 例如渲染结果里出现 null 字节
        return {
            "kind": "ValueError",
            "message": str(exc),
            "line": None,
            "offset": None,
            "text": None,
        }


def run_checks(template, rendered, filename="<渲染结果>"):
    """跑三项检查，返回结果字典；``ok`` 只由禁用字符与编译结果决定。"""
    forbidden = find_forbidden(template)
    syntax = compile_source(rendered, filename)
    unresolved = find_placeholders(rendered)
    return {
        "forbidden": forbidden,
        "syntax": syntax,
        "unresolved": unresolved,
        "ok": (not forbidden) and (syntax is None),
    }


def format_report(template, rendered, report, source_name):
    """把检查结果排成人能直接读的多行报告。"""
    lines = ["==== 交付前自检: %s ====" % source_name]

    # ① 模板里的禁用字符
    forbidden = report["forbidden"]
    if forbidden:
        lines.append("[1/3 禁用字符] 模板中发现 %d 处（交付硬规则：> < & 经粘贴链路"
                     "会变成 HTML 实体）" % len(forbidden))
        for index, char in forbidden[:_MAX_ITEMS]:
            line_no, column = _line_col(template, index)
            lines.append("  第 %d 行第 %d 列: %r  | %s"
                         % (line_no, column, char,
                            _clip(_line_text(template, line_no))))
        if len(forbidden) > _MAX_ITEMS:
            lines.append("  ...(另有 %d 处未列出)" % (len(forbidden) - _MAX_ITEMS))
        lines.append("  提示：改成不含 > < & 的等价写法（见 skill 的「符号写法对照」）")
    else:
        lines.append("[1/3 禁用字符] 模板中未发现 > < &，通过")

    # ② 渲染结果的编译检查
    syntax = report["syntax"]
    if syntax is None:
        lines.append("[2/3 语法编译] 渲染结果 compile() 通过")
    else:
        lines.append("[2/3 语法编译] 渲染结果编译失败")
        lines.append("  %s: %s"
                     % (syntax["kind"], _clip(str(syntax["message"] or ""))))
        line_no = syntax.get("line")
        offset = syntax.get("offset") or 1
        if line_no is not None:
            lines.append("  位置: 第 %d 行第 %d 列" % (line_no, offset))
        text = syntax.get("text")
        if text:
            lines.append("  原文: %s" % _clip(text.rstrip("\r\n")))
            lines.append("        %s^" % (" " * max(offset - 1, 0)))
        lines.append("  提示：注释不豁免替换；多行值撑断注释、值里的连续三个双引号、"
                     "值以单个反斜杠结尾，都会这样报错")

    # ③ 渲染后仍未解析的占位符（只告警）
    unresolved = report["unresolved"]
    if unresolved:
        lines.append("[3/3 未解析占位] 渲染后仍有 %d 处未解析（仅告警：选填参数"
                     "没配时会原样保留）" % len(unresolved))
        for index, literal, closed in unresolved[:_MAX_ITEMS]:
            line_no, _column = _line_col(rendered, index)
            if closed:
                lines.append("  第 %d 行: %s" % (line_no, _clip(literal)))
            else:
                lines.append("  第 %d 行: 残缺 ${（没有配对的 }，它后面的占位符"
                             "会被整段跳过）: %s"
                             % (line_no, _clip(literal, 80)))
        if len(unresolved) > _MAX_ITEMS:
            lines.append("  ...(另有 %d 处未列出)" % (len(unresolved) - _MAX_ITEMS))
    else:
        lines.append("[3/3 未解析占位] 无残留占位符")

    lines.append("")
    if report["ok"]:
        lines.append("结果: 通过（退出码 0）")
    else:
        lines.append("结果: 不通过（退出码 1）—— 先修掉上面的问题，再交付")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 参数与文件读写
# ---------------------------------------------------------------------------
def _coerce_param_value(name, value):
    """JSON 里允许标量；转成字符串（Spring 参数本来就是文本）。"""
    if isinstance(value, str):
        return value
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return json.dumps(value)
    raise ValueError("--params 里 %r 的值必须是字符串（多行用 JSON 转义 \\n），"
                     "实际是 %r" % (name, value))


def load_params(json_path=None, param_pairs=None):
    """合并 ``--params`` 与 ``--param``（后者覆盖前者），返回参数字典。"""
    params = {}
    if json_path:
        with open(json_path, "rb") as handle:
            raw = handle.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("参数文件 %s 不是 UTF-8 编码（%s）" % (json_path, exc))
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ValueError("参数文件 %s 不是合法 JSON：%s" % (json_path, exc))
        if not isinstance(data, dict):
            raise ValueError("参数文件 %s 顶层必须是 JSON 对象（形如 {名字: 值}）"
                             % json_path)
        for name, value in data.items():
            if not isinstance(name, str):
                raise ValueError("参数文件 %s 里的参数名必须是字符串：%r"
                                 % (json_path, name))
            params[name] = _coerce_param_value(name, value)
    for item in param_pairs or []:
        name, separator, value = item.partition("=")
        if not separator:
            raise ValueError("--param 需要「名字=值」形式（按第一个 = 切分），"
                             "实际收到: %r" % item)
        if not name:
            raise ValueError("--param 的名字不能为空: %r" % item)
        params[name] = value
    return params


def read_utf8(path):
    """按 UTF-8 读文本（容忍 BOM）。"""
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("%s 不是有效的 UTF-8 文本（%s）；算子脚本请用 UTF-8 保存"
                         % (path, exc))


def write_utf8(path, text):
    """按 UTF-8 写文本，不改动换行符（渲染结果要原样落盘）。"""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _setup_console():
    """让 Windows cp936 控制台能安全打印中文与多行值。

    Python 3.7+ 的标准流带 ``reconfigure``；被重定向成 StringIO 等对象时没有
    这个方法，跳过即可（自检里会临时替换 sys.stdout）。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------
def build_parser():
    """构造命令行解析器。"""
    epilog = (
        "渲染语义（按 Spring PropertyPlaceholderHelper.parseStringValue 实现）：\n"
        "  * 嵌套 ${ 计深度找配对 }，所以 ${${x}} 能成立；\n"
        "  * 占位符的名字会再解析一遍（键级递归）；\n"
        "  * 取到的值也会再解析一遍（值级递归）；\n"
        "  * 解析不出则原样保留，并从该占位符结尾继续往后扫。\n"
        "\n"
        "与 Spring 的差异：Spring 遇到循环占位（如 a=${a}）会抛 "
        "IllegalArgumentException；\n"
        "本工具用最大递归深度 %d 层做软保护，到顶后原样返回，不会挂死。\n"
        "\n"
        "退出码：0 通过；1 --check 发现结构性问题；2 参数/文件错误。\n"
        "\n"
        "示例：\n"
        "  python render_placeholders.py 算子脚本.py                # 渲染结果打到 stdout\n"
        "  python render_placeholders.py 算子脚本.py --out 渲染后.py\n"
        "  python render_placeholders.py 算子脚本.py --params 参数.json --check\n"
        "  python render_placeholders.py 算子脚本.py --param user_prompt=你好 --check\n"
        "  python render_placeholders.py --self-test\n"
    ) % MAX_DEPTH
    parser = argparse.ArgumentParser(
        prog="render_placeholders.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="按 Spring 占位符语义渲染海豚 Python 算子脚本，并做交付前自检。",
        epilog=epilog,
    )
    parser.add_argument("template", nargs="?", metavar="脚本.py",
                        help="待渲染的模板脚本（UTF-8）")
    parser.add_argument("--params", metavar="参数.json",
                        help="JSON 对象 {名字: 值}；值可多行、含引号反斜杠")
    parser.add_argument("--param", action="append", default=[],
                        metavar="名字=值",
                        help="单个参数，可重复；按第一个 = 切分；同名时覆盖 --params")
    parser.add_argument("--out", metavar="渲染后.py",
                        help="把渲染结果写入该文件（UTF-8）")
    parser.add_argument("--check", action="store_true",
                        help="交付前自检：扫描模板 > < &、编译渲染结果、列出未解析占位")
    parser.add_argument("--self-test", action="store_true",
                        help="跑内置自检（不读文件、不联网）")
    return parser


def main(argv=None):
    """命令行入口；返回退出码。"""
    _setup_console()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        if (args.template or args.params or args.out or args.param or args.check):
            parser.error("--self-test 不能与其它参数一起用")
        return self_test()

    if not args.template:
        parser.error("缺少待渲染的脚本文件（或改用 --self-test 跑内置自检）")

    try:
        template = read_utf8(args.template)
    except (OSError, ValueError) as exc:
        print("错误: 读取模板失败: %s" % exc, file=sys.stderr)
        return 2

    try:
        params = load_params(args.params, args.param)
    except (OSError, ValueError) as exc:
        print("错误: 读取参数失败: %s" % exc, file=sys.stderr)
        return 2

    rendered = render(template, params)

    if args.out:
        try:
            write_utf8(args.out, rendered)
        except OSError as exc:
            print("错误: 写入渲染结果失败: %s" % exc, file=sys.stderr)
            return 2

    if args.check:
        report = run_checks(template, rendered, args.template)
        print(format_report(template, rendered, report, args.template))
        if args.out:
            print("渲染结果已写入: %s" % args.out, file=sys.stderr)
        return 0 if report["ok"] else 1

    if args.out:
        print("渲染结果已写入: %s" % args.out, file=sys.stderr)
        return 0

    sys.stdout.write(rendered)
    return 0


# ---------------------------------------------------------------------------
# 内置自检：不依赖外部文件与网络，覆盖关键语义与 CLI 行为
# ---------------------------------------------------------------------------
def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def _assert_eq(actual, expected, what):
    if actual != expected:
        raise AssertionError("%s：期望 %r，实际 %r" % (what, expected, actual))


def _run_cli(argv):
    """以进程内方式跑一次 main()，返回 ``(退出码, stdout, stderr)``。"""
    stdout, stderr = io.StringIO(), io.StringIO()
    saved = (sys.stdout, sys.stderr)
    sys.stdout, sys.stderr = stdout, stderr
    try:
        try:
            code = main(list(argv))
        except SystemExit as exc:
            code = exc.code
    finally:
        sys.stdout, sys.stderr = saved
    if code is None:
        code = 0
    return int(code), stdout.getvalue(), stderr.getvalue()


def _write_temp(directory, name, text):
    path = os.path.join(directory, name)
    write_utf8(path, text)
    return path


def _write_json_temp(directory, name, obj):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(obj, handle, ensure_ascii=False)
    return path


def _case_key_nested(directory):
    """键级嵌套：参数值填裸名字，靠名字递归取值。"""
    got = resolve("${${probe_name}}",
                  {"probe_name": "probe_payload",
                   "probe_payload": "PROBE_OK_123"})
    _assert_eq(got, "PROBE_OK_123", "键级嵌套（占位套占位）")


def _case_value_recurse(directory):
    """值级递归：参数值写成占位形态，靠值递归展开。"""
    got = resolve("${probe_value}",
                  {"probe_value": "${probe_payload}",
                   "probe_payload": "PROBE_OK_123"})
    _assert_eq(got, "PROBE_OK_123", "值再解析（值里写占位）")


def _case_mixed_write_fails(directory):
    """混写失败形态：名字递归换成值后，再拿这个值当名字查 -> 查不到。"""
    got = resolve("${${sqlresult}}", {"sqlresult": "上游传下来的值"})
    _assert_eq(got, "${${sqlresult}}", "两种填法混写：查不到应原样保留")


def _case_unresolved_kept(directory):
    """解析不出的占位符原样保留。"""
    _assert_eq(resolve("A${missing}B", {}), "A${missing}B",
               "解析不出应原样保留")


def _case_unresolved_then_continue(directory):
    """解析不出之后，后面的占位符仍要替换。"""
    _assert_eq(resolve("${nope}/${yes}", {"yes": "OK"}), "${nope}/OK",
               "解析不出后仍要替换后面的占位符")
    _assert_eq(resolve("${x}${y}", {"x": "${nope}", "y": "OK"}), "${nope}OK",
               "替换进来的值里若还有解析不出的占位，替换后仍要往后扫")


def _case_unclosed_swallows(directory):
    """残缺的 ${（没有配对 }）会把它后面的真占位符一起跳过。"""
    text = 'ok = "${" + "${x}"'
    _assert_eq(resolve(text, {"x": "1"}), text,
               "残缺 ${ 会吞掉后面本可解析的占位符")


def _case_nested_braces(directory):
    """嵌套 ${ 按深度找配对 }。

    注意每一层 ``${...}`` 都会各自查一次表，所以多层嵌套要靠中间参数接力：
    里层先换成值，外层才拿得到要查的名字。
    """
    _assert_eq(resolve("${a${b}}", {"b": "c", "ac": "OK"}), "OK",
               "一层嵌套花括号配对")
    _assert_eq(resolve("${a${b${c}}}", {"c": "d", "bd": "X", "aX": "OK"}),
               "OK", "两层嵌套花括号配对（中间参数接力）")
    _assert_eq(resolve("${${${x}}}", {"x": "y", "y": "z", "z": "OK"}), "OK",
               "三层纯占位嵌套配对")


def _case_multiline_value(directory):
    """多行值原样替换；放进三引号字符串里仍能编译。"""
    template = 'V = """${x}"""\nprint(V)\n'
    got = resolve(template, {"x": "第一行\n第二行"})
    _assert_eq(got, 'V = """第一行\n第二行"""\nprint(V)\n', "多行值替换")
    _assert(compile_source(got) is None, "多行值放进三引号字符串应能编译")


def _case_comment_broken(directory):
    """注释里写了可解析的占位样例，多行值把注释撑断 -> --check 必须报 SyntaxError。"""
    template = '# -*- coding: utf-8 -*-\n# 参数示例：${x}\nprint("ok")\n'
    params = {"x": "第一行\n（多行值把注释撑断）"}
    template_path = _write_temp(directory, "comment_broken.py", template)
    params_path = _write_json_temp(directory, "comment_broken.json", params)
    code, out, _err = _run_cli([template_path, "--check", "--params",
                                params_path])
    _assert(code != 0, "--check 应返回非 0，实际 %r；stdout=%r" % (code, out))
    _assert("SyntaxError" in out, "报告里应有 SyntaxError：%r" % out)
    _assert("第 3 行" in out, "报告里应指出第 3 行：%r" % out)
    _assert("invalid character" in out, "报告里应给出 invalid character：%r" % out)


def _case_forbidden_chars(directory):
    """模板里的 > < & 必须报行号，并让 --check 返回 1。"""
    template = "if a > b:\n    pass\nx = 1 & 2\n"
    template_path = _write_temp(directory, "forbidden.py", template)
    code, out, _err = _run_cli([template_path, "--check"])
    _assert_eq(code, 1, "禁用字符应让 --check 退出码为 1")
    _assert("禁用字符" in out, "报告里应有禁用字符小节：%r" % out)
    _assert("第 1 行" in out and "第 3 行" in out,
            "应报出第 1、3 行：%r" % out)


def _case_param_value_with_equals(directory):
    """--param 按第一个 = 切分，值里可以继续有 =。"""
    template_path = _write_temp(directory, "equals.py", "${x}\n")
    code, out, err = _run_cli([template_path, "--param", "x=a=b=c"])
    _assert_eq(code, 0, "含 = 的 --param 应退出 0（stderr=%r）" % err)
    _assert_eq(out, "a=b=c\n", "--param 按第一个 = 切分后的值")


def _case_params_json_and_override(directory):
    """--params 读 JSON（多行/引号/反斜杠），--param 覆盖同名项。"""
    template_path = _write_temp(directory, "json_case.py", "A=${x}\nB=${y}\n")
    params_path = _write_json_temp(directory, "params.json", {
        "x": "来自JSON",
        "y": "多行\n含 \"双引号\" 与 \\ 反斜杠",
    })
    code, out, err = _run_cli([template_path, "--params", params_path,
                               "--param", "x=命令行覆盖"])
    _assert_eq(code, 0, "--params + --param 应退出 0（stderr=%r）" % err)
    expected = 'A=命令行覆盖\nB=多行\n含 "双引号" 与 \\ 反斜杠\n'
    _assert_eq(out, expected, "JSON 参数与 --param 覆盖")


def _case_triple_quotes(directory):
    """值含连续三个双引号会撑坏原始字符串：渲染不改写，--check 报错。"""
    template = 'V = r"""${x}"""\n'
    template_path = _write_temp(directory, "triple.py", template)
    code, out, _err = _run_cli([template_path, "--check", "--param", 'x=a"""b'])
    _assert(code != 0, "值含连续三个双引号应编译失败，实际退出码 %r" % code)
    _assert("SyntaxError" in out, "报告里应有 SyntaxError：%r" % out)
    _assert_eq(resolve(template, {"x": 'a"""b'}), 'V = r"""a"""b"""\n',
               "值含三引号时的渲染结果")


def _case_trailing_backslash(directory):
    """值以单个反斜杠结尾会撑坏原始字符串：--check 报错。"""
    template = 'V = r"""${x}"""\n'
    value = "abc\\"  # 以单个反斜杠结尾
    template_path = _write_temp(directory, "backslash.py", template)
    code, out, _err = _run_cli([template_path, "--check",
                                "--param", "x=" + value])
    _assert(code != 0, "值以单个反斜杠结尾应编译失败，实际退出码 %r" % code)
    _assert("SyntaxError" in out, "报告里应有 SyntaxError：%r" % out)
    _assert_eq(resolve(template, {"x": value}), 'V = r"""abc\\"""\n',
               "值以单个反斜杠结尾时的渲染结果")


def _case_empty_params(directory):
    """空参数表：占位符原样保留；干净脚本 --check 通过。"""
    template_path = _write_temp(directory, "empty.py", 'print("ok")\n')
    code, out, _err = _run_cli([template_path, "--check"])
    _assert_eq(code, 0, "空参数表 + 干净脚本应通过（stdout=%r）" % out)
    code, out, _err = _run_cli([template_path])
    _assert_eq(code, 0, "无参数渲染应退出 0")
    _assert_eq(out, 'print("ok")\n', "无占位符时渲染结果与原文一致")
    _assert_eq(resolve("${x}", {}), "${x}", "空参数表下占位符原样保留")


def _case_cycle_guard(directory):
    """循环占位：靠深度保护收敛，不抛 RecursionError。"""
    _assert_eq(resolve("${a}", {"a": "${a}"}), "${a}",
               "自引用循环占位应收敛为原样字面量")
    got = resolve("${a}", {"a": "${b}", "b": "${a}"})
    _assert(isinstance(got, str) and len(got) < 10000,
            "互引用循环占位应有限返回，实际 %r" % (got,))
    _assert("${" in got, "互引用循环占位的返回值应保留占位字面量，实际 %r" % (got,))


def _case_unresolved_warning_only(directory):
    """未解析占位只告警，不算结构性问题。"""
    template = '# 选填参数 ${timeout_sec} 没配时原样保留\nprint("ok")\n'
    template_path = _write_temp(directory, "unresolved.py", template)
    code, out, _err = _run_cli([template_path, "--check"])
    _assert_eq(code, 0, "未解析占位只告警，退出码应为 0（stdout=%r）" % out)
    _assert("未解析" in out, "报告里应有未解析占位小节：%r" % out)
    _assert("timeout_sec" in out, "报告里应列出未解析的参数名：%r" % out)


def _case_out_file(directory):
    """--out 写文件，且 stdout 不混入渲染内容。"""
    template_path = _write_temp(directory, "out_case.py", "A=${x}\n")
    destination = os.path.join(directory, "rendered_out.py")
    code, out, err = _run_cli([template_path, "--param", "x=123",
                               "--out", destination])
    _assert_eq(code, 0, "--out 应退出 0（stderr=%r）" % err)
    _assert_eq(out, "", "--out 时 stdout 不应混入渲染内容")
    with open(destination, "r", encoding="utf-8", newline="") as handle:
        _assert_eq(handle.read(), "A=123\n", "--out 写出的内容")


def _case_syntax_error_detail(directory):
    """SyntaxError 报告要带行号、列号与出错行原文。"""
    template = "x = 1\ny = （全角括号）\n"
    template_path = _write_temp(directory, "syntax.py", template)
    code, out, _err = _run_cli([template_path, "--check"])
    _assert_eq(code, 1, "编译失败应退出 1")
    _assert("第 2 行" in out, "应报出行号 2：%r" % out)
    _assert("原文" in out, "应给出出错行原文：%r" % out)


def _case_utf8_bom(directory):
    """带 BOM 的 UTF-8 模板要能读，且 BOM 不进入渲染结果。"""
    path = os.path.join(directory, "bom.py")
    with open(path, "wb") as handle:
        handle.write(b"\xef\xbb\xbf" + "A=${x}\n".encode("utf-8"))
    code, out, err = _run_cli([path, "--param", "x=1"])
    _assert_eq(code, 0, "带 BOM 的 UTF-8 模板应能读取（stderr=%r）" % err)
    _assert_eq(out, "A=1\n", "BOM 应被剥离")


def _case_bad_param_usage(directory):
    """--param 写法错误属于用法错误，返回 2。"""
    template_path = _write_temp(directory, "bad_param.py", "A=${x}\n")
    code, _out, err = _run_cli([template_path, "--param", "=只有值没有名字"])
    _assert_eq(code, 2, "缺名字的 --param 应返回 2")
    _assert("名字不能为空" in err, "应给出清晰错误：%r" % err)
    code, _out, _err = _run_cli([template_path, "--param", "没有等号"])
    _assert_eq(code, 2, "没有 = 的 --param 应返回 2")


_SELF_TEST_CASES = [
    ("键级嵌套（占位套占位）", _case_key_nested),
    ("值级递归（值里写占位）", _case_value_recurse),
    ("两种填法混写会失败", _case_mixed_write_fails),
    ("解析不出原样保留", _case_unresolved_kept),
    ("解析不出后仍替换后续占位符", _case_unresolved_then_continue),
    ("残缺 ${ 会吞掉后面的占位符", _case_unclosed_swallows),
    ("嵌套花括号按深度配对", _case_nested_braces),
    ("多行值替换", _case_multiline_value),
    ("注释被多行值撑断（SyntaxError）", _case_comment_broken),
    ("禁用字符检出", _case_forbidden_chars),
    ("--param 值含 =", _case_param_value_with_equals),
    ("--params JSON + --param 覆盖", _case_params_json_and_override),
    ("值含三引号", _case_triple_quotes),
    ("值以单个反斜杠结尾", _case_trailing_backslash),
    ("空参数表", _case_empty_params),
    ("循环占位保护", _case_cycle_guard),
    ("未解析占位只告警", _case_unresolved_warning_only),
    ("--out 写文件", _case_out_file),
    ("SyntaxError 带行号/列号/原文", _case_syntax_error_detail),
    ("UTF-8 BOM 容忍", _case_utf8_bom),
    ("--param 用法错误返回 2", _case_bad_param_usage),
]


def self_test():
    """跑内置自检；全部通过返回 0，否则返回 1。"""
    directory = tempfile.mkdtemp(prefix="render_placeholders_selftest_")
    passed = 0
    failed = 0
    print("==== render_placeholders.py 内置自检（共 %d 项）===="
          % len(_SELF_TEST_CASES))
    try:
        for name, case in _SELF_TEST_CASES:
            try:
                case(directory)
            except AssertionError as exc:
                failed += 1
                print("[FAIL] %s —— %s" % (name, exc))
            except Exception as exc:  # 自检自身出 bug 也要如实报出来
                failed += 1
                print("[FAIL] %s —— 未预期异常 %s: %s"
                      % (name, type(exc).__name__, exc))
            else:
                passed += 1
                print("[PASS] %s" % name)
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    print("")
    print("自检结果: %d 项通过 / %d 项失败 / 共 %d 项"
          % (passed, failed, len(_SELF_TEST_CASES)))
    if failed:
        print("结果: 失败（退出码 1）")
        return 1
    print("结果: 全部通过（退出码 0）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
