---
name: dolphinscheduler-python-operator
version: 1.3.0
description: "Write, review, or fix Python operator scripts for DolphinScheduler 3.2.2 and fill in the operator's IN/OUT parameter table. Use when the user needs a runnable DolphinScheduler PYTHON task script, asks how to set operator parameters, why an OUT parameter has no value, how to pass SQL query results downstream, how to let users download produced files, why the script raises ModuleNotFoundError or cannot find a path, whether a parameter can reference another parameter name, or how to read platform data views over the HTTP API and configure view parameters (@where / query params / where config)."
description_zh: 海豚调度（DolphinScheduler）Python 算子的脚本编写与【入参/出参】设置指导；也用于从平台「数据视图」HTTP 接口取数、配置视图参数（@where / 查询参数 / where 配置）并排查取数报错。当需要生成、审查或修改一段要粘进海豚 Python 算子节点的脚本，或回答「参数怎么填」「类型下拉选什么」「value 要不要填」「出参为什么没值」「SQL 查询结果怎么传给下游」「产出文件怎么让人在查看结果里下载」「为什么报 ModuleNotFoundError / 路径找不到」「参数能不能引用另一个参数名（参数嵌套取值）」「数据视图怎么取数、viewId 从哪来、空值为什么报整数转型错」这类问题时激活。
user-invocable: true
---

# 海豚 Python 算子

海豚调度（DolphinScheduler 3.2.2）Python 算子的实战规则：脚本怎么写、参数表怎么填、出参怎么传、数据视图怎么取数。

**不要凭记忆作答。** 先判断任务类型，再用文件读取工具读对应的 reference 文件（路径相对本文件所在目录）。

| 任务 | 读这个文件 |
|---|---|
| 写 / 审查算子脚本：符号写法、脚本模板、入参读取、接上游出参、出参、SQL 算子、导出文件、常用片段、路径与存储、踩坑清单 | `references/operator-script.md` |
| 填【入参/出参】表、类型下拉、value 留空、报错排查、最终交付物（仓库名 / 描述 / commit comment） | `references/params-and-delivery.md` |
| 从平台「数据视图」取数：取数接口、`@where` / 查询参数 / where 配置三处参数、内网地址边界、取数排错 | `references/data-view.md` |
| 集群侧环境事实（解释器、pip、目录、权限、超时、平台版本） | 先看 `references/environment.md`；没有就以 `references/environment.example.md` 的 16 个方面去问用户或实测，**不要编造** |

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
| 参数嵌套 | 入参里填上游出参的**名字**，脚本写 `r"""${${名字}}"""`（源码读法，待实测） |
| `system.*` | 脚本里 `${system.xxx}` **不会被替换**，别指望 |
| 出参 | `print("${setValue(key=value)}")`，key 须先在界面声明为 OUT |
| SQL 出参 | 出参名必须**等于查询结果的列名（或别名）** |
| 脚本字符 | **不要出现 `>` `<` `&`**（粘贴链路会转成 HTML 实体，见 operator-script.md） |
| 失败 | `sys.exit(非0)` |
| Spark | 需 `PYSPARK_PYTHON=/usr/bin/python3`，否则失败 |
| 超时 | 平台不设超时，**必须自己给外部调用加 timeout** |
| 数据视图取数 | `POST 平台/api/.DataView/view/v1/sql/resultAppend`，body `{pageNumber, pageSize, queryParamList, viewId}`，**不需要鉴权头** |
| 内网地址 | 本 skill 里的 IP 与主机名**全是内网**（如 `23.36.2.60`），互联网环境访问不到，**不要主动请求** |
| 视图参数 | 注册页配 `年份` / `月份`（必填 + 默认值），where 配置三条；空值会报 PG 整数转型错 |

## 硬约束（交付前逐条过）

1. 交付脚本里**不出现** `>` `<` `&`：先落盘，再扫描（粘贴链路会把它们变成 HTML 实体，截断语句）。
2. 脚本里每个入参读取前做 `startswith("${")` 自检——未替换时会静默留成字面量，跑起来才炸。
3. 失败用 `sys.exit(非0)` 表达，别靠 `print` 报错；`stderr` 打原因。
4. 所有外部调用（HTTP、数据库、SSH）加 `timeout`——平台不设超时。
5. 出参必须先在界面声明为 OUT，否则 `setValue` 静默丢弃。
6. 数据视图响应里的 `code` 是**数字** `20000`，判等前先 `str()` 归一化。
7. 内网地址只写进脚本/文档当占位符，**不要自己发请求、探测或做连通性测试**。
8. pip 依赖钉死版本；超时/失败语义写进脚本头注释。
9. 交付脚本必须先存在于磁盘，再贴进对话——只贴对话、没落盘的代码扫不到。
10. 环境事实（解释器、目录、权限、超时）没实测就标 `[推断]`/`[未决]`，不要编。

## 交付前自检（本机有 Python 时）

本 skill 自带校验脚本，按 Spring 语义渲染占位符后再编译，能抓住「注释被多行值撑断」这类肉眼漏掉的问题：

```powershell
python scripts/render_placeholders.py 算子脚本.py --params 参数.json --check
```

- 检查三件事：模板里的 `>` `<` `&`、渲染结果的 `compile()`、渲染后残留的 `${...}`（仅告警）；
- 退出码：`0` 通过 / `1` 结构性问题 / `2` 参数或文件错误；
- 另可 `python scripts/render_placeholders.py --self-test` 先确认脚本本身可用。

## 交付给用户的内容

一个算子做完，最终回复固定交付这些（细节见 `references/params-and-delivery.md`）：

| # | 交付物 | 形态 |
|---|---|---|
| 1 | 算子脚本 | Python 代码块，完整可粘贴；`>` `<` `&` 已扫过 |
| 2 | 入参/出参表 | 四列 Markdown 表（参数名 / 类型 / 必填 / 填什么）；上游有出参再加一张 |
| 3 | 推荐仓库名 | 一行文本，`dolphinscheduler-{英文短名}` |
| 4 | 仓库描述 | 一段话，可直接粘进 Git 仓库 description |
| 5 | 本次提交的 comment | conventional commit |
| 6 | 视图注册清单 | 仅算子依赖数据视图时必交：视图名 / SQL 主文件 / 参数 / 返回行数×列数 / viewId |

## 工作方式

- 用户当场指示优先于本 skill；规范没覆盖的，沿用项目现有脚本风格。
- 公开或共享的内容不写内网地址、主机名、数据库名、凭据；示例用 `{网关地址}` 这类占位。
- 不要替用户建远程仓库或 push，除非用户明确要求。
- 结论标注证据等级：`[实测]` / `[推断]` / `[未决]`。
