import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useState } from 'react'
import * as materialsApi from '../../research-materials'
import type { ResearchMaterial } from '../../research-materials'
import { StudentMaterials } from './StudentMaterials'

vi.mock('../../research-materials', async (original) => ({
  ...await original<typeof materialsApi>(),
  listAgentMaterials: vi.fn(), prepareAgentMaterialContext: vi.fn(),
  addResearchLibraryMaterial: vi.fn(), getAgentAttachmentMaterial: vi.fn(),
}))
afterEach(() => { cleanup(); vi.clearAllMocks() })
const material: ResearchMaterial = { materialId: 'm1', taskId: 't1', filename: '作业.txt', mediaType: 'text/plain', sizeBytes: 30, status: 'ready', version: 1, parseVersion: 1, segmentCount: 1, updatedAt: '', errorCode: null }
function Harness() {
  const [ids, setIds] = useState<string[]>([])
  return <><StudentMaterials selectedIds={ids} onChange={setIds} /><output>{ids.join(',')}</output></>
}
it('keeps parsing files unavailable and only selects the explicit ready file', async () => {
  vi.mocked(materialsApi.listAgentMaterials).mockResolvedValue([material, { ...material, materialId: 'm2', filename: '解析中.txt', status: 'processing' }])
  render(<Harness />)
  expect(await screen.findByRole('checkbox', { name: '解析中.txt' })).toBeDisabled()
  fireEvent.click(screen.getByRole('checkbox', { name: '作业.txt' }))
  expect(screen.getByRole('status')).toHaveTextContent('m1')
})
it('uploads into personal materials and selects the successfully parsed result', async () => {
  vi.mocked(materialsApi.listAgentMaterials).mockResolvedValue([])
  vi.mocked(materialsApi.prepareAgentMaterialContext).mockResolvedValue({ task_id: 't1', conversation_id: 'c1' })
  vi.mocked(materialsApi.addResearchLibraryMaterial).mockResolvedValue(material)
  render(<Harness />)
  const file = new File(['自己的作答'], '作业.txt', { type: 'text/plain' })
  fireEvent.change(screen.getByLabelText('上传个人材料'), { target: { files: [file] } })
  await waitFor(() => expect(screen.getByRole('checkbox', { name: '作业.txt' })).toBeChecked())
  expect(materialsApi.addResearchLibraryMaterial).toHaveBeenCalledWith('t1', file)
})
