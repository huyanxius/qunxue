import cytoscape, { type Core, type ElementDefinition } from 'cytoscape'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CornersOutIcon, ShuffleIcon } from '@phosphor-icons/react'

import './ObsidianKnowledgeGraph.css'
import type { KnowledgeGraphProjection } from './types'

interface ObsidianKnowledgeGraphProps {
  readonly projection: KnowledgeGraphProjection
  readonly focusNodeId?: string
  readonly onExpandNode?: (nodeId: string) => void
  readonly onSelectEdge?: (edgeId: string) => void
  readonly onSelectKnowledge: (knowledgeId: string) => void
  readonly variant?: 'workspace' | 'preview'
}

function graphElements(
  projection: KnowledgeGraphProjection,
  focusNodeId?: string,
): ElementDefinition[] {
  const neighborIds = new Set(
    projection.edges.flatMap((edge) => (
      edge.source === focusNodeId ? [edge.target]
        : edge.target === focusNodeId ? [edge.source]
          : []
    )),
  )

  return [
    ...projection.nodes.map((node) => {
      const nodeType = node.nodeType ?? 'entry'
      const classes = [
        `node--${nodeType}`,
        node.id === focusNodeId ? 'node--focus' : '',
        neighborIds.has(node.id) ? 'node--neighbor' : '',
        focusNodeId && node.id !== focusNodeId && !neighborIds.has(node.id)
          ? 'node--context'
          : '',
      ].filter(Boolean).join(' ')
      return {
        classes,
        data: {
          id: node.id,
          label: node.label,
          nodeType,
          focus: node.id === focusNodeId,
        },
      }
    }),
    ...projection.edges.map((edge) => ({
      classes: [
        `edge--${edge.layer ?? 'reviewed'}`,
        edge.source === focusNodeId || edge.target === focusNodeId
          ? 'edge--neighbor'
          : 'edge--context',
        edge.direction === 'directed' || edge.direction === 'outbound'
          ? 'edge--directed'
          : '',
        edge.direction === 'bidirectional' ? 'edge--bidirectional' : '',
      ].filter(Boolean).join(' '),
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.layer === 'candidate'
          ? `候选 · ${edge.relationType}`
          : edge.relationType,
        layer: edge.layer ?? 'reviewed',
      },
    })),
  ]
}

function layoutOptions(
  hasFocus: boolean,
  hasEdges: boolean,
  animate = false,
  animationDuration = 560,
) {
  if (!hasFocus && !hasEdges) {
    return {
      name: 'circle',
      animate,
      animationDuration: animate ? animationDuration : 1200,
      animationEasing: 'ease-out-cubic',
      fit: true,
      padding: 96,
      spacingFactor: 1.35,
    }
  }
  return {
    name: 'cose',
    animate: animate ? 'end' : false,
    animationDuration: animate ? animationDuration : 1200,
    animationEasing: 'ease-out-cubic',
    componentSpacing: 56,
    edgeElasticity: 120,
    fit: true,
    gravity: 0.34,
    idealEdgeLength: 54,
    nestingFactor: 1.15,
    nodeOverlap: 14,
    nodeRepulsion: 90000,
    numIter: 800,
    padding: 72,
    randomize: true,
  }
}

function fitView(graph: Core, focusNodeId?: string, preview = false) {
  if (!focusNodeId) {
    const container = graph.container?.()
    const nodes = graph.nodes?.()
    const bounds = nodes?.boundingBox?.({ includeLabels: false })
    if (!bounds) return
    if (!container || bounds.w <= 0 || bounds.h <= 0) return
    const padding = preview
      ? 34
      : Math.min(container.clientWidth, container.clientHeight) * 0.22
    const zoom = Math.max(
      graph.minZoom(),
      Math.min(
        graph.maxZoom(),
        (container.clientWidth - padding * 2) / bounds.w,
        (container.clientHeight - padding * 2) / bounds.h,
      ) * (preview ? 0.9 : 1),
    )
    graph.viewport({
      zoom,
      pan: {
        x: container.clientWidth / 2 - (bounds.x1 + bounds.w / 2) * zoom,
        y: container.clientHeight / 2 - (bounds.y1 + bounds.h / 2) * zoom,
      },
    })
    return
  }
  const focus = graph.getElementById(focusNodeId)
  const container = graph.container()
  if (focus.empty() || !container) {
    graph.fit(graph.elements(), 72)
    return
  }
  const bounds = graph.elements().boundingBox({ includeLabels: false })
  const position = focus.position()
  const padding = 72
  const halfWidth = Math.max(position.x - bounds.x1, bounds.x2 - position.x, 1)
  const halfHeight = Math.max(position.y - bounds.y1, bounds.y2 - position.y, 1)
  const zoom = Math.max(
    graph.minZoom(),
    0.8,
    Math.min(
      graph.maxZoom(),
      (container.clientWidth - padding * 2) / (halfWidth * 2),
      (container.clientHeight - padding * 2) / (halfHeight * 2),
    ),
  )
  graph.viewport({
    zoom,
    pan: {
      x: container.clientWidth / 2 - position.x * zoom,
      y: container.clientHeight / 2 - position.y * zoom,
    },
  })
}

function shuffled<T>(values: readonly T[]): T[] {
  const result = [...values]
  for (let index = result.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1))
    const current = result[index]
    result[index] = result[swapIndex]
    result[swapIndex] = current
  }
  return result
}

function revealBatches(projection: KnowledgeGraphProjection): string[][] {
  if (projection.nodes.length === 0) return []

  const adjacency = new Map(
    projection.nodes.map((node) => [node.id, new Set<string>()]),
  )
  projection.edges.forEach((edge) => {
    adjacency.get(edge.source)?.add(edge.target)
    adjacency.get(edge.target)?.add(edge.source)
  })

  const root = [...projection.nodes].sort((left, right) => {
    const degreeDifference = (adjacency.get(right.id)?.size ?? 0)
      - (adjacency.get(left.id)?.size ?? 0)
    if (degreeDifference !== 0) return degreeDifference
    if (left.nodeType === right.nodeType) return 0
    return left.nodeType === 'dimension' ? -1 : 1
  })[0]
  const distance = new Map<string, number>([[root.id, 0]])
  const queue = [root.id]

  for (let cursor = 0; cursor < queue.length; cursor += 1) {
    const nodeId = queue[cursor]
    const nextDistance = (distance.get(nodeId) ?? 0) + 1
    adjacency.get(nodeId)?.forEach((neighborId) => {
      if (distance.has(neighborId)) return
      distance.set(neighborId, nextDistance)
      queue.push(neighborId)
    })
  }

  const layers = new Map<number, string[]>()
  projection.nodes.forEach((node) => {
    const layer = distance.get(node.id) ?? Number.MAX_SAFE_INTEGER
    const layerNodes = layers.get(layer) ?? []
    layerNodes.push(node.id)
    layers.set(layer, layerNodes)
  })

  return [...layers.entries()]
    .sort(([left], [right]) => left - right)
    .flatMap(([, nodeIds]) => {
      const orderedIds = shuffled(nodeIds)
      const batchSize = Math.max(1, Math.ceil(orderedIds.length / 3))
      const batches: string[][] = []
      for (let index = 0; index < orderedIds.length; index += batchSize) {
        batches.push(orderedIds.slice(index, index + batchSize))
      }
      return batches
    })
}

const graphStyle: cytoscape.StylesheetJson = [
  {
    selector: 'node',
    style: {
      'background-color': '#7f929f',
      'border-color': '#f7fafc',
      'border-width': 1.5,
      color: '#33404a',
      'font-size': 10,
      height: 10,
      label: 'data(label)',
      'min-zoomed-font-size': 8,
      opacity: 0.92,
      shape: 'ellipse',
      'text-background-color': '#fcfdfe',
      'text-background-opacity': 0,
      'text-background-padding': '2px',
      'text-background-shape': 'roundrectangle',
      'text-halign': 'center',
      'text-margin-y': -8,
      'text-outline-color': '#fcfdfe',
      'text-outline-opacity': 0.92,
      'text-outline-width': 2,
      'text-valign': 'top',
      'transition-duration': 420,
      'transition-property': 'background-color, border-color, height, opacity, text-opacity, width',
      'transition-timing-function': 'ease-out-cubic',
      width: 10,
      'z-index': 2,
    },
  },
  {
    selector: 'node.node--dimension',
    style: {
      'background-color': '#264d68',
      'border-color': '#dcebf4',
      'border-width': 2,
      color: '#173f5f',
      'font-size': 10,
      'font-weight': 700,
      height: 16,
      'min-zoomed-font-size': 9,
      'text-margin-y': -10,
      width: 16,
      'z-index': 8,
    },
  },
  {
    selector: 'node.node--category',
    style: {
      'background-color': '#6f8797',
      height: 12,
      width: 12,
      'z-index': 5,
    },
  },
  {
    selector: 'node.node--neighbor',
    style: {
      'background-color': '#3e7cb1',
      height: 11,
      opacity: 1,
      width: 11,
      'z-index': 7,
    },
  },
  {
    selector: 'node.node--focus',
    style: {
      'background-color': '#173f5f',
      'border-color': '#9fc6df',
      'border-width': 3,
      color: '#173f5f',
      'font-size': 11,
      'font-weight': 700,
      height: 16,
      'min-zoomed-font-size': 9,
      'text-margin-y': -11,
      'underlay-color': '#9fc6df',
      'underlay-opacity': 0.2,
      'underlay-padding': 5,
      'underlay-shape': 'ellipse',
      width: 16,
      'z-index': 12,
    },
  },
  {
    selector: 'node.node--unreviewed',
    style: { 'border-color': '#b48752' },
  },
  {
    selector: 'node.node--context',
    style: { opacity: 0.62 },
  },
  {
    selector: 'node.is-hovered, node:selected',
    style: {
      'background-color': '#173f5f',
      'border-color': '#9fc6df',
      'border-width': 4,
      opacity: 1,
      'z-index': 14,
    },
  },
  {
    selector: 'node.is-dimmed',
    style: { opacity: 0.12 },
  },
  {
    selector: 'edge',
    style: {
      'curve-style': 'straight',
      'line-color': '#c8d1d7',
      opacity: 0.72,
      'target-arrow-shape': 'none',
      'transition-duration': 480,
      'transition-property': 'line-color, opacity, width',
      'transition-timing-function': 'ease-out-cubic',
      width: 0.8,
      'z-index': 1,
    },
  },
  {
    selector: 'edge.edge--structure',
    style: {
      'line-color': '#c8d1d7',
      opacity: 0.58,
      width: 0.7,
    },
  },
  {
    selector: 'edge.edge--reviewed',
    style: {
      'line-color': '#3e7cb1',
      opacity: 0.9,
      'target-arrow-color': '#3e7cb1',
      width: 1.8,
    },
  },
  {
    selector: 'edge.edge--candidate',
    style: {
      'line-color': '#a56b2a',
      'line-style': 'dashed',
      opacity: 0.88,
      'target-arrow-color': '#a56b2a',
      width: 1.6,
    },
  },
  {
    selector: 'edge.edge--directed',
    style: {
      'arrow-scale': 0.65,
      'target-arrow-shape': 'triangle',
    },
  },
  {
    selector: 'edge.edge--bidirectional',
    style: {
      'arrow-scale': 0.65,
      'source-arrow-color': '#3e7cb1',
      'source-arrow-shape': 'triangle',
      'target-arrow-shape': 'triangle',
    },
  },
  {
    selector: 'edge.edge--context',
    style: { opacity: 0.42 },
  },
  {
    selector: 'edge.is-hovered, edge:selected',
    style: {
      color: '#33404a',
      'font-size': 9,
      label: 'data(label)',
      opacity: 1,
      'text-background-color': '#fcfdfe',
      'text-background-opacity': 0.92,
      'text-background-padding': '3px',
      width: 2.2,
      'z-index': 10,
    },
  },
  {
    selector: 'edge.is-dimmed',
    style: { opacity: 0.08 },
  },
]

const workspaceGraphStyle: cytoscape.StylesheetJson = [
  ...graphStyle.map((rule) => {
    if (
      !('style' in rule)
      || (rule.selector !== 'node' && rule.selector !== 'edge')
    ) return rule
    return {
      ...rule,
      style: {
        ...rule.style,
        'transition-duration': 0,
      },
    }
  }),
  {
    selector: 'node',
    style: {
      'background-color': '#8d9295',
      'border-color': '#ffffff',
      color: '#303030',
      'text-background-color': '#ffffff',
      'text-outline-color': '#ffffff',
      'font-family': '"Songti SC", "Noto Serif CJK SC", Georgia, serif',
    },
  },
  {
    selector: 'node.node--dimension',
    style: {
      'background-color': '#1d1f20',
      'border-color': '#d9dcde',
      color: '#111111',
      height: 20,
      'text-margin-y': -12,
      width: 20,
    },
  },
  {
    selector: 'node.node--category',
    style: { 'background-color': '#6d7376' },
  },
  {
    selector: 'node.node--neighbor',
    style: { 'background-color': '#3f464b' },
  },
  {
    selector: 'node.node--focus',
    style: {
      'background-color': '#111111',
      'border-color': '#b9bdc0',
      color: '#111111',
      'underlay-color': '#81878a',
    },
  },
  {
    selector: 'node.node--context',
    style: { opacity: 0.42, 'text-opacity': 0 },
  },
  {
    selector: 'node.is-hovered, node:selected',
    style: {
      'background-color': '#111111',
      'border-color': '#b9bdc0',
      'text-opacity': 1,
    },
  },
  {
    selector: 'node.is-entering',
    style: { opacity: 0, 'text-opacity': 0 },
  },
  {
    selector: 'edge.is-entering',
    style: { opacity: 0 },
  },
  {
    selector: 'edge.edge--reviewed',
    style: {
      'line-color': '#3f464b',
      'target-arrow-color': '#3f464b',
    },
  },
  {
    selector: 'edge.edge--bidirectional',
    style: { 'source-arrow-color': '#3f464b' },
  },
]

const previewGraphStyle: cytoscape.StylesheetJson = [
  ...workspaceGraphStyle,
  {
    selector: 'node',
    style: {
      'font-size': 11,
      height: 13,
      'min-zoomed-font-size': 7,
      'text-margin-y': -9,
      'transition-duration': 780,
      width: 13,
    },
  },
  {
    selector: 'edge',
    style: { 'transition-duration': 920 },
  },
  {
    selector: 'node.node--dimension',
    style: { 'font-size': 12, height: 22, width: 22 },
  },
  {
    selector: 'node.node--category',
    style: { height: 17, width: 17 },
  },
  {
    selector: 'edge.edge--structure',
    style: { opacity: 0.68, width: 1.05 },
  },
  {
    selector: 'node.node--neighbor',
    style: {
      height: 18,
      opacity: 1,
      width: 18,
    },
  },
  {
    selector: 'node.node--focus',
    style: {
      'border-width': 3.5,
      'font-size': 13,
      height: 26,
      'min-zoomed-font-size': 8,
      'text-background-opacity': 0.9,
      'text-margin-y': -15,
      'underlay-opacity': 0.28,
      'underlay-padding': 9,
      width: 26,
    },
  },
  {
    selector: 'node.node--context',
    style: { opacity: 0.3 },
  },
  {
    selector: 'edge.edge--neighbor',
    style: {
      'line-color': '#8a6739',
      opacity: 0.96,
      width: 2,
    },
  },
  {
    selector: 'edge.edge--context',
    style: { opacity: 0.2 },
  },
  {
    selector: 'node.is-awaiting-reveal',
    style: {
      height: 2,
      opacity: 0,
      'text-opacity': 0,
      width: 2,
    },
  },
  {
    selector: 'edge.is-awaiting-reveal',
    style: { opacity: 0, width: 0.1 },
  },
]

export function ObsidianKnowledgeGraph({
  projection,
  focusNodeId,
  onExpandNode,
  onSelectEdge,
  onSelectKnowledge,
  variant = 'workspace',
}: ObsidianKnowledgeGraphProps) {
  const canvasRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<Core | undefined>(undefined)
  const onExpandNodeRef = useRef(onExpandNode)
  const onSelectEdgeRef = useRef(onSelectEdge)
  const onSelectKnowledgeRef = useRef(onSelectKnowledge)
  onExpandNodeRef.current = onExpandNode
  onSelectEdgeRef.current = onSelectEdge
  onSelectKnowledgeRef.current = onSelectKnowledge
  const [unavailable, setUnavailable] = useState(false)
  const [hoveredLabel, setHoveredLabel] = useState('')
  const [tourLabel, setTourLabel] = useState('')
  const [activationPoint, setActivationPoint] = useState<{
    key: number
    x: number
    y: number
  }>()
  const activationTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const elements = useMemo(
    () => graphElements(projection, focusNodeId),
    [focusNodeId, projection],
  )
  const hasEdges = projection.edges.length > 0
  const reduceMotion = typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const animateLayout = variant === 'preview' && !reduceMotion
  const layoutDuration = variant === 'preview' ? 1900 : 560

  useEffect(() => () => {
    if (activationTimerRef.current) clearTimeout(activationTimerRef.current)
  }, [])

  const fit = useCallback(() => {
    if (graphRef.current) fitView(graphRef.current, focusNodeId, variant === 'preview')
  }, [focusNodeId, variant])

  const relayout = useCallback(() => {
    const graph = graphRef.current
    if (!graph) return
    graph.one('layoutstop', () => fitView(graph, focusNodeId, variant === 'preview'))
    graph.layout(layoutOptions(
      Boolean(focusNodeId),
      hasEdges,
      !reduceMotion,
      layoutDuration,
    )).run()
  }, [focusNodeId, hasEdges, layoutDuration, reduceMotion, variant])

  useEffect(() => {
    if (!canvasRef.current || elements.length === 0) return
    const canvas = canvasRef.current
    setUnavailable(false)
    setTourLabel('')
    let graph: Core | undefined
    let resizeObserver: ResizeObserver | undefined
    let visibilityObserver: IntersectionObserver | undefined
    let frame = 0
    let tourInterval: ReturnType<typeof setInterval> | undefined
    let tourStartTimer: ReturnType<typeof setTimeout> | undefined
    let entryTimer: ReturnType<typeof setTimeout> | undefined
    const revealTimers: Array<ReturnType<typeof setTimeout>> = []
    let revealStarted = false
    let revealComplete = variant !== 'preview' || reduceMotion
    let pointerInside = false
    let inViewport = variant !== 'preview'
    let documentVisible = typeof document === 'undefined'
      || document.visibilityState !== 'hidden'
    let previousTourNodeId = ''
    let tourQueue: string[] = []

    const clearTourSchedule = () => {
      if (tourInterval) clearInterval(tourInterval)
      if (tourStartTimer) clearTimeout(tourStartTimer)
      tourInterval = undefined
      tourStartTimer = undefined
    }

    const canTour = () => (
      variant === 'preview'
      && !reduceMotion
      && !focusNodeId
      && revealComplete
      && inViewport
      && documentVisible
      && !pointerInside
      && Boolean(graph)
    )

    const refillTourQueue = () => {
      if (!graph) return
      const candidates = graph.nodes()
        .filter((node) => node.data('nodeType') === 'entry' && node.degree(false) > 0)
        .map((node) => node.id())
      tourQueue = shuffled(candidates)
      if (
        tourQueue.length > 1
        && tourQueue[0] === previousTourNodeId
      ) {
        const first = tourQueue.shift()
        if (first) tourQueue.push(first)
      }
    }

    const focusTourNode = (nodeId: string) => {
      if (!graph) return
      const selectedNode = graph.getElementById(nodeId)
      if (selectedNode.empty()) return
      const neighborIds = new Set(
        selectedNode.neighborhood('node').map((node) => node.id()),
      )

      graph.batch(() => {
        graph?.nodes().forEach((node) => {
          node.removeClass('node--focus node--neighbor node--context')
          if (node.id() === nodeId) node.addClass('node--focus')
          else if (neighborIds.has(node.id())) node.addClass('node--neighbor')
          else node.addClass('node--context')
        })
        graph?.edges().forEach((edge) => {
          edge.removeClass('edge--neighbor edge--context')
          if (edge.source().id() === nodeId || edge.target().id() === nodeId) {
            edge.addClass('edge--neighbor')
          } else {
            edge.addClass('edge--context')
          }
        })
      })
      previousTourNodeId = nodeId
      setTourLabel(selectedNode.data('label') ?? '')
    }

    const advanceTour = () => {
      if (!canTour()) return
      if (tourQueue.length === 0) refillTourQueue()
      const nextNodeId = tourQueue.shift()
      if (nextNodeId) focusTourNode(nextNodeId)
    }

    const scheduleTour = (delay = 720) => {
      clearTourSchedule()
      if (!canTour()) return
      tourStartTimer = setTimeout(() => {
        if (!canTour()) return
        advanceTour()
        tourInterval = setInterval(advanceTour, 4800)
      }, delay)
    }

    const revealPreview = () => {
      if (!graph || revealStarted || variant !== 'preview') return
      revealStarted = true
      if (reduceMotion) {
        graph.elements().removeClass('is-awaiting-reveal')
        revealComplete = true
        return
      }

      const batches = revealBatches(projection)
      batches.forEach((nodeIds, index) => {
        const timer = setTimeout(() => {
          if (!graph) return
          graph.batch(() => {
            nodeIds.forEach((nodeId) => {
              graph?.getElementById(nodeId).removeClass('is-awaiting-reveal')
            })
            graph.edges().forEach((edge) => {
              if (
                !edge.source().hasClass('is-awaiting-reveal')
                && !edge.target().hasClass('is-awaiting-reveal')
              ) {
                edge.removeClass('is-awaiting-reveal')
              }
            })
          })
        }, 280 + index * 180)
        revealTimers.push(timer)
      })

      const completionTimer = setTimeout(() => {
        graph?.elements().removeClass('is-awaiting-reveal')
        revealComplete = true
        scheduleTour(1500)
      }, 520 + batches.length * 180)
      revealTimers.push(completionTimer)
    }

    const pauseForPointer = () => {
      pointerInside = true
      clearTourSchedule()
    }

    const resumeAfterPointer = () => {
      pointerInside = false
      setHoveredLabel('')
      scheduleTour(1500)
    }

    const handleVisibilityChange = () => {
      documentVisible = document.visibilityState !== 'hidden'
      if (documentVisible) scheduleTour(1000)
      else clearTourSchedule()
    }

    try {
      graph = cytoscape({
        autoungrabify: false,
        boxSelectionEnabled: false,
        container: canvas,
        elements,
        layout: layoutOptions(
          Boolean(focusNodeId),
          hasEdges,
          animateLayout,
          layoutDuration,
        ),
        maxZoom: 3.2,
        minZoom: 0.16,
        style: variant === 'preview' ? previewGraphStyle : workspaceGraphStyle,
        userPanningEnabled: true,
        userZoomingEnabled: variant === 'workspace',
      })
      graphRef.current = graph
      if (variant === 'preview') {
        if (!reduceMotion) graph.elements().addClass?.('is-awaiting-reveal')
        graph.one('layoutstop', () => fitView(graph!, focusNodeId, true))
      } else if (!reduceMotion) {
        graph.elements().addClass?.('is-entering')
        entryTimer = setTimeout(() => {
          graph?.elements().removeClass('is-entering')
        }, 80)
      }
      graph.on('tap', 'node', (event) => {
        const nodeType = event.target.data('nodeType') ?? 'entry'
        const nodeId = event.target.id()
        if (!reduceMotion) {
          const point = event.target.renderedPosition?.()
          if (point) {
            setActivationPoint({ key: Date.now(), x: point.x, y: point.y })
            if (activationTimerRef.current) clearTimeout(activationTimerRef.current)
            activationTimerRef.current = setTimeout(() => {
              setActivationPoint(undefined)
            }, 520)
          }
        }
        if (nodeType === 'entry') onSelectKnowledgeRef.current(nodeId)
        else onExpandNodeRef.current?.(nodeId)
      })
      graph.on('tap', 'edge', (event) => {
        event.target.select()
        onSelectEdgeRef.current?.(event.target.id())
      })
      graph.on('mouseover', 'node', (event) => {
        const neighborhood = event.target.closedNeighborhood()
        canvas.style.cursor = 'pointer'
        graph?.elements().addClass('is-dimmed')
        neighborhood.removeClass('is-dimmed').addClass('is-hovered')
        setHoveredLabel(event.target.data('label') ?? '')
      })
      graph.on('mouseout', 'node', () => {
        canvas.style.cursor = ''
        graph?.elements().removeClass('is-dimmed is-hovered')
        setHoveredLabel('')
      })
      graph.on('mouseover', 'edge', (event) => event.target.addClass('is-hovered'))
      graph.on('mouseout', 'edge', (event) => event.target.removeClass('is-hovered'))
      canvas.addEventListener('pointerenter', pauseForPointer)
      canvas.addEventListener('pointerleave', resumeAfterPointer)
      document.addEventListener('visibilitychange', handleVisibilityChange)
      frame = globalThis.requestAnimationFrame?.(() => {
        if (graph) fitView(graph, focusNodeId, variant === 'preview')
      }) ?? 0
      if (typeof ResizeObserver !== 'undefined') {
        resizeObserver = new ResizeObserver(() => graph?.resize())
        resizeObserver.observe(canvas)
      }
      if (variant === 'preview' && typeof IntersectionObserver !== 'undefined') {
        visibilityObserver = new IntersectionObserver(([entry]) => {
          inViewport = entry?.isIntersecting ?? false
          if (inViewport) {
            revealPreview()
            scheduleTour(1200)
          } else {
            clearTourSchedule()
          }
        }, { threshold: 0.28 })
        visibilityObserver.observe(canvas)
      } else if (variant === 'preview') {
        inViewport = true
        revealPreview()
      }
    } catch {
      setUnavailable(true)
    }

    return () => {
      if (frame) globalThis.cancelAnimationFrame?.(frame)
      clearTourSchedule()
      if (entryTimer) clearTimeout(entryTimer)
      revealTimers.forEach((timer) => clearTimeout(timer))
      resizeObserver?.disconnect()
      visibilityObserver?.disconnect()
      canvas.removeEventListener('pointerenter', pauseForPointer)
      canvas.removeEventListener('pointerleave', resumeAfterPointer)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      graphRef.current = undefined
      graph?.destroy()
    }
  }, [
    animateLayout,
    elements,
    focusNodeId,
    hasEdges,
    layoutDuration,
    projection,
    reduceMotion,
    variant,
  ])

  const visibleLabel = hoveredLabel || tourLabel

  return (
    <section className={`obsidian-knowledge-graph obsidian-knowledge-graph--${variant}`} aria-label="节点式知识图谱">
      <div className="obsidian-knowledge-graph__controls">
        <span>{projection.nodes.length} 节点 · {projection.edges.length} 关系</span>
        {variant === 'workspace' ? (
          <div>
            <button type="button" aria-label="适应画布" title="适应画布" onClick={fit}>
              <CornersOutIcon size={15} aria-hidden="true" />
            </button>
            <button type="button" aria-label="重新布局" title="重新布局" onClick={relayout}>
              <ShuffleIcon size={15} aria-hidden="true" />
            </button>
          </div>
        ) : (
          <span className="obsidian-knowledge-graph__tour-status">
            <i aria-hidden="true" />
            {reduceMotion ? '拖动节点探索' : '自动巡游 · 移入接管'}
          </span>
        )}
      </div>
      {visibleLabel ? (
        <p className="obsidian-knowledge-graph__hover">
          <span>{hoveredLabel ? '当前节点' : '正在巡游'}</span>
          {visibleLabel}
        </p>
      ) : null}
      {variant === 'workspace' && activationPoint ? (
        <i
          key={activationPoint.key}
          className="obsidian-knowledge-graph__activation"
          style={{ left: activationPoint.x, top: activationPoint.y }}
          aria-hidden="true"
        />
      ) : null}
      {unavailable ? (
        <p className="obsidian-knowledge-graph__notice" role="alert">
          {variant === 'preview'
            ? '节点画布暂时不可用，可以进入完整图谱继续浏览。'
            : '节点画布暂时不可用；右侧搜索、详情与证据仍可继续使用。'}
        </p>
      ) : null}
      {variant === 'preview' && !focusNodeId && !hasEdges ? (
        <p className="obsidian-knowledge-graph__notice" role="status">
          七维入口已就绪。搜索条目，或选择维度节点开始探索。
        </p>
      ) : null}
      {variant === 'workspace' && !focusNodeId && !hasEdges ? (
        <div className="obsidian-knowledge-graph__start" role="status">
          <strong>选择一个维度开始</strong>
          <span>或在右侧搜索具体概念</span>
        </div>
      ) : null}
      <div
        ref={canvasRef}
        className="obsidian-knowledge-graph__canvas"
        role="img"
        aria-label={variant === 'preview' ? '节点式知识图谱画布' : 'Obsidian 式节点知识图谱'}
        hidden={unavailable}
      />
    </section>
  )
}
