import cytoscape, { type Core } from 'cytoscape'
import { useEffect, useRef, useState } from 'react'
import { ArrowCounterClockwiseIcon, CornersOutIcon, MinusIcon, PlusIcon } from '@phosphor-icons/react'
import { syncGraphProjection } from './graphExploration'
import type { KnowledgeGraphProjection } from './types'

const views = new Map<string, { positions: Record<string, { x: number; y: number }>; zoom: number; pan: { x: number; y: number } }>()

const style: cytoscape.StylesheetJson = [
  { selector: 'node', style: {
    label: 'data(label)', 'background-color': '#777d7e', width: 13, height: 13,
    color: '#303331', 'font-size': 13, 'font-family': '"Songti SC", serif',
    'text-valign': 'bottom', 'text-margin-y': 10, 'text-wrap': 'ellipsis',
    'text-max-width': '160px', 'min-zoomed-font-size': 9, 'overlay-padding': 12,
    'border-width': 3, 'border-color': '#f5f5f7',
  } },
  { selector: 'node[nodeType = "dimension"]', style: { width: 27, height: 27, 'background-color': '#343c38', 'font-size': 16, 'font-weight': 600 } },
  { selector: 'node[nodeType = "category"]', style: { width: 19, height: 19, 'background-color': '#a0a6a1', 'font-size': 14 } },
  { selector: 'node.active', style: { width: 24, height: 24, 'background-color': '#405b49', 'border-color': '#ced9cf', 'border-width': 6, 'font-weight': 600, 'font-size': 16 } },
  { selector: 'edge', style: { 'curve-style': 'bezier', width: 1.5, 'line-color': '#b7beb9', 'target-arrow-color': '#64766a', 'arrow-scale': 0.8, 'overlay-padding': 8 } },
  { selector: 'edge[layer = "structure"]', style: { width: 1, 'line-color': '#cbd0cd', 'line-style': 'dotted' } },
  { selector: 'edge[layer = "reviewed"]', style: { width: 2, 'line-color': '#64766a' } },
  { selector: 'edge[layer = "candidate"]', style: { 'line-style': 'dashed', 'line-color': '#a28558' } },
  { selector: 'edge[direction = "outbound"], edge[direction = "directed"], edge[direction = "bidirectional"]', style: { 'target-arrow-shape': 'triangle' } },
  { selector: 'edge[direction = "bidirectional"]', style: { 'source-arrow-shape': 'triangle', 'source-arrow-color': '#64766a' } },
  { selector: 'edge.active, edge:selected', style: { label: 'data(label)', 'font-size': 12, color: '#34443a', 'text-background-color': '#f5f5f7', 'text-background-opacity': 1, 'text-background-padding': '5px', width: 2.5 } },
]

export function ExplorationCanvas({ projection, selectedId, centerId, resetKey, sessionKey, onSelect, onEdge }: {
  sessionKey: string
  resetKey: number
  projection: KnowledgeGraphProjection
  selectedId?: string
  centerId?: string
  onSelect: (id: string) => void
  onEdge: (id?: string) => void
}) {
  const canvas = useRef<HTMLDivElement>(null)
  const graph = useRef<Core>(undefined)
  const callbacks = useRef({ onSelect, onEdge })
  callbacks.current = { onSelect, onEdge }
  const first = useRef(true)
  const previousCenter = useRef(resetKey)
  const canSave = useRef(false)
  canSave.current = resetKey > 0
  const [unavailable, setUnavailable] = useState(false)
  useEffect(() => {
    if (!canvas.current) return
    let cy: Core | undefined
    let resize: ResizeObserver | undefined
    try {
      cy = cytoscape({ container: canvas.current, elements: [], layout: { name: 'preset' }, style,
        minZoom: 0.3, maxZoom: 2.6, wheelSensitivity: 0.2, boxSelectionEnabled: false })
      graph.current = cy
      cy.on('tap', 'node', (event) => callbacks.current.onSelect(event.target.id()))
      cy.on('tap', 'edge', (event) => callbacks.current.onEdge(event.target.id()))
      cy.on('tap', (event) => { if (event.target === cy) callbacks.current.onEdge(undefined) })
      resize = new ResizeObserver(() => cy?.resize())
      resize.observe(canvas.current)
    } catch { setUnavailable(true) }
    return () => {
      if (cy && canSave.current) {
        views.set(sessionKey, { positions: Object.fromEntries(cy.nodes().map((node) => [node.id(), node.position()])), zoom: cy.zoom(), pan: cy.pan() })
        if (views.size > 8) views.delete(views.keys().next().value!)
      }
      resize?.disconnect(); cy?.destroy(); graph.current = undefined; first.current = true
    }
  }, [sessionKey])
  useEffect(() => {
    const cy = graph.current
    if (!cy) return
    syncGraphProjection(cy, projection, selectedId)
    cy.elements().removeClass('active')
    if (selectedId) {
      const selected = cy.getElementById(selectedId)
      selected.addClass('active')
      selected.connectedEdges().filter('[layer != "structure"]').addClass('active')
    }
    if (first.current || previousCenter.current !== resetKey) {
      const saved = views.get(sessionKey)
      if (saved) {
        cy.nodes().forEach((node) => { if (saved.positions[node.id()]) node.position(saved.positions[node.id()]) })
        cy.viewport({ zoom: saved.zoom, pan: saved.pan })
      } else {
        cy.fit(cy.elements(), 90)
        if (cy.zoom() > 1.2) cy.zoom(1.2)
        cy.center()
      }
      first.current = false
    }
    previousCenter.current = resetKey
  }, [projection, selectedId, centerId, resetKey, sessionKey])
  function zoom(factor: number) {
    const cy = graph.current
    if (cy && canvas.current) cy.zoom({ level: cy.zoom() * factor,
      renderedPosition: { x: canvas.current.clientWidth / 2, y: canvas.current.clientHeight / 2 } })
  }
  return <div className="graph-exploration">
    <div ref={canvas} className="graph-exploration__canvas" role="img" aria-label="可探索的知识网络" />
    {unavailable && <p role="alert">画布暂时不可用，可以通过右侧节点列表继续浏览。</p>}
    <div className="graph-exploration__controls" aria-label="画布视图">
      <button aria-label="放大" onClick={() => zoom(1.2)}><PlusIcon /></button>
      <button aria-label="缩小" onClick={() => zoom(1 / 1.2)}><MinusIcon /></button>
      <button aria-label="适应画布" onClick={() => graph.current?.fit(undefined, 80)}><CornersOutIcon /></button>
      <button aria-label="回到中心" onClick={() => {
        const cy = graph.current
        const target = centerId && cy?.getElementById(centerId)
        if (target && target.nonempty()) cy?.center(target)
        else cy?.fit(undefined, 80)
      }}><ArrowCounterClockwiseIcon /></button>
    </div>
  </div>
}
