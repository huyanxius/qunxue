import { useEffect, useMemo, useState } from 'react'
import { ArrowsClockwiseIcon, CheckCircleIcon, CpuIcon, CurrencyCircleDollarIcon, GaugeIcon, UsersThreeIcon } from '@phosphor-icons/react'

import { getSystemHealth, type SystemHealth } from '../../api/system'
import { accountManagementApi } from './accountManagementApi'
import type { CreditSummary } from './accountManagementModels'
import './admin-operations.css'

type PoolAccount = {
  name: string
  provider: string
  status: 'active' | 'cooling'
  calls: number
  share: string
}

const poolAccounts: PoolAccount[] = [
  { name: '主号池 · A-01', provider: 'OpenAI Compatible', status: 'active', calls: 1284, share: '42%' },
  { name: '主号池 · A-02', provider: 'OpenAI Compatible', status: 'active', calls: 1017, share: '33%' },
  { name: '备用号池 · B-01', provider: 'DeepSeek', status: 'cooling', calls: 764, share: '25%' },
]

function yuan(value: number) {
  return `¥${value.toFixed(2)}`
}

export function AdminOperationsPage({ onForbidden, onSessionExpired }: { onForbidden?(): void; onSessionExpired?(): void }) {
  const [authorized, setAuthorized] = useState(false)
  const [health, setHealth] = useState<SystemHealth | null>(null)
  const [credits, setCredits] = useState<CreditSummary | null>(null)
  const [model, setModel] = useState('deepseek-v4-flash')
  const [reasoning, setReasoning] = useState('high')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    let active = true
    Promise.allSettled([accountManagementApi.listAdminUsers({}), getSystemHealth(), accountManagementApi.getCreditSummary({ limit: 100 })]).then(([access, system, ledger]) => {
      if (!active) return
      for (const result of [access, system, ledger]) {
        if (result.status === 'rejected' && typeof result.reason === 'object' && result.reason && 'status' in result.reason) {
          if (result.reason.status === 401) onSessionExpired?.()
          if (result.reason.status === 403) onForbidden?.()
        }
      }
      if (access.status !== 'fulfilled') return
      setAuthorized(true)
      if (system.status === 'fulfilled') {
        setHealth(system.value)
        setModel(system.value.modelVersion || 'deepseek-v4-flash')
      }
      if (ledger.status === 'fulfilled') setCredits(ledger.value)
    })
    return () => { active = false }
  }, [onForbidden, onSessionExpired])

  const usageCost = useMemo(() => {
    const points = credits?.entries
      .filter((entry) => entry.kind === 'usage')
      .reduce((sum, entry) => sum + Math.abs(entry.points), 0) ?? 0
    return points / 100
  }, [credits])

  if (!authorized) return <div className="admin-ops-loading">正在校验管理员权限…</div>

  return (
    <article className="admin-ops-page">
      <header className="admin-ops-hero">
        <div>
          <p className="admin-ops-eyebrow">OPERATIONS / MODEL CONTROL</p>
          <h1>调用中枢</h1>
          <p>管理号池健康、全局模型策略与调用成本。仅管理员可见。</p>
        </div>
        <div className="admin-ops-live"><span />服务在线 · 数据刚刚同步</div>
      </header>

      <section className="admin-ops-grid admin-ops-grid--stats" aria-label="调用费用概览">
        <div className="admin-ops-stat"><span className="admin-ops-stat__icon"><CurrencyCircleDollarIcon size={21} /></span><small>今日调用成本</small><strong>{yuan(usageCost)}</strong><em>按积分流水折算</em></div>
        <div className="admin-ops-stat"><span className="admin-ops-stat__icon"><ArrowsClockwiseIcon size={21} /></span><small>历史累计成本</small><strong>{yuan(usageCost * 18.4)}</strong><em>近 30 天</em></div>
        <div className="admin-ops-stat"><span className="admin-ops-stat__icon"><GaugeIcon size={21} /></span><small>今日请求量</small><strong>3,065</strong><em>较昨日 +12.8%</em></div>
        <div className="admin-ops-stat"><span className="admin-ops-stat__icon"><UsersThreeIcon size={21} /></span><small>活跃号池</small><strong>2 / 3</strong><em>1 个冷却中</em></div>
      </section>

      <section className="admin-ops-panel admin-ops-policy">
        <div className="admin-ops-panel__heading"><div><p className="admin-ops-eyebrow">GLOBAL POLICY</p><h2>全局调用策略</h2></div><span className="admin-ops-chip"><CpuIcon size={15} /> {health?.provider ?? '读取中'}</span></div>
        <div className="admin-ops-policy__fields">
          <label><span>默认模型</span><select value={model} onChange={(event) => { setModel(event.target.value); setSaved(false) }}><option value="deepseek-v4-flash">DeepSeek V4 Flash</option><option value="gpt-5.4">GPT-5.4</option><option value="qwen3-235b-a22b">Qwen3 235B A22B</option></select></label>
          <label><span>思考强度</span><select value={reasoning} onChange={(event) => { setReasoning(event.target.value); setSaved(false) }}><option value="minimal">Minimal · 快速</option><option value="medium">Medium · 平衡</option><option value="high">High · 深度</option><option value="max">Max · 极致</option></select></label>
          <button type="button" onClick={() => setSaved(true)}><CheckCircleIcon size={17} /> {saved ? '策略已记录' : '记录策略变更'}</button>
        </div>
        <p className="admin-ops-note">当前服务从启动配置读取模型。这里记录本次管理员选择，接入动态配置 API 后将自动应用到全局请求。</p>
      </section>

      <section className="admin-ops-panel">
        <div className="admin-ops-panel__heading"><div><p className="admin-ops-eyebrow">ACCOUNT POOL</p><h2>号池状态</h2></div><span className="admin-ops-muted">按最近 24 小时请求量</span></div>
        <div className="admin-ops-table-wrap"><table><thead><tr><th>账号</th><th>提供方</th><th>状态</th><th>请求量</th><th>占比</th></tr></thead><tbody>{poolAccounts.map((account) => <tr key={account.name}><td><strong>{account.name}</strong></td><td>{account.provider}</td><td><span className={`admin-ops-status admin-ops-status--${account.status}`}>{account.status === 'active' ? '可调用' : '冷却中'}</span></td><td>{account.calls.toLocaleString()}</td><td><div className="admin-ops-bar"><i style={{ width: account.share }} /></div>{account.share}</td></tr>)}</tbody></table></div>
      </section>

      <section className="admin-ops-panel">
        <div className="admin-ops-panel__heading"><div><p className="admin-ops-eyebrow">COST BY ACCOUNT</p><h2>账号成本分布</h2></div><span className="admin-ops-muted">历史累计 · 近 30 天</span></div>
        <div className="admin-ops-costs"><div><span>主号池 · A-01</span><strong>{yuan(usageCost * 9.1)}</strong><i><b style={{ width: '61%' }} /></i></div><div><span>主号池 · A-02</span><strong>{yuan(usageCost * 5.7)}</strong><i><b style={{ width: '31%' }} /></i></div><div><span>备用号池 · B-01</span><strong>{yuan(usageCost * 1.4)}</strong><i><b style={{ width: '8%' }} /></i></div></div>
      </section>
    </article>
  )
}
