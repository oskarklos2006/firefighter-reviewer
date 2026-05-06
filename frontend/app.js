const API = '/api';
let currentSessionId = null;

/* ── Drag & Drop ── */
const uploadZone = document.getElementById('upload-zone');

// Clicking anywhere on the zone opens the file picker
uploadZone.addEventListener('click', () => {
  document.getElementById('file-input').click();
});

uploadZone.addEventListener('dragenter', (e) => {
  e.preventDefault();
  e.stopPropagation();
  uploadZone.classList.add('drag-over');
});

uploadZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  e.stopPropagation();
  uploadZone.classList.add('drag-over');
});

uploadZone.addEventListener('dragleave', (e) => {
  e.preventDefault();
  e.stopPropagation();
  if (!uploadZone.contains(e.relatedTarget)) {
    uploadZone.classList.remove('drag-over');
  }
});

uploadZone.addEventListener('drop', (e) => {
  e.preventDefault();
  e.stopPropagation();
  uploadZone.classList.remove('drag-over');

  const files = e.dataTransfer.files;
  if (!files.length) return;

  const file = files[0];
  if (!file.name.endsWith('.json')) {
    alert('Please drop a .json file.');
    return;
  }

  processFile(file);
});

/* ── File input change ── */
function handleFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  processFile(file);
}

/* ── Core processing ── */
async function processFile(file) {
  currentFile = file;
  document.getElementById('file-name').textContent = file.name;
  document.getElementById('loading').classList.add('visible');
  document.getElementById('result').classList.remove('visible');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch(`${API}/review`, { method: 'POST', body: formData });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Review failed');
    }
    const data = await response.json();
    renderResult(data);
    loadSessions();
  } catch (err) {
    alert('Error: ' + err.message);
  } finally {
    document.getElementById('loading').classList.remove('visible');
  }
}

/* ── Render result ── */
function renderResult(data) {
  currentSessionId = data.session_id;

  // Verdict
  const banner = document.getElementById('verdict-banner');
  banner.className = `verdict-banner verdict-${data.verdict}`;
  document.getElementById('verdict-label').textContent = data.verdict.replace(/_/g, ' ');

  const llmNote = data.confidence === 1.0
    ? '· deterministic only'
    : data.confidence === 0.5
      ? '· LLM unavailable'
      : '· LLM assisted';

  document.getElementById('verdict-meta').textContent =
    `${data.session_id}  ·  ${data.findings.length} finding(s)  ${llmNote}`;
  document.getElementById('confidence-val').textContent =
    Math.round(data.confidence * 100) + '%';

  // Findings
  const list = document.getElementById('findings-list');
  if (data.findings.length === 0) {
    list.innerHTML = `
      <div class="no-findings">
        <div class="no-findings-icon">✓</div>
        Session appears compliant — no findings detected.
      </div>`;
  } else {
    list.innerHTML = data.findings.map(f => `
      <div class="finding ${f.severity}">
        <div class="finding-header">
          <span class="badge badge-rule">${f.rule_id}</span>
          <span class="badge badge-${f.severity}">${f.severity}</span>
          <span class="location-tag">${f.location}</span>
        </div>
        <div class="finding-desc">${f.description}</div>
        <div class="finding-evidence">${f.evidence}</div>
      </div>`).join('');
  }

  // Correction
  const corrSection = document.getElementById('correction-section');
  if (data.suggested_correction) {
    corrSection.style.display = 'block';
    corrSection.style.marginBottom = '20px';
    document.getElementById('correction-message').textContent =
      data.suggested_correction.message_to_firefighter || '';
    const rewrite = document.getElementById('correction-rewrite');
    if (data.suggested_correction.suggested_reason_rewrite) {
      rewrite.style.display = 'block';
      rewrite.textContent = '✎ ' + data.suggested_correction.suggested_reason_rewrite;
    } else {
      rewrite.style.display = 'none';
    }
  } else {
    corrSection.style.display = 'none';
  }

  // Session info
  document.getElementById('session-info-content').innerHTML = `
    <div>ID &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <span style="color:var(--blue-bright)">${data.session_id}</span></div>
    <div>Verdict &nbsp;&nbsp; <span style="color:var(--off-white)">${data.verdict}</span></div>
    <div>Findings &nbsp; <span style="color:var(--off-white)">${data.findings.length}</span></div>
  `;

  // Show reanalyze button if LLM was not used
  const reanalyzeBtn = document.getElementById('reanalyze-btn');
  if (data.confidence === 1.0 || data.confidence === 0.5) {
    reanalyzeBtn.style.display = 'inline-flex';
  } else {
    reanalyzeBtn.style.display = 'none';
  }

  document.getElementById('decision-status').style.display = 'none';
  document.getElementById('result').classList.add('visible');
}

/* ── Controller decision ── */
async function recordDecision(decision) {
  if (!currentSessionId) return;
  try {
    const response = await fetch(`${API}/sessions/${currentSessionId}/decision`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision }),
    });
    if (response.ok) {
      const el = document.getElementById('decision-status');
      el.textContent = '✓ Recorded as ' + decision;
      el.style.display = 'inline-flex';
      loadSessions();
    }
  } catch (err) {
    alert('Failed to record decision');
  }
}

/* ── Session history ── */
async function loadSessions() {
  try {
    const response = await fetch(`${API}/sessions`);
    const sessions = await response.json();
    const tbody = document.getElementById('sessions-tbody');
    if (!sessions.length) {
      tbody.innerHTML = '<tr><td colspan="5"><div class="empty-state">No sessions reviewed yet</div></td></tr>';
      return;
    }
    tbody.innerHTML = sessions.map(s => `
      <tr>
        <td class="session-id-cell">${s.session_id}</td>
        <td><span class="pill pill-${s.verdict}">${s.verdict.replace(/_/g,' ')}</span></td>
        <td style="font-family:'JetBrains Mono',monospace;font-size:12px;">
          ${Math.round(s.confidence * 100)}%
        </td>
        <td style="color:var(--muted);font-size:12px;">${s.findings.length} finding(s)</td>
        <td>${s.controller_decision
          ? `<span class="pill pill-decided">${s.controller_decision}</span>`
          : '<span class="pending-text">pending</span>'
        }</td>
      </tr>`).join('');
  } catch (err) {
    console.error('Failed to load sessions', err);
  }
}

/* ── Reanalyze with LLM ── */
let currentFile = null;

async function reanalyze() {
  if (!currentFile) {
    alert('Please upload the session file again to re-analyze.');
    return;
  }

  document.getElementById('loading').classList.add('visible');
  document.getElementById('result').classList.remove('visible');

  const formData = new FormData();
  formData.append('file', currentFile);

  try {
    const response = await fetch(`${API}/review?force_llm=true`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Reanalysis failed');
    }
    const data = await response.json();
    renderResult(data);
    loadSessions();
  } catch (err) {
    alert('Error: ' + err.message);
  } finally {
    document.getElementById('loading').classList.remove('visible');
  }
}
/* ── Init ── */
loadSessions();


