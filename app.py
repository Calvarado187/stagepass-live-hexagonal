import argparse
from bootstrap import build
from adapters.http import make_server
from adapters.scheduler import ExpiryScheduler


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='StagePass Live · demostración local')
    parser.add_argument('--port', type=int, default=8083)
    args = parser.parse_args()
    service = build()
    server = make_server(service, service.gateways, args.port)
    scheduler = ExpiryScheduler(service)
    scheduler.start()
    print(f'StagePass Live: http://127.0.0.1:{args.port}', flush=True)
    print('Demo: no se realizan cobros; los datos se reinician al cerrar. Ctrl+C para salir.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.close()
        server.server_close()
