export class PipelineWSClient {
  constructor(url, onMessage, onStatusChange) {
    this.url = url;
    this.onMessage = onMessage;
    this.onStatusChange = onStatusChange;
    this.ws = null;
    this.reconnectTimer = null;
    this.isConnected = false;
  }

  connect() {
    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.isConnected = true;
        if (this.onStatusChange) this.onStatusChange(true);
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer);
          this.reconnectTimer = null;
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (this.onMessage) this.onMessage(payload);
        } catch (e) {
          console.error("WS Parse Error:", e);
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        if (this.onStatusChange) this.onStatusChange(false);
        this.scheduleReconnect();
      };

      this.ws.onerror = (err) => {
        console.warn("WS Error:", err);
        if (this.ws) this.ws.close();
      };
    } catch (err) {
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    if (!this.reconnectTimer) {
      this.reconnectTimer = setTimeout(() => {
        this.connect();
      }, 2500);
    }
  }

  send(action, params = {}) {
    if (this.ws && this.isConnected) {
      this.ws.send(JSON.stringify({ action, params }));
    }
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.ws) this.ws.close();
  }
}
