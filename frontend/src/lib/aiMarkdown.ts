/** Lightweight safe Markdown for AI chat bubbles (no HTML passthrough). */

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function formatInline(text: string): string {
  let s = escapeHtml(text)
  s = s.replace(/`([^`]+)`/g, '<code class="ai-md-code">$1</code>')
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/__([^_]+)__/g, '<u>$1</u>')
  s = s.replace(/==([^=]+)==/g, '<mark class="ai-md-mark">$1</mark>')
  s = s.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>')
  return s
}

export function renderAiMarkdown(source: string): string {
  const raw = source.replace(/\r\n/g, '\n').trim()
  if (!raw) return ''

  const blocks: string[] = []
  const fence = /```([\w-]*)\n?([\s\S]*?)```/g
  let last = 0
  let match: RegExpExecArray | null
  while ((match = fence.exec(raw)) !== null) {
    if (match.index > last) {
      blocks.push(formatParagraphs(raw.slice(last, match.index)))
    }
    const lang = escapeHtml(match[1] || '')
    const code = escapeHtml(match[2].replace(/\n$/, ''))
    blocks.push(
      `<pre class="ai-md-pre"${lang ? ` data-lang="${lang}"` : ''}><code>${code}</code></pre>`,
    )
    last = match.index + match[0].length
  }
  if (last < raw.length) {
    blocks.push(formatParagraphs(raw.slice(last)))
  }
  return blocks.join('')
}

function formatParagraphs(chunk: string): string {
  const parts = chunk.trim().split(/\n{2,}/)
  return parts
    .map((p) => {
      const heading = p.match(/^(#{1,3})\s+(.+)$/)
      if (heading && !p.includes('\n')) {
        const level = heading[1].length
        return `<h${level} class="ai-md-h">${formatInline(heading[2])}</h${level}>`
      }
      const lines = p.split('\n').map((line) => {
        const h = line.match(/^(#{1,3})\s+(.+)$/)
        if (h) {
          const level = h[1].length
          return `<h${level} class="ai-md-h">${formatInline(h[2])}</h${level}>`
        }
        const bullet = line.match(/^[-*]\s+(.+)$/)
        if (bullet) return `<li>${formatInline(bullet[1])}</li>`
        const numbered = line.match(/^\d+\.\s+(.+)$/)
        if (numbered) return `<li>${formatInline(numbered[1])}</li>`
        return formatInline(line)
      })
      if (lines.every((l) => l.startsWith('<li>'))) {
        return `<ul class="ai-md-list">${lines.join('')}</ul>`
      }
      if (lines.every((l) => l.startsWith('<h'))) {
        return lines.join('')
      }
      return `<p class="ai-md-p">${lines.join('<br>')}</p>`
    })
    .join('')
}
