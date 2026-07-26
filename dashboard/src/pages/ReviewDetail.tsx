import React, { useEffect, useRef, useState } from 'react'
import { reviewAPI, fixesAPI, ReviewDetail, ProposedFix, TestRunSummary, TestFixProgress } from '../api/client'
import { useSSE } from '../hooks/useSSE'
import { StatusBadge } from '../components/StatusBadge'
import { FindingsTable } from '../components/FindingsTable'
import { ProgressStages } from '../components/ProgressStages'
import { ProposedFixCard } from '../components/ProposedFixCard'
import { TestResultPanel } from '../components/TestResultPanel'
import { Loader, AlertCircle, GitBranch, GitCommit } from 'lucide-react'

interface ReviewDetailPageProps {
  reviewId: string
}

export const ReviewDetailPage: React.FC<ReviewDetailPageProps> = ({ reviewId }) => {
  const [review, setReview] = useState<ReviewDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fixActionLoading, setFixActionLoading] = useState(false)
  const [applyLoading, setApplyLoading] = useState(false)
  const [testRunLoading, setTestRunLoading] = useState(false)
  const [testFixLoading, setTestFixLoading] = useState(false)
  const [testFixProgress, setTestFixProgress] = useState<TestFixProgress | null>(null)

  // Single source of truth for proposed fixes — updated directly from raw SSE
  // events (see the event-processing effect below) and from the REST fallback
  // fetch. We deliberately do NOT maintain a second parallel list anywhere
  // else; merging two copies of the same list is what caused approve/reject
  // clicks to be silently reverted previously.
  const [localFixes, setLocalFixes] = useState<ProposedFix[]>([])
  const [testRun, setTestRun] = useState<TestRunSummary | null>(null)
  const [fixesCommittedInfo, setFixesCommittedInfo] = useState<{ committed_count: number; commit_shas: Record<string, string> } | null>(null)

  const { events, stages } = useSSE(reviewId, true, review?.status)

  // Track latest status in a ref so the polling interval (set up once on
  // mount) can read the CURRENT value instead of a stale one captured at
  // effect-creation time.
  const statusRef = useRef<string | undefined>(undefined)
  useEffect(() => {
    statusRef.current = review?.status
  }, [review?.status])

  // Process each RAW SSE event exactly once, in order, applying it directly
  // to localFixes/testRun/fixesCommittedInfo. Using a ref (not state) to
  // track how many events have been consumed avoids re-processing events on
  // every render and avoids needing a second "shadow" list to reconcile.
  const processedCountRef = useRef(0)
  useEffect(() => {
    for (let i = processedCountRef.current; i < events.length; i++) {
      const evt: any = events[i]

      if (evt.type === 'proposed_fix') {
        setLocalFixes(prev => {
          if (prev.some(f => f.id === evt.fix_id)) return prev
          const newFix: ProposedFix = {
            id: evt.fix_id,
            review_id: reviewId,
            category: evt.category,
            file_path: evt.file_path,
            finding_ids: evt.finding_ids || [],
            original_code: '',
            fixed_code: '',
            diff: evt.diff,
            explanation: evt.explanation,
            status: evt.status,
            created_at: new Date().toISOString(),
          }
          return [...prev, newFix]
        })
      } else if (evt.type === 'fix_status_changed') {
        setLocalFixes(prev => prev.map(f => f.id === evt.fix_id ? { ...f, status: evt.new_status } : f))
      } else if (evt.type === 'fixes_committed') {
        setFixesCommittedInfo({ committed_count: evt.committed_count, commit_shas: evt.commit_shas })
        setLocalFixes(prev => prev.map(f => f.status === 'approved' ? { ...f, status: 'committed', commit_sha: evt.commit_shas?.[f.category] } : f))
      } else if (evt.type === 'test_run_update') {
        setTestRun({
          status: evt.status,
          tests_passed: evt.tests_passed ?? 0,
          tests_failed: evt.tests_failed ?? 0,
          skipped: evt.skipped ?? false,
          skip_reason: evt.skip_reason ?? '',
          output: evt.output_tail ?? '',
          duration_seconds: evt.duration_seconds ?? 0,
          ran_at: new Date().toISOString(),
        })
        if (evt.status !== 'running') setTestRunLoading(false)
      } else if (evt.type === 'test_fix_iteration' || evt.type === 'test_fix_file' || evt.type === 'test_fix_committed') {
        setTestFixProgress(evt as TestFixProgress)
      } else if (evt.type === 'test_fix_complete') {
        setTestFixProgress(evt as TestFixProgress)
        setTestFixLoading(false)
        // Re-fetch review to get updated test_run from backend
        setTimeout(async () => {
          try {
            const response = await reviewAPI.getReview(reviewId)
            setReview(response.data)
          } catch (_) {}
        }, 800)
      }
    }
    processedCountRef.current = events.length
  }, [events, reviewId])

  // Load proposed fixes from REST once the review finishes (covers page
  // refresh after the review already completed, when no SSE events replay).
  useEffect(() => {
    if (!review || localFixes.length > 0) return
    if (!['completed', 'failed'].includes(review.status)) return
    fixesAPI.listFixes(reviewId).then(res => {
      if (res.data.proposed_fixes.length > 0) setLocalFixes(res.data.proposed_fixes)
    }).catch(() => {})
  }, [review?.status, reviewId])

  const handleApprove = async (fixId: string) => {
    setFixActionLoading(true)
    try {
      await fixesAPI.reviewFix(reviewId, fixId, 'approve')
      setLocalFixes(prev => prev.map(f => f.id === fixId ? { ...f, status: 'approved' } : f))
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Failed to approve fix')
    }
    setFixActionLoading(false)
  }

  const handleReject = async (fixId: string) => {
    setFixActionLoading(true)
    try {
      await fixesAPI.reviewFix(reviewId, fixId, 'reject')
      setLocalFixes(prev => prev.map(f => f.id === fixId ? { ...f, status: 'rejected' } : f))
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Failed to reject fix')
    }
    setFixActionLoading(false)
  }

  const handleApplyFixes = async () => {
    setApplyLoading(true)
    try {
      const res = await fixesAPI.applyApprovedFixes(reviewId)
      const { committed, commit_shas } = res.data
      setLocalFixes(prev => prev.map(f =>
        f.status === 'approved' ? { ...f, status: 'committed', commit_sha: commit_shas[f.category] } : f
      ))
      setReview(prev => prev ? { ...prev, total_fixes: committed } : null)
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Failed to apply fixes')
    }
    setApplyLoading(false)
  }

  const handleRunTests = async () => {
    setTestRunLoading(true)
    setTestRun(null)
    setTestFixLoading(false)
    setTestFixProgress(null)
    try {
      await fixesAPI.runTests(reviewId)
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Failed to start tests')
      setTestRunLoading(false)
    }
  }

  const handleFixTests = async () => {
    setTestFixLoading(true)
    setTestFixProgress({ type: 'test_fix_iteration', iteration: 0, max: 3, status: 'starting' })
    try {
      await fixesAPI.fixTests(reviewId)
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'Failed to start test fixing')
      setTestFixLoading(false)
      setTestFixProgress(null)
    }
  }

  // Initial + polling fetch. Uses statusRef (not the closed-over `review`
  // variable) so the interval correctly detects a terminal status and stops,
  // regardless of when this effect was originally created. Also stops on a
  // hard fetch error (e.g. 404 for a review that no longer exists after a
  // server restart) instead of hammering the endpoint forever.
  useEffect(() => {
    let cancelled = false

    const fetchReview = async () => {
      try {
        const response = await reviewAPI.getReview(reviewId)
        if (cancelled) return
        setReview(response.data)
        setLoading(false)
        setError(null)
        return true
      } catch (err: any) {
        if (cancelled) return false
        setError(err?.response?.data?.detail || 'Failed to load review')
        setLoading(false)
        return false
      }
    }

    fetchReview()
    const interval = setInterval(async () => {
      if (cancelled) return
      if (statusRef.current && ['completed', 'failed'].includes(statusRef.current)) {
        clearInterval(interval)
        return
      }
      const ok = await fetchReview()
      if (ok === false) clearInterval(interval)
    }, 2000)

    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [reviewId])

  // Safety net: the SSE "stage_update" event announcing COMPLETED fires from
  // inside the graph's finalize node — BEFORE the backend finishes writing
  // agent_results/proposed_fixes onto the Review object. That early signal
  // flips review.status to a terminal value and stops the polling loop
  // above, which could otherwise skip fetching the fully-populated result
  // entirely. Force one or two extra fetches shortly after detecting
  // terminal status to guarantee we have the final data.
  useEffect(() => {
    if (!review || !['completed', 'failed'].includes(review.status)) return
    const timers = [500, 1500].map(delay =>
      setTimeout(async () => {
        try {
          const response = await reviewAPI.getReview(reviewId)
          setReview(response.data)
        } catch (err) {
          console.error('Failed to fetch final review data:', err)
        }
      }, delay)
    )
    return () => timers.forEach(clearTimeout)
  }, [review?.status, reviewId])

  // Update status from SSE stage_update events
  useEffect(() => {
    if (!review || events.length === 0) return
    const lastEvent: any = events[events.length - 1]
    if (lastEvent.status && lastEvent.type === 'stage_update') {
      setReview((prev) => prev ? { ...prev, status: lastEvent.status } : null)
    }
  }, [events])

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

  const pendingCount = localFixes.filter(f => f.status === 'pending').length
  const approvedCount = localFixes.filter(f => f.status === 'approved').length
  const committedCount = localFixes.filter(f => f.status === 'committed').length
  const allDecided = localFixes.length > 0 && pendingCount === 0
  const canApply = allDecided && approvedCount > 0 && committedCount === 0
  const canRunTests = committedCount > 0

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

      {/* ------------------------------------------------------------------ */}
      {/* Proposed Fixes — human-in-the-loop review                          */}
      {/* ------------------------------------------------------------------ */}
      {localFixes.length > 0 && (
        <div className="bg-white rounded-lg shadow p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">
              Proposed Fixes
              <span className="ml-2 text-sm font-normal text-gray-500">
                ({pendingCount} pending · {approvedCount} approved · {committedCount} committed)
              </span>
            </h2>
            <button
              disabled={applyLoading || !canApply}
              onClick={handleApplyFixes}
              title={!allDecided ? 'Decide (approve or reject) every proposed fix before applying' : undefined}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-green-600 text-white hover:bg-green-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {applyLoading ? (
                <><Loader className="w-4 h-4 animate-spin" /> Committing…</>
              ) : (
                <><GitCommit className="w-4 h-4" /> Apply Approved Fixes</>
              )}
            </button>
          </div>

          {!allDecided && committedCount === 0 && (
            <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              Approve or reject all {localFixes.length} proposed fix{localFixes.length !== 1 ? 'es' : ''} before you can apply them
              ({pendingCount} still pending).
            </p>
          )}

          {/* Commit success banner */}
          {fixesCommittedInfo && fixesCommittedInfo.committed_count > 0 && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-sm text-green-800">
              ✓ {fixesCommittedInfo.committed_count} fix{fixesCommittedInfo.committed_count !== 1 ? 'es' : ''} committed.
              {Object.entries(fixesCommittedInfo.commit_shas).map(([cat, sha]) => (
                <span key={cat} className="ml-2 font-mono text-xs bg-green-100 px-1 rounded">
                  {cat}: {sha.slice(0, 7)}
                </span>
              ))}
            </div>
          )}

          <div className="space-y-3">
            {localFixes.map(fix => (
              <ProposedFixCard
                key={fix.id}
                fix={fix}
                onApprove={handleApprove}
                onReject={handleReject}
                isLoading={fixActionLoading}
              />
            ))}
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Test Gate — runs AFTER fixes are committed                         */}
      {/* ------------------------------------------------------------------ */}
      {localFixes.length > 0 && (
        <TestResultPanel
          result={testRun || review?.test_run || null}
          isRunning={testRunLoading}
          canRun={canRunTests}
          onRunTests={handleRunTests}
          onFixTests={handleFixTests}
          isFixing={testFixLoading}
          fixProgress={testFixProgress}
        />
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
