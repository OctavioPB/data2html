import DataEditor, {
  GridCellKind,
  type GridCell,
  type GridColumn,
  type Item,
  type Rectangle,
  type Theme,
} from '@glideapps/glide-data-grid'
import '@glideapps/glide-data-grid/dist/index.css'
import { useCallback, useMemo } from 'react'

import type { Schemas } from '../api/client'
import { usePrefersDark } from './usePrefersDark'
import type { Cell } from './useExplorePages'

type SortKey = Schemas['SortKey']

const DARK: Partial<Theme> = {
  accentColor: '#6c9cf0',
  accentLight: 'rgba(108, 156, 240, 0.18)',
  textDark: '#e8e9ec',
  textMedium: '#b8bcc6',
  textLight: '#9095a0',
  textHeader: '#b8bcc6',
  textBubble: '#e8e9ec',
  bgCell: '#1b1d21',
  bgCellMedium: '#202227',
  bgHeader: '#16171b',
  bgHeaderHasFocus: '#24262c',
  bgHeaderHovered: '#24262c',
  bgBubble: '#2b2e34',
  bgSearchResult: '#3a2f12',
  borderColor: '#2b2e34',
  horizontalBorderColor: '#24262c',
  linkColor: '#6c9cf0',
}

const NUMERIC = /^(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT|U\w*INT|FLOAT|DOUBLE|REAL|DECIMAL)/i
const nf = new Intl.NumberFormat('es-MX', { maximumFractionDigits: 6 })

function toGridCell(v: Cell | undefined): GridCell {
  if (v === undefined) return { kind: GridCellKind.Loading, allowOverlay: false }
  if (v === null) return { kind: GridCellKind.Text, data: '', displayData: '∅', allowOverlay: false, style: 'faded' }
  if (typeof v === 'number') return { kind: GridCellKind.Number, data: v, displayData: nf.format(v), allowOverlay: false, readonly: true }
  if (typeof v === 'boolean') return { kind: GridCellKind.Boolean, data: v, allowOverlay: false, readonly: true }
  return { kind: GridCellKind.Text, data: v, displayData: v, allowOverlay: true, readonly: true }
}

interface Props {
  columns: Schemas['ExploreColumn'][]
  rows: number
  getRow: (row: number) => Cell[] | undefined
  ensureRange: (start: number, end: number) => void
  sort: SortKey[]
  onSort: (sort: SortKey[]) => void
}

export function ExploreGrid({ columns, rows, getRow, ensureRange, sort, onSort }: Props) {
  const dark = usePrefersDark()

  const gridColumns = useMemo<GridColumn[]>(
    () =>
      columns.map((c) => {
        const s = sort.find((k) => k.column === c.name)
        const arrow = s ? (s.desc ? ' ▼' : ' ▲') : ''
        return {
          id: c.name,
          title: `${c.computed ? 'ƒ ' : ''}${c.name}${arrow}`,
          width: NUMERIC.test(c.type) ? 120 : 170,
          themeOverride: c.computed ? { bgHeader: dark ? '#1f2633' : '#eef3fd' } : undefined,
        }
      }),
    [columns, sort, dark],
  )

  const getCellContent = useCallback(
    ([col, row]: Item): GridCell => toGridCell(getRow(row)?.[col]),
    [getRow],
  )

  const onVisibleRegionChanged = useCallback(
    (r: Rectangle) => ensureRange(r.y, r.y + r.height),
    [ensureRange],
  )

  // Clic en encabezado: sin orden → ascendente → descendente → sin orden (una columna a la vez)
  const onHeaderClicked = useCallback(
    (col: number) => {
      const name = columns[col]?.name
      if (!name) return
      const cur = sort.find((k) => k.column === name)
      onSort(!cur ? [{ column: name, desc: false }] : cur.desc ? [] : [{ column: name, desc: true }])
    },
    [columns, sort, onSort],
  )

  return (
    <DataEditor
      columns={gridColumns}
      rows={rows}
      getCellContent={getCellContent}
      onVisibleRegionChanged={onVisibleRegionChanged}
      onHeaderClicked={onHeaderClicked}
      rowMarkers="number"
      smoothScrollY
      getCellsForSelection
      theme={dark ? DARK : undefined}
      width="100%"
      height="100%"
    />
  )
}
