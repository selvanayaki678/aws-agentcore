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

### 4. Agentcore gateway Inbound Auth (Cognito)
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
- This is called **Inbound auth** — the agent authenticating itself to an external service

---

### 5. Agentcore Gateway Outbound Auth (IAM)
**What it is:** How AgentCore Gateway connects securely to your Lambda function.

-  AgentCore Gateway uses **AWS IAM** to authenticate its connection to your Lambda
- Only the Gateway (with the right IAM permissions) can invoke your Lambda function
- This is called **Outbound auth** — ensuring only authorized services can trigger your Lambda

---
### 6. Tool Discovery via Inline Schema
**What it is:** How AgentCore Gateway knows what tools your Lambda exposes.

When you register a Lambda with the Gateway, you don't just point to the function —
you also provide an **inline schema** that describes the tool:
```json
{
  "name": "checkAvailability",
  "description": "Check if a table is available at a given time",
  "parameters": {
    "date": { "type": "string" },
    "time": { "type": "string" },
    "party_size": { "type": "integer" }
  }
}
```

- This schema is registered **once** when you set up the Gateway
- The Gateway reads it and **exposes the tool as MCP**
- When the agent connects via MCP, it discovers this tool automatically
- The agent never talks to Lambda directly — it only sees the MCP interface
```
Lambda (with inline schema)
    │
    │  registered into
    ▼
AgentCore Gateway  ──→  exposes as MCP tool
                            │
                            │  agent discovers at runtime
                            ▼
                        Strands Agent knows:
                        "I have a checkAvailability tool"
```

**This is where MCP becomes meaningful** — the inline schema is what gets
translated into an MCP tool definition that the agent can discover and call
without any hardcoding.
---

## How All the Pieces Fit Together

```
User Message
    │
    ▼
┌─────────────────────────────┐
│   AgentCore Runtime         │  
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

## Arechitecture
![Agentcore (3)](https://github.com/user-attachments/assets/74698333-74fd-4e18-a57f-98e4bc7870a6)

## The Lifecycle of One Agent Call

```
1. User sends a message
2. AgentCore Runtime receives it 
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
| **Agent Outbound Auth** | Cognito token lets agent call the Gateway |
| **Gateway Inbound Auth** | Gateway uses the IAM role to call the lambda |
| **Strands Agent** | The AI framework used to build the agent logic |

---

## How to Run This Example

```bash
# Install
pip install bedrock-agentcore strands-agents bedrock-agentcore-starter-toolkit

# Configure AgentCore
agentcore configure -e restruant_booking_agent.py --disable-memory

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
