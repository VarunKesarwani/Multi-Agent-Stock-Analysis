import { Component } from '@angular/core';
import { ChatComponent } from './components/chat/chat.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [ChatComponent],
  template: `<app-chat></app-chat>`
  //templateUrl: './app.component.html',
  //styleUrls: './app.component.css'
})
export class AppComponent {
  title = 'Chatbot';
}
