/**
 * growthGuard PWA — Main Application Logic
 *
 * Replaces Flask API calls with local IndexedDB + JS z-score engine.
 * All computation happens client-side. Data never leaves the browser.
 */

// ── Global State ──────────────────────────────────────────────

const engine = new ZScoreEngine();
const store = new DataStore();
const fileAccess = new FileAccess();

const state = {
    patients: [],
    currentPatientId: null,
    currentPatient: null,
    measurements: [],
    indicator: 'hfa',
    standard: 'CDC',
};

const PERCENTILE_ZSCORES = {
    3: -1.88079, 5: -1.64485, 10: -1.28155, 25: -0.67449,
    50: 0.0, 75: 0.67449, 90: 1.28155, 95: 1.64485, 97: 1.88079,
};

const PERCENTILE_COLORS = {
    3: '#DC2626', 5: '#EA580C', 10: '#D97706', 25: '#65A30D',
    50: '#15803D', 75: '#65A30D', 90: '#D97706', 95: '#EA580C', 97: '#DC2626',
};

// ── Initialization ────────────────────────────────────────────

async function init() {
    await store.open();
    await engine.loadStandard('CDC');
    await engine.loadStandard('WHO');
    await loadPatients();
    console.log('growthGuard PWA initialized');
}

// ── Patient List ──────────────────────────────────────────────

async function loadPatients() {
    state.patients = await store.getAllPatients();
    renderPatientList();
}

function renderPatientList(filter = '') {
    const list = document.getElementById('patient-list');
    if (!list) return;

    let patients = state.patients;
    if (filter) {
        const q = filter.toLowerCase();
        patients = patients.filter(p =>
            (p.first_name || '').toLowerCase().includes(q) ||
            (p.last_name || '').toLowerCase().includes(q) ||
            (p.medical_record_number || '').includes(q)
        );
    }

    list.innerHTML = patients.map(p => {
        const isActive = p.id === state.currentPatientId;
        const name = `${p.first_name || ''} ${p.last_name || ''}`.trim() || 'Unnamed';
        const age = p.birth_date ? computeAgeStr(p.birth_date) : '';
        const sex = p.sex === 'M' ? 'M' : 'F';
        return `<div class="patient-item ${isActive ? 'active' : ''}" onclick="selectPatient(${p.id})">
            <div class="name" dir="rtl">${name}</div>
            <div class="meta">${sex} · ${age} ${p.medical_record_number ? '· ' + p.medical_record_number : ''}</div>
        </div>`;
    }).join('');
}

function filterPatients(query) {
    renderPatientList(query);
}

function computeAgeStr(birthDateStr) {
    const bd = new Date(birthDateStr);
    const today = new Date();
    let years = today.getFullYear() - bd.getFullYear();
    let months = today.getMonth() - bd.getMonth();
    if (months < 0) { years--; months += 12; }
    if (today.getDate() < bd.getDate()) { months--; if (months < 0) { years--; months += 12; } }
    return years > 0 ? `${years}y ${months}m` : `${months}m`;
}

// ── Patient Selection ─────────────────────────────────────────

async function selectPatient(id) {
    state.currentPatientId = id;
    state.currentPatient = await store.getPatient(id);
    renderPatientList();

    document.getElementById('empty-state').classList.add('hidden');
    document.getElementById('patient-view').classList.remove('hidden');

    const p = state.currentPatient;
    document.getElementById('patient-name').textContent =
        `${p.first_name || ''} ${p.last_name || ''}`.trim();

    const info = [];
    if (p.birth_date) info.push(`DOB: ${new Date(p.birth_date).toLocaleDateString('en-GB')}`);
    if (p.birth_date) info.push(`Age: ${computeAgeStr(p.birth_date)}`);
    info.push(p.sex === 'M' ? 'Male' : 'Female');
    if (p.medical_record_number) info.push(`ID: ${p.medical_record_number}`);
    document.getElementById('patient-info').textContent = info.join(' · ');

    await loadMeasurements();
    updateTabs();
    await renderChart();
}

// ── Measurements ──────────────────────────────────────────────

async function loadMeasurements() {
    if (!state.currentPatientId) return;
    const raw = await store.getMeasurements(state.currentPatientId);
    const p = state.currentPatient;

    state.measurements = raw.map(m => {
        const entry = { ...m };
        if (m.date && p.birth_date) {
            const ageDays = (new Date(m.date) - new Date(p.birth_date)) / 86400000;
            const ageMonths = ageDays / 30.4375;
            entry.age_months = ageMonths;
            entry.age_str = ageMonths >= 12
                ? `${Math.floor(ageMonths / 12)}y ${Math.floor(ageMonths % 12)}m`
                : `${Math.floor(ageMonths)}m`;

            if (m.height_cm) {
                entry.height_zscore = engine.computeZscore(m.height_cm, ageMonths, p.sex, 'hfa', state.standard);
            }
            if (m.weight_kg) {
                entry.weight_zscore = engine.computeZscore(m.weight_kg, ageMonths, p.sex, 'wfa', state.standard);
            }
            if (m.height_cm && m.weight_kg && m.height_cm > 0) {
                const bmi = m.weight_kg / ((m.height_cm / 100) ** 2);
                entry.bmi = Math.round(bmi * 100) / 100;
                entry.bmi_zscore = engine.computeZscore(bmi, ageMonths, p.sex, 'bfa', state.standard);
            }
        }
        return entry;
    });

    renderMeasurementTable();
}

function renderMeasurementTable() {
    const tbody = document.getElementById('measurements-tbody');
    if (!tbody) return;

    document.getElementById('measurement-count').textContent =
        `${state.measurements.length} measurement${state.measurements.length !== 1 ? 's' : ''}`;

    tbody.innerHTML = state.measurements.map(m => {
        const fmtZ = (z) => z != null ? `<span class="${zClass(z)}">${z >= 0 ? '+' : ''}${z.toFixed(2)}</span>` : '—';
        return `<tr class="border-b border-slate-50 hover:bg-slate-50">
            <td class="px-3 py-1.5">${m.date || '—'}</td>
            <td class="px-3 py-1.5">${m.age_str || '—'}</td>
            <td class="px-3 py-1.5 text-right">${m.height_cm ? m.height_cm.toFixed(1) : '—'}</td>
            <td class="px-3 py-1.5 text-right">${fmtZ(m.height_zscore)}</td>
            <td class="px-3 py-1.5 text-right">${m.weight_kg ? m.weight_kg.toFixed(1) : '—'}</td>
            <td class="px-3 py-1.5 text-right">${fmtZ(m.weight_zscore)}</td>
            <td class="px-3 py-1.5 text-right">${m.bmi ? m.bmi.toFixed(1) : '—'}</td>
            <td class="px-3 py-1.5 text-right">${fmtZ(m.bmi_zscore)}</td>
            <td class="px-3 py-1.5 text-right">
                <button onclick="deleteMeasurement(${m.id})" class="text-red-400 hover:text-red-600 text-xs">Del</button>
            </td>
        </tr>`;
    }).join('');
}

function zClass(z) {
    if (z == null) return '';
    const abs = Math.abs(z);
    if (abs > 2) return 'z-severe';
    if (abs > 1) return 'z-warning';
    return 'z-normal';
}

// ── Chart Rendering ───────────────────────────────────────────

function updateTabs() {
    document.querySelectorAll('.indicator-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.ind === state.indicator);
    });
    document.querySelectorAll('.standard-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.std === state.standard);
    });
}

function setIndicator(ind) {
    state.indicator = ind;
    updateTabs();
    renderChart();
}

async function setStandard(std) {
    state.standard = std;
    await engine.loadStandard(std);
    updateTabs();
    await loadMeasurements();
    await renderChart();
}

async function renderChart() {
    const chartDiv = document.getElementById('chart');
    if (!chartDiv || !state.currentPatient) return;

    const p = state.currentPatient;
    const std = state.standard;
    const ind = state.indicator;

    if (ind === 'velocity') {
        renderVelocityChart(chartDiv);
        return;
    }

    // Age range
    const ageMax = std === 'CDC' ? 240 : 228;

    // Build percentile curves
    const traces = [];
    for (const [pct, z] of Object.entries(PERCENTILE_ZSCORES)) {
        const curve = engine.getPercentileCurve(std, ind, p.sex, z, 0, ageMax, 1);
        if (curve.length === 0) continue;

        const color = PERCENTILE_COLORS[pct] || '#999';
        const isOuter = [3, 5, 95, 97].includes(Number(pct));
        const isMedian = Number(pct) === 50;

        traces.push({
            name: `P${pct}`,
            x: curve.map(pt => pt.age),
            y: curve.map(pt => pt.value),
            mode: 'lines',
            line: {
                color,
                width: isMedian ? 1.8 : 0.8,
                dash: isOuter ? 'dash' : (isMedian ? 'solid' : 'dot'),
            },
            hovertemplate: `P${pct}: %{y:.1f} at %{x:.1f}y<extra></extra>`,
            showlegend: [3, 25, 50, 75, 97].includes(Number(pct)),
        });
    }

    // Patient data trace
    const meas = state.measurements.filter(m => {
        if (ind === 'hfa') return m.height_cm && m.age_months != null;
        if (ind === 'wfa') return m.weight_kg && m.age_months != null;
        if (ind === 'bfa') return m.bmi && m.age_months != null;
        return false;
    });

    const dataField = ind === 'hfa' ? 'height_cm' : (ind === 'wfa' ? 'weight_kg' : 'bmi');
    const zField = ind === 'hfa' ? 'height_zscore' : (ind === 'wfa' ? 'weight_zscore' : 'bmi_zscore');
    const color = p.sex === 'M' ? '#2563EB' : '#EC4899';

    if (meas.length) {
        traces.push({
            name: `${p.first_name || ''} ${p.last_name || ''}`.trim(),
            x: meas.map(m => m.age_months / 12),
            y: meas.map(m => m[dataField]),
            text: meas.map(m => {
                const z = m[zField];
                return z != null ? `z=${z >= 0 ? '+' : ''}${z.toFixed(2)}` : '';
            }),
            mode: 'lines+markers+text',
            textposition: 'top center',
            textfont: { size: 10, color },
            line: { color, width: 2.5 },
            marker: { color, size: 8, line: { width: 1.5, color: 'white' } },
        });
    }

    const yLabels = { hfa: 'Height (cm)', wfa: 'Weight (kg)', bfa: 'BMI (kg/m²)' };
    const titles = { hfa: 'Height-for-Age', wfa: 'Weight-for-Age', bfa: 'BMI-for-Age' };

    const layout = {
        title: { text: `${titles[ind] || ''} — ${std} (${p.sex === 'M' ? 'Boys' : 'Girls'})`, font: { size: 14 } },
        xaxis: { title: 'Age (years)', dtick: 1, gridcolor: 'rgba(0,0,0,0.08)', zeroline: false },
        yaxis: { title: yLabels[ind] || '', gridcolor: 'rgba(0,0,0,0.08)' },
        dragmode: 'zoom',
        hovermode: 'closest',
        margin: { l: 60, r: 30, t: 50, b: 50 },
        paper_bgcolor: '#FAFBFC',
        plot_bgcolor: '#FFFFFF',
        showlegend: true,
        legend: { x: 1, y: 1, xanchor: 'right', bgcolor: 'rgba(255,255,255,0.8)', font: { size: 10 } },
    };

    Plotly.react(chartDiv, traces, layout, { responsive: true, displayModeBar: true, doubleClick: 'reset+autosize' });
}

function renderVelocityChart(chartDiv) {
    // Compute velocity from consecutive measurements
    const meas = state.measurements.filter(m => m.height_cm && m.age_months != null);
    if (meas.length < 2) {
        Plotly.react(chartDiv, [], {
            annotations: [{ text: 'Need 2+ height measurements for velocity', showarrow: false, font: { size: 14 } }],
        });
        return;
    }

    const velocities = [];
    for (let i = 0; i < meas.length - 1; i++) {
        const m1 = meas[i], m2 = meas[i + 1];
        const deltaMonths = m2.age_months - m1.age_months;
        if (deltaMonths <= 0) continue;
        const vel = (m2.height_cm - m1.height_cm) / (deltaMonths / 12);
        velocities.push({
            age: (m1.age_months + m2.age_months) / 2 / 12,
            velocity: Math.round(vel * 10) / 10,
        });
    }

    const p = state.currentPatient;
    const color = p.sex === 'M' ? '#2563EB' : '#EC4899';

    const traces = [{
        name: 'Patient velocity',
        x: velocities.map(v => v.age),
        y: velocities.map(v => v.velocity),
        text: velocities.map(v => `${v.velocity}`),
        mode: 'lines+markers+text',
        textposition: 'top center',
        textfont: { size: 10, color },
        line: { color, width: 2.5 },
        marker: { color, size: 9, line: { width: 1.5, color: 'white' } },
    }];

    const layout = {
        title: { text: `Height Velocity — ${p.sex === 'M' ? 'Boys' : 'Girls'}`, font: { size: 14 } },
        xaxis: { title: 'Age (years)', dtick: 1, gridcolor: 'rgba(0,0,0,0.08)' },
        yaxis: { title: 'Velocity (cm/year)', gridcolor: 'rgba(0,0,0,0.08)', rangemode: 'nonnegative' },
        dragmode: 'zoom',
        hovermode: 'closest',
        margin: { l: 60, r: 30, t: 50, b: 50 },
        paper_bgcolor: '#FAFBFC',
        plot_bgcolor: '#FFFFFF',
        showlegend: true,
    };

    Plotly.react(chartDiv, traces, layout, { responsive: true, doubleClick: 'reset+autosize' });
}

// ── CRUD Dialogs ──────────────────────────────────────────────

function showAddPatientDialog() {
    const name = prompt('Patient name (first last):');
    if (!name) return;
    const parts = name.trim().split(/\s+/);
    const first = parts[0] || '';
    const last = parts.slice(1).join(' ') || '';
    const sex = prompt('Sex (M/F):', 'M');
    const dob = prompt('Date of birth (YYYY-MM-DD):');

    store.savePatient({
        first_name: first, last_name: last,
        sex: (sex || 'M').toUpperCase().charAt(0) === 'F' ? 'F' : 'M',
        birth_date: dob || null,
        medical_record_number: '',
        notes: '',
    }).then(() => loadPatients());
}

function editPatient() {
    if (!state.currentPatient) return;
    const p = state.currentPatient;
    const name = prompt('Name:', `${p.first_name} ${p.last_name}`);
    if (name === null) return;
    const parts = name.trim().split(/\s+/);
    p.first_name = parts[0] || '';
    p.last_name = parts.slice(1).join(' ') || '';
    const dob = prompt('DOB (YYYY-MM-DD):', p.birth_date || '');
    if (dob !== null) p.birth_date = dob || null;
    store.savePatient(p).then(() => selectPatient(p.id));
}

function addMeasurement() {
    if (!state.currentPatientId) return;
    const dateStr = prompt('Date (YYYY-MM-DD):', new Date().toISOString().split('T')[0]);
    if (!dateStr) return;
    const ht = prompt('Height (cm):');
    const wt = prompt('Weight (kg):');

    store.saveMeasurement({
        patient_id: state.currentPatientId,
        date: dateStr,
        height_cm: ht ? parseFloat(ht) : null,
        weight_kg: wt ? parseFloat(wt) : null,
    }).then(() => {
        loadMeasurements();
        renderChart();
    });
}

async function deleteMeasurement(id) {
    await store.deleteMeasurement(id);
    await loadMeasurements();
    await renderChart();
}

// ── Import/Export ──────────────────────────────────────────────

function showImportDialog() {
    // Show import options
    const choice = confirm(
        'IMPORT OPTIONS:\n\n' +
        'OK = Import JSON file (exported from growthGuard)\n' +
        'Cancel = Import PDF/Image (requires desktop version)\n\n' +
        'Note: PDF and image import with OCR requires the desktop version ' +
        '(python main.py). This web version supports JSON data import ' +
        'and manual patient/measurement entry.'
    );

    if (choice) {
        // JSON import
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.json';
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            try {
                const text = await file.text();
                const data = JSON.parse(text);
                const count = await store.importFromJSON(data);
                alert(`Imported ${count} patients from JSON`);
                await loadPatients();
            } catch (err) {
                alert(`Import failed: ${err.message}\n\nMake sure the file is a valid growthGuard JSON export.`);
            }
        };
        input.click();
    } else {
        alert(
            'PDF/Image import is available in the desktop version.\n\n' +
            'Run at home:\n' +
            '  cd growthGuard\n' +
            '  python main.py\n\n' +
            'Then open http://localhost:5000 in your browser.\n' +
            'Export your data as JSON and import it here.'
        );
    }
}

function showSettingsDialog() {
    alert('Settings: Font size and default standard can be configured.\nData is stored in IndexedDB (browser local storage).');
}

// ── File System Access (Folder Sync) ──────────────────────────

async function syncToFolder() {
    try {
        if (!fileAccess.isOpen) await fileAccess.openDirectory();
        const data = await store.exportAll();
        await fileAccess.syncToFolder(data);
        alert(`Saved ${data.patients.length} patients to folder`);
    } catch (e) {
        alert('Save failed: ' + e.message);
    }
}

async function syncFromFolder() {
    try {
        if (!fileAccess.isOpen) await fileAccess.openDirectory();
        const data = await fileAccess.syncFromFolder();
        if (!data) { alert('No growthchart-data.json found in folder'); return; }
        const count = await store.importFromJSON(data);
        alert(`Loaded ${count} patients from folder`);
        await loadPatients();
    } catch (e) {
        alert('Load failed: ' + e.message);
    }
}

// ── Start ─────────────────────────────────────────────────────

init();
