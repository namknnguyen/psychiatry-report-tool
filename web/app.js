/* PsychReport - single-page client. No frameworks, no external requests. */
'use strict';

const S = {
  me: null, boot: null, patients: [], tags: [], filter: {q: '', tag: ''},
  patient: null, tab: 'overview', editor: null, gen: null, report: null,
  chat: [], audit: null, compliance: null, view: 'home', busy: false,
  lastRequestAt: Date.now(), idleWarned: false, resume: null,
};

const AUTOSAVE_MS = 45000;
const DEMO_BANNER = 'Public demonstration — every patient is fictional. Do not enter real patient information. '
  + 'Data is erased whenever the service restarts.';
const IDLE_WARN_MS = 13 * 60 * 1000;

const $ = (sel, root) => (root || document).querySelector(sel);
const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g,
  (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const nl2br = (v) => esc(v).replace(/\n/g, '<br>');
const fmtTime = (ts) => new Date(ts * 1000).toLocaleString();

async function api(path, opts = {}) {
  const init = {method: opts.method || 'GET', headers: {'X-PsychReport': '1'}, credentials: 'same-origin'};
  if (opts.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(opts.body);
  }
  S.lastRequestAt = Date.now();
  S.idleWarned = false;
  const res = await fetch(path, init);
  const text = await res.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch (e) { data = {error: 'Unexpected server response.'}; }
  if (!res.ok) {
    const err = new Error(data.error || ('Request failed (' + res.status + ')'));
    err.status = res.status; err.payload = data;
    throw err;
  }
  return data;
}

let toastTimer = null;
function toast(message, isError) {
  const existing = $('#toast');
  if (existing) existing.remove();
  const node = document.createElement('div');
  node.id = 'toast';
  node.className = 'toast' + (isError ? ' err' : '');
  node.textContent = message;
  document.body.appendChild(node);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.remove(), isError ? 7000 : 3500);
}

function fail(err) {
  if (err && err.status === 401) {
    // Hold everything the clinician had open -- especially an unsaved note --
    // so signing back in returns them to it rather than to an empty screen.
    S.resume = {
      patientId: S.patient ? S.patient.patient.id : null,
      tab: S.tab, editor: S.editor, reportId: S.report ? S.report.id : null,
      message: err.message,
    };
    S.me = null;
    render();
  }
  toast((err && err.message) || 'Something went wrong.', true);
}


/* ------------------------------------------------------------------ modal */
/* Native prompt()/confirm() cannot show warnings, validate, or hold more than
   one value, and they block the page. Every decision that carries clinical or
   legal weight — signing, releasing, revoking — goes through this instead. */

function showModal(spec) {
  return new Promise((resolve) => {
    const wrap = document.createElement('div');
    wrap.className = 'modal-back';
    const fields = (spec.fields || []).map((f) => {
      const value = f.value == null ? '' : f.value;
      let input;
      if (f.type === 'textarea') input = `<textarea data-m="${f.id}">${esc(value)}</textarea>`;
      else if (f.type === 'checkbox') input = `<label class="checkline"><input type="checkbox" data-m="${f.id}" ${f.value ? 'checked' : ''}><span>${esc(f.label)}</span></label>`;
      else if (f.type === 'select') input = `<select data-m="${f.id}">${(f.options || []).map((o) =>
        `<option ${o === value ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`;
      else input = `<input type="${f.type || 'text'}" data-m="${f.id}" value="${esc(value)}" placeholder="${esc(f.placeholder || '')}">`;
      if (f.type === 'checkbox') return `<div class="field">${input}</div>`;
      return `<div class="field"><label>${esc(f.label)}${f.required ? ' <span class="badge warn">required</span>' : ''}
        ${f.hint ? `<span class="hint">${esc(f.hint)}</span>` : ''}</label>${input}</div>`;
    }).join('');
    wrap.innerHTML = `<div class="modal" role="dialog" aria-modal="true">
      <h3>${esc(spec.title)}</h3>
      ${(spec.notices || []).map((n) => `<div class="notice ${esc(n.kind || 'warn')}">${esc(n.text)}</div>`).join('')}
      ${spec.intro ? `<p class="small muted">${esc(spec.intro)}</p>` : ''}
      ${fields}
      <div class="modal-err small hidden"></div>
      <div class="modal-actions">
        <button class="btn ghost" data-m-act="cancel">${esc(spec.cancelLabel || 'Cancel')}</button>
        ${(spec.actions || []).map((x) => `<button class="btn ${esc(x.cls || 'ghost')}"
          data-m-act="action" data-m-id="${esc(x.id)}">${esc(x.label)}</button>`).join('')}
        ${spec.actions ? '' : `<button class="btn ${spec.danger ? 'danger' : ''}" data-m-act="ok">${esc(spec.submitLabel || 'Confirm')}</button>`}
      </div></div>`;
    document.body.appendChild(wrap);
    const first = wrap.querySelector('input,textarea,select');
    if (first) first.focus();

    const close = (result) => { wrap.remove(); document.removeEventListener('keydown', onKey); resolve(result); };
    const submit = (action) => {
      const out = action ? {action: action} : {};
      for (const f of (spec.fields || [])) {
        const el = wrap.querySelector(`[data-m="${f.id}"]`);
        out[f.id] = f.type === 'checkbox' ? el.checked : el.value.trim();
        if (f.required && !out[f.id]) {
          const box = wrap.querySelector('.modal-err');
          box.textContent = (f.type === 'checkbox'
            ? 'Tick the box above to continue.' : f.label + ' is required.');
          box.classList.remove('hidden');
          return;
        }
      }
      close(out);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') close(null);
      if (e.key === 'Enter' && e.target.tagName !== 'TEXTAREA' && !spec.actions) {
        e.preventDefault(); submit();
      }
    };
    document.addEventListener('keydown', onKey);
    wrap.addEventListener('click', (e) => {
      if (e.target === wrap) return close(null);
      const act = e.target.closest('[data-m-act]');
      if (!act) return;
      e.stopPropagation();
      if (act.dataset.mAct === 'cancel') close(null);
      else if (act.dataset.mAct === 'action') submit(act.dataset.mId);
      else submit();
    });
  });
}

const DEMOGRAPHIC_FIELDS = [
  {id: 'first_name', label: 'First name'},
  {id: 'last_name', label: 'Last name', required: true},
  {id: 'preferred_name', label: 'Preferred name'},
  {id: 'dob', label: 'Date of birth', type: 'date'},
  {id: 'pronouns', label: 'Pronouns'},
  {id: 'preferred_language', label: 'Preferred language'},
  {id: 'phone', label: 'Phone'},
  {id: 'email', label: 'Email'},
  {id: 'address', label: 'Address'},
];

/* ------------------------------------------------------------------ login */

function loginView() {
  const rows = [
    ['dr.chen', 'Demo!Pass1', 'Dr. Amara Chen — clinician'],
    ['dr.reyes', 'Demo!Pass2', 'Dr. Miguel Reyes — supervisor'],
    ['frontdesk', 'Demo!Pass3', 'Sam Okonkwo — front desk'],
    ['compliance', 'Demo!Pass4', 'Priya Nair — auditor'],
  ];
  const held = S.resume && S.resume.editor
    ? '<div class="notice warn">' + esc(S.resume.message || 'Your session ended.')
      + ' The evaluation you were writing is still open in this window — sign in to return to it.</div>'
    : (S.resume ? '<div class="notice warn">' + esc(S.resume.message || 'Your session ended.') + '</div>' : '');
  return `<div class="login-wrap"><form class="login" id="loginForm">
    <h1>PsychReport</h1>
    <div class="sub">One evaluation in. The right report out, for each person who needs one.</div>
    ${S.hosted ? `<div class="demo-banner">${DEMO_BANNER}</div>` : ''}
    ${held}
    <div class="field"><label for="u">Username</label><input id="u" type="text" autocomplete="username" autofocus></div>
    <div class="field"><label for="p">Password</label><input id="p" type="password" autocomplete="current-password"></div>
    <button class="btn w100"  type="submit">Sign in</button>
    <button class="btn ghost w100 mt2" type="button" data-a="tour-login">Take the guided tour</button>
    <p class="small muted mt1">Signs in as Dr. Amara Chen and walks through the app step by step.</p>
    <div class="demo-users"><strong>Demonstration accounts</strong><table>
      ${rows.map(([u, p, d]) => `<tr><td><button type="button" data-a="fill" data-u="${u}" data-p="${p}">${u}</button></td>
        <td class="mono">${p}</td><td>${esc(d)}</td></tr>`).join('')}
    </table>
    <p class="mt2">${S.hosted
      ? 'All data is fictional. This public demo is erased whenever the service restarts.'
      : 'All data is fictional and stored encrypted on this machine only.'}</p></div>
  </form></div>`;
}

/* ------------------------------------------------------------------ shell */

function sidebar() {
  const chartAccess = S.me.permissions.some((p) => p.indexOf('patient.read') === 0);
  if (!chartAccess) {
    return `<aside class="sidebar">
      <div class="brand"><div class="name">PsychReport</div><div class="tag">${esc(S.boot ? S.boot.practice.name : '')}</div></div>
      <div class="side-foot plainbox" >
        <p>Signed in as <strong>${esc(S.me.role_label)}</strong>.</p>
        <p>This role has access to the audit trail and the compliance panel. Patient records are not accessible from it.</p>
      </div></aside>`;
  }
  const items = S.patients.map((p) => `
    <div class="pitem ${S.patient && S.patient.patient.id === p.id ? 'on' : ''}" data-a="open-patient" data-id="${p.id}">
      <div class="nm">${esc(p.name)}</div>
      <div class="mt"><span>${esc(p.mrn)}</span>${p.age != null ? `<span>${p.age}y</span>` : ''}
        ${p.risk_level && p.risk_level !== 'Not documented' ? `<span>Risk: ${esc(p.risk_level)}</span>` : ''}
        <span>${p.evaluation_count} eval · ${p.report_count} rep</span></div>
    </div>`).join('') || '<div class="side-foot noborder" >No patients match.</div>';
  const tags = S.tags.map((t) => `<button data-a="tag" data-t="${esc(t)}" class="${S.filter.tag === t ? 'on' : ''}">${esc(t)}</button>`).join('');
  return `<aside class="sidebar">
    <div class="brand"><div class="name">PsychReport</div><div class="tag">${esc(S.boot ? S.boot.practice.name : '')}</div></div>
    <div class="side-search"><input id="psearch" type="text" placeholder="Search name, MRN, tag" value="${esc(S.filter.q)}"></div>
    <div class="tagbar">${tags}${S.filter.tag ? '<button data-a="tag" data-t="">clear</button>' : ''}</div>
    <div class="plist" data-tour="patients">${items}</div>
    <div class="side-foot">
      ${S.me.permissions.indexOf('patient.write') >= 0 || S.me.permissions.indexOf('patient.write.demographics') >= 0
        ? '<button data-a="new-patient">+ New patient</button>' : ''}
      ${S.me.permissions.some((p) => p.indexOf('audit.read') === 0)
        ? '<button data-a="view-compliance">Compliance &amp; audit</button>' : ''}
    </div></aside>`;
}

function topbar() {
  const u = S.me.user;
  const perms = S.me.permissions;
  // The sidebar is hidden on narrow screens, so its navigation is repeated here.
  const phoneNav = (perms.some((p) => p.indexOf('patient.read') === 0)
      ? '<button class="btn ghost sm mobile-only" data-a="go-home">Patients</button>' : '')
    + (perms.some((p) => p.indexOf('audit.read') === 0)
      ? '<button class="btn ghost sm mobile-only" data-a="view-compliance">Audit</button>' : '');
  return `<div class="topbar">
    ${phoneNav}
    <strong>${S.patient ? esc(S.patient.patient.name) : 'Overview'}</strong>
    ${S.patient ? `<span class="badge grey">${esc(S.patient.patient.mrn)}</span>` : ''}
    ${S.patient && S.patient.risk && S.patient.risk.level !== 'Not documented' ? riskBadge(S.patient.risk.level) : ''}
    <div class="who">${esc(u.display_name)}${u.credentials ? ', ' + esc(u.credentials) : ''}
      · ${esc(S.me.role_label)}<br>
      ${perms.indexOf('assistant.use') >= 0 || perms.indexOf('report.generate') >= 0
        ? `<button class="btn ghost sm mt1" data-a="llm-settings">AI model${
            S.boot && S.boot.llm && S.boot.llm.user_supplied ? ' ✓' : ''}</button>` : ''}
      <button class="btn ghost sm mt1" data-a="start-tour" data-tour="tour-button">Tour</button>
      <button class="btn ghost sm mt1" data-a="logout" >Sign out</button></div>
  </div>`;
}

function riskBadge(level) {
  const cls = {Low: 'ok', Moderate: 'warn', High: 'danger', Imminent: 'danger'}[level] || 'grey';
  return `<span class="badge ${cls}">Risk: ${esc(level)}</span>`;
}

/* ------------------------------------------------------------------- home */

function homeView() {
  const c = S.compliance;
  const cards = S.patients.map((p) => `<div class="card clickable"  data-a="open-patient" data-id="${p.id}">
      <div class="hstack gap2">
        <h3 class="m0">${esc(p.name)}</h3><span class="badge grey">${esc(p.mrn)}</span>
        ${p.risk_level && p.risk_level !== 'Not documented' ? riskBadge(p.risk_level) : ''}</div>
      <div class="small muted my1" >${p.age != null ? p.age + ' years' : ''}
        ${p.last_encounter ? ' · last visit ' + esc(p.last_encounter) : ''}
        · ${p.evaluation_count} evaluation(s) · ${p.report_count} report(s)</div>
      ${(p.diagnoses || []).map((d) => `<span class="badge">${esc(d.code)} ${esc(d.description)}</span> `).join('')}
      <div class="mt1">${(p.tags || []).map((t) => `<span class="badge grey">${esc(t)}</span> `).join('')}</div>
      ${(p.risk_gaps || []).length ? `<div class="notice warn small mt2" >${esc(p.risk_gaps[0])}</div>` : ''}
    </div>`).join('');
  return `<div class="content">
    ${S.me.user.role === 'auditor' ? '' : `<h1>Patients</h1><p class="muted">Grouped by tag; search from the sidebar.</p><div data-tour="patient-cards">${cards || '<div class="card">No patients yet.</div>'}</div>`}
    ${c ? complianceCard(c) : ''}
  </div>`;
}

function complianceCard(c) {
  return `<div class="card" data-tour="controls"><h3>Safety &amp; compliance controls</h3>
    <table class="data"><tbody>${c.controls.map((x) => `<tr>
      <td class="w180"><strong>${esc(x.name)}</strong></td>
      <td class="w70"><span class="badge ${x.status === 'on' ? 'ok' : (x.status === 'warn' ? 'warn' : 'danger')}">${x.status === 'on' ? 'active' : x.status}</span></td>
      <td class="small">${esc(x.detail)}</td></tr>`).join('')}</tbody></table></div>`;
}

/* ---------------------------------------------------------------- patient */

function patientView() {
  const d = S.patient;
  const restricted = d.clinical_restricted;
  const tabs = restricted
    ? [['overview', 'Demographics'], ['authorizations', 'Authorizations']]
    : [['overview', 'Overview'], ['evaluations', 'Evaluations'], ['generate', 'Generate reports'],
       ['reports', 'Reports (' + d.reports.length + ')'], ['assistant', 'AI assistant'],
       ['authorizations', 'Authorizations & disclosures']];
  let body = '';
  if (S.tab === 'overview') body = overviewTab(d);
  else if (S.tab === 'evaluations') body = S.editor ? editorTab() : evaluationsTab(d);
  else if (S.tab === 'generate') body = generateTab(d);
  else if (S.tab === 'reports') body = S.report ? reportView() : reportsTab(d);
  else if (S.tab === 'assistant') body = assistantTab();
  else if (S.tab === 'authorizations') body = authTab(d);
  return `<div class="content">
    <div class="tabs" data-tour="patient-tabs">${tabs.map(([k, l]) => `<button data-a="tab" data-t="${k}" class="${S.tab === k ? 'on' : ''}">${esc(l)}</button>`).join('')}</div>
    ${body}</div>`;
}

function overviewTab(d) {
  const dem = d.patient.demographics || {};
  const kv = (label, value) => value ? `<tr><th>${esc(label)}</th><td>${esc(value)}</td></tr>` : '';
  const ins = dem.insurance || {}; const em = dem.emergency_contact || {}; const g = dem.guardian || {};
  const risk = d.risk;
  return `<div class="grid2">
    <div class="card" data-tour="demographics"><h3>Patient</h3>
      <table class="data"><tbody>
        ${kv('Name', d.patient.name)}${kv('MRN', d.patient.mrn)}
        ${kv('Date of birth', dem.dob + (d.patient.age != null ? ' (age ' + d.patient.age + ')' : ''))}
        ${kv('Pronouns', dem.pronouns)}${kv('Preferred language', dem.preferred_language)}
        ${kv('Phone', dem.phone)}${kv('Email', dem.email)}${kv('Address', dem.address)}
        ${kv('Guardian', g.name ? g.name + ' — ' + (g.phone || '') : '')}
        ${kv('Emergency contact', em.name ? em.name + ' — ' + (em.phone || '') : '')}
        ${kv('Insurance', ins.carrier ? ins.carrier + ' · ' + (ins.member_id || '') : '')}
        ${kv('School', dem.school)}${kv('Employer', dem.employer)}${kv('PCP', dem.pcp)}
      </tbody></table>
      <div class="mt2">${(d.patient.tags || []).map((t) => `<span class="badge grey">${esc(t)}</span> `).join('')}</div>
      <button class="btn ghost sm mt2" data-a="edit-demographics" >Edit details</button>
    </div>
    <div>
      ${risk && risk.level !== 'Not documented' ? `<div class="card" data-tour="risk"><h3>Risk</h3>
        <p>${riskBadge(risk.level)} ${risk.date ? '<span class="small muted">documented ' + esc(risk.date) + '</span>' : ''}</p>
        ${risk.escalated ? '<div class="notice warn small">Stratification escalated by rule: documented ideation with intent, plan or an identified target.</div>' : ''}
        ${risk.rationale ? `<p class="small">${nl2br(risk.rationale)}</p>` : ''}
        ${(risk.flags || []).map((f) => `<div class="small">• ${esc(f)}</div>`).join('')}
        ${(risk.gaps || []).map((f) => `<div class="notice danger small mt2" >${esc(f)}</div>`).join('')}
        ${risk.safety_plan ? `<h4 class="mt3">Safety plan on file</h4><p class="small">${nl2br(risk.safety_plan)}</p>` : ''}
      </div>` : ''}
      ${risk && risk.level === 'Not documented' ? `<div class="card" data-tour="risk"><h3>Risk</h3>
        <p class="small muted">No suicide-risk stratification is recorded. The instruments used for
        this patient do not include a risk section; add a psychiatric evaluation or follow-up note
        to document one.</p></div>` : ''}
      ${d.completeness ? `<div class="card"><h3>Documentation completeness</h3>
        <p class="small ${d.completeness.findings.length ? '' : 'muted'}">${esc(d.completeness.summary)}</p>
        ${d.completeness.findings.map((f) => `<div class="notice warn small"><strong>${esc(f.form)} (${esc(f.date)})</strong><br>Missing: ${esc(f.missing.join(', '))}</div>`).join('')}
      </div>` : ''}
      ${S.me.permissions.indexOf('report.generate') < 0 ? '' : `<div class="card"><h3>Quick actions</h3>
        <button class="btn sm" data-a="tab" data-t="generate">Generate reports</button>
        <button class="btn ghost sm" data-a="new-eval">Add evaluation</button>
        <button class="btn ghost sm" data-a="tab" data-t="assistant">Ask the assistant</button>
      </div>`}
    </div></div>`;
}

/* ------------------------------------------------------------ evaluations */

function evaluationsTab(d) {
  const rows = d.evaluations.map((e) => `<tr>
      <td><strong>${esc(e.form_name)}</strong><div class="small muted">${e.status === 'signed' ? 'Signed' : 'Draft'}</div></td>
      <td>${esc(e.encounter_date)}</td>
      <td>${Object.keys(e.answers).length} fields</td>
      <td class="ta-right">
        <button class="btn ghost sm" data-a="open-eval" data-id="${e.id}">${e.status === 'signed' ? 'View' : 'Edit'}</button>
        ${e.status !== 'signed' ? `<button class="btn sm" data-a="sign-eval" data-id="${e.id}">Sign</button>` : ''}
      </td></tr>`).join('');
  const forms = (S.boot.forms || []).map((f) => `<option value="${f.id}">${esc(f.name)} (CPT ${esc(f.cpt)})</option>`).join('');
  return `<div class="card" data-tour="evaluations"><h3>Evaluations</h3>
      <p class="muted small">Sessions accumulate: reports can be built from one visit or from several.</p>
      <table class="data"><thead><tr><th>Instrument</th><th>Date of service</th><th>Completed</th><th></th></tr></thead>
      <tbody>${rows || '<tr><td colspan="4" class="muted">No evaluations recorded.</td></tr>'}</tbody></table></div>
    <div class="card"><h3>New evaluation</h3>
      <div class="row"><div class="field"><label for="newform">Instrument</label><select id="newform">${forms}</select></div>
        <div class="field"><label for="newdate">Date of service</label><input id="newdate" type="date" value="${new Date().toISOString().slice(0, 10)}"></div>
        <div class="noflex self-end"><button class="btn" data-a="create-eval">Start</button></div></div></div>`;
}

function editorTab() {
  const ed = S.editor;
  const form = S.boot.forms.find((f) => f.id === ed.form_id);
  const sens = S.boot.sensitivity_labels;
  const sections = form.sections.map((sec, i) => {
    const open = ed.open[sec.id] !== false;
    const fields = sec.fields.map((f) => {
      const val = ed.answers[f.id] || '';
      const tagCls = f.sens === 'process_note' ? 'never' : (S.boot.protected_classes.indexOf(f.sens) >= 0 ? 'prot' : '');
      const tag = f.sens !== 'general' ? `<span class="sens-tag ${tagCls}">${esc(sens[f.sens] || f.sens)}</span>` : '';
      const hint = f.help ? `<span class="hint">${esc(f.help)}</span>` : '';
      let input;
      if (f.type === 'select') {
        input = `<select data-field="${f.id}"><option value=""></option>${(f.options || []).map((o) =>
          `<option ${o === val ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`;
      } else if (f.type === 'multiselect') {
        const chosen = String(val).split(', ').filter(Boolean);
        input = (f.options || []).map((o) => `<label class="checkline fw-normal" >
          <input type="checkbox" data-multi="${f.id}" value="${esc(o)}" ${chosen.indexOf(o) >= 0 ? 'checked' : ''}> ${esc(o)}</label>`).join('');
      } else if (f.type === 'textarea') {
        input = `<textarea data-field="${f.id}" ${f.id === 'hpi' || f.id === 'formulation' ? 'class="tall"' : ''}>${esc(val)}</textarea>`;
      } else {
        input = `<input type="${f.type === 'number' ? 'number' : (f.type === 'date' ? 'date' : 'text')}" data-field="${f.id}" value="${esc(val)}">`;
      }
      return `<div class="field"><label>${esc(f.label)} ${f.req ? '<span class="badge warn">required</span>' : ''} ${tag}${hint}</label>${input}</div>`;
    }).join('');
    return `<div class="section-block">
      <div class="section-head" data-a="toggle-section" data-s="${sec.id}">
        <span class="chev">${open ? '&minus;' : '+'}</span> ${esc(sec.title)}
        <span class="small muted push" >${sec.fields.length} fields</span></div>
      ${open ? `<div class="section-body">${sec.help ? `<p class="small muted">${esc(sec.help)}</p>` : ''}${fields}</div>` : ''}
    </div>`;
  }).join('');
  return `<div class="card"><div class="hstack">
      <h3 class="m0">${esc(form.name)}</h3>
      <span class="badge grey">CPT ${esc(form.cpt)}</span>
      ${ed.locked ? '<span class="badge ok">Signed — read only</span>' : '<span class="badge warn">Draft</span>'}
      ${ed.locked ? '' : `<span id="saveState" class="small muted">${ed.dirty ? 'Unsaved changes'
        : (ed.savedAt ? 'Saved ' + esc(ed.savedAt) : (ed.eval_id ? 'No changes yet' : 'Not saved yet'))}</span>`}
      <div class="push">
        <button class="btn ghost sm" data-a="close-editor">Back</button>
        ${ed.locked ? '' : `<button class="btn sm" data-a="save-eval">Save</button>
          <button class="btn sm" data-a="save-sign-eval">Save &amp; sign</button>`}
      </div></div>
      <p class="small muted">${esc(form.description)}</p></div>
    <fieldset class="bare" ${ed.locked ? 'disabled' : ''}>${sections}</fieldset>`;
}

/* --------------------------------------------------------------- generate */

function generateTab(d) {
  if (!S.gen) {
    S.gen = {evals: d.evaluations.map((e) => e.id), templates: [], polish: false, deid: false, preview: null};
  }
  const evalRows = d.evaluations.map((e) => `<label class="checkline">
      <input type="checkbox" data-gen-eval="${e.id}" ${S.gen.evals.indexOf(e.id) >= 0 ? 'checked' : ''}>
      <span><strong>${esc(e.form_name)}</strong> — ${esc(e.encounter_date)}
        <span class="badge ${e.status === 'signed' ? 'ok' : 'warn'}">${e.status}</span></span></label>`).join('');
  const authTypes = (d.authorizations || []).filter((a) => a.valid).map((a) => a.recipient_type);
  const cards = S.boot.templates.map((t) => {
    const on = S.gen.templates.indexOf(t.id) >= 0;
    const hasAuth = authTypes.indexOf(t.recipient_type) >= 0;
    return `<div class="tmpl-card ${on ? 'on' : ''}" data-a="toggle-template" data-t="${t.id}">
      <div class="tn">${esc(t.name)}</div>
      <div class="small muted">${esc(t.recipient_type)} · ${esc(t.reading_level)} language</div>
      <div class="mt1">
        ${t.requires_authorization ? (hasAuth ? '<span class="badge ok">authorization on file</span>'
          : '<span class="badge danger">needs authorization</span>') : '<span class="badge grey">no authorization required</span>'}
      </div></div>`;
  }).join('');
  return `<div class="card"><h3>1. Choose the source sessions</h3>
      <p class="small muted">Content merges chronologically. Current-state items (mental status, risk, medications) take the most recent entry; narrative accumulates.</p>
      ${evalRows || '<p class="muted">No evaluations yet.</p>'}</div>
    <div class="card" data-tour="templates"><h3>2. Choose who each report is for</h3>
      <p class="small muted">Every template carries its own disclosure rules. Content outside the minimum necessary for that recipient is withheld automatically and itemised on the draft.</p>
      <div class="tmpl-grid">${cards}</div>
      <div class="optbar">
        <label class="checkline m0"><input type="checkbox" data-gen-opt="polish"
            ${S.gen.polish ? 'checked' : ''} ${S.boot.llm.enabled ? '' : 'disabled'}>
          <span>AI language pass ${S.boot.llm.enabled
            ? '<span class="badge">' + esc(S.boot.llm.model) + (S.boot.llm.deidentify_before_send ? ' · de-identified before sending' : ' · local') + '</span>'
            : '<span class="badge grey">no model configured — drafts are composed deterministically</span>'}</span></label>
        ${S.boot.llm.enabled ? '' : '<button class="btn ghost sm" data-a="llm-settings">Use your own key</button>'}
        <label class="checkline m0" ><input type="checkbox" data-gen-opt="deid" ${S.gen.deid ? 'checked' : ''}>
          <span>De-identify (Safe Harbor) — for teaching or research use</span></label>
        <div class="push">
          <button class="btn ghost" data-a="preview">Preview first selection</button>
          <button class="btn" data-a="generate">Generate ${S.gen.templates.length || ''} draft${S.gen.templates.length === 1 ? '' : 's'}</button>
        </div></div></div>
    ${S.gen.preview ? `<h3>Preview — not saved</h3>${reportBody(S.gen.preview, null)}` : ''}`;
}

/* ---------------------------------------------------------------- reports */

function reportsTab(d) {
  const rows = d.reports.map((r) => `<tr>
      <td><strong>${esc(r.template_name)}</strong><div class="small muted">${esc(r.recipient_type)}</div></td>
      <td><span class="badge ${r.status === 'draft' ? 'warn' : (r.status === 'released' ? 'grey' : 'ok')}">${esc(r.status)}</span></td>
      <td class="small">${fmtTime(r.created_at)}${r.amends_report_id
        ? `<div class="muted">amends #${r.amends_report_id}</div>` : ''}</td>
      <td class="ta-right"><button class="btn ghost sm" data-a="open-report" data-id="${r.id}">Open</button></td>
    </tr>`).join('');
  return `<div class="card"><h3>Generated reports</h3>
    <table class="data"><thead><tr><th>Report</th><th>Status</th><th>Created</th><th></th></tr></thead>
    <tbody>${rows || '<tr><td colspan="4" class="muted">Nothing generated yet — use the Generate reports tab.</td></tr>'}</tbody></table></div>`;
}

function reportView() {
  const r = S.report;
  const c = r.content;
  return `<div class="card"><div class="hstack">
      <h3 class="m0">${esc(c.template_name)}</h3>
      <span class="badge ${r.status === 'draft' ? 'warn' : (r.status === 'released' ? 'grey' : 'ok')}">${esc(r.status)}</span>
      ${c.ai_assisted ? '<span class="badge warn">AI-assisted language</span>' : '<span class="badge grey">deterministic draft</span>'}
      ${c.deidentified ? '<span class="badge">de-identified</span>' : ''}
      ${c.amends ? `<span class="badge warn">amends report #${c.amends.report_id}</span>` : ''}
      ${r.amends_report_id && !c.amends ? `<span class="badge warn">amends report #${r.amends_report_id}</span>` : ''}
      <div class="push actionbar" data-tour="report-actions">
        <button class="btn ghost sm" data-a="close-report">Back</button>
        <button class="btn ghost sm" data-a="check-report">Verify against chart</button>
        <button class="btn ghost sm" data-a="print-report">Print / PDF</button>
        <button class="btn ghost sm" data-a="download-report">Download .txt</button>
        ${r.status === 'draft' ? '<button class="btn sm" data-a="sign-report">Review &amp; sign</button>' : ''}
        ${r.status === 'final' ? '<button class="btn sm" data-a="release-report">Record release</button>' : ''}
        ${r.status === 'draft' ? '' : '<button class="btn ghost sm" data-a="amend-report">Create amended version</button>'}
      </div></div>
    <p class="small muted mt2" >${esc(c.audience_note)}</p></div>
    ${(c.warnings || []).map((w) => `<div class="notice warn">${esc(w)}</div>`).join('')}
    ${(c.ai_notes || []).map((w) => `<div class="notice">AI note — ${esc(w)}</div>`).join('')}
    ${S.report.check ? `<div class="notice ${S.report.check.ok ? '' : 'danger'}"><strong>${esc(S.report.check.summary)}</strong>
      ${(S.report.check.problems || []).map((p) => `<div class="small">• ${esc(p)}</div>`).join('')}</div>` : ''}
    <div class="grid2 align-start" >
      <div>${reportBody(c, r)}</div>
      <div>${withheldCard(c)}</div>
    </div>`;
}

function withheldCard(c) {
  const groups = {};
  (c.withheld || []).forEach((w) => { (groups[w.sensitivity_label] = groups[w.sensitivity_label] || []).push(w); });
  const keys = Object.keys(groups);
  return `<div class="card" data-tour="withheld"><h3>Minimum necessary</h3>
    <p class="small muted">Recipient: <strong>${esc(c.recipient_type)}</strong><br>Purpose of disclosure: ${esc(c.purpose)}</p>
    ${c.authorization ? `<div class="notice small"><strong>Authorization on file:</strong> ${esc(c.authorization.recipient_name)},
      signed ${esc(c.authorization.signed_date)}, expires ${esc(c.authorization.expires_date)}.<br>
      Special categories authorised: ${c.authorization.scopes.length ? esc(c.authorization.scopes.join(', ')) : 'none'}.</div>`
      : '<div class="notice warn small">No authorization is linked to this report.</div>'}
    <h4 class="mt3">Withheld from this report (${(c.withheld || []).length})</h4>
    ${keys.length ? keys.map((k) => `<div class="mb2">
      <div class="small"><strong>${esc(k)}</strong></div>
      ${groups[k].map((w) => `<div class="small muted">• ${esc(w.label)}</div>`).join('')}
      <div class="small muted italic" >${esc(groups[k][0].reason)}</div></div>`).join('')
      : '<p class="small muted">Nothing was withheld: every field in the record is within the minimum necessary for this recipient.</p>'}
    ${c.part2_notice ? `<div class="notice warn small"><strong>42 CFR Part 2</strong><br>${esc(c.part2_notice)}</div>` : ''}
    <h4 class="mt3">Source visits</h4>
    <p class="small muted">${(c.source_dates || []).map(esc).join(', ') || '—'}</p></div>`;
}

function reportBody(c, r) {
  const editable = r && r.status === 'draft';
  const sections = c.sections.map((sec, i) => {
    let inner = '';
    const b = sec.body;
    if (sec.kind === 'narrative' || sec.kind === 'signature') inner = b.map((p) => `<p>${nl2br(p)}</p>`).join('');
    else if (sec.kind === 'bullets') inner = '<ul>' + b.map((p) => `<li>${nl2br(p)}</li>`).join('') + '</ul>';
    else if (sec.kind === 'kv') inner = '<table class="kvt"><tbody>' + Object.keys(b).map((k) =>
      `<tr><th>${esc(k)}</th><td>${nl2br(b[k])}</td></tr>`).join('') + '</tbody></table>';
    else if (sec.kind === 'codes') inner = '<ul>' + b.map((x) =>
      `<li><strong>${esc(x.code)}</strong> ${esc(x.description)}</li>`).join('') + '</ul>';
    else if (sec.kind === 'table') inner = '<table class="kvt"><thead><tr>' +
      (sec.columns || []).map((x) => `<th>${esc(x)}</th>`).join('') + '</tr></thead><tbody>' +
      b.map((row) => '<tr>' + row.map((cell) => `<td>${esc(cell)}</td>`).join('') + '</tr>').join('') + '</tbody></table>';
    const prov = (sec.provenance || []).length ? `<div class="prov">Source: ${sec.provenance.map((p) =>
      esc(p.label) + (p.date ? ' (' + esc(p.date) + ')' : '')).join(' · ')}</div>` : '';
    const editBtn = editable && ['narrative', 'bullets'].indexOf(sec.kind) >= 0
      ? `<button class="btn ghost sm float-right"  data-a="edit-section" data-i="${i}">Edit</button>` : '';
    const editing = S.report && S.report.editing === i;
    return `<h3 class="sh">${editBtn}${esc(sec.title)}${sec.ai_edited ? ' <span class="badge warn">AI</span>' : ''}${sec.edited_by_clinician ? ' <span class="badge ok">edited</span>' : ''}</h3>
      ${sec.intro ? `<p><em>${esc(sec.intro)}</em></p>` : ''}
      ${editing ? `<textarea id="secEdit" class="edit-box">${esc(
        (sec.kind === 'kv' ? '' : sec.body.join('\n\n')))}</textarea>
        <div class="my2"><button class="btn sm" data-a="save-section" data-i="${i}">Save section</button>
        <button class="btn ghost sm" data-a="cancel-section">Cancel</button>
        <span class="small muted">One paragraph or bullet per blank line.</span></div>` : inner + prov}`;
  }).join('');
  return `<div class="report" data-tour="report">
    ${(r ? r.status === 'draft' : true) ? '<div class="draft-stamp">DRAFT — NOT FOR RELEASE — CLINICIAN REVIEW REQUIRED</div>' : ''}
    <h2 class="rt">${esc(c.template_name)}</h2>
    <div class="rmeta">${esc(S.boot.practice.name)} · ${esc(S.boot.practice.address)} · ${esc(S.boot.practice.phone)}<br>
      Prepared for: ${esc(c.recipient_type)} · Purpose: ${esc(c.purpose)} · Generated ${esc(c.generated_at)}</div>
    <div class="rhdr">${Object.keys(c.header).map((k) => `<strong>${esc(k)}:</strong> ${esc(c.header[k])}`).join('<br>')}</div>
    ${sections}
    ${c.signature ? `<p class="small"><em>Electronically signed: ${esc(c.signature)}</em></p>` : ''}
    ${c.part2_notice ? `<div class="foot"><strong>42 CFR Part 2 notice.</strong> ${esc(c.part2_notice)}</div>` : ''}
    <div class="foot">${esc(c.footer)}</div></div>`;
}

/* -------------------------------------------------------------- assistant */

const SUGGESTIONS = [
  'What has the medication history been, and what was the response?',
  'Summarise the current risk picture and the safety plan.',
  'What functional impairments are documented?',
  'What did the most recent visit change?',
  'What is missing from the record before I can sign?',
];

function assistantTab() {
  const msgs = S.chat.map((m) => {
    if (m.role === 'user') return `<div class="msg user">${nl2br(m.text)}</div>`;
    const cites = (m.citations || []).length ? `<div class="cites"><strong>Sources</strong>${m.citations.map((c) =>
      `<div class="c">[${c.n}] ${esc(c.title)}${c.date ? ' — ' + esc(c.date) : ''}${c.source ? ' · ' + esc(c.source) : ''}</div>`).join('')}</div>` : '';
    const notes = (m.notes || []).length ? `<div class="cites">${m.notes.map((n) => `<div class="c">${esc(n)}</div>`).join('')}</div>` : '';
    return `<div class="msg bot">${nl2br(m.text)}${cites}${notes}</div>`;
  }).join('');
  const llm = S.boot.llm;
  return `<div class="card" data-tour="assistant"><h3>Assistant</h3>
      <p class="small muted">Scoped to this patient's chart and reports. It answers with citations, declines clinical directives, and never sees psychotherapy process notes.
      ${llm.enabled ? (llm.local ? 'A local model is configured, so nothing leaves this machine.' : 'A remote model is configured; content is de-identified before it is sent.')
        : 'No model is configured — answers are exact quotations retrieved from the chart.'}
      ${S.boot.llm.enabled ? '' : '<button class="btn ghost sm" data-a="llm-settings">Use your own model key</button>'}</p>
      <div class="suggest">${SUGGESTIONS.map((s) => `<button data-a="suggest" data-q="${esc(s)}">${esc(s)}</button>`).join('')}
        <button data-a="completeness">Check documentation completeness</button></div>
      <div class="chat">${msgs || '<div class="muted small">No questions yet.</div>'}</div>
      <div class="chatbar"><input id="chatq" type="text" placeholder="Ask about this patient's record…">
        <button class="btn" data-a="ask">Ask</button></div></div>`;
}

/* ---------------------------------------------------- authorizations tab */

function authTab(d) {
  const rows = (d.authorizations || []).map((a) => `<tr>
      <td><strong>${esc(a.recipient_name)}</strong><div class="small muted">${esc(a.recipient_type)}</div></td>
      <td class="small">${esc(a.scopes.join(', ') || 'general clinical only')}</td>
      <td class="small">${esc(a.signed_date)} → ${esc(a.expires_date)}</td>
      <td><span class="badge ${a.valid ? 'ok' : 'danger'}">${a.revoked ? 'revoked' : (a.expired ? 'expired' : 'valid')}</span></td>
      <td class="ta-right">${a.valid ? `<button class="btn ghost sm" data-a="revoke-auth" data-id="${a.id}">Revoke</button>` : ''}</td>
    </tr>`).join('');
  const types = [...new Set(S.boot.templates.map((t) => t.recipient_type))];
  const scopes = S.boot.protected_classes.filter((s) => s !== 'process_note');
  const disc = (d.disclosures || []).map((x) => `<tr><td class="small">${fmtTime(x.released_at)}</td>
      <td>${esc(x.recipient)}</td><td class="small">${esc(x.method)}</td><td class="small">${esc(x.purpose)}</td>
      <td class="small">${esc(x.released_by)}${x.override_reason ? '<br><span class="badge danger">override</span> ' + esc(x.override_reason) : ''}</td></tr>`).join('');
  return `<div class="card" data-tour="authorizations"><h3>Authorizations for release of information</h3>
      <p class="small muted">Special categories (substance use, trauma, sexual and reproductive, HIV, genetic, legal) are withheld from every report unless the authorization names them. Psychotherapy process notes are never released through this tool.</p>
      <table class="data"><thead><tr><th>Recipient</th><th>Special categories authorised</th><th>Valid</th><th></th><th></th></tr></thead>
      <tbody>${rows || '<tr><td colspan="5" class="muted">None on file.</td></tr>'}</tbody></table></div>
    <div class="card"><h3>Record a new authorization</h3>
      <div class="row">
        <div class="field"><label>Recipient name</label><input id="aName" type="text" placeholder="e.g. Rosa Ellison (mother)"></div>
        <div class="field"><label>Recipient type</label><select id="aType">${types.map((t) => `<option>${esc(t)}</option>`).join('')}</select></div>
      </div>
      <div class="row">
        <div class="field"><label>Signed</label><input id="aSigned" type="date" value="${new Date().toISOString().slice(0, 10)}"></div>
        <div class="field"><label>Expires</label><input id="aExpires" type="date"></div>
        <div class="field"><label>Purpose</label><input id="aPurpose" type="text" placeholder="Purpose of the disclosure"></div>
      </div>
      <label>Special categories the patient specifically authorised</label>
      <div class="row gap1" >${scopes.map((s) => `<label class="checkline noflex fw-normal" >
        <input type="checkbox" data-scope="${s}"> ${esc(S.boot.sensitivity_labels[s] || s)}</label>`).join('')}</div>
      <button class="btn mt2" data-a="create-auth" >Record authorization</button></div>
    <div class="card"><h3>Accounting of disclosures</h3>
      <p class="small muted">Every release is logged here and is available to the patient on request.</p>
      <table class="data"><thead><tr><th>When</th><th>To</th><th>Method</th><th>Purpose</th><th>By</th></tr></thead>
      <tbody>${disc || '<tr><td colspan="5" class="muted">No disclosures recorded.</td></tr>'}</tbody></table></div>`;
}

/* --------------------------------------------------------------- audit UI */

function auditView() {
  const a = S.audit;
  if (!a) return '<div class="content"><div class="card">Loading…</div></div>';
  return `<div class="content"><h1>Compliance &amp; audit</h1>
    ${S.compliance ? complianceCard(S.compliance) : ''}
    <div class="card" data-tour="audit"><h3>Audit trail</h3>
      <p class="small ${a.chain.ok ? 'muted' : ''}">${a.chain.ok ? '' : '<span class="badge danger">TAMPERED</span> '}${esc(a.chain.message)}
        Each entry is chained to the hash of the previous entry.</p>
      <table class="data"><thead><tr><th>When</th><th>User</th><th>Action</th><th>Entity</th><th>Patient</th><th>Detail</th><th>Hash</th></tr></thead>
      <tbody>${a.entries.map((e) => `<tr><td class="small">${fmtTime(e.ts)}</td><td class="small">${esc(e.user)}</td>
        <td class="small"><strong>${esc(e.action)}</strong></td><td class="small">${esc(e.entity)}${e.entity_id ? ' #' + e.entity_id : ''}</td>
        <td class="small">${e.patient_id || ''}</td><td class="small">${esc(e.detail)}</td>
        <td class="mono">${esc(e.hash)}</td></tr>`).join('')}</tbody></table></div></div>`;
}

/* ---------------------------------------------------------------- render */

function render() {
  const root = $('#root');
  if (!S.me) { root.innerHTML = loginView(); return; }
  let main;
  if (S.view === 'audit') main = auditView();
  else if (S.patient) main = patientView();
  else main = homeView();
  const banner = S.hosted ? `<div class="demo-banner">${DEMO_BANNER}</div>` : '';
  root.innerHTML = `<div class="shell">${sidebar()}<div class="main">${banner}${topbar()}${main}</div></div>`;
}

/* --------------------------------------------------------------- actions */

async function loadPatients() {
  const params = new URLSearchParams();
  if (S.filter.q) params.set('q', S.filter.q);
  if (S.filter.tag) params.set('tag', S.filter.tag);
  const data = await api('/api/patients?' + params.toString());
  S.patients = data.patients; S.tags = data.tags;
}

async function openPatient(id) {
  const data = await api('/api/patients/' + id);
  S.patient = data; S.report = null; S.editor = null; S.gen = null; S.view = 'patient';
  if (data.clinical_restricted && ['evaluations', 'generate', 'reports', 'assistant'].indexOf(S.tab) >= 0) S.tab = 'overview';
  if (S.tab === 'assistant') await loadChat(id);
}

async function loadChat(id) {
  try {
    const data = await api('/api/patients/' + id + '/assistant');
    S.chat = data.messages;
  } catch (e) { S.chat = []; }
}

async function refresh() {
  await loadPatients();
  if (S.patient) {
    const id = S.patient.patient.id;
    const keepTab = S.tab, keepReport = S.report && S.report.id;
    await openPatient(id);
    S.tab = keepTab;
    if (keepReport) {
      const data = await api('/api/reports/' + keepReport);
      S.report = data.report;
    }
  }
  render();
}

function collectEditorValues() {
  document.querySelectorAll('[data-field]').forEach((el) => { S.editor.answers[el.dataset.field] = el.value; });
  const multi = {};
  document.querySelectorAll('[data-multi]').forEach((el) => {
    multi[el.dataset.multi] = multi[el.dataset.multi] || [];
    if (el.checked) multi[el.dataset.multi].push(el.value);
  });
  Object.keys(multi).forEach((k) => { S.editor.answers[k] = multi[k].join(', '); });
}

async function saveEvaluation(sign, quiet) {
  collectEditorValues();
  const ed = S.editor;
  const body = {answers: ed.answers, encounter_date: ed.answers.encounter_date || ed.encounter_date};
  if (ed.eval_id) await api('/api/evaluations/' + ed.eval_id, {method: 'PUT', body});
  else {
    const created = await api('/api/patients/' + S.patient.patient.id + '/evaluations',
      {method: 'POST', body: {form_id: ed.form_id, ...body}});
    ed.eval_id = created.evaluation.id;
  }
  ed.dirty = false;
  ed.savedAt = new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
  if (quiet) {
    // Autosave must never steal focus or reflow the form under the cursor.
    const badge = $('#saveState');
    if (badge) badge.textContent = 'Saved ' + ed.savedAt;
    return;
  }
  if (sign) {
    await api('/api/evaluations/' + ed.eval_id + '/sign', {method: 'POST', body: {}});
    S.editor = null;
    toast('Evaluation signed.');
  } else {
    toast('Saved.');
  }
  await refresh();
}

/* Leaving an editor with unsaved content is the easiest way to lose a note, so
   it is always an explicit choice. */
async function leaveEditor() {
  if (!S.editor || !S.editor.dirty || S.editor.locked) return true;
  const choice = await showModal({
    title: 'Unsaved changes',
    intro: 'This evaluation has changes that have not been saved.',
    cancelLabel: 'Keep editing',
    actions: [
      {id: 'save', label: 'Save and continue', cls: ''},
      {id: 'discard', label: 'Discard changes', cls: 'danger'},
    ],
    fields: [],
  });
  if (!choice) return false;
  if (choice.action === 'save') {
    try {
      await saveEvaluation(false, true);
      toast('Saved.');
    } catch (e) {
      fail(e);
      return false;
    }
  }
  S.editor = null;
  return true;
}

async function amendReport() {
  const choice = await showModal({
    title: 'Create an amended version',
    intro: 'The signed report stays in the record exactly as it was, along with any disclosure of '
      + 'it. This creates a new draft that says which document it supersedes.',
    cancelLabel: 'Cancel',
    actions: [
      {id: 'copy', label: 'Copy this document', cls: ''},
      {id: 'regenerate', label: 'Rebuild from the chart', cls: 'ghost'},
    ],
    fields: [],
  });
  if (!choice) return;
  const data = await api('/api/reports/' + S.report.id + '/amend',
    {method: 'POST', body: {regenerate: choice.action === 'regenerate'}});
  S.report = data.report;
  toast('Amended draft created.');
  await refresh();
}

async function doGenerate(previewOnly) {
  const g = S.gen;
  if (!g.templates.length) { toast('Choose at least one recipient template.', true); return; }
  if (!g.evals.length) { toast('Choose at least one evaluation.', true); return; }
  const base = {eval_ids: g.evals, ai_polish: g.polish, deidentify: g.deid};
  if (previewOnly) {
    const data = await api('/api/patients/' + S.patient.patient.id + '/reports/preview',
      {method: 'POST', body: {...base, template_id: g.templates[0]}});
    S.gen.preview = data.content;
    render();
    return;
  }
  const data = await api('/api/patients/' + S.patient.patient.id + '/reports',
    {method: 'POST', body: {...base, template_ids: g.templates}});
  toast(data.reports.length + ' draft report(s) generated.');
  const keep = S.gen.templates.length;
  S.gen = null; S.tab = 'reports';
  await refresh();
  void keep;
}

async function signReport() {
  const all = S.report.content.warnings || [];
  const blocking = all.filter((w) => w.indexOf('Required section') === 0);
  const values = await showModal({
    title: 'Review and sign', submitLabel: 'Sign report',
    intro: 'Signing applies your electronic signature and locks the document. Corrections after this point require a new version.',
    notices: all.map((w) => ({kind: 'warn', text: w})),
    fields: [
      {id: 'attest', type: 'checkbox', required: true,
       label: 'I have read this report in full and attest that it accurately reflects my clinical findings.'},
    ].concat(blocking.length ? [{id: 'ack', type: 'checkbox', required: true,
       label: 'I am signing despite the missing required section(s) named above.'}] : []),
  });
  if (!values) return;
  const data = await api('/api/reports/' + S.report.id + '/sign',
    {method: 'POST', body: {attest: true, acknowledge_incomplete: blocking.length > 0}});
  S.report = data.report;
  toast('Report signed.');
  await refresh();
}

async function releaseReport() {
  const auth = S.report.content.authorization;
  const values = await showModal({
    title: 'Record a release', submitLabel: 'Record release',
    intro: 'This is the accounting of disclosures the patient is entitled to see. Record it at the moment the document actually leaves the practice.',
    notices: auth ? [] : [{kind: 'warn', text: 'No authorization is linked to this report.'}],
    fields: [
      {id: 'recipient', label: 'Released to', required: true,
       value: auth ? auth.recipient_name : '', placeholder: 'Name and organisation'},
      {id: 'method', label: 'Delivery method', type: 'select',
       options: ['Secure fax', 'Encrypted email', 'Patient portal', 'Hand-delivered', 'Postal mail', 'Direct message (HISP)']},
      {id: 'purpose', label: 'Purpose of the disclosure', value: S.report.content.purpose},
    ],
  });
  if (!values) return;
  try {
    const data = await api('/api/reports/' + S.report.id + '/release', {method: 'POST', body: values});
    S.report = data.report;
    toast('Release recorded in the accounting of disclosures.');
    await refresh();
  } catch (e) {
    if (e.status !== 403) return fail(e);
    const override = await showModal({
      title: 'Authorization missing', danger: true, submitLabel: 'Release with documented override',
      notices: [{kind: 'danger', text: e.message}],
      intro: 'Some disclosures are permitted without authorization — an emergency, a duty to warn, or a legally required report. Document which applies. This reason is written to the audit trail and to the accounting of disclosures.',
      fields: [{id: 'override_reason', label: 'Reason this disclosure is permitted without authorization',
                type: 'textarea', required: true}],
    });
    if (!override) return;
    const data = await api('/api/reports/' + S.report.id + '/release',
      {method: 'POST', body: {...values, override_reason: override.override_reason}});
    S.report = data.report;
    toast('Release recorded with a documented override.');
    await refresh();
  }
}

async function ask(question) {
  if (!question.trim()) return;
  S.chat.push({role: 'user', text: question});
  render();
  try {
    const data = await api('/api/patients/' + S.patient.patient.id + '/assistant',
      {method: 'POST', body: {question}});
    S.chat.push({role: 'assistant', text: data.answer, citations: data.citations, notes: data.notes});
  } catch (e) {
    S.chat.pop();
    fail(e);
  }
  render();
}

async function openAudit() {
  const [entries, chain, compliance] = await Promise.all([
    api('/api/audit?limit=300'), api('/api/audit/verify'), api('/api/compliance'),
  ]);
  S.audit = {entries: entries.entries, chain};
  S.compliance = compliance;
  S.view = 'audit'; S.patient = null;
  render();
}

/* ---------------------------------------------------------------- events */

document.addEventListener('click', async (ev) => {
  const target = ev.target.closest('[data-a]');
  if (!target) return;
  const a = target.dataset.a;
  try {
    if (a === 'fill') { $('#u').value = target.dataset.u; $('#p').value = target.dataset.p; return; }
    if (a === 'llm-settings') { await llmSettings(); return; }
    if (a === 'start-tour') { await startTour(); return; }
    if (a === 'go-home') {
      if (!await leaveEditor()) return;
      S.patient = null; S.report = null; S.editor = null; S.view = 'home';
      await loadPatients(); render(); return;
    }
    if (a === 'tour-login') {
      await api('/api/login', {method: 'POST', body: {username: 'dr.chen', password: 'Demo!Pass1'}});
      await boot();
      if (S.me) await startTour();
      return;
    }
    if (a === 'logout') {
      if (!await leaveEditor()) return;
      await api('/api/logout', {method: 'POST', body: {}});
      S.me = null; S.patient = null; S.resume = null; render(); return;
    }
    if (a === 'tag') { S.filter.tag = target.dataset.t; await loadPatients(); render(); return; }
    if (a === 'open-patient') {
      if (!await leaveEditor()) return;
      await openPatient(Number(target.dataset.id)); S.tab = 'overview'; render(); return;
    }
    if (a === 'view-compliance') { if (!await leaveEditor()) return; await openAudit(); return; }
    if (a === 'tab') {
      if (!await leaveEditor()) return;
      S.tab = target.dataset.t; S.report = null; S.editor = null;
      if (S.tab === 'assistant') await loadChat(S.patient.patient.id);
      render(); return;
    }
    if (a === 'new-patient') {
      const values = await showModal({
        title: 'New patient', submitLabel: 'Create record',
        intro: 'A medical record number is assigned automatically. Everything entered here is encrypted before it touches the disk.',
        fields: DEMOGRAPHIC_FIELDS.concat([{id: 'tags', label: 'Tags', hint: 'Comma separated, e.g. Mood disorders, Telepsychiatry'}]),
      });
      if (!values) return;
      const tags = values.tags.split(',').map((t) => t.trim()).filter(Boolean);
      delete values.tags;
      const created = await api('/api/patients', {method: 'POST',
        body: {demographics: values, tags}});
      await loadPatients();
      await openPatient(created.patient.id);
      S.tab = 'overview'; render(); return;
    }
    if (a === 'edit-demographics') {
      const dem = S.patient.patient.demographics;
      const values = await showModal({
        title: 'Patient details', submitLabel: 'Save',
        fields: DEMOGRAPHIC_FIELDS.map((f) => ({...f, value: dem[f.id] || ''}))
          .concat([{id: 'tags', label: 'Tags', value: (S.patient.patient.tags || []).join(', ')}]),
      });
      if (!values) return;
      const tags = values.tags.split(',').map((t) => t.trim()).filter(Boolean);
      delete values.tags;
      await api('/api/patients/' + S.patient.patient.id, {method: 'PUT',
        body: {demographics: values, tags}});
      toast('Updated.'); await refresh(); return;
    }
    if (a === 'new-eval') { S.tab = 'evaluations'; render(); return; }
    if (a === 'create-eval') {
      const form_id = $('#newform').value; const date = $('#newdate').value;
      if (!date) { toast('Choose a date of service.', true); return; }
      S.editor = {form_id, eval_id: null, answers: {encounter_date: date}, open: {}, locked: false, encounter_date: date};
      S.tab = 'evaluations'; render(); return;
    }
    if (a === 'open-eval') {
      const e = S.patient.evaluations.find((x) => x.id === Number(target.dataset.id));
      S.editor = {form_id: e.form_id, eval_id: e.id, answers: {...e.answers}, open: {},
        locked: e.status === 'signed', encounter_date: e.encounter_date};
      render(); return;
    }
    if (a === 'toggle-section') {
      collectEditorValues();
      const id = target.dataset.s;
      S.editor.open[id] = S.editor.open[id] === false;
      render(); return;
    }
    if (a === 'close-editor') { if (!await leaveEditor()) return; S.editor = null; render(); return; }
    if (a === 'save-eval') { await saveEvaluation(false); return; }
    if (a === 'save-sign-eval') { await saveEvaluation(true); return; }
    if (a === 'sign-eval') {
      await api('/api/evaluations/' + target.dataset.id + '/sign', {method: 'POST', body: {}});
      toast('Signed.'); await refresh(); return;
    }
    if (a === 'toggle-template') {
      const t = target.dataset.t;
      const i = S.gen.templates.indexOf(t);
      if (i >= 0) S.gen.templates.splice(i, 1); else S.gen.templates.push(t);
      render(); return;
    }
    if (a === 'preview') { await doGenerate(true); return; }
    if (a === 'generate') { await doGenerate(false); return; }
    if (a === 'open-report') {
      const data = await api('/api/reports/' + target.dataset.id);
      S.report = data.report; S.tab = 'reports'; render(); return;
    }
    if (a === 'close-report') { S.report = null; render(); return; }
    if (a === 'edit-section') { S.report.editing = Number(target.dataset.i); render(); return; }
    if (a === 'cancel-section') { S.report.editing = null; render(); return; }
    if (a === 'save-section') {
      const i = Number(target.dataset.i);
      const text = $('#secEdit').value;
      const body = S.report.content.sections[i].kind === 'bullets'
        ? text.split('\n').map((s) => s.trim()).filter(Boolean)
        : text.split(/\n\s*\n/).map((s) => s.trim()).filter(Boolean);
      const data = await api('/api/reports/' + S.report.id, {method: 'PUT', body: {section_index: i, body}});
      S.report = data.report; S.report.editing = null;
      toast('Section updated.'); render(); return;
    }
    if (a === 'amend-report') { await amendReport(); return; }
    if (a === 'sign-report') { await signReport(); return; }
    if (a === 'release-report') { await releaseReport(); return; }
    if (a === 'check-report') {
      const data = await api('/api/reports/' + S.report.id + '/consistency', {method: 'POST', body: {}});
      S.report.check = data; render(); return;
    }
    if (a === 'print-report') { window.open('/api/reports/' + S.report.id + '/export?format=html', '_blank'); return; }
    if (a === 'download-report') { window.location.href = '/api/reports/' + S.report.id + '/export?format=txt'; return; }
    if (a === 'suggest') { await ask(target.dataset.q); return; }
    if (a === 'ask') { const box = $('#chatq'); const q = box.value; box.value = ''; await ask(q); return; }
    if (a === 'completeness') {
      const c = S.patient.completeness;
      S.chat.push({role: 'user', text: 'Check documentation completeness'});
      S.chat.push({role: 'assistant', text: c.summary + '\n' + c.findings.map((f) =>
        `\n${f.form} (${f.date}) — missing: ${f.missing.join(', ')}`).join(''), citations: [], notes: []});
      render(); return;
    }
    if (a === 'create-auth') {
      const scopes = [...document.querySelectorAll('[data-scope]')].filter((x) => x.checked).map((x) => x.dataset.scope);
      await api('/api/patients/' + S.patient.patient.id + '/authorizations', {method: 'POST', body: {
        recipient_name: $('#aName').value, recipient_type: $('#aType').value,
        signed_date: $('#aSigned').value, expires_date: $('#aExpires').value,
        purpose: $('#aPurpose').value, scopes}});
      toast('Authorization recorded.'); await refresh(); return;
    }
    if (a === 'revoke-auth') {
      const ok = await showModal({
        title: 'Revoke authorization', danger: true, submitLabel: 'Revoke',
        notices: [{kind: 'danger', text: 'Reports for that recipient can no longer be released without a new authorization or a documented override. Disclosures already made are unaffected and remain in the accounting.'}],
        fields: [],
      });
      if (!ok) return;
      await api('/api/authorizations/' + target.dataset.id + '/revoke', {method: 'POST', body: {}});
      toast('Revoked.'); await refresh(); return;
    }
  } catch (e) { fail(e); }
});

document.addEventListener('submit', async (ev) => {
  if (ev.target.id !== 'loginForm') return;
  ev.preventDefault();
  try {
    await api('/api/login', {method: 'POST', body: {username: $('#u').value, password: $('#p').value}});
    await boot();
  } catch (e) { toast(e.message, true); }
});

let searchTimer = null;
document.addEventListener('input', (ev) => {
  const el = ev.target;
  if (el.id === 'psearch') {
    S.filter.q = el.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => {
      const pos = el.selectionStart;
      await loadPatients(); render();
      const box = $('#psearch');
      if (box) { box.focus(); box.setSelectionRange(pos, pos); }
    }, 250);
    return;
  }
  if (el.dataset && el.dataset.field && S.editor) {
    S.editor.answers[el.dataset.field] = el.value;
    markDirty();
  }
  if (el.dataset && el.dataset.multi && S.editor) markDirty();
  if (el.dataset && el.dataset.genEval && S.gen) {
    const id = Number(el.dataset.genEval);
    const i = S.gen.evals.indexOf(id);
    if (el.checked && i < 0) S.gen.evals.push(id);
    if (!el.checked && i >= 0) S.gen.evals.splice(i, 1);
  }
  if (el.dataset && el.dataset.genOpt && S.gen) S.gen[el.dataset.genOpt] = el.checked;
});

document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Enter' && ev.target.id === 'chatq') {
    ev.preventDefault();
    const q = ev.target.value; ev.target.value = '';
    ask(q);
  }
});

/* ------------------------------------------------- bring your own model key */

async function llmSettings() {
  const current = S.boot.llm || {};
  const defaults = S.boot.llm_defaults || {};
  const mine = !!current.user_supplied;
  const actions = [{id: 'save', label: mine ? 'Replace key' : 'Save & test'}];
  if (mine) actions.push({id: 'remove', label: 'Remove key', cls: 'danger'});
  const values = await showModal({
    title: 'Use your own model key',
    intro: mine
      ? `This session is using ${current.model} with key ${current.key_hint}. Paste a new key to replace it.`
      : 'The assistant and the AI language pass work without a model, using exact quotations from the '
        + 'chart and deterministic drafting. Add an OpenRouter key to have a model write instead.',
    notices: [{kind: 'warn', text: 'The key is kept in memory for your sign-in only: never written to the '
      + 'database or the audit log, and dropped when you sign out or the service restarts. Requests are '
      + 'billed to you, so set a spending limit on the key first.'}],
    submitLabel: 'Save & test',
    actions,
    fields: [
      {id: 'api_key', label: 'OpenRouter API key', type: 'password',
       placeholder: 'sk-or-v1-…', hint: 'Create one at openrouter.ai/keys'},
      {id: 'model', label: 'Model', value: mine ? current.model : (defaults.model || ''),
       hint: 'Any model id listed at openrouter.ai/models'},
      {id: 'base_url', label: 'Endpoint', value: defaults.base_url || '',
       hint: 'Any OpenAI-compatible endpoint; OpenRouter by default'},
    ],
  });
  if (!values) return;
  if (values.action === 'remove') {
    await api('/api/llm/session', {method: 'DELETE'});
    toast('Key removed. Drafting and the assistant are deterministic again.');
  } else {
    if (!values.api_key) { toast('Paste a key, or cancel.', true); return; }
    const result = await api('/api/llm/session', {method: 'POST', body: {
      api_key: values.api_key, model: values.model, base_url: values.base_url}});
    toast(result.message || 'Key accepted.');
  }
  S.boot = await api('/api/bootstrap');
  render();
}

/* ------------------------------------------------------------ guided tour */
/* Each step's prepare() establishes the full state that step needs on its own,
   rather than relying on the step before it. That is what makes Back, Next,
   and restarting mid-way all safe. */

const TOUR_PATIENT = 'MRN-00101';
const TOUR_TEMPLATES = ['family_caregiver', 'insurance_lmn', 'employer_accommodation'];
const Tour = {steps: [], i: 0, active: false, busy: false, target: null};
/* Waits for layout to settle before measuring. requestAnimationFrame is paused
   while a tab or pane is hidden, so a timer guarantees the tour never stalls. */
/* A selector may match an element the current layout hides (the sidebar on a
   phone). The first match with a real size is the one worth pointing at. */
function findVisible(selector) {
  return [...document.querySelectorAll(selector)].find((el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }) || null;
}

const nextFrame = () => new Promise((resolve) => {
  let done = false;
  const finish = () => { if (!done) { done = true; resolve(); } };
  requestAnimationFrame(() => requestAnimationFrame(finish));
  setTimeout(finish, 100);
});

async function tourHome() {
  S.patient = null; S.report = null; S.editor = null; S.view = 'home';
  S.filter = {q: '', tag: ''};
  await loadPatients();
  render();
}

async function tourPatient(mrn, tab) {
  let p = S.patients.find((x) => x.mrn === mrn);
  if (!p) {
    S.filter = {q: '', tag: ''};
    await loadPatients();
    p = S.patients.find((x) => x.mrn === mrn);
  }
  if (!p) throw new Error('The demo patient this step uses is not in this database. Reset the demo data and try again.');
  if (!S.patient || S.patient.patient.id !== p.id || S.view !== 'patient') await openPatient(p.id);
  S.view = 'patient'; S.tab = tab; S.report = null; S.editor = null;
  if (tab === 'assistant') await loadChat(p.id);
  render();
}

async function tourGenerate() {
  await tourPatient(TOUR_PATIENT, 'generate');
  S.gen = {evals: S.patient.evaluations.map((e) => e.id), templates: TOUR_TEMPLATES.slice(),
    polish: false, deid: false, preview: null};
  render();
}

async function tourReport(templateId) {
  await tourPatient(TOUR_PATIENT, 'reports');
  const pid = S.patient.patient.id;
  // Reuse drafts from an earlier run so repeating the tour doesn't pile up duplicates.
  const missing = TOUR_TEMPLATES.filter((t) => !S.patient.reports.some((r) => r.template_id === t));
  if (missing.length) {
    await api('/api/patients/' + pid + '/reports', {method: 'POST',
      body: {template_ids: missing, eval_ids: S.patient.evaluations.map((e) => e.id)}});
    await openPatient(pid);
    S.view = 'patient'; S.tab = 'reports';
    await loadPatients();
  }
  const existing = S.patient.reports.find((r) => r.template_id === templateId);
  const data = await api('/api/reports/' + existing.id);
  S.report = data.report;
  render();
}

const TOUR_CLINICAL = [
  {id: 'welcome', title: 'Welcome to PsychReport', target: null, prepare: tourHome,
   body: '<p>PsychReport turns one psychiatric evaluation into the different documents each person in a patient’s care needs — each written for its reader, each carrying only what that reader is entitled to see.</p><p>This tour uses the fictional demo patients. Along the way it creates three draft reports for Maya Ellison. Nothing is signed or released.</p>'},
  {id: 'patients', title: 'Patients', target: '[data-tour="patients"], [data-tour="patient-cards"]', prepare: tourHome,
   body: '<p>Patients are grouped by tag and searchable by name, MRN or tag. Each row shows the documented risk level and how many evaluations and reports the chart holds.</p>'},
  {id: 'risk', title: 'Risk comes first', target: '[data-tour="risk"]', prepare: () => tourPatient(TOUR_PATIENT, 'overview'),
   body: '<p>Opening a chart surfaces the current suicide-risk stratification and safety plan, taken from the most recent visit.</p><p>Gaps — moderate risk with no safety plan, or an identified potential victim with no duty-to-warn analysis — are flagged here in red.</p>'},
  {id: 'evaluations', title: 'Sessions accumulate', target: '[data-tour="evaluations"]', prepare: () => tourPatient(TOUR_PATIENT, 'evaluations'),
   body: '<p>Maya has two visits: an initial evaluation structured on the APA practice guideline, and a follow-up note.</p><p>A report can be built from one visit or several. Current-state items such as mental status, risk and medication come from the latest visit; narrative accumulates in date order.</p>'},
  {id: 'templates', title: 'Choose who each report is for', target: '[data-tour="templates"]', prepare: tourGenerate,
   body: '<p>Each card is a recipient. Three are selected: a family summary, a letter of medical necessity for the insurer, and a workplace accommodation letter.</p><p>Every template is also a disclosure rule. The badge shows whether the signed authorization that recipient requires is on file.</p>'},
  {id: 'generate', title: 'One chart, several documents', target: '[data-a="generate"]', prepare: tourGenerate,
   nextLabel: 'Generate the drafts',
   body: '<p>One click composes all three drafts from the same record. Composition is deterministic: the clinician’s own words, selected and framed for each reader. Nothing is invented.</p>'},
  {id: 'report', title: 'A draft, written for its reader', target: '[data-tour="report"]', prepare: () => tourReport('family_caregiver'),
   body: '<p>The family summary uses plain language, explains clinical terms in place, and attaches crisis resources.</p><p>Under every section, <em>Source</em> names the visit and field each statement came from. The document stays a watermarked draft until a clinician signs it.</p>'},
  {id: 'withheld', title: 'What was left out, and why', target: '[data-tour="withheld"]', prepare: () => tourReport('family_caregiver'),
   body: '<p>Substance use, trauma, legal and family genetic history are withheld from a family member unless the patient’s authorization names them. Each omission is listed with its reason.</p><p>Psychotherapy process notes never leave. There is no override.</p>'},
  {id: 'employer', title: 'Same chart, different reader', target: '[data-tour="report"]', prepare: () => tourReport('employer_accommodation'),
   body: '<p>The employer letter describes functional limitations and the accommodations recommended — and deliberately contains <strong>no diagnosis</strong>, which an employer is not entitled to.</p>'},
  {id: 'actions', title: 'Nothing leaves without a signature', target: '[data-tour="report-actions"]', prepare: () => tourReport('family_caregiver'),
   body: '<p><strong>Verify against chart</strong> confirms every number, dose, code and date is traceable to the record.</p><p>Signing requires an attestation and locks the document; a correction becomes an amended version. Release is blocked without a valid authorization, and every release is logged.</p>'},
  {id: 'assistant', title: 'An assistant that stays inside the record', target: '[data-tour="assistant"]', prepare: () => tourPatient(TOUR_PATIENT, 'assistant'),
   body: '<p>The assistant answers questions about this one patient’s chart and reports, quoting the record with citations. It declines clinical directives and never sees process notes.</p><p>Try a suggested question after the tour.</p>'},
  {id: 'authorizations', title: 'Authorizations and disclosures', target: '[data-tour="authorizations"]', prepare: () => tourPatient(TOUR_PATIENT, 'authorizations'),
   body: '<p>Authorizations record who may receive what, and until when. Revoking one blocks further releases immediately.</p><p>Further down, the accounting of disclosures is the list a patient is entitled to request.</p>'},
  {id: 'controls', title: 'Safeguards you can inspect', target: '[data-tour="controls"]', prepare: openAudit,
   body: '<p>Every safeguard is listed with its live status: encryption at rest, minimum necessary, 42 CFR Part 2, automatic logoff. Anything needing attention shows as a warning, not a footnote.</p>'},
  {id: 'audit', title: 'A tamper-evident audit trail', target: '[data-tour="audit"]', prepare: openAudit,
   body: '<p>Every access, generation, signature and release is logged. Each entry carries the hash of the one before it, so editing or deleting a row breaks the chain — and the check here reports it.</p>'},
  {id: 'finish', title: 'That’s the core loop', target: null, prepare: () => tourPatient('MRN-00104', 'overview'),
   body: '<p>A good next step: <strong>Thomas Whitfield</strong>, open behind this card, has elevated risk and substance use content. Generate his insurer letter and his school letter, and compare what the 42 CFR Part 2 rules let each one carry.</p><p>Restart the tour any time from <strong>Tour</strong> at the top right.</p>'},
];

const TOUR_STAFF = [
  {id: 'welcome', title: 'Front desk view', target: null, prepare: tourHome,
   body: '<p>You’re signed in as front desk. This role manages registration details and never sees clinical content. This short tour shows where that boundary sits.</p>'},
  {id: 'patients', title: 'Patients', target: '[data-tour="patients"], [data-tour="patient-cards"]', prepare: tourHome,
   body: '<p>The patient list is available for scheduling and registration. Risk levels and diagnoses are not shown to this role.</p>'},
  {id: 'demographics', title: 'Demographics only', target: '[data-tour="demographics"]', prepare: () => tourPatient(TOUR_PATIENT, 'overview'),
   body: '<p>Contact, insurance and emergency-contact details are available for registration and billing tasks.</p>'},
  {id: 'tabs', title: 'The clinical boundary', target: '[data-tour="patient-tabs"]', prepare: () => tourPatient(TOUR_PATIENT, 'overview'),
   body: '<p>Evaluations, reports and the assistant are not offered to this role — and the server refuses those requests even if they’re made directly.</p>'},
  {id: 'finish', title: 'See the clinical side', target: null, prepare: () => tourPatient(TOUR_PATIENT, 'overview'),
   body: '<p>Sign out and choose <strong>Take the guided tour</strong> on the sign-in page to see the clinician’s view.</p>'},
];

const TOUR_AUDITOR = [
  {id: 'welcome', title: 'Compliance auditor view', target: null, prepare: openAudit,
   body: '<p>You’re signed in as compliance auditor: control status and the audit trail, and nothing in any patient’s chart.</p>'},
  {id: 'controls', title: 'Safeguards you can inspect', target: '[data-tour="controls"]', prepare: openAudit,
   body: '<p>Every safeguard is listed with its live status. Anything needing attention shows as a warning.</p>'},
  {id: 'audit', title: 'A tamper-evident audit trail', target: '[data-tour="audit"]', prepare: openAudit,
   body: '<p>Each entry carries the hash of the one before it, so an edited or deleted row breaks the chain — and the check above reports it.</p><p>Recipient names are kept out of this log deliberately: an auditor is not entitled to the content of a disclosure.</p>'},
  {id: 'finish', title: 'See the clinical side', target: null, prepare: openAudit,
   body: '<p>Sign out and choose <strong>Take the guided tour</strong> on the sign-in page to see the clinician’s view.</p>'},
];

function tourStepsFor(role) {
  if (role === 'staff') return TOUR_STAFF;
  if (role === 'auditor') return TOUR_AUDITOR;
  return TOUR_CLINICAL;
}

async function startTour() {
  if (Tour.active || !S.me) return;
  if (!await leaveEditor()) return;
  Tour.steps = tourStepsFor(S.me.user.role);
  Tour.active = true;
  Tour.target = null;
  const layer = document.createElement('div');
  layer.id = 'tourLayer';
  layer.className = 'tour-layer';
  layer.innerHTML = `<div class="tour-shade"></div><div class="tour-spot hidden"></div>
    <div class="tour-card centered" role="dialog" aria-modal="true" aria-labelledby="tourTitle">
      <div class="tour-progress"></div>
      <h3 id="tourTitle"></h3>
      <div class="tour-body"></div>
      <div class="tour-err small hidden" role="alert"></div>
      <div class="tour-actions">
        <button class="btn ghost sm" type="button" data-tour-act="skip">End tour</button>
        <span class="push"></span>
        <button class="btn ghost sm" type="button" data-tour-act="back">Back</button>
        <button class="btn sm" type="button" data-tour-act="next">Next</button>
      </div></div>`;
  document.body.appendChild(layer);
  document.body.classList.add('tour-active');
  layer.addEventListener('click', onTourClick);
  layer.addEventListener('wheel', onTourWheel, {passive: true});
  document.addEventListener('keydown', onTourKey, true);
  document.addEventListener('scroll', positionTour, true);
  window.addEventListener('resize', positionTour);
  await showTourStep(0);
}

function endTour(message) {
  if (!Tour.active) return;
  Tour.active = false;
  Tour.busy = false;
  Tour.target = null;
  const layer = $('#tourLayer');
  if (layer) layer.remove();
  document.body.classList.remove('tour-active');
  document.removeEventListener('keydown', onTourKey, true);
  document.removeEventListener('scroll', positionTour, true);
  window.removeEventListener('resize', positionTour);
  if (message) toast(message);
}

async function showTourStep(i) {
  const layer = $('#tourLayer');
  if (!layer || Tour.busy) return;
  Tour.busy = true;
  Tour.i = i;
  const step = Tour.steps[i];
  const card = layer.querySelector('.tour-card');
  const err = layer.querySelector('.tour-err');
  const [skip, back, next] = ['skip', 'back', 'next'].map((a) => layer.querySelector(`[data-tour-act="${a}"]`));
  card.dataset.step = step.id;
  card.dataset.ready = 'false';
  layer.querySelector('.tour-progress').textContent = `Step ${i + 1} of ${Tour.steps.length}`;
  layer.querySelector('#tourTitle').textContent = step.title;
  layer.querySelector('.tour-body').innerHTML = '<p class="muted">Working…</p>';
  err.classList.add('hidden');
  [back, next].forEach((b) => { b.disabled = true; });

  let failure = null;
  try {
    if (step.prepare) await step.prepare();
  } catch (e) {
    failure = e;
  }
  if (!Tour.active) return;
  if (failure && failure.status === 401) {
    endTour();
    fail(failure);
    return;
  }

  layer.querySelector('.tour-body').innerHTML = step.body;
  const target = step.target ? findVisible(step.target) : null;
  Tour.target = target;
  card.dataset.targetFound = step.target ? String(!!target) : 'none';
  if (failure) {
    err.textContent = failure.message || 'This step could not be prepared.';
    err.classList.remove('hidden');
  } else if (step.target && !target) {
    err.textContent = 'The part of the page this step points to isn’t available right now.';
    err.classList.remove('hidden');
  }
  if (target) {
    const narrow = window.innerWidth < 720;
    const tall = target.getBoundingClientRect().height > window.innerHeight * (narrow ? 0.3 : 0.6);
    if (narrow || tall) {
      // On a phone the card docks over the lower part of the screen, and a tall
      // target can't be centred either way, so align its top just below the
      // sticky top bar where it stays visible.
      target.scrollIntoView({block: 'start', inline: 'nearest'});
      const main = document.querySelector('.main');
      const bar = document.querySelector('.topbar');
      if (main && bar && main.contains(target)) {
        const clearance = bar.getBoundingClientRect().bottom + 12 - target.getBoundingClientRect().top;
        if (clearance > 0) main.scrollTop -= clearance;
      }
    } else {
      target.scrollIntoView({block: 'center', inline: 'nearest'});
    }
  }
  back.classList.toggle('hidden', i === 0);
  next.textContent = i === Tour.steps.length - 1 ? 'Finish' : (step.nextLabel || 'Next');
  skip.classList.toggle('hidden', i === Tour.steps.length - 1);
  await nextFrame();
  positionTour();
  [back, next].forEach((b) => { b.disabled = false; });
  card.dataset.ready = 'true';
  Tour.busy = false;
  next.focus({preventScroll: true});
}

/* Placement uses CSSOM properties (el.style.top), which the Content Security
   Policy permits; only inline style attributes in markup are blocked. */
function positionTour() {
  if (!Tour.active) return;
  const layer = $('#tourLayer');
  if (!layer) return;
  const spot = layer.querySelector('.tour-spot');
  const shade = layer.querySelector('.tour-shade');
  const card = layer.querySelector('.tour-card');
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const target = Tour.target && document.body.contains(Tour.target) ? Tour.target : null;

  if (!target) {
    spot.classList.add('hidden');
    shade.classList.remove('hidden');
    card.classList.remove('docked');
    card.classList.add('centered');
    card.style.top = ''; card.style.left = '';
    return;
  }
  const pad = 8;
  const gap = 14;
  const r = target.getBoundingClientRect();
  const top = Math.max(r.top - pad, 4);
  const left = Math.max(r.left - pad, 4);
  const bottom = Math.min(r.bottom + pad, vh - 4);
  const right = Math.min(r.right + pad, vw - 4);
  spot.style.top = top + 'px';
  spot.style.left = left + 'px';
  spot.style.width = Math.max(right - left, 0) + 'px';
  spot.style.height = Math.max(bottom - top, 0) + 'px';
  spot.classList.remove('hidden');
  shade.classList.add('hidden');
  card.classList.remove('centered');

  if (vw < 720) {
    card.classList.add('docked');
    card.style.top = ''; card.style.left = '';
    return;
  }
  card.classList.remove('docked');
  const cw = card.offsetWidth;
  const ch = card.offsetHeight;
  let ct;
  let cl;
  if (vh - bottom >= ch + gap) { ct = bottom + gap; cl = left; }
  else if (top >= ch + gap) { ct = top - gap - ch; cl = left; }
  else if (vw - right >= cw + gap) { ct = top; cl = right + gap; }
  else if (left >= cw + gap) { ct = top; cl = left - gap - cw; }
  else { ct = vh - ch - 16; cl = left; }
  const cardLeft = Math.min(Math.max(cl, 12), vw - cw - 12);
  const cardTop = Math.min(Math.max(ct, 12), vh - ch - 12);
  card.style.left = cardLeft + 'px';
  card.style.top = cardTop + 'px';
  // A target taller and wider than the free space leaves nowhere for the card.
  // Rather than cover it, keep its start highlighted and stop the spotlight
  // just above the card -- provided enough of the target remains to be useful.
  const cardRight = cardLeft + cw;
  const overlapsSpot = cardTop < bottom && cardTop + ch > top && cardLeft < right && cardRight > left;
  if (overlapsSpot && cardTop - gap - top >= 48) {
    spot.style.height = (cardTop - gap - top) + 'px';
  }
}

async function onTourClick(e) {
  const button = e.target.closest('[data-tour-act]');
  if (!button || Tour.busy) return;
  const act = button.dataset.tourAct;
  if (act === 'skip') return endTour('Tour ended. Restart it any time from Tour at the top right.');
  if (act === 'back' && Tour.i > 0) return showTourStep(Tour.i - 1);
  if (act === 'next') {
    if (Tour.i >= Tour.steps.length - 1) return endTour();
    return showTourStep(Tour.i + 1);
  }
}

function onTourWheel(e) {
  const main = document.querySelector('.main');
  if (main) main.scrollTop += e.deltaY;
}

function onTourKey(e) {
  if (!Tour.active || document.querySelector('.modal-back')) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); endTour(); return; }
  if (Tour.busy) return;
  if (e.key === 'ArrowRight') { e.preventDefault(); onTourClick({target: $('#tourLayer [data-tour-act="next"]')}); }
  if (e.key === 'ArrowLeft' && Tour.i > 0) { e.preventDefault(); showTourStep(Tour.i - 1); }
}

/* ---------------------------------------------------- timers and recovery */

function markDirty() {
  if (!S.editor || S.editor.locked) return;
  S.editor.dirty = true;
  const badge = $('#saveState');
  if (badge) badge.textContent = 'Unsaved changes';
}

/* Autosave does two jobs: it protects the note, and the request keeps the
   server-side session alive while the clinician is typing rather than clicking. */
setInterval(async () => {
  if (!S.me || !S.editor || !S.editor.dirty || S.editor.locked || !S.patient) return;
  try {
    await saveEvaluation(false, true);
  } catch (e) {
    const badge = $('#saveState');
    if (badge) badge.textContent = 'Autosave failed — use Save';
    if (e.status === 401) fail(e);
  }
}, AUTOSAVE_MS);

/* The server signs a session out after 15 minutes without a request. Warn
   before that happens rather than failing the next action. */
let idleModalOpen = false;
setInterval(async () => {
  if (!S.me || idleModalOpen || S.idleWarned) return;
  if (Date.now() - S.lastRequestAt < IDLE_WARN_MS) return;
  S.idleWarned = true;
  idleModalOpen = true;
  const stay = await showModal({
    title: 'You will be signed out shortly',
    intro: 'For safety, PsychReport signs you out after 15 minutes without activity. Anything you '
      + 'have typed is kept in this window either way.',
    submitLabel: 'Stay signed in', cancelLabel: 'Sign out now',
    fields: [],
  });
  idleModalOpen = false;
  if (stay) {
    try { await api('/api/me'); } catch (e) { fail(e); }
  } else {
    try { await api('/api/logout', {method: 'POST', body: {}}); } catch (e) { /* already gone */ }
    S.me = null; S.patient = null; render();
  }
}, 30000);

window.addEventListener('beforeunload', (ev) => {
  if (S.editor && S.editor.dirty && !S.editor.locked) {
    ev.preventDefault();
    ev.returnValue = '';
  }
});

async function restoreAfterSignIn() {
  const held = S.resume;
  S.resume = null;
  if (!held || !held.patientId) return false;
  try {
    await openPatient(held.patientId);
    S.tab = held.tab || 'overview';
    if (held.editor) {
      S.editor = held.editor;
      S.tab = 'evaluations';
      toast('Signed back in. Your unsaved evaluation was restored — save it now.');
    } else if (held.reportId) {
      const data = await api('/api/reports/' + held.reportId);
      S.report = data.report;
    }
    render();
    return true;
  } catch (e) {
    return false;
  }
}

/* ------------------------------------------------------------------ boot */

async function boot() {
  try {
    S.hosted = !!(await api('/api/public-config')).hosted;
  } catch (e) {
    S.hosted = false;
  }
  try {
    S.me = await api('/api/me');
    S.boot = await api('/api/bootstrap');
  } catch (e) {
    S.me = null;
    render();
    return;
  }
  // A role may legitimately lack access to a panel; that must not look like a
  // failed sign-in. The auditor, for instance, can reach the log and nothing else.
  if (S.me.user.role === 'auditor') { S.resume = null; await openAudit(); return; }
  try { await loadPatients(); } catch (e) { S.patients = []; S.tags = []; }
  try { S.compliance = await api('/api/compliance'); } catch (e) { S.compliance = null; }
  S.view = 'home';
  if (await restoreAfterSignIn()) return;
  render();
}

boot();
