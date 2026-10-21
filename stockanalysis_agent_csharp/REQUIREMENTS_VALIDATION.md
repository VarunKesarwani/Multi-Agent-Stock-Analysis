# Agent validation — 2026-10-03

## Before this change
Inspected main at commit 00c8c761173007e61e371fe1cc9f8701cc9eb03b.
`Program.cs` exposed MCP status, discovery, refresh and invoke endpoints only.
`IMcpClientManager.GetAgentFunctionsAsync` already returned policy-wrapped AIFunctions.
README explicitly deferred Ollama orchestration. The project existed, but the LLM agent
was not implemented in that project. This is source validation, not a live service test.

## Implementation and remaining data requirements
| Requirement | Implementation | Prerequisite / limitation |
|---|---|---|
| LLM orchestration | Bounded Ollama /api/chat loop using existing manager AIFunctions | Tool-capable local model and running MCP services |
| Short-term momentum | Runtime instructions and editable JSON for MACD, EMA 5/13/21/55, RSI, volume, news | Complete daily bars, warmup, timestamps; hypotheses unbacktested; no deterministic signal engine |
| Long-term investing | Financial and annual-report retrieval instructions | Populated financial data; annual-report server enabled; ratio weights not supplied |
| Portfolio CAGR | Deterministic endpoint/tool | No external flows; actual dated start/end values |
| Portfolio XIRR | Deterministic endpoint/tool | Full conventional cash-flow history and terminal value; ambiguous multiple sign changes rejected |
| Sharpe/TWR/volatility/drawdown | Deterministic endpoint/tool | Regular net total returns, adjusted external flows, explicit risk-free rate and frequency |
| Portfolio reconstruction | Not implemented by this change | Historical trades, cash ledger, fees, dividends, corporate actions, daily valuations needed; live holdings insufficient |
| Tax details | Input-gated arithmetic scenario endpoint/tool | Reconciled taxable gains, financial year, jurisdiction, verified rates/source; not FIFO or full tax engine |
| Broker integration | Existing manager and two-layer tool allowlist | Interactive Kite login and available read tools; no trades |
| Chat UI | API ready for Angular | UI, durable conversations and multi-user auth remain separate |

## Tax requirements
India is a likely jurisdiction, but the agent must ask rather than silently assume it.
Demat share capital-gain reconciliation needs FIFO acquisition lots per account. A full
implementation must handle corporate actions, holding-period classification, instrument
eligibility, STT conditions, allowable expenses, grandfathering, losses, aggregate annual
exemptions, dividends, residency, applicable slabs, surcharge/cess and marginal relief.
Intraday/F&O/business-income and foreign assets require distinct rules. Effective dates
must be versioned. No statutory rate is embedded in this change.

Authoritative requirement reference reviewed: https://www.incometaxindia.gov.in/sale-of-shares
Ollama tool-loop contract: https://docs.ollama.com/capabilities/tool-calling

## Boundaries
The runtime policy is loaded from Markdown plus JSON. It guides model analysis; it cannot
guarantee model correctness. The agent has bounded tool rounds, timeouts and explicit
allowlists; deterministic calculators validate their inputs. Returned tool traces record
which functions ran, but are not proof that every claim in generated text is correct.
A failed/oversized tool response must remain unavailable evidence, never neutral evidence.

## Verification
Release build and 30 unit/integration tests passed using .NET SDK 8.0.425.
Tests cover known numeric examples, zero-volatility Sharpe, cash-flow rejection,
ambiguous XIRR, required tax inputs, tool allowlists and bounded Ollama loops using a
mock HTTP handler. No live Ollama, Kite, database or personal portfolio was accessed.
