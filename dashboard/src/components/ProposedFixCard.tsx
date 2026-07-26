import React, { useState } from 'react'
import { CheckCircle, XCircle, ChevronDown, ChevronUp, FileCode } from 'lucide-react'
import { DiffViewer } from './DiffViewer'
import { ProposedFix } from '../api/client'

interface ProposedFixCardProps {
  fix: ProposedFix
  onApprove: (id: string) => void
  onReject: (id: string) => void
  isLoading?: boolean
}

const categoryColor: Record<string, string> = {
  security:      'bg-red-100 text-red-800',
  bug_detection: 'bg-orange-100 text-orange-800',
  style:         'bg-blue-100 text-blue-800',
  performance:   'bg-purple-100 text-purple-800',
}

const statusBorder: Record<string, string> = {
  pending:   'border-gray-200',
  approved:  'border-green-400 bg-green-50',
  rejected:  'border-red-300 bg-red-50 opacity-60',
  committed: 'border-green-600 bg-green-50',
  failed:    'border-red-500 bg-red-50',
}

export const ProposedFixCard: React.FC<ProposedFixCardProps> = ({
  fix,
  onApprove,
  onReject,
  isLoading = false,
}) => {
  const [expanded, setExpanded] = useState(true)
  const isPending = fix.status === 'pending'
  const isApproved = fix.status === 'approved'
  const isRejected = fix.status === 'rejected'
  const isCommitted = fix.status === 'committed'

  return (
    <div className={`rounded-lg border-2 transition-all ${statusBorder[fix.status] || 'border-gray-200'}`}>
      {/* Header */}
      <div className="flex items-start justify-between px-4 py-3 gap-3">
        <div className="flex items-start gap-2 min-w-0">
          <FileCode className="w-4 h-4 text-gray-400 flex-shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="text-sm font-mono font-medium text-gray-900 truncate">{fix.file_path}</p>
            {fix.explanation && (
              <p className="text-xs text-gray-600 mt-0.5 line-clamp-2">{fix.explanation}</p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${categoryColor[fix.category] || 'bg-gray-100 text-gray-800'}`}>
            {fix.category === 'bug_detection' ? 'bug' : fix.category}
          </span>
          {isCommitted && fix.commit_sha && (
            <span className="text-xs font-mono text-green-700 bg-green-100 px-2 py-0.5 rounded">
              {fix.commit_sha.slice(0, 7)}
            </span>
          )}
          <span className={`text-xs px-2 py-0.5 rounded capitalize font-medium ${
            isApproved || isCommitted ? 'text-green-700 bg-green-100' :
            isRejected ? 'text-red-700 bg-red-100' :
            'text-gray-500 bg-gray-100'
          }`}>
            {fix.status}
          </span>
        </div>
      </div>

      {/* Diff toggle */}
      <button
        className="w-full flex items-center gap-1 px-4 py-1.5 text-xs text-gray-500 hover:text-gray-700 border-t border-gray-100 bg-gray-50 hover:bg-gray-100 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        {expanded ? 'Hide diff' : 'Show diff'}
      </button>

      {/* Diff */}
      {expanded && (
        <div className="px-4 pb-3 pt-2">
          <DiffViewer diff={fix.diff} />
        </div>
      )}

      {/* Action buttons */}
      {(isPending || isApproved || isRejected) && !isCommitted && (
        <div className="flex gap-2 px-4 py-3 border-t border-gray-100">
          <button
            disabled={isLoading || isApproved}
            onClick={() => onApprove(fix.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              isApproved
                ? 'bg-green-600 text-white cursor-default'
                : 'bg-white text-green-700 border border-green-400 hover:bg-green-50 disabled:opacity-50'
            }`}
          >
            <CheckCircle className="w-4 h-4" />
            {isApproved ? 'Approved' : 'Approve'}
          </button>
          <button
            disabled={isLoading || isRejected}
            onClick={() => onReject(fix.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              isRejected
                ? 'bg-red-500 text-white cursor-default'
                : 'bg-white text-red-600 border border-red-300 hover:bg-red-50 disabled:opacity-50'
            }`}
          >
            <XCircle className="w-4 h-4" />
            {isRejected ? 'Rejected' : 'Reject'}
          </button>
        </div>
      )}
    </div>
  )
}
