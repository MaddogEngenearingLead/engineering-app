// API Configuration
const API_BASE_URL = 'http://127.0.0.1:8000';
let equipmentList = [];
let pipelineList = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    checkHealth();
    loadEquipment();
    loadPipelines();
    setupEventListeners();
    updateLastUpdated();
});

// Section Navigation
function showSection(sectionId) {
    // Hide all sections
    document.querySelectorAll('.section').forEach(section => {
        section.classList.remove('active');
    });

    // Remove active from all nav links
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
    });

    // Show selected section
    document.getElementById(sectionId).classList.add('active');

    // Set active nav link
    event.target.classList.add('active');
}

// Check API Health
function checkHealth() {
    fetch(`${API_BASE_URL}/api/health`)
        .then(response => response.json())
        .then(data => {
            document.getElementById('api-status').textContent = 'API: Connected ✓';
            document.getElementById('api-status').style.color = '#4CAF50';
        })
        .catch(error => {
            document.getElementById('api-status').textContent = 'API: Disconnected ✗';
            document.getElementById('api-status').style.color = '#F44336';
            console.error('Health check failed:', error);
        });
}

// Load Equipment
function loadEquipment() {
    // For now, load from localStorage
    const stored = localStorage.getItem('equipmentList');
    if (stored) {
        equipmentList = JSON.parse(stored);
        renderEquipmentTable();
        updateKPIs();
    }
}

// Render Equipment Table
function renderEquipmentTable() {
    const tbody = document.getElementById('equipment-table-body');
    
    if (equipmentList.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No equipment added yet. Click "Add Equipment" to get started.</td></tr>';
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
                <button class="btn btn-secondary" onclick="editEquipment(${index})" style="padding: 0.5rem;">Edit</button>
                <button class="btn btn-secondary" onclick="deleteEquipment(${index})" style="padding: 0.5rem; margin-left: 0.5rem; background: #ffebee; color: #c62828;">Delete</button>
            </td>
        </tr>
    `).join('');
}

// Add Equipment Form
function showAddEquipmentForm() {
    document.getElementById('add-equipment-form').classList.remove('hidden');
}

function closeAddEquipmentForm() {
    document.getElementById('add-equipment-form').classList.add('hidden');
    document.getElementById('equipment-form').reset();
}

// Setup Event Listeners
function setupEventListeners() {
    // Equipment form submission
    document.getElementById('equipment-form').addEventListener('submit', function(e) {
        e.preventDefault();
        const equipment = {
            tag: document.getElementById('eq-tag').value,
            name: document.getElementById('eq-name').value,
            type: document.getElementById('eq-type').value,
            location: document.getElementById('eq-location').value,
            status: 'operational'
        };
        equipmentList.push(equipment);
        saveEquipment();
        renderEquipmentTable();
        updateKPIs();
        closeAddEquipmentForm();
    });

    // Pipeline form submission
    document.getElementById('pipeline-form').addEventListener('submit', function(e) {
        e.preventDefault();
        const pipeline = {
            id: document.getElementById('pipe-id').value,
            name: document.getElementById('pipe-name').value,
            description: document.getElementById('pipe-desc').value,
            status: 'active'
        };
        pipelineList.push(pipeline);
        savePipelines();
        renderPipelines();
        closeAddPipelineForm();
    });
}

// Save Equipment
function saveEquipment() {
    localStorage.setItem('equipmentList', JSON.stringify(equipmentList));
}

// Delete Equipment
function deleteEquipment(index) {
    if (confirm('Are you sure you want to delete this equipment?')) {
        equipmentList.splice(index, 1);
        saveEquipment();
        renderEquipmentTable();
        updateKPIs();
    }
}

// Edit Equipment
function editEquipment(index) {
    const item = equipmentList[index];
    document.getElementById('eq-tag').value = item.tag;
    document.getElementById('eq-name').value = item.name;
    document.getElementById('eq-type').value = item.type;
    document.getElementById('eq-location').value = item.location;
    showAddEquipmentForm();
    // Note: Full edit functionality would need more implementation
}

// Load Pipelines
function loadPipelines() {
    const stored = localStorage.getItem('pipelineList');
    if (stored) {
        pipelineList = JSON.parse(stored);
        renderPipelines();
    }
}

// Render Pipelines
function renderPipelines() {
    const container = document.getElementById('pipelines-list');
    
    if (pipelineList.length === 0) {
        container.innerHTML = '<div class="empty-state">No pipelines configured yet. Click "Add Pipeline" to create one.</div>';
        return;
    }

    container.innerHTML = pipelineList.map((pipeline, index) => `
        <div class="pipeline-card">
            <h4>${pipeline.name}</h4>
            <p><strong>ID:</strong> ${pipeline.id}</p>
            <p>${pipeline.description}</p>
            <p><strong>Status:</strong> <span style="color: #4CAF50;">${pipeline.status}</span></p>
            <button class="btn btn-secondary" onclick="deletePipeline(${index})" style="margin-top: 1rem; padding: 0.5rem; width: 100%; background: #ffebee; color: #c62828;">Delete</button>
        </div>
    `).join('');
}

// Add Pipeline Form
function showAddPipelineForm() {
    document.getElementById('add-pipeline-form').classList.remove('hidden');
}

function closeAddPipelineForm() {
    document.getElementById('add-pipeline-form').classList.add('hidden');
    document.getElementById('pipeline-form').reset();
}

// Save Pipelines
function savePipelines() {
    localStorage.setItem('pipelineList', JSON.stringify(pipelineList));
}

// Delete Pipeline
function deletePipeline(index) {
    if (confirm('Are you sure you want to delete this pipeline?')) {
        pipelineList.splice(index, 1);
        savePipelines();
        renderPipelines();
    }
}

// Update KPIs
function updateKPIs() {
    const total = equipmentList.length;
    const operational = equipmentList.filter(e => e.status === 'operational').length;
    const warning = equipmentList.filter(e => e.status === 'warning').length;
    const offline = equipmentList.filter(e => e.status === 'offline').length;

    document.getElementById('total-assets').textContent = total;
    document.getElementById('operating-count').textContent = operational;
    document.getElementById('warning-count').textContent = warning;
    document.getElementById('offline-count').textContent = offline;
}

// Toggle Dark Mode
function toggleDarkMode() {
    document.body.classList.toggle('dark-mode');
    localStorage.setItem('darkMode', document.body.classList.contains('dark-mode'));
}

// Load Dark Mode Preference
if (localStorage.getItem('darkMode') === 'true') {
    document.body.classList.add('dark-mode');
    document.getElementById('dark-mode').checked = true;
}

// Update Last Updated Time
function updateLastUpdated() {
    const now = new Date().toLocaleString();
    document.getElementById('last-updated').textContent = now;
}

// Add status badge styling
const style = document.createElement('style');
style.textContent = `
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 500;
    }
    .status-operational {
        background: #c8e6c9;
        color: #2e7d32;
    }
    .status-warning {
        background: #ffe0b2;
        color: #e65100;
    }
    .status-offline {
        background: #ffcccc;
        color: #c62828;
    }
    .status-unknown {
        background: #e0e0e0;
        color: #616161;
    }
`;
document.head.appendChild(style);
