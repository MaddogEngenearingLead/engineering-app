from py2neo import Graph
from app.core.config import settings

# Neo4j connection
NEO4J_URL = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "password")

graph = Graph(NEO4J_URL, auth=NEO4J_AUTH)


def get_graph():
    return graph
