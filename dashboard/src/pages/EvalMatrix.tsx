import React, { useCallback, useEffect, useRef, useState } from 'react'
import { evalAPI, EvalReport, FixEvalReport, E2EReport, EvalType, EvalRunState } from '../api/client'
import { AlertTriangle, Bug, Zap, Eye, AlertCircle, Play, Loader2, CheckCircle2 } from 'lucide-react'

const categoryIcons: Record<string, React.ReactNode> = {
  security: <AlertTriangle className="w-4 h-4" />,
  bug_detection: <Bug className="w-4 h-4" />,
  performance: <Zap className="w-4 h-4" />,
  style: <Eye className="w-4 h-4" />,
}

function scoreColor(score: number): string {
  if (score >= 0.8) return 'bg-green-100 text-green-800 border-green-300'
  if (score >= 0.5) return 'bg-yellow-100 text-yellow-800 border-yellow-300'
  return 'bg-red-100 text-red-800 border-red-300'
}

const POLL_INTERVAL_MS = 2000

interface EvalRunControlProps {
  evalType: EvalType
  label: string
  onCompleted: () => void
}

const EvalRunControl: React.FC<EvalRunControlProps> = ({ evalType, label, onCompleted }) => {
  const [state, setState] = useState<EvalRunState>('idle')
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  useEffect(() => stopPolling, [stopPolling])

  const poll = useCallback(() => {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const res = await evalAPI.getRunStatus(evalType)
        setState(res.data.status)
        if (res.data.status === 'completed') {
          stopPolling()
          onCompleted()
        } else if (res.data.status === 'failed') {
          stopPolling()
          setError(res.data.error || 'Eval run failed')
        }
      } catch {
        stopPolling()
        setError('Lost connection while polling eval run status')
      }
    }, POLL_INTERVAL_MS)
  }, [evalType, onCompleted, stopPolling])

  const handleRun = async () => {
    setError(null)
    try {
      await evalAPI.triggerRun(evalType)
      setState('running')
      poll()
    } catch (err: any) {
      setError(err?.response?.data?.detail || `Failed to start ${label}`)
    }
  }

  const isRunning = state === 'running'

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleRun}
        disabled={isRunning}
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border transition-colors ${
          isRunning
            ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
            : 'bg-blue-600 text-white border-blue-600 hover:bg-blue-700'
        }`}
      >
        {isRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        {isRunning ? 'Running…' : `Run ${label}`}
      </button>
      {state === 'completed' && (
        <span className="inline-flex items-center gap-1 text-green-700 text-xs font-medium">
          <CheckCircle2 className="w-4 h-4" /> Report updated
        </span>
      )}
      {error && <span className="text-red-700 text-xs font-medium">{error}</span>}
    </div>
  )
}

export const EvalMatrixPage: React.FC = () => {
  const [report, setReport] = useState<EvalReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [fixReport, setFixReport] = useState<FixEvalReport | null>(null)
  const [fixLoading, setFixLoading] = useState(true)
  const [fixError, setFixError] = useState<string | null>(null)

  const [e2eReport, setE2eReport] = useState<E2EReport | null>(null)
  const [e2eLoading, setE2eLoading] = useState(true)
  const [e2eError, setE2eError] = useState<string | null>(null)

  const fetchReport = useCallback(() => {
    setLoading(true)
    return evalAPI
      .getLatest()
      .then((res) => {
        setReport(res.data)
        setError(null)
      })
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load eval report'))
      .finally(() => setLoading(false))
  }, [])

  const fetchFixReport = useCallback(() => {
    setFixLoading(true)
    return evalAPI
      .getLatestFix()
      .then((res) => {
        setFixReport(res.data)
        setFixError(null)
      })
      .catch((err) => setFixError(err?.response?.data?.detail || 'Failed to load fix-eval report'))
      .finally(() => setFixLoading(false))
  }, [])

  const fetchE2eReport = useCallback(() => {
    setE2eLoading(true)
    return evalAPI
      .getLatestE2E()
      .then((res) => {
        setE2eReport(res.data)
        setE2eError(null)
      })
      .catch((err) => setE2eError(err?.response?.data?.detail || 'Failed to load e2e-eval report'))
      .finally(() => setE2eLoading(false))
  }, [])

  useEffect(() => {
    fetchReport()
    fetchFixReport()
    fetchE2eReport()
  }, [fetchReport, fetchFixReport, fetchE2eReport])

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <div className="flex items-start justify-between gap-4 mb-1 flex-wrap">
        <h1 className="text-2xl font-bold">Agent Evaluation Matrix</h1>
        <EvalRunControl evalType="finding" label="Finding Eval" onCompleted={fetchReport} />
      </div>
      <p className="text-sm text-gray-500 mb-6">
        {report ? `Generated ${new Date(report.generated_at).toLocaleString()}` : 'No report generated yet — run the finding eval to produce one.'}
      </p>

      {loading ? (
        <div className="text-gray-500">Loading evaluation matrix...</div>
      ) : error || !report ? (
        <div className="flex items-center gap-2 text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <AlertCircle className="w-5 h-5" />
          {error || 'No evaluation report available'}
        </div>
      ) : (
        <>
      <div className="overflow-x-auto bg-white rounded-lg shadow">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-2 text-left font-semibold">Agent</th>
              <th className="px-4 py-2 text-right font-semibold">TP</th>
              <th className="px-4 py-2 text-right font-semibold">FP</th>
              <th className="px-4 py-2 text-right font-semibold">FN</th>
              <th className="px-4 py-2 text-right font-semibold">Precision</th>
              <th className="px-4 py-2 text-right font-semibold">Recall</th>
              <th className="px-4 py-2 text-right font-semibold">F1</th>
              <th className="px-4 py-2 text-right font-semibold">Avg Similarity</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {report.agents.map((m) => (
              <tr key={m.agent_name} className="hover:bg-gray-50">
                <td className="px-4 py-2 font-medium flex items-center gap-2">
                  {categoryIcons[m.agent_name] || '—'}
                  {m.agent_name}
                </td>
                <td className="px-4 py-2 text-right">{m.true_positives}</td>
                <td className="px-4 py-2 text-right">{m.false_positives}</td>
                <td className="px-4 py-2 text-right">{m.false_negatives}</td>
                <td className="px-4 py-2 text-right">
                  <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.precision)}`}>
                    {m.precision.toFixed(3)}
                  </span>
                </td>
                <td className="px-4 py-2 text-right">
                  <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.recall)}`}>
                    {m.recall.toFixed(3)}
                  </span>
                </td>
                <td className="px-4 py-2 text-right">
                  <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.f1)}`}>
                    {m.f1.toFixed(3)}
                  </span>
                </td>
                <td className="px-4 py-2 text-right">
                  <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.avg_similarity)}`}>
                    {m.avg_similarity.toFixed(3)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-8 space-y-6">
        {report.agents.map((m) => (
          <div key={m.agent_name} className="bg-white rounded-lg shadow p-4">
            <h2 className="font-semibold mb-3 flex items-center gap-2">
              {categoryIcons[m.agent_name] || '—'}
              {m.agent_name} — matched, missed &amp; unexpected findings
            </h2>
            {m.cases.map((c) => (
              <div key={c.file} className="mb-3 text-xs">
                <div className="font-mono text-gray-600 mb-1">{c.file}</div>
                {c.matched.length === 0 && c.missed.length === 0 && c.unexpected.length === 0 ? (
                  <div className="text-gray-400">No expected findings for this file.</div>
                ) : (
                  <ul className="list-disc list-inside space-y-0.5">
                    {c.matched.map((pair, i) => (
                      <li key={`matched-${i}`} className="text-green-700">
                        Matched: {pair.expected.description} (line {pair.actual_start_line ?? '?'}) —{' '}
                        <span className={`px-1.5 py-0.5 rounded border text-xs font-semibold ${scoreColor(pair.similarity)}`}>
                          similarity {pair.similarity.toFixed(2)}
                        </span>
                      </li>
                    ))}
                    {c.missed.map((f, i) => (
                      <li key={`missed-${i}`} className="text-red-700">
                        Missed: {f.description} (line {f.start_line})
                      </li>
                    ))}
                    {c.unexpected.map((title, i) => (
                      <li key={`unexpected-${i}`} className="text-yellow-700">
                        Unexpected: {title}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>
        </>
      )}

      <div className="flex items-start justify-between gap-4 mb-1 mt-12 flex-wrap">
        <h1 className="text-2xl font-bold">Fix Agent Model Comparison</h1>
        <EvalRunControl evalType="fix" label="Fix Eval" onCompleted={fetchFixReport} />
      </div>
      <p className="text-sm text-gray-500 mb-6">
        LLM-as-judge scores (0-1) for each candidate generator model, judged against golden findings.
      </p>

      {fixLoading ? (
        <div className="text-gray-500">Loading fix-eval matrix...</div>
      ) : fixError || !fixReport ? (
        <div className="flex items-center gap-2 text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <AlertCircle className="w-5 h-5" />
          {fixError || 'No fix-eval report available'}
        </div>
      ) : (
        <div className="overflow-x-auto bg-white rounded-lg shadow">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-4 py-2 text-left font-semibold">Model</th>
                <th className="px-4 py-2 text-right font-semibold">Cases</th>
                <th className="px-4 py-2 text-right font-semibold">Fix Generated</th>
                <th className="px-4 py-2 text-right font-semibold">Syntax OK</th>
                <th className="px-4 py-2 text-right font-semibold">Resolved</th>
                <th className="px-4 py-2 text-right font-semibold">Correctness</th>
                <th className="px-4 py-2 text-right font-semibold">Safety</th>
                <th className="px-4 py-2 text-right font-semibold">Minimality</th>
                <th className="px-4 py-2 text-right font-semibold">Explanation</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {fixReport.models.map((m) => (
                <tr key={m.model_label} className="hover:bg-gray-50">
                  <td className="px-4 py-2 font-medium">{m.model_label}</td>
                  <td className="px-4 py-2 text-right">{m.cases}</td>
                  <td className="px-4 py-2 text-right">
                    <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.success_rate)}`}>
                      {m.success_rate.toFixed(3)}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.syntax_valid_rate)}`}>
                      {m.syntax_valid_rate.toFixed(3)}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.resolved_rate)}`}>
                      {m.resolved_rate.toFixed(3)}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.avg_correctness)}`}>
                      {m.avg_correctness.toFixed(3)}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.avg_safety)}`}>
                      {m.avg_safety.toFixed(3)}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.avg_minimality)}`}>
                      {m.avg_minimality.toFixed(3)}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.avg_explanation_quality)}`}>
                      {m.avg_explanation_quality.toFixed(3)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-start justify-between gap-4 mb-1 mt-12 flex-wrap">
        <h1 className="text-2xl font-bold">End-to-End Pipeline (Finding → Fix)</h1>
        <EvalRunControl evalType="e2e" label="E2E Eval" onCompleted={fetchE2eReport} />
      </div>
      <p className="text-sm text-gray-500 mb-6">
        Live finding-agent output matched against golden findings, then fed straight into the fix
        agent.
      </p>

      {e2eLoading ? (
        <div className="text-gray-500">Loading e2e-eval matrix...</div>
      ) : e2eError || !e2eReport ? (
        <div className="flex items-center gap-2 text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <AlertCircle className="w-5 h-5" />
          {e2eError || 'No e2e-eval report available'}
        </div>
      ) : (
        <>
          <div className="overflow-x-auto bg-white rounded-lg shadow">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-4 py-2 text-left font-semibold">Agent</th>
                  <th className="px-4 py-2 text-right font-semibold">TP</th>
                  <th className="px-4 py-2 text-right font-semibold">FP</th>
                  <th className="px-4 py-2 text-right font-semibold">FN</th>
                  <th className="px-4 py-2 text-right font-semibold">Precision</th>
                  <th className="px-4 py-2 text-right font-semibold">Recall</th>
                  <th className="px-4 py-2 text-right font-semibold">F1</th>
                  <th className="px-4 py-2 text-right font-semibold">Fix Generated</th>
                  <th className="px-4 py-2 text-right font-semibold">Resolved</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {e2eReport.agents.map((m) => (
                  <tr key={m.agent_name} className="hover:bg-gray-50">
                    <td className="px-4 py-2 font-medium flex items-center gap-2">
                      {categoryIcons[m.agent_name] || '—'}
                      {m.agent_name}
                    </td>
                    <td className="px-4 py-2 text-right">{m.true_positives}</td>
                    <td className="px-4 py-2 text-right">{m.false_positives}</td>
                    <td className="px-4 py-2 text-right">{m.false_negatives}</td>
                    <td className="px-4 py-2 text-right">
                      <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.precision)}`}>
                        {m.precision.toFixed(3)}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.recall)}`}>
                        {m.recall.toFixed(3)}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.f1)}`}>
                        {m.f1.toFixed(3)}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.fix_success_rate)}`}>
                        {m.fix_success_rate.toFixed(3)}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.resolved_rate)}`}>
                        {m.resolved_rate.toFixed(3)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-8 space-y-6">
            {e2eReport.agents.map((m) => (
              <div key={m.agent_name} className="bg-white rounded-lg shadow p-4">
                <h2 className="font-semibold mb-3 flex items-center gap-2">
                  {categoryIcons[m.agent_name] || '—'}
                  {m.agent_name} — per-file pipeline outcome
                </h2>
                {m.case_results.map((c) => (
                  <div key={c.finding.file} className="mb-3 text-xs">
                    <div className="font-mono text-gray-600 mb-1">{c.finding.file}</div>
                    {c.finding.matched.length === 0 &&
                    c.finding.missed.length === 0 &&
                    c.finding.unexpected.length === 0 ? (
                      <div className="text-gray-400">No expected findings for this file.</div>
                    ) : (
                      <>
                        <ul className="list-disc list-inside space-y-0.5">
                          {c.finding.matched.map((pair, i) => (
                            <li key={`matched-${i}`} className="text-green-700">
                              Matched: {pair.expected.description} (line {pair.actual_start_line ?? '?'})
                            </li>
                          ))}
                          {c.finding.missed.map((f, i) => (
                            <li key={`missed-${i}`} className="text-red-700">
                              Missed: {f.description} (line {f.start_line}) — never reached the fix agent
                            </li>
                          ))}
                          {c.finding.unexpected.map((title, i) => (
                            <li key={`unexpected-${i}`} className="text-yellow-700">
                              Unexpected: {title}
                            </li>
                          ))}
                        </ul>
                        <div className="mt-1">
                          {!c.fix_attempted ? (
                            <span className="text-gray-400">Fix not attempted (nothing matched).</span>
                          ) : (
                            <span
                              className={`px-2 py-0.5 rounded border text-xs font-semibold ${
                                c.judge?.resolved
                                  ? 'bg-green-100 text-green-800 border-green-300'
                                  : 'bg-red-100 text-red-800 border-red-300'
                              }`}
                            >
                              Fix {c.fix_success ? 'succeeded' : 'failed'}
                              {c.judge ? `, judge: ${c.judge.resolved ? 'resolved' : 'not resolved'}` : ''}
                            </span>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
