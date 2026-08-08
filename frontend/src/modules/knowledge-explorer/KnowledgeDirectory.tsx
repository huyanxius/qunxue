import type {
  KnowledgeDirectoryCategory,
  KnowledgeDirectoryDimension,
} from './directoryTree'

interface KnowledgeDirectoryProps {
  directory: readonly KnowledgeDirectoryDimension[]
  selectedDimensionId?: string
  selectedCategoryId?: string
  onSelectDimension: (dimensionId: string) => void
  onSelectCategory: (dimensionId: string, categoryId: string) => void
}

function KnowledgeDirectoryCategories({
  categories,
  dimensionId,
  selectedCategoryId,
  onSelectCategory,
}: {
  categories: readonly KnowledgeDirectoryCategory[]
  dimensionId: string
  selectedCategoryId?: string
  onSelectCategory: (dimensionId: string, categoryId: string) => void
}) {
  return (
    <ul>
      {categories.map((category) => {
        const isLeaf = category.children.length === 0
        return (
          <li key={category.nodeId}>
            {isLeaf ? (
              <button
                type="button"
                aria-pressed={selectedCategoryId === category.nodeId}
                onClick={() => onSelectCategory(dimensionId, category.nodeId)}
              >
                <span>{category.title}</span>
                <small>{category.entryCount} 条</small>
              </button>
            ) : (
              <details className="knowledge-explorer__directory-branch">
                <summary>
                  <span>{category.title}</span>
                  <small>{category.entryCount} 条</small>
                </summary>
                <KnowledgeDirectoryCategories
                  categories={category.children}
                  dimensionId={dimensionId}
                  selectedCategoryId={selectedCategoryId}
                  onSelectCategory={onSelectCategory}
                />
              </details>
            )}
          </li>
        )
      })}
    </ul>
  )
}

export function KnowledgeDirectory({
  directory,
  selectedDimensionId,
  selectedCategoryId,
  onSelectDimension,
  onSelectCategory,
}: KnowledgeDirectoryProps) {
  return (
    <nav className="knowledge-explorer__directory" aria-labelledby="knowledge-directory-title">
      <h2 id="knowledge-directory-title">七维目录</h2>
      <ul>
        {directory.map((dimension) => (
          <li key={dimension.nodeId}>
            <button
              type="button"
              aria-pressed={selectedDimensionId === dimension.nodeId && !selectedCategoryId}
              onClick={() => onSelectDimension(dimension.nodeId)}
            >
              <span>{dimension.nodeId} · {dimension.title}</span>
              <small>{dimension.entryCount} 条</small>
            </button>
            {dimension.entryCount === 0 ? (
              <p>当前发布暂无可浏览条目</p>
            ) : (
              <details className="knowledge-explorer__directory-branch">
                <summary>展开 {dimension.entryCount} 条条目</summary>
                <KnowledgeDirectoryCategories
                  categories={dimension.categories}
                  dimensionId={dimension.nodeId}
                  selectedCategoryId={selectedCategoryId}
                  onSelectCategory={onSelectCategory}
                />
              </details>
            )}
          </li>
        ))}
      </ul>
    </nav>
  )
}
