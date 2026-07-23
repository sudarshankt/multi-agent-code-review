import React from 'react'

interface DiffViewerProps {
  diff: string
  filePath?: string
}

interface DiffLine {
  type: 'added' | 'removed' | 'hunk' | 'context' | 'header'
  content: string
  lineNumber?: number
}

function parseDiff(diff: string): DiffLine[] {
  if (!diff) return []
  return diff.split('\n').map((line): DiffLine => {
    if (line.startsWith('+++') || line.startsWith('---')) return { type: 'header', content: line }
    if (line.startsWith('@@')) return { type: 'hunk', content: line }
    if (line.startsWith('+')) return { type: 'added', content: line.slice(1) }
    if (line.startsWith('-')) return { type: 'removed', content: line.slice(1) }
    return { type: 'context', content: line.startsWith(' ') ? line.slice(1) : line }
  })
}

const lineClass: Record<DiffLine['type'], string> = {
  added:   'bg-green-50 text-green-900 border-l-4 border-green-400',
  removed: 'bg-red-50 text-red-900 border-l-4 border-red-400',
  hunk:    'bg-blue-50 text-blue-700 text-xs font-medium',
  header:  'bg-gray-100 text-gray-500 text-xs',
  context: 'bg-white text-gray-800',
}

const linePrefix: Record<DiffLine['type'], string> = {
  added:   '+',
  removed: '-',
  hunk:    '',
  header:  '',
  context: ' ',
}

export const DiffViewer: React.FC<DiffViewerProps> = ({ diff, filePath }) => {
  const lines = parseDiff(diff)

  if (!diff) {
    return <p className="text-sm text-gray-400 italic">No diff available</p>
  }

  return (
    <div className="rounded border border-gray-200 overflow-hidden text-xs font-mono">
      {filePath && (
        <div className="bg-gray-800 text-gray-100 px-3 py-1.5 text-xs font-sans truncate">
          {filePath}
        </div>
      )}
      <div className="overflow-x-auto max-h-96 overflow-y-auto">
        <table className="w-full border-collapse">
          <tbody>
            {lines.map((line, idx) => (
              <tr key={idx} className={lineClass[line.type]}>
                <td className="select-none w-4 px-1.5 text-gray-400 text-right align-top border-r border-gray-200">
                  {linePrefix[line.type]}
                </td>
                <td className="px-2 py-0.5 whitespace-pre-wrap break-all align-top">
                  {line.content || ' '}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
