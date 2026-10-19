---
name: dolphinscheduler-python-operator
description: 在海豚调度（DolphinScheduler）的 Python 算子节点上编写脚本、并指导填写算子【入参/出参】设置。当需要生成或审查一段能在该算子环境里正常运行的 Python 脚本时使用；也用于回答"参数怎么填""类型下拉选什么""value 要不要填""出参为什么没值""SQL 的查询结果怎么传给下游""产出文件怎么让人在查看结果里下载""脚本为什么报 ModuleNotFoundError / 路径找不到"这类问题。
---

# 海豚 Python 算子

在这个环境里写 Python 算子，或指导填算子的入参/出参。

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
| `system.*` | 脚本里 `${system.xxx}` **不会被替换**，别指望 |
| 执行目录 | `os.getcwd()` 路径里编着 projectCode / 工作流code / 两个实例 id |
| 出参 | `print("${setValue(key=value)}")`，key 须先在界面声明为 OUT |
| SQL 出参 | 出参名必须**等于查询结果的列名（或别名）** |
| 脚本字符 | **不要出现 `>` `<` `&`**（粘贴链路会转成 HTML 实体，见下） |
| 失败 | `sys.exit(非0)` |
| Spark | 需 `PYSPARK_PYTHON=/usr/bin/python3`，否则失败 |
| 超时 | 平台不设超时，**必须自己给外部调用加 timeout** |

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
                       endpoint_override="<s3-endpoint-host>:9002", scheme="http")
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
conn = psycopg2.connect(host="<postgres-host>", port=5432, dbname="<dbname>",
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

---

# 算子参数怎么填（界面侧）

交付时**只给这张表**，四列：参数名 / 类型 / 必填 / 填什么。

| 参数名 | 类型 | 必填 | 填什么 |
|---|---|---|---|
| target_dir | VARCHAR | 是 | 要检查的目录，如 `/data` |
| pattern | VARCHAR | 是 | 文件名通配符，如 `*.tar.gz` |
| recursive | VARCHAR | 否 | 填 `1` 含子目录；留空或 `0` 不含 |
| checkResult | VARCHAR | 出参 | value 留空，脚本写入 `true` / `false` |

上游算子单独一张表，同样四列。

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
