import { getTextWidth } from '@evenrealities/pretext'

/**
 * Greedy word wrap using the same glyph metrics LVGL uses on the device, so a
 * line that fits here fits on the glasses. `measureTextWrap` only reports a
 * line count, not the lines themselves, so we wrap ourselves and use the
 * measurement to verify.
 */
export function wrapText(text: string, maxWidth: number): string[] {
  const words = text.split(/\s+/).filter(Boolean)
  const lines: string[] = []
  let line = ''

  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word
    if (getTextWidth(candidate) <= maxWidth) {
      line = candidate
      continue
    }
    if (line) lines.push(line)
    // A single word wider than the container: hard-split on characters.
    if (getTextWidth(word) > maxWidth) {
      let chunk = ''
      for (const ch of word) {
        if (getTextWidth(chunk + ch) > maxWidth && chunk) {
          lines.push(chunk)
          chunk = ch
        } else {
          chunk += ch
        }
      }
      line = chunk
    } else {
      line = word
    }
  }
  if (line) lines.push(line)
  return lines.length ? lines : ['']
}
