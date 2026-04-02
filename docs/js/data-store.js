/**
 * IndexedDB Data Store — replaces SQLite for the PWA version.
 *
 * Stores patients, measurements, lab results, and settings locally
 * in the browser. Data never leaves the machine.
 */

class DataStore {
    constructor(dbName = 'growthchart') {
        this.dbName = dbName;
        this.db = null;
        this.version = 2;
    }

    async open() {
        return new Promise((resolve, reject) => {
            const req = indexedDB.open(this.dbName, this.version);

            req.onupgradeneeded = (e) => {
                const db = e.target.result;

                if (!db.objectStoreNames.contains('patients')) {
                    const ps = db.createObjectStore('patients', { keyPath: 'id', autoIncrement: true });
                    ps.createIndex('lastName', 'last_name');
                    ps.createIndex('mrn', 'medical_record_number');
                }

                if (!db.objectStoreNames.contains('measurements')) {
                    const ms = db.createObjectStore('measurements', { keyPath: 'id', autoIncrement: true });
                    ms.createIndex('patientId', 'patient_id');
                    ms.createIndex('date', 'date');
                }

                if (!db.objectStoreNames.contains('lab_results')) {
                    const ls = db.createObjectStore('lab_results', { keyPath: 'id', autoIncrement: true });
                    ls.createIndex('patientId', 'patient_id');
                }

                if (!db.objectStoreNames.contains('settings')) {
                    db.createObjectStore('settings', { keyPath: 'key' });
                }
            };

            req.onsuccess = (e) => {
                this.db = e.target.result;
                resolve(this);
            };

            req.onerror = (e) => reject(e.target.error);
        });
    }

    // ── Patients ──────────────────────────────────────────────

    async savePatient(patient) {
        const tx = this.db.transaction('patients', 'readwrite');
        const store = tx.objectStore('patients');
        const id = await this._put(store, patient);
        if (!patient.id) patient.id = id;
        return patient;
    }

    async getPatient(id) {
        const tx = this.db.transaction('patients', 'readonly');
        return this._get(tx.objectStore('patients'), id);
    }

    async getAllPatients() {
        const tx = this.db.transaction('patients', 'readonly');
        return this._getAll(tx.objectStore('patients'));
    }

    async searchPatients(query) {
        const all = await this.getAllPatients();
        const q = query.toLowerCase();
        return all.filter(p =>
            (p.first_name || '').toLowerCase().includes(q) ||
            (p.last_name || '').toLowerCase().includes(q) ||
            (p.medical_record_number || '').includes(q)
        );
    }

    async deletePatient(id) {
        const tx = this.db.transaction(['patients', 'measurements', 'lab_results'], 'readwrite');
        tx.objectStore('patients').delete(id);
        // Cascade delete measurements
        const meas = await this._getAllByIndex(tx.objectStore('measurements'), 'patientId', id);
        for (const m of meas) tx.objectStore('measurements').delete(m.id);
        // Cascade delete labs
        const labs = await this._getAllByIndex(tx.objectStore('lab_results'), 'patientId', id);
        for (const l of labs) tx.objectStore('lab_results').delete(l.id);
    }

    // ── Measurements ──────────────────────────────────────────

    async saveMeasurement(measurement) {
        const tx = this.db.transaction('measurements', 'readwrite');
        const id = await this._put(tx.objectStore('measurements'), measurement);
        if (!measurement.id) measurement.id = id;
        return measurement;
    }

    async getMeasurements(patientId) {
        const tx = this.db.transaction('measurements', 'readonly');
        const results = await this._getAllByIndex(tx.objectStore('measurements'), 'patientId', patientId);
        return results.sort((a, b) => (a.date || '').localeCompare(b.date || ''));
    }

    async deleteMeasurement(id) {
        const tx = this.db.transaction('measurements', 'readwrite');
        tx.objectStore('measurements').delete(id);
    }

    // ── Lab Results ───────────────────────────────────────────

    async saveLabResult(lab) {
        const tx = this.db.transaction('lab_results', 'readwrite');
        const id = await this._put(tx.objectStore('lab_results'), lab);
        if (!lab.id) lab.id = id;
        return lab;
    }

    async getLabResults(patientId) {
        const tx = this.db.transaction('lab_results', 'readonly');
        return this._getAllByIndex(tx.objectStore('lab_results'), 'patientId', patientId);
    }

    async deleteLabResult(id) {
        const tx = this.db.transaction('lab_results', 'readwrite');
        tx.objectStore('lab_results').delete(id);
    }

    // ── Settings ──────────────────────────────────────────────

    async getSetting(key) {
        const tx = this.db.transaction('settings', 'readonly');
        const result = await this._get(tx.objectStore('settings'), key);
        return result ? result.value : null;
    }

    async setSetting(key, value) {
        const tx = this.db.transaction('settings', 'readwrite');
        await this._put(tx.objectStore('settings'), { key, value });
    }

    // ── Import/Export ─────────────────────────────────────────

    async exportAll() {
        const patients = await this.getAllPatients();
        const allMeasurements = {};
        const allLabs = {};

        for (const p of patients) {
            allMeasurements[p.id] = await this.getMeasurements(p.id);
            allLabs[p.id] = await this.getLabResults(p.id);
        }

        return {
            version: 1,
            exported_at: new Date().toISOString(),
            patients,
            measurements: allMeasurements,
            lab_results: allLabs,
        };
    }

    async importFromJSON(data) {
        let imported = 0;
        const idMap = {};  // old ID -> new ID

        for (const p of (data.patients || [])) {
            const oldId = p.id;
            delete p.id;
            const saved = await this.savePatient(p);
            idMap[oldId] = saved.id;
            imported++;

            // Import measurements
            const meas = data.measurements?.[oldId] || [];
            for (const m of meas) {
                delete m.id;
                m.patient_id = saved.id;
                await this.saveMeasurement(m);
            }

            // Import labs
            const labs = data.lab_results?.[oldId] || [];
            for (const l of labs) {
                delete l.id;
                l.patient_id = saved.id;
                await this.saveLabResult(l);
            }
        }

        return imported;
    }

    // ── Internal Helpers ──────────────────────────────────────

    _put(store, data) {
        return new Promise((resolve, reject) => {
            const req = store.put(data);
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }

    _get(store, key) {
        return new Promise((resolve, reject) => {
            const req = store.get(key);
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }

    _getAll(store) {
        return new Promise((resolve, reject) => {
            const req = store.getAll();
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }

    _getAllByIndex(store, indexName, value) {
        return new Promise((resolve, reject) => {
            const index = store.index(indexName);
            const req = index.getAll(value);
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }
}

if (typeof module !== 'undefined') module.exports = DataStore;
