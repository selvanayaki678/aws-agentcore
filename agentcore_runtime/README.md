# Learning AWS Bedrock AgentCore

This project is a hands-on example of how AgentCore works. The restaurant booking theme is just the use case — the real focus is understanding AgentCore's building blocks.

---

## What is AgentCore?

AgentCore is AWS's managed platform for **hosting and running AI agents**. Instead of you managing servers, auth, and scaling — AgentCore handles all of that. You just write the agent logic.

Think of it like this:

```
Without AgentCore:  You manage servers + auth + scaling + endpoints + sessions
With AgentCore:     You write agent code → AWS handles everything else
```

---

## AgentCore Building Blocks

### 1. AgentCore Runtime
**What it is:** The managed environment that runs your agent code.

```python
app = BedrockAgentCoreApp()

@app.entrypoint
def invoke(payload: dict) -> dict:
    # Your agent logic goes here
    # AgentCore calls this on every user message
```

- You don't manage any server
- AgentCore exposes a `/invocations` endpoint automatically
- Handles scaling, sessions, and inbound security (IAM) for you
- Your only job is to handle the `payload` and return a response

---

### 2. AgentCore Gateway
**What it is:** A managed middle layer that connects your agent to external tools (like Lambda functions).

```
Agent  →  "I need to check table availability"
       →  Gateway  →  Lambda Function
       ←  Gateway  ←  {"available": true}
Agent  ←  uses the result to respond
```

- You register your Lambda functions as **tools** in the Gateway
- The Gateway exposes them as **MCP (Model Context Protocol)** tools
- The agent picks them up automatically — no hardcoding needed
- Gateway handles routing + auth between agent and Lambda

---

### 3. MCP (Model Context Protocol)
**What it is:** A standard way for AI agents to discover and call tools.

```python
# Agent connects to Gateway via MCP
with MCPClient(transport_factory) as mcp_client:
    tools = get_all_tools(mcp_client)   # discovers all available tools
    agent = Agent(tools=tools, ...)     # agent now knows what it can do
```

- Instead of hardcoding tool names, the agent **discovers** them at runtime
- Add a new Lambda tool to the Gateway → agent picks it up automatically
- No code change needed in the agent when tools change

---

### 4. Outbound Auth (Cognito)
**What it is:** How the agent proves its identity when calling the Gateway.

```
Agent → fetches a short-lived token from Cognito
      → attaches token to every Gateway request
Gateway → validates the token → allows the call
```

```python
# Agent fetches token before every call
access_token = fetch_access_token()

# Token attached to MCP connection
streamablehttp_client(GATEWAY_URL, headers={"Authorization": f"Bearer {access_token}"})
```

- Uses **OAuth 2.0 client credentials** flow (machine-to-machine)
- Token is short-lived — fetched fresh on every invocation
- This is called **outbound auth** — the agent authenticating itself to an external service

---

### 5. Inbound Auth (IAM — automatic)
**What it is:** How AgentCore protects your agent from unauthorized callers.

- You don't write any code for this
- AgentCore Runtime uses **AWS IAM** to verify every incoming request
- Only callers with the right AWS permissions can reach your agent
- This is called **inbound auth** — protecting the door into your agent

---

## How All the Pieces Fit Together

```
User Message
    │
    ▼
┌─────────────────────────────┐
│   AgentCore Runtime         │  ← inbound auth (IAM) handled here
│   @app.entrypoint           │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────┐
│   Strands Agent             │  ← AI brain (Claude via Bedrock)
│   + MCP tools loaded        │
└────────────┬────────────────┘
             │  outbound auth (Cognito token)
             ▼
┌─────────────────────────────┐
│   AgentCore Gateway         │  ← tool routing layer
└────────────┬────────────────┘
             │  IAM role
             ▼
┌─────────────────────────────┐
│   Lambda Function           │  ← actual tool logic lives here
└─────────────────────────────┘
```

---

## The Lifecycle of One Agent Call

```
1. User sends a message
2. AgentCore Runtime receives it → verifies IAM auth → calls invoke()
3. invoke() fetches a Cognito token
4. MCPClient connects to Gateway using that token
5. Agent discovers available tools (checkAvailability, bookTable)
6. Agent decides which tool to call based on the user's message
7. Gateway receives the tool call → invokes Lambda
8. Lambda runs the logic → returns result to Gateway → back to Agent
9. Agent uses the result to form a response
10. Response returned to the user
```

---

## Key Concepts Summary

| Concept | What to Remember |
|---------|-----------------|
| **AgentCore Runtime** | Hosts your agent — no server management needed |
| **AgentCore Gateway** | Connects agent to tools (Lambda) via MCP |
| **MCP** | Standard protocol for agent tool discovery |
| **Inbound Auth** | IAM protects your agent automatically |
| **Outbound Auth** | Cognito token lets agent call the Gateway |
| **Strands Agent** | The AI framework used to build the agent logic |

---

## How to Run This Example

```bash
# Install
pip install bedrock-agentcore strands-agents bedrock-agentcore-starter-toolkit

# Configure AgentCore
agentcore configure -e agent-core-app_create.py --disable-memory

# Deploy
agentcore launch

# Test
agentcore invoke '{"prompt": "Any tables for 2 tonight at 7?"}'
```

### Test Locally First

```bash
python agent-core-app_create.py

curl -X POST http://localhost:8080/invocations \
     -H 'Content-Type: application/json' \
     -d '{"prompt": "Any tables for 2 tonight?"}'
```