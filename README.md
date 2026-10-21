# dsh-dolphinscheduler-operator

为 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（dsh）准备的插件包：
把「DolphinScheduler Python 算子」的编写规范 skill 与配套的 **「海豚算子构建」Agent 模式**一起交付。

> A DeepSeek Harness bundle that ships a DolphinScheduler Python-operator skill and a matching agent preset.

## 包含什么

| 组成 | 说明 |
|---|---|
| Agent 模式 `dolphinscheduler` | 显示名「海豚算子构建」。工具集对齐内置 Standard 模式（文件读写/搜索、shell、job、schedule、skill、goal、plan、compaction、subagent、workflow、web、todo、ask_user、present），persona 改为海豚算子专家，并要求动手写算子前先加载 skill。 |
| Skill `dolphinscheduler-python-operator` | 海豚调度（DolphinScheduler 3.2.2）Python 算子编写规范 + 入参/出参填写指导，含参数嵌套取值（入参填上游出参名字）与注释不豁免替换等实战陷阱；自带交付前占位符渲染自检工具；末尾规定最终交付清单（脚本 / 参数表 / 推荐仓库名 / 仓库描述 / 提交注释）。由 `lib/index.js` 从包内 `assets/skills/` 直接注册，不依赖 `~/.dsh/skills`。 |
| 环境报告模板 | `assets/skills/dolphinscheduler-python-operator/REFERENCE.example.md`，说明如何为你自己的调度集群补一份 `REFERENCE.md`。 |

## 安装

前置：DeepSeek Harness（在 `0.2.1-rc.2` desktop profile 上验证）。

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
  注释不豁免替换等实战陷阱、常见错误与排查路径等。
- 最终交付：一次算子交付的回复固定包含 ① 算子脚本 ② 入参/出参表
  ③ 推荐仓库名（统一 `dolphinscheduler-` 前缀，如 `dolphinscheduler-llm-operator`）
  ④ 仓库描述 ⑤ 本次提交的 comment（conventional commit）。
- 交付前自检：`assets/skills/dolphinscheduler-python-operator/tools/render_placeholders.py`
  按 Spring 语义把算子脚本渲染一遍再编译，顺带扫 `>` `<` `&`，能复现「注释里的占位样例
  被多行值撑断 → SyntaxError」这类肉眼漏掉的问题（`--self-test` 可先自检工具本身）。
- 环境细节（你的集群的地址、配额、组件版本）由 `REFERENCE.md` 提供，见下节。

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
  20.2 K 字符，按标准阈值加载后会被裁到 4 K 头 + 1 K 尾，长会话里模型可能丢失算子规则。
  这里保留裁剪器但把阈值调到 24576 字符（头 16384 / 尾 2048）。
- **模式专属**：skill 与 persona 只在「海豚算子构建」模式下生效，不影响 Standard 等其它模式。
- **无第三方运行时依赖**：`lib/index.js` 只用 Node 内置模块，安装时无需构建。

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
```

## 更新与卸载

- 更新：`git pull`，然后重启 dsh 或 remove + install bundle 重新激活。
- 卸载：

  ```text
  plugin_manager(action: "remove_bundle", target: "@local/dsh-dolphinscheduler-operator")
  ```

## License

[MIT](LICENSE) © 2026 kkomia
