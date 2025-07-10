class Request:
    def __init__(self, method="GET", args=None, json=None):
        self.method = method
        self.args = args or {}
        self.json = json or {}

class Response:
    def __init__(self, data="", status=200, headers=None, mimetype="application/json"):
        self.data = data
        self.status = status
        self.headers = headers or {}
        self.mimetype = mimetype

    # allow FastAPI JSON conversion
    def json(self):
        return self.data

# Decorator stub that simply returns the function unchanged
def on_request():
    def decorator(func):
        return func
    return decorator
