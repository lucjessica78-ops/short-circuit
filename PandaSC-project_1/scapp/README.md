# PandaSC — short-circuit analysis studio

A standalone, licensable desktop tool for building a single-line network diagram
(buses, external grids, lines, transformers, loads, motors) and running IEC 60909
short-circuit fault studies on it with [pandapower](http://www.pandapower.org/).

Built as a local Flask app with an SVG network editor front end, so it packages
into a single executable with PyInstaller and needs no internet connection to run.

## What's in here

```
scapp/
  backend/
    app.py              Flask routes / REST API
    network_store.py    Wraps the pandapower network (add/remove elements, run SC)
    license_manager.py  Offline license key validation (used by app.py)
    templates/index.html
    static/css/style.css
    static/js/app.js    The network editor UI
  seller_tools/
    keygen.py           YOU run this to generate keys for customers -- never ship it
  requirements.txt
  build.spec            PyInstaller spec
  build_exe.bat          Windows build script
  build_exe.sh           macOS/Linux build script
```

## Running it from source (for development)

```bash
python3 -m pip install -r requirements.txt
python3 backend/app.py
```

This opens `http://127.0.0.1:5731` in your browser. On first run it'll ask for a
license key -- generate one for yourself with:

```bash
python3 seller_tools/keygen.py
```

## Building the standalone executable

**Important: PyInstaller does not cross-compile.** Build on the OS you're
targeting -- run `build_exe.bat` on Windows to get `PandaSC.exe`, or
`build_exe.sh` on macOS/Linux for a native binary there. I built and tested the
Linux build in this environment (short-circuit calc, license gate, and file
save/load all confirmed working in the packaged binary); the Windows build
uses the identical spec, so you just need to run the one script there once.

```
# On Windows:
build_exe.bat

# On macOS / Linux:
./build_exe.sh
```

The result is a single file in `dist/` — that's the whole app. Hand that file
to a customer along with a license key from `keygen.py` and they're done; they
don't need Python, pandapower, or anything else installed.

## Selling it: license keys

- Keys are generated entirely offline by `seller_tools/keygen.py`, which shares
  a secret with `backend/license_manager.py`. **Change the `SECRET` constant
  in `license_manager.py` to your own random value before you ship this** --
  the placeholder in this repo is not secret.
- Keep `seller_tools/` off customer machines and out of any public repo.
- A key can be perpetual or set to expire (`--days N`).
- Validation is fully offline (no server, no internet, no phone-home) — that's
  what makes the app truly standalone. The honest trade-off: someone who
  extracts `SECRET` from the compiled binary could mint their own keys. That's
  the standard level of protection for a small offline desktop tool — it stops
  casual copying and key-sharing, not a determined reverse engineer. If you
  later want stronger protection, the natural upgrade is to check keys against
  a small web endpoint you control instead of validating locally.
- Each activation is loosely tied to the machine it was activated on (a hashed
  MAC-address fingerprint), mainly to flag casual sharing -- it's not a hard
  seat limit, since there's no server tracking activations across machines.

## What it can do today

- Draw a network: buses, external grid in-feed, lines (pandapower's standard
  cable library), transformers (standard library), loads, and motors (their
  locked-rotor contribution counts toward fault current).
- Run three-phase short-circuit studies per IEC 60909, both **maximum**
  (equipment/switchgear rating) and **minimum** (protection relay sizing)
  cases, reporting Ik" (initial symmetrical), Ip (peak), and Ith
  (thermal-equivalent) at every bus.
- Save/load a network to a `.json` file so a study can be revisited.

## Known limitation / roadmap

Single line-to-ground (1ph) fault studies aren't enabled yet. Pandapower needs
zero-sequence (R0/X0) impedance data per line and transformer for that
calculation, and the bundled standard cable library doesn't ship those values
for most cable types. Rather than show numbers that look precise but aren't,
1ph is left out of this version. If you need it, the next step is adding
zero-sequence fields to the line/transformer forms (`static/js/app.js`) and
passing them through to pandapower's line/transformer creation calls in
`network_store.py`.

Other things worth knowing if you keep developing this:
- The whole network lives in one global in-memory pandapower object
  (`network_store.py`), which is fine for a single-user desktop tool but would
  need per-session state if this ever became multi-user/server-hosted.
- The Flask dev server is used directly (fine for a local single-user app);
  if you ever expose this beyond localhost, put a production WSGI server in
  front of it.
