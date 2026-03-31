"""
One-time script: attach Cognito JWT inbound authorizer to your AgentCore Runtime.
Run ONCE after deploying with: python setup_inbound_auth.py
"""
import boto3
import json
# ── Fill these in ──────────────────────────────────────────────────────────
REGION          = "us-east-1"
AGENT_RUNTIME_ID = "agent_core_app-4t5viPEqr7"      # from agentcore launch output
USER_POOL_ID    = "us-east-1_8Z2IXourG"   # e.g. us-east-1_xxxxxxxx
CLIENT_ID       = "2nist1p754n4c3vig2dvg88u38"
# ──────────────────────────────────────────────────────────────────────────

DISCOVERY_URL = (
    f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
    "/.well-known/openid-configuration"
)

client = boto3.client("bedrock-agentcore-control", region_name=REGION)

# ── Step 1: fetch existing runtime config ─────────────────────────────────
print(f"Fetching existing runtime config for: {AGENT_RUNTIME_ID}")
existing = client.get_agent_runtime(agentRuntimeId=AGENT_RUNTIME_ID)
print("Existing config fetched.")

# Uncomment to inspect all available fields:
# print(json.dumps(existing, indent=2, default=str))

# ── Step 2: update with authorizer, preserving all required fields ─────────
print(f"\nAttaching Cognito JWT authorizer...")
print(f"  Discovery URL : {DISCOVERY_URL}")
print(f"  Allowed client: {CLIENT_ID}")

response = client.update_agent_runtime(
    agentRuntimeId       = AGENT_RUNTIME_ID,
    agentRuntimeArtifact = existing["agentRuntimeArtifact"],
    roleArn              = existing["roleArn"],
    networkConfiguration = existing["networkConfiguration"],

    # ← the new part we're adding
    authorizerConfiguration={
        "customJWTAuthorizer": {
            "discoveryUrl":   DISCOVERY_URL,
            "allowedClients": [CLIENT_ID],
        }
    },

    # preserve optional fields if they exist
    **({"description": existing["description"]} if existing.get("description") else {}),
    **({"environmentVariables": existing["environmentVariables"]} if existing.get("environmentVariables") else {}),
)

print("\nInbound auth configured successfully!")
print(f"  Runtime ARN : {response.get('agentRuntimeArn')}")
print(f"  Status      : {response.get('status')}")