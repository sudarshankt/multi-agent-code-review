# PR Input Sources & Output Storage

Complete documentation of how pull requests enter the system, are processed, and where results are stored.

**Table of Contents:**
1. [Input Sources](#input-sources)
2. [Data Flow](#data-flow)
3. [Output Storage](#output-storage)
4. [API Endpoints](#api-endpoints)
5. [Implementation Details](#implementation-details)
6. [Production Deployment](#production-deployment)

---

## Input Sources

The system accepts pull request reviews from **two independent sources**:

### 1. REST API Endpoint

**Endpoint:** `POST /api/v1/reviews`  
**Status Code:** 202 (Accepted) — review runs asynchronously in background  
**Source Code:** [src/api/endpoints/review.py](../src/api/endpoints/review.py#L158)

#### Request Formats

**Option A: Direct PR URL**
```bash
curl -X POST http://localhost:8000/api/v1/reviews \
  -H "Content-Type: application/json" \
  -d '{
    "pr_url": "https://github.com/owner/repo/pull/123"
  }'
```

**Option B: Component Parts**
```bash
curl -X POST http://localhost:8000/api/v1/reviews \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "owner",
    "repo": "repo",
    "pr_number": 123
  }'
```

#### Response

```json
{
  "id": "abc123def456",
  "status": "pending",
  "pr_info": {
    "owner": "owner",
    "repo": "repo",
    "pr_number": 123,
    "html_url": "https://github.com/owner/repo/pull/123"
  },
  "created_at": "2026-07-18T18:00:00Z",
  "total_findings": 0
}
```

The `id` field is the unique **review ID** used to track progress and retrieve results.

#### URL Parsing

The API automatically parses PR URLs using regex:
```regex
https://github\.com/([^/]+)/([^/]+)/pull/(\d+)
```

Invalid formats return:
```json
{
  "detail": "Invalid PR URL format. Expected https://github.com/{owner}/{repo}/pull/{pr_number}"
}
```

---

### 2. GitHub Webhook

**Endpoint:** `POST /api/v1/webhook/github`  
**Trigger Events:**
- Pull request opened (`pull_request.action == "opened"`)
- Pull request synchronized (`pull_request.action == "synchronize"`) — new commits pushed
- Pull request reopened (`pull_request.action == "reopened"`)

**Source Code:** [src/api/endpoints/webhook.py](../src/api/endpoints/webhook.py#L23)

#### Webhook Setup

Configure on GitHub repository:
1. Go to **Settings → Webhooks → Add webhook**
2. Set **Payload URL:** `https://your-domain/api/v1/webhook/github`
3. Set **Content type:** `application/json`
4. Select **Events:** Pull requests
5. Click **Add webhook**

#### Webhook Payload

GitHub sends the full webhook payload including:
```json
{
  "action": "opened|synchronize|reopened",
  "pull_request": {
    "number": 123,
    "title": "Add feature",
    "user": { "login": "author" },
    "head": {
      "ref": "feature-branch",
      "sha": "abc123..."
    },
    "base": {
      "ref": "main",
      "sha": "def456..."
    },
    "html_url": "https://github.com/owner/repo/pull/123"
  },
  "repository": {
    "name": "repo",
    "owner": { "login": "owner" }
  }
}
```

#### Webhook Response

```json
{
  "status": "enqueued",
  "review_id": "abc123def456"
}
```

or (if event is ignored):
```json
{
  "status": "ignored",
  "reason": "Action not actionable (closed)"
}
```

---

## Data Flow

Complete journey from PR input to final output:

```
┌──────────────────────────────────────────────────────────────┐
│ STEP 1: INPUT                                                │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Path A: REST API               Path B: GitHub Webhook      │
│  ├─ POST /reviews               ├─ Webhook received         │
│  │   ├─ pr_url or               │   ├─ Parse pull_request   │
│  │   │  owner/repo/pr_number    │   │   event               │
│  │   └─ Return 202 Accepted     │   └─ Enqueue async task   │
│  │                               │                          │
│  └─> Extract owner/repo/pr_num  └─> Extract owner/repo/num │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 2: PREFLIGHT VALIDATION                                 │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ ✓ Validate owner, repo, pr_number present                   │
│ ✓ Fetch PR metadata via GitHub API                          │
│ ✓ Filter eligible source files (*.py, *.js, *.ts, etc.)    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 3: STORAGE — In-Memory Review Object Created           │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ _reviews[review_id] = Review(                               │
│   id="abc123...",                                           │
│   pr_info=PRInfo(owner, repo, pr_number, ...),              │
│   status=ReviewStatus.PENDING,                              │
│   agent_results={},  ← Will be populated                   │
│   agent_inputs={},   ← Will be populated                   │
│   created_at=now()                                          │
│ )                                                            │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 4: FETCH PR CONTENT                                     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ GitHub API calls:                                            │
│ ├─ Get PR files (list of changed files)                     │
│ ├─ Get file diffs (git diff for each file)                  │
│ └─ Store in review.agent_inputs:                            │
│    {                                                         │
│      "security": { "files": {...}, "context": {...} },      │
│      "bug_detection": { "files": {...}, ... },              │
│      "style": { "files": {...}, ... },                      │
│      "performance": { "files": {...}, ... }                 │
│    }                                                         │
│                                                              │
│ Status update: PENDING → FETCHING → ANALYZING               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 5: RUN ORCHESTRATOR (4 Agents in Parallel)              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ Each agent receives:                                         │
│ - files: {file_path: file_content}                          │
│ - context: {diffs, triage_enabled, ...}                     │
│                                                              │
│ Each agent returns:                                          │
│ - findings: [Finding, Finding, ...]                         │
│                                                              │
│ Agents:                                                      │
│ 1. Security Agent                                            │
│    └─ Output: 5-10 findings (vulnerabilities, injection)    │
│ 2. Bug Detection Agent                                       │
│    └─ Output: 3-7 findings (logic errors, edge cases)       │
│ 3. Style Analyzer Agent                                      │
│    └─ Output: 2-5 findings (linting, conventions)           │
│ 4. Performance Agent                                         │
│    └─ Output: 2-4 findings (complexity, memory leaks)       │
│                                                              │
│ Status: ANALYZING                                            │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 6: AGGREGATE & STORE FINDINGS                           │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ review.agent_results = {                                    │
│   "security": {                                              │
│     "agent_name": "security",                                │
│     "status": "completed",                                   │
│     "findings": [                                            │
│       Finding(                                               │
│         id="f1",                                             │
│         file_path="src/app.py",                              │
│         line_number=45,                                      │
│         category="security",                                 │
│         severity="high",                                     │
│         title="SQL Injection",                               │
│         cwe_id="CWE-89",                                     │
│         ...                                                  │
│       ),                                                      │
│       ...                                                    │
│     ],                                                        │
│     "duration_seconds": 12.5                                 │
│   },                                                         │
│   "bug_detection": { ... },                                  │
│   "style": { ... },                                          │
│   "performance": { ... }                                     │
│ }                                                            │
│                                                              │
│ review.total_findings = sum of all findings                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 7: PATCH GENERATION (If Fixes Available)                │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ For each fixable finding:                                    │
│ - Apply remediation logic                                    │
│ - Generate fixed code                                        │
│ - Validate syntax                                            │
│                                                              │
│ Status: FIXING → TESTING                                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 8: OUTPUT STORAGE                                       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ Output Location A: In-Memory Review                          │
│ ├─ _reviews[review_id] stays in memory                       │
│ ├─ Accessible via GET /api/v1/reviews/{id}                  │
│ └─ Survives until service restart                           │
│                                                              │
│ Output Location B: File System Artifacts                     │
│ ├─ Directory: results/generated/{review_id}/                │
│ ├─ Contents: Fixed code files                               │
│ └─ Created by: persist_generated_artifacts()                │
│                                                              │
│ Output Location C: GitHub PR                                 │
│ ├─ Branch: cap-fix-{review_id}                              │
│ ├─ PR URL stored in: review.fix_pr_url                       │
│ └─ Created by: Fix Agent (if fixes generated)               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 9: COMPLETION                                           │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ Status: CREATING_PR → COMPLETED (or FAILED)                  │
│ completed_at = now()                                         │
│ SSE stream closes (terminal status)                          │
│                                                              │
│ Review object now contains:                                  │
│ - All findings from all agents                               │
│ - All fixes (if generated)                                   │
│ - Link to fix PR (if created)                                │
│ - Complete timing information                                │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Output Storage

Three independent storage systems for review outputs:

### 1. In-Memory Review Store (Current Session)

**Location:** `_reviews` dictionary in [src/api/endpoints/review.py](../src/api/endpoints/review.py#L29)

```python
_reviews: dict[str, Review] = {}
```

**Lifetime:** From creation until service restart  
**Data Structure:** Fully populated `Review` object  

**Contains:**
- PR metadata (owner, repo, pr_number, author, branches, SHA, URL)
- All agent results with findings
- All patches and fix artifacts
- Complete timing (created_at, updated_at, completed_at)
- Status and error messages

**Access:** REST API endpoints
```bash
GET /api/v1/reviews               # List all reviews
GET /api/v1/reviews/{review_id}   # Get specific review
```

**Limitations:**
- ⚠️ Lost on service restart
- ⚠️ Not persisted to disk
- ✅ Fast access (in-memory)
- ✅ Supports streaming updates

### 2. File System Artifacts (Generated Fixes)

**Location:** `results/generated/{review_id}/`  
**Created by:** [src/services/artifact_service.py](../src/services/artifact_service.py)  
**When:** After patches are successfully generated

**Directory Structure:**
```
results/generated/
├── abc123def456/              # review_id
│   ├── src/
│   │   ├── app.py             # Fixed version
│   │   └── utils.py           # Fixed version
│   ├── tests/
│   │   └── test_app.py        # Fixed version
│   └── [other files]
│
├── xyz789ijk012/              # Another review
│   ├── src/
│   │   └── module.py
│   └── ...
│
└── ...
```

**File Contents:**
- Complete fixed Python/JavaScript/TypeScript files
- With all patches applied
- Ready to review or merge

**Access:**
```bash
cat results/generated/{review_id}/src/module.py  # View fixed file
```

**Persistence:**
- ✅ Survives service restart
- ✅ Easily inspected manually
- ✅ Can be committed to git
- ✅ Provides before/after comparison (in git)

**API Reference:**
Stored path is available in `FixResult.artifact_path` from agent responses.

### 3. GitHub Pull Request (Auto-Generated Fix PR)

**Location:** GitHub repository  
**Created by:** Fix Agent (if fixes are applicable)  
**Format:** New pull request with patches

**PR Details:**
```
Title: "CAP Review: {review_id} - Auto-generated fixes"
Branch: cap-fix-{review_id}
Base: {original_pr_base_branch}
Description: Lists all fixes with explanation
Files Changed: All patched files
```

**Access:**
```python
review.fix_pr_url
# Returns: "https://github.com/owner/repo/pull/456"
```

**Workflow:**
1. **Create:** Fix Agent generates patches → Creates new branch → Opens PR
2. **Review:** Human reviews patches in GitHub UI
3. **Merge:** Approved patches are merged into base branch
4. **Track:** Review object stores URL for reference

**Stored in:**
- `review.fix_pr_url` (string)
- `review.fix_branch` (branch name)

---

## API Endpoints

Complete API reference for PR handling:

### Create Review (Async)

**Request:**
```bash
POST /api/v1/reviews
Content-Type: application/json

# Format A: PR URL
{
  "pr_url": "https://github.com/owner/repo/pull/123"
}

# Format B: Components
{
  "owner": "owner",
  "repo": "repo",
  "pr_number": 123
}
```

**Response:**
```
202 Accepted

{
  "id": "abc123def456",
  "status": "pending",
  "pr_info": {
    "owner": "owner",
    "repo": "repo",
    "pr_number": 123,
    "title": "Add feature",
    "author": "user",
    "html_url": "https://github.com/owner/repo/pull/123"
  },
  "created_at": "2026-07-18T18:00:00Z",
  "total_findings": 0
}
```

### List All Reviews

**Request:**
```bash
GET /api/v1/reviews?skip=0&limit=10
```

**Response:**
```
200 OK

{
  "total": 42,
  "skip": 0,
  "limit": 10,
  "items": [
    {
      "id": "abc123def456",
      "status": "completed",
      "pr_info": { ... },
      "total_findings": 15,
      "total_fixes": 3,
      "completed_at": "2026-07-18T18:15:00Z"
    },
    ...
  ]
}
```

### Get Review Details

**Request:**
```bash
GET /api/v1/reviews/{review_id}
```

**Response:**
```
200 OK

{
  "id": "abc123def456",
  "status": "completed",
  "pr_info": { ... },
  "agent_results": {
    "security": {
      "agent_name": "security",
      "status": "completed",
      "findings": [
        {
          "id": "f1",
          "file_path": "src/app.py",
          "line_number": 45,
          "category": "security",
          "severity": "high",
          "title": "SQL Injection",
          "description": "...",
          "cwe_id": "CWE-89",
          "confidence": "high",
          "source": "llm",
          "remediation": "Use parameterized queries"
        },
        ...
      ],
      "duration_seconds": 12.5
    },
    "bug_detection": { ... },
    "style": { ... },
    "performance": { ... }
  },
  "total_findings": 15,
  "total_fixes": 3,
  "fix_pr_url": "https://github.com/owner/repo/pull/456",
  "created_at": "2026-07-18T18:00:00Z",
  "completed_at": "2026-07-18T18:15:00Z"
}
```

### Stream Progress (SSE)

**Request:**
```bash
GET /api/v1/sse/{review_id}
```

**Response:**
```
200 OK
Content-Type: text/event-stream

data: {"type":"status_update","review_id":"abc123","status":"pending"}

data: {"type":"status_update","review_id":"abc123","status":"fetching"}

data: {"type":"status_update","review_id":"abc123","status":"analyzing"}

data: {"type":"findings_update","agent":"security","count":7}

data: {"type":"findings_update","agent":"bug_detection","count":3}

data: {"type":"findings_update","agent":"style","count":2}

data: {"type":"status_update","review_id":"abc123","status":"completed"}
```

---

## Implementation Details

### Review Model

**File:** [src/models/review.py](../src/models/review.py)

```python
class Review(BaseModel):
    id: str                              # Unique UUID, auto-generated
    pr_info: PRInfo                      # Input PR metadata
    status: ReviewStatus                 # State machine: pending → completed
    agent_results: dict[str, AgentResult]  # Findings from all agents
    agent_inputs: dict[str, dict]        # Input files/diffs sent to agents
    total_findings: int                  # Aggregated count
    total_fixes: int                     # Count of applied patches
    fix_branch: str | None              # Branch name for fixes
    fix_pr_url: str | None              # URL to GitHub fix PR
    triggered_by: str | None            # "api" or "webhook"
    error_message: str | None           # If status == FAILED
    created_at: datetime                # Review creation time
    updated_at: datetime                # Last update time
    completed_at: datetime | None       # Completion time
```

### PRInfo Model

**File:** [src/models/review.py](../src/models/review.py)

```python
class PRInfo(BaseModel):
    owner: str                           # Repository owner
    repo: str                            # Repository name
    pr_number: int                       # Pull request number
    title: str | None = None            # PR title
    author: str | None = None           # PR author login
    head_branch: str | None = None      # Source branch name
    base_branch: str | None = None      # Target branch name
    head_sha: str | None = None         # Latest commit SHA
    html_url: str | None = None         # GitHub PR URL
```

### Finding Model

**File:** [src/models/finding.py](../src/models/finding.py)

```python
class Finding(BaseModel):
    id: str                              # Unique finding UUID
    file_path: str                       # Path to file in repo
    line_number: int                     # Line where issue occurs
    category: Category                   # security|bug_detection|style|performance
    severity: Severity                   # critical|high|medium|low|info
    title: str                           # Finding summary (1 line)
    description: str                     # Detailed explanation
    cwe_id: str | None = None           # CWE classification
    confidence: Confidence               # high|medium|low
    source: FindingSource               # llm|ast_analyzer|linter
    remediation: str | None = None      # Suggested fix
```

### AgentResult Model

**File:** [src/models/review.py](../src/models/review.py)

```python
class AgentResult(BaseModel):
    agent_name: str                      # "security", "bug_detection", etc.
    status: str                          # pending|running|completed|failed|skipped
    findings: list[Finding]              # Analysis results
    duration_seconds: float | None       # How long agent ran
    error: str | None                   # Error if status == failed
```

### Status Lifecycle

```
PENDING          Initial state, queued for processing
   ↓
FETCHING         Downloading PR files and diffs from GitHub
   ↓
ANALYZING        Running agents to find issues
   ↓
FIXING           Generating patches for fixable issues
   ↓
TESTING          Validating patches (if enabled)
   ↓
CREATING_PR      Creating/updating GitHub fix PR
   ↓
COMPLETED        Done (terminal status)

Alternative paths:
FETCHING    → FAILED      (GitHub API error)
ANALYZING   → FAILED      (Agent crash)
CREATING_PR → FAILED      (GitHub API error)
ANY         → SKIPPED     (Cancelled/disabled)
```

---

## Production Deployment

### For Production Use

The current implementation is **MVP (in-memory storage)**. For production, consider:

#### 1. Persistent Database
```python
# Replace in-memory _reviews with database
# Option A: SQLite (for single-server)
# Option B: PostgreSQL (for multi-server)
# Option C: Firestore/DynamoDB (for serverless)

# Implement:
- save_review(review: Review) → str (review_id)
- get_review(review_id: str) → Review | None
- list_reviews(filter, limit, offset) → list[Review]
- update_review(review_id: str, **updates) → Review
```

#### 2. Task Queue
```python
# Replace asyncio.create_task() with durable queue
# Options: Redis/RQ, Celery, AWS SQS, Google Cloud Tasks

# Benefits:
- Reviews survive service restarts
- Retry on failure
- Parallel processing across workers
- Progress tracking
```

#### 3. Result Archival
```python
# Store artifacts longer than session lifetime
# Options: AWS S3, Google Cloud Storage, Azure Blob

# For each review:
- Upload results/generated/{review_id}/ to cloud
- Keep local cache for recent reviews
- Archive older results to cold storage
```

#### 4. Authentication & Authorization
```python
# Add to API endpoints:
- API key validation
- Rate limiting (per user/org)
- Access control (who can see which reviews)
- Audit logging
```

#### 5. Webhooks Security
```python
# Verify GitHub webhook signature:
import hmac
import hashlib

github_secret = os.getenv("GITHUB_WEBHOOK_SECRET")
signature = request.headers.get("X-Hub-Signature-256")
payload = await request.body()

expected = "sha256=" + hmac.new(
    github_secret.encode(),
    payload,
    hashlib.sha256
).hexdigest()

if not hmac.compare_digest(signature, expected):
    raise HTTPException(status_code=401)
```

### Scaling Considerations

**Single Server (MVP):**
- ✅ Simple in-memory storage
- ✅ No database setup
- ✅ Fast access
- ⚠️ Limited to ~500 concurrent reviews (depending on memory)
- ⚠️ Data lost on restart

**Multiple Servers:**
- ✅ Database for shared state
- ✅ Redis queue for tasks
- ✅ Load balancer for incoming requests
- ✅ Horizontal scaling
- ✅ High availability
- ⚠️ Complexity increases

**Recommended for Production:**
```
Load Balancer
    ↓
┌─────────────────────────────────────────┐
│ API Server (x3 instances)               │
│ - Flask/FastAPI                         │
│ - Stateless                             │
└─────────────────────────────────────────┘
    ↓                           ↓
PostgreSQL                  Redis Queue
(reviews,              (task queue,
findings, etc)        caching)
    ↓
S3 / Cloud Storage
(artifacts, backups)
```

---

## Troubleshooting

### Review Stuck in "FETCHING"

**Cause:** GitHub API error or timeout  
**Check:**
```bash
curl http://localhost:8000/api/v1/reviews/{review_id}

# Look for error_message field
```

**Fix:**
```bash
# Manually retry
curl -X POST http://localhost:8000/api/v1/reviews \
  -d '{"pr_url": "https://github.com/owner/repo/pull/123"}'
```

### Findings Not Showing Up

**Cause:** Agent crashed or timed out  
**Check:**
```bash
# Look at agent_results
curl http://localhost:8000/api/v1/reviews/{review_id} | jq .agent_results

# Check each agent status (should be "completed")
# If "failed", check "error" field
```

### Fix PR Not Created

**Cause:** No fixable findings, or GitHub auth error  
**Check:**
```bash
# Verify findings exist and are fixable
curl http://localhost:8000/api/v1/reviews/{review_id} | jq .agent_results.*.findings

# Check GitHub token has write permissions
echo $GITHUB_TOKEN  # Should be set
```

### Results Lost After Restart

**Expected Behavior (MVP):** In-memory storage is lost  
**Solution:** Implement persistent database (see Production Deployment)

---

## Summary

| Aspect | MVP | Production |
|--------|-----|------------|
| **Input** | REST API + Webhook | ✅ Same |
| **Storage** | In-memory dict | PostgreSQL + Redis |
| **Artifacts** | results/generated/ | S3 + local cache |
| **Persistence** | Session only | Permanent |
| **Scaling** | Single server | Multiple servers |
| **Reliability** | Good | HA + redundancy |
| **Retention** | Until restart | Configurable |

