document.addEventListener('DOMContentLoaded', () => {
    const uploadZone = document.getElementById('uploadZone');
    const fileInput = document.getElementById('fileInput');
    const filePreview = document.getElementById('filePreview');
    const fileName = document.getElementById('fileName');
    const previewImage = document.getElementById('previewImage');
    const scanningSection = document.getElementById('scanningSection');
    const detectedSection = document.getElementById('detectedSection');
    const bomSection = document.getElementById('bomSection');
    const equipmentList = document.getElementById('equipmentList');
    const bomTableBody = document.getElementById('bomTableBody');
    const totalMaterials = document.getElementById('totalMaterials');
    const totalCost = document.getElementById('totalCost');

    const API_BASE = 'http://localhost:8000/api';

    function showScanState(isScanning) {
        scanningSection.style.display = isScanning ? 'block' : 'none';
        detectedSection.style.display = isScanning ? 'none' : 'block';
        bomSection.style.display = isScanning ? 'none' : 'block';
    }

    function renderDetectedAssets(assets) {
        equipmentList.innerHTML = '';
        const counters = { pump: 0, valve: 0, vessel: 0, instrument: 0 };

        assets.forEach((asset) => {
            const type = asset.type || 'equipment';
            counters[type] = (counters[type] || 0) + 1;

            const item = document.createElement('div');
            item.className = 'detected-equipment';
            item.innerHTML = `
                <div class="detected-icon">${type === 'pump' ? '💧' : type === 'valve' ? '⛭' : type === 'vessel' ? '🛢️' : '📐'}</div>
                <div class="detected-label">
                    <strong>${asset.tag || 'AUTO-ITEM'}</strong>
                    <span>${type}</span>
                </div>
            `;
            equipmentList.appendChild(item);
        });

        document.getElementById('totalEquip').textContent = assets.length;
        document.getElementById('totalPumps').textContent = counters.pump || 0;
        document.getElementById('totalValves').textContent = counters.valve || 0;
        document.getElementById('totalVessels').textContent = counters.vessel || 0;
    }

    function renderMaterials(materials) {
        bomTableBody.innerHTML = '';
        materials.forEach((item) => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${item.item_number || 1}</td>
                <td><span class="material-tag">${item.tag_id || item.tag || 'AUTO'}</span></td>
                <td>${item.description || 'Detected equipment'}</td>
                <td>${item.type || 'equipment'}</td>
                <td><span class="quantity-badge">${item.quantity || 1}</span></td>
                <td>${item.unit || 'ea'}</td>
                <td>${item.supplier || 'Auto-generated'}</td>
                <td>$${Number(item.unit_cost || 0).toFixed(2)}</td>
                <td>$${Number(item.total_cost || 0).toFixed(2)}</td>
            `;
            bomTableBody.appendChild(row);
        });

        totalMaterials.textContent = materials.length;
        totalCost.textContent = `$${materials.reduce((sum, item) => sum + Number(item.total_cost || 0), 0).toFixed(2)}`;
    }

    async function handleFileUpload(event) {
        const file = event.target.files[0];
        if (!file) return;

        fileName.textContent = file.name;
        filePreview.style.display = 'block';
        previewImage.style.display = file.type.startsWith('image/') ? 'block' : 'none';

        if (file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = (e) => { previewImage.src = e.target.result; };
            reader.readAsDataURL(file);
        }

        showScanState(true);

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch(`${API_BASE}/scan`, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Scan failed');
            }

            const data = await response.json();
            const assets = data.detected_assets || [];
            const materials = data.materials || [];

            renderDetectedAssets(assets);
            renderMaterials(materials);
            showScanState(false);
            detectedSection.style.display = 'block';
            bomSection.style.display = 'block';
        } catch (error) {
            showScanState(false);
            console.error(error);
            alert(`Scan error: ${error.message}`);
        }
    }

    uploadZone.addEventListener('dragover', (event) => {
        event.preventDefault();
        uploadZone.classList.add('dragover');
    });

    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('dragover');
    });

    uploadZone.addEventListener('drop', (event) => {
        event.preventDefault();
        uploadZone.classList.remove('dragover');
        if (event.dataTransfer.files && event.dataTransfer.files[0]) {
            fileInput.files = event.dataTransfer.files;
            handleFileUpload({ target: { files: event.dataTransfer.files } });
        }
    });

    fileInput.addEventListener('change', handleFileUpload);
});

function exportBOM(format) {
    const rows = [...document.querySelectorAll('#bomTableBody tr')];
    if (!rows.length) {
        alert('No BOM data available yet.');
        return;
    }

    const rowsData = rows.map((row) => Array.from(row.children).map((cell) => cell.textContent.trim()));
    const payload = JSON.stringify(rowsData, null, 2);

    if (format === 'json') {
        const blob = new Blob([payload], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'bom.json';
        a.click();
        URL.revokeObjectURL(url);
        return;
    }

    if (format === 'csv') {
        const csv = rowsData.map((r) => r.join(',')).join('\n');
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'bom.csv';
        a.click();
        URL.revokeObjectURL(url);
        return;
    }

    alert('PDF export is not implemented in the browser demo. Use CSV or JSON export.');
}
