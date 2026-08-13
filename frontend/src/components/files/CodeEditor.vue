<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import jsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker'
import cssWorker from 'monaco-editor/esm/vs/language/css/css.worker?worker'
import htmlWorker from 'monaco-editor/esm/vs/language/html/html.worker?worker'
import tsWorker from 'monaco-editor/esm/vs/language/typescript/ts.worker?worker'
import { useThemeStore } from '@/stores/theme'

const props = withDefaults(
  defineProps<{
    modelValue: string
    path: string
    language?: string
    readonly?: boolean
    colorMode?: 'auto' | 'light' | 'dark'
    fontSize?: number
    wordWrap?: boolean
    minimap?: boolean
  }>(),
  { readonly: false, colorMode: 'auto', fontSize: 14, wordWrap: true, minimap: true },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  save: []
}>()

const theme = useThemeStore()
const host = ref<HTMLDivElement | null>(null)
const lineCount = ref(1)
const cursorLabel = ref('Ln 1, Col 1')

let editor: monaco.editor.IStandaloneCodeEditor | null = null
let model: monaco.editor.ITextModel | null = null
let contentDisposable: monaco.IDisposable | null = null
let cursorDisposable: monaco.IDisposable | null = null
let workersReady = false

function ensureWorkers() {
  if (workersReady) return
  ;(globalThis as typeof globalThis & { MonacoEnvironment?: MonacoEnvironment }).MonacoEnvironment = {
    getWorker(_: string, label: string) {
      if (label === 'json') return new jsonWorker()
      if (label === 'css' || label === 'scss' || label === 'less') return new cssWorker()
      if (label === 'html' || label === 'handlebars' || label === 'razor') return new htmlWorker()
      if (label === 'typescript' || label === 'javascript') return new tsWorker()
      return new editorWorker()
    },
  }
  workersReady = true
}

const LANGUAGE_MAP: Record<string, string> = {
  ts: 'typescript',
  tsx: 'typescript',
  js: 'javascript',
  jsx: 'javascript',
  mjs: 'javascript',
  cjs: 'javascript',
  vue: 'html',
  py: 'python',
  php: 'php',
  rb: 'ruby',
  go: 'go',
  rs: 'rust',
  java: 'java',
  kt: 'kotlin',
  c: 'c',
  h: 'c',
  cpp: 'cpp',
  cc: 'cpp',
  cxx: 'cpp',
  hpp: 'cpp',
  cs: 'csharp',
  html: 'html',
  htm: 'html',
  css: 'css',
  scss: 'scss',
  less: 'less',
  json: 'json',
  jsonc: 'json',
  yaml: 'yaml',
  yml: 'yaml',
  toml: 'ini',
  xml: 'xml',
  svg: 'xml',
  md: 'markdown',
  markdown: 'markdown',
  sh: 'shell',
  bash: 'shell',
  zsh: 'shell',
  sql: 'sql',
  graphql: 'graphql',
  gql: 'graphql',
  ini: 'ini',
  conf: 'ini',
  cfg: 'ini',
  env: 'ini',
  dockerfile: 'dockerfile',
  txt: 'plaintext',
  log: 'plaintext',
  csv: 'plaintext',
}

function languageFromPath(path: string): string {
  const base = path.split('/').pop()?.toLowerCase() || ''
  if (base === 'dockerfile' || base.startsWith('dockerfile.')) return 'dockerfile'
  if (base === 'makefile' || base === 'gnumakefile') return 'plaintext'
  const ext = base.includes('.') ? base.slice(base.lastIndexOf('.') + 1) : ''
  return LANGUAGE_MAP[ext] || 'plaintext'
}

const language = computed(() => props.language || languageFromPath(props.path))
const languageLabel = computed(() => {
  const lang = language.value
  if (lang === 'plaintext') {
    const base = props.path.split('/').pop() || props.path
    const ext = base.includes('.') ? base.slice(base.lastIndexOf('.') + 1).toUpperCase() : 'TXT'
    return ext
  }
  return lang.toUpperCase()
})

function monacoTheme() {
  if (props.colorMode === 'dark') return 'vs-dark'
  if (props.colorMode === 'light') return 'vs'
  return theme.isDark ? 'vs-dark' : 'vs'
}

function lineHeightFor(size: number) {
  return Math.round(size * 1.55)
}

function applyViewOptions() {
  editor?.updateOptions({
    fontSize: props.fontSize,
    lineHeight: lineHeightFor(props.fontSize),
    wordWrap: props.wordWrap ? 'on' : 'off',
    wrappingStrategy: 'advanced',
    // Avoid horizontal scroll when wrapped; keep long lines readable
    wordWrapColumn: 120,
    wrappingIndent: 'same',
    scrollBeyondLastColumn: 0,
  })
}

function syncCursor() {
  if (!editor) return
  const pos = editor.getPosition()
  if (!pos) return
  cursorLabel.value = `Ln ${pos.lineNumber}, Col ${pos.column}`
}

function createEditor() {
  if (!host.value) return
  ensureWorkers()

  model = monaco.editor.createModel(props.modelValue, language.value, monaco.Uri.file(props.path || 'untitled.txt'))
  editor = monaco.editor.create(host.value, {
    model,
    theme: monacoTheme(),
    readOnly: props.readonly,
    automaticLayout: true,
    fontSize: props.fontSize,
    fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', 'Cascadia Code', Menlo, Monaco, Consolas, monospace",
    fontLigatures: true,
    lineHeight: lineHeightFor(props.fontSize),
    minimap: { enabled: props.minimap, scale: 1, showSlider: 'mouseover' },
    scrollBeyondLastLine: false,
    smoothScrolling: true,
    cursorBlinking: 'smooth',
    cursorSmoothCaretAnimation: 'on',
    renderLineHighlight: 'all',
    renderWhitespace: 'selection',
    bracketPairColorization: { enabled: true },
    guides: { bracketPairs: true, indentation: true },
    padding: { top: 12, bottom: 12 },
    tabSize: 2,
    wordWrap: props.wordWrap ? 'on' : 'off',
    wrappingStrategy: 'advanced',
    wrappingIndent: 'same',
    scrollBeyondLastColumn: 0,
    scrollbar: {
      verticalScrollbarSize: 10,
      horizontalScrollbarSize: 10,
      useShadows: false,
      horizontal: props.wordWrap ? 'hidden' : 'auto',
    },
    overviewRulerLanes: 0,
    fixedOverflowWidgets: true,
  })

  lineCount.value = model.getLineCount()
  syncCursor()

  contentDisposable = editor.onDidChangeModelContent(() => {
    if (!editor || !model) return
    lineCount.value = model.getLineCount()
    emit('update:modelValue', editor.getValue())
  })

  cursorDisposable = editor.onDidChangeCursorPosition(() => syncCursor())

  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
    if (!props.readonly) emit('save')
  })
}

function disposeEditor() {
  contentDisposable?.dispose()
  cursorDisposable?.dispose()
  contentDisposable = null
  cursorDisposable = null
  editor?.dispose()
  model?.dispose()
  editor = null
  model = null
}

onMounted(() => createEditor())
onBeforeUnmount(() => disposeEditor())

watch(
  () => props.modelValue,
  (value) => {
    if (!editor || !model) return
    const current = editor.getValue()
    if (current === value) return
    // Progressive AI writes arrive as cumulative content; append instead of
    // setValue so scroll/cursor/undo behave like live typing.
    if (value.startsWith(current) && value.length > current.length) {
      const end = model.getFullModelRange().getEndPosition()
      editor.executeEdits('ai-stream', [
        {
          range: monaco.Range.fromPositions(end, end),
          text: value.slice(current.length),
          forceMoveMarkers: true,
        },
      ])
      editor.revealLineInCenterIfOutsideViewport(model.getLineCount())
    } else {
      editor.setValue(value)
    }
    lineCount.value = model.getLineCount()
  },
)

watch(
  () => [props.path, props.language],
  () => {
    if (!model) return
    monaco.editor.setModelLanguage(model, language.value)
  },
)

watch(
  () => props.minimap,
  (enabled) => {
    editor?.updateOptions({ minimap: { enabled, scale: 1, showSlider: 'mouseover' } })
  },
)

watch(
  () => props.readonly,
  (readonly) => {
    editor?.updateOptions({ readOnly: readonly })
  },
)

watch(
  () => theme.isDark,
  () => {
    monaco.editor.setTheme(monacoTheme())
  },
)

watch(
  () => props.colorMode,
  () => {
    monaco.editor.setTheme(monacoTheme())
  },
)

watch(
  () => [props.fontSize, props.wordWrap],
  () => {
    applyViewOptions()
    editor?.updateOptions({
      scrollbar: {
        verticalScrollbarSize: 10,
        horizontalScrollbarSize: 10,
        useShadows: false,
        horizontal: props.wordWrap ? 'hidden' : 'auto',
      },
    })
  },
)

defineExpose({
  focus: () => editor?.focus(),
  language,
})
</script>

<template>
  <div class="code-editor">
    <div ref="host" class="code-editor-host" />
    <footer class="code-editor-status">
      <span class="status-item">{{ languageLabel }}</span>
      <span class="status-sep" />
      <span class="status-item">{{ lineCount }} lines</span>
      <span class="status-sep" />
      <span class="status-item">{{ cursorLabel }}</span>
      <span class="status-sep" />
      <span class="status-item">{{ fontSize }}px</span>
      <span class="status-spacer" />
      <span class="status-item muted">{{ wordWrap ? 'Wrap' : 'No wrap' }}</span>
      <span class="status-sep" />
      <span class="status-item muted">UTF-8</span>
      <span class="status-sep" />
      <span class="status-item muted">LF</span>
      <span v-if="readonly" class="status-item readonly-badge">Read only</span>
      <span v-else class="status-item muted">⌘S to save</span>
    </footer>
  </div>
</template>

<style scoped>
.code-editor {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
  overflow: hidden;
  border-radius: 0.75rem;
  border: 1px solid color-mix(in srgb, var(--color-border) 85%, transparent);
  background: var(--color-surface-raised);
}
.code-editor-host {
  flex: 1;
  min-height: 18rem;
  overflow: hidden;
}
.code-editor-status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  border-top: 1px solid color-mix(in srgb, var(--color-border) 80%, transparent);
  background: color-mix(in srgb, var(--color-surface) 70%, var(--color-surface-raised));
  padding: 0.35rem 0.75rem;
  font-size: 0.7rem;
  font-family: 'JetBrains Mono', 'SF Mono', Menlo, Monaco, Consolas, monospace;
  color: var(--color-text-muted);
}
.status-item { white-space: nowrap; }
.status-item.muted { opacity: 0.75; }
.status-sep {
  width: 1px;
  height: 0.75rem;
  background: color-mix(in srgb, var(--color-border) 90%, transparent);
}
.status-spacer { flex: 1; }
.readonly-badge {
  border-radius: 999px;
  background: rgb(245 158 11 / 0.15);
  color: #d97706;
  padding: 0.1rem 0.45rem;
}
:deep(.monaco-editor),
:deep(.monaco-editor .overflow-guard) {
  border-radius: 0.75rem 0.75rem 0 0;
}
</style>
