async function apiRequest(url, method, body) {
  var response = await fetch(url, {
    method: method || "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  var payload = await response.json().catch(function () {
    return { detail: "No JSON response body" };
  });

  if (!response.ok) {
    var error = new Error(payload.detail || "Request failed");
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  return payload;
}
