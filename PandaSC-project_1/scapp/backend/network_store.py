"""
Wraps a single in-memory pandapower network and exposes plain-dict
operations the Flask layer can turn straight into JSON. This is a
single-user desktop tool, so one global network per running app is fine.
"""
import pandapower as pp
import pandapower.shortcircuit as sc
import pandapower.toolbox as pp_toolbox
import numpy as np


class NetworkStore:
    def __init__(self):
        self.reset()

    def reset(self):
        self.net = pp.create_empty_network(sn_mva=100)
        self.last_sc_results = None

    # ---------- element creation ----------

    def add_bus(self, name, vn_kv, x, y):
        idx = pp.create_bus(self.net, vn_kv=float(vn_kv), name=name or f"Bus {len(self.net.bus)}",
                             geodata=(float(x), float(y)))
        return int(idx)

    def move_bus(self, idx, x, y):
        import json
        self.net.bus.loc[idx, "geo"] = json.dumps({"coordinates": [float(x), float(y)], "type": "Point"})

    def add_ext_grid(self, bus, s_sc_max_mva, rx_max, s_sc_min_mva, rx_min, vm_pu=1.0,
                      r0x0_max=0.1, x0x_max=1.0):
        idx = pp.create_ext_grid(
            self.net, bus=int(bus), vm_pu=float(vm_pu),
            s_sc_max_mva=float(s_sc_max_mva), rx_max=float(rx_max),
            s_sc_min_mva=float(s_sc_min_mva), rx_min=float(rx_min),
            r0x0_max=float(r0x0_max), x0x_max=float(x0x_max),
        )
        return int(idx)

    def add_line(self, from_bus, to_bus, std_type, length_km):
        idx = pp.create_line(self.net, from_bus=int(from_bus), to_bus=int(to_bus),
                              length_km=float(length_km), std_type=std_type)
        # Required by IEC 60909 min-case (thermal) short-circuit calcs. 250C is the
        # standard assumption for XLPE cables; adjust per element later if needed.
        self.net.line.loc[idx, "endtemp_degree"] = 250.0
        return int(idx)

    def add_trafo(self, hv_bus, lv_bus, std_type):
        idx = pp.create_transformer(self.net, hv_bus=int(hv_bus), lv_bus=int(lv_bus),
                                     std_type=std_type)
        return int(idx)

    def add_load(self, bus, p_mw, q_mvar):
        idx = pp.create_load(self.net, bus=int(bus), p_mw=float(p_mw), q_mvar=float(q_mvar))
        return int(idx)

    def add_sgen_motor(self, bus, p_mw, k, rx):
        """Represents a synchronous/induction motor contribution as a pandapower motor
        element (for short-circuit in-feed). k = ratio Ilr/In, rx = R/X ratio."""
        idx = pp.create_motor(self.net, bus=int(bus), pn_mech_mw=float(p_mw),
                               cos_phi=0.9, efficiency_percent=95, lrc_pu=float(k),
                               rx=float(rx))
        return int(idx)

    # ---------- element deletion ----------

    def delete_element(self, etype, idx):
        idx = int(idx)
        table_map = {
            "bus": "bus", "line": "line", "trafo": "trafo",
            "ext_grid": "ext_grid", "load": "load", "motor": "motor",
        }
        table = table_map.get(etype)
        if table is None:
            raise ValueError(f"unknown element type {etype}")
        if etype == "bus":
            pp_toolbox.drop_buses(self.net, [idx])
        else:
            self.net[table].drop(index=idx, inplace=True)

    # ---------- std types ----------

    def line_std_types(self):
        return sorted(pp.available_std_types(self.net, "line").index.tolist())

    def trafo_std_types(self):
        return sorted(pp.available_std_types(self.net, "trafo").index.tolist())

    # ---------- serialization for the frontend ----------

    def to_dict(self):
        net = self.net

        def bus_pos(i):
            import json
            geo = net.bus.at[i, "geo"] if "geo" in net.bus.columns else None
            if isinstance(geo, str) and geo:
                try:
                    coords = json.loads(geo)["coordinates"]
                    return float(coords[0]), float(coords[1])
                except Exception:
                    return 0.0, 0.0
            return 0.0, 0.0

        buses = []
        for i, row in net.bus.iterrows():
            x, y = bus_pos(i)
            buses.append({"id": int(i), "name": row["name"], "vn_kv": float(row.vn_kv),
                           "x": x, "y": y})

        lines = []
        for i, row in net.line.iterrows():
            lines.append({"id": int(i), "from_bus": int(row.from_bus), "to_bus": int(row.to_bus),
                           "std_type": row.std_type, "length_km": float(row.length_km),
                           "name": row["name"]})

        trafos = []
        for i, row in net.trafo.iterrows():
            trafos.append({"id": int(i), "hv_bus": int(row.hv_bus), "lv_bus": int(row.lv_bus),
                            "std_type": row.std_type, "name": row["name"]})

        ext_grids = []
        for i, row in net.ext_grid.iterrows():
            ext_grids.append({"id": int(i), "bus": int(row.bus),
                               "s_sc_max_mva": float(row.s_sc_max_mva),
                               "rx_max": float(row.rx_max),
                               "s_sc_min_mva": float(row.s_sc_min_mva),
                               "rx_min": float(row.rx_min),
                               "r0x0_max": float(row.get("r0x0_max", np.nan)) if not np.isnan(row.get("r0x0_max", np.nan)) else None,
                               "x0x_max": float(row.get("x0x_max", np.nan)) if not np.isnan(row.get("x0x_max", np.nan)) else None})

        loads = []
        for i, row in net.load.iterrows():
            loads.append({"id": int(i), "bus": int(row.bus), "p_mw": float(row.p_mw),
                           "q_mvar": float(row.q_mvar)})

        motors = []
        if len(net.motor) > 0:
            for i, row in net.motor.iterrows():
                motors.append({"id": int(i), "bus": int(row.bus),
                                "p_mw": float(row.pn_mech_mw), "lrc_pu": float(row.lrc_pu),
                                "rx": float(row.rx)})

        return {"buses": buses, "lines": lines, "trafos": trafos, "ext_grids": ext_grids,
                "loads": loads, "motors": motors}

    # ---------- short circuit ----------

    def run_short_circuit(self, case="max", fault="3ph"):
        if len(self.net.ext_grid) == 0:
            raise ValueError("Add at least one external grid before running a fault study.")
        if len(self.net.bus) == 0:
            raise ValueError("Add at least one bus first.")

        sc.calc_sc(self.net, case=case, fault=fault, ip=True, ith=True, tk_s=1.0)

        results = []
        res = self.net.res_bus_sc
        for i, row in res.iterrows():
            def g(col):
                v = row[col] if col in row else np.nan
                return None if (v is None or (isinstance(v, float) and np.isnan(v))) else round(float(v), 4)

            results.append({
                "bus": int(i),
                "ikss_ka": g("ikss_ka"),
                "ip_ka": g("ip_ka"),
                "ith_ka": g("ith_ka"),
                "rk_ohm": g("rk_ohm"),
                "xk_ohm": g("xk_ohm"),
            })
        self.last_sc_results = {"case": case, "fault": fault, "results": results}
        return self.last_sc_results

    # ---------- save / load ----------

    def to_json(self):
        return pp.to_json(self.net)

    def from_json(self, json_str):
        self.net = pp.from_json_string(json_str)
        self.last_sc_results = None
