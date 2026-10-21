import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideMarkdown } from 'ngx-markdown';
import { ChatComponent } from './chat.component';

describe('ChatComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [ChatComponent], providers: [provideHttpClient(), provideMarkdown()] }));
  it('preserves Shift+Enter and blocks plain Enter newline', () => {
    const component = TestBed.createComponent(ChatComponent).componentInstance;
    const send = spyOn(component, 'onSend');
    component.onKeydown(new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true }));
    expect(send).not.toHaveBeenCalled();
    component.onKeydown(new KeyboardEvent('keydown', { key: 'Enter' }));
    expect(send).toHaveBeenCalled();
  });
  it('adds one copy button per code block', () => {
    const component = TestBed.createComponent(ChatComponent).componentInstance;
    const container = document.createElement('div');
    container.innerHTML = '<pre><code>const n = 1;</code></pre>';
    component.addCopyButtons(container);
    component.addCopyButtons(container);
    expect(container.querySelectorAll('button.copy-code').length).toBe(1);
  });
});
