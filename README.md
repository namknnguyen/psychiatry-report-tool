# PsychReport

One psychiatric evaluation in. The right report out, for each person who needs one.

A psychiatrist documents a session once, in a structured evaluation form. This turns
that record into the several different documents the work actually demands — a plain-language
summary for a family member, an accommodations letter for a school, a letter of medical
necessity for the insurer, a consultation letter for the referring clinician — each written
for its reader and each carrying only what that reader is entitled to see.

Runs entirely on your machine. **Python 3.9+ standard library only — nothing to install.**

```bash
./run.sh
```

Then open <http://127.0.0.1:8765> and click **Take the guided tour** — it signs in as
Dr. Chen and walks through the whole app in 15 steps. Or sign in yourself with
`dr.chen` / `Demo!Pass1`. The **Tour** button at the top right restarts it any time, and
the front desk and auditor accounts get their own shorter tours.

**To publish it as a public demo on Render, follow [DEPLOY.md](DEPLOY.md).**

```
dr.chen      Demo!Pass1   Dr. Amara Chen      clinician
dr.reyes     Demo!Pass2   Dr. Miguel Reyes    supervising psychiatrist
frontdesk    Demo!Pass3   Sam Okonkwo         front desk (demographics only)
compliance   Demo!Pass4   Priya Nair          compliance auditor (audit log only)
```

Four fictional patients are seeded: an adult with two visits for recurrent depression, a
child autism evaluation, an adult ADHD evaluation, and a complex case carrying substance
use content and elevated suicide risk. **No real patient information is included, and none
should be entered — see "Before real use" below.**

```bash
python3 -m tests.test_all      # 96 tests: crypto vectors, access control,
                               # disclosure rules, generation, assistant, HTTP end to end
```

---

## What it does

### 1. Structured intake, built on real instruments

Four forms, 227 fields, following the APA *Practice Guidelines for the Psychiatric Evaluation
of Adults* (3rd ed.) and the documentation payers expect for CPT 90791/90792:

| Form | Contents |
|---|---|
| **Adult Initial Psychiatric Evaluation** (90792) | Chief complaint, HPI, psychiatric review of symptoms, treatment and medication-trial history, substance use, medical history and monitoring labs, family/developmental/social history, cultural formulation, the ten-domain mental status examination, structured risk assessment, quantitative measures, functional assessment, biopsychosocial formulation, DSM-5-TR diagnoses with ICD-10-CM codes, treatment plan, informed consent, capacity |
| **Psychiatric Follow-Up / Progress Note** | Interval history, target-symptom response, adherence and adverse effects, brief MSE, risk, measures, plan changes |
| **Autism Spectrum Diagnostic Evaluation** | Developmental history along ADI-R domains, ADOS-2 module/domain totals/comparison score, ADI-R algorithm scores, SRS-2/SCQ/CARS-2, cognitive, language and adaptive testing, DSM-5-TR criteria A1–A3 and B1–B4 with severity levels, criteria C–E, differential, educational recommendations |
| **ADHD Diagnostic Evaluation** | DSM-5-TR symptom counts, onset before 12, cross-setting evidence, Vanderbilt/Conners/ASRS, cardiac screening before stimulants, diversion risk, monitoring plan |

Several sessions accumulate into one longitudinal record. When a report is built from more
than one visit, current-state items (mental status, risk, medications, diagnoses) take the
most recent entry and narrative accumulates in date order.

### 2. Eight recipient templates

Each template is a disclosure contract as much as a layout: it declares its reader, the lawful
purpose of the disclosure, the sensitivity classes it may ever carry, how much identity to
include, and the reading level.

| Template | Reader | Notable behaviour |
|---|---|---|
| Summary for Family / Caregiver | Support person | 8th-grade language, jargon translated in place, crisis resources attached, needs authorization |
| After-Visit Summary | Patient | Right of access — the patient sees everything except process notes |
| Letter to School Team (IEP / 504) | School | Functional impact and actionable accommodations; risk, substance, trauma withheld |
| Letter of Medical Necessity | Insurer | ICD-10 + CPT, measures with trend, prior treatment failures, explicit necessity statement |
| Consultation Letter | Referring clinician | Full clinical detail, complete MSE, risk assessment |
| Care Coordination Summary | Therapist / care team | Scoped to what a concurrent therapist needs, plus escalation instructions |
| Workplace Accommodation Letter | Employer | Functional limitations only — **no diagnosis**, per ADA practice |
| Disability / Functional Capacity Report | Adjudicator | Organised by the four broad areas of mental functioning |

Selecting several templates at once produces all of those drafts from one chart in a single pass.

### 3. An assistant that stays inside the record

Scoped to one patient. Retrieval is local BM25 with light stemming, so it works with no model
configured at all — answers are then exact quotations with citations. It refuses clinical
directives by design, never sees psychotherapy process notes, attaches the documented risk
stratification to any safety-related question, and says plainly when the record does not
contain an answer instead of filling the gap.

Two one-click checks: **documentation completeness** (which required fields are still empty)
and **verify against chart** (every number, code, dose and date in a report is traceable to
the record — this is what catches an edited draft drifting from the chart).

---

## Not losing work

A clinical note that vanishes is a safety problem, not an inconvenience. Three things guard
against it:

- The evaluation editor **autosaves every 45 seconds** while there are unsaved changes, and the
  header always says whether the note is saved. That request also keeps the session alive while
  the clinician is typing rather than clicking.
- Navigating away with unsaved changes asks — **save, discard, or keep editing** — rather than
  discarding silently. Closing the browser tab prompts too.
- If the session does time out, **what was on screen is held in the window**. The sign-in page
  says so, and signing back in returns the clinician to the same patient, the same tab, and the
  same half-written note.

## Signed documents are immutable

A signed report cannot be edited. Correcting one issues an **amended version** — a new draft
that names the document it supersedes, carries that statement in its footer, and leaves the
original and any disclosure of it untouched in the record. The amendment can either copy the
signed document or be rebuilt from the current chart, picking up anything documented since.

## Safety and compliance

The generated document is a **draft** until a clinician reads it and signs. The draft is
watermarked, signing requires an explicit attestation, and a signed report cannot be edited.

**Nothing is invented.** The base of every report is composed deterministically from the
clinician's own words. If a language model is configured, it may only *rephrase* what was
already composed, and every rewrite passes a fact guard that rejects any introduced number,
dose, date, diagnosis code, or clinical assertion. A rejected rewrite silently falls back to
the clinician's original text and says so on the draft.

| Control | Implementation |
|---|---|
| Encryption at rest | AES-256-GCM per record (`app/crypto.py`, pinned to the FIPS-197 and NIST GCM test vectors). Fresh 96-bit nonce per write; associated data binds each ciphertext to its table and row, so a record cannot be moved between patients. Data key wrapped by PBKDF2-HMAC-SHA256, 600,000 iterations, from `PSYCHREPORT_PASSPHRASE` |
| Minimum necessary | Every field carries a sensitivity class. A template declares what it may carry; anything else is withheld and **itemised on the draft with the reason**, so the clinician sees exactly what was left out |
| 42 CFR Part 2 | Substance use content is withheld unless the patient's authorization specifically names it — including a substance use *diagnosis code* (F10–F19), which is itself Part 2 information. When it is included, the redisclosure notice is attached |
| Psychotherapy notes | Process-note fields are excluded from every generated report and from the assistant's context, with or without an authorization. No override exists |
| Authorizations | Per recipient, with scope, signed and expiry dates, and revocation. Release is blocked without a current one; an emergency release requires a documented reason that is written to the audit trail and the accounting of disclosures |
| Accounting of disclosures | Every release logged with recipient, method, purpose, authorization and content hash — the record a patient is entitled to request |
| Audit trail | Every PHI access, generation, edit, signature and release. Each entry hashes the previous one, so an edit or deletion inside the log is detectable (`/api/audit/verify`) |
| Access control | Four roles. Front desk sees demographics and never clinical content; the compliance auditor sees the log and never a chart. Enforced server-side on every route |
| Sessions | PBKDF2 password hashing, lockout after five failures, 15-minute idle and 12-hour absolute timeouts, session tokens stored only as hashes. The client warns two minutes before an idle logout and preserves unsaved work across it |
| Browser hardening | CSP allowing only this origin, no third-party requests anywhere in the app, `no-store` on all responses, `SameSite=Strict` cookies plus a custom-header CSRF check |
| Network | Binds to 127.0.0.1 and refuses to start on any other interface |
| De-identification | HIPAA Safe Harbor scrubbing, available as a report option and applied automatically to anything sent to a non-local model |
| Risk surfacing | Risk stratification is escalated by rule when ideation with intent, plan or an identified target is documented; moderate-or-higher risk without a safety plan, without means counselling, or an identified potential victim without a duty-to-warn analysis, are flagged on the chart and on the draft |

### Optional language model

Off by default; everything works without it. To enable a **local** model (nothing leaves the machine):

```bash
PSYCHREPORT_LLM_PROVIDER=ollama \
PSYCHREPORT_LLM_BASE_URL=http://localhost:11434/v1 \
PSYCHREPORT_LLM_MODEL=llama3.1:8b ./run.sh
```

Any OpenAI-compatible endpoint works (`PSYCHREPORT_LLM_PROVIDER=openai`, plus
`PSYCHREPORT_LLM_API_KEY`). A **non-local** endpoint is refused unless
`PSYCHREPORT_ALLOW_REMOTE_PHI=1` is set deliberately, and content is Safe Harbor
de-identified before it is sent. The compliance panel states which of these is in force.

**Or let each person bring their own key.** The **AI model** button in the top bar accepts an
OpenRouter key (or any OpenAI-compatible endpoint) for *that sign-in only*. The key is tested
before it is accepted, kept in memory, never written to the database or the audit log, never
returned by any endpoint, and dropped at sign-out or restart. This is what makes a shared demo
workable: a single service-wide key would be spent by every visitor, whereas each person's
requests are billed to their own key. Set a spending limit on the key first.

Both paths scrub identifiers before anything leaves the process. The assistant sends
de-identified excerpts. The language pass can't simply drop names — a letter needs them back —
so identifiers travel as numbered markers the model is told to reproduce, and are restored on
return; if the markers don't come back intact the rewrite is rejected and the clinician's text
is kept.

---

## Before real use

This is a demonstration and is **not ready for protected health information.** What it does
not have, and would need:

- A signed Business Associate Agreement with any model provider, and a HIPAA Security Rule
  risk analysis of the deployment.
- A hosting arrangement fit for PHI. `--hosted` mode (used for Render) is built for a public
  demonstration with fictional data: TLS at the provider's proxy, Secure cookies and HSTS, but
  shared demo accounts and a database erased on every restart.
- Key management beyond a passphrase in an environment variable — an HSM or KMS, key rotation,
  and a re-encryption path.
- Encrypted, tested backups, and a documented retention and destruction schedule.
- Multi-factor authentication, and state-law review: several states impose stricter rules
  than HIPAA on mental health records, minors' consent, and HIV status.
- Clinical validation. The templates follow published standards, but no generated document
  should leave a practice without a clinician reading every line — which is why nothing here
  releases without a signature.

Set `PSYCHREPORT_PASSPHRASE` before entering anything real; the built-in demonstration
passphrase is a compliance warning in the UI for a reason.

---

## Layout

```
app/crypto.py       AES-256-GCM, PBKDF2, audit hash chain (stdlib only)
app/db.py           SQLite with record-level sealed payloads
app/auth.py         roles, sessions, lockout, timeouts
app/audit.py        tamper-evident audit trail
app/forms.py        the four clinical instruments, with sensitivity tags
app/templates.py    the eight recipient templates and the plain-language glossary
app/redaction.py    minimum-necessary filter, Safe Harbor, risk detection
app/generator.py    deterministic report composition with provenance
app/llm.py          optional model client, egress controls, fact guard
app/assistant.py    retrieval, citations, guardrails, consistency checks
app/api.py          HTTP API
app/server.py       routing, static files, security headers
web/                single-page client, no frameworks, no external requests
app/config.py       local vs hosted (Render) deployment mode
tests/test_all.py   96 tests
render.yaml         Render Blueprint
DEPLOY.md           step-by-step Render deployment
```

## Sources

Clinical structure follows the
[APA Practice Guidelines for the Psychiatric Evaluation of Adults, 3rd ed.](https://psychiatryonline.org/doi/book/10.1176/appi.books.9780890426760),
the [mental status examination](https://www.ncbi.nlm.nih.gov/books/NBK546682/),
[CMS billing and documentation guidance for psychiatric diagnostic evaluation](https://www.cms.gov/medicare-coverage-database/view/article.aspx?articleId=57520&ver=43),
DSM-5-TR criteria for autism spectrum disorder and ADHD with
[ADOS-2/ADI-R](https://www.autism.org.uk/advice-and-guidance/diagnosis/assessment-and-diagnosis/criteria-and-tools-used-in-an-autism-assessment)
practice, and for the privacy controls the
[HIPAA Privacy Rule guidance on mental health information](https://www.hhs.gov/sites/default/files/hipaa-privacy-rule-and-sharing-info-related-to-mental-health.pdf)
and the [42 CFR Part 2 final rule](https://www.hhs.gov/hipaa/for-professionals/regulatory-initiatives/fact-sheet-42-cfr-part-2-final-rule/index.html).
