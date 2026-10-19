/**
 * Bundled skill provider for the `dolphinscheduler-python-operator` skill.
 *
 * The skill body and its REFERENCE.md live under `assets/skills/<name>/`, so the
 * bundle is self-contained: installing it ships the skill without depending on
 * anything under the user's DSH skills directory.
 *
 * Registered through `ctx.skills.register` (runtime source) inside the preset's
 * standing composition, so the skill lands in that preset's skill-registry
 * layer and outranks a same-name copy discovered from `~/.dsh/skills`.
 */
import { readFileSync } from 'node:fs'
import { dirname, join, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const PACKAGE_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const SKILL_NAME = 'dolphinscheduler-python-operator'
const SKILL_DIR = join(PACKAGE_ROOT, 'assets', 'skills', SKILL_NAME)
const FRONTMATTER = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/u

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
}
