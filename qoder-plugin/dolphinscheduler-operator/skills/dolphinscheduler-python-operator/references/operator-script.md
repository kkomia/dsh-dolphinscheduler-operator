# 海豚 Python 算子：脚本侧规范

写或审查一段要粘进海豚 Python 算子的脚本时，以本文件为准。

## 定制算子：一个算子做完，能确定的固化

用户说「定制算子」时，按这一节做，**不要**套用通用算子模板。
目标：**一个任务一份脚本，写完就能上，不为将来留扩展。**（DSH 版对应 `/custom-operator` 命令。）

| 规则 | 做法 |
|---|---|
| 主体一个脚本 | 取数、清洗、计算、产出、`setValue` 都在同一个算子节点里，不拆 A/B/C |
| 唯一例外：文件导出 | 只有「文件要出现在【查看结果】」时才拆第二个通用上传算子（见「导出文件的标准做法」）；只是把文件交给下游，单算子写 `/data/` 发绝对路径就够了 |
| 能固化的固化 | 数据源（视图 viewId / MinIO 端点-桶-对象键 / 库表）、口径与列名、输出目录与文件名、时间窗口、超时，全部写在脚本顶部常量区 |
| 参数最少 | 只留本次任务真的要外部决定的，**0~3 个**；能写死就不声明；上游出参不重复声明；出参只留下游或交付真正要用的 |
| 不做通用化 | 不要多视图 Map、配置对象、插件式开关、兼容分支、用不到的兜底；新需求就再写一份 |
| 交付精简 | 脚本 + 参数表（可能 0 行）+ 一句部署说明；仓库名 / 描述 / commit 只在用户要建仓库时补 |

判断「这个参数该不该留」只有一句话：**换一次任务它会不会变？不变就写进常量。**

### 什么固化、什么留参数

| 东西 | 处理 |
|---|---|
| 数据源（viewId、桶 + 对象键、库表名） | 固化 |
| 统计口径（年份、月份、过滤条件） | 固化；要每月自动变就按运行时间算，仍然不加参数 |
| 输出目录 / 文件名 / 列名 / 断言行数列数 | 固化（文件名可带实例 id 防重名） |
| 「同一份脚本明天还要按别的参数跑」 | 才留入参，且只留会变的那一个 |
| 下游 / 交付真正要用的结果 | 才声明出参 |

### 最小样子：0 个入参、1 个出参、单脚本产出文件

```python
# -*- coding: utf-8 -*-
"""定制算子示例：数据视图取数、写 xlsx、把绝对路径发给下游。

固定项全在顶部常量区；本节点不入参；出参只有 filePath。
"""
import importlib.util as u
import json
import os
import subprocess
import sys
import urllib.request

# ---------- 固定项：换任务只改这里，不加入参 ----------
API_BASE = "http://PLATFORM_HOST:8998"
VIEW_ID = "视图页 F12 抄到的 viewId"
VIEW_PARAMS = [{"年份": "2026"}, {"月份": "10"}]
OUT_DIR = "/data/outbox"
OUT_NAME = "统计月报_2026-10.xlsx"
TIMEOUT = 60
DEPS = [("openpyxl", "3.1.5", "openpyxl")]

URL = API_BASE.rstrip("/") + "/api/.DataView/view/v1/sql/resultAppend"


def die(msg):
    print("错误: %s" % msg, file=sys.stderr)
    sys.exit(2)


def check_deps(deps):
    """只检查；缺了才装。"""
    missing = [d for d in deps if u.find_spec(d[2]) is None]
    if not missing:
        return
    pkgs = ["%s==%s" % (d[0], d[1]) for d in missing]
    p = subprocess.run([sys.executable, "-m", "pip", "install", "--no-input",
                        "--disable-pip-version-check"] + pkgs,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
    if p.returncode != 0:
        die("装包失败: %s" % p.stdout.decode("utf-8", "replace")[-1000:])


def fetch_rows():
    body = json.dumps({"pageNumber": 1, "pageSize": 5000,
                       "queryParamList": VIEW_PARAMS,
                       "viewId": VIEW_ID}).encode("utf-8")
    req = urllib.request.Request(URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json;charset=UTF-8")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        doc = json.loads(resp.read().decode("utf-8", "replace"))
    if str(doc.get("code")) != "20000":
        die("视图返回失败: code=%s message=%s"
            % (doc.get("code"), doc.get("message")))
    data = doc.get("data") or {}
    rows = data.get("list") or data.get("rows") or []
    return [{k: v for k, v in row.items() if k != "rows"} for row in rows]


def write_xlsx(rows):
    import openpyxl
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, OUT_NAME)
    wb = openpyxl.Workbook()
    ws = wb.active
    cols = list(rows[0].keys())
    ws.append(cols)
    for row in rows:
        ws.append([row.get(c) for c in cols])
    wb.save(path)
    return path


check_deps(DEPS)
rows = fetch_rows()
if not rows:
    die("视图返回 0 行：先按默认参数在视图页预览确认有数据")
path = write_xlsx(rows)
print("[out] %d 行，写到 %s" % (len(rows), path))
print("${setValue(filePath=%s)}" % path)
```

参数表就只有一行：

| 参数名 | 类型 | 必填 | 填什么 |
|---|---|---|---|
| filePath | VARCHAR | 出参 | value 留空，脚本写入文件绝对路径 |

下游接通用上传算子即可（它按约定只认上游出参 `filePath`）。

## 符号写法对照（交付脚本必须遵守）

脚本是靠**复制粘贴**进海豚的。实测：`>` 会在粘贴链路里变成 `&gt;`，
里面的 `;` 直接把语句截断 —— `if len(x) &gt; 1:` 报 `SyntaxError: invalid syntax`。
所以交付的脚本里**不要出现 `>` `<` `&`**：

| 想写 | 写成 |
|---|---|
| `a > b` | `a != b`（只判不等时）／`max(a, b) == a` |
| `a >= 32` | `a not in range(32)` |
| `a < b` | `min(a, b) == a` |
| `a <= n` | `a in range(n + 1)` |
| 注释里的 `->` | 用文字，例如「转成」 |

`<` 也**实测**会被转成 `&lt;` —— `if len(parts) &lt; 4:` 报同样的 `SyntaxError`。
`&` 没单独实测，按同样风险处理。

**交付前必须：代码先落盘，再过一遍这四种字符的扫描。**
本项目已经栽过两次，第二次就是因为「只把代码贴在对话里、没落盘，
扫描工具根本没跑到」。贴在对话里的每一段可执行代码，都要先在磁盘上存在过。

### 注释不豁免替换（用户实跑反馈）

平台替换的是**整段脚本文本**，注释只是文本的一部分：注释里出现「真实参数名 + 占位形状」的样例，
**照样会被替换**。值是「多行」时注释会被撑断，报 `SyntaxError: invalid character`。
规则：**注释里只用文字描述占位形状，不要写占位样例。**

自检里 `startswith("${")` 这类**残缺的 `${`** 会一路扫到下一个配平的 `}`，
把中间的真占位符一起跳过。所以 **所有参数读取都放在自检块之前，一行都别往下挪**。
（这条是 Spring 扫描语义的推断，本环境未实测；但遵守成本为零。）

**交付前自检（可选，需本机有 Python）**：在本 skill 目录下用
`scripts/render_placeholders.py` 按 Spring 语义把脚本渲染一遍再编译，顺带扫 `> < &`。
能抓住「注释被多行值撑断」这类肉眼漏掉的问题：

```powershell
python scripts/render_placeholders.py 算子脚本.py --params 参数.json --check
```

## 算子脚本模板

```python
# -*- coding: utf-8 -*-
import subprocess
import sys


# ---------- 1. 读入参 ----------
# 参数值是平台替换进来的，读到的就是字符串
TARGET = "${target_dir}".strip()
PATTERN = "${pattern}".strip()
RAW_REC = "${recursive}".strip()

# 必填项：未配置则退出（未配置时读到的是字面量 "${target_dir}"）
if TARGET.startswith("${"):
    print("错误: 入参 target_dir 未配置", file=sys.stderr)
    sys.exit(2)

# 可选项：未配置时用默认值（不查的话会被当成 False）
RECURSIVE = RAW_REC in ("1", "true", "True") if not RAW_REC.startswith("${") else False


# ---------- 2. 业务逻辑 ----------
def run(cmd, timeout=120):
    """所有外部调用都要加 timeout —— 平台不设超时。"""
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=timeout)
    return p.returncode, p.stdout.decode("utf-8", "replace")


rc, out = run(["ls", "-la", TARGET])
ok = (rc == 0)
print(out[-500:])                                # 便于人在日志里看


# ---------- 3. 发出参 ----------
print("${setValue(checkResult=%s)}" % ("true" if ok else "false"))


# ---------- 4. 退出码表达成败 ----------
sys.exit(0 if ok else 2)
```

## 入参：脚本侧

占位符写成 `${参数名}`，平台执行前替换成实际值。

### 参数从哪来：替换是"查表"，不是"找声明"

平台派发任务时会拼一张 `prepareParamsMap`，脚本里的 `${名字}` 就是拿它查表替换的。
**"声明入参" = 往这张表里加一条，不是"申请权限"。** 表里本来就有的，不写也能取到。

| 来源 | 要不要在本节点写 |
|---|---|
| **上游任务的 OUT 参数** | **千万别写** |
| 本节点的本地参数（IN） | 要写 |
| **全局参数 / 工作流级参数** | **不用写**，`prepareParamsMap` 里本来就有 [实测] |
| `system.*`（项目/工作流/任务 ID、业务日期） | **写了也取不到**，见下 |

**上游出参为什么千万别写**：优先级是
`启动参数 本地参数 上游传入 全局参数` —— 本地参数更高。
在下游再声明一个同名的空参数，就把上游传下来的值**盖成空**了。
（实测：某任务的 `localParams` 里没有 `org_code`，脚本里 `${org_code}` 照样被替换。）

**`system.*` 是个陷阱**：它们在 `prepareParamsMap` 里**有键有值**，
但脚本里 `${system.project.code}` **不会被替换**（实测两次）。
**要什么值，就让上游用出参传下来，或者自己声明一个带值的入参。**

平台自带一个全局参数 `参数1=v1`（下面那张表的第 4 条），它跟本节点配了什么无关 ——
别看到它就以为是自己节点配的值。

> 过滤发生在哪一层**尚未定位**——`PropertyPlaceholderHelper` 通读过，
> 对占位符名字没有任何字符限制。按实测用就行，别去推导。
>
> 例外：**平台用「启动参数」启动工作流时**，`${projectCode}` 这类短名是能拿到的。
> 手工从 UI 点运行就没有。兜底办法见「那 5 个 ID 从哪来」。

#### 表里到底有什么：`prepareParamsMap`

平台派发任务时先拼这张表，脚本里的 `${名字}` 就是拿它**查表替换**。
任务日志里 `End initialize task {...}` 能看到它（脱敏后）[实测]：

```json
"prepareParamsMap" : {
  "stat_year" : {"prop":"stat_year","direct":"IN","type":"VARCHAR","value":"2026"},
  "dry_run"   : {"prop":"dry_run","direct":"IN","type":"VARCHAR","value":""},
  "filepath"  : {"prop":"filepath","direct":"OUT","type":"VARCHAR","value":null},
  "参数1"     : {"prop":"参数1","direct":"IN","type":"VARCHAR","value":"v1"},
  "system.project.code" : {"prop":"system.project.code","direct":"IN","type":"VARCHAR","value":"<项目ID>"}
}
```

四条结论，按重要性排：

| # | 结论 | 证据 |
|---|---|---|
| 1 | **全局参数直接在这张表里**，节点【入参】为空也能替换成功 | [实测] 三个参数只配在全局参数里，节点没声明，脚本取到 `'2026' / '10' / ''` |
| 2 | 上游传下来的 OUT 参数也在表里，`direct` 是 `OUT`，没发值时是 `null` | [实测] `"filepath": {"direct":"OUT","value":null}` |
| 3 | `system.*` 有键有值，但脚本里 `${system.xxx}` **不会被替换** | [实测，两次] |
| 4 | 平台自带一个全局参数 `参数1=v1`，别被它误导成本节点的值 | [实测] |

> 所以「声明入参」不是申请权限，而是往这张表里加一条；**表里本来就有的，不声明也能取到。**

**排查顺序（别靠猜）**：参数值不对时先翻日志里这张表 ——
① 有没有这个键（没有 = 名字拼错 / 没配）；② `value` 是什么（`null` = 上游 OUT 没发值，`""` = 配了空值）；
③ 本节点有没有同名空入参把全局值盖掉。

#### 全局参数 / 工作流参数：配在项目里，节点上不用声明

| 配法 | 脚本里怎么写 | 要不要在本节点声明【入参】 |
|---|---|---|
| 全局参数（项目级） | `${stat_year}` | **不用** [实测] |
| 工作流定义里的「工作流参数」 | `${stat_year}` | 不用 [推断] |
| 本节点本地参数 | `${stat_year}` | 要，且 value 必须填值 |

推荐配法：**统计年 / 月份 / 是否干跑这类跨工作流共享的配置放全局参数，节点上什么都不声明** ——
改名只改一处，不用改每个节点。本项目实际配置 [实测]：

```
全局参数：stat_year = 2026
          end_month = 10
          dry_run   = （空）
导出节点【入参】：空
导出节点【出参】：filePath（VARCHAR，value 留空）
```

日志里能看到替换成功：`[入参] stat_year = '2026'  end_month = '10'  dry_run = ''`。

优先级：**启动参数 高于 本地参数 高于 上游传入 高于 全局参数**。

- **坑一：在本节点又声明了同名入参。** 本地参数优先级更高，值留空就把全局值**盖成空**。
  既然用全局参数，节点上就别再声明。
- **坑二：在下游重复声明上游的 OUT 参数。** 同上，本地那个空值会盖掉上游传下来的值。
  上游的 OUT 参数在下游**一个字都不要写**。

> 旧说法「全局参数要在本节点声明一条入参、value 填成全局参数的 key」**已被实测推翻**：
> 不声明就生效；反而声明了同名空入参会把值盖空。只有想在本节点覆盖全局值时才声明，且必须填值。

#### 空值的三种形态（自检必须都判）

| 形态 | 什么时候出现 |
|---|---|
| 字面量（没替换的占位） | 表里没有这个键（拼错、没配） |
| 空字符串 `""` | 配了但值为空（`dry_run` 这种「空 = 不干跑」的开关就是空串） |
| `null` / `None` | 上游 OUT 声明了但没发 `setValue`，或值为空 |

```python
PH = "$" + "{"          # 拼出来写，脚本里不留残缺的占位前缀


def is_blank(raw):
    t = (raw or "").strip()
    if not t:
        return True                       # 空串
    if t.startswith(PH):
        return True                       # 没替换
    return t in ("null", "NULL", "None", "undefined")


def pick(*cands):
    """按顺序取第一个「已替换且非空」的值；全空返回 None。"""
    for c in cands:
        v = (c or "").strip()
        if v and not v.startswith(PH):
            return v
    return None
```

两通道写法（同一份语义，参数名大小写写错也能救回来）：

```python
A = "${filePath}".strip()
B = "${filepath}".strip()
SRC = pick(A, B)
```

**必做**：每个入参都做未替换自检。未配置的参数会**原样留成字面量** `"${target_dir}"`，不会报错，只会静默出错。

```python
TARGET = "${target_dir}".strip()
if TARGET.startswith("${") or not TARGET:
    sys.exit(2)
```

**可选参数也要查**，否则"没配"会被当成默认值：

```python
RAW = "${recursive}".strip()
if RAW.startswith("${"):
    RECURSIVE = False          # 未配置
else:
    RECURSIVE = RAW in ("1", "true", "True")
```

**转换放代码里**：`int("${count}")`、`float("${rate}")`。

## 接上游出参（值来自上一个算子）

上游的 OUT 参数会像普通入参一样替换进脚本正文，**不需要在本节点再声明一遍**。
但它往往是 JSON，里面有双引号和反斜杠，用 `"${x}"` 会直接把脚本写坏。**一律用 `r"""`**：

```python
RAW = r"""${sqlresult}"""
if RAW.startswith("${") or not RAW.strip():
    print("错误: 上游出参 sqlresult 没传过来", file=sys.stderr)
    sys.exit(2)
```

- **三引号**：值里的 `"` 和换行都不会截断字符串
- **`r`**：保住 `\"` 里的反斜杠，否则 `json.loads` 会失败
- 自检仍然必须做（写法同普通入参）

**不要在【入参】里重复声明这个参数。** 参数优先级是
`启动参数 > 本地参数 > 上游传入 > 全局参数` —— 你在下游声明一个同名本地参数，
反而会拿本地那个值把上游传过来的盖掉。脚本里直接引用 `${名字}` 就行。

### 参数嵌套：参数值填「上游出参的名字」

有时入参要填的不是值，而是**上游出参的名字**（例如用户提示词来自上游 SQL 的结果列 `sqlresult`）。
DS 的 `${名字}` 替换器是 Spring `PropertyPlaceholderHelper`，它会把**占位符的名字再解析一遍**，
所以能用「占位套占位」：里层换成名字，外层再按这个名字取值。

**推荐双通道**：一路接上游名字，一路接字面量。两者互不干扰，失败也能被显式判出来。

```python
PROMPT_FROM = r"""${${user_prompt_from}}"""     # 名字再解析一遍，拿到上游的值
PROMPT_FROM_NAME = r"""${user_prompt_from}"""   # 名字本身：区分「没配」和「配了但没解析出来」
PROMPT_TEXT = r"""${user_prompt}"""             # 字面提示词

FROM_READY = not PROMPT_FROM_NAME.startswith("${")
PROMPT_SOURCE = ""
USER_PROMPT = ""

if FROM_READY:
    if PROMPT_FROM.startswith("${"):
        print("错误: user_prompt_from 填的是 %s，但嵌套没解析出来。" % PROMPT_FROM_NAME,
              file=sys.stderr)
        print("      检查三件事：①上游任务【出参】里确实有这个名字（大小写要一致）",
              file=sys.stderr)
        print("      ②本节点【入参】里没有再声明同名参数（会盖掉上游的值）",
              file=sys.stderr)
        print("      ③名字填裸名，不要写成带花括号的占位形式", file=sys.stderr)
        sys.exit(2)
    if not PROMPT_FROM.strip():
        print("错误: user_prompt_from 指向 %s，但取到的值是空的" % PROMPT_FROM_NAME,
              file=sys.stderr)
        sys.exit(2)
    USER_PROMPT = PROMPT_FROM
    PROMPT_SOURCE = "上游参数 " + PROMPT_FROM_NAME
elif not PROMPT_TEXT.startswith("${") and PROMPT_TEXT.strip():
    USER_PROMPT = PROMPT_TEXT
    PROMPT_SOURCE = "字面提示词"
else:
    print("错误: 用户提示词没配。给 user_prompt_from 填上游出参的名字，",
          file=sys.stderr)
    print("      或者给 user_prompt 直接写字面提示词，二者至少配一个", file=sys.stderr)
    sys.exit(2)
```

规则：

- 参数值填**裸名字**（`sqlresult`），不要填 `${sqlresult}` —— 后者走「值再解析」那条路，
  两种填法不能混用；混写（`${${sqlresult}}`）会拿到上游值再当名字查，查不到。
- **本节点不要再声明被引用的上游参数**（见上一节）。嵌套写法下更容易踩：参数框里填的正是那个名字，
  手容易顺带把它加成入参，上游值就被本地空值盖掉。
- 名字**逐字匹配**：大小写不符、多一个点都查不到。SQL 出参名在 PostgreSQL 里不加引号会被折成小写。
- **证据等级 ⚠️**：名字递归 / 值递归是 Spring 源码读法，**本环境尚未实测**。
  先跑一次验证探针：3 条 VARCHAR 入参（`probe_name` = 另一个参数名、`probe_payload` = 任意值、
  `probe_value` = 占位形态），脚本里分别用占位套占位和直接取值，看哪个等于 `probe_payload` 的值
  （探针按 `references/environment.example.md` 的建议自建）。`key_ok=True` 才能用双通道；只有值递归成立时退到
  「值里写占位形态」；两个都不成立就退回「上游落文件、下游读文件」。
- 只在「永远接上游」时用单通道极简：`USER_PROMPT = r"""${${user_prompt_from}}"""`，
  代价是字面提示词不能再填。
- 多行值的两个硬边界：值里不能有**连续三个双引号**，也不能以**单个反斜杠**结尾
  （`r"""..."""` 会直接 `SyntaxError`）。

## 出参：脚本侧

```python
print("${setValue(key=value)}")
```

规则：

- 一个 `setValue` 只放一个 `key=value`；要多个就分行发多次
- `key` 必须是**已声明的出参名**，否则值被丢弃
- 值里可以含空格、中文、引号、逗号、等号、斜杠（按第一个 `=` 切分）
- 值里含**换行**时要发 `repr(value)`，否则传不过去
- 同名 key 重复发是**覆盖**，不是追加
- 任务失败时不落库

### 出参名逐字匹配：`filePath` 和 `filepath` 是两个键

平台按键名**精确查表**，差一个大小写就取不到。本项目踩过的完整链条 [实测]：

1. 导出节点【出参】声明的是全小写 `filepath`；
2. 导出脚本只 `print("[出参] filePath = ...")` 打了给人看的日志，**没发 `setValue`**；
3. 于是下游 `prepareParamsMap` 里只有 `"filepath": {"direct":"OUT","value":null}`；
4. 上传算子读的是 `${filePath}` → 取不到 → 报「上游没传 filePath 过来」。

修法两条，缺一不可：

```python
# ① 脚本里真发 setValue（打在 print 里，平台从输出里取）
print("${setValue(filePath=%s)}" % PATH)
print("${setValue(filepath=%s)}" % PATH)      # 小写别名兜底

# ② 下游两个名字都读
SRC = pick("${filePath}", "${filepath}")
```

- 未声明的 key 是**静默丢弃**（不报错、任务照样成功），所以「两个名字都发」零成本；
- 值里有换行要发 `repr(value)`；
- 任务失败时不落库 —— 上游失败，下游永远读不到它的出参。

### 脚本 exit 0 **不等于**任务成功

DS 在脚本跑完之后还有一段"收尾"（`WorkerTaskExecutor.afterExecute`）：发告警 →
组装结果 → **遍历出参上传文件** → 清执行目录。**这段里抛异常，任务一样判 FAILURE**，
哪怕脚本是 exit 0、日志里所有输出都正常。

判断成败要看这一行：

```
Send task execute status: SUCCESS to master : ...
```

没有这行、或者出现 `Task execute failed, due to meet an exception`，就是收尾挂了。

实测踩到过：自定义算子注册出来的参数带 `"type":""`（空串），
枚举字段反序列化成 `null`，收尾里的
`property.getType().equals(DataType.FILE)` 直接 NPE
（`TaskFilesTransferUtils.getFileLocalParams`）。**规避：出参一个都别声明**，
空 `localParams` 会让那段直接 return，而 `setValue` 本来就会静默丢弃未声明的 key。

## SQL 算子：查询结果怎么给下游

**SQL 出参不是整个结果集，而是结果里的某一列。** 规则：

| 结果行数 | 出参类型 | 拿到的值 |
|---|---|---|
| 多行 | `LIST` | 该列所有值组成的 **JSON 数组字符串** |
| 多行 | 非 `LIST` | **拿不到**（不赋值） |
| 1 行 | 任意 | 该列的值（裸值，不是数组） |

**出参名必须和结果的列名（或别名）逐字一致。** 名字对不上**不报错**，
值会变成字符串 `"null"` —— 这是最常见的坑。

**不是"出参清单要跟 select 的列清单对齐"，是"一个出参去找一个同名列"**：

- 结果里没被出参点名的列 → **直接忽略**
- 出参点名了但结果里没这列 → 该出参**静默变成 `"null"`**
- 想要几列就声明几个出参（各自一个 JSON 数组），但下游得自己拼回去，**别这么干**

列名**区分大小写**。PostgreSQL 里不加引号的别名会被折成小写，
`as sqlresult` 配小写出参名；写成 `as "sqlResult"` 就对不上了。

多行 + `LIST` 时，列里的 **NULL 会变成字符串 `"null"`**（源码读法，未实测）——
NULL 和真的 `"null"` 分不开。这又是一个该走整行 JSON 的理由。

要整行导出，就把整行塞进一个列、并让它和出参同名：

```sql
select to_json(t)::text as sqlresult from 库.表 t
```

- 用 `to_json`，**别用 `to_jsonb`** —— jsonb 会按 key 长度重排列顺序
- 下游要同时认两种形状：多行是 JSON 数组，单行是裸对象
- 查询结果**最多 10000 行**（查询上限填 0 时的默认值），**静默截断**

## 从对象存储（MinIO）取数

算子的输入文件常放在对象存储上。取文件只用标准库 `urllib`，**不需要 boto3、不用装包**。

### 端点与端口

| 地址 | 是什么 | 用法 |
|---|---|---|
| `http://MINIO_HOST:9000` | S3 API | **取文件用这个** |
| `http://MINIO_HOST:9001` | 控制台网页 | 浏览器里看桶、传文件 |
| `:9002` | 业务那台 MinIO 上**拒绝连接**（DS 资源中心另有 9002，是另一套） | 不要用它取业务文件 |

**用错端口会拿到一整个 HTML 页面**：HTTP 200、内容是控制台首页，`openpyxl.load_workbook`
报「不是 zip」，非常容易误判成「文件坏了」[实测]。
所以下载完**先验内容、再交给解析器**（见下面的 `classify_blob`）。

### 对象键的编码

键里有中文、空格、破折号时，必须**按路径分段编码、保留斜杠**：

```python
import urllib.parse

KEY = "统计月报/2026年/1-10月—示例报表_20260318.xlsx"
URL = "http://MINIO_HOST:9000/template/" + urllib.parse.quote(KEY, safe="/")
```

`safe="/"` 不能省：整体 `quote` 会把 `/` 也编码成 `%2F`，S3 就找不到这个对象 [实测]。

### 匿名读

桶策略放开匿名 GET 之后，直接 `urlopen` 就行，不用 AccessKey / SecretKey [实测]：

```python
import urllib.request

with urllib.request.urlopen(URL, timeout=60) as r:
    data = r.read()
```

没开匿名读就让管理员给匿名 `s3:GetObject`（本项目没走签名）。

### 先分出「看着像成功」的几种错误

```python
MAGIC_ZIP = b"PK"      # xlsx 就是 zip
MAGIC_LT = b"\x3c"     # 尖括号的字节写法：转义写，避开脚本禁用字符


def classify_blob(data):
    """判断下回来的东西到底是什么。"""
    head = data[:200].lstrip()
    if head[:2] == MAGIC_ZIP:
        return "zip/xlsx"
    if head[:1] == MAGIC_LT:
        text = data[:2000].decode("utf-8", "replace")
        if "NoSuchKey" in text:
            return "NoSuchKey（对象键不对）"
        if "AccessDenied" in text:
            return "AccessDenied（没权限）"
        if "SignatureDoesNotMatch" in text:
            return "签名错（用了签名地址又改了参数）"
        if "DOCTYPE html" in text or "console" in text.lower():
            return "这是一个网页（端口选错了，9001 是控制台）"
        return "未知 XML 错误: " + text[:200]
    return "未知内容，前 16 字节: %r" % (head[:16],)
```

对应处置：

| 现象 | 原因 |
|---|---|
| `AccessDenied` | 桶 / 前缀没开匿名读，或用了别的账号；让管理员给匿名 `s3:GetObject` |
| `NoSuchKey` | 对象键不对（大小写、空格、全角破折号都要逐字抄） |
| 拿到 HTML | 端口用了 9001（控制台） |
| 连不上 | worker 到 MinIO 的网络 / 端口不通，先在 worker 上探 9000 端口 |

### 别用平台的「全局文件参数」当取数入口

本项目试过、放弃了 [实测]：

- 上传到「全局文件参数」后，拿到的只是**一个被改名后的文件名**（形如
  `e4ae16f48ff95f1d5aec1a82bec.xlsx`），不是路径、也不是内容；
- 任务日志里 `Download resources successfully:` 与 `Download upstream files: []` 都是空的；
- 真正能拿到内容的是 **MinIO 对象键**（本项目做法）或平台的 `dsTaskFile` 文件服务（走 HTTP）。

结论：**文件走对象存储，参数里只传「对象键」这种纯文本** —— 最透明、最好排错。

### 和 DS 资源中心的 MinIO 不是同一个

- DS 资源中心：S3 端点 `:9002`、bucket `test`，路径形如
  `root/resources/DATA_TRANSFER/日期/工作流Code/版本_实例ID/`；
- 业务文件桶（本项目）：S3 API `:9000`、bucket `template`。

两套别混：`FILE` 类型的参出参只对「把文件交给下游」有意义，【查看结果】里不会出现，
要出现必须调平台文件服务登记（见「导出文件的标准做法」）。

### 可复制的取数骨架

```python
import sys
import urllib.parse
import urllib.request

MINIO_HOSTS = ("http://MINIO_HOST:9000",)   # 按顺序试；9001 是控制台，别写进来
BUCKET = "template"
KEY = "统计月报/2026年/1-10月—示例报表_20260318.xlsx"
TIMEOUT = 120


def die(msg):
    print("错误: %s" % msg, file=sys.stderr)
    sys.exit(2)


def encode_url(host, bucket, key):
    return "%s/%s/%s" % (host.rstrip("/"), bucket, urllib.parse.quote(key, safe="/"))


def download(key, dest):
    last = ""
    for host in MINIO_HOSTS:
        url = encode_url(host, BUCKET, key)
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
                data = r.read()
        except Exception as exc:
            last = "%s 请求失败: %r" % (host, exc)
            print("[minio] %s" % last)
            continue
        kind = classify_blob(data)
        if kind != "zip/xlsx":
            last = "%s 回来的是 %s" % (host, kind)
            print("[minio] %s" % last)
            continue
        with open(dest, "wb") as f:
            f.write(data)
        print("[minio] %s  %d 字节" % (url, len(data)))
        return dest
    die("取不到对象 %s：%s" % (key, last))
```

要点：

- 落地名要给 `/data/` 下的**唯一名**；工作目录执行完会被清空；
- 拿到路径后按「导出文件的标准做法」发 `filePath` 出参，下游就接得上；
- 换环境只改 `MINIO_HOSTS` / `BUCKET` 两个常量；端口写错会一路走到「回来的是网页」。

## 导出文件的标准做法（**已跑通**）

要让人能在【查看结果】里下载产出文件，**拆成两个算子**：

```
SQL/业务算子  →  算子A（业务）              →  算子B（通用上传）
                 产出文件到 /data/outbox/      读路径 → 传平台文件服务 → 登记
                 出参 xlsxPath = 绝对路径
```

**为什么这么分**：取 token / 拼 multipart / 登记这段最容易写错，
收进算子 B 之后业务算子只管产出文件，换文件类型（csv / zip）也不用改 B。

**为什么不用海豚自带的 `FILE` 参数**：

| | 传到哪 | 【查看结果】读吗 |
|---|---|---|
| 海豚 `FILE` 出参 | DS 资源中心 `DATA_TRANSFER/日期/工作流Code/版本_实例ID/` | **不读** |
| 平台的 `dsTaskFile` | 平台文件服务 | **读** |

实测：`FILE` 出参确实传成功了（`Upload output files: [...] successfully`，
落到 `test/root/resources/DATA_TRANSFER/...`），但【查看结果】**仍然空白**。

- **`FILE` 出参**：能用，但只对"把文件交给下游"有意义。`value` 填**相对执行目录**
  的路径，文件不存在会让任务**失败**。
- **`FILE` 入参**：**3.2.2 里是坏的，别用。** `downloadUpstreamFiles` 在下游 varPool
  里按 `direct=IN` 过滤，而上游传下来的 varPool **全是 `direct=OUT`**
  （`mergeVarPool` 只留 OUT），map 恒空 → 抛 `Can not find upstream file`。
- **两个算子之间传文件**：走**共享目录**。上游写到 `/data/` 下的唯一文件名，
  把**绝对路径**当普通 VARCHAR 出参传下去，下游直接读。
  （前提是两个算子跑在同一个 worker 上 —— standalone 就是。多 worker 就不成立了。）

### 把上传算子固化成常用算子

**整个接口只有一条约定：上游出参必须叫 `filePath`（类型 `VARCHAR`，值是文件绝对路径）。**

约定死这一个名字，上传算子就再也不用改：

| 业务算子要做的 | 做法 |
|---|---|
| 产出文件（写 `/data/outbox/` 下的唯一名） | — |
| 把路径发下去 | 出参栏加 `filePath`；脚本里 `print("${setValue(filePath=%s)}" % PATH)` |
| 接到上传算子后面 | 前置任务连线，完事 |

上传算子这一侧：

- **入参 0 个** —— `filePath` 是上游出参，会自动替换进来
- **出参默认一个都别加。** 这个算子的职责在"传完"那一刻就结束了，出参是给下游用的；
  没人用就是纯累赘。`setValue` 对未声明的 key 静默丢弃，任务照样成功 ——
  **所以它是真正的「零参数」算子，贴上去就能跑。**
- **只有下游真要用时才加，而且只加要用的那个。** 常见是 `fileToken` ——
  比如后面还要把它写进业务表。加了之后必须确认注册出来的参数 **`type` 不是空串**，
  否则 worker 收尾会 NPE（见前面「脚本 exit 0 不等于任务成功」）。
- 文件类型不用管，脚本按后缀自己识别（xlsx / csv / zip 都行）
- 换环境只改脚本顶部三个常量：`BASE_URL` / `APP_KEY` / `APP_SECRET`

> 注意：`filePath` 依赖"同一个 worker 上的共享目录"。standalone 只有一个 worker，成立；
> 将来多 worker 就得改成走对象存储中转，这条约定才继续有效。

`/data/outbox/` 会一直涨（每个实例留一个文件）。要么定期清，要么在上传成功后
`os.remove(SRC)` —— 想留着排查就先别删。

### 算子 B：三步调平台文件服务

```
① 取 token   POST 平台/api/authserver/app/getToken
                json {"appKey": "...", "appSecret": "..."}
                ← {"success":true,"code":20000,"message":"SUCCESS",
                   "data":{"expireTime":...,"token":"eyJ..."}}

② 传文件     POST 平台/api/filejava/Services/ServiceFDFS
                multipart: action=upload, articleid=SJZT_SYSTEM, file=文件内容
                超时要放大（jar 用 600000）
                ← 要求 success 为真且 code==20000，取 data 作为 fileToken

③ 登记       POST 平台/api/java-dolphin-wrap/dsTaskFile/saveFileInfo
                json {projectCode, processCode, processInstanceId,
                      taskInstanceId, taskCode, fileName, fileToken,
                      fileSize, fileType, type}
                ← code==20000 才算成功
```

- token **原样**放进 `Authorization` 头，**没有 `Bearer ` 前缀**
- `type` 写死 `"file"`；`fileType` 给真实后缀（xlsx / zip / csv）
- **第 ③ 步才是让它出现在【查看结果】里的那一步**，只做完 ② 不算
- 纯标准库 `urllib` 就够，multipart 手搓约 20 行，不用引第三方包

⚠️ **判成功必须归一化类型。** 接口回的 `code` 是**数字** `20000`。
参照实现是 Java，`getStr("code")` 会把数字转成字符串；Python 的 `!=` 不会，
`20000 != "20000"` 会**把成功的响应判成失败**。`success` 同理（`true` 或 `"true"`）。

```python
if str(j.get("code")) == "20000":      # 对
    pass

if j.get("code") == "20000":           # 错，永远不成立
    pass
```

### 那 5 个 ID 从哪来

`${system.project.code}` 这类**在脚本里不会被替换**（见前面的「入参：脚本侧」）。
`${projectCode}` 这类短名只有**平台用「启动参数」启动**时才有，手工跑没有。

**兜底：执行目录路径里白送 4 个**

```
/tmp/dolphinscheduler/exec/process/root/171431627380672/186911950210240_11/2106/3560
                                     └projectCode────┘ └processCode──┘ └ver┘└procInst┘└taskInst┘
```

```python
parts = os.getcwd().replace("\\", "/").rstrip("/").split("/")
# parts[-4]=projectCode  parts[-3]="processCode_版本"
# parts[-2]=流程实例id     parts[-1]=任务实例id
```

先取 `${projectCode}` 这类短名，取不到再落到这条。

**`taskCode` 不在路径里**，先发 `"0"` —— 实测**不影响**文件出现在【查看结果】里。

## 常用代码片段

**依赖安装**

已装的包**留在环境里，下次执行不用重装**。所以标准写法是两段：

> ① 开头**只检查**（`find_spec`，毫秒级，不联网、不加载）
> ② 缺了才装（一次装齐）；业务代码里正常 `import`

```python
import importlib.util as u
import subprocess
import sys

# (pip 包名, 版本, import 名) —— 第三个必须写，且必须是能 import 的名字
# 例：pip 叫 psycopg2-binary，import 却叫 psycopg2
DEPS = [
    ("pandas", "2.5.4", "pandas"),
    ("pyarrow", "26.0.0", "pyarrow"),
    ("psycopg2-binary", "2.9.13", "psycopg2"),
]


def check_deps(mods):
    """只检查，不导入、不联网。返回装完仍缺的 import 名。"""
    missing = [m for m in mods if u.find_spec(m[2]) is None]
    if not missing:
        print("[deps] 依赖已就绪")
        return []
    pkgs = ["%s==%s" % (m[0], m[1]) for m in missing]
    print("[deps] 缺少 %d 个，安装: %s" % (len(pkgs), " ".join(pkgs)))
    p = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-input",
         "--disable-pip-version-check", "--no-warn-script-location"] + pkgs,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
    if p.returncode != 0:
        print(p.stdout.decode("utf-8", "replace")[-2000:], file=sys.stderr)
        sys.exit(2)
    return [m[2] for m in missing
            if u.find_spec(m[2]) is None]


# ---------- 开头：只检查 ----------
still = check_deps(DEPS)
if still:
    print("[deps] 安装后仍缺失: %s" % still, file=sys.stderr)
    sys.exit(2)

# ---------- 业务代码里正常 import ----------
import pandas as pd
import pyarrow.parquet as pq
```

要点：

- 检查开销可以忽略（毫秒级）；`import pandas` 那 600 ms 是**业务代码本来就要付的代价**，别算在检查头上
- **不要用 `import` 做检查**，也不要把 `import` 塞进 `check_deps` —— 用不到的包也会被整个加载
- **缺包时一次装齐**，不要逐个装（pip 自身启动就要 300+ ms）
- 版本号**必须钉死**，否则不同算子会互相覆盖同一个包

**读写 Parquet / 对象存储**（推荐路线，不用 Spark）

```python
import pyarrow as pa, pyarrow.parquet as pq, pyarrow.fs as pafs

s3 = pafs.S3FileSystem(access_key="...", secret_key="...",
                       endpoint_override="S3_ENDPOINT_HOST:9002", scheme="http")
with s3.open_output_stream("test/warehouse/out.parquet") as f:
    pq.write_table(pa.table({"id": [1, 2]}), f)
```

**写 xlsx**：用 `openpyxl`（纯 Python，装得上）。工作目录会被清空，
输出目录要给 `/data/` 这种持久路径，并把路径用出参发出去。

**调 Spark**（需要分布式计算时才用）

```python
import os, subprocess
env = os.environ.copy()
env["PYSPARK_PYTHON"] = "/usr/bin/python3"
env["PYSPARK_DRIVER_PYTHON"] = "/usr/bin/python3"
subprocess.run(["/path/to/spark/bin/spark-submit", "job.py"], env=env, timeout=1800)
```

**查 DS 元数据库**

```python
import psycopg2
conn = psycopg2.connect(host="PG_HOST", port=5432, dbname="DBNAME",
                        user="postgres", password="见配置文件", connect_timeout=5)
cur = conn.cursor()
cur.execute("select state, var_pool from dolphinscheduler.t_ds_task_instance where id = %s",
            (task_id,))
```

## 路径与存储

| 路径 | 位置 | 可写 |
|---|---|---|
| `/data/` | 容器本地磁盘，约 128 GB 可用 | ✅ 中间结果首选 |
| 容器本地 `/tmp` | 内存盘，执行结束即失 | ✅ 但易失 |
| `/dev/` | 对象存储 | ✅ 持久 |
| `/warehouse/` | 对象存储（Iceberg 仓库） | ✅ 持久 |
| `/tmp/` | HDFS | ✅ |
| `/user/` | HDFS | ✅ |
| `/export/` | 与系统盘同盘，仅约 34 GB 可用 | ⚠️ 别放数据 |

**未显式挂载的路径会落到对象存储。** 对象存储上：`rename` 不是原子操作、不能追加写、小文件 `list` 慢。

## 容易踩的坑

1. **依赖没装**：默认环境除 pip 外什么都没有，必须自己装并**钉死版本**。
2. **参数没配**：占位符原样保留成字符串，不报错。
3. **出参没声明**：`setValue` 静默失效，`var_pool` 为空。
4. **SQL 出参名不等于列名**：值静默变成字符串 `"null"`。
5. **接上游出参用了 `"..."`**：值里的引号把脚本写坏，报 SyntaxError。
6. **在下游重复声明同名参数**：本地值把上游传过来的盖掉。
7. **靠工作目录传文件**：执行结束目录被清空。要跨算子传就写 `/data/` 并把路径当出参发。
8. **以为 `${system.*}` 能用**：脚本里取不到，静默留成字面量。
9. **移植 Java 判等逻辑**：`getStr()` 会转类型，Python 不会。`code` 一律 `str()` 归一化。
10. **用 Spark 忘了指定解释器**：默认 Python 3.14 会直接失败，必须 `PYSPARK_PYTHON=/usr/bin/python3`。
11. **没设超时**：平台不设超时，死循环会永久占住执行器。
12. **写死 `python` 命令**：环境里有多套 Python，用 `sys.executable`。
13. **往 `/export` 写大数据**：和系统盘同盘，空间小。
14. **注释里写了可解析的占位样例**：注释不豁免替换，多行值会把注释撑断 → `SyntaxError`。
15. **参数嵌套的两种填法混用**：键级嵌套要填裸名；填成 `${名字}` 会拿到上游值再当名字查 → 查不到。
16. **数据视图 `code` 也是数字 `20000`**：与平台文件服务同源，`str()` 归一化再判，`success` 一起判。
17. **接口注入的 `rows` 字段**：每行都带行号 `rows`，不丢会让表头多一列、按列名取值也可能取到它。
18. **把 `size` 当本页行数**：`size` 是 pageSize；末页判断用「本页行数 != size」或「累计到 total」。
19. **JSON 列被包装**：平台把 JSON 列包成 `{"type":"json","value":"..."}`（可多层），要递归剥壳。
20. **参数空值报 PG 转型错**：`invalid input syntax for type integer: ""` 是参数空不是 SQL 错；注册配默认值 + 核对 `queryParamList`。
21. **全局参数又在节点上声明了一遍**：本地空值把全局值盖成空串。用全局参数就别在节点声明。
22. **把 MinIO 控制台端口当 S3 端口**：`:9001` 回来的是 HTML（200 状态码），解析器报「不是 zip」；取数用 `:9000`。
23. **对象键整体 `quote`**：`/` 变 `%2F` → `NoSuchKey`。要 `quote(key, safe="/")`。
24. **用「全局文件参数」传文件**：拿到的只是个改名后的文件名，不是路径也不是内容。文件走对象存储，参数只传对象键。
25. **出参名大小写差一个**：`filePath` 和 `filepath` 是两个键，下游读到 `null`。发 `setValue` 时两个名字都发。

---
