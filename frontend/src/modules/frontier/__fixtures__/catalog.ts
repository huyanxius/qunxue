import seed from './seed.json'
import type { FrontierRecord } from '../model'
import type { FrontierDataset } from '../dataset'
export const frontierRecords: readonly FrontierRecord[] = seed
export const testDataset: FrontierDataset = { records: frontierRecords, topics: [], sources: [], asOf: '2026-10-01', modelStatus: 'not_configured' }
