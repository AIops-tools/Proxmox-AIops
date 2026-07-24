# syntax=docker/dockerfile:1
# Minimal image for Glama introspection: starts the MCP server over stdio.
# The tools/list introspection handshake needs no live Proxmox credentials.
FROM python:3.12-slim

RUN pip install --no-cache-dir proxmox-aiops

# MCP server speaks JSON-RPC over stdio.
ENTRYPOINT ["proxmox-aiops-mcp"]
