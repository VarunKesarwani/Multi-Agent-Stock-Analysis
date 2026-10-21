import { Injectable, inject, signal } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { BehaviorSubject, Subscription, timeout } from 'rxjs';
import { ChatMessage, AgentMode, AgentResponse } from '../models/chat';

const STORAGE_KEY = 'ai_chat_history';

@Injectable({ providedIn: 'root' })
export class ChatService {
  private http = inject(HttpClient);
  private messagesSubject = new BehaviorSubject<ChatMessage[]>([]);
  readonly messages$ = this.messagesSubject.asObservable();
  readonly busy = signal(false);
  readonly storageWarning = signal('');
  private request?: Subscription;
  private initialized = false;
  private sequence = 0;

  // Called after the first browser render so SSR and hydration start identically.
  initialize(): void {
    if (this.initialized) return;
    this.initialized = true;
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (!saved) return;
      const parsed: unknown = JSON.parse(saved);
      if (!Array.isArray(parsed)) throw new Error('Invalid history');
      const ids = new Set<string>();
      const messages = parsed.map((m: any): ChatMessage => {
        if (!m || typeof m.id !== 'string' || ids.has(m.id) ||
            !['user', 'agent'].includes(m.sender) || typeof m.text !== 'string' ||
            typeof m.timestamp !== 'string' || !Number.isFinite(Date.parse(m.timestamp))) {
          throw new Error('Invalid history');
        }
        ids.add(m.id);
        return { id: m.id, sender: m.sender, text: m.text, timestamp: new Date(m.timestamp) };
      });
      this.messagesSubject.next(messages);
    } catch {
      this.storageWarning.set('Saved chat could not be loaded. You can still chat or clear the saved history.');
    }
  }

  private publish(messages: ChatMessage[]): void {
    this.messagesSubject.next(messages);
    if (!this.initialized) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.filter(m => !m.isPending)));
      this.storageWarning.set('');
    } catch {
      this.storageWarning.set('Chat is available in this tab but could not be saved on this device.');
    }
  }

  clearHistory(): void {
    this.request?.unsubscribe();
    this.request = undefined;
    this.busy.set(false);
    this.messagesSubject.next([]);
    try {
      localStorage.removeItem(STORAGE_KEY);
      this.storageWarning.set('');
    } catch {
      this.storageWarning.set('Chat cleared in this tab, but saved history could not be removed.');
    }
  }

  sendMessage(text: string, mode: AgentMode): void {
    text = text.trim();
    if (!text || this.busy()) return;
    const id = `${Date.now()}-${++this.sequence}`;
    this.busy.set(true);
    this.publish([...this.messagesSubject.value,
      { id: `${id}-user`, sender: 'user', text, timestamp: new Date() },
      { id, sender: 'agent', text: 'Analyzing your request…', timestamp: new Date(), isPending: true }
    ]);
    this.request = this.http.post<AgentResponse>('/api/agent/chat', { message: text, mode })
      .pipe(timeout(660000))
      .subscribe({
        next: response => {
          if (!response || typeof response.answer !== 'string' || !response.answer.trim()) {
            this.finish(id, 'The agent returned an invalid or empty answer. Please try again.');
            return;
          }
          this.finish(id, response.answer, { ...response, tools: Array.isArray(response.tools)
            ? response.tools.filter(tool => tool && typeof tool.name === 'string' && typeof tool.status === 'string') : [] });
        },
        error: (error: unknown) => {
          const status = error instanceof HttpErrorResponse ? error.status : undefined;
          const messages: Record<number, string> = {
            0: 'Cannot reach the agent. Check that the API is running and the proxy target is correct.',
            400: 'The agent rejected this request. Check the message length and selected mode.',
            502: 'The model provider is unavailable. Check the agent provider configuration.',
            503: 'The agent is unavailable. Check that it is enabled and configured.',
            504: 'The agent timed out. Try a narrower question.'
          };
          this.finish(id, status !== undefined ? (messages[status] ?? `Request failed (HTTP ${status}). Please try again.`)
            : 'The request timed out. Please try a narrower question.');
        }
      });
  }

  private finish(id: string, text: string, response?: AgentResponse): void {
    this.busy.set(false);
    this.publish(this.messagesSubject.value.map(m => m.id === id
      ? { ...m, text, isPending: false, response } : m));
  }
}
