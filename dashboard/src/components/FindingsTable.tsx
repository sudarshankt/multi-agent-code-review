import React from 'react'
import { Finding } from '../api/client'
import { AlertTriangle, Bug, Zap, Eye } from 'lucide-react'

interface FindingsTableProps {
  findings: Finding[]
}

const severityColors: Record<string, string> = {
  critical: 'bg-red-100 text-red-800 border-red-300',
  high: 'bg-orange-100 text-orange-800 border-orange-300',
  medium: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  low: 'bg-blue-100 text-blue-800 border-blue-300',
  info: 'bg-gray-100 text-gray-800 border-gray-300',
}

const categoryIcons: Record<string, React.ReactNode> = {
  security: <AlertTriangle className="w-4 h-4" />,
  bug_detection: <Bug className="w-4 h-4" />,
  performance: <Zap className="w-4 h-4" />,
  style: <Eye className="w-4 h-4" />,
}

export const FindingsTable: React.FC<FindingsTableProps> = ({ findings }) => {
  if (findings.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        No findings
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 border-b">
          <tr>
            <th className="px-4 py-2 text-left font-semibold">Category</th>
            <th className="px-4 py-2 text-left font-semibold">Severity</th>
            <th className="px-4 py-2 text-left font-semibold">Title</th>
            <th className="px-4 py-2 text-left font-semibold">File</th>
            <th className="px-4 py-2 text-left font-semibold">Suggestion</th>
            <th className="px-4 py-2 text-left font-semibold">CWE</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {findings.map((finding) => (
            <tr key={finding.id} className="hover:bg-gray-50">
              <td className="px-4 py-2 text-center">
                {categoryIcons[finding.category] || '—'}
              </td>
              <td className="px-4 py-2">
                <span className={`px-2 py-1 rounded border text-xs font-semibold ${severityColors[finding.severity] || severityColors.info}`}>
                  {finding.severity}
                </span>
              </td>
              <td className="px-4 py-2">
                <div className="font-medium">{finding.title}</div>
                <div className="text-xs text-gray-600">{finding.description}</div>
              </td>
              <td className="px-4 py-2 text-xs font-mono">
                {finding.location.file_path}
                {finding.location.start_line && (
                  <span className="text-gray-500">:{finding.location.start_line}</span>
                )}
              </td>
              <td className="px-4 py-2 text-xs max-w-xs">
                {finding.suggestion ? (
                  <div className="text-gray-700">{finding.suggestion}</div>
                ) : (
                  <span className="text-gray-400">—</span>
                )}
              </td>
              <td className="px-4 py-2 text-xs font-mono">
                {finding.cwe_id ? (
                  <a
                    href={`https://cwe.mitre.org/data/definitions/${finding.cwe_id.replace('CWE-', '')}.html`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline"
                  >
                    {finding.cwe_id}
                  </a>
                ) : (
                  <span className="text-gray-400">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
