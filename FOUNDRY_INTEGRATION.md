# Microsoft Foundry Agent Integration

This document describes the Microsoft Azure AI Foundry agent integration in the Agentic Memory Quest application.

## Overview

The Foundry agent provides integration with Microsoft Azure AI Foundry, Microsoft's platform for building and deploying AI agents with advanced memory management and orchestration capabilities.

## Architecture

### Backend Components

1. **FoundryAgent Class** (`server/memoryquest_server/agents/foundry_agent.py`)
   - Wraps the Azure AI Foundry client
   - Provides agent initialization with fallback support
   - Implements stubbed memory management methods

2. **API Endpoints** (`server/memoryquest_server/server.py`)
   - `POST /foundry` - Chat with Foundry agent
   - `POST /foundry/memories` - Retrieve user memories

3. **Client Initialization**
   - Uses `AIProjectClient` from `azure-ai-projects` (Foundry portal pattern)
   - References an existing agent created in the Foundry portal (no runtime creation)
   - Auth via Azure AD (`DefaultAzureCredential`)
   - Graceful fallback to GPT-4 client if not configured

### Frontend Components

- Dropdown option "Foundry" in the Agent Interface selector (`web/src/App.jsx`)

## Authentication

### Azure AD Authentication

The Foundry agent uses Azure Active Directory authentication via `DefaultAzureCredential`, which supports multiple authentication methods in the following order:

1. **Environment Variables** - Service Principal authentication
   ```bash
   AZURE_CLIENT_ID
   AZURE_TENANT_ID
   AZURE_CLIENT_SECRET
   ```

2. **Managed Identity** - When running in Azure (App Service, Functions, VMs, etc.)

3. **Azure CLI** - Uses credentials from `az login`

4. **Azure PowerShell** - Uses credentials from `Connect-AzAccount`

5. **Interactive Browser** - Prompts for login if other methods fail

### Required Azure RBAC Roles

The identity used for authentication must have one of these roles on the Azure AI Foundry resource:
- **Azure AI Developer** (recommended for development)
- **Azure AI User** (for production use)

### Important Notes

- ⚠️ **API key authentication is NOT supported** by Azure AI Foundry
- Ensure the service principal or managed identity has proper RBAC permissions

## Configuration

### Environment Variables

#### Required

```bash
# Azure AI Foundry project endpoint
# Format: https://<resource-name>.services.ai.azure.com/api/projects/<project-name>
AZURE_FOUNDRY_ENDPOINT=https://your-resource.services.ai.azure.com/api/projects/your-project

# Agent name as defined in the Foundry portal
AZURE_FOUNDRY_AGENT_NAME=your-foundry-agent-name
```

#### Optional (endpoint construction)

Instead of `AZURE_FOUNDRY_ENDPOINT`, you can build it from parts:

```bash
AZURE_FOUNDRY_RESOURCE_NAME=your-resource
AZURE_FOUNDRY_PROJECT=your-project
```

Or set the base resource endpoint directly:

```bash
AZURE_FOUNDRY_RESOURCE_ENDPOINT=https://your-resource.services.ai.azure.com
AZURE_FOUNDRY_PROJECT=your-project
```

#### For Service Principal Authentication

```bash
# Azure AD Service Principal credentials
AZURE_CLIENT_ID=your-client-id-here
AZURE_TENANT_ID=your-tenant-id-here
AZURE_CLIENT_SECRET=your-client-secret-here
```

### Example Configurations

#### Development with Azure CLI

```bash
# Login with Azure CLI first
az login

# Set the Foundry endpoint
export AZURE_FOUNDRY_ENDPOINT="https://your-resource.services.ai.azure.com/api/projects/your-project"

# Set the Foundry agent name
export AZURE_FOUNDRY_AGENT_NAME="your-foundry-agent-name"

# Run the server
cd server/memoryquest_server
python3 -m uvicorn server:app --reload
```

#### Production with Service Principal

```bash
# Set service principal credentials
export AZURE_CLIENT_ID="12345678-1234-1234-1234-123456789abc"
export AZURE_TENANT_ID="87654321-4321-4321-4321-abcdef123456"
export AZURE_CLIENT_SECRET="your-secret-value"

# Set the Foundry endpoint
export AZURE_FOUNDRY_ENDPOINT="https://your-resource.services.ai.azure.com/api/projects/your-project"

# Set the Foundry agent name
export AZURE_FOUNDRY_AGENT_NAME="your-foundry-agent-name"

# Run the server
cd server/memoryquest_server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

#### Azure App Service (Managed Identity)

When deployed to Azure App Service with Managed Identity enabled:

1. Enable System-assigned or User-assigned Managed Identity in App Service
2. Assign Azure AI Developer or Azure AI User role to the Managed Identity
3. Set `AZURE_FOUNDRY_ENDPOINT` and `AZURE_FOUNDRY_AGENT_NAME` environment variables
4. The app will automatically use Managed Identity for authentication

```bash
AZURE_FOUNDRY_ENDPOINT=https://your-resource.services.ai.azure.com/api/projects/your-project
AZURE_FOUNDRY_AGENT_NAME=your-foundry-agent-name
```

## Fallback Behavior

If the Foundry endpoint is not configured or initialization fails:
- The agent falls back to using the GPT-4 client
- A warning message is logged to the console
- The application continues to work with reduced functionality

## Memory Management

### Current Implementation (Stubbed)

The Foundry agent currently includes stubbed memory management methods:

- `get_memories(username)` - Returns empty/stub memory data
- `delete_user_memories(username)` - Simulates memory deletion

### Future Implementation

To implement actual memory management:

1. **Create FoundryMemoryTool** as a ContextProvider
   - Store conversation history in Azure AI Foundry's memory store
   - Retrieve relevant context based on conversation_id or user identity
   - Integrate with Foundry's agent memory capabilities

2. **Update agent initialization** in `foundry_agent.py`:
   ```python
   from tools.foundry_memory_tool import FoundryMemoryTool
   
   memory_provider = FoundryMemoryTool()
   self._agent = Agent(
       client=foundry_client,
       instructions=INSTRUCTIONS,
       context_provider=memory_provider,  # Add memory provider
       name="foundry-agent"
   )
   ```

3. **Implement memory operations** in FoundryMemoryTool:
   - Use Azure AI Foundry APIs for memory storage
   - Implement search and retrieval based on user context
   - Handle conversation threading and context management

## Testing

### Local Testing

```bash
# Run the integration tests
cd /home/runner/work/agentic-memory-quest/agentic-memory-quest
python3 /tmp/test_foundry_integration.py
```

### Expected Output

```
============================================================
Microsoft Foundry Agent Integration Tests
============================================================
Testing Foundry agent import...
✓ FoundryAgent imported successfully

Testing Azure AI Projects client availability...
✓ AIProjectClient is available

Testing Azure identity availability...
✓ DefaultAzureCredential is available

Testing Foundry agent creation...
✓ FoundryAgent is configured and ready

============================================================
Test Results Summary
============================================================
Import                         ✓ PASS
Azure AI Projects Client       ✓ PASS
Azure Identity                 ✓ PASS
Agent Creation                 ✓ PASS
============================================================
All tests passed!
```

## Troubleshooting

### Common Issues

#### 1. Authentication Failures

**Error**: `DefaultAzureCredential failed to retrieve a token`

**Solutions**:
- Verify Azure CLI is logged in: `az login`
- Check service principal credentials are set correctly
- Ensure the identity has proper RBAC roles on the Foundry resource
- Try: `az account get-access-token --resource "https://ai.azure.com"`

#### 2. Endpoint Configuration Issues

**Error**: `AZURE_FOUNDRY_ENDPOINT not set`

**Solutions**:
- Set the environment variable with correct format
- Verify the endpoint URL is correct
- Check that the resource and project names match your Azure setup

#### 3. Permission Errors

**Error**: `Insufficient permissions` or `403 Forbidden`

**Solutions**:
- Assign Azure AI Developer or Azure AI User role to the identity
- Check RBAC assignments in Azure Portal
- Wait a few minutes for role assignments to propagate

#### 4. Module Import Errors

**Error**: `No module named 'azure.ai.projects'`

**Solutions**:
```bash
cd server/memoryquest_server
pip3 install -r requirements.txt
```

If you see errors about `agent_framework.azure`, ensure `agent-framework-azure-ai` is installed (it is included in `requirements.txt`).

## Dependencies

### Python Packages

- `agent-framework` - Core Agent Framework
- `azure-ai-projects` - Azure AI Foundry Projects + OpenAI client access
- `azure-identity` - Azure AD authentication
- `fastapi[standard]` - Web framework
- `python-dotenv` - Environment variable management

All dependencies are listed in `server/memoryquest_server/requirements.txt`.

## API Reference

### POST /foundry

Send a message to the Foundry agent.

**Request Body**:
```json
{
  "username": "john_doe",
  "messages": [
    {
      "role": "user",
      "content": "Hello, I'd like to book a spa treatment"
    }
  ]
}
```

**Response**:
```json
{
  "message": "I'd be happy to help you book a spa treatment...",
  "usage": {
    "inputTokenCount": 45,
    "outputTokenCount": 128,
    "totalTokenCount": 173
  }
}
```

### POST /foundry/memories

Retrieve memories for a user.

**Request Body**:
```json
{
  "username": "john_doe",
  "query": "spa preferences"
}
```

**Response**:
```json
{
  "message": {
    "memories": [],
    "count": 0,
    "source": "foundry_stub",
    "note": "Foundry memory retrieval not yet implemented"
  }
}
```


> Note: A delete endpoint is not currently exposed for Foundry in `server.py`.

## Security Considerations

1. **Credential Storage**
   - Never commit credentials to source control
   - Use Azure Key Vault for production secrets
   - Prefer Managed Identity over service principals when possible

2. **RBAC Permissions**
   - Follow principle of least privilege
   - Use Azure AI User role for production agents
   - Regularly audit role assignments

3. **Network Security**
   - Use private endpoints for Azure AI Foundry when possible
   - Implement proper firewall rules
   - Enable diagnostic logging

## Related Documentation

- [Azure AI Foundry Documentation](https://learn.microsoft.com/azure/ai-studio/)
- [Agent Framework Documentation](https://github.com/microsoft/agent-framework)
- [DefaultAzureCredential Documentation](https://learn.microsoft.com/python/api/azure-identity/azure.identity.defaultazurecredential)
- [Azure RBAC Documentation](https://learn.microsoft.com/azure/role-based-access-control/)

## Support

For issues specific to:
- **Foundry Integration**: Check this README and troubleshooting section
- **Azure AI Foundry**: Refer to Microsoft Azure support
- **Agent Framework**: Visit the [Agent Framework GitHub](https://github.com/microsoft/agent-framework)
- **Application Issues**: Create an issue in the repository
