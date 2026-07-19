from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.config_runtime import load_eval_config
from eval.datasets.internal_benchmarks import load_citation_review, summarize_binary_rate
from eval.datasets.prepare_owasp_cwe import prepare_owasp_cwe
from eval.metrics.ablation import compute_rag_baseline_from_support_labels
from eval.metrics.classification import bootstrap_confidence_interval
from eval.metrics.ragas_wrapper import compute_ragas_scores
from eval.optional_dependencies import dependency_status
from eval.zero_shot_baseline import run_zero_shot_binary_predictions


def run_rag_eval(output_dir: str | Path | None = None) -> dict[str, Any]:
    """Evaluate the RAG pipeline using local OWASP/CWE knowledge files."""
    cfg = load_eval_config()
    dataset_dir = prepare_owasp_cwe()
    citation_rows = load_citation_review()
    citation_support_accuracy, citation_n = summarize_binary_rate(citation_rows, "supported")
    support_labels = [str(row.get("supported", "")).strip().lower() in {"1", "true", "yes", "y"} for row in citation_rows]
    ragas_result = compute_ragas_scores(citation_rows)

    baseline_rows = [{"supported": int(label)} for label in support_labels]
    zero_shot_preds = run_zero_shot_binary_predictions(
        "rag_citation_support",
        baseline_rows,
        label_key="supported",
        prediction_key="prediction",
        cache_enabled=cfg.cache_enabled,
        cache_dir=cfg.cache_dir,
    )
    zero_shot_supported = [pred == 1 for pred in zero_shot_preds]
    baseline = compute_rag_baseline_from_support_labels(zero_shot_supported)

    ragas_dep = dependency_status("ragas", "ragas")
    ragas_status = "implemented" if ragas_result.get("status") in {"executed", "executed_partial"} else "pending"
    citation_support_ci95 = bootstrap_confidence_interval([1.0 if label else 0.0 for label in support_labels]) if support_labels else [0.0, 0.0]

    payload = {
        "benchmark": "RAGAS Faithfulness",
        "agent": "rag",
        "dataset_path": str(dataset_dir),
        "n": cfg.ragas_sample_n,
        "metrics": {
            "faithfulness": float(ragas_result["scores"].get("faithfulness", 0.0)),
            "answer_relevance": float(ragas_result["scores"].get("answer_relevance", 0.0)),
            "context_precision": float(ragas_result["scores"].get("context_precision", 0.0)),
            "citation_support_accuracy": citation_support_accuracy,
            "citation_support_accuracy_ci95": citation_support_ci95,
        },
        "baseline_zero_shot": {
            "faithfulness": baseline["faithfulness"],
            "answer_relevance": baseline["answer_relevance"],
            "context_precision": baseline["context_precision"],
        },
        "dependency_status": {"ragas": ragas_dep},
        "ragas_execution": ragas_result,
        "benchmark_coverage": [
            {"name": "RAGAS", "status": ragas_status},
            {
                "name": "Human-checked OWASP/CWE citation sample",
                "status": "implemented",
                "notes": f"Scored citation support on {citation_n} reviewed claims.",
            },
        ],
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    output_path = Path(output_dir or cfg.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "rag_eval.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
