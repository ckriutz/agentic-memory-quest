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
    from azure.search.documents.indexes.models import SearchIndex

    credential = AzureKeyCredential(AZURE_SEARCH_API_KEY)
    client = SearchIndexClient(endpoint=AZURE_SEARCH_ENDPOINT, credential=credential)

    index_def = get_index_definition()
    print(f"Creating/updating index '{MEMORY_INDEX_NAME}' at {AZURE_SEARCH_ENDPOINT}...")

    try:
        client.create_or_update_index(SearchIndex(**index_def))
        print(f"✓ Index '{MEMORY_INDEX_NAME}' is ready.")
    except Exception as e:
        print(f"✗ Index operation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    create_or_update_index()
