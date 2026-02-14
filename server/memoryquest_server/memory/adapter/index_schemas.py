"""Azure AI Search index schema definition.

Provides the index schema as a plain dict for SDK-based index creation
and a helper function to create/update the index programmatically.
"""

from __future__ import annotations

from memory.config import (
    AZURE_SEARCH_SEMANTIC_CONFIG_NAME,
    AZURE_SEARCH_VECTOR_DIM,
    MEMORY_INDEX_NAME,
)

INDEX_FIELDS = [
    {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
    {"name": "agent_id", "type": "Edm.String", "filterable": True},
    {"name": "tenant_id", "type": "Edm.String", "filterable": True},
    {"name": "user_id", "type": "Edm.String", "filterable": True},
    {
        "name": "ts",
        "type": "Edm.DateTimeOffset",
        "sortable": True,
        "filterable": True,
    },
    {"name": "text", "type": "Edm.String", "searchable": True},
    {
        "name": "tags",
        "type": "Collection(Edm.String)",
        "filterable": True,
    },
    {
        "name": "vector",
        "type": "Collection(Edm.Single)",
        "searchable": True,
        "dimensions": AZURE_SEARCH_VECTOR_DIM,
        "vectorSearchProfile": "default-vector-profile",
    },
    {"name": "metadata_json", "type": "Edm.String", "retrievable": True},
    {"name": "expires_at", "type": "Edm.DateTimeOffset", "filterable": True},
]


def get_index_definition() -> dict:
    """Return the full JSON-serialisable index definition."""
    return {
        "name": MEMORY_INDEX_NAME,
        "fields": INDEX_FIELDS,
        "vectorSearch": {
            "algorithms": [
                {
                    "name": "hnsw-algo",
                    "kind": "hnsw",
                    "hnswParameters": {
                        "m": 4,
                        "efConstruction": 400,
                        "efSearch": 500,
                        "metric": "cosine",
                    },
                }
            ],
            "profiles": [
                {
                    "name": "default-vector-profile",
                    "algorithm": "hnsw-algo",
                }
            ],
        },
        "semantic": {
            "configurations": [
                {
                    "name": AZURE_SEARCH_SEMANTIC_CONFIG_NAME,
                    "prioritizedFields": {
                        "contentFields": [{"fieldName": "text"}],
                    },
                }
            ]
        },
    }
