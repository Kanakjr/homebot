"""
n8n workflow management tools.
"""

import json
import logging

import aiohttp
from langchain_core.tools import tool

import config

log = logging.getLogger("homebot.tools.n8n")


def _headers() -> dict:
    return {"X-N8N-API-KEY": config.N8N_API_KEY, "Content-Type": "application/json"}


@tool
async def n8n_list_workflows() -> str:
    """List all n8n workflows with their names and active status."""
    url = f"{config.N8N_URL}/api/v1/workflows"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status == 200:
                data = await resp.json()
                workflows = data.get("data", data) if isinstance(data, dict) else data
                summary = [{"id": w.get("id"), "name": w.get("name"), "active": w.get("active")}
                           for w in (workflows if isinstance(workflows, list) else [])]
                return json.dumps({"workflows": summary, "count": len(summary)})
            return json.dumps({"error": f"HTTP {resp.status}", "detail": (await resp.text())[:300]})


@tool
async def n8n_get_workflow(workflow_id: str) -> str:
    """Get full details of an n8n workflow by ID.
    workflow_id: Workflow ID
    """
    url = f"{config.N8N_URL}/api/v1/workflows/{workflow_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status == 200:
                return json.dumps(await resp.json(), default=str)
            return json.dumps({"error": f"HTTP {resp.status}", "detail": (await resp.text())[:300]})


@tool
async def n8n_create_workflow(name: str, nodes: str, connections: str = "{}") -> str:
    """Create a new n8n workflow. Provide nodes as JSON array and connections as JSON object.
    name: Workflow name
    nodes: JSON array of n8n node definitions
    connections: JSON object of node connections
    """
    try:
        parsed_nodes = json.loads(nodes) if isinstance(nodes, str) else nodes
        parsed_connections = json.loads(connections) if isinstance(connections, str) else connections
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})

    payload = {"name": name, "nodes": parsed_nodes, "connections": parsed_connections, "settings": {}}
    url = f"{config.N8N_URL}/api/v1/workflows"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=_headers(), json=payload) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                return json.dumps({"status": "created", "id": result.get("id"), "name": result.get("name")})
            return json.dumps({"error": f"HTTP {resp.status}", "detail": (await resp.text())[:500]})


@tool
async def n8n_activate_workflow(workflow_id: str, active: bool) -> str:
    """Activate or deactivate an n8n workflow.
    workflow_id: Workflow ID
    active: True to activate, false to deactivate
    """
    url = f"{config.N8N_URL}/api/v1/workflows/{workflow_id}"
    async with aiohttp.ClientSession() as session:
        async with session.patch(url, headers=_headers(), json={"active": active}) as resp:
            if resp.status == 200:
                result = await resp.json()
                return json.dumps({"status": "ok", "id": workflow_id, "active": result.get("active")})
            return json.dumps({"error": f"HTTP {resp.status}", "detail": (await resp.text())[:300]})


@tool
async def n8n_execute_workflow(workflow_id: str, data: str = "{}") -> str:
    """Trigger execution of an n8n workflow.
    workflow_id: Workflow ID
    data: Input data as JSON string
    """
    try:
        payload = json.loads(data) if isinstance(data, str) and data else {}
    except json.JSONDecodeError:
        payload = {}

    url = f"{config.N8N_URL}/api/v1/workflows/{workflow_id}/run"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=_headers(), json=payload) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                return json.dumps({"status": "executed", "execution": result}, default=str)
            return json.dumps({"error": f"HTTP {resp.status}", "detail": (await resp.text())[:300]})


@tool
async def n8n_list_executions(workflow_id: str = "") -> str:
    """List recent n8n workflow executions, optionally filtered by workflow ID.
    workflow_id: Optional workflow ID to filter by
    """
    url = f"{config.N8N_URL}/api/v1/executions"
    params = {"limit": "10"}
    if workflow_id:
        params["workflowId"] = workflow_id
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers(), params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                executions = data.get("data", data) if isinstance(data, dict) else data
                summary = [{"id": e.get("id"), "workflowId": e.get("workflowId"), "status": e.get("status"),
                            "startedAt": e.get("startedAt"), "stoppedAt": e.get("stoppedAt")}
                           for e in (executions if isinstance(executions, list) else [])]
                return json.dumps({"executions": summary})
            return json.dumps({"error": f"HTTP {resp.status}", "detail": (await resp.text())[:300]})


def create_n8n_tools():
    return [n8n_list_workflows, n8n_get_workflow, n8n_create_workflow,
            n8n_activate_workflow, n8n_execute_workflow, n8n_list_executions]
