// Restricts message sources to either 'user' or 'agent'
export type MessageSender = 'user' | 'agent';

export interface ChatMessage {
  id: string;
  sender: MessageSender;
  text: string;
  timestamp: Date;
  response?: AgentResponse;
  isPending?: boolean; // True while waiting for AI response
}

export interface Chat {
  id: string;
  messages: ChatMessage[];
}

export type AgentMode = 'short_term' | 'long_term' | 'portfolio' | 'tax';
export interface AgentResponse {
  answer: string;
  mode: AgentMode;
  model: string;
  policyVersion: string;
  tools: { name: string; status: string }[];
  status: string;
}
