import { useState, type CSSProperties } from 'react'

import type {
  KnowledgeDirectoryCategory,
  KnowledgeDirectoryDimension,
} from './directoryTree'

function CategoryBranches({
  categories,
  onSelectCategory,
  depth = 0,
}: {
  categories: readonly KnowledgeDirectoryCategory[]
  onSelectCategory: (categoryId: string) => void
  depth?: number
}) {
  if (categories.length === 1 && categories[0].children.length > 1) {
    return (
      <CategoryBranches
        categories={categories[0].children}
        depth={depth}
        onSelectCategory={onSelectCategory}
      />
    )
  }

  return (
    <ul className="knowledge-explorer__category-list" data-depth={depth}>
      {categories.map((category, index) => (
        <CategoryBranch
          key={category.nodeId}
          category={category}
          depth={depth}
          index={index}
          onSelectCategory={onSelectCategory}
        />
      ))}
    </ul>
  )
}

function CategoryBranch({
  category,
  depth,
  index,
  onSelectCategory,
}: {
  category: KnowledgeDirectoryCategory
  depth: number
  index: number
  onSelectCategory: (categoryId: string) => void
}) {
  const [open, setOpen] = useState(false)
  const directLeaf = category.children.length === 1 && category.children[0].children.length === 0

  return (
    <li style={{ '--category-index': index } as CSSProperties}>
      {directLeaf ? (
        <button type="button" onClick={() => onSelectCategory(category.children[0].nodeId)}>
          <span>{category.children[0].title}</span>
          <small>{category.entryCount} 条</small>
          <b aria-hidden="true">→</b>
        </button>
      ) : category.children.length > 0 ? (
        <details open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
          <summary>
            <span>{category.title}</span>
            <small>{category.entryCount} 条</small>
          </summary>
          {open ? (
            <CategoryBranches
              categories={category.children}
              depth={depth + 1}
              onSelectCategory={onSelectCategory}
            />
          ) : null}
        </details>
      ) : (
        <button type="button" onClick={() => onSelectCategory(category.nodeId)}>
          <span>{category.title}</span>
          <small>{category.entryCount} 条</small>
          <b aria-hidden="true">→</b>
        </button>
      )}
    </li>
  )
}

export function KnowledgeCatalogIndex({
  directory,
  selectedDimension,
  onSelectDimension,
  onSelectCategory,
}: {
  directory: readonly KnowledgeDirectoryDimension[]
  selectedDimension?: KnowledgeDirectoryDimension
  onSelectDimension: (dimensionId: string) => void
  onSelectCategory: (dimensionId: string, categoryId: string) => void
}) {
  const activeDimension = selectedDimension ?? directory[0]
  if (!activeDimension) return null
  const totalEntries = directory.reduce((total, dimension) => total + dimension.entryCount, 0)

  return (
    <section className="knowledge-explorer__catalog" aria-labelledby="knowledge-catalog-title">
      <header>
        <div>
          <p>知识空间</p>
          <h2 id="knowledge-catalog-title">七维目录</h2>
        </div>
        <span>当前发布共 {totalEntries} 条知识。选择维度并展开分类后进入条目。</span>
      </header>

      <div className="knowledge-explorer__catalog-browser">
        <nav className="knowledge-explorer__dimension-nav" aria-label="知识维度">
          {directory.map((dimension) => {
            const active = dimension.nodeId === activeDimension.nodeId
            return (
              <button
                key={dimension.nodeId}
                type="button"
                aria-pressed={active}
                onClick={() => onSelectDimension(dimension.nodeId)}
              >
                <span>{dimension.nodeId}</span>
                <strong>{dimension.title}</strong>
                <small>{dimension.entryCount}</small>
              </button>
            )
          })}
        </nav>

        <div className="knowledge-explorer__catalog-detail" key={activeDimension.nodeId}>
          <header>
            <div>
              <p>{activeDimension.nodeId} / 知识维度</p>
              <h3>{activeDimension.title}</h3>
              <span>按真实目录层级展开当前维度</span>
            </div>
            <strong><b>{activeDimension.entryCount}</b> 条知识</strong>
          </header>
          <div className="knowledge-explorer__category-index">
            <CategoryBranches
              categories={activeDimension.categories}
              onSelectCategory={(categoryId) => onSelectCategory(activeDimension.nodeId, categoryId)}
            />
          </div>
        </div>
      </div>
    </section>
  )
}
