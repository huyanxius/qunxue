import { describe, expect, it } from 'vitest'

import { buildKnowledgeDirectory } from './directoryTree'
import type { KnowledgeDirectoryFacet } from './types'

const facets: KnowledgeDirectoryFacet[] = [
  { entryCount: 1, nodeId: 'D1', nodeType: 'dimension', title: '本体论' },
  { entryCount: 1, nodeId: 'D1:I. 古典社会学奠基', nodeType: 'category', parentNodeId: 'D1', title: 'I. 古典社会学奠基' },
  { entryCount: 1, nodeId: 'D1:I. 古典社会学奠基/1. 古典社会学奠基', nodeType: 'category', parentNodeId: 'D1:I. 古典社会学奠基', title: '1. 古典社会学奠基' },
  { entryCount: 0, nodeId: 'D2', nodeType: 'dimension', title: '实践论' },
  { entryCount: 0, nodeId: 'D3', nodeType: 'dimension', title: '方法论' },
  { entryCount: 0, nodeId: 'D4', nodeType: 'dimension', title: '价值论' },
  { entryCount: 0, nodeId: 'D5', nodeType: 'dimension', title: '认识论' },
  { entryCount: 0, nodeId: 'D6', nodeType: 'dimension', title: '学派传统' },
  { entryCount: 0, nodeId: 'D7', nodeType: 'dimension', title: '学科史' },
]

describe('buildKnowledgeDirectory', () => {
  it('keeps seven taxonomy roots while retaining nested category paths from one release', () => {
    const directory = buildKnowledgeDirectory(facets)

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

  it('rejects a directory node whose parent is missing', () => {
    const invalid: KnowledgeDirectoryFacet = {
      entryCount: 1,
      nodeId: 'C999',
      nodeType: 'category',
      parentNodeId: 'missing',
      title: '未知分类',
    }

    expect(() => buildKnowledgeDirectory([...facets, invalid])).toThrow('知识目录契约错误')
  })
})
