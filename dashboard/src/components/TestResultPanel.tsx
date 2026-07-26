import React from 'react'
import { PlayCircle, Loader, CheckCircle, XCircle, AlertTriangle, Wrench, GitCommit } from 'lucide-react'

interface TestFixProgress {
  type: string
  iteration?: number
  max?: number
  status?: string
  files?: string[]
  file_path?: string
  explanation?: string
  commit_sha?: string
  tests_passed?: number
  tests_failed?: number
  message?: string
}

interface TestResultPanelProps {
  result: {
    status: 'running' | 'passed' | 'failed' | 'skipped'
    tests_passed: number
    tests_failed: number
    skipped: boolean
    skip_reason: string
    output: string
    duration_seconds: number
  } | null
  isRunning: boolean
  canRun: boolean
  onRunTests: () => void
  onFixTests: () => void
  isFixing: boolean
  fixProgress: TestFixProgress | null
}

export const TestResultPanel: React.FC<TestResultPanelProps> = ({
  result,
  isRunning,
  canRun,
  onRunTests,
  onFixTests,
  isFixing,
  fixProgress,
}) => {
  const showsFixButton = result?.status === 'failed' && !isFixing

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">Test Gate</h3>
        <div className="flex items-center gap-2">
          {!isFixing && (
            <button
              disabled={!canRun || isRunning}
              onClick={onRunTests}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {isRunning ? (
                <><Loader className="w-4 h-4 animate-spin" /> Running pytest…</>
              ) : (
                <><PlayCircle className="w-4 h-4" /> Run Tests</>
              )}
            </button>
          )}
          {showsFixButton && (
            <button
              onClick={onFixTests}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors bg-amber-600 text-white hover:bg-amber-700"
            >
              <Wrench className="w-4 h-4" />
              Fix Failing Tests
            </button>
          )}
        </div>
      </div>

      {!result && !isRunning && !isFixing && !canRun && (
        <p className="text-sm text-gray-500">
          Apply your approved fixes first — once they're committed, you can run tests
          against the updated branch to confirm nothing broke.
        </p>
      )}

      {!result && !isRunning && !isFixing && canRun && (
        <p className="text-sm text-gray-500">
          Fixes are committed. Run tests to verify the updated branch still passes.
        </p>
      )}

      {isRunning && !result && (
        <div className="flex items-center gap-3 text-sm text-indigo-700 bg-indigo-50 rounded-lg p-4">
          <Loader className="w-4 h-4 animate-spin flex-shrink-0" />
          <span>Cloning the branch and running pytest…</span>
        </div>
      )}

      {/* ---- Test-fixing loop progress ---- */}
      {isFixing && fixProgress && (
        <div className="space-y-2 mb-4">
          <div className="flex items-center gap-3 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3">
            <Loader className="w-4 h-4 animate-spin flex-shrink-0" />
            <div>
              <p className="font-medium">Auto-fixing failing tests</p>
              {fixProgress.iteration && (
                <p className="text-xs text-amber-600 mt-0.5">
                  Iteration {fixProgress.iteration}/{fixProgress.max}
                  {fixProgress.status === 'running_tests' && ' — running tests…'}
                  {fixProgress.status === 'fixing' && ' — generating fixes…'}
                </p>
              )}
            </div>
          </div>

          {/* Per-file fix status */}
          {fixProgress.type === 'test_fix_file' && fixProgress.file_path && (
            <div className={`text-xs px-3 py-2 rounded border ${
              fixProgress.status === 'fixed'
                ? 'bg-green-50 border-green-200 text-green-700'
                : 'bg-gray-50 border-gray-200 text-gray-500'
            }`}>
              <span className="font-mono">{fixProgress.file_path}</span>
              {' — '}
              {fixProgress.status === 'fixed' ? (
                <span>✓ {fixProgress.explanation || 'Fixed'}</span>
              ) : (
                <span>{fixProgress.explanation || 'Skipped'}</span>
              )}
            </div>
          )}

          {/* Commit status */}
          {fixProgress.type === 'test_fix_committed' && fixProgress.commit_sha && (
            <div className="flex items-center gap-2 text-xs text-green-700 bg-green-50 border border-green-200 rounded-lg p-2">
              <GitCommit className="w-3 h-3" />
              <span>Committed: <code className="font-mono">{fixProgress.commit_sha.slice(0, 7)}</code></span>
            </div>
          )}
        </div>
      )}

      {/* ---- Result display ---- */}
      {result && !isFixing && (
        <div className="space-y-3">
          {result.status === 'passed' && (
            <div className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-lg p-3 text-green-800 text-sm font-medium">
              <CheckCircle className="w-4 h-4 text-green-600 flex-shrink-0" />
              All {result.tests_passed} test{result.tests_passed !== 1 ? 's' : ''} passed — committed fixes look safe
            </div>
          )}
          {result.status === 'failed' && (
            <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg p-3 text-red-800 text-sm font-medium">
              <XCircle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
              <div>
                <p>
                  {result.tests_failed} test{result.tests_failed !== 1 ? 's' : ''} failed
                  {result.tests_passed > 0 && ` (${result.tests_passed} passed)`}
                  {' — the committed fixes may have broken something. '}
                </p>
                <p className="font-normal text-red-600 mt-1">
                  Click "Fix Failing Tests" to auto-fix the test failures via AI, or review manually.
                </p>
              </div>
            </div>
          )}
          {result.status === 'skipped' && (
            <div className="flex items-center gap-2 bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-yellow-800 text-sm font-medium">
              <AlertTriangle className="w-4 h-4 text-yellow-600 flex-shrink-0" />
              Could not run tests: {result.skip_reason || 'unknown reason'}
            </div>
          )}

          {result.duration_seconds > 0 && (
            <p className="text-xs text-gray-400">
              Completed in {result.duration_seconds}s
            </p>
          )}

          {result.output && (
            <details className="group">
              <summary className="cursor-pointer text-xs text-gray-500 hover:text-gray-700 select-none">
                Show pytest output
              </summary>
              <pre className="mt-2 bg-gray-900 text-gray-100 rounded-lg p-3 text-xs overflow-x-auto max-h-64 overflow-y-auto font-mono whitespace-pre-wrap">
                {result.output}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  )
}
