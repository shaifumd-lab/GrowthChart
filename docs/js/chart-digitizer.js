/**
 * Chart Digitizer — Extract data points from growth chart images.
 *
 * Workflow:
 *   1. User uploads chart image
 *   2. Calibration: 4 clicks to define X/Y axis mapping (pixel → real values)
 *   3. Auto-detect: OpenCV finds colored dots/marks on the chart
 *   4. User verifies/edits detected points
 *   5. Points exported as measurements
 */

const ChartDigitizer = (() => {
    // ── State ──────────────────────────────────────────────────
    let canvas, ctx, img;
    let zoom = 1, panX = 0, panY = 0;
    let isDragging = false, dragStart = { x: 0, y: 0 }, panStart = { x: 0, y: 0 };

    // Calibration
    const calibration = {
        step: 0,          // 0-3: four calibration clicks
        points: [],       // [{px, py, value}]
        xTransform: null, // {scale, offset} for X axis
        yTransform: null, // {scale, offset} for Y axis
        done: false,
    };

    // Data points
    let dataPoints = [];   // [{px, py, age, measurement, source: 'auto'|'manual'}]
    let measurementType = 'height_cm';  // or 'weight_kg'

    const CALIBRATION_STEPS = [
        { axis: 'x', label: 'Click a known point on the AGE (X) axis', prompt: 'Age at this point (years):' },
        { axis: 'x', label: 'Click another point on the AGE (X) axis', prompt: 'Age at this point (years):' },
        { axis: 'y', label: 'Click a known point on the MEASUREMENT (Y) axis', prompt: 'Value at this point (cm or kg):' },
        { axis: 'y', label: 'Click another point on the MEASUREMENT (Y) axis', prompt: 'Value at this point (cm or kg):' },
    ];

    // ── Initialize ─────────────────────────────────────────────

    function init(canvasId) {
        canvas = document.getElementById(canvasId);
        if (!canvas) return;
        ctx = canvas.getContext('2d');

        canvas.addEventListener('click', onCanvasClick);
        canvas.addEventListener('mousedown', onMouseDown);
        canvas.addEventListener('mousemove', onMouseMove);
        canvas.addEventListener('mouseup', onMouseUp);
        canvas.addEventListener('wheel', onWheel, { passive: false });

        reset();
    }

    function reset() {
        calibration.step = 0;
        calibration.points = [];
        calibration.xTransform = null;
        calibration.yTransform = null;
        calibration.done = false;
        dataPoints = [];
        zoom = 1;
        panX = 0;
        panY = 0;
        img = null;
        updateUI();
    }

    // ── Image Loading ──────────────────────────────────────────

    function loadImage(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => {
                img = new Image();
                img.onload = () => {
                    // Fit image to canvas
                    const canvasW = canvas.parentElement.clientWidth;
                    const canvasH = Math.min(500, window.innerHeight * 0.5);
                    canvas.width = canvasW;
                    canvas.height = canvasH;

                    zoom = Math.min(canvasW / img.width, canvasH / img.height);
                    panX = (canvasW - img.width * zoom) / 2;
                    panY = (canvasH - img.height * zoom) / 2;

                    render();
                    updateUI();
                    resolve();
                };
                img.onerror = reject;
                img.src = e.target.result;
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    // ── Rendering ──────────────────────────────────────────────

    function render() {
        if (!ctx || !canvas) return;
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Background
        ctx.fillStyle = '#f8fafc';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        if (!img) return;

        // Draw image with pan/zoom
        ctx.save();
        ctx.translate(panX, panY);
        ctx.scale(zoom, zoom);
        ctx.drawImage(img, 0, 0);
        ctx.restore();

        // Draw calibration points
        calibration.points.forEach((pt, i) => {
            const sx = pt.px * zoom + panX;
            const sy = pt.py * zoom + panY;
            ctx.beginPath();
            ctx.arc(sx, sy, 8, 0, Math.PI * 2);
            ctx.fillStyle = i < 2 ? 'rgba(59, 130, 246, 0.8)' : 'rgba(234, 88, 12, 0.8)';
            ctx.fill();
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 2;
            ctx.stroke();

            // Label
            ctx.font = 'bold 11px sans-serif';
            ctx.fillStyle = '#1e293b';
            const label = i < 2 ? `X: ${pt.value}y` : `Y: ${pt.value}`;
            ctx.fillText(label, sx + 12, sy + 4);
        });

        // Draw calibration crosshairs (axis lines)
        if (calibration.done) {
            ctx.setLineDash([4, 4]);
            ctx.strokeStyle = 'rgba(100, 116, 139, 0.3)';
            ctx.lineWidth = 1;

            // X axis line through Y calibration points
            const y1s = calibration.points[2].py * zoom + panY;
            const y2s = calibration.points[3].py * zoom + panY;
            ctx.beginPath();
            ctx.moveTo(0, y1s);
            ctx.lineTo(canvas.width, y1s);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(0, y2s);
            ctx.lineTo(canvas.width, y2s);
            ctx.stroke();

            ctx.setLineDash([]);
        }

        // Draw data points
        dataPoints.forEach((pt, i) => {
            const sx = pt.px * zoom + panX;
            const sy = pt.py * zoom + panY;

            // Point marker
            ctx.beginPath();
            ctx.arc(sx, sy, 6, 0, Math.PI * 2);
            ctx.fillStyle = pt.source === 'auto' ? 'rgba(16, 185, 129, 0.9)' : 'rgba(220, 38, 38, 0.9)';
            ctx.fill();
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 2;
            ctx.stroke();

            // Crosshair
            ctx.strokeStyle = 'rgba(0,0,0,0.15)';
            ctx.lineWidth = 0.5;
            ctx.setLineDash([2, 2]);
            ctx.beginPath();
            ctx.moveTo(sx, 0); ctx.lineTo(sx, canvas.height);
            ctx.moveTo(0, sy); ctx.lineTo(canvas.width, sy);
            ctx.stroke();
            ctx.setLineDash([]);

            // Label
            ctx.font = '10px sans-serif';
            ctx.fillStyle = '#1e293b';
            ctx.fillText(`${pt.age.toFixed(1)}y, ${pt.measurement.toFixed(1)}`, sx + 10, sy - 8);
        });
    }

    // ── Canvas Events ──────────────────────────────────────────

    function screenToImage(sx, sy) {
        return {
            x: (sx - panX) / zoom,
            y: (sy - panY) / zoom,
        };
    }

    function onCanvasClick(e) {
        if (isDragging) return;
        const rect = canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const sy = e.clientY - rect.top;
        const imgPt = screenToImage(sx, sy);

        if (!calibration.done) {
            handleCalibrationClick(imgPt.x, imgPt.y);
        } else {
            handleDigitizeClick(imgPt.x, imgPt.y);
        }
    }

    function onMouseDown(e) {
        if (e.button === 0 && e.ctrlKey) {
            isDragging = true;
            dragStart = { x: e.clientX, y: e.clientY };
            panStart = { x: panX, y: panY };
            canvas.style.cursor = 'grabbing';
            e.preventDefault();
        }
    }

    function onMouseMove(e) {
        if (isDragging) {
            panX = panStart.x + (e.clientX - dragStart.x);
            panY = panStart.y + (e.clientY - dragStart.y);
            render();
        }
    }

    function onMouseUp(e) {
        if (isDragging) {
            isDragging = false;
            canvas.style.cursor = 'crosshair';
        }
    }

    function onWheel(e) {
        e.preventDefault();
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
        const newZoom = Math.max(0.1, Math.min(10, zoom * zoomFactor));

        // Zoom towards mouse position
        panX = mx - (mx - panX) * (newZoom / zoom);
        panY = my - (my - panY) * (newZoom / zoom);
        zoom = newZoom;

        render();
    }

    // ── Calibration ────────────────────────────────────────────

    function handleCalibrationClick(imgX, imgY) {
        const step = calibration.step;
        if (step >= 4) return;

        const stepDef = CALIBRATION_STEPS[step];
        const valueStr = prompt(stepDef.prompt);
        if (valueStr === null) return;

        const value = parseFloat(valueStr);
        if (isNaN(value)) { alert('Please enter a valid number'); return; }

        calibration.points.push({ px: imgX, py: imgY, value });
        calibration.step++;

        if (calibration.step === 4) {
            computeTransform();
        }

        render();
        updateUI();
    }

    function computeTransform() {
        const [p1, p2, p3, p4] = calibration.points;

        // X axis: pixel → age
        const xScale = (p2.value - p1.value) / (p2.px - p1.px);
        const xOffset = p1.value - p1.px * xScale;

        // Y axis: pixel → measurement (note: Y is inverted in screen coords)
        const yScale = (p4.value - p3.value) / (p4.py - p3.py);
        const yOffset = p3.value - p3.py * yScale;

        calibration.xTransform = { scale: xScale, offset: xOffset };
        calibration.yTransform = { scale: yScale, offset: yOffset };
        calibration.done = true;

        canvas.style.cursor = 'crosshair';
    }

    function pixelToReal(px, py) {
        if (!calibration.done) return null;
        return {
            age: px * calibration.xTransform.scale + calibration.xTransform.offset,
            measurement: py * calibration.yTransform.scale + calibration.yTransform.offset,
        };
    }

    // ── Digitization ───────────────────────────────────────────

    function handleDigitizeClick(imgX, imgY) {
        const real = pixelToReal(imgX, imgY);
        if (!real) return;

        // Sanity check
        if (real.age < -1 || real.age > 25 || real.measurement < 0 || real.measurement > 250) {
            alert(`Values seem out of range: age=${real.age.toFixed(1)}, value=${real.measurement.toFixed(1)}. Click closer to the chart area.`);
            return;
        }

        dataPoints.push({
            px: imgX, py: imgY,
            age: real.age,
            measurement: real.measurement,
            source: 'manual',
        });

        render();
        updatePointsTable();
    }

    function removePoint(index) {
        dataPoints.splice(index, 1);
        render();
        updatePointsTable();
    }

    function undoLastPoint() {
        if (dataPoints.length > 0) {
            dataPoints.pop();
            render();
            updatePointsTable();
        }
    }

    // ── Auto-Detection (server-side OpenCV) ────────────────────

    async function autoDetect(imageFile) {
        if (!calibration.done) {
            alert('Please complete calibration first (4 points)');
            return;
        }

        const formData = new FormData();
        formData.append('file', imageFile);
        formData.append('cal_x1_px', calibration.points[0].px);
        formData.append('cal_x1_val', calibration.points[0].value);
        formData.append('cal_x2_px', calibration.points[1].px);
        formData.append('cal_x2_val', calibration.points[1].value);
        formData.append('cal_y1_py', calibration.points[2].py);
        formData.append('cal_y1_val', calibration.points[2].value);
        formData.append('cal_y2_py', calibration.points[3].py);
        formData.append('cal_y2_val', calibration.points[3].value);

        const statusEl = document.getElementById('digitizer-status');
        if (statusEl) statusEl.textContent = 'Detecting points...';

        try {
            const resp = await fetch('/api/import/chart-detect', { method: 'POST', body: formData });
            const result = await resp.json();

            if (result.success && result.points) {
                // Add auto-detected points
                result.points.forEach(pt => {
                    const real = pixelToReal(pt.px, pt.py);
                    if (real && real.age >= 0 && real.age <= 22 &&
                        real.measurement > 0 && real.measurement < 250) {
                        dataPoints.push({
                            px: pt.px, py: pt.py,
                            age: real.age,
                            measurement: real.measurement,
                            source: 'auto',
                        });
                    }
                });

                // Sort by age
                dataPoints.sort((a, b) => a.age - b.age);
                render();
                updatePointsTable();

                if (statusEl) statusEl.textContent =
                    `Detected ${result.points.length} points. Review and click to add any missed ones.`;
            } else {
                if (statusEl) statusEl.textContent =
                    result.error || 'Auto-detection found no points. Click manually to add them.';
            }
        } catch (err) {
            if (statusEl) statusEl.textContent = `Auto-detect error: ${err.message}. Click manually instead.`;
        }
    }

    // ── UI Updates ─────────────────────────────────────────────

    function updateUI() {
        const stepEl = document.getElementById('digitizer-step');
        const statusEl = document.getElementById('digitizer-status');
        const autoBtn = document.getElementById('digitizer-auto-btn');
        const undoBtn = document.getElementById('digitizer-undo-btn');
        const doneBtn = document.getElementById('digitizer-done-btn');

        if (!stepEl) return;

        if (!img) {
            stepEl.textContent = 'Upload a chart image to begin';
            if (statusEl) statusEl.textContent = '';
        } else if (!calibration.done) {
            const step = CALIBRATION_STEPS[calibration.step] || {};
            stepEl.textContent = `Step ${calibration.step + 1}/4: ${step.label || 'Calibration complete'}`;
            if (statusEl) statusEl.textContent = `${calibration.step}/4 calibration points set`;
        } else {
            stepEl.textContent = 'Calibrated! Auto-detect runs first, then click to add missed points.';
            if (statusEl) statusEl.textContent = `${dataPoints.length} point(s) captured`;
        }

        if (autoBtn) autoBtn.disabled = !calibration.done;
        if (undoBtn) undoBtn.disabled = dataPoints.length === 0;
        if (doneBtn) doneBtn.disabled = dataPoints.length === 0;
    }

    function updatePointsTable() {
        const tbody = document.getElementById('digitizer-points-tbody');
        if (!tbody) return;

        tbody.innerHTML = '';
        dataPoints.forEach((pt, i) => {
            const tr = document.createElement('tr');
            tr.className = 'border-b border-slate-100';
            tr.innerHTML = `
                <td class="px-2 py-1 text-sm">${pt.age.toFixed(2)}</td>
                <td class="px-2 py-1 text-sm">${pt.measurement.toFixed(1)}</td>
                <td class="px-2 py-1 text-xs text-slate-400">${pt.source}</td>
                <td class="px-2 py-1">
                    <button onclick="ChartDigitizer.removePoint(${i})"
                            class="text-red-500 text-xs hover:text-red-700">✕</button>
                </td>`;
            tbody.appendChild(tr);
        });

        updateUI();
    }

    // ── Export ──────────────────────────────────────────────────

    function getPoints() {
        return dataPoints.map(pt => ({
            age_years: Math.round(pt.age * 100) / 100,
            measurement: Math.round(pt.measurement * 10) / 10,
            measurement_type: measurementType,
            source: pt.source,
        }));
    }

    function setMeasurementType(type) {
        measurementType = type;
    }

    // ── Public API ─────────────────────────────────────────────

    return {
        init,
        reset,
        loadImage,
        autoDetect,
        removePoint,
        undoLastPoint,
        getPoints,
        setMeasurementType,
        get isCalibrated() { return calibration.done; },
        get pointCount() { return dataPoints.length; },
    };
})();
