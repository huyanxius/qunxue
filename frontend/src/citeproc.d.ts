declare module 'citeproc' {
  type CslItem = { id: string } & Record<string, unknown>

  type EngineSystem = {
    retrieveItem(id: string): CslItem | undefined
    retrieveLocale(locale: string): string
  }

  type BibliographyParameters = {
    bibstart: string
    bibend: string
  }

  class Engine {
    constructor(system: EngineSystem, style: string, locale?: string, forceLang?: boolean)
    setOutputFormat(format: 'html' | 'text' | 'rtf'): void
    updateItems(ids: string[]): string[]
    makeBibliography(): [BibliographyParameters, string[]] | false
  }

  const CSL: { Engine: typeof Engine }
  export default CSL
}
