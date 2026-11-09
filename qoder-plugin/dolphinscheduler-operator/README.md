# 海豚 Python 算子（Qoder 插件）

把海豚调度（DolphinScheduler 3.2.2）Python 算子的实战经验做成一个 Qoder 插件：写脚本、填【入参/出参】、把 SQL 结果和产出文件交给下游、以及从平台「数据视图」HTTP 接口取数，都能直接问、直接出可粘贴的结果。

## 装到 Qoder

三种方式，任选其一：

1. **IDE 导入本地文件夹**：Qoder → `Settings` → `Plugins` → 右上角从本地导入（`+ Create Plugin` → import），选本目录 `dolphinscheduler-operator/`。
2. **拖 zip 进聊天**：把 `dolphinscheduler-operator-1.3.0.zip` 拖进 Qoder 聊天窗口，说「安装这个插件」。
3. **CLI**：`qoderclicn plugins install <zip 路径>`。

装完在扩展视图里确认插件已启用；没生效就重载插件或重启 Qoder。触发方式：直接描述任务（如「帮这个算子写个 Python 脚本」），或输入 `/dolphinscheduler-operator`。

## 里面有什么

```
.qoder-plugin/plugin.json                 # 插件清单
skills/dolphinscheduler-python-operator/
  SKILL.md                                # 入口：任务分流 + 速查 + 硬约束 + 交付清单
  references/
    operator-script.md                    # 脚本侧：符号写法、模板、入参/出参、SQL 算子、导出文件、踩坑
    params-and-delivery.md                # 界面侧参数表、报错排查、仓库名/描述/commit、最终回复结构
    data-view.md                          # 平台数据视图取数接口、三处视图参数、内网地址边界
    environment.example.md                # 集群环境事实模板（16 个方面）
  scripts/
    render_placeholders.py                # 交付前自检：渲染占位符 + 编译 + 扫 > < &
assets/avatar.svg                         # 插件图标
```

入口 `SKILL.md` 刻意保持精简：先判断你要做的事，再让模型去读对应的 reference。这样触发快、细节也不丢。

## 用法示例

- 「写一段海豚 Python 算子脚本，扫 `/data` 下昨天的 tar.gz，结果用出参传给下游」
- 「这个算子的入参表怎么填？类型下拉选什么？」
- 「出参 print 了但下游取不到值，为什么？」
- 「SQL 算子的查询结果怎么传给下一个算子？」
- 「产出文件怎么让用户在【查看结果】里下载？」
- 「从平台数据视图取数怎么调？viewId 从哪来？为什么报 `invalid input syntax for type integer: ""`？」

## 交付前自检（可选，本机有 Python）

```powershell
python skills/dolphinscheduler-python-operator/scripts/render_placeholders.py 算子脚本.py --params 参数.json --check
python skills/dolphinscheduler-python-operator/scripts/render_placeholders.py --self-test
```

退出码 `0` 通过 / `1` 有结构性问题 / `2` 参数或文件错误。

## 环境事实

`references/environment.md` **不在插件里**（通常含内网地址、主机名、库名等内部信息）。需要集群细节时，按 `references/environment.example.md` 的 16 个方面自己实测一份，放回 `references/environment.md` 即可；skill 会自动优先读它。

## 网络边界

本插件里的所有 IP 和主机名（如 `23.36.2.60`、`23.26.x.x`，以及 `10.x`、`192.168.x`、`172.16–31.x`、`100.64.x` 等私有网段）**都是内网地址**，只能在算子的内网执行容器 / 平台侧访问。在互联网环境里**不要请求、探测或做连通性测试**；要验证接口，把脚本交给算子在平台上跑。

## 来源

规则来自真实算子交付与实测，与 DSH 版插件同源：<https://github.com/kkomia/dsh-dolphinscheduler-operator>（本插件位于该仓库 `qoder-plugin/` 子目录）。

## 维护

- 改脚本侧规则 → `references/operator-script.md`
- 改参数表 / 交付规范 → `references/params-and-delivery.md`
- 改数据视图接口或参数 → `references/data-view.md`
- 改完同步 `.qoder-plugin/plugin.json` 的 `version`，重新打包（zip 根层直接是 `.qoder-plugin/`）。
