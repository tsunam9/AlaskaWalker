package ai.alaskawalker.capture;

import android.util.Base64;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.util.UUID;

import okhttp3.Headers;
import okhttp3.Interceptor;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.ResponseBody;
import okio.Buffer;
import okio.ByteString;

/** Records the final OkHttp request and response without mutating either. */
public final class CaptureInterceptor implements Interceptor {
    private static final long BODY_LIMIT = 32L * 1024L * 1024L;

    @Override
    public Response intercept(Chain chain) throws IOException {
        Request request = chain.request();
        String flowId = UUID.randomUUID().toString();
        long started = System.currentTimeMillis();
        InAppTrafficRecorder.record(requestEvent(flowId, request, started));
        try {
            Response response = chain.proceed(request);
            InAppTrafficRecorder.record(responseEvent(flowId, response, started));
            return response;
        } catch (IOException error) {
            JSONObject event = base("http_error", flowId);
            put(event, "url", request.url().toString());
            put(event, "error", error.toString());
            put(event, "duration_ms", System.currentTimeMillis() - started);
            InAppTrafficRecorder.record(event);
            throw error;
        }
    }

    private static JSONObject requestEvent(String flowId, Request request, long started) {
        JSONObject event = base("http_request", flowId);
        put(event, "started_at_ms", started);
        put(event, "method", request.method());
        put(event, "url", request.url().toString());
        put(event, "headers", headers(request.headers()));
        put(event, "body", requestBody(request.body()));
        return event;
    }

    private static JSONObject responseEvent(String flowId, Response response, long started) {
        JSONObject event = base("http_response", flowId);
        put(event, "url", response.request().url().toString());
        put(event, "status", response.code());
        put(event, "message", response.message());
        put(event, "protocol", response.protocol().toString());
        put(event, "headers", headers(response.headers()));
        put(event, "duration_ms", System.currentTimeMillis() - started);
        put(event, "body", responseBody(response));
        return event;
    }

    private static JSONObject base(String kind, String flowId) {
        JSONObject event = new JSONObject();
        put(event, "kind", kind);
        put(event, "flow_id", flowId);
        return event;
    }

    private static JSONArray headers(Headers headers) {
        JSONArray result = new JSONArray();
        for (int index = 0; index < headers.size(); index++) {
            JSONArray pair = new JSONArray();
            pair.put(headers.name(index));
            pair.put(headers.value(index));
            result.put(pair);
        }
        return result;
    }

    private static JSONObject requestBody(RequestBody body) {
        JSONObject result = new JSONObject();
        if (body == null) return result;
        try {
            if (body.contentType() != null) put(result, "content_type", body.contentType().toString());
            long length = body.contentLength();
            put(result, "declared_length", length);
            if (body.isDuplex() || body.isOneShot() || length > BODY_LIMIT) {
                put(result, "omitted", true);
                put(result, "reason", body.isDuplex() ? "duplex" : body.isOneShot() ? "one_shot" : "size_limit");
                return result;
            }
            Buffer buffer = new Buffer();
            body.writeTo(buffer);
            put(result, "base64", Base64.encodeToString(buffer.readByteArray(), Base64.NO_WRAP));
        } catch (Throwable error) {
            put(result, "capture_error", error.toString());
        }
        return result;
    }

    private static JSONObject responseBody(Response response) {
        JSONObject result = new JSONObject();
        try {
            ResponseBody body = response.body();
            if (body == null) return result;
            if (body.contentType() != null) put(result, "content_type", body.contentType().toString());
            long length = body.contentLength();
            put(result, "declared_length", length);
            ResponseBody peek = response.peekBody(BODY_LIMIT);
            byte[] bytes = peek.bytes();
            put(result, "base64", Base64.encodeToString(bytes, Base64.NO_WRAP));
            put(result, "truncated", length > BODY_LIMIT || bytes.length == BODY_LIMIT);
        } catch (Throwable error) {
            put(result, "capture_error", error.toString());
        }
        return result;
    }

    public static void recordWebSocketText(Object socket, boolean inbound, String text) {
        JSONObject event = webSocketBase(socket, inbound, "text");
        put(event, "text", text);
        InAppTrafficRecorder.record(event);
    }

    public static void recordWebSocketBytes(Object socket, boolean inbound, ByteString bytes) {
        JSONObject event = webSocketBase(socket, inbound, "binary");
        if (bytes != null) put(event, "base64", Base64.encodeToString(bytes.toByteArray(), Base64.NO_WRAP));
        InAppTrafficRecorder.record(event);
    }

    private static JSONObject webSocketBase(Object socket, boolean inbound, String messageType) {
        JSONObject event = new JSONObject();
        put(event, "kind", "websocket_message");
        put(event, "direction", inbound ? "server_to_client" : "client_to_server");
        put(event, "message_type", messageType);
        try {
            Object request = socket.getClass().getMethod("request").invoke(socket);
            put(event, "url", request.getClass().getMethod("url").invoke(request).toString());
        } catch (Throwable ignored) {
        }
        return event;
    }

    private static void put(JSONObject target, String name, Object value) {
        try {
            target.put(name, value);
        } catch (Throwable ignored) {
        }
    }
}
