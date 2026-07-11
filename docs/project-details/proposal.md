# Advanced Certification Programme in Agentic and Generative AI
## CAPSTONE PROJECT PROPOSAL - TEAM 10
### Project 1: Multi-Agent Code Review & Auto-Debugging System
#### IISc – TalentSprint | GenAI C2

---

### 1. Project Title
**Multi-Agent Code Review & Auto-Debugging System**

---

### 2. Brief Problem Statement
Software teams lose significant time to manual code reviews that are inconsistent, expertise-dependent, and unscalable. Security vulnerabilities are missed, bugs go undetected, coding standards drift, and patch generation remains manual. This project builds an AI-powered, LangGraph-orchestrated multi-agent pipeline automating security analysis, bug detection, style checking, patch generation, and test creation — grounded via RAG over OWASP/CWE knowledge bases.

---

### 3. Background Information
Modern DevSecOps demands shift-left security. Static tools (Bandit, SonarQube, Pylint) catch surface violations but cannot reason contextually, generate patches, or cite authoritative references. LLMs combined with LangGraph orchestration and RAG enable a new class of intelligent code review tools.

#### Applications:
* **CI/CD pipeline integration** on pull requests
* **IDE plugin** for real-time developer feedback
* **Security audit automation** for legacy codebases
* **Educational tooling** for junior developers

---

### 4. Motivation for Selection
1. **Technical depth:** Full agentic AI stack — LangGraph, RAG, Pydantic, FastAPI — ideal for this programme.
2. **Industry relevance:** AI code review is among the highest-investment enterprise AI areas in 2025–2026 (GitHub Copilot, JetBrains AI).
3. **Profile impact:** A multi-agent, RAG-grounded, evaluation-backed system differentiates resumes for Staff/Senior AI engineering roles.
4. **Tractable scope:** Public datasets, open-source tools; build plan aligns precisely with the 4 mentored sessions.

---

### 5. Dataset Description & Sources

| Dataset | Source | Content | Usage in Project |
| :--- | :--- | :--- | :--- |
| **CodeXGLUE** | Microsoft/GitHub | 110K samples; CWE labels; vulnerability annotations across multiple languages | Security Agent training & eval |
| **Defects4J** | GitHub (rjust) | 835 real Java bugs with bug-fix pairs, stack traces, corrected implementations | Bug Detection Agent eval |
| **CodeSearchNet** | HuggingFace | 2M+ code-docstring pairs across 6 languages | Code embedding baseline |
| **GitHub Python Repos** | Open-source | PEP8 violations, high complexity, performance anti-patterns | Style & Performance Agent |
| **OWASP Top-10 + CWE** | owasp.org / cwe.mitre.org | Vulnerability descriptions, attack patterns, mitigations — RAG knowledge base | ChromaDB RAG retrieval |
| **Synthetic Samples** | LLM-generated (team) | Targeted edge-case buggy/vulnerable snippets | Stress-test & augment eval |

---

### 6. Current Benchmarks & References
* **CodeXGLUE** (Lu et al., 2021): Vulnerability detection F1 ~72%; target > 0.75.  
  [https://github.com/microsoft/CodeXGLUE](https://github.com/microsoft/CodeXGLUE)
* **Defects4J** (Just et al., 2014): Best fault localization ~40–60%; patch pass rate target > 70%.  
  [https://github.com/rjust/defects4j](https://github.com/rjust/defects4j)
* **CodeBERT** (Feng et al., 2020): Defect detection ~65% accuracy — embedding baseline.  
  [https://arxiv.org/abs/2002.08155](https://arxiv.org/abs/2002.08155)
* **OWASP SAST tools** (Checkmarx, SonarQube): 60–80% precision on OWASP Top-10; our RAG+LLM pipeline targets exceeding this.

---

### 7. Proposed Plan

#### 7a. Approach: LangGraph Supervisor–Worker Multi-Agent Architecture
A Supervisor Agent routes code to five specialized sub-agents sharing a common LangGraph state graph:

| Agent | Responsibility | Key Tools |
| :--- | :--- | :--- |
| **Security Analysis** | OWASP Top-10 detection; RAG-grounded citations from ChromaDB | LLM + ChromaDB RAG |
| **Bug Detection** | AST analysis for logic errors, runtime exceptions, faulty control flow | `ast`, `tree-sitter`, LLM |
| **Style & Performance** | PEP8 compliance; cyclomatic/cognitive complexity; code smells | `Pylint`, `Radon`, LLM |
| **Patch Generation** | Structured code fixes + unified diffs via Pydantic schemas | LLM + Pydantic v2 |
| **Test Generation** | Auto-generate pytest tests; sandbox execution; coverage check | LLM + `pytest` + `subprocess` |

#### 7b. Packages & Tools

| Category | Tools | Purpose |
| :--- | :--- | :--- |
| **Orchestration** | LangGraph, LangChain LCEL | Multi-agent state graph & conditional routing |
| **LLMs** | Groq (Llama 3), OpenAI GPT-4o-mini | Reasoning, code generation, structured output |
| **RAG / Vector DB** | ChromaDB, FAISS, sentence-transformers | OWASP/CWE retrieval; semantic search |
| **Static Analysis** | Pylint, Bandit, Radon, ast | PEP8 validation, vuln flags, complexity metrics |
| **Backend / UI** | FastAPI, Uvicorn, Streamlit | REST API & interactive code review dashboard |
| **Evaluation** | RAGAS, scikit-learn, pytest | RAG quality, F1 metrics, patch validation |
| **MLOps** | LangSmith, Docker, GitHub Actions | Agent tracing, containerization, CI pipeline |

#### 7c. Algorithms | 7d. Metrics

##### Key Algorithms:
* **RAG:** Dense retrieval (sentence-transformers) + ChromaDB; cross-encoder re-ranking (top-k=5)
* **Bug Detection:** Python ast parse-tree pattern matching + LLM zero-shot reasoning
* **Vuln Classification:** LLM zero-shot over OWASP Top-10 with RAG-grounded context
* **Complexity:** McCabe cyclomatic, cognitive complexity, Halstead metrics via Radon
* **Patch:** Pydantic-constrained LLM diff generation; difflib unified diffs

##### Evaluation Metrics & Targets:
* **Vulnerability Detection** F1 > 0.75 (Precision, Recall on CodeXGLUE)
* **Bug Detection:** False Positive Rate < 20%
* **Patch Pass Rate** > 70% on pytest execution (Defects4J)
* **RAGAS** Faithfulness > 0.75; Answer Relevance > 0.70
* **PEP8 Detection** > 90% agreement with Pylint baseline
* **End-to-end latency** < 30 seconds per review request

---

#### 7e. Stages & Deliverables | 7f. Deployment | 7g. MLOps

| Phase | Activity | Deliverable |
| :--- | :--- | :--- |
| **Phase 1 – Foundation** | Env setup, datasets, ChromaDB index | Dev env ready; OWASP/CWE indexed; dataset schema validated |
| **Phase 2 – Core Build** | Security + Bug + Style agents; LangGraph | 3 functional agents; LangGraph supervisor routing operational with unit tests |
| **Phase 3 – Integration** | Patch + Test agents; FastAPI; LangSmith | Full 5-agent pipeline; FastAPI REST live; LangSmith traces visible |
| **Phase 4 – Testing** | RAGAS eval; F1/patch metrics; error analysis | Evaluation report with quantitative scores; refined prompts & retrieval |
| **Phase 5 – Deploy** | Streamlit UI; Docker; docs; demo video | Live app on Streamlit Cloud/HF Spaces; Docker image; 5-min walkthrough |

**Deployment:** Streamlit Cloud (primary) or HuggingFace Spaces; FastAPI on Uvicorn in Docker; secrets via `.env`.  
**MLOps:** LangSmith for agent tracing; RAGAS in CI; Docker for reproducible packaging.

---

### 8. Preliminary Exploratory Data Analysis

#### CodeXGLUE
110K samples; Python 42%, Java 31%, C/C++ 27%. Class imbalance: 18% vulnerable $\rightarrow$ stratified sampling applied. Mean snippet ~320 tokens (95th pct ~1,200 tokens — within LLM context window).

#### Defects4J
835 bugs, 17 Java projects. Bug categories: logic errors 31%, null pointers 22%, API misuse 19%. 80% of fixes < 10 lines — tractable for patch generation.

#### OWASP / CWE Knowledge Base
OWASP Top-10 (2021): 10 categories; ~150 CWE entries; chunked at 512-token overlapping windows. Informal RAG test: top-5 chunks show high relevance; cross-encoder re-ranking improves over BM25.

---

### 9. Expected Outcomes
1. **5-agent LangGraph pipeline** (Security, Bug, Style, Patch, Test) fully operational
2. **RAG pipeline grounded on OWASP/CWE;** RAGAS Faithfulness > 0.75
3. **FastAPI backend** enabling CI/CD integration
4. **Streamlit dashboard** with interactive code review & patch diffing
5. **Evaluation report:** F1 > 0.75, patch pass rate > 70%
6. **Dockerized deployment** + 5-min walkthrough demo video
7. **20-page final report** with architecture, metrics, limitations

---

### 10. Demonstration Strategy

#### Pitch (May 31, 5–8 min):
* Problem + proposed solution slides; Security Agent demo on a vulnerable Python sample

#### Mentored Sessions (Jul 5, 12, 19, 26):
* **S1:** RAG query demo.
* **S2:** LangGraph 3-agent routing.
* **S3:** End-to-end via Streamlit.
* **S4:** Polished demo + eval metrics.

#### Final Presentation (Aug 1–2, 30 min):
* **10 min:** Architecture.
* **12 min:** Live demo (buggy code $\rightarrow$ 5 agents $\rightarrow$ patch + pytest).
* **5 min:** RAGAS/F1 results.
* **3 min:** Limitations + Q&A.

---

### 11. Proposed Timeline

| Timeline | Session / Milestone | Weekly Progress Goals & Deliverables |
| :--- | :--- | :--- |
| **Week 1 – Jul 5** | Mentored Session 1 | Project planning, requirement analysis, and initial environment setup. |
| **Week 2 – Jul 12** | Mentored Session 2 | Core development in progress with key components under implementation. |
| **Week 3 – Jul 19** | Mentored Session 3 | Continued development, integration of major modules, and preliminary validation. |
| **Week 6 – Jul 26** | Mentored Session 4 | Project refinement, evaluation, documentation, and preparation for final submission and demonstration. |
| **Jul 28** | Final Report | Project report compilation and submission, including implementation details and key findings. |
| **Aug 1–2** | Final Presentation | Project presentation, demonstration, and discussion of outcomes with evaluators. |

---

### 12. Team Members

| # | Trainee ID | Full Name | Email Address |
| :--- | :--- | :--- | :--- |
| 1 | 2301852 | Ravi Agarwal | ravi.mragarwal@gmail.com |
| 2 | 2510815 | Dorothy Christina Rajkumar | dorothyrajkumar811@gmail.com |
| 3 | 2236325 | Smita Anil Gholkar | smitagh@gmail.com |
| 4 | 2512432 | Sudarshan Kidambi Thiruvengadam | sudarshan.kidambi@gmail.com |
| 5 | 2513531 | DEEPKANT JAIN | deepkant.intel@gmail.com |
| 6 | 2513970 | Tarun Pareek | pareektarunsss@gmail.com |
| 7 | 2513900 | GANESH BHEEMARAJ | ganesha.5@gmail.com |
| 8 | 2512156 | Vinod Kumar Pinniboyina | vinode3power@gmail.com |
| 9 | 2511993 | Veeresh Nete | kneteviresh@gmail.com |
| 10 | 2513978 | Komal Namdeo Bahetwar | komalnbahetwar@gmail.com |
| 11 | 2511659 | Suman Prakash | suman.nanda@gmail.com |

---

### 13. Designated Team Coordinator
**Komal Namdeo Bahetwar (Trainee ID: 2513978)** will serve as the designated Team Coordinator and primary point of contact for mentor communications, submissions, scheduling, and coordination across all project activities.

***
*Advanced Certification Programme in Agentic and Generative AI | IISc – TalentSprint | GenAI C2 | COPYRIGHT © TALENTSPRINT, 2026*