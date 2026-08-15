import { useEffect, useState, type CSSProperties } from 'react'
import {
  CaretDownIcon,
  CaretRightIcon,
} from '@phosphor-icons/react'

import type {
  KnowledgeDirectoryCategory,
  KnowledgeDirectoryDimension,
} from './directoryTree'
import { describeTaxonomyNode, dimensionTone, type KnowledgeDimensionTone } from './taxonomyPresentation'

interface KnowledgeCatalogProps {
  directory: readonly KnowledgeDirectoryDimension[]
  selectedDimension?: KnowledgeDirectoryDimension
  selectedCategoryId?: string
  onSelectDimension: (dimensionId: string) => void
  onSelectCategory: (dimensionId: string, categoryId: string) => void
}

function findCategoryPath(
  categories: readonly KnowledgeDirectoryCategory[],
  targetId: string,
  path: readonly string[] = [],
): readonly string[] | undefined {
  for (const category of categories) {
    const nextPath = [...path, category.nodeId]
    if (category.nodeId === targetId) return nextPath
    const nested = findCategoryPath(category.children, targetId, nextPath)
    if (nested) return nested
  }
  return undefined
}

function CategoryTree({
  categories,
  depth,
  dimensionId,
  expandedNodes,
  selectedCategoryId,
  tone,
  onToggle,
  onSelectCategory,
}: {
  categories: readonly KnowledgeDirectoryCategory[]
  depth: number
  dimensionId: string
  expandedNodes: ReadonlySet<string>
  selectedCategoryId?: string
  tone: KnowledgeDimensionTone
  onToggle: (nodeId: string) => void
  onSelectCategory: (dimensionId: string, categoryId: string) => void
}) {
  return (
    <ul className="knowledge-tree__branch">
      {categories.map((category) => {
        const presentation = describeTaxonomyNode(category.title)
        const expandable = category.children.length > 0
        const expanded = expandedNodes.has(category.nodeId)
        const selected = category.nodeId === selectedCategoryId
        return (
          <li key={category.nodeId}>
            <button
              className="knowledge-tree__category"
              type="button"
              data-active={selected || undefined}
              data-dimension-tone={tone}
              data-node-kind={presentation.kind}
              data-stage={presentation.stage}
              style={{ '--tree-depth': depth } as CSSProperties}
              aria-label={`${expandable ? (expanded ? '收起' : '进入') : '浏览'} ${category.title}`}
              onClick={() => {
                if (expandable) onToggle(category.nodeId)
                else onSelectCategory(dimensionId, category.nodeId)
              }}
            >
              <span className="knowledge-tree__disclosure" aria-hidden="true">
                {expandable
                  ? expanded
                    ? <CaretDownIcon size={13} weight="bold" />
                    : <CaretRightIcon size={13} weight="bold" />
                  : <span />}
              </span>
              <span className="knowledge-tree__node-badge" aria-hidden="true">{presentation.badge ?? '·'}</span>
              <span className="knowledge-tree__label">{presentation.label}</span>
              <small>{category.entryCount}</small>
            </button>
            {expandable && expanded ? (
              <CategoryTree
                categories={category.children}
                depth={depth + 1}
                dimensionId={dimensionId}
                expandedNodes={expandedNodes}
                selectedCategoryId={selectedCategoryId}
                tone={tone}
                onToggle={onToggle}
                onSelectCategory={onSelectCategory}
              />
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}

export function KnowledgeCatalog({
  directory,
  selectedDimension,
  selectedCategoryId,
  onSelectDimension,
  onSelectCategory,
}: KnowledgeCatalogProps) {
  const activeDimensionId = selectedDimension?.nodeId ?? directory[0]?.nodeId
  const [expandedNodes, setExpandedNodes] = useState<ReadonlySet<string>>(
    () => new Set(activeDimensionId ? [activeDimensionId] : []),
  )

  useEffect(() => {
    if (!activeDimensionId) return
    const activeDimension = directory.find((dimension) => dimension.nodeId === activeDimensionId)
    const selectedPath = activeDimension && selectedCategoryId
      ? findCategoryPath(activeDimension.categories, selectedCategoryId)
      : undefined
    setExpandedNodes((current) => new Set([
      ...current,
      activeDimensionId,
      ...(selectedPath?.slice(0, -1) ?? []),
    ]))
  }, [activeDimensionId, directory, selectedCategoryId])

  function toggle(nodeId: string) {
    setExpandedNodes((current) => {
      const next = new Set(current)
      if (next.has(nodeId)) next.delete(nodeId)
      else next.add(nodeId)
      return next
    })
  }

  function openDimension(dimensionId: string) {
    setExpandedNodes((current) => new Set([...current, dimensionId]))
    onSelectDimension(dimensionId)
  }

  return (
    <nav className="knowledge-tree" aria-label="知识目录">
      <header className="knowledge-tree__heading">
        <span>知识维度</span>
        <small>{directory.length}</small>
      </header>
      <div className="knowledge-tree__scroll">
        {directory.map((dimension) => {
          const tone = dimensionTone(dimension.nodeId)
          const expanded = expandedNodes.has(dimension.nodeId)
          const active = dimension.nodeId === activeDimensionId
          return (
            <section className="knowledge-tree__dimension" key={dimension.nodeId}>
              <div className="knowledge-tree__dimension-row" data-active={active || undefined} data-dimension-tone={tone}>
                <button
                  className="knowledge-tree__dimension-toggle"
                  type="button"
                  aria-label={`${expanded ? '收起' : '展开'} ${dimension.title}`}
                  onClick={() => toggle(dimension.nodeId)}
                >
                  {expanded
                    ? <CaretDownIcon size={13} weight="bold" aria-hidden="true" />
                    : <CaretRightIcon size={13} weight="bold" aria-hidden="true" />}
                </button>
                <button
                  className="knowledge-tree__dimension-link"
                  type="button"
                  aria-current={active ? 'page' : undefined}
                  aria-label={`浏览 ${dimension.title} 目录`}
                  data-dimension-tone={tone}
                  onClick={() => openDimension(dimension.nodeId)}
                >
                  <span className="knowledge-tree__dimension-badge" aria-hidden="true">{dimension.nodeId}</span>
                  <strong>{dimension.title}</strong>
                  <small>{dimension.entryCount}</small>
                </button>
              </div>
              {expanded ? (
                <CategoryTree
                  categories={dimension.categories}
                  depth={1}
                  dimensionId={dimension.nodeId}
                  expandedNodes={expandedNodes}
                  selectedCategoryId={selectedCategoryId}
                  tone={tone}
                  onToggle={toggle}
                  onSelectCategory={onSelectCategory}
                />
              ) : null}
            </section>
          )
        })}
      </div>
    </nav>
  )
}
