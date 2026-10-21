import { Component, ElementRef, ViewChild, afterNextRender, effect, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { toSignal } from '@angular/core/rxjs-interop';
import { ChatService } from '../../services/chat.service';
import { AgentMode } from '../../models/chat';
import { MarkdownComponent } from 'ngx-markdown';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, MarkdownComponent],
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.css'
})
export class ChatComponent {
  readonly chatService = inject(ChatService);
  @ViewChild('scrollContainer') private scrollContainer?: ElementRef<HTMLDivElement>;
  messages = toSignal(this.chatService.messages$, { initialValue: [] });
  draft = '';
  mode: AgentMode = 'short_term';
  readonly copyStatus = signal('');

  constructor() {
    afterNextRender(() => this.chatService.initialize());
    effect(() => {
      this.messages();
      queueMicrotask(() => {
        const container = this.scrollContainer?.nativeElement;
        if (container) container.scrollTop = container.scrollHeight;
      });
    });
  }

  onSend(): void {
    if (!this.draft.trim() || this.chatService.busy()) return;
    this.chatService.sendMessage(this.draft, this.mode);
    this.draft = '';
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      this.onSend();
    }
  }

  clearChat(): void {
    this.chatService.clearHistory();
    this.copyStatus.set('');
  }

  // Use textContent, never HTML, for clipboard data from rendered code blocks.
  async copyCode(event: MouseEvent): Promise<void> {
    const target = event.target;
    if (!(target instanceof HTMLElement) || !target.classList.contains('copy-code')) return;
    const code = target.parentElement?.querySelector('code');
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code.textContent ?? '');
      this.copyStatus.set('Code copied.');
    } catch {
      this.copyStatus.set('Copy unavailable. Select the code and copy it manually.');
    }
  }

  addCopyButtons(container: HTMLElement): void {
    container.querySelectorAll('pre').forEach(pre => {
      if (pre.querySelector('.copy-code')) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'copy-code';
      button.textContent = 'Copy code';
      pre.appendChild(button);
    });
  }
}
