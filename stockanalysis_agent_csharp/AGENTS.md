# C# agent development instructions

- Extend the existing MCP manager; preserve timeouts, reconnect handling and allowlists.
- Use MCP for external financial data; no database clients in the agent.
- Keep calculations deterministic and test numeric edge cases. Never outsource returns,
  risk statistics or tax arithmetic to the LLM.
- `Instructions/agent-system.md` is the runtime system prompt. `strategy-rules.json`
  contains user-editable starter hypotheses. Load both, include them in publish output,
  and identify their version/hash in every response. Rules are LLM guidance, not a
  deterministic trading strategy evaluator; do not describe them as backtested.
- Keep all broker actions read-only. Agent tool exposure must be the intersection of
  the manager policy and the agent allowlist. Do not add order execution.
- Tax scenarios are not tax filing calculations. No guessed rates or hidden legal assumptions.
- Preserve secrets in environment variables. Do not log prompts, account data or tool arguments.
- Bind this unauthenticated development API to loopback. Authentication, per-user account
  isolation and rate limiting are required before shared deployment.
- Run `dotnet test stockanalysis_agent_csharp/tests/StockAnalysis.Agent.Api.Tests.csproj`.
- Preserve the project's existing net8.0 target in this change. A framework migration is
  separate work; the repository's general .NET 9 guidance differs from this project/CI.
