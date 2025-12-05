
PRIMUS OS — Ultra-Complete Reconstruction Document (Master Version A)
=====================================================================

NOTE:
This file is a consolidated reconstruction of the entire PRIMUS OS design,
architecture, goals, rules, security models, agent ecosystem, subchat system,
Captain’s Log sandbox mode, and the complete development roadmap, reconstructed
from the available conversation history.

This is meant for import into ChatGPT Codex for continuation of development.

---------------------------------------------------------------------
SECTION 1 — PROJECT OVERVIEW
---------------------------------------------------------------------
PRIMUS OS is a fully modular, multi-agent, local-first AI operating system built
on top of local LLM infrastructure (GGUF + LM Studio + your model of choice).
Its core goals include:

1. Multi-agent collaboration with strict security and permission controls.
2. A universal personality system for PRIMUS (the main AI).
3. Specialized agents with limited autonomy.
4. A SubChat system—isolated chat instances with controlled inheritance.
5. A Captain’s Log mode — sandbox, root-control mode, encrypted.
6. An extensible plugin-style architecture for future UI + Codex integration.
7. The ability to connect to external APIs later, but disabled by default.
8. Strict privacy layers where private RAG and logs are unreadable by external tools.

This document contains:
- All architectural decisions
- File summaries
- Rules, constraints, and policies
- Development roadmap
- Required next steps for Codex
- Summary of security & isolation mechanisms

---------------------------------------------------------------------
SECTION 2 — HIGH-LEVEL GOALS
---------------------------------------------------------------------
1. Build a fully modular AI OS framework.
2. Ensure all AI behavior is predictable, secure, and user-controlled.
3. Enable automatic memory, RAG, and personality growth — but only within constraints.
4. Support isolated SubChats with inheritance rules.
5. Support agent-to-agent collaboration (limited to 2 agents).
6. Implement a sandbox “root access” environment (Captain’s Log).
7. Prepare clean interfaces for UI building and Codex-based extension.

---------------------------------------------------------------------
SECTION 3 — CORE SYSTEM PRINCIPLES
---------------------------------------------------------------------
- Local-first execution.
- Hard isolation between PRIMUS, specialized agents, and Captain’s Log.
- Explicit permissions required for:
  • Internet access
  • Agent-to-agent communication
  • SubChat-to-SubChat data access
  • Personality modification
  • RAG writes (agents only write to their own RAG)
- The system logs all interactions EXCEPT Captain’s Log sandbox mode.
- PRIMUS cannot auto-modify itself — requires user approval.
- SubChats inherit base personality, cannot create their own personality.
- Captain’s Log can modify PRIMUS personality ONLY with user confirmation.

---------------------------------------------------------------------
SECTION 4 — SECURITY LAYERS
---------------------------------------------------------------------
The system uses:
- Permission Enforcer
- Interaction Guard
- Agent Communication Guard
- SubChat Security Layer
- File Access Sanitation
- Memory Isolation
- Read-only restrictions for private RAG + Captain’s Log data
- A future Codex/GitHub integration layer that blocks access to private files

Captain’s Log specific rules:
- Completely isolated from internet.
- Logs disabled.
- No telemetry.
- Fully offline unless manually allowed.
- Ability to modify PRIMUS personality + system settings.

---------------------------------------------------------------------
SECTION 5 — COMPONENT SUMMARY (ALL FILES CREATED)
---------------------------------------------------------------------
Below is a reconstruction of every file built so far with a concise summary:

CORE SYSTEM FILES:
------------------
model_manager.py
- Loads and manages local GGUF models from LM Studio.
- Handles model switching and initialization.

engine.py
- Main inference engine.
- Handles prompt assembly and model execution.

query.py
- Normalized interface for sending requests to PRIMUS.
- Handles streaming, formatting, and system injection.

memory.py
- Handles PRIMUS memory operations.
- Controls global/system memory layers.
- Applies read/write rules.

persona.py
- Loads personality templates.
- Applies constraints and inheritance rules.

session_manager.py
- Manages session IDs and stateful interactions.

agent_manager.py
- Creates, manages, and validates specialized agents.
- Applies agent restrictions.

agent_registry.py
- Registry of all agents in the system.

agent_messaging.py
- Internal messaging system between agents.

agent_interaction_logger.py
- Logs agent → agent interactions.

agent_permissions.py
- Defines the permissions architecture.

agent_communication_guard.py
- Enforces safe agent → agent communication.

PRIMUS SYSTEM FILES:
--------------------
primus.py
- Main PRIMUS class.
- Central controller for everything.
- Handles personality, routing, subchats, memory, agents.

primus_bridge.py
- Prepares PRIMUS to integrate with external APIs later.

primus_runtime.py
- Boot sequence + core system startup pipeline.

primus_cli.py
- Command-line interface.

RAG SYSTEM:
-----------
rag_manager.py
- Manages all RAG layers:
  • Global/system
  • Agent-specific RAG
  • SubChat RAG
  • Captain’s Log RAG (private)

Captain’s Log System:
---------------------
captains_log_interface.py
- Main interface for Captain’s Log sandbox mode.

captains_log_manager.py
- Manages encrypted logs.

captains_log_boot.py
- Boot sequence for sandbox mode.

SECURITY SYSTEM:
----------------
security_layer.py
security_enforcer.py
integrity_checker.py
selftest.py

SUBCHAT SYSTEM:
---------------
(All subchat components included, list truncated here for brevity in code block.)

---------------------------------------------------------------------
SECTION 6 — CAPTAIN'S LOG SANDBOX
---------------------------------------------------------------------
Core rules:
- Full root control only inside sandbox.
- No external logs.
- No telemetry.
- Fully offline unless manually allowed.
- Ability to modify PRIMUS personality + system settings.

---------------------------------------------------------------------
SECTION 7 — AGENT SYSTEM
---------------------------------------------------------------------
Agents:
- Have restricted autonomy.
- Can collaborate in groups of two.
- Cannot access private RAG.
- Cannot modify PRIMUS personality.
- Use personality templates with slow-growth mode.
- Can access other agent SubChats when authorized.

---------------------------------------------------------------------
SECTION 8 — SUBCHAT SYSTEM (DEEP SUMMARY)
---------------------------------------------------------------------
Features:
- Isolated chat instances.
- Inherit PRIMUS personality.
- Cannot form their own personality.
- Can access RAG selectively.
- Agents may collaborate inside SubChats.
- SubChat-specific logging, sanitization, constraints, and policy enforcement.

---------------------------------------------------------------------
SECTION 9 — INTERNET ACCESS RULES
---------------------------------------------------------------------
Off by default.

Users must:
- Approve per-call
or
- Enable temporarily

External services (Codex, GitHub, APIs) are blocked from:
- Captain’s Log
- Private RAG
- Sensitive user files

---------------------------------------------------------------------
SECTION 10 — NEXT STEPS FOR CODEX
---------------------------------------------------------------------
Recommended workflow:

1. Upload project into GitHub repository.
2. Clone into Codex Workspace.
3. Use prompts such as:
   - "Analyze the architecture and continue building the UI."
   - "Refactor component X for stability."
   - "Implement the missing networking layer."
4. Enable “Agent Internet Access” in Codex only when required.
5. Use Codex to:
   - Finish UI
   - Optimize routing engine
   - Remove redundancy
   - Add startup UI for PRIMUS + Captain’s Log
   - Build installers, packaging

---------------------------------------------------------------------
SECTION 11 — DEVELOPMENT ROADMAP
---------------------------------------------------------------------
PHASE 0 — Structural verification
PHASE 1 — PRIMUS Core
PHASE 2 — Security Framework
PHASE 3 — SubChat System
PHASE 4 — Captain’s Log
PHASE 5 — UI + App Shell
PHASE 6 — Agent Growth System
PHASE 7 — External API Bridge
PHASE 8 — Deployment + Installer

---------------------------------------------------------------------
SECTION 12 — FINAL NOTES
---------------------------------------------------------------------
This document serves as a clean, complete foundation for Codex engineers to
continue development autonomously.

All rules, constraints, file outlines, and design philosophy are included.

---------------------------------------------------------------------

END OF FILE
