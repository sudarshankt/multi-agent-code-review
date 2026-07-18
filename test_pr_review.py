#!/usr/bin/env python3
"""
Test script to submit a GitHub PR for review and collect agent inputs/outputs.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx


async def submit_pr_for_review(
    owner: str,
    repo: str,
    pr_number: int,
    backend_url: str = "http://localhost:8000",
) -> dict:
    """Submit a PR to the review API and stream results."""
    
    client = httpx.AsyncClient(timeout=300.0)
    
    print(f"📤 Submitting PR: {owner}/{repo}#{pr_number}")
    print(f"🔗 Backend: {backend_url}")
    print("-" * 70)
    
    # Step 1: Create review request
    review_payload = {
        "owner": owner,
        "repo": repo,
        "pr_number": pr_number,
    }
    
    try:
        # Submit review
        response = await client.post(
            f"{backend_url}/api/reviews",
            json=review_payload,
        )
        response.raise_for_status()
        review = response.json()
        review_id = review.get("id")
        
        print(f"✅ Review created: {review_id}")
        print(f"📊 Status: {review.get('status')}")
        print()
        
        # Step 2: Stream the review progress using SSE
        print("🔄 Streaming review progress...")
        print("-" * 70)
        
        findings_count = 0
        agents_completed = set()
        
        async with client.stream(
            "GET",
            f"{backend_url}/api/reviews/{review_id}/stream",
        ) as stream:
            async for line in stream.aiter_lines():
                if not line.strip():
                    continue
                    
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                        
                        # Handle different event types
                        if data.get("type") == "agent_start":
                            agent = data.get("agent", "unknown")
                            print(f"  🤖 {agent.upper()} agent starting...")
                            
                        elif data.get("type") == "agent_complete":
                            agent = data.get("agent", "unknown")
                            findings = data.get("findings", [])
                            findings_count += len(findings)
                            agents_completed.add(agent)
                            print(f"  ✅ {agent.upper()} agent completed ({len(findings)} findings)")
                            
                        elif data.get("type") == "finding":
                            finding = data.get("finding", {})
                            title = finding.get("title", "Unknown")
                            severity = finding.get("severity", "info").upper()
                            print(f"     📌 [{severity}] {title}")
                            
                        elif data.get("type") == "progress":
                            message = data.get("message", "")
                            print(f"  ℹ️  {message}")
                            
                        elif data.get("type") == "complete":
                            print(f"\n✨ Review completed!")
                            
                    except json.JSONDecodeError:
                        pass
        
        print()
        print("-" * 70)
        
        # Step 3: Get final review with agent inputs/outputs
        print("\n📊 Fetching complete review with agent inputs/outputs...")
        response = await client.get(f"{backend_url}/api/reviews/{review_id}")
        response.raise_for_status()
        review_result = response.json()
        
        # Step 4: Display summary
        print(f"\n{'='*70}")
        print("📋 REVIEW SUMMARY")
        print(f"{'='*70}")
        print(f"Review ID: {review_result.get('id')}")
        print(f"PR: {review_result['pr_info']['owner']}/{review_result['pr_info']['repo']}#{review_result['pr_info']['pr_number']}")
        print(f"Status: {review_result.get('status')}")
        print(f"Total Findings: {review_result.get('total_findings', 0)}")
        print(f"Total Fixes: {review_result.get('total_fixes', 0)}")
        print()
        
        # Step 5: Display agent results
        if review_result.get("agent_results"):
            print(f"{'='*70}")
            print("🤖 AGENT RESULTS")
            print(f"{'='*70}")
            
            for agent_name, agent_result in review_result["agent_results"].items():
                status = agent_result.get("status", "unknown")
                findings = agent_result.get("findings", [])
                duration = agent_result.get("duration_seconds", 0)
                
                print(f"\n{agent_name.upper()}:")
                print(f"  Status: {status}")
                print(f"  Findings: {len(findings)}")
                print(f"  Duration: {duration:.2f}s")
                
                if findings:
                    for finding in findings[:3]:  # Show first 3
                        title = finding.get("title", "Unknown")
                        severity = finding.get("severity", "info")
                        print(f"    - [{severity}] {title}")
                    
                    if len(findings) > 3:
                        print(f"    ... and {len(findings) - 3} more")
        
        # Step 6: Display agent inputs
        if review_result.get("agent_inputs"):
            print(f"\n{'='*70}")
            print("📥 AGENT INPUTS")
            print(f"{'='*70}")
            
            for agent_name, agent_input in review_result["agent_inputs"].items():
                files = agent_input.get("files", {})
                context = agent_input.get("context", {})
                
                print(f"\n{agent_name.upper()}:")
                print(f"  Files: {len(files) if isinstance(files, dict) else 'N/A'}")
                if isinstance(context, dict):
                    print(f"  Triage: {context.get('triage_enabled', False)}")
                    print(f"  Diffs available: {bool(context.get('diffs'))}")
        
        # Step 7: Save the review artifact
        output_path = Path("results") / f"review_{review_id}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(review_result, indent=2), encoding="utf-8")
        print(f"\n💾 Review artifact saved: {output_path}")
        
        return review_result
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise
    finally:
        await client.aclose()


async def main():
    """Main entry point."""
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python test_pr_review.py <owner/repo> <pr_number>")
        print("Example: python test_pr_review.py torvalds/linux 1")
        sys.exit(1)
    
    repo_str = sys.argv[1]
    pr_number = int(sys.argv[2])
    
    if "/" not in repo_str:
        print("Error: repo must be in format owner/repo")
        sys.exit(1)
    
    owner, repo = repo_str.split("/", 1)
    
    await submit_pr_for_review(owner, repo, pr_number)


if __name__ == "__main__":
    asyncio.run(main())
