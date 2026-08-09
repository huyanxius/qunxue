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
  onShowCatalog: () => void
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
  if (categories.length === 1 && categories[0].children.length > 1) {
    return (
      <KnowledgeDirectoryCategories
        categories={categories[0].children}
        dimensionId={dimensionId}
        selectedCategoryId={selectedCategoryId}
        onSelectCategory={onSelectCategory}
      />
    )
  }

  function includesSelected(category: KnowledgeDirectoryCategory): boolean {
    return category.nodeId === selectedCategoryId || category.children.some(includesSelected)
  }

  return (
    <ul>
      {categories.map((category) => {
        const isLeaf = category.children.length === 0
        const directLeaf = category.children.length === 1 && category.children[0].children.length === 0
        return (
          <li key={category.nodeId}>
            {isLeaf || directLeaf ? (
              <button
                type="button"
                aria-pressed={selectedCategoryId === (directLeaf ? category.children[0].nodeId : category.nodeId)}
                onClick={() => onSelectCategory(dimensionId, directLeaf ? category.children[0].nodeId : category.nodeId)}
              >
                <span>{directLeaf ? category.children[0].title : category.title}</span>
                <small>{category.entryCount} 条</small>
              </button>
            ) : (
              <details className="knowledge-explorer__directory-branch" open={includesSelected(category)}>
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
  onShowCatalog,
}: KnowledgeDirectoryProps) {
  const activeDimension = directory.find((dimension) => dimension.nodeId === selectedDimensionId)

  return (
    <nav className="knowledge-explorer__directory" aria-labelledby="knowledge-directory-title">
      <header>
        {activeDimension ? (
          <button className="knowledge-explorer__directory-back" type="button" onClick={onShowCatalog}>
            ← 七维目录
          </button>
        ) : <p>知识结构</p>}
        <h2 id="knowledge-directory-title">{activeDimension?.title ?? '七维目录'}</h2>
        {activeDimension ? <small>{activeDimension.entryCount} 条知识</small> : null}
      </header>
      {activeDimension ? (
        <KnowledgeDirectoryCategories
          categories={activeDimension.categories}
          dimensionId={activeDimension.nodeId}
          selectedCategoryId={selectedCategoryId}
          onSelectCategory={onSelectCategory}
        />
      ) : (
        <ul>
          {directory.map((dimension) => (
            <li key={dimension.nodeId}>
              <button type="button" onClick={() => onSelectDimension(dimension.nodeId)}>
                <span>{dimension.nodeId} / {dimension.title}</span>
                <small>{dimension.entryCount} 条</small>
              </button>
            </li>
          ))}
        </ul>
      )}
    </nav>
  )
}
