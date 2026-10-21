import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { ChatService } from './chat.service';
import { ChatMessage } from '../models/chat';

describe('ChatService', () => {
  let service: ChatService;
  let http: HttpTestingController;
  let messages: ChatMessage[];
  beforeEach(() => {
    localStorage.removeItem('ai_chat_history');
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(ChatService);
    http = TestBed.inject(HttpTestingController);
    service.messages$.subscribe(value => messages = value);
    service.initialize();
  });
  afterEach(() => { http.verify(); localStorage.removeItem('ai_chat_history'); });

  it('posts the API contract, renders the answer and persists completed messages', () => {
    service.sendMessage(' TCS risks ', 'long_term');
    const request = http.expectOne('/api/agent/chat');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ message: 'TCS risks', mode: 'long_term' });
    expect(JSON.parse(localStorage.getItem('ai_chat_history')!).length).toBe(1);
    request.flush({ answer: 'Evidence', status: 'incomplete', tools: [], model: 'test', mode: 'long_term', policyVersion: '1' });
    expect(messages[1].text).toBe('Evidence');
    expect(messages[1].response?.status).toBe('incomplete');
    expect(service.busy()).toBeFalse();
    expect(JSON.parse(localStorage.getItem('ai_chat_history')!).length).toBe(2);
  });

  it('blocks duplicate sends and cancels an in-flight request on clear', () => {
    service.sendMessage('TCS', 'short_term');
    service.sendMessage('duplicate', 'short_term');
    const request = http.expectOne('/api/agent/chat');
    service.clearHistory();
    expect(request.cancelled).toBeTrue();
    expect(messages).toEqual([]);
    expect(localStorage.getItem('ai_chat_history')).toBeNull();
    expect(service.busy()).toBeFalse();
  });

  it('shows API failures and allows another request', () => {
    service.sendMessage('TCS', 'short_term');
    http.expectOne('/api/agent/chat').flush({}, { status: 503, statusText: 'Unavailable' });
    expect(messages[1].text).toContain('unavailable');
    expect(service.busy()).toBeFalse();
  });

  it('keeps chatting when storage writes are blocked', () => {
    spyOn(Storage.prototype, 'setItem').and.throwError('quota');
    service.sendMessage('TCS', 'portfolio');
    http.expectOne('/api/agent/chat').flush({ answer: 'Answer' });
    expect(messages[1].text).toBe('Answer');
    expect(service.storageWarning()).toContain('could not be saved');
  });
});

describe('Chat history loading', () => {
  afterEach(() => localStorage.removeItem('ai_chat_history'));
  it('rejects malformed history without crashing', () => {
    localStorage.setItem('ai_chat_history', '{broken');
    TestBed.configureTestingModule({ providers: [provideHttpClient()] });
    const service = TestBed.inject(ChatService);
    service.initialize();
    expect(service.storageWarning()).toContain('could not be loaded');
  });
  it('restores messages and Date values', () => {
    localStorage.setItem('ai_chat_history', JSON.stringify([{ id: 'a', sender: 'user', text: 'TCS', timestamp: '2026-10-06T00:00:00Z' }]));
    TestBed.configureTestingModule({ providers: [provideHttpClient()] });
    const service = TestBed.inject(ChatService);
    service.initialize();
    service.messages$.subscribe(messages => {
      expect(messages[0].text).toBe('TCS');
      expect(messages[0].timestamp instanceof Date).toBeTrue();
    });
  });
});
