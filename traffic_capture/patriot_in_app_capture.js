(function () {
  "use strict";

  if (globalThis.__alaskaCaptureInstalled) return;
  globalThis.__alaskaCaptureInstalled = true;

  const emit = (event) => {
    try {
      globalThis.AlaskaCapture?.record(JSON.stringify(event));
    } catch (_) {
      // Recording must never affect vendor traffic or application control flow.
    }
  };

  const bytesToBase64 = (bytes) => {
    let binary = "";
    const view = new Uint8Array(bytes);
    for (let offset = 0; offset < view.length; offset += 0x8000) {
      binary += String.fromCharCode.apply(null, view.subarray(offset, offset + 0x8000));
    }
    return btoa(binary);
  };

  const bodyRecord = async (value) => {
    try {
      if (value == null) return {};
      if (value instanceof Blob) {
        return { type: value.type || "", base64: bytesToBase64(await value.arrayBuffer()) };
      }
      if (value instanceof ArrayBuffer || ArrayBuffer.isView(value)) {
        const buffer = value instanceof ArrayBuffer
          ? value
          : value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength);
        return { base64: bytesToBase64(buffer) };
      }
      return { text: String(value) };
    } catch (error) {
      return { capture_error: String(error) };
    }
  };

  const headerPairs = (headers) => {
    const result = [];
    try {
      new Headers(headers).forEach((value, name) => result.push([name, value]));
    } catch (_) {}
    return result;
  };

  const originalFetch = globalThis.fetch.bind(globalThis);
  globalThis.fetch = function (input, init) {
    const flowId = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    const started = Date.now();
    let request;
    try {
      request = new Request(input, init);
      const copy = request.clone();
      copy.arrayBuffer().then((body) => emit({
        kind: "http_request",
        flow_id: flowId,
        started_at_ms: started,
        method: request.method,
        url: request.url,
        headers: headerPairs(request.headers),
        body: { base64: bytesToBase64(body) },
      })).catch((error) => emit({
        kind: "http_request",
        flow_id: flowId,
        started_at_ms: started,
        method: request.method,
        url: request.url,
        headers: headerPairs(request.headers),
        body: { capture_error: String(error) },
      }));
    } catch (_) {
      request = input;
    }
    return originalFetch(input, init).then((response) => {
      const copy = response.clone();
      copy.arrayBuffer().then((body) => emit({
        kind: "http_response",
        flow_id: flowId,
        url: response.url,
        status: response.status,
        status_text: response.statusText,
        headers: headerPairs(response.headers),
        duration_ms: Date.now() - started,
        body: { base64: bytesToBase64(body) },
      })).catch((error) => emit({
        kind: "http_response",
        flow_id: flowId,
        url: response.url,
        status: response.status,
        headers: headerPairs(response.headers),
        duration_ms: Date.now() - started,
        body: { capture_error: String(error) },
      }));
      return response;
    }, (error) => {
      emit({ kind: "http_error", flow_id: flowId, url: request?.url || String(input), error: String(error), duration_ms: Date.now() - started });
      throw error;
    });
  };

  const OriginalXHR = globalThis.XMLHttpRequest;
  if (OriginalXHR) {
    const open = OriginalXHR.prototype.open;
    const setRequestHeader = OriginalXHR.prototype.setRequestHeader;
    const send = OriginalXHR.prototype.send;
    OriginalXHR.prototype.open = function (method, url) {
      this.__alaska = { flow_id: crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`, method, url: String(url), headers: [], started_at_ms: Date.now() };
      return open.apply(this, arguments);
    };
    OriginalXHR.prototype.setRequestHeader = function (name, value) {
      this.__alaska?.headers.push([String(name), String(value)]);
      return setRequestHeader.apply(this, arguments);
    };
    OriginalXHR.prototype.send = function (body) {
      const meta = this.__alaska || { flow_id: `${Date.now()}-${Math.random()}`, headers: [], started_at_ms: Date.now() };
      bodyRecord(body).then((captured) => emit({ kind: "http_request", ...meta, body: captured }));
      this.addEventListener("loadend", async () => {
        let responseBody = {};
        try {
          responseBody = await bodyRecord(this.responseType === "" || this.responseType === "text" ? this.responseText : this.response);
        } catch (error) {
          responseBody = { capture_error: String(error) };
        }
        emit({
          kind: "http_response",
          flow_id: meta.flow_id,
          url: this.responseURL || meta.url,
          status: this.status,
          status_text: this.statusText,
          headers_raw: this.getAllResponseHeaders(),
          duration_ms: Date.now() - meta.started_at_ms,
          body: responseBody,
        });
      }, { once: true });
      return send.apply(this, arguments);
    };
  }

  const OriginalWebSocket = globalThis.WebSocket;
  if (OriginalWebSocket) {
    globalThis.WebSocket = new Proxy(OriginalWebSocket, {
      construct(Target, args, NewTarget) {
        const socket = Reflect.construct(Target, args, NewTarget);
        const url = String(args[0]);
        const nativeSend = socket.send;
        socket.send = function (data) {
          bodyRecord(data).then((body) => emit({ kind: "websocket_message", direction: "client_to_server", url, body }));
          return nativeSend.apply(this, arguments);
        };
        socket.addEventListener("message", (message) => {
          bodyRecord(message.data).then((body) => emit({ kind: "websocket_message", direction: "server_to_client", url, body }));
        });
        socket.addEventListener("close", (event) => emit({ kind: "websocket_close", url, code: event.code, reason: event.reason }));
        return socket;
      },
    });
  }

  globalThis.addEventListener("pagehide", () => globalThis.AlaskaCapture?.flush());
})();
