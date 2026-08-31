# ExecWeave 0.8.0 implementation plan

> Baseline: `main` @ `bfdfb1b` (v0.7.9).
> This is a specification to execute item by item, not a proposal. Every item needs a
> corresponding browser check.

---

## 0. What this round fixes

v0.7.9 collapsed live, finished and `viewer.html` into one dashboard and reduced the
agent panel to "root: Prompt and Final response" / "subagent: Task, Thinking and
Response".

Running a real session with five subagents and two rounds of questions exposed three
things:

1. Two subagents lost their Response; it rendered as encrypted.
2. The `/root` panel paired the first question with the second question's answer, and
   the first round's real answer was nowhere.
3. process, file and tool_call nodes carry nothing when selected, so they have no
   meaning in the graph.

The first two are defects. The third is a gap.

---

## 1. Fix: a subagent's Response classified as injected context

### Symptom

In one run, two of five subagents showed this in the Response card:

```
Observed — plaintext not exposed by provider.
```

while `conversations.json` holds their `subagent_final_response` as `plaintext`, intact.

### Cause

The v0.7.9 rule in `_mark_shared_injected_context()`
(`src/execweave/_conversation_records_core.py`) reads:

> text of 400 characters or more appearing verbatim under two or more agents is marked
> `content_role = "shared_injected_context"`.

The rule exists to stop the plugin catalogue a provider prepends to every subagent from
being read as that agent's assignment. But **a child's answer legitimately appears
twice**: in the child's own rollout, and in the root's record, because the child reports
back to root. The answer is therefore classified as injected context and filtered out by
`isInjected()` in `viewer_agent_panel.py`.

Only two of five were affected because the other three answers are shorter than 400
characters and slipped under the threshold.

### Fix

Apply the rule to inbound assignments only:

- consider only messages where `recipient === <the agent>` and `sender !== <the agent>`
- never apply it to messages the agent wrote itself (`sender === <the agent>`)
- keep the 400-character threshold, but stop treating it as the sole criterion

### Verification

- unit: assert against the real `conversations.json` from that run that all five agents
  keep a plaintext Response
- browser: select each of the five subagents; no Response may render the encrypted notice
- reverted: restore the old rule and the check must fail

---

## 2. Rounds

### Definition

| panel | one round |
|---|---|
| `/root` | one user message through that round's final answer |
| subagent | one assignment through its Task / Thinking / Response |

### Presentation

- **the newest round is on top and expanded**
- older rounds fold to a single line: `17:22 · five agents reviewing dependency risk`
- **no fold at all when there is only one round**; keep the v0.7.9 appearance
- a subagent's fold carries the timestamp of **the root round it belongs to**, not of its
  own assignment, so the two sides line up
- time only within a single day; a `08-31` style prefix appears when a run crosses
  midnight

### Attribution

Each subagent round belongs to the root round whose interval contains it. A root round's
interval runs from its question to the next question, and the last round runs to the end
of the run.

### Verification

- browser: a run with two questions gives `/root` two rounds, newest expanded, older
  folded
- browser: expanding an older round shows that round's question beside **that round's own**
  answer
- browser: a subagent's fold timestamp equals the root round it belongs to

---

## 3. Non-agent nodes

Selecting a process, file, tool_call or network_endpoint currently shows nothing. What
follows lists **only what the existing data actually supports**. No field may be shown
that does not exist.

| node | shows | source |
|---|---|---|
| `process` | command, executable, pid / ppid, when it appeared | `cmdline`, `exe`, `pid`, `ppid`, `create_time` |
| `file` | filename, creation / modification / deletion and their times | edge `event_types`, `first_seen`, `last_seen` |
| `tool_call` | tool name, time, input field names | `tool_name`, `input_keys`, `tool_use_id` |
| `session` | launch command, working directory, backend | `command`, `cwd`, `backend` |
| `network_endpoint` | address, first and last seen, which process connected | node name and edge |
| `model` / `tool` / `provider_session` | provider, name, session id | node attributes |

### cmdline already carries inline scripts

`cmdline` is captured verbatim, newlines included. For example:

```
['/bin/zsh', '-lc', 'if [[ -n "$ZDOTDIR" ]]; then\n  rc="$ZDOTDIR/.zshrc"\n…']
```

For inline execution the script text is **already in the data today** and simply is not
rendered. The panel shows it in full, folding when long.

### The content boundary for tool_call

The inputs and outputs of `collaborationspawn_agent`, `collaborationsend_message` and
`collaborationwait_agent` **are the agent conversation itself**.

- **conversation-routing tools: do not show message content.** Name the agent the message
  was addressed to and say the content lives in that agent's panel.
- **non-conversation tools** such as `webrun`: show prompt and response.

The reason: v0.7.9 established that a conversation belongs to an agent and a non-agent
node must not show one. If a tool_call panel rendered its input verbatim,
`collaborationsend_message` would become a place to read agent conversations from a
non-agent node — the hole just closed, reopened through a different door.

### Verification

- browser: selecting a `collaborationsend_message` node shows no agent conversation
- browser: selecting a `webrun` node shows what was queried and what came back
- browser: selecting a process node shows the full cmdline

---

## 4. Red lines

The v0.7.9 boundaries hold and are not relaxed for this round:

1. Live, finished and `viewer.html` share one renderer.
2. Completion never calls `fetch('/final')`, `document.write()`, or replaces the DOM.
3. A conversation belongs to an agent. A non-agent node never shows one.
4. The main dashboard does not regain Conversation records, Raw node evidence, Show all
   agents, Open raw conversation evidence, Saved views, Timeline, Filters, or
   provider/relation/bytes source annotations.
5. Encrypted content reads as observed without plaintext, never as unobserved.
6. Every new contract needs a Chromium behaviour check. Source-string assertions are not
   an acceptable substitute.

---

## 5. Out of scope

Capturing file contents and rendering diffs changes the collection layer and belongs to
0.8.1. Here, a file node shows creation, modification and deletion with their timestamps.
