"""
Restaurant Booking Agent — deployed on Amazon Bedrock AgentCore Runtime.

How it works:
  • BedrockAgentCoreApp wraps the agent and exposes an HTTP /invocations endpoint
    that AgentCore Runtime calls when a user message arrives.
  • The interactive while-loop and manual token-fetch are removed; AgentCore handles
    session management, authentication, and scaling automatically.
  • The MCP client is created once per invocation inside the entrypoint so the
    connection is properly scoped to each serverless session.

Deployment (after installing deps):
    pip install bedrock-agentcore strands-agents bedrock-agentcore-starter-toolkit

    # Configure (creates .bedrock_agentcore.yaml)
    agentcore configure -e restaurant_agent.py --disable-memory

    # Deploy to AgentCore Runtime
    agentcore launch

    # Test
    agentcore invoke '{"prompt": "Is there a table for 2 available tonight at 7pm?"}'
"""

import logging
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client
import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration  ← keep your existing values
# ---------------------------------------------------------------------------
CLIENT_ID = "2nist1p754n4c3vig2dvg88u38"
CLIENT_SECRET = "3e2do63tdk9ou7j04ekdopdi9c90qas0ip653jl5jdl7qc9r0fj"
TOKEN_URL = (
    "https://us-east-18z2ixourg.auth.us-east-1.amazoncognito.com/oauth2/token"
)
GATEWAY_URL = (
    "https://lambda-agentcore-gateway-zr0uqivebq.gateway.bedrock-agentcore"
    ".us-east-1.amazonaws.com/mcp"
)

# ---------------------------------------------------------------------------
# AgentCore application
# ---------------------------------------------------------------------------
app = BedrockAgentCoreApp()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fetch_access_token() -> str:
    """Obtain a Cognito client-credentials access token."""
    response = requests.post(
        TOKEN_URL,
        data=(
            f"grant_type=client_credentials"
            f"&client_id={CLIENT_ID}"
            f"&client_secret={CLIENT_SECRET}"
        ),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def get_all_tools(client: MCPClient) -> list:
    """Paginate through all available MCP tools."""
    tools, pagination_token = [], None
    while True:
        page = client.list_tools_sync(pagination_token=pagination_token)
        tools.extend(page)
        pagination_token = page.pagination_token
        if pagination_token is None:
            break
    return tools


# ---------------------------------------------------------------------------
# Entrypoint — called by AgentCore Runtime on every invocation
# ---------------------------------------------------------------------------
@app.entrypoint
def invoke(payload: dict) -> dict:
    """
    AgentCore calls this function with the JSON body sent to the runtime.
    Expected payload shape: {"prompt": "<user message>"}
    """
    user_message = payload.get("prompt", "")
    if not user_message:
        return {"result": "Please provide a prompt."}

    logger.info("Received prompt: %s", user_message)

    # Obtain a fresh token for each invocation (tokens are short-lived)
    access_token = fetch_access_token()

    # Build the MCP transport factory (lambda keeps it lazy)
    def transport_factory():
        return streamablehttp_client(
            GATEWAY_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # Connect to MCP, build the Strands agent, and invoke — all within the
    # same context so the connection is cleanly closed afterwards.
    with MCPClient(transport_factory, startup_timeout=30) as mcp_client:
        tools = get_all_tools(mcp_client)
        logger.info("Loaded %d MCP tools: %s", len(tools), [t.tool_name for t in tools])

        bedrock_model = BedrockModel(
            model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            region_name="us-east-1",
        )

        agent = Agent(
            name="RestaurantBookingAgent",
            system_prompt=(
                "You are a restaurant booking agent. "
                "Help users check table availability and make reservations."
            ),
            model=bedrock_model,
            tools=tools,
        )

        response = agent(user_message)

    return {"result": str(response)}


# ---------------------------------------------------------------------------
# Local development entry-point
# Run:  python restaurant_agent.py
# Then: curl -X POST http://localhost:8080/invocations \
#            -H 'Content-Type: application/json' \
#            -d '{"prompt": "Any tables for 2 tonight?"}'
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run()