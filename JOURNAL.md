# Week 7 — Issue selection

**Issue link:** https://github.com/ascherj/pathreview/issues/18

**Issue title:** #18 Add end-to-end ingestion test with a sample resume fixture

**Tier:** [ ] Tier 1  [✅] Tier 2  [ ] Tier 3

**Problem summary:**  
The PathReview project is missing a complete, end-to-end test suite for ingestion pipeline (parsing, chunking, embedding, and storing documents). This test suite must be located in `tests/integration/test_ingestion_pipeline.py` and use the fixtures in `tests/fixtures/sample_resumes`.

**Branch name:** `test/18-ingestion-pipeline-tests`

**Setup confirmation:** [✅] App runs locally at localhost:5173

**Cohort ledger:** [✅] Issue added to cohort ledger

## Is This Issue Right for Me?
### Part 1 — Understanding the Issue
* **Can I explain what this issue is asking for in my own words?**  
✅ I can explain the problem and the expected behavior in 2–3 sentences without reading the issue: The problem summary can be found above.
* **Do I understand which part of the app is affected?**  
✅ I've located the relevant files and confirmed they exist in the codebase: `ingestion/pipeline.py`
* **Do I understand what "done" looks like?**  
✅ I can describe a concrete before-and-after: what the user sees before the fix and what they see after:  
*Before:* The ingestion pipeline is untested and could produce undetected bugs due to the absence of end-to-end integration test suite.  
*After:* A complete integration test suite exists at `tests/integration/test_ingestion_pipeline.py` and stress-tests the document ingestion feature. This test suite uses `pytest` and follows the code patterns and convenions that are set by the existing test suites in `tests/unit`

### Part 2 — Tier Fit
* **Is the tier a realistic match for where I am right now?**  
✅ If I've contributed to large codebases before: Tier 2 or 3 is fair game.

### Part 3 — Codebase Readiness
* **Can I find the relevant code?**  
✅ I've found and read the specific code the issue references (not just the file — the function or section).
* **Do I understand the surrounding code well enough to change it safely?**  
✅ I've read enough surrounding context that I can write a rough plan for the fix without looking anything up.
* **Have I read the relevant test file?**  
✅ I've found the test file for my module and read at least one test end-to-end.

### Part 4 — Scope and Time
* **How many others are already working on this issue?**  
✅ I've checked the issue comments and the ledger's Claims count, and I'm fine with how many others are on this issue.
* **Is the scope realistic for Weeks 8–9?**  
✅ I've estimated the time this will take and I'm confident I can complete it before the Week 9 deadline.
* **Are there any blockers or dependencies?**  
✅ This issue has no open blockers or dependencies on other unresolved issues.