class DynamicExtHeaderCorsMiddleware:
    """
    Dynamically allow any ``X-LTAI-EXT-*`` header through CORS so that
    different customers can use their own header keys without requiring
    a code change.

    Must be placed in MIDDLEWARE immediately **after**
    ``corsheaders.middleware.CorsMiddleware`` so it can augment the
    Access-Control-Allow-Headers that CorsMiddleware already set.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.method == "OPTIONS":
            requested = request.headers.get("Access-Control-Request-Headers", "")
            ext_headers = [
                h.strip() for h in requested.split(",")
                if h.strip().lower().startswith("x-ltai-ext-")
            ]
            if ext_headers:
                existing = response.get("Access-Control-Allow-Headers", "")
                already_lower = {h.strip().lower() for h in existing.split(",") if h.strip()}
                new_headers = [h for h in ext_headers if h.strip().lower() not in already_lower]
                if new_headers:
                    merged = ", ".join(filter(None, [existing] + new_headers))
                    response["Access-Control-Allow-Headers"] = merged
        return response
