# Stock Analysis AI chatbot

Angular 19 interface for `stockanalysis_agent_csharp`. Sends JSON to
`POST /api/agent/chat`: `{ "message": "...", "mode": "short_term" }`.
Displays `answer` as sanitized Markdown, including tables and fenced code blocks
with Copy code buttons. Displays response status, model, and attempted tools.
No simulated replies or streaming endpoint are used.

## Run locally (PowerShell, two terminals)

Start your MCP services and configure the agent provider as described in
`../stockanalysis_agent_csharp/README.md`, then:

```powershell
cd C:\Repo\StockAnalysis_AI\stockanalysis_agent_csharp
dotnet run --urls http://localhost:8080
```

```powershell
cd C:\Repo\StockAnalysis_AI\Chatbot
npm ci
npm start
```

Open http://localhost:4200. `proxy.conf.json` forwards `/api/**` to port 8080.
Change its target and restart `npm start` if your API uses another address.
The browser calls its own origin, so no permissive CORS policy is required.
Keep provider keys on the API server, never in Angular or local storage.

## Behavior

- Select momentum, long-term, portfolio, or tax mode before sending.
- Enter sends; Shift+Enter inserts a newline. One request runs at a time.
- Chat messages persist under `ai_chat_history` in this browser's local storage.
  Storage failures show a warning without blocking chat. Saved text can include
  portfolio data; clear chat to remove it on a shared device.
- Clear chat removes this key and cancels the pending browser request. It does
  not delete other application storage. It does not guarantee that upstream
  model processing or billing already started will stop.
- The API is stateless: local history is display history, not model conversation
  memory. Include symbol, period, and context in each question.
- Copy code copies code text only and reports clipboard failures. Clipboard
  access requires localhost or HTTPS. Markdown HTML sanitization stays enabled.
- The browser timeout is 11 minutes to accommodate the API's configurable limit.

## Build and verify

```powershell
npm run build
npm test -- --watch=false --browsers=ChromeHeadless
```

Manual smoke test with your configured agent (paid providers may incur usage):
1. Ask for TCS news in long-term mode; inspect Network for `/api/agent/chat`,
   `{message, mode}`, and the response `answer`.
2. Reload and verify messages survive. Change mode and send another question.
3. Stop the API; send a request and verify an error appears and Send re-enables.
4. Clear while waiting; verify late replies do not return and reload stays empty.
5. Check an answer containing a Markdown table and fenced code. Copy code and
   paste it into an editor; verify only the code was copied.

## Hosting

The development proxy is used only by `ng serve`. For a production build or the
SSR Node server, configure your hosting reverse proxy to forward `/api/` to the
agent, using a timeout of at least 660 seconds. Serve the UI and API through the
same trusted origin. This change does not add deployment authentication;
keep the existing local agent private unless you add an authenticated gateway.
