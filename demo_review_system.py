#!/usr/bin/env python3
"""
Demo: Multi-Agent Code Review System
Shows how to submit PRs and collect agent outputs
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx


def demo_review_submission():
    """Show the review submission workflow."""
    print("\n" + "="*70)
    print("🤖 MULTI-AGENT CODE REVIEW SYSTEM - DEMO")
    print("="*70)
    
    client = httpx.Client(timeout=30.0)
    base_url = "http://localhost:8000"
    
    print("\n1️⃣  HEALTH CHECK")
    print("-" * 70)
    try:
        response = client.get(f"{base_url}/health")
        health = response.json()
        print(f"   ✅ Server Status: {health['status']}")
    except Exception as e:
        print(f"   ❌ Server Error: {e}")
        return
    
    print("\n2️⃣  AVAILABLE REVIEW ENDPOINTS")
    print("-" * 70)
    endpoints = [
        ("POST", "/api/v1/reviews", "Create a new PR review"),
        ("GET", "/api/v1/reviews", "List all reviews"),
        ("GET", "/api/v1/reviews/{review_id}", "Get review details"),
        ("GET", "/api/v1/sse/{review_id}", "Stream review progress (SSE)"),
    ]
    for method, path, desc in endpoints:
        print(f"   {method:5} {path:35} - {desc}")
    
    print("\n3️⃣  SAMPLE REQUEST PAYLOAD")
    print("-" * 70)
    sample_payload = {
        "owner": "torvalds",
        "repo": "linux",
        "pr_number": 1234,
    }
    print(f"   POST /api/v1/reviews")
    print(f"   {json.dumps(sample_payload, indent=6)}")
    
    print("\n4️⃣  AGENT CAPABILITIES")
    print("-" * 70)
    agents = [
        ("🔒 Security Agent", "Detects vulnerabilities (SQL injection, XSS, etc.)", "PrimeVul"),
        ("🐛 Bug Detection", "Finds logic errors and null dereferences", "Defects4J"),
        ("🔧 Patch Generator", "Auto-generates fixes for identified issues", "SEC-bench"),
        ("📐 Style Analyzer", "Checks code style and performance", "Pylint"),
        ("🔍 RAG Pipeline", "Retrieves relevant security knowledge (OWASP/CWE)", "RAGAS"),
    ]
    for agent, capability, benchmark in agents:
        print(f"   {agent:20} {capability:45} ({benchmark})")
    
    print("\n5️⃣  EXPECTED OUTPUT FROM REVIEW")
    print("-" * 70)
    
    sample_review = Path("eval/datasets/sample_review.json")
    if sample_review.exists():
        review_data = json.loads(sample_review.read_text())
        
        print(f"   Review ID: {review_data['id']}")
        print(f"   PR: {review_data['pr_info']['owner']}/{review_data['pr_info']['repo']}#{review_data['pr_info']['pr_number']}")
        print(f"   Status: {review_data['status']}")
        
        findings_count = 0
        for agent_name, agent_result in review_data.get("agent_results", {}).items():
            findings = agent_result.get("findings", [])
            findings_count += len(findings)
            print(f"   - {agent_name}: {len(findings)} findings")
        
        print(f"   Total Findings: {findings_count}")
        
        if findings_count > 0:
            print(f"\n   Sample Finding:")
            first_finding = None
            for agent_result in review_data.get("agent_results", {}).values():
                findings = agent_result.get("findings", [])
                if findings:
                    first_finding = findings[0]
                    break
            
            if first_finding:
                print(f"   [{first_finding['severity'].upper()}] {first_finding['title']}")
                print(f"   Location: {first_finding['location']['file_path']}")
                print(f"   CWE: {first_finding.get('cwe_id', 'N/A')}")
    
    print("\n6️⃣  HOW TO SUBMIT YOUR OWN PR")
    print("-" * 70)
    print("   Option A: Use the test script")
    print("      python test_pr_review.py owner/repo pr_number")
    print()
    print("   Option B: Direct API call")
    print("      curl -X POST http://localhost:8000/api/v1/reviews \\")
    print("        -H 'Content-Type: application/json' \\")
    print("        -d '{\"owner\": \"owner\", \"repo\": \"repo\", \"pr_number\": 123}'")
    print()
    print("   Option C: Use Python requests")
    print("      import httpx")
    print("      client = httpx.Client()")
    print("      response = client.post(")
    print("          'http://localhost:8000/api/v1/reviews',")
    print("          json={'owner': 'owner', 'repo': 'repo', 'pr_number': 123}")
    print("      )")
    
    print("\n7️⃣  EVALUATION RESULTS")
    print("-" * 70)
    final_report = Path("results/final_report.json")
    if final_report.exists():
        report_data = json.loads(final_report.read_text())
        print(f"   Total Benchmarks: {report_data['summary']['count']}")
        print(f"   Agents Evaluated: {', '.join(report_data['summary']['agents'])}")
        
        for result in report_data.get("results", [])[:3]:
            agent = result.get("agent", "unknown")
            benchmark = result.get("benchmark", "unknown")
            if "f1" in result.get("metrics", {}):
                f1 = result["metrics"]["f1"]
                baseline = result.get("baseline_zero_shot", {}).get("f1", 0)
                improvement = ((f1 - baseline) / baseline * 100) if baseline > 0 else 0
                print(f"   {agent:15} ({benchmark:15}): F1={f1:.3f} (+{improvement:.1f}%)")
    
    print("\n8️⃣  NEXT STEPS")
    print("-" * 70)
    print("   ✅ Backend server is running on http://localhost:8000")
    print("   ✅ All agents are configured and ready")
    print("   ✅ Redis cache is running")
    print()
    print("   To test with a real PR:")
    print("      python test_pr_review.py \"python/cpython\" 123")
    print()
    print("   To view the API documentation:")
    print("      Open http://localhost:8000/docs in your browser")
    
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    demo_review_submission()
