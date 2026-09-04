import { useEffect, useState } from 'react'
import { accountManagementApi } from './accountManagementApi'
import './admin-operations.css'

const efforts = ['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'] as const

export function AdminOperationsPage({ onForbidden, onSessionExpired }: { onForbidden?(): void; onSessionExpired?(): void }) {
  const [model, setModel] = useState('')
  const [reasoningEffort, setReasoningEffort] = useState('high')
  const [providerBaseUrl, setProviderBaseUrl] = useState('')
  const [status, setStatus] = useState('正在读取服务器配置…')
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    if (!accountManagementApi.getRuntimeSettings) { setStatus('当前版本未接入真实配置接口'); return }
    accountManagementApi.getRuntimeSettings().then((settings) => { setModel(settings.model); setReasoningEffort(settings.reasoningEffort); setProviderBaseUrl(settings.providerBaseUrl); setStatus('配置来自当前生产服务') }).catch((error: unknown) => { if (typeof error === 'object' && error && 'status' in error) { if (error.status === 401) onSessionExpired?.(); if (error.status === 403) onForbidden?.() }; setStatus('无法读取服务器配置') })
  }, [onForbidden, onSessionExpired])
  async function save() { if (!accountManagementApi.updateRuntimeSettings) return; setSaving(true); setStatus('正在写入配置并重载服务…'); try { await accountManagementApi.updateRuntimeSettings({ model: model.trim(), reasoningEffort }); setStatus('已写入服务器配置，服务正在重载') } catch (error) { if (typeof error === 'object' && error && 'status' in error) { if (error.status === 401) onSessionExpired?.(); if (error.status === 403) onForbidden?.() }; setStatus('写入失败，服务器配置未改变') } finally { setSaving(false) } }
  return <article className="admin-ops-page"><header className="admin-ops-hero"><p className="admin-ops-eyebrow">ADMIN / RUNTIME CONTROL</p><h1>模型调用配置</h1><p>修改当前 Qunxue 生产服务实际使用的模型与思考强度。</p></header><section className="admin-ops-panel"><div className="admin-ops-panel__heading"><div><p className="admin-ops-eyebrow">LIVE CONFIGURATION</p><h2>当前服务器配置</h2></div><span className="admin-ops-muted">{status}</span></div><dl className="admin-ops-facts"><div><dt>调用地址</dt><dd>{providerBaseUrl || '读取中…'}</dd></div><div><dt>当前模型</dt><dd>{model || '读取中…'}</dd></div><div><dt>思考强度</dt><dd>{reasoningEffort}</dd></div></dl><div className="admin-ops-form"><label><span>切换模型 ID</span><input value={model} onChange={(event) => setModel(event.target.value)} placeholder="例如 gpt-5.6-sol" /></label><label><span>思考强度</span><select value={reasoningEffort} onChange={(event) => setReasoningEffort(event.target.value)}>{efforts.map((effort) => <option key={effort} value={effort}>{effort}</option>)}</select></label><button type="button" disabled={saving || !model.trim()} onClick={() => void save()}>{saving ? '正在应用…' : '应用并重载服务'}</button></div><p className="admin-ops-note">保存会更新服务器 canonical 配置并重启 `qunxue-api`。下一次请求将使用新配置。</p></section></article>
}
