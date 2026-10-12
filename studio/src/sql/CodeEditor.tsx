import { sql, StandardSQL, type SQLNamespace } from '@codemirror/lang-sql'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { Compartment, EditorState, Prec } from '@codemirror/state'
import { EditorView, keymap } from '@codemirror/view'
import { basicSetup } from 'codemirror'
import { tags as t } from '@lezer/highlight'
import { useEffect, useRef } from 'react'

// Resaltado con tokens propios (--code-*): el de CodeMirror por defecto es para fondo claro y en
// oscuro los keywords quedaban ilegibles. Contraste de texto ≥ 4.5:1 en ambos modos.
const highlight = HighlightStyle.define([
  { tag: t.keyword, color: 'var(--code-keyword)', fontWeight: '600' },
  { tag: [t.string, t.special(t.string)], color: 'var(--code-string)' },
  { tag: [t.number, t.bool, t.null], color: 'var(--code-number)' },
  { tag: [t.typeName, t.standard(t.name)], color: 'var(--code-type)' },
  { tag: [t.lineComment, t.blockComment, t.comment], color: 'var(--muted)', fontStyle: 'italic' },
  { tag: [t.operator, t.punctuation, t.separator], color: 'var(--muted)' },
])

// Colores desde los tokens del studio: funciona igual en claro y oscuro
const theme = EditorView.theme({
  '&': { fontSize: '13px', backgroundColor: 'var(--panel)', color: 'var(--text)', height: '100%' },
  '.cm-scroller': { fontFamily: "ui-monospace, 'Cascadia Code', Consolas, monospace" },
  '.cm-gutters': { backgroundColor: 'var(--bg)', color: 'var(--muted)', border: 'none' },
  '.cm-activeLine, .cm-activeLineGutter': { backgroundColor: 'color-mix(in oklab, var(--accent) 8%, transparent)' },
  '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection': {
    backgroundColor: 'color-mix(in oklab, var(--accent) 30%, transparent)',
  },
  '.cm-cursor': { borderLeftColor: 'var(--text)' },
  '.cm-tooltip': { backgroundColor: 'var(--panel)', border: '1px solid var(--border)', color: 'var(--text)' },
  '.cm-tooltip-autocomplete ul li[aria-selected]': { backgroundColor: 'var(--accent)', color: '#fff' },
})

interface Props {
  value: string
  onChange: (value: string) => void
  onRun: () => void
  schema: SQLNamespace
}

export function CodeEditor({ value, onChange, onRun, schema }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const view = useRef<EditorView | null>(null)
  const lang = useRef(new Compartment())
  // los callbacks cambian en cada render; el editor se crea una vez y los lee de refs
  const cb = useRef({ onChange, onRun })
  cb.current = { onChange, onRun }

  useEffect(() => {
    const v = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: value,
        extensions: [
          Prec.highest(
            keymap.of([{ key: 'Mod-Enter', preventDefault: true, run: () => (cb.current.onRun(), true) }]),
          ),
          basicSetup,
          lang.current.of(sql({ dialect: StandardSQL, schema, upperCaseKeywords: true })),
          theme,
          syntaxHighlighting(highlight),
          EditorView.updateListener.of((u) => {
            if (u.docChanged) cb.current.onChange(u.state.doc.toString())
          }),
          EditorView.contentAttributes.of({ 'aria-label': 'Editor SQL' }),
        ],
      }),
    })
    view.current = v
    return () => v.destroy()
    // el editor vive mientras viva el componente; doc y esquema se sincronizan abajo
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // esquema nuevo (otra fuente) → reconfigurar el autocompletado
  useEffect(() => {
    view.current?.dispatch({
      effects: lang.current.reconfigure(sql({ dialect: StandardSQL, schema, upperCaseKeywords: true })),
    })
  }, [schema])

  // valor cambiado desde fuera (historial, guardadas) → reemplazar el documento
  useEffect(() => {
    const v = view.current
    if (v && v.state.doc.toString() !== value) {
      v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: value } })
    }
  }, [value])

  return <div className="code-editor" ref={host} />
}
