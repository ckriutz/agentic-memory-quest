#!/usr/bin/env python3
"""Create (or update) the Azure AI Search index for the memory layer.

Usage:
    python create_index.py

Requires AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_API_KEY in the environment.
"""

from __future__ import annotations

import os
import sys

# Allow running from repo root or scripts/memory/.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "server", "memoryquest_server"))

from dotenv import load_dotenv

load_dotenv()

from memory.adapter.index_schemas import get_index_definition
from memory.config import AZURE_SEARCH_API_KEY, AZURE_SEARCH_ENDPOINT, MEMORY_INDEX_NAME


def create_or_update_index() -> None:
    if not AZURE_SEARCH_ENDPOINT or not AZURE_SEARCH_API_KEY:
        print("ERROR: AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_API_KEY must be set.")
        sys.exit(1)

    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import (
        SearchIndex,
        SearchField,
        SearchFieldDataType,
        SearchableField,
        SimpleField,
        VectorSearch,
        HnswAlgorithmConfiguration,
        HnswParameters,
        VectorSearchProfile,
        SemanticConfiguration,
        SemanticSearch,
        SemanticPrioritizedFields,
        SemanticField,
    )

    credential = AzureKeyCredential(AZURE_SEARCH_API_KEY)
    client = SearchIndexClient(endpoint=AZURE_SEARCH_ENDPOINT, credential=credential)

    index_def = get_index_definition()
    dim = index_def["fields"][7]["dimensions"]  # vector field
    sem_config_name = index_def["semantic"]["configurations"][0]["name"]

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SimpleField(name="agent_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="tenant_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="user_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="ts", type=SearchFieldDataType.DateTimeOffset, sortable=True, filterable=True),
        SearchableField(name="text", type=SearchFieldDataType.String),
        SimpleField(name="tags", type=SearchFieldDataType.Collection(SearchFieldDataType.String), filterable=True),
        SearchField(
            name="vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=dim,
            vector_search_profile_name="default-vector-profile",
        ),
        SimpleField(name="metadata_json", type=SearchFieldDataType.String, retrievable=True),
        SimpleField(name="expires_at", type=SearchFieldDataType.DateTimeOffset, filterable=True),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="hnsw-algo",
                parameters=HnswParameters(m=4, ef_construction=400, ef_search=500, metric="cosine"),
            )
        ],
        profiles=[
            VectorSearchProfile(name="default-vector-profile", algorithm_configuration_name="hnsw-algo"),
        ],
    )

    semantic_search = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name=sem_config_name,
                prioritized_fields=SemanticPrioritizedFields(
                    content_fields=[SemanticField(field_name="text")]
                ),
            )
        ]
    )

    index = SearchIndex(
        name=MEMORY_INDEX_NAME,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )

    print(f"Creating/updating index '{MEMORY_INDEX_NAME}' at {AZURE_SEARCH_ENDPOINT}...")

    try:
        client.create_or_update_index(index)
        print(f"✓ Index '{MEMORY_INDEX_NAME}' is ready.")
    except Exception as e:
        print(f"✗ Index operation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    create_or_update_index()
