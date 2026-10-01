import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { FrontierSourceFigure } from './FrontierSourceFigure'
import type { FrontierMedia } from './model'

const media: FrontierMedia = { url: 'https://publisher.example/figure-1.png', caption: '研究中的机制示意图', source_url: 'https://publisher.example/paper', kind: 'figure', alt: '组织机制的三个关联环节' }
afterEach(cleanup)
it('renders an attributed source image without leaking the private page URL', () => {
  render(<FrontierSourceFigure media={media} />)
  const image = screen.getByRole('img', { name: media.alt! })
  expect(image).toHaveAttribute('src', media.url)
  expect(image).toHaveAttribute('loading', 'lazy')
  expect(image).toHaveAttribute('referrerpolicy', 'no-referrer')
  expect(screen.getByRole('link', { name: '图片来源' })).toHaveAttribute('href', media.source_url)
  expect(screen.getByText(media.caption)).toBeVisible()
})
it('hides failed and insecure media rather than showing a broken placeholder', () => {
  const { container, rerender } = render(<FrontierSourceFigure media={media} />)
  fireEvent.error(screen.getByRole('img'))
  expect(container.querySelector('figure')).not.toBeInTheDocument()
  rerender(<FrontierSourceFigure media={{ ...media, url: 'http://publisher.example/other.png' }} />)
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
  rerender(<FrontierSourceFigure media={{ ...media, url: 'https://publisher.example/other.png' }} />)
  expect(screen.getByRole('img')).toBeInTheDocument()
})
