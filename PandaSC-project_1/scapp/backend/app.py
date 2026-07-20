import os
import sys
import threading
import webbrowser

from flask import Flask, jsonify, request, render_template, send_file
import io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import license_manager as lm
from network_store import NetworkStore

app = Flask(__name__)
store = NetworkStore()


# ---------------------------------------------------------------- license --

@app.route("/api/license/status")
def license_status():
    return jsonify(lm.current_status())


@app.route("/api/license/activate", methods=["POST"])
def license_activate():
    key = (request.json or {}).get("key", "")
    ok, msg = lm.validate_key(key)
    if not ok:
        return jsonify({"activated": False, "message": msg}), 400
    lm.save_activation(key)
    return jsonify({"activated": True, "message": "Activated."})


def require_license():
    status = lm.current_status()
    if not status.get("activated"):
        return jsonify({"error": "License not activated.", "license_required": True}), 403
    return None


@app.before_request
def gate_api():
    if request.path.startswith("/api/") and not request.path.startswith("/api/license"):
        blocked = require_license()
        if blocked:
            return blocked


# ---------------------------------------------------------------- pages ---

@app.route("/")
def index():
    return render_template("index.html")


# ------------------------------------------------------------ std types ---

@app.route("/api/std_types/line")
def std_types_line():
    return jsonify(store.line_std_types())


@app.route("/api/std_types/trafo")
def std_types_trafo():
    return jsonify(store.trafo_std_types())


# -------------------------------------------------------------- network ---

@app.route("/api/network")
def get_network():
    return jsonify(store.to_dict())


@app.route("/api/network/reset", methods=["POST"])
def reset_network():
    store.reset()
    return jsonify(store.to_dict())


@app.route("/api/bus", methods=["POST"])
def create_bus():
    d = request.json
    idx = store.add_bus(d.get("name"), d["vn_kv"], d["x"], d["y"])
    return jsonify({"id": idx, **store.to_dict()})


@app.route("/api/bus/<int:idx>/move", methods=["POST"])
def move_bus(idx):
    d = request.json
    store.move_bus(idx, d["x"], d["y"])
    return jsonify(store.to_dict())


@app.route("/api/ext_grid", methods=["POST"])
def create_ext_grid():
    d = request.json
    idx = store.add_ext_grid(d["bus"], d["s_sc_max_mva"], d["rx_max"],
                              d["s_sc_min_mva"], d["rx_min"], d.get("vm_pu", 1.0),
                              d.get("r0x0_max", 0.1), d.get("x0x_max", 1.0))
    return jsonify({"id": idx, **store.to_dict()})


@app.route("/api/line", methods=["POST"])
def create_line():
    d = request.json
    idx = store.add_line(d["from_bus"], d["to_bus"], d["std_type"], d["length_km"])
    return jsonify({"id": idx, **store.to_dict()})


@app.route("/api/trafo", methods=["POST"])
def create_trafo():
    d = request.json
    idx = store.add_trafo(d["hv_bus"], d["lv_bus"], d["std_type"])
    return jsonify({"id": idx, **store.to_dict()})


@app.route("/api/loads", methods=["POST"])
def create_load():
    d = request.json
    idx = store.add_load(d["bus"], d["p_mw"], d["q_mvar"])
    return jsonify({"id": idx, **store.to_dict()})


@app.route("/api/motor", methods=["POST"])
def create_motor():
    d = request.json
    idx = store.add_sgen_motor(d["bus"], d["p_mw"], d["lrc_pu"], d["rx"])
    return jsonify({"id": idx, **store.to_dict()})


@app.route("/api/element/<etype>/<int:idx>", methods=["DELETE"])
def delete_element(etype, idx):
    try:
        store.delete_element(etype, idx)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(store.to_dict())


# ---------------------------------------------------------- short circuit --

@app.route("/api/shortcircuit", methods=["POST"])
def shortcircuit():
    d = request.json or {}
    case = d.get("case", "max")
    fault = d.get("fault", "3ph")
    try:
        result = store.run_short_circuit(case=case, fault=fault)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(result)


# -------------------------------------------------------------- save/load --

@app.route("/api/save", methods=["GET"])
def save_network():
    data = store.to_json()
    buf = io.BytesIO(data.encode("utf-8"))
    buf.seek(0)
    return send_file(buf, mimetype="application/json", as_attachment=True,
                      download_name="network.pandasc.json")


@app.route("/api/load", methods=["POST"])
def load_network():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file uploaded."}), 400
    try:
        store.from_json(f.read().decode("utf-8"))
    except Exception as e:
        return jsonify({"error": f"Could not read that file: {e}"}), 400
    return jsonify(store.to_dict())


# ------------------------------------------------------------------ main --

def _open_browser(port):
    webbrowser.open(f"http://127.0.0.1:{port}")


def main():
    port = int(os.environ.get("PANDASC_PORT", 5731))
    if os.environ.get("PANDASC_NO_BROWSER") != "1":
        threading.Timer(1.0, _open_browser, args=(port,)).start()
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
