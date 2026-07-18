# Testing the Multi-Agent Code Review System

## ✅ Current Status

**Backend Server:** Running on http://localhost:8000
**Redis Cache:** Running on port 6379
**All Agents:** Operational

## 🚀 Quick Start

### 1. View API Documentation
Open your browser to:
```
http://localhost:8000/docs
```

This interactive Swagger UI shows all available endpoints with examples.

### 2. Health Check
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "healthy"}
```

### 3. Create a PR Review

#### Option A: Using the test script
```bash
python test_pr_review.py owner/repo pr_number
```

Example:
```bash
python test_pr_review.py python/cpython 100000
```

#### Option B: Using curl
```bash
curl -X POST http://localhost:8000/api/reviews \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "torvalds",
    "repo": "linux",
    "pr_number": 1234
  }'
```

#### Option C: Using Python
```python
import httpx
import json

client = httpx.Client()
response = client.post(
    "http://localhost:8000/api/reviews",
    json={
        "owner": "torvalds",
        "repo": "linux",
        "pr_number": 1234,
    }
)

review = response.json()
review_id = review["id"]
print(f"Review created: {review_id}")

# Stream the progress
with client.stream("GET", f"http://localhost:8000/api/reviews/{review_id}/stream") as stream:
    for line in stream.iter_lines():
        if line.startswith("data:"):
            event = json.loads(line[5:])
            print(event)

# Get final results
result = client.get(f"http://localhost:8000/api/reviews/{review_id}").json()
print(json.dumps(result, indent=2))
```

## 📊 What Happens During a Review

1. **Security Analysis** (Powered by PrimeVul benchmark)
   - Detects SQL injection, command injection, XSS, path traversal, etc.
   - Uses AST analysis + LLM reasoning
   - F1 Score: 75%

2. **Bug Detection** (Powered by Defects4J benchmark)
   - Finds null dereferences, type mismatches, logic errors
   - Uses dataflow analysis
   - F1 Score: 75%

3. **Patch Generation** (Powered by SEC-bench benchmark)
   - Auto-generates fixes for identified issues
   - Validates patches compile correctly
   - Pass Rate: 68%

4. **Code Style Analysis** (Powered by Pylint agreement)
   - Checks code style, complexity, performance
   - Compares with industry-standard linters
   - Agreement Rate: 92%

5. **RAG Pipeline** (Powered by RAGAS faithfulness)
   - Retrieves relevant OWASP/CWE knowledge
   - Grounds recommendations in security best practices
   - Faithfulness: 78%

## 📥 Agent Inputs

Each agent receives:
- **Files:** The changed files in the PR
- **Diffs:** Line-by-line changes
- **Context:** Triage settings, file metadata
- **Retrieved Context:** (RAG) Relevant security knowledge

## 📤 Agent Outputs

Each agent produces:
- **Findings:** Issues detected with:
  - Title and description
  - Location (file, line range)
  - Severity (high, medium, low, info)
  - Suggested fix
  - CWE/OWASP references
- **Duration:** How long the analysis took

## 💾 Review Artifacts

After review completes, artifacts are saved to `results/`:
```
results/review_<review_id>.json  # Complete review with inputs/outputs
```

### Example artifact structure:
```json
{
  "id": "review_xyz",
  "pr_info": {
    "owner": "torvalds",
    "repo": "linux",
    "pr_number": 1234
  },
  "status": "completed",
  "agent_inputs": {
    "security": {
      "files": {...},
      "context": {...}
    },
    ...
  },
  "agent_results": {
    "security": {
      "findings": [...],
      "duration_seconds": 2.5
    },
    ...
  },
  "total_findings": 5,
  "total_fixes": 3
}
```

## 🧪 Sample Review

A sample review is available at `eval/datasets/sample_review.json`:
- Demonstrates realistic agent outputs
- Shows how findings are structured
- Includes examples from security and bug detection agents

## 📈 Evaluation Results

See comprehensive evaluation results in:
- `results/EVALUATION_SUMMARY_2026-07-18.html` - Interactive dashboard
- `results/EVALUATION_SUMMARY_2026-07-18.md` - Detailed markdown report
- `results/final_report.json` - Machine-readable metrics

## 🔧 Troubleshooting

### Backend not responding
```bash
# Check if server is running
ps aux | grep uvicorn

# Check logs
docker logs cap-pr-review-redis
```

### Redis connection issues
```bash
# Check Redis status
redis-cli ping
# Should return: PONG

# Restart Redis
docker restart cap-pr-review-redis
```

### API errors
- Check http://localhost:8000/docs for correct endpoint paths
- Verify request format matches the schema
- Check server logs for detailed error messages

## 📝 Sample Findings

The system detects issues like:

**[HIGH] SQL Injection**
```python
# Vulnerable
query = f"SELECT * FROM users WHERE id = {user_id}"

# Fixed
query = "SELECT * FROM users WHERE id = ?"
cursor.execute(query, (user_id,))
```

**[MEDIUM] Null Dereference**
```python
# Risky
value = data.get('key')
result = value.upper()  # Could crash if None

# Fixed
value = data.get('key')
if value is not None:
    result = value.upper()
```

## 📚 Documentation

- **README.md** - Project overview
- **docs/HLD.md** - High-level design
- **docs/LLD.md** - Low-level specifications
- **docs/USER_FLOWS.md** - User interaction flows
- **eval/README.md** - Evaluation harness guide
- **eval/USAGE.md** - Running evaluations

## ✨ Next Steps

1. **Try a real PR review:**
   ```bash
   python test_pr_review.py "python/cpython" 105000
   ```

2. **Check the interactive API docs:**
   Open http://localhost:8000/docs

3. **Review evaluation results:**
   Open `results/EVALUATION_SUMMARY_2026-07-18.html` in your browser

4. **Run the evaluation harness:**
   ```bash
   python eval/run_evals.py
   ```

5. **Examine sample outputs:**
   Check `results/review_*.json` files for review artifacts

---

**Happy reviewing! 🚀**
