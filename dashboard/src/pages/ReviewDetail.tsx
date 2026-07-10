import React, { useEffect, useState } from 'react'
import { reviewAPI, ReviewDetail } from '../api/client'
import { useSSE } from '../hooks/useSSE'
import { StatusBadge } from '../components/StatusBadge'
import { FindingsTable } from '../components/FindingsTable'
import { ProgressStages } from '../components/ProgressStages'
import { Loader, AlertCircle, GitBranch } from 'lucide-react'

interface ReviewDetailPageProps {
  reviewId: string
}

export const ReviewDetailPage: React.FC<ReviewDetailPageProps> = ({ reviewId }) => {
  const [review, setReview] = useState<ReviewDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { events, stages } = useSSE(reviewId, true, review?.status)

  useEffect(() => {
    const fetchReview = async () => {
      try {
        const response = await reviewAPI.getReview(reviewId)
        setReview(response.data)
        setLoading(false)
        setError(null)
      } catch (err: any) {
        setError(err?.response?.data?.detail || 'Failed to load review')
        setLoading(false)
      }
    }

    fetchReview()
    // Poll every 2 seconds, but stop once review is terminal or on error
    const interval = setInterval(() => {
      if (error || (review && ['completed', 'failed'].includes(review.status))) {
        clearInterval(interval)
      } else if (review) {
        fetchReview()
      }
    }, 2000)
    return () => clearInterval(interval)
  }, [reviewId])

  // Update status from SSE events
  useEffect(() => {
    if (!review || events.length === 0) return
    const lastEvent = events[events.length - 1]
    // Backend publishes "stage_update" events with status field
    if (lastEvent.status && lastEvent.type === 'stage_update') {
      setReview((prev) => prev ? { ...prev, status: lastEvent.status } : null)
    }
  }, [events])

  // Auto-fetch review one more time when completed to ensure all data is loaded
  useEffect(() => {
    if (!review || !['completed', 'failed'].includes(review.status)) return
    const timer = setTimeout(async () => {
      try {
        const response = await reviewAPI.getReview(reviewId)
        setReview(response.data)
      } catch (err) {
        console.error('Failed to fetch final review data:', err)
      }
    }, 500)
    return () => clearTimeout(timer)
  }, [review?.status, reviewId])

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <Loader className="w-8 h-8 animate-spin text-blue-600 mx-auto mb-4" />
          <p className="text-gray-600">Loading review...</p>
        </div>
      </div>
    )
  }

  if (error || !review) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-red-900">Error</h3>
            <p className="text-red-700">{error}</p>
          </div>
        </div>
      </div>
    )
  }

  const findings = Object.values(review.findings_by_category || {}).flat()
  const isTerminal = ['completed', 'failed'].includes(review.status)

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">{review.pr_title || `PR #${review.pr_number}`}</h1>
            <div className="flex items-center gap-2 text-gray-600 mt-2">
              <GitBranch className="w-4 h-4" />
              <span>#{review.pr_number}</span>
              {review.pr_author && <span className="text-gray-400">by {review.pr_author}</span>}
            </div>
          </div>
          <div>
            <StatusBadge status={review.status} />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4 pt-4 border-t">
          <div>
            <p className="text-sm text-gray-600">Findings</p>
            <p className="text-2xl font-bold text-gray-900">{review.total_findings}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600">Fixed</p>
            <p className="text-2xl font-bold text-green-600">{review.total_fixes}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600">Status</p>
            <p className="text-sm font-mono text-gray-700">{review.status}</p>
          </div>
        </div>

        {/* Fix PR Link */}
        {review.fix_pr_url && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4 mt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-green-900">Fixes Applied</p>
                <p className="text-sm text-green-700 mt-1">
                  {review.total_fixes} issue{review.total_fixes !== 1 ? 's' : ''} fixed and committed to the PR branch
                </p>
              </div>
              <a
                href={review.fix_pr_url}
                target="_blank"
                rel="noopener noreferrer"
                className="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded hover:bg-green-700"
              >
                View PR with Fixes →
              </a>
            </div>
          </div>
        )}
      </div>

      {/* Progress Stages */}
      <ProgressStages stages={stages} />

      {/* Live Stream */}
      {!isTerminal && events.length > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-sm text-blue-700">
            <span className="font-semibold">● Live</span> — {events.length} event{events.length !== 1 ? 's' : ''} received
          </p>
        </div>
      )}

      {/* Findings by Category */}
      {Object.entries(review.findings_by_category || {}).map(([category, categoryFindings]) => (
        <div key={category} className="bg-white rounded-lg shadow overflow-hidden">
          <div className="bg-gray-50 px-6 py-3 border-b">
            <h2 className="text-lg font-semibold text-gray-900 capitalize">
              {category === 'bug_detection' ? 'Bugs' : category}
              <span className="text-gray-600 font-normal ml-2">({categoryFindings.length})</span>
            </h2>
          </div>
          <div className="p-6">
            {categoryFindings.length > 0 ? (
              <FindingsTable findings={categoryFindings} />
            ) : (
              <p className="text-center text-gray-500">No issues found</p>
            )}
          </div>
        </div>
      ))}

      {findings.length === 0 && isTerminal && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-6 text-center">
          <p className="text-green-700 font-semibold">✓ No issues found</p>
          <p className="text-green-600 text-sm mt-1">This PR looks good!</p>
        </div>
      )}

      {/* Timeline */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Timeline</h3>
        <div className="space-y-2 text-sm text-gray-600">
          <div>Created: {new Date(review.created_at).toLocaleString()}</div>
          <div>Updated: {new Date(review.updated_at).toLocaleString()}</div>
          {review.completed_at && (
            <div>Completed: {new Date(review.completed_at).toLocaleString()}</div>
          )}
        </div>
      </div>
    </div>
  )
}
