ARCHITECTURE OVERVIEW
--------------------
This system implements a multi-stage analytical agent using LangGraph.

Flow:
1. user_request:
   - Extracts user intent
   - Loads database schema
   - Applies environment flags

2. sql_layer:
   - Generates a read-only SQL query
   - Enforces safety validation
   - Executes query against Postgres

3. router:
   - Decides between:
       - direct_response
       - python_analysis (visualization)
       - discovery (proactive insights)

4. python_node:
   - Executes LLM-generated visualization code in a sandboxed REPL
   - Saves plots to image artifacts

5. assembly:
   - Merges all tool outputs
   - Redacts PII
   - Returns final AIMessage (with optional image artifact)

Design Principles:
- Read-only DB access
- Deterministic routing
- Explicit state transitions
- Safety-first SQL execution

