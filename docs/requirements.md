### Refined Requirements

- **FastAPI Backend**  
  - Expose an endpoint at `/foundry` that calls the Foundry agent's API endpoint.  
  - Parse the response from the Foundry API.  
  - Return the formatted results to the React frontend.

- **React Frontend**  
  - Include a dropdown option for 'Foundry'.  
  - When 'Foundry' is selected, it should trigger the `/foundry` endpoint in the FastAPI backend.