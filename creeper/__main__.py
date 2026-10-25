import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .ingress import DeepWater, MAX_BODY, Rejected, Sail


def make_server(sail, host="127.0.0.1", port=8787):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def respond(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.respond(200, {"status": "afloat"}) if self.path == "/healthz" else self.respond(404, {"error": "not_found"})

        def do_POST(self):
            if self.path != "/webhooks/github":
                return self.respond(404, {"error": "not_found"})
            try:
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or self.headers.get("Transfer-Encoding"):
                    raise Rejected(400, "content_length_required")
                length = int(lengths[0])
                if length < 0 or length > MAX_BODY:
                    raise Rejected(413, "payload_too_large")
                if self.headers.get_content_type() != "application/json":
                    raise Rejected(415, "json_required")
                body = self.rfile.read(length)
                if len(body) != length:
                    raise Rejected(400, "incomplete_body")
                result = sail.capture(dict(self.headers), body)
                self.respond(202 if "delivery" in result else 200, result)
            except Rejected as error:
                self.respond(error.status, {"error": error.reason})
            except (ValueError, TimeoutError):
                self.respond(400, {"error": "invalid_request"})
            except Exception:
                self.respond(503, {"error": "ingress_unavailable_retry_later"})

        def log_message(self, *_args):
            pass

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["listen", "digest", "status"])
    parser.add_argument("--state", default=".creeper")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--once", action="store_true")
    arguments = parser.parse_args()
    water = DeepWater(arguments.state)
    repositories = [item.strip() for item in os.environ.get("CREEPER_REPOSITORIES", "").split(",") if item.strip()]
    if arguments.command == "status":
        print(json.dumps(water.records(), indent=2))
    elif arguments.command == "listen":
        sail = Sail(water, os.environ.get("CREEPER_WEBHOOK_SECRET", ""), repositories)
        server = make_server(sail, port=arguments.port)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    else:
        from .digest import SpatialModel, digest_once
        from .source import GitHubSources
        from .gemma import reviewer_from_environment
        if not repositories:
            parser.error("CREEPER_REPOSITORIES is required")
        model = SpatialModel()
        resolver = GitHubSources(repositories)
        reviewer = reviewer_from_environment()
        while True:
            result = digest_once(water, resolver, model, reviewer=reviewer)
            if result:
                print(json.dumps(result), flush=True)
            if arguments.once:
                break
            if result is None:
                time.sleep(5)


if __name__ == "__main__":
    main()
