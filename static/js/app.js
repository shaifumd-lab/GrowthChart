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
};

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
}

// ══════════════════════════════════════════════════════════════
//  MEASUREMENTS
// ══════════════════════════════════════════════════════════════
async function loadMeasurements() {
    if (!state.currentPatientId) return;
    state.measurements = await api(`/patients/${state.currentPatientId}/measurements?standard=${state.standard}`);
    renderMeasurementTable();
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
        tbody.innerHTML = '<tr><td colspan="12" class="px-4 py-6 text-center text-slate-400 text-sm">No measurements yet</td></tr>';
        return;
    }

    tbody.innerHTML = state.measurements.map(m => `
        <tr class="hover:bg-slate-50 transition">
            <td class="px-3 py-2 text-left whitespace-nowrap">${m.date ? new Date(m.date).toLocaleDateString('en-GB') : '—'}</td>
            <td class="px-3 py-2 text-left whitespace-nowrap text-slate-500">${m.age_str || '—'}</td>
            <td class="px-3 py-2 text-right font-mono">${m.height_cm != null ? m.height_cm.toFixed(1) : '—'}</td>
            <td class="px-3 py-2 text-right font-mono">${m.weight_kg != null ? m.weight_kg.toFixed(1) : '—'}</td>
            <td class="px-3 py-2 text-right font-mono">${m.bmi != null ? m.bmi.toFixed(1) : '—'}</td>
            <td class="px-3 py-2 text-right font-mono ${zClass(m.height_zscore)}">${fmtZ(m.height_zscore)}</td>
            <td class="px-3 py-2 text-right font-mono text-slate-500">${fmtPct(m.height_percentile)}</td>
            <td class="px-3 py-2 text-right font-mono ${zClass(m.weight_zscore)}">${fmtZ(m.weight_zscore)}</td>
            <td class="px-3 py-2 text-right font-mono text-slate-500">${fmtPct(m.weight_percentile)}</td>
            <td class="px-3 py-2 text-right font-mono ${zClass(m.bmi_zscore)}">${fmtZ(m.bmi_zscore)}</td>
            <td class="px-3 py-2 text-right font-mono text-slate-500">${fmtPct(m.bmi_percentile)}</td>
            <td class="px-3 py-2 text-center">
                <button onclick="deleteMeasurement(${m.id})" class="text-slate-400 hover:text-red-500 transition" title="Delete">✕</button>
            </td>
        </tr>
    `).join('');
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

    // Determine age range from measurements or default
    let ageMin = 0, ageMax = 240;
    if (state.measurements.length) {
        const ages = state.measurements
            .filter(m => m.age_months)
            .map(m => m.age_months);
        if (ages.length) {
            const pad = Math.max((Math.max(...ages) - Math.min(...ages)) * 0.3, 12);
            ageMin = Math.max(0, Math.min(...ages) - pad);
            ageMax = Math.max(...ages) + pad;
        }
    }

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

    // MPH target height band (Phase 12)
    if (patData.target_height_shape) {
        layout.shapes.push(patData.target_height_shape);
    }
    if (patData.mph_annotation) {
        layout.annotations.push(patData.mph_annotation);
    }

    const config = {
        responsive: true,
        displayModeBar: true,
        modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
        displaylogo: false,
        scrollZoom: true,
    };

    Plotly.react('chart', traces, layout, config);
}

// ══════════════════════════════════════════════════════════════
//  VELOCITY CHART (Phase 15)
// ══════════════════════════════════════════════════════════════
async function renderVelocityChart() {
    if (!state.currentPatient) return;

    const velData = await api(`/charts/velocity?patient_id=${state.currentPatientId}&standard=${state.standard}`);

    if (!velData.trace) {
        // Show empty chart with message
        Plotly.react('chart', [], {
            title: {
                text: velData.message || 'No velocity data available',
                font: { size: 14, color: '#94A3B8' },
            },
            paper_bgcolor: '#FAFBFC',
            plot_bgcolor: '#FFFFFF',
        }, { responsive: true, displaylogo: false });
        return;
    }

    const traces = [velData.trace];

    const nameDisplay = velData.patient_name || '';
    const sexLabel = velData.sex_label || '';
    const title = `${nameDisplay}  |  Height Velocity · ${sexLabel}`;

    const layout = {
        ...velData.layout,
        title: {
            text: title,
            font: { size: 14, color: '#475569' },
            x: 0.5,
        },
        showlegend: false,
    };

    const config = {
        responsive: true,
        displayModeBar: true,
        modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
        displaylogo: false,
        scrollZoom: true,
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

function setStandard(std) {
    state.standard = std;
    updateTabs();
    loadMeasurements().then(() => renderChart());
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
    form.birth_date.value = state.currentPatient.birth_date || '';
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
    showDialog('patient-dialog');
}

async function savePatient(e) {
    e.preventDefault();
    const form = e.target;
    const data = {
        first_name: form.first_name.value,
        last_name: form.last_name.value,
        birth_date: form.birth_date.value || null,
        sex: form.sex.value,
        medical_record_number: form.medical_record_number.value,
        // Phase 12-16 fields
        mother_height_cm: form.mother_height_cm ? (form.mother_height_cm.value || null) : null,
        father_height_cm: form.father_height_cm ? (form.father_height_cm.value || null) : null,
        mph_cm: form.mph_cm ? (form.mph_cm.value || null) : null,
        mph_user_edited: form.mph_user_edited ? (form.mph_user_edited.value === '1') : false,
        syndrome: form.syndrome ? form.syndrome.value : '',
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
    form.date.value = new Date().toISOString().slice(0, 10);
    showDialog('measurement-dialog');
}

async function saveMeasurement(e) {
    e.preventDefault();
    const form = e.target;
    const data = {
        date: form.date.value,
        height_cm: form.height_cm.value ? parseFloat(form.height_cm.value) : null,
        weight_kg: form.weight_kg.value ? parseFloat(form.weight_kg.value) : null,
        bone_age_years: form.bone_age_years.value ? parseFloat(form.bone_age_years.value) : null,
    };

    await api(`/patients/${state.currentPatientId}/measurements`, { method: 'POST', body: data });
    closeDialog('measurement-dialog');
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

function showImportDialog() {
    // Placeholder — will show file upload dialog when Phase 6 is implemented
    alert('Import functionality will be implemented in Phase 6');
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
//  INIT
// ══════════════════════════════════════════════════════════════
(async function init() {
    await loadSettings();
    await loadPatients();
    updateTabs();
})();
