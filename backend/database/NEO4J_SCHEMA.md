Neo4j Graph Database Setup

Neo4j is used to store and query the topology graph of P&ID equipment and connections.

Key nodes:
- Equipment (pump, valve, vessel, instrument)
- Pipeline (logical groupings)
- Connection (edges between equipment)

Key relationships:
- CONNECTED_TO (equipment to equipment)
- CONTAINS (pipeline contains equipment)
- FLOWS_TO (directional flow)

Example queries:
- Match all equipment connected to a specific pump
- Find all paths between two pieces of equipment
- Get all downstream equipment from a valve
