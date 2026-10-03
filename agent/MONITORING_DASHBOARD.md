# Engineering Agent Monitoring Dashboard

> **Last Updated:** [DATE]  
> **Check Frequency:** Daily  
> **Dashboard Version:** 1.0

---

## 🔴 Quick Status

| Metric | Status | Expected | ⚠️ Alert |
|--------|--------|----------|---------|
| Agent Status | ? | BOOTSTRAP | |
| Phase | ? | 3 | |
| Gate | ? | G8 | |
| Live Trading | ? | BLOCKED | |
| Auto Merge | ? | BLOCKED | |
| Last CI Result | ? | success | |

---

## 📋 Daily Checklist

### 1. State File Check
**File:** `agent/STATE.md`

- [ ] File exists and readable
- [ ] Status is: `BOOTSTRAP` or `ACTIVE`
- [ ] Phase is: `3`
- [ ] Gate is: `G8` or higher
- [ ] PR is: valid number (e.g., #2)
- [ ] last_ci_conclusion: `success`
- [ ] live_trading_allowed: `false` ✅
- [ ] auto_merge_allowed: `false` ✅

**Notes:**
```
[Add observations here]
```

---

### 2. Report File Check
**File:** `agent/REPORT.md`

- [ ] File exists and readable
- [ ] Agent: `OKX Engineering Agent V1`
- [ ] Phase: `3`
- [ ] Gate: `G8` or higher
- [ ] PR: matches STATE.md
- [ ] Last verified CI: `SUCCESS`
- [ ] Live trading: `BLOCKED` ✅
- [ ] Auto merge: `BLOCKED` ✅
- [ ] Test count: >= 69 tests

**Notes:**
```
[Add observations here]
```

---

### 3. PR Status Check
**Repository:** `solgea/okx_grid_bot`  
**Expected PR:** #2 or latest

- [ ] PR exists and accessible
- [ ] PR is `OPEN` (not merged)
- [ ] Branch name matches STATE.md
- [ ] Latest commit: < 24 hours old
- [ ] Commit message relevant to G8
- [ ] No draft/WIP status
- [ ] Labels/metadata correct

**PR Branch:** `_________________`  
**Latest Commit SHA:** `_________________`  
**Latest Commit Date:** `_________________`

**Notes:**
```
[Add observations here]
```

---

### 4. GitHub Actions / CI Check
**Workflow Path:** `.github/workflows/`

- [ ] Workflow file exists
- [ ] Last run ID: `_________________`
- [ ] Last run status: `✅ success` or `❌ failure`
- [ ] Test results:
  - Total tests: `_________`
  - Passed: `_________`
  - Failed: `_________`
- [ ] All jobs completed
- [ ] Duration reasonable (< 30 min)
- [ ] No infrastructure errors

**Latest CI Run Link:**
```
[Add link to latest CI run]
```

**Failed Tests (if any):**
```
[List any failures]
```

**Notes:**
```
[Add observations here]
```

---

### 5. Gate Progress Check
**File:** `agent/GATE_PLAN.md`

**Current Gate:** `G8 — Execution Preflight`

Verify all G8 controls implemented:
- [ ] G8.1 — instrument metadata ✅
- [ ] G8.2 — price/quantity validity ✅
- [ ] G8.3 — leverage/margin ✅
- [ ] G8.4 — market availability ✅
- [ ] G8.5 — kill switch/trading halt ✅
- [ ] G8.6 — PreFlight check enforcement ✅

**Next Gates (planned):**
- [ ] G9 — Demo Order Placement
- [ ] G10 — Order Lifecycle
- [ ] G11 — OrderSync Live-Demo
- [ ] G12 — Position Integrity
- [ ] G13 — Risk/Kill Switch
- [ ] G14 — Restart Recovery
- [ ] G15 — Failure Injection
- [ ] G16 — Demo Soak
- [ ] G17 — Phase 3 Freeze

**Gate Status:** `_________________`

**Notes:**
```
[Add observations here]
```

---

### 6. Safety Guard Verification
**Critical Controls** — must all be ✅

- [ ] No live exchange orders placed
- [ ] No live trading credentials used
- [ ] Auto merge is BLOCKED
- [ ] No policy bypass detected
- [ ] No unauthorized gate modification
- [ ] No batch fixes (single-blocker rule enforced)
- [ ] Changes are minimal/focused
- [ ] Test evidence exists
- [ ] CI passed before any action
- [ ] Human approval requirement documented

**Security Notes:**
```
[Add any security observations]
```

---

### 7. Evidence Quality Check

**Latest Change Evidence:**

- [ ] Regression test created/updated
- [ ] Test command documented
- [ ] Test result: `PASS` or `FAIL`
- [ ] Commit SHA: `_________________`
- [ ] Commit message precise
- [ ] CI run linked
- [ ] CI status: `success`
- [ ] Remaining risk statement exists
- [ ] Human action requirement noted
- [ ] REPORT.md updated

**Latest Test Command:**
```bash
[Command to run tests]
```

**Test Result:**
```
[Test output summary]
```

**Remaining Risk:**
```
[Risk assessment from agent]
```

---

## 🚨 Alert Conditions

**RED FLAGS — Investigate Immediately:**

| Condition | Action |
|-----------|--------|
| live_trading_allowed: `true` | ⛔ STOP — Review policy |
| auto_merge_allowed: `true` | ⛔ STOP — Review policy |
| last_ci_conclusion: `failure` | ⚠️ Check CI logs for blocker |
| status: `BLOCKED` | ⚠️ Check last_blocker field |
| No CI run in 6+ hours | ⚠️ Check GitHub Actions status |
| PR merged unexpectedly | ⛔ STOP — Audit merge event |
| Gate frozen without evidence | ⛔ STOP — Check gate plan |
| Live order detected | ⛔ STOP — Security incident |

---

## 📊 Health Metrics

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Agent uptime | 24/7 | ? | ? |
| CI success rate | 95%+ | ? | ? |
| Test pass rate | 100% | ? | ? |
| Time since last activity | < 24h | ? | ? |
| PR open duration | < 7 days | ? | ? |
| Safety violations | 0 | ? | ? |

---

## 📝 Weekly Summary

**Week:** `_________________`

### Completed Tasks
```
- [Task 1]
- [Task 2]
- [Task 3]
```

### Blockers Encountered
```
- [Blocker 1]
- [Blocker 2]
```

### Safety Incidents
```
[None expected - list if any]
```

### Next Week Focus
```
- [Focus area 1]
- [Focus area 2]
```

---

## 🔗 Quick Links

| Resource | Link |
|----------|------|
| STATE.md | `agent/STATE.md` |
| REPORT.md | `agent/REPORT.md` |
| GATE_PLAN.md | `agent/GATE_PLAN.md` |
| Engineering Agent | `agent/G8_ENGINEERING_AGENT.md` |
| AGENTS.md | `AGENTS.md` |
| PR #2 | `https://github.com/solgea/okx_grid_bot/pull/2` |
| GitHub Actions | `https://github.com/solgea/okx_grid_bot/actions` |
| Latest CI Run | [ADD LINK] |

---

## 📞 Escalation Checklist

**If any RED FLAG detected:**

1. [ ] Take screenshot of STATE.md
2. [ ] Note exact time and condition
3. [ ] Check CI logs for root cause
4. [ ] Review last 3 commits
5. [ ] Verify safety guards still enabled
6. [ ] Document findings in "Incident Log" below
7. [ ] Report to team lead

---

## 📋 Incident Log

**Format:** `[DATE] [TIME] [SEVERITY] [CONDITION] [ACTION]`

```
[Add incidents here as they occur]
```

---

## ✅ Sign-Off

| Role | Name | Date | Status |
|------|------|------|--------|
| Monitor | ? | ? | ✅ Reviewed |
| Lead | ? | ? | ✅ Approved |

---

**Footer:**  
This dashboard is automatically monitored. For live updates, check:
- `agent/STATE.md` (machine state)
- `agent/REPORT.md` (human report)
- GitHub Actions (execution evidence)
