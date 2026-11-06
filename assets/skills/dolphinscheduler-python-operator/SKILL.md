---
name: dolphinscheduler-python-operator
description: 在海豚调度（DolphinScheduler）的 Python 算子节点上编写脚本、并指导填写算子【入参/出参】设置。当需要生成或审查一段能在该算子环境里正常运行的 Python 脚本时使用；也用于从平台「数据视图」的 HTTP 接口取数、配置视图参数（@where / 查询参数 / where 配置）与排查视图取数报错，以及回答"参数怎么填""类型下拉选什么""value 要不要填""出参为什么没值""SQL 的查询结果怎么传给下游""产出文件怎么让人在查看结果里下载""脚本为什么报 ModuleNotFoundError / 路径找不到""参数能不能引用另一个参数名（参数嵌套取值）"这类问题。
---

# 海豚 Python 算子

在这个环境里写 Python 算子，或指导填算子的入参/出参。

## 网络边界：内网地址不要在互联网环境里请求

本 skill、`REFERENCE.md` 与平台文档里出现的**所有 IP 和主机名都是内网地址**——例如 `23.36.2.60`、`23.26.x.x` 这类平台地址，以及 `10.x`、`192.168.x`、`172.16–31.x`、`100.64.x` 等私有网段。

- 内网地址**只能在内网环境访问**（算子的执行容器 / 平台侧）；当前对话所在的互联网环境**访问不到**；
- 因此**不要去请求、探测或做连通性测试**：不要用 `web_fetch`、`curl`、`urllib`、`ping`、`telnet` 去连这些地址，也不要为了「验证接口通不通」而发请求；
- skill 里的示例地址当**占位符**用：写进算子脚本可以（脚本跑在内网），但**自己不要去连**；
- 要验证接口或取数，交给算子在平台上跑，或让用户在内网执行；报错按下面的排查表分析，不要靠联网试探。

## 速查

| 项 | 值 |
|---|---|
| 解释器 | `/opt/python/bin/python3`（Python 3.14，除 pip 外无第三方包） |
| 装包 | `pip install 包名==版本`（包源已配好，无需参数） |
| 工作目录 | 每次执行后**被清空**，不能跨算子传文件 |
| 大数据中间结果 | 写 `/data/`（约 128 GB 可用） |
| 跨算子传数据 | 走**出参**；或写 `/dev/`、`/warehouse/`（对象存储） |
| 入参 | 脚本里写 `${参数名}`，界面里加同名 IN 参数 |
| 接上游出参 | `RAW = r"""${参数名}"""`，**别用** `"..."` |
| 参数嵌套 | 入参里填上游出参的**名字**，脚本写 `r"""${${名字}}"""`（⚠️ 源码读法，待实测） |
| `system.*` | 脚本里 `${system.xxx}` **不会被替换**，别指望 |
| 执行目录 | `os.getcwd()` 路径里编着 projectCode / 工作流code / 两个实例 id |
| 出参 | `print("${setValue(key=value)}")`，key 须先在界面声明为 OUT |
| SQL 出参 | 出参名必须**等于查询结果的列名（或别名）** |
| 脚本字符 | **不要出现 `>` `<` `&`**（粘贴链路会转成 HTML 实体，见下） |
| 失败 | `sys.exit(非0)` |
| Spark | 需 `PYSPARK_PYTHON=/usr/bin/python3`，否则失败 |
| 超时 | 平台不设超时，**必须自己给外部调用加 timeout** |
| 数据视图取数 | `POST 平台/api/.DataView/view/v1/sql/resultAppend`，body `{pageNumber, pageSize, queryParamList, viewId}`，**不需要鉴权头** |
| 内网地址 | 本 skill / `REFERENCE.md` 里的 IP 与主机名**全是内网**（如 `23.36.2.60`），互联网环境访问不到，**不要主动请求** |
| 视图参数 | 注册页配 `年份` / `月份`（必填 + 默认值），where 配置三条；空值会报 PG 整数转型错 |
| 接到视图 | 请求体 `queryParamList=[{"年份":"2026"},{"月份":"10"}]`，参数名逐字一致；多视图可共用一套 |
| 算子依赖视图 | 交付物多一样「视图注册清单」（视图名 / SQL 文件 / 参数 / where / viewId） |

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

**交付前自检（可选，需本机有 Python）**：在 skill 目录下用
`tools/render_placeholders.py` 按 Spring 语义把脚本渲染一遍再编译，顺带扫 `> < &`。
能抓住「注释被多行值撑断」这类肉眼漏掉的问题：

```powershell
python tools\render_placeholders.py 算子脚本.py --params 参数.json --check
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
| 全局参数 / 工作流级参数 | **要写**，且本地参数的值填成全局参数的 key |
| `system.*`（项目/工作流/任务 ID、业务日期） | **写了也取不到**，见下 |

**上游出参为什么千万别写**：优先级是
`启动参数 本地参数 上游传入 全局参数` —— 本地参数更高。
在下游再声明一个同名的空参数，就把上游传下来的值**盖成空**了。
（实测：某任务的 `localParams` 里没有 `org_code`，脚本里 `${org_code}` 照样被替换。）

**`system.*` 是个陷阱**：它们在 `prepareParamsMap` 里**有键有值**，
但脚本里 `${system.project.code}` **不会被替换**（实测两次）。`参数1` 这类
全局参数同样不替换。**要什么值，就让上游用出参传下来，或者自己声明一个带值的入参。**

> 过滤发生在哪一层**尚未定位**——`PropertyPlaceholderHelper` 通读过，
> 对占位符名字没有任何字符限制。按实测用就行，别去推导。
>
> 例外：**平台用「启动参数」启动工作流时**，`${projectCode}` 这类短名是能拿到的。
> 手工从 UI 点运行就没有。兜底办法见「那 5 个 ID 从哪来」。

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
  （`REFERENCE.md` 附录 C 有现成的）。`key_ok=True` 才能用双通道；只有值递归成立时退到
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

## 从平台数据视图取数（内网）

算子的数据不一定连库或读文件：很多内网环境把口径放在**平台「数据视图」**里（视图配 SQL + 参数），算子用 HTTP 取回结果集自己渲染。契约如下（本项目内网 `[实测]`）：

> 本节示例里的 `API_BASE`、host 与 IP 都是**内网地址**（如 `23.36.2.60:8998`）：只能在算子的内网执行环境里访问，当前互联网环境访问不到，**不要请求或探测**（见「网络边界」）。

### 接口事实

| 项 | 值 |
|---|---|
| 方法 / 路径 | `POST` `/api/.DataView/view/v1/sql/resultAppend`（大小写、点号照抄） |
| 请求体 | `{pageNumber, pageSize, queryParamList, viewId}` |
| 鉴权 | **不需要**鉴权头，不要 token |
| 响应 | `success` / `code` / `message` / `data.current`、`size`、`total`、`list` |
| 换环境 | 只改 `API_BASE`（形如 `http://PLATFORM_HOST:8998`） |

6 个容易误判的点：

1. `code` 是**数字** `20000`，不是字符串 —— 先 `str(doc.get("code")) == "20000"` 归一化再判；`success` 也要判（`true` / `"true"` 都可能）。与平台文件服务那条坑同源。
2. 行在 `data.list`，分页元数据在 `data.current / size / total`。`data` 直接是数组、或行列表在 `data.rows`，都是兜底形态（按平台行为推断，**本项目未实测**），代码留分支即可。
3. `size` 是每页条数，不是本页行数 —— 末页用「本页行数 != size」判断，别拿 `size` 当本页条数。
4. 每行的 `rows` 是接口注入的行号，业务代码必须丢掉，否则表头多一列、按列名也可能取到它。
5. 列集合随视图不同，**列名就是视图 SQL 的别名**：一律按列名取值，不按列位置、不写死列数。
6. 接口**只读**：数据视图能查询不能写库；要写库另走 SQL 算子或接口。

### 视图参数：三处都要配

平台把「视图参数」拆成三个地方，只配一处不生效：

| # | 位置 | 写什么 | 不写会怎样 |
|---|---|---|---|
| 1 | 视图 SQL 里 | 只留**一行** `    @where`（4 空格缩进、全文唯一）；SQL 末尾**不加分号**，一个文件一条 SELECT | 参数没地方注入 |
| 2 | 注册页「查询参数」 | 参数名 / 必填 / 默认值（本项目 `年份`、`月份`，必填 + 默认值 2026 / 9） | 请求带参数会报「参数不存在 / 不能为空」；不配默认值，注册校验就拼空值报错 |
| 3 | 注册页「where 配置」 | 三条条件（见下） | 能出数但不过滤，等于取全量 |

**where 配置三条**（本项目统计视图统一写法，工程规划许可视图先验证通过，其余照抄）：

| 序 | 条件 |
|---|---|
| 1 | `年份 <= @年份` |
| 2 | `月份 <= @月份` |
| 3 | `年份 >= @年份-3` |

- 报表要算累计和同比，时间窗口是「统计年 - 3 到统计年」，必须用区间：只写 `年份 = @年份` 会只剩当年，累计、同比全错；月份同理必须 `<=`。
- 参数名用 SQL 暴露出来的列名（SQL 里取成 `年份` / `月份`，参数就叫这个），**逐字匹配**，中文、大小写、前后空格都算错；默认值只用于注册校验。
- 一个视图只能有**一个** `@where`（平台 where 配置只支持单占位）—— 合并视图方案的前提。

> 未验证：`@参数` 是否只在 `@where` 行生效、能否在 SQL 其它位置引用，本项目按「只在 where 行生效」用，没做过对照实验 `[推断]`；参数名是否必须与列名一致（本项目刻意一致）也未测 `[推断]`。

**空值坑（最常见的卡点）**

- 参数没给值 / 没配默认值时，平台会拼出 `年份 <= ''`，PG 报 `invalid input syntax for type integer: ""`；
- **这不是 SQL 写错了，是参数空值**：注册时先配默认值，算子侧确认 `queryParamList` 里确实带了这两个键；
- 若校验阶段强制用空值跑，兜底用空值安全写法：`年份 <= nullif(@年份::text, '')::int`、`月份 <= nullif(@月份::text, '')::int`、`年份 >= nullif(@年份::text, '')::int - 3`（本项目配默认值就过了，兜底写法未实测）。

### 运行期怎么传

```python
query_param_list = [{"年份": "2026"}, {"月份": "10"}]
```

- 一个参数一个单键对象，顺序不重要；值是**字符串**也认（PG 按列类型转型）`[实测]`；
- 多个视图可**共用同一套参数**（本项目 6 个视图共用 `年份` / `月份`）；
- 视图**没声明**这些参数（老视图、写死日期）时传参会报错 `[实测]` —— 脚本留开关（如 `VIEW_HAS_PARAMS`，老视图置 False 就不发参数）；
- 除时间外的业务条件也走同一个 `queryParamList`（例如 `[{"区县名称": "渝中区"}]`），按视图声明过的参数名传。

### 算子侧最小骨架

```python
import json
import sys
import time
import urllib.request

API_BASE = "http://PLATFORM_HOST:8998"   # 换环境只改这里
VIEW_ID = "视图页 F12 抄到的 viewId"
VIEW_IDS = {"工程规划许可": VIEW_ID, "竣工核实": ""}   # 多报表遍历它；空串 = 跳过
VIEW_HAS_PARAMS = True       # 老视图（没声明 年份/月份）置 False
PAGE_SIZE = 5000
MAX_PAGES = 20
EXPECT_COLS = 0              # 视图注册后填期望列数；0 = 不断言
EXPECT_ROWS = 0              # 期望行数；0 = 不断言
KEY_COLS = ()                # 关键列名，如 ("区县名称",)；空 = 不校验

URL = API_BASE.rstrip("/") + "/api/.DataView/view/v1/sql/resultAppend"


def die(msg):
    print("错误: %s" % msg, file=sys.stderr)
    sys.exit(2)


def post_view(payload, timeout=60):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json;charset=UTF-8")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def fetch_all(view_id, query_params, page_size=PAGE_SIZE, max_pages=MAX_PAGES):
    """按 viewId 翻页取全量；每页失败重试 3 次；返回去掉 rows 的业务行。"""
    rows = []
    for page in range(1, max_pages + 1):
        doc = None
        for attempt in range(1, 4):
            try:
                doc = post_view({"pageNumber": page, "pageSize": page_size,
                                 "queryParamList": query_params,
                                 "viewId": view_id})
                break
            except Exception:
                if attempt == 3:
                    raise
        if str(doc.get("code")) != "20000":
            raise RuntimeError("视图返回失败: code=%s message=%s"
                               % (doc.get("code"), doc.get("message")))
        if doc.get("success") in (False, "false", "False", 0, "0"):
            raise RuntimeError("视图 success=false: %s" % (doc.get("message"),))
        data = doc.get("data") or {}
        if isinstance(data, list):
            data = {"list": data, "size": len(data), "total": len(data)}
        batch = data.get("list")
        if batch is None:
            batch = data.get("rows") or []
        total = int(data.get("total") or 0)
        size = int(data.get("size") or 0)
        rows.extend(batch)
        if not batch or not size or len(batch) != size:   # 末页
            break
        if total and len(rows) != total:
            continue
        break
    return [{k: v for k, v in row.items() if k != "rows"}
            for row in rows if isinstance(row, dict)]


# ---------- 定时任务没人传参，默认取北京时间上个月 ----------
NOW = time.gmtime(time.time() + 8 * 3600)   # 北京时间；别用容器本地时区
STAT_YEAR = NOW.tm_year
END_MONTH = NOW.tm_mon - 1
if END_MONTH == 0:
    END_MONTH = 12
    STAT_YEAR = STAT_YEAR - 1
QLIST = [{"年份": str(STAT_YEAR)}, {"月份": str(END_MONTH)}]
if not VIEW_HAS_PARAMS:
    QLIST = []


try:
    rows = fetch_all(VIEW_ID, QLIST)
except Exception as exc:
    die("取数失败: %r" % (exc,))
if not rows:
    die("视图返回 0 行（先按默认参数在视图页预览，确认有数据）")
cols = list(rows[0].keys())
if EXPECT_COLS and len(cols) != EXPECT_COLS:
    die("列数不对: 期望 %d 实际 %d，前 30 列: %s"
        % (EXPECT_COLS, len(cols), cols[:30]))
if EXPECT_ROWS and len(rows) != EXPECT_ROWS:
    die("行数不对: 期望 %d 实际 %d" % (EXPECT_ROWS, len(rows)))
for col in KEY_COLS:
    if col not in rows[0]:
        die("识别不出列 %s，实际前 30 列: %s" % (col, cols[:30]))
print("[view] %d 行 / %d 列" % (len(rows), len(cols)))
```

要点：

- 配置区常量集中放顶部；每个请求带 `timeout`（平台不设超时），每页失败重试 3 次；
- 0 行、HTTP 非 200、接口报错、响应不是合法 JSON —— 都 `exit 2`，stderr 打原因（HTTP 失败可打响应前 300 字）；
- 按列名取值，加**列数 / 行数 / 列名**断言，视图配错当场暴露（列数少 = 输出列没全选或 viewId 指错）；
- 列名 = 视图 SQL 别名，**改别名等于改接口**，两边一起改；结果太大落 `/data/` 文件，出参只发 `filePath`。

### viewId 怎么来、什么时候要重新核对

- 数据视图页面**打开预览、按 F12**，从 `resultAppend` 请求的 payload 里抄 `viewId`（形如 `0d714714-...`）；
- 填进配置区（如 `VIEW_IDS` 字典：报表名 → viewId；没填的跳过并告警，全空 `exit 2`）；
- **改视图 SQL 重新保存后一般沿用原 viewId，但不保证** `[推断]` —— 改完重新抓一次对一遍；
- 保存**主文件**（带 `@where` 的那份），不是把 `@where` 换成固定条件的 `_本地验证.sql`；
- 输出列勾成子集时接口只返回那几列 —— **按整条 SQL 全列注册**，否则列数断言会挂。

### 合并视图：一行一个分析块（`[方案]`）

一个视图只有一个 `@where`，但可以返回多行、每行一个分析块：`块号 / 块名 / 数据`，`数据` 列是 JSON 数组；各块先归一化成 `src_all` 再统一 `@where` 过滤，所以 where 配置和统计视图一样。13 个分析块可合成 2 个视图（本项目第二期方案，**尚未实跑**），算子按块号把 JSON 拆回去。

代价：**JSON 列会被平台包一层** `[实测]`，实际拿到的可能不是裸 JSON，而是 `{"type": "json", "value": "[{\"a\": 1}]"}`，而且可能多层套娃。算子侧要递归剥壳：

```python
def unwrap_json(value):
    """平台把 JSON 列包成 {"type":"json","value":"..."}，可能套多层。"""
    for _ in range(5):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                return value
        if isinstance(value, dict) and "type" in value and "value" in value:
            value = value["value"]
            continue
        return value
    return value
```

### 内网探针：换环境先验四步

1. 视图页 F12 抄一个已注册视图的 `viewId`；
2. 用默认参数 POST 一次，记 `data.total`；
3. 换一组参数（如 2025 / 6）再 POST：`total` 变了 = 参数与 where 配置都生效；没变 = where 配置没生效；
4. 故意传空参数，确认能复现 `invalid input syntax for type integer: ""` —— 以后看到这个报错就知道是参数问题。

### 本节的未验证点（按推断用，别写成结论）

| 点 | 现状 |
|---|---|
| `@参数` 只在 `@where` 行生效？SQL 其它位置能否引用 | 按「只在 where 行生效」用，未做对照实验 `[推断]` |
| 参数名是否必须与 SQL 暴露的列名一致 | 本项目刻意一致；不一致能否跑未测 `[推断]` |
| `pageSize` / 单次返回行数 / 总行数是否有上限 | 本项目最大 44 行，没压测 `[推断]` |
| 给没声明参数的视图传多余参数：报错还是忽略 | 只确认「没声明就传参会报错」，多余参数未测 `[推断]` |
| 重保存视图后 viewId 是否一定不变 | 只观察到「一般沿用」`[推断]` |
| 请求是否需要 `Referer` / `User-Agent` | 本项目带上了；不带是否被拒未测 `[推断]` |
| 算子不需要数据库账号 | 依「只读视图、视图用注册账号权限」推断 `[推断]` |

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

`${system.project.code}` 这类**在脚本里不会被替换**（见上一节）。
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

---

# 算子参数怎么填（界面侧）

**参数表**交付时只给这张表，四列：参数名 / 类型 / 必填 / 填什么。

| 参数名 | 类型 | 必填 | 填什么 |
|---|---|---|---|
| target_dir | VARCHAR | 是 | 要检查的目录，如 `/data` |
| pattern | VARCHAR | 是 | 文件名通配符，如 `*.tar.gz` |
| recursive | VARCHAR | 否 | 填 `1` 含子目录；留空或 `0` 不含 |
| checkResult | VARCHAR | 出参 | value 留空，脚本写入 `true` / `false` |

上游算子单独一张表，同样四列。

**边界：视图参数不是节点入参。** 视图参数（`年份` / `月份`）配在**视图注册页**，节点入参可以另起英文名（`stat_year` / `end_month`），脚本里做映射；**两套别都配**，节点上再声明一遍中文参数只会绕晕自己。

**脚本已经处理掉的情况不要写进表里**（未配置会怎样、填错了会怎样、为什么不能那样填）。
那些属于脚本注释。表里只回答"填什么"。

## 写表规则

- **参数名**：英文小写+下划线，与脚本里 `${...}` / `setValue(...)` 逐字一致
- **类型**：入参出参**一律 `VARCHAR`**。值是被当文本替换进脚本的，脚本里拿到的都是字符串，
  类型转换交给脚本（`int("${count}")`）
- **必填/选填**：脚本里有 `startswith("${")` 兜底的写"否"，其余写"是"
- **接上游出参**：本节点不声明它，所以**本表里不出现**，只写在上游那张表
- 参数名和值都**不要含**引号、换行、`${}`、空格

## 两个易错点（写给自己，不进表）

- 出参必须真的加进【出参】栏，没加 = 脚本发了 `setValue` 也不落库
- SQL 算子的出参名**必须等于查询结果的列名（或别名）**，类型 `LIST`

## 排查对照

| 现象 | 原因 |
|---|---|
| 报 `ModuleNotFoundError` | 依赖没装，脚本里要 `pip install` |
| 脚本里出现 `${xxx}` 字面量 | 该参数没在入参里添加，或名字拼错 |
| 出参没值 | 出参没声明；或 key 拼错；或任务失败（失败不落库） |
| 上游出参收到 `null` | SQL 的出参名和列名不一致 |
| 上游出参收到空串 | 下游把同名参数又声明了一遍，本地值盖掉了上游值 |
| 上传算子报「没传 filePath 过来」 | 上游出参名不叫 `filePath`。检查上游【出参】栏和 `setValue` 里的名字，两头一起改 |
| 脚本 exit 0，任务却 FAILURE | 收尾阶段挂了。看有没有 `Send task execute status: SUCCESS`，以及 `Task execute failed` 后面的栈。自定义算子的 `"type":""` 会触发 NPE，出参别声明 |
| 自定义算子跑完必 FAILURE | 注册时参数类型留成了空串。把出参全删掉 |
| SQL 日志里看不出出参有没有生效 | **正常**。出参处理在打印 row 之后，SQL 日志里永远看不到。看【工作流实例】页面或下游任务的日志 |
| 接上游出参报 SyntaxError | 用了 `"${x}"`，应该用 `r"""${x}"""` |
| 结果文件找不到 / 【查看结果】是空的 | 只用海豚 `FILE` 出参是**不够的**，还得调平台文件服务登记（见「导出文件的标准做法」） |
| 接口明明返回成功了却判成失败 | `code` 是数字 `20000`，要 `str()` 归一化再比 |
| 脚本里 `${system.xxx}` 没被替换 | **正常**，系统参数在脚本里取不到。改用上游出参，或从执行目录路径解析 |
| Spark 任务报序列化错误 | 没设 `PYSPARK_PYTHON=/usr/bin/python3` |
| 任务一直不结束 | 平台无超时，自己没给外部调用加 `timeout` |
| 报「嵌套没解析出来」 | 参数值拼错 / 大小写不符 / 上游没发这个出参 / 本节点又声明了同名入参把它盖空 |
| 报「取到的值是空的」 | 上游 `setValue` 发的是空值（空值存成 `null`） |
| 报 `SyntaxError: invalid character`，位置在注释行 | 注释里写了可解析的占位样例，多行值把注释撑断 |
| 提示词里明明有占位形状却没被替换 | 那个占位符落在某段残缺 `${` 的扫描区间里，被跳过了 |
| 视图报 `invalid input syntax for type integer: ""` | 视图参数没给值 / 没配默认值，平台拼出 `年份 <= ''`。注册时配默认值，算子侧确认带了 `年份`/`月份` |
| 视图报「参数 X 不能为空」 | 请求没带该参数，或参数名不逐字一致 |
| 数据视图 `code=20000` 却判成失败 | `code` 是数字，要比 `str(code)`；`success` 也要判 |
| 视图返回 0 行 | where 把数据过滤光了 / 时间窗口不对；先用默认参数在视图页预览 |
| 某 sheet 列数不对 | 注册视图时输出列没全选，或 viewId 指错；按整条 SQL 重新注册 |
| 表头多一列 `rows` | 接口注入的行号字段，清洗时丢掉 |
| JSON 列读成 `{"type":"json","value":"..."}` | 平台包装，递归剥壳 |
| 改完视图 SQL 算子还取旧列 | 保存后 viewId 可能变，F12 重新抓 |
| 月初跑月份差一个月 | 容器时区不是北京时间，按 `time.time() + 8*3600` 算 |
| 老视图传参报错 | 视图没有 `年份`/`月份` 参数，脚本要能关掉传参 |

## 提需求时的模板

```
【要做什么】一句话，例如：把上游 SQL 的查询结果导出成 xlsx
【输入】
  - target_dir  要检查的目录     示例：/data
  - pattern     文件名通配符     示例：*.tar.gz
  - recursive   是否含子目录(1/0) 示例：1
  【类型全部填 VARCHAR】
【输出】
  - checkResult  true=有匹配文件，false=没有
  【类型填 VARCHAR，value 留空】
【上游出参】sqlresult  值留空，本节点不声明
【失败怎么办】目录不存在时：任务报错退出，还是记 false 继续？
```

---

# 最后交付给用户的内容

一个算子做完，**最终回复固定交付五样，缺一不可**；算子依赖数据视图时再加第 6 样：

| # | 交付物 | 形态 |
|---|---|---|
| 1 | 算子脚本 | Python 代码块，完整可粘贴；`>` `<` `&` 已扫过 |
| 2 | 入参/出参表 | 四列 Markdown 表；本节点一张，上游有出参就再加一张 |
| 3 | 推荐仓库名 | 一行文本 |
| 4 | 仓库描述 | 一段话，可直接粘进 Git 仓库的 description 栏 |
| 5 | 本次提交的 comment | conventional commit，可直接拿去 `git commit` |
| 6 | 视图注册清单 | 表格：视图名 / SQL 主文件 / 参数 / 返回行数×列数 / viewId；**仅当算子依赖数据视图时必交** |

仓库名、仓库描述、提交注释是**交给用户的信息**：除非用户明确要求，不要代为创建远程仓库或 push。

算子依赖数据视图时，第 6 样必交：`VIEW_IDS` 是硬编码的，视图没注册 / viewId 换了算子就是空转，清单让人能照着注册、照着核对：

| 视图名 | SQL 主文件 | 参数 | 返回行数 / 列数 | viewId |
|---|---|---|---|---|
| 行政审批处季报_工程许可证 | `工程规划许可.sql` | 年份 / 月份 | 44 行 / 155 列 | `0d714714-...` |

## 推荐仓库名

统一 **`dolphinscheduler-` 前缀 + 算子英文短名**：全小写、单词间用 `-`。例如：

| 算子 | 推荐仓库名 |
|---|---|
| 大模型调用 | `dolphinscheduler-llm-operator` |
| SQL 结果导出 xlsx | `dolphinscheduler-sql-to-xlsx-operator` |
| 文件上传 | `dolphinscheduler-file-upload-operator` |

- 前缀写全 `dolphinscheduler`，不要缩成 `ds-`（`ds-llm-operator` 这类名字不成体系，也看不出归属）
- 短名用英文讲"做什么"，不带日期、版本号、项目代号
- 一组配套算子（业务 + 上传）放同一个仓库时，用主算子的名字

## 仓库描述

一段话，可直接粘进仓库的 description 栏：**开头点明目标环境，中间讲入参到出参，结尾讲依赖与失败**：

```
海豚调度（DolphinScheduler 3.2.2）PYTHON 算子：{一句话做什么}。入参 {关键参数}，
出参 {关键出参}；{依赖：纯标准库，或钉死版本的 pip 包}，{失败语义：参数没配、
上游值为空、接口报错均 exit 2}。
```

- 公开仓库**不写**内网地址、主机名、数据库名、密钥；示例用 `{网关地址}` 这类占位
- 可选补一行标签：`dolphinscheduler` `python-operator` `{领域词}`
- 描述里出现的参数名、出参名必须与脚本、参数表逐字一致

## 本次提交的 comment

用 conventional commits，中文 subject + 三行要点正文：

```
feat: 新增{算子中文名}算子，{最关键的一个能力}

- 入参：{参数1} / {参数2} / ...（全部 VARCHAR）
- 出参：{出参1} / {出参2}（VARCHAR，value 留空）
- 失败：参数没配、上游值为空、接口报错均 exit 2，stderr 打原因
```

- 新算子用 `feat:`，修 bug 用 `fix:`，只动文档用 `docs:`
- subject 一句话说完"新增了什么算子、最关键的能力"，不要写"更新一下"这类空话
- 正文必带**入参 / 出参 / 失败语义**三块，以后 `git log` 就能看懂接口
- 一次提交一个算子；业务算子、上传算子分开提交时，各写各的 comment

## 最终回复的结构

```
【算子】{中文名}（{一句话能力}）
【脚本】{完整 Python 代码块}
【参数表】{四列：参数名 / 类型 / 必填 / 填什么}
【仓库名】dolphinscheduler-{短名}
【仓库描述】{一段话}
【提交注释】{conventional commit}
【视图注册清单】{视图名 / SQL 主文件 / 参数 / 返回行数×列数 / viewId}；依赖数据视图时必给
```
