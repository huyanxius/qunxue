// Cohen's Kappa:两名编码者(AI 初编 vs 研究者终裁)对同一批段落的类目一致性。
// κ = (Po − Pe) / (1 − Pe),Po 为观察一致率,Pe 为随机期望一致率。

export interface KappaResult {
  n: number
  po: number
  pe: number
  kappa: number | null
}

export function cohenKappa(pairs: Array<[string, string]>): KappaResult {
  const n = pairs.length
  if (n === 0) return { n: 0, po: 0, pe: 0, kappa: null }

  const agree = pairs.filter(([a, b]) => a === b).length
  const po = agree / n

  const categories = new Set(pairs.flat())
  let pe = 0
  for (const c of categories) {
    const pa = pairs.filter(([a]) => a === c).length / n
    const pb = pairs.filter(([, b]) => b === c).length / n
    pe += pa * pb
  }

  const kappa = pe === 1 ? null : (po - pe) / (1 - pe)
  return { n, po, pe, kappa }
}

export function kappaLevel(k: number): string {
  if (k >= 0.81) return '几乎完全一致'
  if (k >= 0.61) return '高度一致'
  if (k >= 0.41) return '中度一致'
  if (k >= 0.21) return '一般一致'
  return '一致性弱'
}
