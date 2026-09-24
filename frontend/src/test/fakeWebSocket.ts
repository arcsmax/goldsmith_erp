// Minimal WebSocket stand-in for Vitest (W2-13). Records every instance so
// tests can drive open/message/close from the "server" side.
import { vi } from 'vitest';

export class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  static latest(): FakeWebSocket {
    const socket = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    if (!socket) throw new Error('No FakeWebSocket was created');
    return socket;
  }

  readonly url: string;
  readonly sent: string[] = [];
  closedByClient = false;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.closedByClient = true;
    this.onclose?.({ code: 1000 } as CloseEvent);
  }

  open(): void {
    this.onopen?.({} as Event);
  }

  serverSend(payload: unknown): void {
    this.serverSendRaw(JSON.stringify(payload));
  }

  serverSendRaw(data: string): void {
    this.onmessage?.({ data } as MessageEvent);
  }

  serverClose(code = 1011): void {
    this.onclose?.({ code } as CloseEvent);
  }
}

export function installFakeWebSocket(): void {
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket);
}
