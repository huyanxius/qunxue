/**
 * Compatibility entry point for callers that already import the material reader.
 * The actual browser lives in CodedDocumentWorkbench so the document, code tree,
 * retrieved results and evidence inspector evolve as one interaction model.
 */
export {
  CodedDocumentWorkbench as MaterialReaderView,
  type MaterialReaderViewProps,
  type ReaderHeading,
} from './CodedDocumentWorkbench'
