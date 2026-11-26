# Writes are confirmed by elicitation in either protocol era; `confirm: true` only where the client cannot ask

`raise_dispute` and `flag_transaction_for_review` change money-adjacent records, and the arguments that request them come from a model that may be manipulated (security LLD, LLM06 excessive agency). A write therefore happens only once the person behind the MCP client agrees to it. When the client declares the elicitation capability, the gateway asks through MCP elicitation in whichever protocol era the connection negotiated: on 2026-07-28 connections, which have no server-initiated requests, the tool answers `input_required` with the question and the client calls again carrying the answer; on earlier connections it sends `elicitation/create` during the call. Only a client that cannot ask may pass `confirm: true`, and when the client can ask, `confirm` is ignored, because a model sets arguments and only the client's prompt reaches the person. A no, a decline or a dismissal is a `declined` error and nothing is written. Because the gateway is deployed as stateless Streamable HTTP, a 2025-era client's capabilities, sent once at `initialize`, are unknown to its later requests, so over the deployed transport such clients confirm with `confirm: true`; 2026-07-28 clients send their capabilities with every request and are asked.

## Considered Options

- **`confirm: true` everywhere**: one code path, but it is the model, not the person, that sets it, so it only documents intent.
- **Honour `confirm: true` even when the client can ask**: saves a prompt, but lets a prompt-injected model skip the one control a person sees.
- **Carry the question's arguments in `request_state`** to bind the answer to them: FastMCP seals it with a per-process key unless a shared key is configured, so on Lambda the second leg could fail on another instance; and a client that can forge an answer can equally skip asking, so the binding adds little.
- **Stateful or streamed HTTP so 2025-era clients can be asked too**: needs session affinity or a response stream through the Lambda Web Adapter, against the plan's stateless, any-instance deployment; those clients are the shrinking population.

## Consequences

- The confirmation is only as trustworthy as the client application; the gateway trusts what the client reports the person answered, as it trusts the client with the person's token.
- `declined` joins the error taxonomy (LLD §4): not retryable without asking the person again.
- `tests/test_write_tools.py` runs both eras in memory and the deployed transport itself (`serve_http`), so a transport change that starts or stops prompting 2025-era clients fails a test.
