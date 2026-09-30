// Dashboard logic
let equipmentList = [];
let pipelineList = [];

const API_BASE_URL = 'http://127.0.0.1:8000';

function setActivePanel(targetId) {
    document.querySelectorAll('.nav-item').forEach(btn => btn.classList.toggle('active', btn.dataset.target === targetId));
    document.querySelectorAll('.panel').forEach(panel => panel.classList.toggle('active-panel', panel.id === targetId));
}

function renderEquipmentTable() {
    const tbody = document.getElementById('equipment-table-body');

    if (equipmentList.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No equipment added yet.</td></tr>';
        return;
    }

    tbody.innerHTML = equipmentList.map((item, index) => `
        <tr>
            <td><strong>${item.tag}</strong></td>
            <td>${item.name}</td>
            <td>${item.type}</td>
            <td><span class="status-badge status-${item.status || 'unknown'}">${item.status || 'Unknown'}</span></td>
            <td>${item.location || '--'}</td>
            <td>
                <button class="secondary-btn" style="padding: 8px 10px; font-size: 0.8rem; margin-right: 8px;" onclick="editEquipment(${index})">Edit</button>
                <button class="secondary-btn" style="padding: 8px 10px; font-size: 0.8rem; background: rgba(239,68,68,0.08); color: #b91c1c;" onclick="deleteEquipment(${index})">Delete</button>
            </td>
        </tr>
    `).join('');
}

function renderPipelines() {
    const container = document.getElementById('pipelines-list');

    if (pipelineList.length === 0) {
        container.innerHTML = '<div class="empty-state-card">No pipelines configured yet.</div>';
        return;
    }

    container.innerHTML = pipelineList.map((pipeline, index) => `
        <article class="pipeline-card">
            <h4>${pipeline.name}</h4>
            <p><strong>ID:</strong> ${pipeline.id}</p>
            <p>${pipeline.description || 'No description provided.'}</p>
            <p><strong>Status:</strong> <span style="color: #22c55e;">${pipeline.status || 'Active'}</span></p>
            <button class="secondary-btn" style="margin-top: 10px; width: 100%; background: rgba(239, 68, 68, 0.08); color: #b91c1c;" onclick="deletePipeline(${index})">Delete</button>
        </article>
    `).join('');
}

function updateKPIs() {
    const total = equipmentList.length;
    const operating = equipmentList.filter(item => item.status === 'operational').length;
    const warning = equipmentList.filter(item => item.status === 'warning').length;
    const offline = equipmentList.filter(item => item.status === 'offline').length;

    document.getElementById('total-assets').textContent = total;
    document.getElementById('operating-count').textContent = operating;
    document.getElementById('warning-count').textContent = warning;
    document.getElementById('offline-count').textContent = offline;
}

function saveEquipment() {
    localStorage.setItem('engineering-equipment', JSON.stringify(equipmentList));
}

function savePipelines() {
    localStorage.setItem('engineering-pipelines', JSON.stringify(pipelineList));
}

function loadEquipment() {
    const saved = localStorage.getItem('engineering-equipment');
    if (saved) {
        equipmentList = JSON.parse(saved);
    }
    renderEquipmentTable();
    updateKPIs();
}

function loadPipelines() {
    const saved = localStorage.getItem('engineering-pipelines');
    if (saved) {
        pipelineList = JSON.parse(saved);
    }
    renderPipelines();
}

function checkHealth() {
    fetch(`${API_BASE_URL}/api/health`)
        .then(r => r.json())
        .then(data => {
            document.getElementById('api-status').textContent = `API: Connected (${data.status})`;
        })
        .catch(() => {
            document.getElementById('api-status').textContent = 'API: Disconnected';
        });
}

function showAddEquipmentForm() {
    document.getElementById('add-equipment-form').classList.remove('hidden');
}

function closeAddEquipmentForm() {
    document.getElementById('add-equipment-form').classList.add('hidden');
    document.getElementById('equipment-form').reset();
}

function showAddPipelineForm() {
    document.getElementById('add-pipeline-form').classList.remove('hidden');
}

function closeAddPipelineForm() {
    document.getElementById('add-pipeline-form').classList.add('hidden');
    document.getElementById('pipeline-form').reset();
}

function updateLastUpdated() {
    document.getElementById('last-updated').textContent = new Date().toLocaleString();
}

function toggleDarkMode() {
    document.body.classList.toggle('dark-mode', document.getElementById('dark-mode').checked);
    localStorage.setItem('engineering-dark-mode', document.getElementById('dark-mode').checked ? 'true' : 'false');
}

function deleteEquipment(index) {
    if (!confirm('Delete this equipment item?')) return;
    equipmentList.splice(index, 1);
    saveEquipment();
    renderEquipmentTable();
    updateKPIs();
}

function editEquipment(index) {
    const item = equipmentList[index];
    document.getElementById('eq-tag').value = item.tag;
    document.getElementById('eq-name').value = item.name;
    document.getElementById('eq-type').value = item.type;
    document.getElementById('eq-location').value = item.location || '';
    showAddEquipmentForm();
    // Full CRUD editing could be expanded later
}

function deletePipeline(index) {
    if (!confirm('Delete this pipeline?')) return;
    pipelineList.splice(index, 1);
    savePipelines();
    renderPipelines();
}

function setupEventListeners() {
    document.querySelectorAll('.nav-item').forEach(button => {
        button.addEventListener('click', () => setActivePanel(button.dataset.target));
    });

    document.getElementById('equipment-form').addEventListener('submit', (event) => {
        event.preventDefault();
        equipmentList.push({
            tag: document.getElementById('eq-tag').value,
            name: document.getElementById('eq-name').value,
            type: document.getElementById('eq-type').value,
            location: document.getElementById('eq-location').value,
            status: 'operational'
        });
        saveEquipment();
        renderEquipmentTable();
        updateKPIs();
        closeAddEquipmentForm();
    });

    document.getElementById('pipeline-form').addEventListener('submit', (event) => {
        event.preventDefault();
        pipelineList.push({
            id: document.getElementById('pipe-id').value,
            name: document.getElementById('pipe-name').value,
            description: document.getElementById('pipe-desc').value,
            status: 'Active'
        });
        savePipelines();
        renderPipelines();
        closeAddPipelineForm();
    });

    document.getElementById('search-equipment').addEventListener('input', (event) => {
        const term = event.target.value.toLowerCase();
        const filtered = equipmentList.filter(item => {
            return item.tag.toLowerCase().includes(term) || item.name.toLowerCase().includes(term) || item.type.toLowerCase().includes(term);
        });

        const tbody = document.getElementById('equipment-table-body');
        if (!filtered.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No matching equipment found.</td></tr>';
            return;
        }

        tbody.innerHTML = filtered.map((item, index) => `
            <tr>
                <td><strong>${item.tag}</strong></td>
                <td>${item.name}</td>
                <td>${item.type}</td>
                <td><span class="status-badge status-${item.status || 'unknown'}">${item.status || 'Unknown'}</span></td>
                <td>${item.location || '--'}</td>
                <td>
                    <button class="secondary-btn" style="padding: 8px 10px; font-size: 0.8rem; margin-right: 8px;" onclick="editEquipment(${equipmentList.indexOf(item)})">Edit</button>
                    <button class="secondary-btn" style="padding: 8px 10px; font-size: 0.8rem; background: rgba(239,68,68,0.08); color: #b91c1c;" onclick="deleteEquipment(${equipmentList.indexOf(item)})">Delete</button>
                </td>
            </tr>
        `).join('');
    });
}

window.addEventListener('DOMContentLoaded', () => {
    loadEquipment();
    loadPipelines();
    setupEventListeners();
    updateLastUpdated();
    checkHealth();

    const dark = localStorage.getItem('engineering-dark-mode') === 'true';
    document.getElementById('dark-mode').checked = dark;
    document.body.classList.toggle('dark-mode', dark);
});
