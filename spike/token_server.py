#!/usr/bin/env python3
"""Local LiveKit token server. Serves JWTs at GET /token?room=voice&identity=user"""
import json
import sys
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LIVEKIT_API_KEY = os.environ.get('LIVEKIT_API_KEY', 'devkey')
LIVEKIT_API_SECRET = os.environ.get('LIVEKIT_API_SECRET', 'XhtHLb2P1O6vZBy5uuLEegDQFk-Tg6RcTbTZGzXm840')
LIVEKIT_WS_URL = os.environ.get('LIVEKIT_WS_URL', 'wss://hyggan-system-product-name.tail19f0b5.ts.net:10000')
PORT = int(os.environ.get('TOKEN_PORT', '8080'))


class TokenHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f'[token_server] {format % args}')

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path not in ('/token', '/'):
            self.send_response(404)
            self.end_headers()
            return

        from livekit import api as lk_api
        params = parse_qs(parsed.query)
        room = params.get('room', ['voice'])[0]
        identity = params.get('identity', ['user'])[0]

        token = (
            lk_api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_identity(identity)
            .with_grants(lk_api.VideoGrants(room_join=True, room=room))
            .to_jwt()
        )

        body = json.dumps({'token': token, 'url': LIVEKIT_WS_URL}).encode()
        self.send_response(200)
        self._cors()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')


if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', PORT), TokenHandler)
    print(f'[token_server] listening on 127.0.0.1:{PORT}')
    server.serve_forever()
