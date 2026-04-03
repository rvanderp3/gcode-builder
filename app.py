import io
import socket
import requests as req
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, request, send_file, jsonify

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/download', methods=['POST'])
def download():
    gcode    = request.form.get('gcode', '')
    filename = request.form.get('filename', 'program.nc')
    buf      = io.BytesIO(gcode.encode('utf-8'))
    return send_file(buf, as_attachment=True, download_name=filename, mimetype='text/plain')


@app.route('/send-to-gsender', methods=['POST'])
def send_to_gsender():
    data        = request.json or {}
    host      = (data.get('host')     or 'localhost').strip()
    http_port = (data.get('httpPort') or '8000').strip()
    gcode     = data.get('gcode', '')
    name      = data.get('name', 'program.nc')

    url     = f'http://{host}:{http_port}/api/gcode'
    payload = {'gcode': gcode, 'name': name}

    try:
        resp = req.post(url, json=payload, timeout=5)
        try:
            body = resp.json()
        except Exception:
            body = {'message': resp.text}
        return jsonify(body), resp.status_code
    except req.exceptions.ConnectionError:
        return jsonify({'error': f'Could not connect to gSender at {host}:{http_port}'}), 502
    except req.exceptions.Timeout:
        return jsonify({'error': 'gSender request timed out'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _local_ip():
    """Best-effort: get the machine's outbound IP by opening a UDP socket."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def _probe(host, port, timeout=0.3):
    """Return host if TCP port is open, else None."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return host
    except Exception:
        return None


@app.route('/discover-gsender')
def discover_gsender():
    port = int(request.args.get('port', 8000))
    local = _local_ip()
    if not local:
        return jsonify({'error': 'Could not determine local IP'}), 500

    prefix = '.'.join(local.split('.')[:3])
    candidates = [f'{prefix}.{i}' for i in range(1, 255)]

    found = []
    with ThreadPoolExecutor(max_workers=64) as ex:
        futures = {ex.submit(_probe, h, port): h for h in candidates}
        for f in as_completed(futures):
            result = f.result()
            if result:
                found.append(result)

    found.sort(key=lambda ip: int(ip.split('.')[-1]))
    return jsonify({'hosts': found, 'subnet': f'{prefix}.0/24'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
