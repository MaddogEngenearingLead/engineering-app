// P&ID Visualizer - Process & Instrumentation Diagram drawing engine

const PIDVisualizer = (() => {
    let canvas, ctx;
    let scale = 1;
    let offsetX = 0, offsetY = 0;
    let selectedAsset = null;

    const diagramData = {
        main: {
            title: "Main Process Line",
            equipment: [
                { id: "P-101", type: "pump", x: 80, y: 150, label: "Feed Pump", status: "operational", pressure: "45 PSI", temp: "68°F", flow: "120 GPM" },
                { id: "V-101", type: "valve", x: 150, y: 150, label: "Inlet Valve", status: "operational", pressure: "45 PSI", temp: "68°F", flow: "120 GPM" },
                { id: "E-101", type: "vessel", x: 240, y: 150, label: "Mix Tank", status: "operational", pressure: "50 PSI", temp: "72°F", flow: "120 GPM" },
                { id: "I-101", type: "instrument", x: 240, y: 230, label: "Pressure Indicator", status: "warning", pressure: "52 PSI", temp: "--", flow: "--" },
                { id: "V-102", type: "valve", x: 310, y: 150, label: "Outlet Valve", status: "operational", pressure: "48 PSI", temp: "74°F", flow: "118 GPM" },
                { id: "P-102", type: "pump", x: 380, y: 150, label: "Transfer Pump", status: "operational", pressure: "48 PSI", temp: "74°F", flow: "118 GPM" },
            ],
            connections: [
                { from: "P-101", to: "V-101" },
                { from: "V-101", to: "E-101" },
                { from: "E-101", to: "V-102" },
                { from: "V-102", to: "P-102" },
            ]
        },
        reactor: {
            title: "Reactor Unit",
            equipment: [
                { id: "R-101", type: "vessel", x: 200, y: 120, label: "Reactor Vessel", status: "operational", pressure: "100 PSI", temp: "185°F", flow: "95 GPM" },
                { id: "H-101", type: "instrument", x: 200, y: 200, label: "Temperature Control", status: "operational", pressure: "--", temp: "185°F", flow: "--" },
                { id: "P-201", type: "pump", x: 80, y: 120, label: "Feed Pump", status: "operational", pressure: "95 PSI", temp: "180°F", flow: "95 GPM" },
                { id: "V-201", type: "valve", x: 140, y: 120, label: "Flow Control", status: "operational", pressure: "95 PSI", temp: "182°F", flow: "95 GPM" },
                { id: "V-202", type: "valve", x: 260, y: 120, label: "Discharge", status: "operational", pressure: "98 PSI", temp: "184°F", flow: "94 GPM" },
                { id: "C-101", type: "pump", x: 320, y: 120, label: "Product Pump", status: "operational", pressure: "98 PSI", temp: "184°F", flow: "94 GPM" },
            ],
            connections: [
                { from: "P-201", to: "V-201" },
                { from: "V-201", to: "R-101" },
                { from: "R-101", to: "V-202" },
                { from: "V-202", to: "C-101" },
            ]
        },
        separator: {
            title: "Separator Train",
            equipment: [
                { id: "S-101", type: "vessel", x: 150, y: 100, label: "Primary Separator", status: "operational", pressure: "75 PSI", temp: "140°F", flow: "200 GPM" },
                { id: "S-102", type: "vessel", x: 300, y: 100, label: "Secondary Separator", status: "operational", pressure: "60 PSI", temp: "135°F", flow: "180 GPM" },
                { id: "V-301", type: "valve", x: 100, y: 100, label: "Inlet Valve", status: "operational", pressure: "75 PSI", temp: "140°F", flow: "200 GPM" },
                { id: "V-302", type: "valve", x: 225, y: 100, label: "Transfer Valve", status: "operational", pressure: "70 PSI", temp: "138°F", flow: "195 GPM" },
                { id: "D-101", type: "instrument", x: 150, y: 180, label: "Level Gauge", status: "warning", pressure: "--", temp: "--", flow: "--" },
                { id: "V-303", type: "valve", x: 350, y: 100, label: "Outlet Valve", status: "operational", pressure: "58 PSI", temp: "133°F", flow: "175 GPM" },
            ],
            connections: [
                { from: "V-301", to: "S-101" },
                { from: "S-101", to: "V-302" },
                { from: "V-302", to: "S-102" },
                { from: "S-102", to: "V-303" },
            ]
        }
    };

    function init() {
        canvas = document.getElementById('pid-canvas');
        if (!canvas) return;
        
        ctx = canvas.getContext('2d');
        canvas.width = canvas.offsetWidth;
        canvas.height = 400;

        canvas.addEventListener('click', handleCanvasClick);
        canvas.addEventListener('wheel', handleZoom);
        canvas.addEventListener('mousemove', handleMouseMove);

        drawDiagram('main');
    }

    function drawDiagram(diagramType) {
        const diagram = diagramData[diagramType];
        if (!diagram) return;

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#f8faff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Draw connections first (so they appear behind equipment)
        diagram.connections.forEach(conn => {
            drawConnection(diagram, conn);
        });

        // Draw equipment
        diagram.equipment.forEach(equipment => {
            drawEquipment(equipment);
        });

        // Draw title
        ctx.fillStyle = '#122033';
        ctx.font = 'bold 16px Inter, sans-serif';
        ctx.fillText(diagram.title, 20, 25);
    }

    function drawEquipment(equipment) {
        const x = equipment.x * scale + offsetX;
        const y = equipment.y * scale + offsetY;
        const size = 35 * scale;

        // Get color based on status
        let statusColor = '#22c55e';
        if (equipment.status === 'warning') statusColor = '#f59e0b';
        if (equipment.status === 'error') statusColor = '#ef4444';

        // Draw equipment symbol
        ctx.save();
        ctx.fillStyle = statusColor;
        ctx.strokeStyle = '#122033';
        ctx.lineWidth = 2;

        switch (equipment.type) {
            case 'pump':
                // Circle for pump
                ctx.beginPath();
                ctx.arc(x, y, size / 2, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
                ctx.fillStyle = 'white';
                ctx.font = 'bold 10px Inter, sans-serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText('P', x, y);
                break;

            case 'valve':
                // Triangle for valve
                ctx.beginPath();
                ctx.moveTo(x, y - size / 2);
                ctx.lineTo(x + size / 2, y + size / 2);
                ctx.lineTo(x - size / 2, y + size / 2);
                ctx.closePath();
                ctx.fill();
                ctx.stroke();
                ctx.fillStyle = 'white';
                ctx.font = 'bold 10px Inter, sans-serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText('V', x, y);
                break;

            case 'vessel':
                // Rectangle for vessel
                ctx.fillRect(x - size / 2, y - size / 2, size, size);
                ctx.strokeRect(x - size / 2, y - size / 2, size, size);
                ctx.fillStyle = 'white';
                ctx.font = 'bold 9px Inter, sans-serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText('E', x, y);
                break;

            case 'instrument':
                // Diamond for instrument
                ctx.beginPath();
                ctx.moveTo(x, y - size / 2);
                ctx.lineTo(x + size / 2, y);
                ctx.lineTo(x, y + size / 2);
                ctx.lineTo(x - size / 2, y);
                ctx.closePath();
                ctx.fill();
                ctx.stroke();
                ctx.fillStyle = 'white';
                ctx.font = 'bold 10px Inter, sans-serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText('I', x, y);
                break;
        }

        ctx.restore();

        // Draw label
        ctx.fillStyle = '#122033';
        ctx.font = '11px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(equipment.id, x, y + size / 2 + 20);
    }

    function drawConnection(diagram, conn) {
        const fromEquip = diagram.equipment.find(e => e.id === conn.from);
        const toEquip = diagram.equipment.find(e => e.id === conn.to);

        if (!fromEquip || !toEquip) return;

        const x1 = fromEquip.x * scale + offsetX;
        const y1 = fromEquip.y * scale + offsetY;
        const x2 = toEquip.x * scale + offsetX;
        const y2 = toEquip.y * scale + offsetY;

        ctx.strokeStyle = '#64748b';
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();

        // Draw arrow
        const angle = Math.atan2(y2 - y1, x2 - x1);
        const arrowSize = 8;
        ctx.fillStyle = '#64748b';
        ctx.beginPath();
        ctx.moveTo(x2, y2);
        ctx.lineTo(x2 - arrowSize * Math.cos(angle - Math.PI / 6), y2 - arrowSize * Math.sin(angle - Math.PI / 6));
        ctx.lineTo(x2 - arrowSize * Math.cos(angle + Math.PI / 6), y2 - arrowSize * Math.sin(angle + Math.PI / 6));
        ctx.closePath();
        ctx.fill();
    }

    function handleCanvasClick(e) {
        const rect = canvas.getBoundingClientRect();
        const clickX = (e.clientX - rect.left - offsetX) / scale;
        const clickY = (e.clientY - rect.top - offsetY) / scale;

        const diagram = diagramData[document.getElementById('diagram-select').value];
        const clickSize = 40;

        for (const equipment of diagram.equipment) {
            const dx = equipment.x - clickX;
            const dy = equipment.y - clickY;
            if (Math.sqrt(dx * dx + dy * dy) < clickSize) {
                selectAsset(equipment);
                return;
            }
        }

        selectedAsset = null;
        document.getElementById('selected-asset-info').classList.add('hidden');
    }

    function handleZoom(e) {
        e.preventDefault();
        const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
        scale *= zoomFactor;
        scale = Math.max(0.5, Math.min(3, scale));
        
        const diagram = document.getElementById('diagram-select').value;
        drawDiagram(diagram);
    }

    function handleMouseMove(e) {
        const rect = canvas.getBoundingClientRect();
        const moveX = (e.clientX - rect.left - offsetX) / scale;
        const moveY = (e.clientY - rect.top - offsetY) / scale;

        const diagram = diagramData[document.getElementById('diagram-select').value];
        let found = false;

        for (const equipment of diagram.equipment) {
            const dx = equipment.x - moveX;
            const dy = equipment.y - moveY;
            if (Math.sqrt(dx * dx + dy * dy) < 40) {
                canvas.style.cursor = 'pointer';
                found = true;
                break;
            }
        }

        if (!found) canvas.style.cursor = 'default';
    }

    function selectAsset(equipment) {
        selectedAsset = equipment;
        document.getElementById('asset-tag').textContent = equipment.id;
        document.getElementById('asset-type').textContent = equipment.type.charAt(0).toUpperCase() + equipment.type.slice(1);
        document.getElementById('asset-status').textContent = equipment.status.charAt(0).toUpperCase() + equipment.status.slice(1);
        document.getElementById('asset-pressure').textContent = equipment.pressure;
        document.getElementById('asset-temp').textContent = equipment.temp;
        document.getElementById('asset-flow').textContent = equipment.flow;
        document.getElementById('selected-asset-info').classList.remove('hidden');
    }

    return {
        init,
        drawDiagram: (type) => drawDiagram(type),
        resetZoom: () => {
            scale = 1;
            offsetX = 0;
            offsetY = 0;
            drawDiagram(document.getElementById('diagram-select').value);
        }
    };
})();

// Initialize P&ID visualizer when page loads
window.addEventListener('DOMContentLoaded', () => {
    PIDVisualizer.init();
});

function loadDiagram(type) {
    PIDVisualizer.drawDiagram(type);
}

function resetZoom() {
    PIDVisualizer.resetZoom();
}
