import type { AppLocale } from '../../i18n/AppLocaleProvider'

const stageLabels: Record<string, string> = {
  '现象输入': 'Phenomenon input',
  '现象确认': 'Phenomenon confirmation',
  '理论匹配': 'Theory matching',
  '理论决策': 'Theory decision',
  '研究方案': 'Research plan',
  '方案确认': 'Plan review',
  '已完成': 'Completed',
}

const actionLabels: Record<string, string> = {
  '补充研究现象': 'Add phenomenon details',
  '确认研究现象': 'Confirm phenomenon',
  '开始理论匹配': 'Start theory matching',
  '审阅理论候选': 'Review theory candidates',
  '确认理论方案': 'Confirm theory plan',
  '生成研究方案': 'Generate research plan',
  '审阅研究方案': 'Review research plan',
  '确认研究方案': 'Confirm research plan',
  '查看并导出成果': 'View and export results',
  '重新匹配': 'Match again',
}

export function researchStageLabel(value: string, locale: AppLocale) {
  return locale === 'en-US' ? stageLabels[value] ?? 'Research stage' : value
}

export function researchActionLabel(value: string, locale: AppLocale) {
  return locale === 'en-US' ? actionLabels[value] ?? 'Continue research' : value
}

export function researchBlockerLabel(code: string, value: string, locale: AppLocale) {
  if (locale !== 'en-US') return value
  if (code === 'no_reliable_candidate') {
    return 'No reliable theory candidate is available in the current knowledge release. Adjust the phenomenon and try again.'
  }
  return 'This step needs attention before the research can continue.'
}
