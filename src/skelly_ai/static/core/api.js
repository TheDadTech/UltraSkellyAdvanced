(() => {
  const USA = window.USA = window.USA || {};

  class ApiError extends Error {
    constructor(message, { status = 0, url = "", payload = null } = {}) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.url = url;
      this.payload = payload;
    }
  }

  async function request(url, options = {}) {
    const headers = new Headers(options.headers || {});
    const init = { ...options, headers };

    if (
      init.body &&
      typeof init.body !== "string" &&
      !(init.body instanceof FormData)
    ) {
      headers.set("Content-Type", "application/json");
      init.body = JSON.stringify(init.body);
    }

    let response;

    try {
      response = await fetch(url, init);
    } catch (error) {
      throw new ApiError(
        error?.message || "Network request failed",
        { url }
      );
    }

    const contentType = response.headers.get("content-type") || "";
    let payload = null;

    if (response.status !== 204) {
      try {
        payload = contentType.includes("application/json")
          ? await response.json()
          : await response.text();
      } catch {
        payload = null;
      }
    }

    if (!response.ok) {
      const message =
        (payload &&
          typeof payload === "object" &&
          (payload.detail || payload.error || payload.message)) ||
        (typeof payload === "string" && payload.trim()) ||
        `Request failed (${response.status})`;

      throw new ApiError(String(message), {
        status: response.status,
        url,
        payload
      });
    }

    return payload;
  }

  USA.api = {
    ApiError,
    request,

    get(url, options = {}) {
      return request(url, {
        ...options,
        method: "GET"
      });
    },

    post(url, body = undefined, options = {}) {
      return request(url, {
        ...options,
        method: "POST",
        body
      });
    }
  };
})();
