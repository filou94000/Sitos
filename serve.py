#!/usr/bin/env python3
"""Lance le site en local pour le visualiser.

    python3 serve.py            # http://127.0.0.1:8765
    python3 serve.py 9000       # port personnalisé

Sert le dossier statique tel qu'il sera déployé. Aucune dépendance externe.
Les formulaires de leads appellent la vraie API Supabase (HTTPS) même en local :
évite d'envoyer de faux leads, ils écrivent dans la table `site_leads`.
"""
import http.server
import socketserver
import sys
import webbrowser
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
ROOT = Path(__file__).parent


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        # Pas de cache en local : on voit les modifs immédiatement.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_error(self, code, message=None, explain=None):
        # Comme Netlify : la page 404.html personnalisée pour les URL inconnues.
        page = ROOT / "404.html"
        if code == 404 and page.exists():
            body = page.read_bytes()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        super().send_error(code, message, explain)


def main() -> None:
    url = f"http://127.0.0.1:{PORT}/"
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"🌐 Site servi sur {url}  (Ctrl+C pour arrêter)")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n👋 Serveur arrêté.")


if __name__ == "__main__":
    main()
