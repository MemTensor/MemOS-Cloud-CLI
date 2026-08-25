"""Generated host-side hook artifacts for agents without config-file hooks.

Cline and OpenCode load JS plugins, Hermes loads a Python plugin, and OpenClaw
discovers an extension directory. Each generated artifact embeds the managed
marker (`memos hook run --agent ...`) so install/uninstall can recognize
MemOS-owned files.
"""
from __future__ import annotations

import json

from .agents import HookAgentSpec


def hermes_plugin_manifest() -> str:
    """Build the manifest for the Hermes user plugin."""
    return (
        "name: memos-memory\n"
        'version: "1.0.0"\n'
        'description: "MemOS automatic memory retrieval and capture. Managed by MemOS CLI."\n'
        "kind: standalone\n"
        "hooks:\n"
        "  - pre_llm_call\n"
        "  - post_llm_call\n"
    )


def hermes_plugin_entry(argv: list[str], spec: HookAgentSpec) -> str:
    """Build a Hermes Python plugin shared by CLI, TUI, gateway, and Desktop."""
    return f'''# Managed by MemOS CLI: memos hook run --agent {spec.agent}
from __future__ import annotations

import json
import logging
import os
import subprocess

MEMOS_ARGV = {json.dumps(argv, ensure_ascii=False)}
TIMEOUT_SECONDS = 60
logger = logging.getLogger(__name__)


def _run_memos(event, payload):
    try:
        completed = subprocess.run(
            [*MEMOS_ARGV, "--event", event],
            input=json.dumps(payload, ensure_ascii=False, default=str),
            capture_output=True,
            text=True,
            shell=False,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
        if completed.returncode != 0:
            logger.debug(
                "MemOS hook exited %s for %s: %s",
                completed.returncode,
                event,
                completed.stderr[:400],
            )
        parsed = json.loads(completed.stdout or "{{}}")
        return parsed if isinstance(parsed, dict) else {{}}
    except Exception:
        logger.debug("MemOS hook failed for %s", event, exc_info=True)
        return {{}}


def _payload(event, session_id, values):
    extra = dict(values)
    payload = {{
        "hook_event_name": event,
        "session_id": str(session_id or "default"),
        "cwd": os.getcwd(),
        "extra": extra,
    }}
    turn_id = extra.get("turn_id")
    if turn_id is not None and str(turn_id).strip():
        payload["turn_id"] = str(turn_id)
    return payload


def _pre_llm_call(session_id="", user_message="", **kwargs):
    values = {{"user_message": user_message, **kwargs}}
    result = _run_memos(
        "{spec.search_event}",
        _payload("{spec.search_event}", session_id, values),
    )
    context = result.get("context")
    if isinstance(context, str) and context.strip():
        return {{"context": context}}
    return None


def _post_llm_call(
    session_id="",
    user_message="",
    assistant_response="",
    **kwargs,
):
    values = {{
        "user_message": user_message,
        "assistant_response": assistant_response,
        **kwargs,
    }}
    _run_memos(
        "{spec.add_event}",
        _payload("{spec.add_event}", session_id, values),
    )
    return None


def register(ctx):
    ctx.register_hook("{spec.search_event}", _pre_llm_call)
    ctx.register_hook("{spec.add_event}", _post_llm_call)
'''


def antigravity_hook_adapter(argv: list[str], spec: HookAgentSpec) -> str:
    """Build a local compatibility adapter for Antigravity hook payloads.

    Antigravity 2.9.x uses ``lastUserInput``/``finalModelOutput`` and its
    transcript records are ``USER_INPUT``/``PLANNER_RESPONSE``.  The adapter
    normalizes those values before invoking the installed MemOS CLI, which
    also lets an older packaged CLI (before the parser aliases shipped) work.
    """
    return f'''#!/usr/bin/env python3
# Managed by MemOS CLI: antigravity payload adapter -> memos hook run --agent {spec.agent}
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MEMOS_ARGV = {json.dumps(argv, ensure_ascii=False)}


def _text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("content", "text", "message", "value", "lastUserInput", "finalModelOutput"):
            if key in value:
                return _text(value[key])
    if isinstance(value, list):
        return "\\n".join(part for part in (_text(item) for item in value) if part)
    return "" if value is None else str(value)


def _clean_user(value):
    text = _text(value)
    if not text.strip():
        return ""
    opener = "<USER_REQUEST>"
    closer = "</USER_REQUEST>"
    start = text.find(opener)
    if start >= 0:
        body_start = start + len(opener)
        end = text.find(closer, body_start)
        text = text[body_start:] if end < 0 else text[body_start:end]
    for marker in ("<ADDITIONAL_METADATA>", "<USER_SETTINGS_CHANGE>", "The current local time is:", "The user changed setting `"):
        index = text.find(marker)
        if index > 0:
            text = text[:index]
    return text.strip()


def _records(value):
    if isinstance(value, dict):
        for key in ("events", "entries", "items", "messages", "transcript"):
            if isinstance(value.get(key), list):
                return value[key]
        return [value]
    if isinstance(value, list):
        return value
    return []


def _read_transcript(path):
    candidates = [Path(str(path)).expanduser()]
    if candidates[0].name == "transcript.jsonl":
        candidates.insert(0, candidates[0].with_name("transcript_full.jsonl"))
    for candidate in candidates:
        try:
            raw = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            return _records(json.loads(raw))
        except json.JSONDecodeError:
            records = []
            for line in raw.splitlines():
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            if records:
                return records
    return []


def _normalize(payload):
    if not isinstance(payload, dict):
        return payload
    normalized = dict(payload)
    records = _records(normalized.get("transcript"))
    if not records:
        transcript_path = normalized.get("transcriptPath") or normalized.get("transcript_path")
        if transcript_path:
            records = _read_transcript(transcript_path)

    # Prefer the canonical transcript USER_INPUT over lastUserInput. The
    # latter can contain Antigravity runtime metadata appended to the text
    # shown by the user, which must not be persisted as part of the prompt.
    for record in reversed(records):
        if not isinstance(record, dict):
            continue
        kind = str(record.get("type", "")).strip().upper().replace("-", "_")
        if kind != "USER_INPUT":
            continue
        values = record.get("data") if isinstance(record.get("data"), dict) else record
        prompt = _clean_user(values)
        if prompt:
            normalized["prompt"] = prompt
            break

    if not _text(normalized.get("prompt")):
        if _text(normalized.get("userMessage")):
            normalized["prompt"] = _clean_user(normalized["userMessage"])
        elif _text(normalized.get("lastUserInput")):
            normalized["prompt"] = _clean_user(normalized["lastUserInput"])
    if not _text(normalized.get("last_assistant_message")):
        if _text(normalized.get("finalModelOutput")):
            normalized["last_assistant_message"] = _text(normalized["finalModelOutput"])
    for record in reversed(records):
        if not isinstance(record, dict):
            continue
        kind = str(record.get("type", "")).strip().upper().replace("-", "_")
        values = record.get("data") if isinstance(record.get("data"), dict) else record
        if kind == "USER_INPUT" and not _text(normalized.get("prompt")):
            normalized["prompt"] = _clean_user(values)
        elif kind == "PLANNER_RESPONSE" and not _text(normalized.get("last_assistant_message")):
            normalized["last_assistant_message"] = _text(values)
    return normalized


def main():
    event = None
    args = list(sys.argv[1:])
    if "--event" in args:
        index = args.index("--event")
        if index + 1 < len(args):
            event = args[index + 1]
    try:
        payload = json.loads(sys.stdin.read() or "{{}}")
        normalized = _normalize(payload)
        command = [*MEMOS_ARGV]
        if event:
            command.extend(["--event", event])
        completed = subprocess.run(
            command,
            input=json.dumps(normalized, ensure_ascii=False),
            text=True,
            capture_output=True,
            check=False,
        )
        sys.stdout.write(completed.stdout or "{{}}")
        sys.stderr.write(completed.stderr or "")
        raise SystemExit(completed.returncode)
    except Exception as exc:
        print(f"[memos antigravity adapter] {{exc}}", file=sys.stderr)
        print("{{}}")
        raise SystemExit(0)


if __name__ == "__main__":
    main()
'''


def cline_plugin(argv: list[str], spec: HookAgentSpec) -> str:
    """Build the Cline AgentPlugin that owns the MemOS memory lifecycle."""
    return (
        _js_runner(argv, spec.agent)
        + "\n"
        "let sessionKey = \"default\"\n"
        "const contextByPrompt = new Map()\n"
        "\n"
        "function contentText(value) {\n"
        "  if (typeof value === \"string\") return value\n"
        "  if (Array.isArray(value)) {\n"
        "    return value.map(contentText).filter(Boolean).join(\"\\n\")\n"
        "  }\n"
        "  if (value && typeof value === \"object\") {\n"
        "    const type = String(value.type || \"\").toLowerCase()\n"
        "    if (type === \"thinking\" || type === \"reasoning\") return \"\"\n"
        "    return contentText(value.text ?? value.content ?? value.message ?? value.input ?? \"\")\n"
        "  }\n"
        "  return \"\"\n"
        "}\n"
        "\n"
        "function lastRoleText(messages, roles) {\n"
        "  if (!Array.isArray(messages)) return \"\"\n"
        "  const accepted = new Set(roles.map((role) => String(role).toLowerCase()))\n"
        "  for (let index = messages.length - 1; index >= 0; index -= 1) {\n"
        "    const message = messages[index]\n"
        "    if (!message || !accepted.has(String(message.role || \"\").toLowerCase())) continue\n"
        "    const metadata = message.metadata\n"
        "    if (metadata && (metadata.displayRole === \"system\" || metadata.userRunSpan === 0)) continue\n"
        "    const text = contentText(message.content ?? message)\n"
        "    if (text.trim()) return text\n"
        "  }\n"
        "  return \"\"\n"
        "}\n"
        "\n"
        "function injectContext(messages, context) {\n"
        "  const updated = [...messages]\n"
        "  for (let index = updated.length - 1; index >= 0; index -= 1) {\n"
        "    const message = updated[index]\n"
        "    if (!message || String(message.role || \"\").toLowerCase() !== \"user\") continue\n"
        "    const metadata = message.metadata\n"
        "    if (metadata && (metadata.displayRole === \"system\" || metadata.userRunSpan === 0)) continue\n"
        "    const original = Array.isArray(message.content)\n"
        "      ? message.content\n"
        "      : [{ type: \"text\", text: contentText(message.content) }]\n"
        "    updated[index] = {\n"
        "      ...message,\n"
        "      content: [{ type: \"text\", text: context }, ...original],\n"
        "    }\n"
        "    return updated\n"
        "  }\n"
        "  return [...updated, { role: \"user\", content: [{ type: \"text\", text: context }] }]\n"
        "}\n"
        "\n"
        "function promptKey(prompt) {\n"
        "  return `${sessionKey}\\n${prompt}`\n"
        "}\n"
        "\n"
        "const plugin = {\n"
        "  name: \"memos-memory\",\n"
        "  manifest: { capabilities: [\"hooks\", \"messageBuilders\"] },\n"
        "  setup(api, ctx) {\n"
        "    sessionKey = String(\n"
        "      (ctx && ctx.session && ctx.session.sessionId)\n"
        "        || (ctx && ctx.workspaceInfo && ctx.workspaceInfo.rootPath)\n"
        "        || \"default\",\n"
        "    )\n"
        "    if (!api || typeof api.registerMessageBuilder !== \"function\") return\n"
        "    api.registerMessageBuilder({\n"
        "      name: \"memos-memory-context\",\n"
        "      async build(messages) {\n"
        "        try {\n"
        "          const prompt = lastRoleText(messages, [\"user\", \"human\"])\n"
        "          if (!prompt.trim()) return messages\n"
        "          const key = promptKey(prompt)\n"
        "          let context = contextByPrompt.get(key)\n"
        "          if (!contextByPrompt.has(key)) {\n"
        f"            const response = await runMemos(\"{spec.search_event}\", {{\n"
        "              session_id: sessionKey,\n"
        "              prompt,\n"
        "            })\n"
        "            const value = response && (response.contextModification || response.context)\n"
        "            context = typeof value === \"string\" ? value : \"\"\n"
        "            contextByPrompt.set(key, context)\n"
        "          }\n"
        "          return context && Array.isArray(messages)\n"
        "            ? injectContext(messages, context)\n"
        "            : messages\n"
        "        } catch {\n"
        "          return messages\n"
        "        }\n"
        "      },\n"
        "    })\n"
        "  },\n"
        "  hooks: {\n"
        "    async afterRun(payload) {\n"
        "      try {\n"
        "        const snapshot = payload && payload.snapshot\n"
        "        const result = payload && payload.result\n"
        "        const status = String(\n"
        "          (result && result.status) || \"\",\n"
        "        ).toLowerCase()\n"
        "        const resultMessages = result && result.messages\n"
        "        const snapshotMessages = snapshot && snapshot.messages\n"
        "        const prompt = lastRoleText(resultMessages, [\"user\", \"human\"])\n"
        "          || lastRoleText(snapshotMessages, [\"user\", \"human\"])\n"
        "        const answer = contentText(result && result.outputText)\n"
        "          || lastRoleText(resultMessages, [\"assistant\", \"model\", \"agent\"])\n"
        "          || lastRoleText(snapshotMessages, [\"assistant\", \"model\", \"agent\"])\n"
        "        if (prompt.trim()) contextByPrompt.delete(promptKey(prompt))\n"
        "        if (!prompt.trim() || !answer.trim()) return undefined\n"
        # Cline gives plugin hooks a 3-second sandbox budget and retries a
        # timed-out hook. MemOS add may wait for the remote HTTP request, so
        # never block the lifecycle callback on that request; otherwise one
        # turn can be stored twice when Cline retries the hook.
        f"        void runMemos(\"{spec.add_event}\", {{\n"
        "          session_id: sessionKey,\n"
        "          prompt,\n"
        "          last_assistant_message: answer,\n"
        "          status,\n"
        "        })\n"
        "      } catch {}\n"
        "      return undefined\n"
        "    },\n"
        "  },\n"
        "}\n"
        "\n"
        "export { plugin }\n"
        "export default plugin\n"
    )


def cline_plugin_package_json() -> str:
    """Build the package manifest used by Cline CLI plugin discovery."""
    return json.dumps(
        {
            "name": "memos-memory",
            "version": "1.0.0",
            "private": True,
            "type": "module",
            "cline": {
                "plugins": [
                    {
                        "paths": ["./index.js"],
                        "capabilities": ["hooks", "messageBuilders"],
                    }
                ]
            },
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def _js_runner(argv: list[str], agent: str) -> str:
    """Shared JS snippet that pipes a payload into `memos hook run`."""
    return (
        f"// Managed by MemOS CLI: memos hook run --agent {agent}\n"
        "import { spawn } from \"node:child_process\"\n"
        "\n"
        f"const MEMOS_ARGV = {json.dumps(argv)}\n"
        "\n"
        "function runMemos(event, payload) {\n"
        "  return new Promise((resolve) => {\n"
        "    try {\n"
        "      const [command, ...args] = MEMOS_ARGV\n"
        "      const child = spawn(command, [...args, \"--event\", event], {\n"
        "        stdio: [\"pipe\", \"pipe\", \"ignore\"],\n"
        "      })\n"
        "      let stdout = \"\"\n"
        "      child.stdout.on(\"data\", (chunk) => { stdout += chunk })\n"
        "      child.on(\"error\", () => resolve(null))\n"
        "      child.on(\"close\", () => {\n"
        "        try { resolve(JSON.parse(stdout)) } catch { resolve(null) }\n"
        "      })\n"
        "      child.stdin.write(JSON.stringify(payload))\n"
        "      child.stdin.end()\n"
        "    } catch {\n"
        "      resolve(null)\n"
        "    }\n"
        "  })\n"
        "}\n"
    )


def opencode_plugin(argv: list[str], spec: HookAgentSpec) -> str:
    """Build the OpenCode plugin that owns the MemOS memory lifecycle."""
    return (
        _js_runner(argv, spec.agent)
        + "\n"
        "const lastPromptBySession = new Map()\n"
        "const lastAnswerBySession = new Map()\n"
        "\n"
        "function textOfParts(parts) {\n"
        "  if (!Array.isArray(parts)) return \"\"\n"
        "  return parts\n"
        "    .filter((part) => part && part.type === \"text\" && typeof part.text === \"string\")\n"
        "    .map((part) => part.text)\n"
        "    .join(\"\\n\")\n"
        "}\n"
        "\n"
        "export const MemosMemoryPlugin = async () => {\n"
        "  return {\n"
        f"    \"{spec.search_event}\": async (input, output) => {{\n"
        "      const sessionId = String(\n"
        "        (output && output.message && output.message.sessionID)\n"
        "          || (input && input.sessionID)\n"
        "          || \"default\",\n"
        "      )\n"
        "      const prompt = textOfParts(output && output.parts)\n"
        "      if (!prompt.trim()) return\n"
        "      lastPromptBySession.set(sessionId, prompt)\n"
        f"      const response = await runMemos(\"{spec.search_event}\", {{ session_id: sessionId, prompt }})\n"
        "      const context = response && (response.context || response.additionalContext)\n"
        "      if (!context || !output || !Array.isArray(output.parts)) return\n"
        "      for (const part of output.parts) {\n"
        "        if (part && part.type === \"text\" && typeof part.text === \"string\") {\n"
        "          part.text = context + \"\\n\\n\" + part.text\n"
        "          return\n"
        "        }\n"
        "      }\n"
        "    },\n"
        "    event: async ({ event }) => {\n"
        "      if (!event || !event.type) return\n"
        "      const properties = event.properties || {}\n"
        "      if (event.type === \"message.part.updated\") {\n"
        "        const part = properties.part\n"
        "        if (part && part.type === \"text\" && typeof part.text === \"string\" && part.sessionID) {\n"
        "          lastAnswerBySession.set(String(part.sessionID), part.text)\n"
        "        }\n"
        "        return\n"
        "      }\n"
        f"      if (event.type !== \"{spec.add_event}\") return\n"
        "      const sessionId = String(properties.sessionID || \"default\")\n"
        "      const prompt = lastPromptBySession.get(sessionId) || \"\"\n"
        "      const answer = lastAnswerBySession.get(sessionId) || \"\"\n"
        "      lastPromptBySession.delete(sessionId)\n"
        "      lastAnswerBySession.delete(sessionId)\n"
        "      if (!prompt.trim() || !answer.trim() || answer === prompt) return\n"
        f"      await runMemos(\"{spec.add_event}\", {{\n"
        "        session_id: sessionId,\n"
        "        prompt,\n"
        "        last_assistant_message: answer,\n"
        "      })\n"
        "    },\n"
        "  }\n"
        "}\n"
    )


def deepseek_plugin(argv: list[str], spec: HookAgentSpec) -> str:
    """Build the dsh Cordis plugin that owns the MemOS memory lifecycle."""
    return (
        _js_runner(argv, spec.agent)
        + "\n"
        "import { randomUUID } from \"node:crypto\"\n"
        "function firstText(value) {\n"
        "  if (typeof value === \"string\") return value\n"
        "  if (Array.isArray(value)) {\n"
        "    for (let index = value.length - 1; index >= 0; index -= 1) {\n"
        "      const text = firstText(value[index])\n"
        "      if (text) return text\n"
        "    }\n"
        "    return \"\"\n"
        "  }\n"
        "  if (value && typeof value === \"object\") {\n"
        "    return firstText(value.text ?? value.content ?? value.message ?? value.prompt ?? \"\")\n"
        "  }\n"
        "  return \"\"\n"
        "}\n"
        "\n"
        "function lastRoleText(messages, roles) {\n"
        "  if (!Array.isArray(messages)) return \"\"\n"
        "  for (let index = messages.length - 1; index >= 0; index -= 1) {\n"
        "    const item = messages[index]\n"
        "    const role = String((item && item.role) || \"\").toLowerCase()\n"
        "    if (!roles.includes(role)) continue\n"
        "    const text = firstText(item)\n"
        "    if (text.trim()) return text\n"
        "  }\n"
        "  return \"\"\n"
        "}\n"
        "\n"
        "function sessionKeyOf(payload, agent) {\n"
        "  return String(\n"
        "    (agent && agent.session && agent.session.id)\n"
        "      || (payload && (payload.sessionId ?? payload.session_id ?? payload.turnId ?? payload.turn_id))\n"
        "      || \"default\",\n"
        "  )\n"
        "}\n"
        "\n"
        "function contextMessage(text) {\n"
        "  return {\n"
        "    id: randomUUID(),\n"
        "    role: \"user\",\n"
        "    content: [{ type: \"text\", text }],\n"
        "    source: { kind: \"plugin\", plugin: \"memos-memory\" },\n"
        "  }\n"
        "}\n"
        "\n"
        "function assistantAnswer(agent, turn) {\n"
        "  const events = agent && agent.session && agent.session.events\n"
        "  if (!Array.isArray(events)) return \"\"\n"
        "  let lastMessage = \"\"\n"
        "  const partial = []\n"
        "  for (const event of events) {\n"
        "    const data = event && event.data\n"
        "    if (!data || data.turn !== turn) continue\n"
        "    if (event.type === \"assistant/message\") {\n"
        "      const text = firstText(data.message && data.message.content)\n"
        "      if (text.trim()) lastMessage = text\n"
        "    } else if (event.type === \"assistant/chunk\"\n"
        "      && data.chunk && data.chunk.type === \"text-delta\") {\n"
        "      if (typeof data.chunk.text === \"string\") partial.push(data.chunk.text)\n"
        "    }\n"
        "  }\n"
        "  return lastMessage || partial.join(\"\")\n"
        "}\n"
        "\n"
        "const lastPromptByAgent = new WeakMap()\n"
        "\n"
        "export const name = \"memos-memory\"\n"
        "\n"
        "export function apply(ctx) {\n"
        f"  ctx.on(\"{spec.search_event}\", async (payload, next) => {{\n"
        "    try {\n"
        "      const agent = payload && payload.agent\n"
        "      const messages = payload && payload.messages\n"
        "      const prompt = lastRoleText(messages, [\"user\", \"human\"]) || firstText(payload && payload.prompt)\n"
        "      if (prompt.trim()) {\n"
        "        lastPromptByAgent.set(agent, { prompt, turn: payload && payload.turn })\n"
        f"        const response = await runMemos(\"{spec.search_event}\", {{\n"
        "          session_id: sessionKeyOf(payload, agent),\n"
        "          turn_id: String((payload && payload.turn) || \"\"),\n"
        "          prompt,\n"
        "        })\n"
        "        const context = response && (response.context || response.additionalContext)\n"
        "        const downstream = typeof next === \"function\" ? await next() : { kind: \"enter\", messages: messages || [] }\n"
        "        if (context && downstream && downstream.kind === \"enter\") {\n"
        "          return { ...downstream, messages: [...downstream.messages, contextMessage(context)] }\n"
        "        }\n"
        "        return downstream\n"
        "      }\n"
        "    } catch {}\n"
        "    if (typeof next === \"function\") return next()\n"
        "    return undefined\n"
        "  })\n"
        f"  ctx.on(\"{spec.add_event}\", async (payload) => {{\n"
        "    try {\n"
        "      const agent = payload && payload.agent\n"
        "      const turn = payload && payload.turn\n"
        "      const saved = agent && lastPromptByAgent.get(agent)\n"
        "      const prompt = saved && saved.prompt || \"\"\n"
        "      const answer = assistantAnswer(agent, turn)\n"
        "      const cancelled = Boolean(payload && (payload.cancelled ?? payload.aborted))\n"
        "      if (cancelled || !prompt.trim() || !answer.trim()) return\n"
        "      lastPromptByAgent.delete(agent)\n"
        f"      await runMemos(\"{spec.add_event}\", {{\n"
        "        session_id: sessionKeyOf(payload, agent),\n"
        "        turn_id: String(turn || \"\"),\n"
        "        prompt,\n"
        "        last_assistant_message: answer,\n"
        "      })\n"
        "    } catch {}\n"
        "  })\n"
        "}\n"
        "\n"
        "export default { name, apply }\n"
    )


def openclaw_plugin_manifest() -> str:
    """Build the openclaw.plugin.json manifest for the OpenClaw plugin."""
    return json.dumps(
        {
            "id": "memos-memory",
            "name": "MemOS Memory",
            "description": "MemOS automatic memory retrieval and capture. Managed by MemOS CLI.",
            "configSchema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {},
            },
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def openclaw_plugin_package_json() -> str:
    """Build the package.json declaring the runtime entry via openclaw.extensions."""
    return json.dumps(
        {
            "name": "memos-memory",
            "version": "1.0.0",
            "description": "MemOS automatic memory retrieval and capture. Managed by MemOS CLI.",
            "type": "module",
            "main": "index.js",
            "openclaw": {
                "extensions": ["./index.js"],
            },
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def openclaw_plugin_entry(argv: list[str], spec: HookAgentSpec) -> str:
    """Build the OpenClaw plugin entry registering typed hooks via api.on."""
    return (
        _js_runner(argv, spec.agent)
        + "\n"
        "function firstText(value) {\n"
        "  if (typeof value === \"string\") return value\n"
        "  if (Array.isArray(value)) {\n"
        "    for (const item of value) {\n"
        "      const text = firstText(item)\n"
        "      if (text) return text\n"
        "    }\n"
        "    return \"\"\n"
        "  }\n"
        "  if (value && typeof value === \"object\") {\n"
        "    return firstText(value.text ?? value.content ?? value.message ?? value.prompt ?? \"\")\n"
        "  }\n"
        "  return \"\"\n"
        "}\n"
        "\n"
        "function contentText(value) {\n"
        "  if (typeof value === \"string\") return value\n"
        "  if (Array.isArray(value)) {\n"
        "    return value\n"
        "      .map((item) => contentText(item))\n"
        "      .filter((text) => text.trim())\n"
        "      .join(\"\\n\")\n"
        "  }\n"
        "  if (value && typeof value === \"object\") {\n"
        "    const type = String(value.type || \"\").toLowerCase()\n"
        "    if (type === \"thinking\" || type === \"reasoning\") return \"\"\n"
        "    if (typeof value.text === \"string\") return value.text\n"
        "    return contentText(value.content ?? value.message ?? \"\")\n"
        "  }\n"
        "  return \"\"\n"
        "}\n"
        "\n"
        "function lastRoleText(messages, roles) {\n"
        "  if (!Array.isArray(messages)) return \"\"\n"
        "  for (let index = messages.length - 1; index >= 0; index -= 1) {\n"
        "    const message = messages[index]\n"
        "    const role = String((message && message.role) || \"\").toLowerCase()\n"
        "    if (!roles.includes(role)) continue\n"
        "    const text = contentText(message && (message.content ?? message.message))\n"
        "    if (text.trim()) return text\n"
        "  }\n"
        "  return \"\"\n"
        "}\n"
        "\n"
        "function sessionKeyOf(event, ctx) {\n"
        "  return String(\n"
        "    (ctx && (ctx.sessionKey || ctx.chatId || ctx.channelId))\n"
        "      || (event && (event.sessionKey || event.sessionId || event.runId))\n"
        "      || \"default\",\n"
        "  )\n"
        "}\n"
        "\n"
        "const lastPromptBySession = new Map()\n"
        "\n"
        "export default {\n"
        "  id: \"memos-memory\",\n"
        "  name: \"MemOS Memory\",\n"
        "  register(api) {\n"
        f"    api.on(\"{spec.search_event}\", async (event, ctx) => {{\n"
        "      try {\n"
        "        const sessionKey = sessionKeyOf(event, ctx)\n"
        "        const prompt = firstText(event && (event.prompt ?? event.messages))\n"
        "        if (!prompt.trim()) return undefined\n"
        "        lastPromptBySession.set(sessionKey, prompt)\n"
        f"        const response = await runMemos(\"{spec.search_event}\", {{\n"
        "          session_id: sessionKey,\n"
        "          prompt,\n"
        "        })\n"
        "        const context = response && response.prependContext\n"
        "        if (context) return { prependContext: context }\n"
        "      } catch {}\n"
        "      return undefined\n"
        "    })\n"
        f"    api.on(\"{spec.add_event}\", async (event, ctx) => {{\n"
        "      try {\n"
        "        const sessionKey = sessionKeyOf(event, ctx)\n"
        "        const prompt = lastPromptBySession.get(sessionKey) || \"\"\n"
        "        lastPromptBySession.delete(sessionKey)\n"
        "        const answer = lastRoleText(event && event.messages, [\"assistant\", \"model\"])\n"
        "        const success = !event || event.success !== false\n"
        "        if (!success || !prompt.trim() || !answer.trim()) return\n"
        f"        await runMemos(\"{spec.add_event}\", {{\n"
        "          session_id: sessionKey,\n"
        "          prompt,\n"
        "          last_assistant_message: answer,\n"
        "        })\n"
        "      } catch {}\n"
        "    })\n"
        "  },\n"
        "}\n"
    )
