/**
 * Z-Score Engine — LMS method for pediatric growth percentiles.
 *
 * Port of Python zscore/engine.py to JavaScript.
 * Uses the same LMS formula: z = ((x/M)^L - 1) / (L*S) when L!=0
 *                             z = ln(x/M) / S when L=0
 *
 * Data loaded from JSON files converted from official CDC/WHO CSVs.
 */

class ZScoreEngine {
    constructor() {
        this.tables = {};  // key -> {ages, L, M, S}
        this.loaded = { CDC: false, WHO: false };
    }

    // ── Data Loading ──────────────────────────────────────────

    async loadStandard(standard) {
        if (this.loaded[standard]) return;

        if (standard === 'CDC') {
            await this._loadCDC();
        } else if (standard === 'WHO') {
            await this._loadWHO();
        }
        this.loaded[standard] = true;
    }

    async _loadCDC() {
        // CDC uses sex-separated data in single files
        const files = {
            'hfa': ['data/cdc_hfa.json', 'data/cdc_hfa_infant.json'],
            'wfa': ['data/cdc_wfa.json', 'data/cdc_wfa_infant.json'],
            'bfa': ['data/cdc_bfa.json'],
        };

        for (const [indicator, urls] of Object.entries(files)) {
            // Load stature/child first, then infant (infant overwrites overlapping ages)
            for (const url of urls) {
                try {
                    const resp = await fetch(url);
                    const data = await resp.json();

                    for (const sex of ['boys', 'girls']) {
                        const sexCode = sex === 'boys' ? 'M' : 'F';
                        const key = `CDC_${indicator}_${sexCode}`;
                        const sexData = data[sex];
                        if (!sexData || !sexData.ages) continue;

                        if (!this.tables[key]) {
                            this.tables[key] = { ages: [], L: [], M: [], S: [] };
                        }

                        const table = this.tables[key];
                        for (let i = 0; i < sexData.ages.length; i++) {
                            const age = sexData.ages[i];
                            // For infant data overlapping with stature, overwrite
                            const existIdx = table.ages.indexOf(age);
                            if (existIdx >= 0) {
                                table.L[existIdx] = sexData.L[i];
                                table.M[existIdx] = sexData.M[i];
                                table.S[existIdx] = sexData.S[i];
                            } else {
                                table.ages.push(age);
                                table.L.push(sexData.L[i]);
                                table.M.push(sexData.M[i]);
                                table.S.push(sexData.S[i]);
                            }
                        }

                        // Sort by age
                        const indices = table.ages.map((_, i) => i);
                        indices.sort((a, b) => table.ages[a] - table.ages[b]);
                        table.ages = indices.map(i => table.ages[i]);
                        table.L = indices.map(i => table.L[i]);
                        table.M = indices.map(i => table.M[i]);
                        table.S = indices.map(i => table.S[i]);
                    }
                } catch (e) {
                    console.warn(`Failed to load ${url}:`, e);
                }
            }
        }
    }

    async _loadWHO() {
        const files = [
            ['hfa', 'M', 'data/who_hfa_boys_0_5.json', 'data/who_hfa_boys_5_19.json'],
            ['hfa', 'F', 'data/who_hfa_girls_0_5.json', 'data/who_hfa_girls_5_19.json'],
            ['wfa', 'M', 'data/who_wfa_boys_0_5.json', null],
            ['wfa', 'F', 'data/who_wfa_girls_0_5.json', null],
            ['bfa', 'M', 'data/who_bfa_boys_0_5.json', 'data/who_bfa_boys_5_19.json'],
            ['bfa', 'F', 'data/who_bfa_girls_0_5.json', 'data/who_bfa_girls_5_19.json'],
        ];

        for (const [indicator, sex, url1, url2] of files) {
            const key = `WHO_${indicator}_${sex}`;
            this.tables[key] = { ages: [], L: [], M: [], S: [] };

            for (const url of [url1, url2]) {
                if (!url) continue;
                try {
                    const resp = await fetch(url);
                    const data = await resp.json();
                    const table = this.tables[key];
                    for (let i = 0; i < data.ages.length; i++) {
                        table.ages.push(data.ages[i]);
                        table.L.push(data.L[i]);
                        table.M.push(data.M[i]);
                        table.S.push(data.S[i]);
                    }
                } catch (e) {
                    console.warn(`Failed to load ${url}:`, e);
                }
            }
        }
    }

    // ── LMS Interpolation ─────────────────────────────────────

    _interpolateLMS(table, ageMonths) {
        const ages = table.ages;
        if (!ages.length) return null;

        if (ageMonths <= ages[0]) return [table.L[0], table.M[0], table.S[0]];
        if (ageMonths >= ages[ages.length - 1]) {
            const n = ages.length - 1;
            return [table.L[n], table.M[n], table.S[n]];
        }

        // Binary search for bracketing indices
        let lo = 0, hi = ages.length - 1;
        while (lo < hi - 1) {
            const mid = (lo + hi) >> 1;
            if (ages[mid] <= ageMonths) lo = mid;
            else hi = mid;
        }

        const frac = (ageMonths - ages[lo]) / (ages[hi] - ages[lo]);
        return [
            table.L[lo] + frac * (table.L[hi] - table.L[lo]),
            table.M[lo] + frac * (table.M[hi] - table.M[lo]),
            table.S[lo] + frac * (table.S[hi] - table.S[lo]),
        ];
    }

    // ── Z-Score Computation ───────────────────────────────────

    computeZscore(measurement, ageMonths, sex, indicator, standard) {
        const key = `${standard}_${indicator}_${sex}`;
        const table = this.tables[key];
        if (!table || !table.ages.length) return null;

        const lms = this._interpolateLMS(table, ageMonths);
        if (!lms) return null;

        const [L, M, S] = lms;
        if (M <= 0 || S <= 0) return null;

        let z;
        if (Math.abs(L) < 1e-10) {
            z = Math.log(measurement / M) / S;
        } else {
            z = (Math.pow(measurement / M, L) - 1) / (L * S);
        }

        return Math.round(z * 1000) / 1000;
    }

    zscoreToPercentile(z) {
        // Standard normal CDF using error function approximation
        return 0.5 * (1 + this._erf(z / Math.SQRT2)) * 100;
    }

    // ── Percentile Curve Generation ───────────────────────────

    getPercentileCurve(standard, indicator, sex, zscore, ageMin, ageMax, step = 1) {
        const key = `${standard}_${indicator}_${sex}`;
        const table = this.tables[key];
        if (!table || !table.ages.length) return [];

        const points = [];
        for (let age = ageMin; age <= ageMax; age += step) {
            const lms = this._interpolateLMS(table, age);
            if (!lms) continue;
            const [L, M, S] = lms;
            if (M <= 0 || S <= 0) continue;

            let value;
            if (Math.abs(L) < 1e-10) {
                value = M * Math.exp(S * zscore);
            } else {
                value = M * Math.pow(1 + L * S * zscore, 1 / L);
            }

            if (isFinite(value) && value > 0) {
                points.push({ age: age / 12, value: Math.round(value * 100) / 100 });
            }
        }
        return points;
    }

    // ── Error Function Approximation ──────────────────────────

    _erf(x) {
        // Abramowitz and Stegun approximation
        const a1 = 0.254829592;
        const a2 = -0.284496736;
        const a3 = 1.421413741;
        const a4 = -1.453152027;
        const a5 = 1.061405429;
        const p = 0.3275911;

        const sign = x < 0 ? -1 : 1;
        x = Math.abs(x);
        const t = 1.0 / (1.0 + p * x);
        const y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
        return sign * y;
    }
}

// Export for both module and script contexts
if (typeof module !== 'undefined') module.exports = ZScoreEngine;
