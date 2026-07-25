# Voice Gateway

The Voice Gateway context covers spoken interaction with coding agents across different agent platforms and runtimes. This glossary is the canonical language for product discussion, design, and implementation in this repository.

## Agent domain

**Agent Platform**:
A system that manages coding agents, their sessions, permissions, machines, and user-facing access. OmniGent and Happier are Agent Platforms.
_Avoid_: Harness, backend, provider

**Agent Control Plane**:
The part of an Agent Platform through which clients discover, observe, and control agents and sessions. This is a technical boundary, not a synonym for the whole Agent Platform.
_Avoid_: Agent Platform when referring only to its control interface

**Agent Runtime**:
Software that executes an agent's turns and tools. Codex, Claude Code, OpenCode, and Qwen Code are Agent Runtimes.
_Avoid_: Agent Platform, model provider

**Coding Agent**:
The work-performing actor presented to the user, backed by an Agent Runtime and operating within an Agent Session.
_Avoid_: Model, runtime, session

**Agent Session**:
The persistent work context in which a Coding Agent receives requests, uses tools, and produces results.
_Avoid_: Voice Session, chat room, harness session

**Agent Protocol**:
A standardized control and event contract used to communicate with an agent-facing system. ACP is an Agent Protocol.
_Avoid_: Transport

## Voice domain

**Voice Gateway**:
The platform-neutral system that turns spoken interaction into conversation or work directed at an Agent Platform.
_Avoid_: OmniGent Voice, voice harness, voice bot

**Voice Session**:
One active spoken interaction targeting one Agent Session through one Platform Connection.
_Avoid_: Agent Session, room

**Voice Profile**:
A reusable selection of speech providers, Conversation Brain behavior, voice, and interaction preferences.
_Avoid_: Connector configuration, platform profile

**Conversation Brain**:
The optional fast decision-maker between speech recognition and the target Coding Agent. It may respond, clarify, or forward a request; “middle brain” is an accepted conversational synonym.
_Avoid_: Coding Agent, router

**Direct Mode**:
A Voice Gateway mode that forwards a completed transcript to the target Agent Session without consulting a Conversation Brain.
_Avoid_: No-agent mode, dummy mode

**Conversation Mode**:
A Voice Gateway mode that asks a Conversation Brain to respond, clarify, or forward each completed transcript.
_Avoid_: Smart mode, agent mode

**Speech Provider**:
An implementation of speech recognition or speech synthesis used by a Voice Profile.
_Avoid_: Model provider when the speech role matters

## Integration domain

**Platform Connector**:
The integration boundary through which the Voice Gateway discovers and controls Agent Sessions on one kind of Agent Platform.
_Avoid_: Harness adapter, plugin, backend

**Connector Manifest**:
Static metadata describing a Platform Connector's identity, capabilities, loading contract, authentication methods, and configuration schema.
_Avoid_: Connection profile, credentials, runtime configuration

**Platform Connection**:
A configured relationship between the Voice Gateway and one specific Agent Platform instance.
_Avoid_: Connector, manifest, session

**Runtime Adapter**:
An Agent Platform's integration with one kind of Agent Runtime.
_Avoid_: Platform Connector, harness when discussing the Voice Gateway boundary

**Credential Grant**:
A revocable authorization allowing a Platform Connection or service to act for a user within a defined scope and lifetime.
_Avoid_: Browser cookie, permanent token, copied login

**Capability Set**:
The operations and events a Platform Connector can faithfully support, such as session discovery, cancellation, permissions, and streaming text.
_Avoid_: Feature flags

## Reserved language

**Harness**:
An internal wrapper that launches, controls, or tests an Agent Runtime. It is not the canonical term for an Agent Platform or a Voice Gateway integration.

**Provider**:
A source of a specific service, such as a Speech Provider or model API. It must be qualified because “provider” alone is ambiguous.
