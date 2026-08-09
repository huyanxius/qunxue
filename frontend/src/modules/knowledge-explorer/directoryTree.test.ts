import { describe, expect, it } from 'vitest'

import { buildKnowledgeDirectory } from './directoryTree'
import type { KnowledgeEntrySummary } from './types'

function entry(): KnowledgeEntrySummary {
  return {
    category: '1. 古典社会学奠基',
    categoryId: 'D1:I. 古典社会学奠基/1. 古典社会学奠基',
    contentVersion: 1,
    dimension: '本体论',
    dimensionId: 'D1',
    directoryPath: [
      { nodeId: 'D1', nodeType: 'dimension', title: '本体论' },
      { nodeId: 'D1:I. 古典社会学奠基', nodeType: 'category', title: 'I. 古典社会学奠基' },
      {
        nodeId: 'D1:I. 古典社会学奠基/1. 古典社会学奠基',
        nodeType: 'category',
        title: '1. 古典社会学奠基',
      },
    ],
    knowledgeId: 'D1:C001',
    reviewStatus: 'pending',
    title: '概念',
  }
}

describe('buildKnowledgeDirectory', () => {
  it('keeps seven taxonomy roots while retaining nested category paths from one release', () => {
    const directory = buildKnowledgeDirectory([entry()])

    expect(directory.map((dimension) => dimension.nodeId)).toEqual([
      'D1',
      'D2',
      'D3',
      'D4',
      'D5',
      'D6',
      'D7',
    ])
    expect(directory[0]).toMatchObject({
      nodeId: 'D1',
      entryCount: 1,
      categories: [{
        nodeId: 'D1:I. 古典社会学奠基',
        entryCount: 1,
        title: 'I. 古典社会学奠基',
        children: [{
          nodeId: 'D1:I. 古典社会学奠基/1. 古典社会学奠基',
          entryCount: 1,
          title: '1. 古典社会学奠基',
        }],
      }],
    })
    expect(directory[5]).toMatchObject({
      nodeId: 'D6',
      entryCount: 0,
      categories: [],
    })
  })

  it('rejects an entry whose root is outside the fixed taxonomy', () => {
    const invalid = {
      ...entry(),
      dimensionId: 'D8',
      directoryPath: [
        { nodeId: 'D8', nodeType: 'dimension' as const, title: '未知维度' },
        { nodeId: 'D8:C001', nodeType: 'category' as const, title: '概念' },
      ],
    }

    expect(() => buildKnowledgeDirectory([invalid])).toThrow('知识目录契约错误')
  })
})
