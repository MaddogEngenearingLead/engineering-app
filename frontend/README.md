# Frontend - P&ID Dashboard

A modern, responsive HTML/CSS/JavaScript dashboard for monitoring engineering assets and process instrumentation diagrams.

## Features

- **Dashboard Overview**: KPI cards and system status visualization
- **Equipment Inventory**: Add, view, edit, and delete equipment assets (pumps, valves, vessels, instruments)
- **Pipeline Management**: Create and track pipeline configurations
- **Settings Panel**: API configuration, display options, and system information
- **Dark Mode**: Toggle between light and dark themes
- **Responsive Design**: Works on desktop, tablet, and mobile devices

## Quick Start

1. Open `frontend/index.html` in your web browser
2. Navigate through the dashboard sections using the top navigation bar
3. Add equipment and pipelines to track your assets

## Data Storage

Currently uses browser localStorage for data persistence. Equipment and pipeline data is saved locally.

## Future Enhancements

- Connect to the FastAPI backend for persistent database storage
- Real-time asset status updates from sensors
- Advanced P&ID visualization
- Equipment health analytics and trending
- Alarm and notification system
- User authentication and role-based access
