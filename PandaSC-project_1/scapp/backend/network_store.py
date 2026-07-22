"""
Wraps a single in-memory pandapower network and exposes plain-dict
operations the Flask layer can turn straight into JSON. This is a
single-user desktop tool, so one global network per running app is fine.
"""
import pandapower as pp
import pandapower.shortcircuit as sc
import pandapower.toolbox as pp_toolbox
import numpy as np

from cable_library import CABLE_LIBRARY, cable_choices

DEFAULT_ENDTEMP_DEGREE = 250.0  # IEC 60909 min-case assumption for cable end temperature


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

    def add_line(self, from_bus, to_bus, cable_key, length_km):
        cable = CABLE_LIBRARY.get(cable_key)
        if cable is None:
            raise ValueError(f"Unknown cable type '{cable_key}'.")
        idx = pp.create_line_from_parameters(
            self.net, from_bus=int(from_bus), to_bus=int(to_bus), length_km=float(length_km),
            r_ohm_per_km=cable["r_ohm_per_km"], x_ohm_per_km=cable["x_ohm_per_km"],
            c_nf_per_km=cable["c_nf_per_km"], max_i_ka=cable["max_i_ka"],
            name=cable["label"], endtemp_degree=DEFAULT_ENDTEMP_DEGREE,
        )
        self.net.line.loc[idx, "std_type"] = cable_key
        return int(idx)

    def update_line(self, idx, cable_key, length_km):
        cable = CABLE_LIBRARY.get(cable_key)
        if cable is None:
            raise ValueError(f"Unknown cable type '{cable_key}'.")
        self.net.line.loc[idx, ["r_ohm_per_km", "x_ohm_per_km", "c_nf_per_km", "max_i_ka",
                                 "name", "std_type", "length_km", "endtemp_degree"]] = [
            cable["r_ohm_per_km"], cable["x_ohm_per_km"], cable["c_nf_per_km"], cable["max_i_ka"],
            cable["label"], cable_key, float(length_km), DEFAULT_ENDTEMP_DEGREE,
        ]

    def add_trafo(self, hv_bus, lv_bus, std_type):
        idx = pp.create_transformer(self.net, hv_bus=int(hv_bus), lv_bus=int(lv_bus),
                                     std_type=std_type)
        return int(idx)

    def update_trafo(self, idx, std_type):
        pp.change_std_type(self.net, int(idx), std_type, element="trafo")

    def add_load(self, bus, p_mw, q_mvar):
        idx = pp.create_load(self.net, bus=int(bus), p_mw=float(p_mw), q_mvar=float(q_mvar))
        return int(idx)

    def add_sgen_motor(self, bus, p_mw, k, rx):
        """Represents an induction motor contribution as a pandapower motor
        element (for short-circuit in-feed). k = ratio Ilr/In, rx = R/X ratio."""
        idx = pp.create_motor(self.net, bus=int(bus), pn_mech_mw=float(p_mw),
                               cos_phi=0.9, efficiency_percent=95, lrc_pu=float(k),
                               rx=float(rx))
        return int(idx)

    def add_generator(self, bus, p_mw, sn_mva, vn_kv, xdss_pu, rdss_ohm, cos_phi, pg_percent=0.0):
        """A synchronous generator, contributing fault current per IEC 60909."""
        idx = pp.create_gen(
            self.net, bus=int(bus), p_mw=float(p_mw), sn_mva=float(sn_mva),
            vn_kv=float(vn_kv), xdss_pu=float(xdss_pu), rdss_ohm=float(rdss_ohm),
            cos_phi=float(cos_phi), pg_percent=float(pg_percent),
        )
        return int(idx)

    # ---------- element editing (in place) ----------

    def update_bus(self, idx, name, vn_kv):
        self.net.bus.loc[idx, ["name", "vn_kv"]] = [name, float(vn_kv)]

    def update_ext_grid(self, idx, s_sc_max_mva, rx_max, s_sc_min_mva, rx_min):
        self.net.ext_grid.loc[idx, ["s_sc_max_mva", "rx_max", "s_sc_min_mva", "rx_min"]] = [
            float(s_sc_max_mva), float(rx_max), float(s_sc_min_mva), float(rx_min)
        ]

    def update_load(self, idx, p_mw, q_mvar):
        self.net.load.loc[idx, ["p_mw", "q_mvar"]] = [float(p_mw), float(q_mvar)]

    def update_motor(self, idx, p_mw, k, rx):
        self.net.motor.loc[idx, ["pn_mech_mw", "lrc_pu", "rx"]] = [float(p_mw), float(k), float(rx)]

    def update_generator(self, idx, p_mw, sn_mva, xdss_pu, rdss_ohm, cos_phi):
        self.net.gen.loc[idx, ["p_mw", "sn_mva", "xdss_pu", "rdss_ohm", "cos_phi"]] = [
            float(p_mw), float(sn_mva), float(xdss_pu), float(rdss_ohm), float(cos_phi)
        ]

    # ---------- element deletion ----------

    def delete_element(self, etype, idx):
        idx = int(idx)
        table_map = {
            "bus": "bus", "line": "line", "trafo": "trafo", "ext_grid": "ext_grid",
            "load": "load", "motor": "motor", "gen": "gen",
        }
        table = table_map.get(etype)
        if table is None:
            raise ValueError(f"unknown element type {etype}")
        if etype == "bus":
            pp_toolbox.drop_buses(self.net, [idx])
        else:
            self.net[table].drop(index=idx, inplace=True)

    # ---------- std types / cable choices ----------

    def line_cable_choices(self):
        return cable_choices()

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
            cable_key = row.get("std_type")
            cable = CABLE_LIBRARY.get(cable_key)
            lines.append({"id": int(i), "from_bus": int(row.from_bus), "to_bus": int(row.to_bus),
                           "cable_key": cable_key,
                           "cable_label": cable["label"] if cable else (cable_key or "Custom"),
                           "length_km": float(row.length_km), "name": row["name"]})

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
                               "rx_min": float(row.rx_min)})

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

        generators = []
        if len(net.gen) > 0:
            for i, row in net.gen.iterrows():
                generators.append({"id": int(i), "bus": int(row.bus), "p_mw": float(row.p_mw),
                                    "sn_mva": float(row.sn_mva), "xdss_pu": float(row.xdss_pu),
                                    "rdss_ohm": float(row.rdss_ohm), "cos_phi": float(row.cos_phi)})

        return {"buses": buses, "lines": lines, "trafos": trafos, "ext_grids": ext_grids,
                "loads": loads, "motors": motors, "generators": generators}

    # ---------- short circuit ----------

    def run_short_circuit(self, case="max", fault="3ph"):
        if len(self.net.ext_grid) == 0 and len(self.net.gen) == 0:
            raise ValueError("Add at least one external grid or generator before running a fault study.")
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
        notes = []
        if len(self.net.gen) > 0:
            notes.append("With a generator in the network, Ip (peak) and Ith (thermal) values for "
                          "buses electrically close to that generator are approximate -- IEC 60909's "
                          "full near-generator correction isn't applied here. Ik\" (initial symmetrical) "
                          "is accurate regardless.")
        self.last_sc_results = {"case": case, "fault": fault, "results": results, "notes": notes}
        return self.last_sc_results

    # ---------- save / load ----------

    def to_json(self):
        return pp.to_json(self.net)

    def from_json(self, json_str):
        self.net = pp.from_json_string(json_str)
        self.last_sc_results = None
