# dsh-dolphinscheduler-operator

为 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（dsh）准备的插件包：
把「DolphinScheduler Python 算子」的编写规范 skill 与配套的 **「海豚算子构建」Agent 模式**一起交付。

> A DeepSeek Harness bundle that ships a DolphinScheduler Python-operator skill and a matching agent preset.

同一套算子规则另有一份 **Qoder 插件**（同事用 Qoder 时装它），见 [`qoder-plugin/`](qoder-plugin/)。

## 包含什么

| 组成 | 说明 |
|---|---|
| Agent 模式 `dolphinscheduler` | 显示名「海豚算子构建」。工具集对齐 **dsh 0.2.2-rc.1 内置 Standard 模式**（文件读写/搜索、shell、job、schedule、skill、goal、plan、compaction、subagent、workflow、web、todo、ask_user、present），persona 改为海豚算子专家，并要求动手写算子前先加载 skill。 |
| Skill `dolphinscheduler-python-operator` | 海豚调度（DolphinScheduler 3.2.2）Python 算子编写规范 + 入参/出参填写指导，含参数嵌套取值（入参填上游出参名字）与注释不豁免替换等实战陷阱；**从平台「数据视图」HTTP 接口取数**（接口契约、翻页与 `rows` 清洗、视图参数三处配置、空值报错排查）与算子侧断言/默认时间窗口；自带交付前占位符渲染自检工具；末尾规定最终交付清单（脚本 / 参数表 / 推荐仓库名 / 仓库描述 / 提交注释，依赖数据视图时加视图注册清单）。由 `lib/index.js` 从包内 `assets/skills/` 直接注册，不依赖 `~/.dsh/skills`。 |
| 环境报告模板 | `assets/skills/dolphinscheduler-python-operator/REFERENCE.example.md`，说明如何为你自己的调度集群补一份 `REFERENCE.md`。 |

## 安装

前置：DeepSeek Harness `0.2.2-rc.1`（desktop profile 上验证）。`package.json` 里声明了
`engines.dsh: ^0.2.2-rc.1`，内核不匹配时 bundle 会被启动器跳过（不会报错，模式会静默消失）。

1. 克隆本仓库：

   ```powershell
   git clone https://github.com/kkomia/dsh-dolphinscheduler-operator.git
   ```

2. 在 dsh 中把 clone 后的目录作为本地 bundle 安装（`plugin_manager` 的 `install_bundle`）：

   ```text
   plugin_manager(action: "install_bundle", target: "<本仓库绝对路径>")
   ```

3. 刷新 dsh Web 页面，在 Settings 的模式列表（自定义组）中应看到「海豚算子构建」；
   新建会话时选择该模式即可。

安装后 profile 的 `package.json` 会以 `link:` 方式引用本仓库目录，所以更新本仓库文件后，
重启 dsh（或 `remove_bundle` 后再 `install_bundle`）即可生效。

## 使用

- 选择「海豚算子构建」模式后，模型在编写/审查算子脚本前会先调用 `skill` 加载
  `dolphinscheduler-python-operator`；也可以直接输入 `/dolphinscheduler-python-operator` 手动触发。
- skill 覆盖：解释器与装包、执行目录与存储语义、入参/出参写法、`setValue` 语法、
  交付脚本的字符限制（`>` `<` `&`）、参数嵌套取值（参数值填另一个参数名）、
  注释不豁免替换等实战陷阱、常见错误与排查路径，以及**从平台数据视图取数**：
  接口契约、翻页与 `rows` 清洗、视图参数（`@where` / 查询参数 / where 配置）、
  空值报错排查、算子侧默认时间窗口与列数/行数断言。
- 最终交付：一次算子交付的回复固定包含 ① 算子脚本 ② 入参/出参表
  ③ 推荐仓库名（统一 `dolphinscheduler-` 前缀，如 `dolphinscheduler-llm-operator`）
  ④ 仓库描述 ⑤ 本次提交的 comment（conventional commit）；算子依赖平台数据视图时
  再加第 ⑥ 样**视图注册清单**（视图名 / SQL 主文件 / 参数 / 返回行数×列数 / viewId）。
- **网络边界**：skill 与环境报告里出现的**所有 IP、主机名都是内网地址**（含 `23.36.2.60`、
  `23.26.x.x` 这类环境地址，以及 `10.x` / `192.168.x` / `172.16–31.x` / `100.64.x` 等私有网段）。
  它们只能在**海豚执行环境（内网）**访问，互联网环境访问不到——**不要**用 `web_fetch`、
  `curl`、`urllib`、`ping` 去请求或探测，也不要用联网来「验证接口通不通」。
- 交付前自检：`assets/skills/dolphinscheduler-python-operator/tools/render_placeholders.py`
  按 Spring 语义把算子脚本渲染一遍再编译，顺带扫 `>` `<` `&`，能复现「注释里的占位样例
  被多行值撑断 → SyntaxError」这类肉眼漏掉的问题（`--self-test` 可先自检工具本身）。
- 环境细节（你的集群的地址、配额、组件版本）由 `REFERENCE.md` 提供，见下节。

## Qoder 版

同一套算子规则也做成了一份 **Qoder 插件**，放在
[`qoder-plugin/dolphinscheduler-operator/`](qoder-plugin/dolphinscheduler-operator/)。
两版内容同源：入口 `SKILL.md` 只做任务分流，细节在 `references/`（脚本写法 / 参数与交付 /
数据视图取数 / 环境事实模板）与 `scripts/render_placeholders.py` 自检工具里。

- **装到 Qoder**：`Settings` → `Plugins` → 从本地文件夹导入，选
  `qoder-plugin/dolphinscheduler-operator/`；或把打包出的 zip 拖进 Qoder 聊天窗口说
  「安装这个插件」；CLI 为 `qoderclicn plugins install <zip 路径>`。
- **打包 zip**：`python qoder-plugin/build-zip.py`，产物
  `qoder-plugin/dolphinscheduler-operator-<version>.zip`，zip 根层直接是
  `.qoder-plugin/plugin.json`。
- **触发**：直接描述任务（如「帮这个算子写段 Python 脚本」），或 `/dolphinscheduler-operator`。
- **维护**：改规则时 DSH 版的
  `assets/skills/dolphinscheduler-python-operator/SKILL.md` 与 Qoder 版的
  `qoder-plugin/dolphinscheduler-operator/skills/dolphinscheduler-python-operator/references/`
  要一起改，并同步两边版本（`package.json` / `.qoder-plugin/plugin.json`）。

## 关于 `REFERENCE.md`

本仓库**不包含**任何真实环境报告：那是按具体集群实测出来的产物，通常含内网地址、
主机名、数据库名与凭据位置，不适合公开分发。仓库只提供
[`REFERENCE.example.md`](assets/skills/dolphinscheduler-python-operator/REFERENCE.example.md)
（15 个方面的写作清单，无具体值）。

需要时把你自己生成的报告放到：

```text
assets/skills/dolphinscheduler-python-operator/REFERENCE.md
```

然后重新激活插件。该文件已在 `.gitignore` 中，不会被误提交。`SKILL.md` 不依赖它，
缺少时 skill 仍可正常加载，只是少了环境细节。

## 与 `~/.dsh/skills` 下同名 skill 的关系

插件的 skill 以 **runtime 来源**注册进该 preset 的 skill-registry 层，同层内 runtime 来源
优先于用户目录来源，因此即使 `~/.dsh/skills/dolphinscheduler-python-operator/` 还在，
模式里生效的也是插件自带版本。把用户目录删掉后插件版本仍然可用。

## 有意的设计选择

- **调高 `tool-result-pruner` 阈值**：Standard 默认 `thresholdChars: 8192`，而本 skill 正文约
  2.97 万字符，按标准阈值加载后会被裁到 4 K 头 + 1 K 尾，长会话里模型可能丢失算子规则。
  这里保留裁剪器但把阈值调到 32768 字符（头 28672 / 尾 3072，内核要求
  `headChars + 标记 + tailChars <= thresholdChars`，标记 39 字符 → 31783 通过）。
- **与 Standard 的刻意差异**：`cordis.patch.yml` 的 preset 逐行对齐
  `@deepseek-ai/dsh-web-app/presets/standard.patch.yml`，只保留四处差异——persona 文案、
  `tool-result-pruner` 预算、多一行本包自带的 skill provider、preset 的 id/name/description/order。
  这样内核升级带来的工具增删只需跟 Standard 同步。
- **模式专属**：skill 与 persona 只在「海豚算子构建」模式下生效，不影响 Standard 等其它模式。
- **无第三方运行时依赖**：`lib/index.js` 只用 Node 内置模块，安装时无需构建。

## 内核版本适配

| 内核 | 本插件版本 | 适配内容 |
|---|---|---|
| `0.2.1-rc.2` | `1.2.0` | 首版：自带 skill provider + 海豚算子构建模式。 |
| `0.2.2-rc.1` | `1.3.0` | preset 对齐 Standard：`tool-subagent` 改用 `modelSelection` / `modelDiscovery`（旧键 `modelSelectionSettings` 被静默忽略）、`tool-fs` 关掉 `apply_patch`、`tool-plugin-manager` 按 `profileContext` 条件启用、删除内核已合并掉的 `tool-subagent-control/list-agents` 行；`package.json` 增加 `dsh.manifestVersion: 1` 与 `engines.dsh`；skill 补「从平台数据视图取数」。 |

升级内核后建议的验证顺序：`dsh --profile <临时 profile> --dump-config` 能组合出 preset →
在 App 的模式列表里出现「海豚算子构建」→ 新建该模式会话能正常加载 skill。

## 目录结构

```
dsh-dolphinscheduler-operator/
  package.json          # dsh.bundle.patch 指向 cordis.patch.yml
  cordis.patch.yml      # 插入 preset-dolphinscheduler（@deepseek-ai/dsh-agent-preset 实例）
  lib/index.js          # skill provider：读 assets/skills/ 并 ctx.skills.register
  assets/skills/dolphinscheduler-python-operator/
    SKILL.md            # skill 正文（公开）
    REFERENCE.example.md# 环境报告模板（公开）
    REFERENCE.md        # 你的环境报告（.gitignore，不提交）
    tools/
      render_placeholders.py  # 交付前自检：Spring 语义渲染 + 编译 + 禁用字符扫描
  locale/{zh,en}.json   # 插件展示元数据
  icon.svg              # 插件图标
  LICENSE               # MIT
  qoder-plugin/         # Qoder 版（同一套规则，可选）
    build-zip.py        # 打 zip：python qoder-plugin/build-zip.py
    dolphinscheduler-operator/
      .qoder-plugin/plugin.json
      skills/dolphinscheduler-python-operator/{SKILL.md,references/,scripts/}
```

## 更新与卸载

- 更新：`git pull`，然后重启 dsh 或 remove + install bundle 重新激活。
- 卸载：

  ```text
  plugin_manager(action: "remove_bundle", target: "@local/dsh-dolphinscheduler-operator")
  ```

## License

[MIT](LICENSE) © 2026 kkomia
