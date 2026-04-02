/**
 * GrowthChart v2 — Main SPA Application
 * Handles: patient list, chart rendering, measurement table, dialogs
 */

// ══════════════════════════════════════════════════════════════
//  STATE
// ══════════════════════════════════════════════════════════════
let state = {
    patients: [],
    currentPatientId: null,
    currentPatient: null,
    measurements: [],
    indicator: 'hfa',
    standard: 'CDC',
    editingPatientId: null,
    mphCurveActive: false,
    mphCurveTrace: null,
};

// ══════════════════════════════════════════════════════════════
//  SIDEBAR TOGGLE (privacy mode)
// ══════════════════════════════════════════════════════════════
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('hidden');
    // Resize chart to fill space
    const chartDiv = document.getElementById('chart');
    if (chartDiv && chartDiv.data) {
        setTimeout(() => Plotly.Plots.resize(chartDiv), 50);
    }
}

// ══════════════════════════════════════════════════════════════
//  API HELPERS
// ══════════════════════════════════════════════════════════════
async function api(path, options = {}) {
    const url = `/api${path}`;
    const opts = { headers: { 'Content-Type': 'application/json' }, ...options };
    if (opts.body && typeof opts.body === 'object') opts.body = JSON.stringify(opts.body);
    const res = await fetch(url, opts);
    if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(err.error || res.statusText);
    }
    return res.json();
}

// ══════════════════════════════════════════════════════════════
//  PATIENT LIST
// ══════════════════════════════════════════════════════════════
async function loadPatients() {
    state.patients = await api('/patients');
    renderPatientList();
}

function renderPatientList(filter = '') {
    const container = document.getElementById('patient-list');
    let patients = state.patients;
    if (filter) {
        const q = filter.toLowerCase();
        patients = patients.filter(p =>
            (p.full_name || '').toLowerCase().includes(q) ||
            (p.medical_record_number || '').includes(q)
        );
    }

    if (!patients.length) {
        container.innerHTML = '<div class="text-center text-slate-400 text-sm py-8">No patients found</div>';
        return;
    }

    container.innerHTML = patients.map(p => {
        const isActive = p.id === state.currentPatientId;
        const sexIcon = p.sex === 'M' ? '♂' : '♀';
        const sexColor = p.sex === 'M' ? 'text-blue-500' : 'text-pink-500';
        return `
            <div class="patient-item ${isActive ? 'active' : ''}" onclick="selectPatient(${p.id})">
                <div class="flex items-center gap-2">
                    <span class="${sexColor} text-lg">${sexIcon}</span>
                    <div class="flex-1 min-w-0">
                        <div class="name truncate">${p.full_name || 'Unknown'}</div>
                        <div class="meta">${p.age_str || ''} ${p.medical_record_number ? '· ' + p.medical_record_number : ''}</div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// ══════════════════════════════════════════════════════════════
//  PATIENT SELECTION
// ══════════════════════════════════════════════════════════════
async function selectPatient(id) {
    state.currentPatientId = id;
    state.currentPatient = await api(`/patients/${id}`);
    renderPatientList();

    document.getElementById('empty-state').classList.add('hidden');
    document.getElementById('patient-view').classList.remove('hidden');

    // Update header
    document.getElementById('patient-name').textContent = state.currentPatient.full_name;
    const info = [];
    if (state.currentPatient.birth_date) {
        const d = new Date(state.currentPatient.birth_date);
        info.push(`DOB: ${d.toLocaleDateString('en-GB')}`);
    }
    if (state.currentPatient.age_str) info.push(`Age: ${state.currentPatient.age_str}`);
    info.push(state.currentPatient.sex === 'M' ? 'Male' : 'Female');
    if (state.currentPatient.medical_record_number) info.push(`ID: ${state.currentPatient.medical_record_number}`);
    document.getElementById('patient-info').textContent = info.join(' · ');

    // Syndrome info (Phase 16)
    const syndromeEl = document.getElementById('patient-syndrome-info');
    if (syndromeEl) {
        if (state.currentPatient.syndrome) {
            syndromeEl.textContent = `Syndrome: ${state.currentPatient.syndrome}`;
            syndromeEl.classList.remove('hidden');
        } else {
            syndromeEl.classList.add('hidden');
        }
    }

    // MPH info (Phase 12)
    const mphEl = document.getElementById('patient-mph-info');
    if (mphEl) {
        const mph = state.currentPatient.effective_mph;
        const thr = state.currentPatient.target_height_range;
        if (mph != null && thr) {
            mphEl.textContent = `MPH: ${mph} cm (Target: ${thr.low}–${thr.high} cm)`;
            mphEl.classList.remove('hidden');
        } else {
            mphEl.classList.add('hidden');
        }
    }

    await loadMeasurements();
    updateTabs();
    await renderChart();

    // CDS evaluation (Phase K)
    loadCdsAssessment(id);
}

// ══════════════════════════════════════════════════════════════
//  MEASUREMENTS
// ══════════════════════════════════════════════════════════════
async function loadMeasurements() {
    if (!state.currentPatientId) return;
    state.measurements = await api(`/patients/${state.currentPatientId}/measurements?standard=${state.standard}`);
    renderMeasurementTable();
    renderPubertyTable();
}

function _boneAgeFromForm(form) {
    const y = form.bone_age_y ? parseFloat(form.bone_age_y.value) : NaN;
    const m = form.bone_age_m ? parseFloat(form.bone_age_m.value) : 0;
    if (isNaN(y) && isNaN(m)) return null;
    return (isNaN(y) ? 0 : y) + (isNaN(m) ? 0 : m) / 12;
}

function fmtBoneAge(ba) {
    if (ba == null) return '—';
    const y = Math.floor(ba);
    const m = Math.round((ba - y) * 12);
    return m > 0 ? `${y}y ${m}m` : `${y}y`;
}

/** Parse DD/MM/YYYY (or YYYY-MM-DD) → ISO 'YYYY-MM-DD'. Returns null if invalid. */
function parseDateInput(str) {
    if (!str) return null;
    // Already ISO?
    if (/^\d{4}-\d{2}-\d{2}$/.test(str)) return str;
    const m = str.match(/(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})/);
    if (m) return `${m[3]}-${m[2].padStart(2,'0')}-${m[1].padStart(2,'0')}`;
    return null;
}

/** Format ISO date → DD/MM/YYYY for display (used in today's default too) */
function todayDDMMYYYY() {
    const d = new Date();
    return `${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')}/${d.getFullYear()}`;
}

function fmtDate(d) {
    if (!d) return '—';
    const dt = new Date(d);
    if (isNaN(dt)) return d;
    const dd = String(dt.getDate()).padStart(2, '0');
    const mm = String(dt.getMonth() + 1).padStart(2, '0');
    const yyyy = dt.getFullYear();
    return `${dd}/${mm}/${yyyy}`;
}

function zClass(z) {
    if (z === null || z === undefined) return '';
    const abs = Math.abs(z);
    if (abs >= 2) return 'z-severe';
    if (abs >= 1) return 'z-warning';
    return 'z-normal';
}

function fmtZ(z) {
    if (z === null || z === undefined) return '—';
    return (z >= 0 ? '+' : '') + z.toFixed(2);
}

function fmtPct(p) {
    if (p === null || p === undefined) return '—';
    return p.toFixed(1) + '%';
}

function renderMeasurementTable() {
    const tbody = document.getElementById('measurements-body');
    const count = document.getElementById('measurement-count');
    count.textContent = `${state.measurements.length} measurements`;

    if (!state.measurements.length) {
        tbody.innerHTML = '<tr><td colspan="14" class="px-4 py-6 text-center text-slate-400 text-sm">No measurements yet</td></tr>';
        return;
    }

    tbody.innerHTML = state.measurements.map(m => `
        <tr class="hover:bg-slate-50 transition" data-mid="${m.id}">
            <td class="px-3 py-2 text-left whitespace-nowrap editable" data-field="date" data-mid="${m.id}" onclick="inlineEdit(this, ${m.id}, 'date')">${fmtDate(m.date)}</td>
            <td class="px-3 py-2 text-left whitespace-nowrap text-slate-500">${m.age_str || '—'}</td>
            <td class="px-3 py-2 text-right font-mono editable" data-field="height_cm" onclick="inlineEdit(this, ${m.id}, 'height_cm')">${m.height_cm != null ? m.height_cm.toFixed(1) : '—'}</td>
            <td class="px-3 py-2 text-right font-mono editable" data-field="weight_kg" onclick="inlineEdit(this, ${m.id}, 'weight_kg')">${m.weight_kg != null ? m.weight_kg.toFixed(1) : '—'}</td>
            <td class="px-3 py-2 text-right font-mono">${m.bmi != null ? m.bmi.toFixed(1) : '—'}</td>
            <td class="px-3 py-2 text-right font-mono ${zClass(m.height_zscore)}">${fmtZ(m.height_zscore)}</td>
            <td class="px-3 py-2 text-right font-mono text-slate-500">${fmtPct(m.height_percentile)}</td>
            <td class="px-3 py-2 text-right font-mono ${zClass(m.weight_zscore)}">${fmtZ(m.weight_zscore)}</td>
            <td class="px-3 py-2 text-right font-mono text-slate-500">${fmtPct(m.weight_percentile)}</td>
            <td class="px-3 py-2 text-right font-mono ${zClass(m.bmi_zscore)}">${fmtZ(m.bmi_zscore)}</td>
            <td class="px-3 py-2 text-right font-mono text-slate-500">${fmtPct(m.bmi_percentile)}</td>
            <td class="px-3 py-2 text-right font-mono text-purple-600 editable" onclick="inlineEdit(this, ${m.id}, 'bone_age_years')">${m.bone_age_years != null ? fmtBoneAge(m.bone_age_years) : '—'}</td>
            <td class="px-3 py-2 text-right font-mono text-sky-600">${m.velocity != null ? m.velocity.toFixed(1) : '—'}</td>
            <td class="px-3 py-2 text-center whitespace-nowrap">
                <button onclick="deleteMeasurement(${m.id})" class="text-slate-400 hover:text-red-500 transition" title="Delete">✕</button>
            </td>
        </tr>
    `).join('');
}

function renderPubertyTable() {
    const panel = document.getElementById('puberty-panel');
    const header = document.getElementById('puberty-header');
    const tbody = document.getElementById('puberty-body');
    if (!panel || !state.currentPatient) { if (panel) panel.classList.add('hidden'); return; }

    const sex = state.currentPatient.sex;
    // Filter measurements that have any Tanner data
    const tannerRows = state.measurements.filter(m =>
        m.tanner_breast != null || m.tanner_pubic_hair != null ||
        m.tanner_genital != null || m.testicular_volume != null ||
        m.menarche_date != null
    );

    // Show panel if patient is old enough (>7y girls, >8y boys) OR has Tanner data
    const age = state.currentPatient.age_months ? state.currentPatient.age_months / 12 : 0;
    const showAge = sex === 'F' ? 7 : 8;
    if (tannerRows.length === 0 && age < showAge) { panel.classList.add('hidden'); return; }
    panel.classList.remove('hidden');

    // Build sex-appropriate headers
    if (sex === 'F') {
        header.innerHTML = `
            <th class="px-3 py-2 text-left">Date</th>
            <th class="px-3 py-2 text-left">Age</th>
            <th class="px-3 py-2 text-center">B</th>
            <th class="px-3 py-2 text-center">P</th>
            <th class="px-3 py-2 text-center">Menarche</th>
            <th class="px-3 py-2 w-8"></th>`;
    } else {
        header.innerHTML = `
            <th class="px-3 py-2 text-left">Date</th>
            <th class="px-3 py-2 text-left">Age</th>
            <th class="px-3 py-2 text-center">P</th>
            <th class="px-3 py-2 text-center">G</th>
            <th class="px-3 py-2 text-center">TV (mL)</th>
            <th class="px-3 py-2 w-8"></th>`;
    }

    if (tannerRows.length === 0) {
        const cols = 6;
        tbody.innerHTML = `<tr><td colspan="${cols}" class="px-4 py-3 text-center text-slate-400 text-sm">No Tanner staging recorded</td></tr>`;
        return;
    }

    tbody.innerHTML = tannerRows.map(m => {
        if (sex === 'F') {
            return `<tr class="hover:bg-slate-50">
                <td class="px-3 py-2 text-left">${fmtDate(m.date)}</td>
                <td class="px-3 py-2 text-left text-slate-500">${m.age_str || '—'}</td>
                <td class="px-3 py-2 text-center font-mono">${m.tanner_breast != null ? 'B' + m.tanner_breast : '—'}</td>
                <td class="px-3 py-2 text-center font-mono">${m.tanner_pubic_hair != null ? 'P' + m.tanner_pubic_hair : '—'}</td>
                <td class="px-3 py-2 text-center font-mono">${m.menarche_date ? fmtDate(m.menarche_date) : '—'}</td>
                <td class="px-3 py-2 text-center"><button onclick="editTanner(${m.id})" class="text-slate-400 hover:text-teal-600">✏️</button></td>
            </tr>`;
        } else {
            return `<tr class="hover:bg-slate-50">
                <td class="px-3 py-2 text-left">${fmtDate(m.date)}</td>
                <td class="px-3 py-2 text-left text-slate-500">${m.age_str || '—'}</td>
                <td class="px-3 py-2 text-center font-mono">${m.tanner_pubic_hair != null ? 'P' + m.tanner_pubic_hair : '—'}</td>
                <td class="px-3 py-2 text-center font-mono">${m.tanner_genital != null ? 'G' + m.tanner_genital : '—'}</td>
                <td class="px-3 py-2 text-center font-mono">${m.testicular_volume != null ? m.testicular_volume : '—'}</td>
                <td class="px-3 py-2 text-center"><button onclick="editTanner(${m.id})" class="text-slate-400 hover:text-teal-600">✏️</button></td>
            </tr>`;
        }
    }).join('');
}

async function addTannerEntry() {
    if (!state.currentPatientId) return;
    const sex = state.currentPatient.sex;
    const date = prompt('Date (DD/MM/YYYY):', todayDDMMYYYY());
    if (!date) return;

    const body = { date: parseDateInput(date) };
    if (sex === 'F') {
        const b = prompt('Breast stage (1-5):'); if (b) body.tanner_breast = parseInt(b);
        const p = prompt('Pubic hair stage (1-5):'); if (p) body.tanner_pubic_hair = parseInt(p);
    } else {
        const p = prompt('Pubic hair stage (1-5):'); if (p) body.tanner_pubic_hair = parseInt(p);
        const g = prompt('Genital stage (1-5):'); if (g) body.tanner_genital = parseInt(g);
        const tv = prompt('Testicular volume (mL):'); if (tv) body.testicular_volume = parseFloat(tv);
    }
    await api(`/patients/${state.currentPatientId}/measurements`, { method: 'POST', body: body });
    await loadMeasurements();
    await renderChart();
}

async function editTanner(mid) {
    const m = state.measurements.find(x => x.id === mid);
    if (!m) return;
    const sex = state.currentPatient.sex;
    const body = {};
    if (sex === 'F') {
        const b = prompt('Breast stage (1-5):', m.tanner_breast || ''); if (b !== null) body.tanner_breast = b ? parseInt(b) : null;
        const p = prompt('Pubic hair stage (1-5):', m.tanner_pubic_hair || ''); if (p !== null) body.tanner_pubic_hair = p ? parseInt(p) : null;
    } else {
        const p = prompt('Pubic hair stage (1-5):', m.tanner_pubic_hair || ''); if (p !== null) body.tanner_pubic_hair = p ? parseInt(p) : null;
        const g = prompt('Genital stage (1-5):', m.tanner_genital || ''); if (g !== null) body.tanner_genital = g ? parseInt(g) : null;
        const tv = prompt('Testicular volume (mL):', m.testicular_volume || ''); if (tv !== null) body.testicular_volume = tv ? parseFloat(tv) : null;
    }
    await api(`/measurements/${mid}?standard=${state.standard}`, { method: 'PUT', body: body });
    await loadMeasurements();
    await renderChart();
}

function inlineEdit(td, mid, field) {
    if (td.querySelector('input')) return; // already editing
    const m = state.measurements.find(x => x.id === mid);
    if (!m) return;

    const orig = td.textContent.trim();
    let val = '';
    let inputType = 'number';
    let step = '0.1';

    if (field === 'date') {
        val = m.date ? fmtDate(m.date) : '';
        inputType = 'text';
        step = '';
    } else if (field === 'height_cm') {
        val = m.height_cm != null ? m.height_cm : '';
    } else if (field === 'weight_kg') {
        val = m.weight_kg != null ? m.weight_kg : '';
    } else if (field === 'bone_age_years') {
        val = m.bone_age_years != null ? m.bone_age_years : '';
        step = '0.1';
    }

    const input = document.createElement('input');
    input.type = 'text';
    if (field !== 'date') input.inputMode = 'decimal';
    input.value = val;
    if (field === 'date') input.placeholder = 'DD/MM/YYYY';
    input.className = 'px-1 py-0.5 text-sm border border-teal-400 rounded focus:outline-none font-mono';
    input.style.width = field === 'date' ? '100px' : '70px';
    if (field !== 'date') input.style.textAlign = 'right';

    td.textContent = '';
    td.appendChild(input);
    // Delay focus to avoid click-through issues
    setTimeout(() => { input.focus(); input.select(); }, 10);

    let saving = false;
    async function save() {
        if (saving || cancelled) return;
        saving = true;
        const newVal = input.value.trim();
        if (newVal === '' && field !== 'date') {
            // Empty = no change, revert
            td.textContent = orig;
            return;
        }
        let body = {};

        if (field === 'date') {
            // Parse DD/MM/YYYY to ISO YYYY-MM-DD
            const parts = newVal.match(/(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})/);
            body.date = parts ? `${parts[3]}-${parts[2].padStart(2,'0')}-${parts[1].padStart(2,'0')}` : m.date;
        } else if (field === 'bone_age_years') {
            body.bone_age_years = newVal ? parseFloat(newVal) : null;
        } else {
            body[field] = newVal ? parseFloat(newVal) : null;
        }

        try {
            const res = await fetch(`/api/measurements/${mid}?standard=${state.standard}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ error: res.statusText }));
                throw new Error(err.error || `HTTP ${res.status}`);
            }
            await loadMeasurements();
            await renderChart();
        } catch (e) {
            console.error('Inline edit save failed:', e);
            alert('Edit failed: ' + e.message);
            td.textContent = orig;
        }
    }

    let cancelled = false;
    input.addEventListener('blur', () => { if (!cancelled) save(); });
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
        if (e.key === 'Tab') { e.preventDefault(); input.blur(); }
        if (e.key === 'Escape') { cancelled = true; td.textContent = orig; }
    });
}

// ══════════════════════════════════════════════════════════════
//  CHART RENDERING (Plotly)
// ══════════════════════════════════════════════════════════════
async function renderChart() {
    if (!state.currentPatient) return;

    // Handle velocity chart separately
    if (state.indicator === 'velocity') {
        await renderVelocityChart();
        return;
    }

    const sex = state.currentPatient.sex;
    const syndrome = state.currentPatient.syndrome || '';

    // Always show full reference data range: 0 to end of standard
    // CDC goes to 240 months (20y), WHO goes to 228 months (19y)
    let ageMin = 0;
    let ageMax = state.standard === 'CDC' ? 240 : 228;

    // Build percentile URL with optional syndrome param
    let percUrl = `/charts/percentiles?indicator=${state.indicator}&standard=${state.standard}&sex=${sex}&age_min=${ageMin}&age_max=${ageMax}`;
    if (syndrome) {
        percUrl += `&syndrome=${encodeURIComponent(syndrome)}`;
    }

    // Fetch percentile curves and patient data in parallel
    const [percData, patData] = await Promise.all([
        api(percUrl),
        api(`/charts/patient-data?patient_id=${state.currentPatientId}&indicator=${state.indicator}&standard=${state.standard}`),
    ]);

    // Build traces: bands first (background), then percentile lines, then patient data
    const traces = [];

    // Colored bands between percentiles
    for (const band of percData.bands) {
        traces.push(band);
    }

    // Percentile line traces
    for (const trace of percData.traces) {
        traces.push(trace);
    }

    // Syndromic curves (Phase 16) — dashed purple
    if (percData.syndromic_traces && percData.syndromic_traces.length > 0) {
        for (const st of percData.syndromic_traces) {
            traces.push(st);
        }
    }

    // BMI obesity grade lines (120%/140% of P95)
    if (percData.obesity_traces && percData.obesity_traces.length > 0) {
        for (const ot of percData.obesity_traces) {
            traces.push(ot);
        }
    }

    // Patient data trace
    if (patData.trace && patData.trace.x.length > 0) {
        traces.push(patData.trace);
    }

    // Bone age trace
    if (patData.bone_age_trace && patData.bone_age_trace.x.length > 0) {
        traces.push(patData.bone_age_trace);
    }

    // PAH trace (Bayley-Pinneau predicted adult height — Phase 14)
    if (patData.pah_trace && patData.pah_trace.x.length > 0) {
        traces.push(patData.pah_trace);
    }

    // Title
    const nameDisplay = patData.patient_name || '';
    const sexLabel = patData.sex_label || '';
    const indLabel = patData.indicator_label || '';
    let title = `${nameDisplay}  |  ${indLabel} · ${sexLabel} · ${state.standard}`;
    if (syndrome) title += ` · ${syndrome}`;
    const dob = patData.birth_date ? `DOB: ${new Date(patData.birth_date).toLocaleDateString('en-GB')}` : '';

    // Layout
    const layout = {
        ...percData.layout,
        title: {
            text: title,
            font: { size: 14, color: '#475569' },
            x: 0.5,
        },
        annotations: dob ? [{
            text: dob,
            xref: 'paper', yref: 'paper',
            x: 1, y: 1.06,
            showarrow: false,
            font: { size: 10, color: '#94A3B8' },
        }] : [],
        showlegend: false,
        shapes: [],
    };

    // MPH target height band + right-edge marker (Phase 12)
    if (patData.target_height_shape) {
        layout.shapes.push(patData.target_height_shape);
    }
    if (patData.mph_annotation) {
        layout.annotations.push(patData.mph_annotation);
    }
    if (patData.mph) {
        const mph = patData.mph;
        // MPH exact marker on right edge of chart
        layout.annotations.push({
            x: 1.01, xref: 'paper',
            y: mph.mph, yref: 'y',
            text: `◆ MPH ${mph.mph.toFixed(1)}`,
            showarrow: false,
            font: { size: 10, color: '#6B7280', family: 'Arial' },
            bgcolor: 'rgba(255,255,255,0.9)',
            bordercolor: '#6B7280',
            borderwidth: 1,
            borderpad: 3,
            xanchor: 'left',
        });
        // Range low marker
        layout.annotations.push({
            x: 1.01, xref: 'paper',
            y: mph.range_low, yref: 'y',
            text: `${mph.range_low.toFixed(1)}`,
            showarrow: false,
            font: { size: 8, color: '#6B7280' },
            xanchor: 'left',
        });
        // Range high marker
        layout.annotations.push({
            x: 1.01, xref: 'paper',
            y: mph.range_high, yref: 'y',
            text: `${mph.range_high.toFixed(1)}`,
            showarrow: false,
            font: { size: 8, color: '#6B7280' },
            xanchor: 'left',
        });
        // Horizontal dashed line at MPH across the chart
        layout.shapes.push({
            type: 'line',
            x0: 0, x1: 1, xref: 'paper',
            y0: mph.mph, y1: mph.mph, yref: 'y',
            line: { color: '#6B7280', width: 1, dash: 'dot' },
        });
    }

    // ── MPH percentile curve (when toggled on and indicator is hfa) ──
    if (state.mphCurveActive && state.indicator === 'hfa' && state.mphCurveTrace) {
        traces.push(state.mphCurveTrace);
    }

    // ── GH therapy start line (vertical dotted line) ──
    if (patData.gh_line) {
        const ghAge = patData.gh_line.age_years;
        // Vertical dashed line from bottom to the growth curve
        layout.shapes.push({
            type: 'line',
            x0: ghAge, x1: ghAge,
            y0: 0, y1: 1,
            yref: 'paper',
            line: { color: '#7C3AED', width: 1.5, dash: 'dashdot' },
        });
        // Label "GH" at the bottom of the line
        layout.annotations.push({
            x: ghAge, y: 0, yref: 'paper',
            text: '⬆ GH',
            showarrow: false,
            font: { size: 10, color: '#7C3AED', family: 'Arial Black' },
            yanchor: 'top',
            yshift: 10,
        });
    }

    const config = {
        responsive: true,
        displayModeBar: true,
        modeBarButtonsToRemove: ['lasso2d', 'select2d'],
        displaylogo: false,
        scrollZoom: false,
        doubleClick: 'reset+autosize',
    };

    Plotly.react('chart', traces, layout, config);

    // Show/hide MPH button based on whether we have MPH data + height chart
    updateMphButton();
}

// ══════════════════════════════════════════════════════════════
//  VELOCITY CHART (Phase 15)
// ══════════════════════════════════════════════════════════════
async function renderVelocityChart() {
    if (!state.currentPatient) return;

    const velData = await api(`/charts/velocity?patient_id=${state.currentPatientId}&standard=${state.standard}`);

    if (!velData.traces || velData.traces.length === 0) {
        // Show empty chart with message
        Plotly.react('chart', [], {
            title: {
                text: velData.message || 'Need at least 2 height measurements for velocity chart',
                font: { size: 14, color: '#94A3B8' },
            },
            paper_bgcolor: '#FAFBFC',
            plot_bgcolor: '#FFFFFF',
        }, { responsive: true, displaylogo: false });
        return;
    }

    const traces = velData.traces;

    const nameDisplay = velData.patient_name || '';
    const sexLabel = velData.sex_label || '';
    const title = `${nameDisplay}  |  Height Velocity · ${sexLabel} · ${state.standard}`;

    const layout = {
        ...velData.layout,
        title: {
            text: title,
            font: { size: 14, color: '#475569' },
            x: 0.5,
        },
    };

    const config = {
        responsive: true,
        displayModeBar: true,
        modeBarButtonsToRemove: ['lasso2d', 'select2d'],
        displaylogo: false,
        scrollZoom: false,
        doubleClick: 'reset+autosize',
    };

    Plotly.react('chart', traces, layout, config);
}

function resetZoom() {
    Plotly.relayout('chart', {
        'xaxis.autorange': true,
        'yaxis.autorange': true,
    });
}

// ══════════════════════════════════════════════════════════════
//  INDICATOR & STANDARD TOGGLES
// ══════════════════════════════════════════════════════════════
function setIndicator(ind) {
    state.indicator = ind;
    updateTabs();
    // Velocity chart doesn't need measurement reload (uses its own endpoint)
    if (ind === 'velocity') {
        renderChart();
    } else {
        loadMeasurements().then(() => renderChart());
    }
}

async function setStandard(std) {
    state.standard = std;
    updateTabs();
    // Refetch MPH curve for new standard if active
    if (state.mphCurveActive && state.currentPatient && state.currentPatient.effective_mph) {
        try {
            const data = await api(
                `/charts/mph-curve?mph=${state.currentPatient.effective_mph}&standard=${std}&sex=${state.currentPatient.sex}`
            );
            state.mphCurveTrace = data.trace || null;
        } catch (e) { state.mphCurveTrace = null; }
    }
    await loadMeasurements();
    await renderChart();
}

function updateTabs() {
    // Indicator tabs
    document.querySelectorAll('.indicator-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.ind === state.indicator);
    });
    // Standard buttons
    document.querySelectorAll('.standard-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.std === state.standard);
    });
}

// ══════════════════════════════════════════════════════════════
//  DIALOGS
// ══════════════════════════════════════════════════════════════
function showDialog(id) {
    document.getElementById(id).classList.remove('hidden');
}

function closeDialog(id) {
    document.getElementById(id).classList.add('hidden');
}

function showNewPatientDialog() {
    state.editingPatientId = null;
    document.getElementById('patient-dialog-title').textContent = 'New Patient';
    document.getElementById('patient-form').reset();
    showDialog('patient-dialog');
}

function editPatient() {
    if (!state.currentPatient) return;
    state.editingPatientId = state.currentPatient.id;
    document.getElementById('patient-dialog-title').textContent = 'Edit Patient';
    const form = document.getElementById('patient-form');
    form.first_name.value = state.currentPatient.first_name || '';
    form.last_name.value = state.currentPatient.last_name || '';
    form.birth_date.value = state.currentPatient.birth_date ? fmtDate(state.currentPatient.birth_date) : '';
    form.sex.value = state.currentPatient.sex || 'M';
    form.medical_record_number.value = state.currentPatient.medical_record_number || '';
    // Phase 12-16 fields
    if (form.mother_height_cm) form.mother_height_cm.value = state.currentPatient.mother_height_cm || '';
    if (form.father_height_cm) form.father_height_cm.value = state.currentPatient.father_height_cm || '';
    if (form.mph_cm) {
        form.mph_cm.value = state.currentPatient.effective_mph || '';
    }
    if (form.mph_user_edited) form.mph_user_edited.value = state.currentPatient.mph_user_edited ? '1' : '0';
    if (form.syndrome) form.syndrome.value = state.currentPatient.syndrome || '';
    if (form.gh_start_date) form.gh_start_date.value = state.currentPatient.gh_start_date ? fmtDate(state.currentPatient.gh_start_date) : '';
    showDialog('patient-dialog');
}

async function savePatient(e) {
    e.preventDefault();
    const form = e.target;
    const data = {
        first_name: form.first_name.value,
        last_name: form.last_name.value,
        birth_date: parseDateInput(form.birth_date.value),
        sex: form.sex.value,
        medical_record_number: form.medical_record_number.value,
        // Phase 12-16 fields
        mother_height_cm: form.mother_height_cm ? (form.mother_height_cm.value || null) : null,
        father_height_cm: form.father_height_cm ? (form.father_height_cm.value || null) : null,
        mph_cm: form.mph_cm ? (form.mph_cm.value || null) : null,
        mph_user_edited: form.mph_user_edited ? (form.mph_user_edited.value === '1') : false,
        syndrome: form.syndrome ? form.syndrome.value : '',
        gh_start_date: form.gh_start_date ? parseDateInput(form.gh_start_date.value) : null,
    };

    if (state.editingPatientId) {
        await api(`/patients/${state.editingPatientId}`, { method: 'PUT', body: data });
    } else {
        const created = await api('/patients', { method: 'POST', body: data });
        state.currentPatientId = created.id;
    }

    closeDialog('patient-dialog');
    await loadPatients();
    if (state.currentPatientId) await selectPatient(state.currentPatientId);
}

function addMeasurement() {
    const form = document.getElementById('measurement-form');
    form.reset();
    // Default to today
    form.date.value = todayDDMMYYYY();
    showDialog('measurement-dialog');
}

async function saveMeasurement(e) {
    e.preventDefault();
    const form = e.target;
    const data = {
        date: parseDateInput(form.date.value),
        height_cm: form.height_cm.value ? parseFloat(form.height_cm.value) : null,
        weight_kg: form.weight_kg.value ? parseFloat(form.weight_kg.value) : null,
        bone_age_years: _boneAgeFromForm(form),
    };

    await api(`/patients/${state.currentPatientId}/measurements`, { method: 'POST', body: data });
    closeDialog('measurement-dialog');
    await loadMeasurements();
    await renderChart();
}

async function editMeasurement(id) {
    const m = state.measurements.find(m => m.id === id);
    if (!m) return;

    const dateStr = prompt('Date (DD/MM/YYYY):', m.date ? fmtDate(m.date) : '');
    if (dateStr === null) return;

    // Parse DD/MM/YYYY to YYYY-MM-DD
    let isoDate = m.date;
    if (dateStr) {
        const parts = dateStr.match(/(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})/);
        if (parts) {
            isoDate = `${parts[3]}-${parts[2].padStart(2,'0')}-${parts[1].padStart(2,'0')}`;
        }
    }

    const ht = prompt('Height (cm):', m.height_cm || '');
    const wt = prompt('Weight (kg):', m.weight_kg || '');
    const baStr = prompt('Bone age (e.g. "12y 6m" or "12.5", leave empty if none):', m.bone_age_years != null ? fmtBoneAge(m.bone_age_years) : '');
    let baVal = null;
    if (baStr) {
        const ym = baStr.match(/(\d+)\s*y\s*(\d+)\s*m/i);
        if (ym) { baVal = parseInt(ym[1]) + parseInt(ym[2]) / 12; }
        else { baVal = parseFloat(baStr); }
    }

    await api(`/measurements/${id}?standard=${state.standard}`, {
        method: 'PUT',
        body: {
            date: isoDate,
            height_cm: ht ? parseFloat(ht) : null,
            weight_kg: wt ? parseFloat(wt) : null,
            bone_age_years: baVal,
        },
    });

    await loadMeasurements();
    await renderChart();
}

async function deleteMeasurement(id) {
    await api(`/measurements/${id}`, { method: 'DELETE' });
    await loadMeasurements();
    await renderChart();
}

// ══════════════════════════════════════════════════════════════
//  MPH HELPERS (Phase 12)
// ══════════════════════════════════════════════════════════════
function updateMphPreview() {
    const form = document.getElementById('patient-form');
    if (!form || !form.mother_height_cm || !form.father_height_cm || !form.mph_cm) return;

    const mother = parseFloat(form.mother_height_cm.value);
    const father = parseFloat(form.father_height_cm.value);
    if (isNaN(mother) || isNaN(father)) return;

    // Only auto-fill if user hasn't manually edited MPH
    if (form.mph_user_edited.value === '0') {
        const sex = form.sex.value;
        const mph = sex === 'M'
            ? (father + mother + 13) / 2
            : (father + mother - 13) / 2;
        form.mph_cm.value = mph.toFixed(1);
    }
}

function markMphEdited() {
    const form = document.getElementById('patient-form');
    if (form && form.mph_user_edited) {
        form.mph_user_edited.value = '1';
    }
}

// ── MPH Percentile Curve Toggle ──────────────────────────────
function updateMphButton() {
    const btn = document.getElementById('mph-curve-btn');
    if (!btn) return;

    const hasMph = state.currentPatient && state.currentPatient.effective_mph;
    const isHeight = state.indicator === 'hfa';

    if (hasMph && isHeight) {
        btn.classList.remove('hidden');
        // Active state styling
        if (state.mphCurveActive) {
            btn.classList.add('bg-green-100', 'text-green-800', 'border-green-400');
            btn.classList.remove('bg-white', 'text-slate-600');
        } else {
            btn.classList.remove('bg-green-100', 'text-green-800', 'border-green-400');
            btn.classList.add('bg-white', 'text-slate-600');
        }
    } else {
        btn.classList.add('hidden');
    }
}

async function toggleMphCurve() {
    const chartDiv = document.getElementById('chart');
    state.mphCurveActive = !state.mphCurveActive;

    if (state.mphCurveActive && state.currentPatient && state.currentPatient.effective_mph) {
        // Fetch the MPH percentile curve from the API
        try {
            const mph = state.currentPatient.effective_mph;
            const sex = state.currentPatient.sex;
            const data = await api(
                `/charts/mph-curve?mph=${mph}&standard=${state.standard}&sex=${sex}`
            );
            if (data.trace) {
                state.mphCurveTrace = data.trace;
                // Add trace and preserve current zoom range
                if (chartDiv && chartDiv.data) {
                    const xRange = chartDiv.layout.xaxis.range ? [...chartDiv.layout.xaxis.range] : null;
                    const yRange = chartDiv.layout.yaxis.range ? [...chartDiv.layout.yaxis.range] : null;
                    Plotly.addTraces(chartDiv, [data.trace]);
                    if (xRange && yRange) {
                        Plotly.relayout(chartDiv, {'xaxis.range': xRange, 'yaxis.range': yRange});
                    }
                    return;
                }
            }
        } catch (e) {
            console.error('Failed to fetch MPH curve:', e);
            state.mphCurveActive = false;
            state.mphCurveTrace = null;
        }
    } else {
        state.mphCurveTrace = null;
        // Remove the last trace (MPH curve) without resetting zoom
        if (chartDiv && chartDiv.data && chartDiv.data.length > 0) {
            // Find and remove the MPH trace by name
            for (let i = chartDiv.data.length - 1; i >= 0; i--) {
                if (chartDiv.data[i].name && chartDiv.data[i].name.includes('MPH')) {
                    Plotly.deleteTraces(chartDiv, [i]);
                    return;
                }
            }
        }
    }

    await renderChart();
}

// ══════════════════════════════════════════════════════════════
//  EXPORT
// ══════════════════════════════════════════════════════════════
function exportElysiaPdf() {
    if (!state.currentPatientId) return;
    window.open(`/api/export/elysia/${state.currentPatientId}?standard=${state.standard}`, '_blank');
}

function exportChartPng() {
    if (!state.currentPatientId) return;
    window.open(`/api/export/chart-png?patient_id=${state.currentPatientId}&indicator=${state.indicator}&standard=${state.standard}`, '_blank');
}

// ══════════════════════════════════════════════════════════════
//  SETTINGS
// ══════════════════════════════════════════════════════════════
async function loadSettings() {
    try {
        const settings = await api('/settings');
        if (settings.font_size) {
            document.documentElement.style.setProperty('--app-font-size', settings.font_size + 'px');
        }
        if (settings.default_standard) {
            state.standard = settings.default_standard;
        }
        if (settings.date_format) {
            state.dateFormat = settings.date_format;
        }
    } catch (e) {
        // Settings endpoint may not exist yet; use defaults
        console.log('Settings not loaded:', e.message);
    }
}

function showSettingsDialog() {
    const fontSlider = document.getElementById('settings-font-size');
    const fontValue = document.getElementById('font-size-value');
    const stdSelect = document.getElementById('settings-default-standard');

    if (fontSlider && fontValue) {
        const currentSize = getComputedStyle(document.documentElement)
            .getPropertyValue('--app-font-size') || '16px';
        fontSlider.value = parseInt(currentSize);
        fontValue.textContent = fontSlider.value + 'px';
    }
    if (stdSelect) {
        stdSelect.value = state.standard;
    }
    showDialog('settings-dialog');
}

async function saveSettings(e) {
    e.preventDefault();
    const fontSlider = document.getElementById('settings-font-size');
    const stdSelect = document.getElementById('settings-default-standard');

    const data = {
        font_size: parseInt(fontSlider.value),
        default_standard: stdSelect.value,
    };

    try {
        await api('/settings', { method: 'PUT', body: data });
        document.documentElement.style.setProperty('--app-font-size', data.font_size + 'px');
        state.standard = data.default_standard;
        updateTabs();
        closeDialog('settings-dialog');
    } catch (e) {
        alert('Failed to save settings: ' + e.message);
    }
}

// ══════════════════════════════════════════════════════════════
//  IMPORT SYSTEM
// ══════════════════════════════════════════════════════════════
let importState = { extractedData: null, selectedFiles: [] };

function showImportDialog() {
    importState = { extractedData: null, selectedFiles: [] };
    document.getElementById('import-status').classList.add('hidden');
    document.getElementById('import-confirm-btn').classList.add('hidden');
    document.getElementById('import-upload-area').classList.remove('hidden');
    document.getElementById('import-file-input').value = '';

    // Populate patient dropdown
    const sel = document.getElementById('import-patient-select');
    sel.innerHTML = '<option value="">Auto-detect from file</option>';
    for (const p of state.patients) {
        sel.innerHTML += `<option value="${p.id}">${p.full_name} (${p.age_str})</option>`;
    }

    showDialog('import-dialog');
}

function closeImportDialog() {
    closeDialog('import-dialog');
}

function handlePasteEvent(e) {
    e.preventDefault(); e.stopPropagation();
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
        if (item.type.startsWith('image/')) {
            const blob = item.getAsFile();
            if (blob) { handleFileSelect([blob]); return; }
        }
    }
    // Text fallback
    const text = e.clipboardData.getData('text/plain');
    if (text && text.trim()) {
        const file = new File([text], 'clipboard-paste.csv', { type: 'text/csv' });
        handleFileSelect([file]);
    }
}

async function pasteFromClipboard() {
    try {
        const items = await navigator.clipboard.read();
        for (const item of items) {
            // Check for image (screenshot)
            const imgType = item.types.find(t => t.startsWith('image/'));
            if (imgType) {
                const blob = await item.getType(imgType);
                const file = new File([blob], 'clipboard-screenshot.png', { type: imgType });
                handleFileSelect([file]);
                return;
            }
            // Check for text (tabular data, pasted from Excel/table)
            if (item.types.includes('text/plain')) {
                const blob = await item.getType('text/plain');
                const text = await blob.text();
                if (text.trim()) {
                    const file = new File([text], 'clipboard-paste.csv', { type: 'text/csv' });
                    handleFileSelect([file]);
                    return;
                }
            }
        }
        alert('No image or text data found in clipboard. Copy a screenshot or table first.');
    } catch (e) {
        // Fallback: try readText for older browsers
        try {
            const text = await navigator.clipboard.readText();
            if (text && text.trim()) {
                const file = new File([text], 'clipboard-paste.csv', { type: 'text/csv' });
                handleFileSelect([file]);
                return;
            }
        } catch (e2) { /* ignore */ }
        alert('Clipboard access denied. Please allow clipboard permissions or use Ctrl+V in the upload area.');
    }
}

function handleFileDrop(e) {
    e.preventDefault();
    e.currentTarget.classList.remove('border-teal-400', 'bg-teal-50');
    if (e.dataTransfer.files.length) handleFileSelect(e.dataTransfer.files);
}

async function handleFileSelect(files) {
    if (!files || !files.length) return;
    importState.selectedFiles = files;

    const statusDiv = document.getElementById('import-status');
    const progressDiv = document.getElementById('import-progress');
    statusDiv.classList.remove('hidden');
    progressDiv.innerHTML = `<span class="text-teal-600">⏳ Processing ${files.length} file(s)...</span>`;

    // Hide upload area, show processing
    document.getElementById('import-upload-area').classList.add('hidden');

    try {
        if (files.length === 1) {
            await processSingleFile(files[0]);
        } else {
            await processMultipleFiles(files);
        }
    } catch (err) {
        progressDiv.innerHTML = `<span class="text-red-600">❌ Error: ${err.message}</span>`;
        document.getElementById('import-upload-area').classList.remove('hidden');
    }
}

async function processSingleFile(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    const formData = new FormData();
    formData.append('file', file);

    const assignTo = document.getElementById('import-patient-select').value;
    if (assignTo && state.patients.find(p => p.id == assignTo)) {
        const p = state.patients.find(p => p.id == assignTo);
        if (p.birth_date) formData.append('patient_birth_date', p.birth_date);
    }

    let result;
    const imageExts = ['jpg', 'jpeg', 'png', 'bmp', 'tiff', 'tif'];
    if (ext === 'pdf') {
        const resp = await fetch('/api/import/pdf', { method: 'POST', body: formData });
        result = await resp.json();
    } else if (imageExts.includes(ext)) {
        const resp = await fetch('/api/import/image', { method: 'POST', body: formData });
        result = await resp.json();
    } else if (['xlsx', 'xls', 'csv', 'tsv'].includes(ext)) {
        const resp = await fetch('/api/import/excel', { method: 'POST', body: formData });
        result = await resp.json();
    } else {
        throw new Error(`Unsupported file type: .${ext}`);
    }

    if (!result.success && result.error) throw new Error(result.error);

    importState.extractedData = result;
    displayImportPreview(result, ext);
}

async function processMultipleFiles(files) {
    const formData = new FormData();
    for (const f of files) formData.append('files', f);

    const assignTo = document.getElementById('import-patient-select').value;
    formData.append('mode', assignTo ? 'same_patient' : 'auto_detect');
    if (assignTo) formData.append('patient_id', assignTo);

    const resp = await fetch('/api/import/folder', { method: 'POST', body: formData });
    const result = await resp.json();
    if (!result.success && result.error) throw new Error(result.error);

    importState.extractedData = result;
    displayBatchPreview(result);
}

function displayImportPreview(data, ext) {
    const progressDiv = document.getElementById('import-progress');
    progressDiv.innerHTML = `<span class="text-green-600">✅ File processed successfully</span>`;

    // Patient info
    if (data.patient && (data.patient.first_name || data.patient.last_name)) {
        const pi = document.getElementById('import-patient-info');
        const pd = document.getElementById('import-patient-details');
        pi.classList.remove('hidden');
        const p = data.patient;
        pd.innerHTML = `
            <div dir="rtl"><strong>${p.first_name || ''} ${p.last_name || ''}</strong></div>
            ${p.birth_date ? `<div>DOB: ${p.birth_date}</div>` : ''}
            ${p.sex ? `<div>Sex: ${p.sex === 'M' ? 'Male' : 'Female'}</div>` : ''}
            ${p.medical_record_number ? `<div>ID: ${p.medical_record_number}</div>` : ''}
        `;
    }

    // Measurements
    const measurements = data.measurements || data.preview_rows || [];
    if (measurements.length) {
        document.getElementById('import-measurements-preview').classList.remove('hidden');
        const tbody = document.getElementById('import-measurements-body');
        tbody.innerHTML = measurements.map((m, i) => `
            <tr class="hover:bg-slate-50">
                <td class="px-2 py-1"><input type="checkbox" checked data-idx="${i}" class="import-check"></td>
                <td class="px-2 py-1">${fmtDate(m.date)}</td>
                <td class="px-2 py-1 text-right">${m.height_cm != null ? m.height_cm : '—'}</td>
                <td class="px-2 py-1 text-right">${m.weight_kg != null ? m.weight_kg : '—'}</td>
                <td class="px-2 py-1 text-right">${m.confidence != null ? (m.confidence * 100).toFixed(0) + '%' : '—'}</td>
            </tr>
        `).join('');
    }

    // Parental heights
    if (data.parental_heights) {
        const ph = data.parental_heights;
        if (ph.father_height_cm || ph.mother_height_cm || ph.mph_from_letter) {
            const div = document.getElementById('import-parental-info');
            div.classList.remove('hidden');
            const details = document.getElementById('import-parental-details');
            const parts = [];
            if (ph.father_height_cm) parts.push(`Father: ${ph.father_height_cm} cm`);
            if (ph.mother_height_cm) parts.push(`Mother: ${ph.mother_height_cm} cm`);
            if (ph.mph_from_letter) parts.push(`MPH (from letter): ${ph.mph_from_letter} cm`);
            details.innerHTML = parts.join(' · ');
        }
    }

    // Warnings
    if (data.warnings && data.warnings.length) {
        const wd = document.getElementById('import-warnings');
        wd.classList.remove('hidden');
        document.getElementById('import-warnings-list').innerHTML =
            data.warnings.map(w => `<div>⚠️ ${w}</div>`).join('');
    }

    document.getElementById('import-confirm-btn').classList.remove('hidden');
}

function displayBatchPreview(data) {
    const progressDiv = document.getElementById('import-progress');
    const groups = data.groups || [];
    const total = data.total_measurements || 0;
    progressDiv.innerHTML = `<span class="text-green-600">✅ ${data.total_files || 0} files → ${groups.length} patient(s), ${total} measurements</span>`;

    if (groups.length) {
        document.getElementById('import-measurements-preview').classList.remove('hidden');
        const tbody = document.getElementById('import-measurements-body');
        let rows = '';
        for (const g of groups) {
            for (const m of (g.measurements || [])) {
                rows += `<tr class="hover:bg-slate-50">
                    <td class="px-2 py-1"><input type="checkbox" checked class="import-check"></td>
                    <td class="px-2 py-1">${fmtDate(m.date)}</td>
                    <td class="px-2 py-1 text-right">${m.height_cm != null ? m.height_cm : '—'}</td>
                    <td class="px-2 py-1 text-right">${m.weight_kg != null ? m.weight_kg : '—'}</td>
                    <td class="px-2 py-1 text-right">—</td>
                </tr>`;
            }
        }
        tbody.innerHTML = rows || '<tr><td colspan="5" class="text-center py-2 text-slate-400">No measurements extracted</td></tr>';
    }

    document.getElementById('import-confirm-btn').classList.remove('hidden');
}

async function confirmImport() {
    const data = importState.extractedData;
    if (!data) return;

    // Gather checked measurements
    const checks = document.querySelectorAll('.import-check');
    const measurements = (data.measurements || data.preview_rows || [])
        .filter((m, i) => !checks[i] || checks[i].checked);

    const assignTo = document.getElementById('import-patient-select').value;

    const body = {
        patient: assignTo
            ? { id: parseInt(assignTo), ...(data.patient || {}) }
            : (data.patient || {}),
        measurements: measurements,
        match_action: assignTo ? 'merge' : 'new_patient',
    };

    // Add parental heights to patient if extracted
    if (data.parental_heights) {
        const ph = data.parental_heights;
        if (ph.father_height_cm) body.patient.father_height_cm = ph.father_height_cm;
        if (ph.mother_height_cm) body.patient.mother_height_cm = ph.mother_height_cm;
        if (ph.mph_from_letter) body.patient.mph_cm = ph.mph_from_letter;
    }

    // Add Tanner staging data to measurements if extracted
    if (data.tanner_staging) {
        const ts = data.tanner_staging;
        // Apply to the most recent measurement (or all if only one)
        const target = body.measurements.length > 0 ? body.measurements[body.measurements.length - 1] : null;
        if (target) {
            if (ts.tanner_breast != null) target.tanner_breast = ts.tanner_breast;
            if (ts.tanner_pubic_hair != null) target.tanner_pubic_hair = ts.tanner_pubic_hair;
            if (ts.tanner_genital != null) target.tanner_genital = ts.tanner_genital;
            if (ts.testicular_volume != null) target.testicular_volume = ts.testicular_volume;
        }
    }

    try {
        const result = await api('/import/confirm', { method: 'POST', body: body });
        closeImportDialog();
        await loadPatients();
        if (result.patient_id) await selectPatient(result.patient_id);
    } catch (err) {
        document.getElementById('import-progress').innerHTML =
            `<span class="text-red-600">❌ Import failed: ${err.message}</span>`;
    }
}

// ══════════════════════════════════════════════════════════════
//  HELP
// ══════════════════════════════════════════════════════════════
function showHelpDialog() {
    showDialog('help-dialog');
}

// ══════════════════════════════════════════════════════════════
//  SEARCH
// ══════════════════════════════════════════════════════════════
document.getElementById('search-input').addEventListener('input', (e) => {
    renderPatientList(e.target.value);
});

// ══════════════════════════════════════════════════════════════
//  KEYBOARD SHORTCUTS
// ══════════════════════════════════════════════════════════════
document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'n') { e.preventDefault(); showNewPatientDialog(); }
    if (e.ctrlKey && e.key === 'f') { e.preventDefault(); document.getElementById('search-input').focus(); }
    if (e.key === 'Escape') {
        document.querySelectorAll('.dialog-overlay:not(.hidden)').forEach(d => d.classList.add('hidden'));
    }
});

// Close dialogs on overlay click
document.querySelectorAll('.dialog-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.classList.add('hidden');
    });
});

// ══════════════════════════════════════════════════════════════
//  CDS (Clinical Decision Support) — Phase K
// ══════════════════════════════════════════════════════════════

const CDS_COLORS = { 1: '#16A34A', 2: '#EAB308', 3: '#EA580C', 4: '#DC2626' };
const CDS_BG = { 1: '#F0FDF4', 2: '#FEFCE8', 3: '#FFF7ED', 4: '#FEF2F2' };
const CDS_LABELS = { 1: 'On Track', 2: 'Observe', 3: 'Evaluate', 4: 'Act / Refer' };

async function loadCdsAssessment(patientId) {
    const badge = document.getElementById('cds-tier-badge');
    const panel = document.getElementById('cds-panel');
    if (!badge || !panel) return;

    try {
        const cds = await api(`/patient/${patientId}/cds?standard=${state.standard}`);
        const tier = cds.max_tier || 1;

        // Tier badge
        badge.textContent = CDS_LABELS[tier] || 'Unknown';
        badge.style.background = CDS_BG[tier];
        badge.style.color = CDS_COLORS[tier];
        badge.style.borderColor = CDS_COLORS[tier];
        badge.classList.remove('hidden');

        // Alert panel
        const flagged = cds.categories_flagged || [];
        if (flagged.length === 0) {
            panel.classList.add('hidden');
            return;
        }

        let html = `<div class="flex items-center justify-between mb-2 cursor-pointer" onclick="this.parentElement.querySelector('.cds-details').classList.toggle('hidden')">
            <span class="font-bold text-sm" style="color:${CDS_COLORS[tier]}">CDS Alert — ${CDS_LABELS[tier]} (Tier ${tier})</span>
            <span class="text-xs text-slate-400">click to collapse</span>
        </div>
        <div class="cds-details">`;

        for (const cat of flagged) {
            const r = cds[cat];
            if (!r || !r.tier) continue;
            const catTier = r.tier;
            html += `<div class="mb-3 p-2 rounded" style="background:${CDS_BG[catTier]}; border-left:3px solid ${CDS_COLORS[catTier]}">
                <div class="font-semibold text-sm" style="color:${CDS_COLORS[catTier]}">${r.scenario_name} — Tier ${catTier}</div>`;

            if (r.trigger_criteria_met && r.trigger_criteria_met.length) {
                html += `<ul class="text-xs text-slate-600 mt-1 ml-4 list-disc">`;
                for (const c of r.trigger_criteria_met) {
                    html += `<li>${c}</li>`;
                }
                html += `</ul>`;
            }
            if (r.physician_action) {
                html += `<div class="text-xs text-slate-700 mt-1 font-medium">Action: ${r.physician_action}</div>`;
            }
            if (r.order_set) {
                html += `<div class="text-xs text-teal-600 mt-1">Order set: ${r.order_set}</div>`;
            }
            html += `</div>`;
        }

        html += `</div>`;
        panel.innerHTML = html;
        panel.classList.remove('hidden');

    } catch (e) {
        // CDS failure should not break the UI
        console.warn('CDS evaluation failed:', e);
        badge.classList.add('hidden');
        panel.classList.add('hidden');
    }
}


// ══════════════════════════════════════════════════════════════
//  CHART DIGITIZER INTEGRATION
// ══════════════════════════════════════════════════════════════

let _digitizerImageFile = null;

function openDigitizer() {
    document.getElementById('import-dialog').classList.add('hidden');
    document.getElementById('digitizer-dialog').classList.remove('hidden');
    ChartDigitizer.init('digitizer-canvas');
}

function closeDigitizer() {
    document.getElementById('digitizer-dialog').classList.add('hidden');
    _digitizerImageFile = null;
}

async function loadDigitizerImage(file) {
    if (!file) return;
    _digitizerImageFile = file;
    ChartDigitizer.reset();
    ChartDigitizer.init('digitizer-canvas');
    await ChartDigitizer.loadImage(file);
}

async function runAutoDetect() {
    if (!_digitizerImageFile) {
        alert('Please load a chart image first');
        return;
    }
    await ChartDigitizer.autoDetect(_digitizerImageFile);
}

async function confirmDigitizerPoints() {
    const points = ChartDigitizer.getPoints();
    if (!points.length) {
        alert('No points to import');
        return;
    }

    const patientId = state.currentPatientId;
    if (!patientId) {
        alert('Please select a patient first, then open the digitizer');
        return;
    }

    const patient = state.patients.find(p => p.id === patientId);
    if (!patient || !patient.birth_date) {
        alert('Selected patient has no birth date. Cannot compute measurement dates from ages.');
        return;
    }

    // Convert age-based points to date-based measurements
    const birthDate = new Date(patient.birth_date);
    const measurements = points.map(pt => {
        const measDate = new Date(birthDate);
        measDate.setDate(measDate.getDate() + Math.round(pt.age_years * 365.25));
        return {
            date: measDate.toISOString().split('T')[0],
            [pt.measurement_type]: pt.measurement,
            notes: `Digitized from chart (${pt.source})`,
        };
    });

    // Save each measurement
    let saved = 0;
    for (const m of measurements) {
        try {
            const resp = await fetch('/api/measurements', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ patient_id: patientId, ...m }),
            });
            if (resp.ok) saved++;
        } catch (e) {
            console.error('Failed to save measurement:', e);
        }
    }

    alert(`Imported ${saved}/${measurements.length} measurements from chart.`);
    closeDigitizer();
    await selectPatient(patientId);
}


// ══════════════════════════════════════════════════════════════
//  INIT
// ══════════════════════════════════════════════════════════════
(async function init() {
    await loadSettings();
    await loadPatients();
    updateTabs();
})();
