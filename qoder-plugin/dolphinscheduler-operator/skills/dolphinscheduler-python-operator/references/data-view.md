# 平台数据视图取数（内网）

## 网络边界：内网地址不要在互联网环境里请求

本 skill 与平台文档里出现的**所有 IP 和主机名都是内网地址**——例如 `23.36.2.60`、`23.26.x.x` 这类平台地址，以及 `10.x`、`192.168.x`、`172.16–31.x`、`100.64.x` 等私有网段。

- 内网地址**只能在内网环境访问**（算子的执行容器 / 平台侧）；当前对话所在的互联网环境**访问不到**；
- 因此**不要去请求、探测或做连通性测试**：不要用 `web_fetch`、`curl`、`urllib`、`ping`、`telnet` 去连这些地址，也不要为了「验证接口通不通」而发请求；
- skill 里的示例地址当**占位符**用：写进算子脚本可以（脚本跑在内网），但**自己不要去连**；
- 要验证接口或取数，交给算子在平台上跑，或让用户在内网执行；报错按 `params-and-delivery.md` 的「排查对照」分析，不要靠联网试探。

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
