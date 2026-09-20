(function () {
  "use strict";

  const endpoint = "http://127.0.0.1:18080/__patriot_capture_event";

  globalThis.__patriotCaptureInbound = function (eventName, payload) {
    let body;
    try {
      body = JSON.stringify({
        source: "FirebaseMessaging",
        event: eventName,
        received_at: new Date().toISOString(),
        payload: payload,
      });
    } catch (error) {
      body = JSON.stringify({
        source: "FirebaseMessaging",
        event: eventName,
        received_at: new Date().toISOString(),
        serialization_error: String(error),
      });
    }

    fetch(endpoint, {
      method: "POST",
      mode: "no-cors",
      cache: "no-store",
      keepalive: true,
      body: body,
    }).catch(function () {
      // Capture must never break the stock notification handler.
    });
  };
})();
