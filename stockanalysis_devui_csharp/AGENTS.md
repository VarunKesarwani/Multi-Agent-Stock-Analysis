# DevUI adapter instructions

- Keep this project on net8.0 and use the official Microsoft Agent Framework DevUI.
- Route analysis through the existing /api/agent/chat contract. Do not duplicate the LLM loop, MCP manager, trading rules or broker credentials.
- Preserve the backend's four modes, status, policy identity and tool audit information.
- The backend is stateless and non-streaming. Do not claim conversational memory or live tool/token streaming.
- Keep all endpoints loopback-only and Development-only. Never log chat bodies, portfolio data or tokens.
- Add no trading or order execution capabilities.
- Test the adapter with a fake backend; never use live broker data in tests.
- Run dotnet test stockanalysis_devui_csharp/tests/StockAnalysis.DevUI.Tests.csproj and the existing agent tests.
