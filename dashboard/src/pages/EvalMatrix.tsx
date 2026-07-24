import React, { useEffect, useState } from 'react'
import { evalAPI, EvalReport, FixEvalReport } from '../api/client'
import { AlertTriangle, Bug, Zap, Eye, AlertCircle } from 'lucide-react'

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

export const EvalMatrixPage: React.FC = () => {
  const [report, setReport] = useState<EvalReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [fixReport, setFixReport] = useState<FixEvalReport | null>(null)
  const [fixLoading, setFixLoading] = useState(true)
  const [fixError, setFixError] = useState<string | null>(null)

  useEffect(() => {
    evalAPI
      .getLatest()
      .then((res) => setReport(res.data))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load eval report'))
      .finally(() => setLoading(false))

    evalAPI
      .getLatestFix()
      .then((res) => setFixReport(res.data))
      .catch((err) => setFixError(err?.response?.data?.detail || 'Failed to load fix-eval report'))
      .finally(() => setFixLoading(false))
  }, [])

  if (loading) {
    return <div className="max-w-6xl mx-auto px-6 py-8 text-gray-500">Loading evaluation matrix...</div>
  }

  if (error || !report) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex items-center gap-2 text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <AlertCircle className="w-5 h-5" />
          {error || 'No evaluation report available'}
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-bold mb-1">Agent Evaluation Matrix</h1>
      <p className="text-sm text-gray-500 mb-6">
        Generated {new Date(report.generated_at).toLocaleString()}
      </p>

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

      <h1 className="text-2xl font-bold mb-1 mt-12">Fix Agent Model Comparison</h1>
      <p className="text-sm text-gray-500 mb-6">
        LLM-as-judge scores (0-5) for each candidate generator model, judged against golden findings.
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
                <th className="px-4 py-2 text-right font-semibold">Success</th>
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
                    <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.avg_correctness / 5)}`}>
                      {m.avg_correctness.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.avg_safety / 5)}`}>
                      {m.avg_safety.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.avg_minimality / 5)}`}>
                      {m.avg_minimality.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <span className={`px-2 py-1 rounded border text-xs font-semibold ${scoreColor(m.avg_explanation_quality / 5)}`}>
                      {m.avg_explanation_quality.toFixed(2)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
