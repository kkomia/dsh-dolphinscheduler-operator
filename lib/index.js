/**
 * Bundled skill provider + the `/custom-operator` command.
 *
 * The skill body and its REFERENCE.md live under `assets/skills/<name>/`, so the
 * bundle is self-contained: installing it ships the skill without depending on
 * anything under the user's DSH skills directory.
 *
 * The skill is registered through `ctx.skills.register` (runtime source) inside
 * the preset's standing composition, so it lands in that preset's skill-registry
 * layer and outranks a same-name copy discovered from `~/.dsh/skills`.
 *
 * The command is registered in a child context that injects `commands`, which
 * keeps it agent-scoped: it only exists in sessions of the preset this bundle
 * adds. Its handler submits one user message that opens the "定制算子" flow
 * (single operator, hardcoded constants, minimal parameters) and returns a
 * direct acknowledgement to the dispatching UI.
 */
import { readFileSync } from 'node:fs'
import { dirname, join, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const PACKAGE_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const SKILL_NAME = 'dolphinscheduler-python-operator'
const SKILL_DIR = join(PACKAGE_ROOT, 'assets', 'skills', SKILL_NAME)
const FRONTMATTER = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/u

const COMMAND_NAME = 'custom-operator'
const COMMAND_DESCRIPTION = '定制算子：单算子实现、能确定的固化、只留必要参数'
const COMMAND_USAGE = '用法：/custom-operator <需求>。'
  + '例如：/custom-operator 用统计视图出 2026 年 10 月的月报 xlsx，'
  + '下游上传算子接 filePath'

function parseSkill(raw, path) {
  const frontmatter = FRONTMATTER.exec(raw)
  if (frontmatter?.[1] === undefined) {
    throw new Error(`dsh-dolphinscheduler-operator: ${path} has no YAML frontmatter`)
  }
  const description = /^description:\s*(.+?)\s*$/mu.exec(frontmatter[1])?.[1]
  if (description === undefined || description.length === 0) {
    throw new Error(`dsh-dolphinscheduler-operator: ${path} has no description`)
  }
  return {
    description: description.replace(/^["']|["']$/gu, ''),
    content: raw.slice(frontmatter[0].length).trim(),
  }
}

/**
 * Build the model-visible task message for `/custom-operator`.
 *
 * The rules are intentionally inlined instead of only pointing at the skill:
 * the command must work even before the skill is loaded. The skill's
 * "定制算子" section is the long form of the same rules.
 */
function buildCustomOperatorTask(requirement) {
  return [
    '【定制算子】按「单算子、能确定的固化、最少参数」交付，需求如下：',
    requirement,
    '',
    '执行规则（与通用算子模板不同，按这个来）：',
    '1. 主体只用一个 Python 算子做完：取数、计算、产出、发出参都在同一个脚本里。'
      + '只有「文件要出现在【查看结果】」这一件事才拆出第二个通用上传算子；'
      + '只是把文件交给下游，就单算子写到 /data/ 并发绝对路径。',
    '2. 能确定的全部固化成脚本顶部常量：数据源（数据视图 viewId / MinIO 端点-桶-对象键 / 库表）、'
      + '口径与列名、输出目录与文件名、时间窗口规则、超时。不为「以后可能变」加开关。',
    '3. 参数只留本次任务真的要外部决定的（目标 0~3 个）：能写死就不声明；'
      + '上游已有出参不重复声明；出参只留下游或交付真正要用的。',
    '4. 不做通用化：不要多视图 Map、配置对象、兼容分支、用不到的兜底；新需求再写一份。',
    '5. 缺关键信息（数据源、口径、产出给谁）就先问清楚，不要编。',
    '',
    '先加载 dolphinscheduler-python-operator skill 的「定制算子」一节，'
      + '遵守其中的 > < & 字符限制、sys.exit 约定与交付前自检。'
      + '交付：脚本 + 参数表（可能 0 行）+ 一句部署说明。',
  ].join('\n')
}

export const name = 'dolphinscheduler-operator-skill'
export const inject = ['skills']

export function apply(ctx) {
  const skillFile = join(SKILL_DIR, 'SKILL.md')
  const { description, content } = parseSkill(readFileSync(skillFile, 'utf8'), skillFile)
  ctx.effect(() =>
    ctx.skills.register({
      name: SKILL_NAME,
      description,
      content,
      path: skillFile,
      source: 'runtime',
      resourceBase: { kind: 'directory', path: SKILL_DIR.split(sep).join('/') },
      invocation: { modelInvocable: true, userInvocable: true },
    }),
  )

  ctx.inject(['commands'], (commandCtx) => {
    commandCtx.commands.register({
      name: COMMAND_NAME,
      description: COMMAND_DESCRIPTION,
      input: { hint: '<需求：数据从哪来、算什么、产出给谁>' },
      handler: ({ agent, rawInput }) => {
        const requirement = rawInput.trim()
        if (requirement === '') {
          return { kind: 'error', text: COMMAND_USAGE }
        }
        agent.followup({
          content: [{ type: 'text', text: buildCustomOperatorTask(requirement) }],
          source: { kind: 'user' },
        })
        return {
          kind: 'success',
          text: '已按「定制算子」开工：单算子实现、能确定的固化、只留必要参数。',
        }
      },
    })
  })
}
