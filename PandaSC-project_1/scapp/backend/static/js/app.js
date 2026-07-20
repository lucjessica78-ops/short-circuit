(() => {
  const SVG_NS = "http://www.w3.org/2000/svg";

  const state = {
    tool: "select",
    network: { buses: [], lines: [], trafos: [], ext_grids: [], loads: [], motors: [] },
    selected: null,        // { type, id }
    pending: null,         // { kind: 'line'|'trafo', fromBus }
    dragBus: null,         // { id, offsetX, offsetY }
    scResults: null,       // map bus id -> row
  };

  const svg = document.getElementById("canvas");
  const statusText = document.getElementById("status-text");
  const paletteHint = document.getElementById("palette-hint");

  // ------------------------------------------------------------- utils --

  function setStatus(msg) { statusText.textContent = msg; }

  async function api(path, opts) {
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch (e) { /* no body */ }
    if (!res.ok) {
      const err = new Error((data && data.error) || res.statusText);
      err.data = data;
      throw err;
    }
    return data;
  }

  function svgEl(tag, attrs) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    return el;
  }

  function canvasPoint(evt) {
    const rect = svg.getBoundingClientRect();
    return { x: evt.clientX - rect.left, y: evt.clientY - rect.top };
  }

  function busById(id) { return state.network.buses.find(b => b.id === id); }

  // --------------------------------------------------------- rendering --

  function resizeCanvas() {
    const rect = svg.parentElement.getBoundingClientRect();
    svg.setAttribute("viewBox", `0 0 ${rect.width} ${rect.height}`);
    svg.setAttribute("width", rect.width);
    svg.setAttribute("height", rect.height);
  }

  function render() {
    svg.innerHTML = "";
    const net = state.network;

    // branches first (so buses draw on top)
    net.lines.forEach(l => renderBranch(l, "line", busById(l.from_bus), busById(l.to_bus)));
    net.trafos.forEach(t => renderBranch(t, "trafo", busById(t.hv_bus), busById(t.lv_bus)));

    // pending connection preview
    if (state.pending && state.pending.fromBus != null) {
      const b = busById(state.pending.fromBus);
      if (b) {
        const marker = svgEl("circle", { cx: b.x, cy: b.y, r: 22, class: "branch-line pending", fill: "none" });
        svg.appendChild(marker);
      }
    }

    // attachments
    net.ext_grids.forEach(g => renderExtGrid(g, busById(g.bus)));
    net.loads.forEach(ld => renderLoad(ld, busById(ld.bus)));
    net.motors.forEach(m => renderMotor(m, busById(m.bus)));

    // buses
    net.buses.forEach(b => renderBus(b));

    // fault result badges
    if (state.scResults) {
      const rows = state.scResults.results;
      const worst = rows.reduce((a, b) => (b.ikss_ka || 0) > (a.ikss_ka || 0) ? b : a, rows[0] || {});
      rows.forEach(r => {
        const b = busById(r.bus);
        if (!b || r.ikss_ka == null) return;
        renderFaultBadge(b, r, worst && r.bus === worst.bus);
      });
    }
  }

  function renderBus(b) {
    const g = svgEl("g", { "data-kind": "bus", "data-id": b.id });
    const selected = state.selected && state.selected.type === "bus" && state.selected.id === b.id;
    const rect = svgEl("rect", {
      x: b.x - 16, y: b.y - 9, width: 32, height: 18, rx: 2,
      class: "bus-rect" + (selected ? " selected" : "")
    });
    g.appendChild(rect);
    const label = svgEl("text", { x: b.x, y: b.y - 15, "text-anchor": "middle", class: "bus-label" });
    label.textContent = b.name || `Bus ${b.id}`;
    g.appendChild(label);
    const sub = svgEl("text", { x: b.x, y: b.y + 26, "text-anchor": "middle", class: "bus-sub" });
    sub.textContent = `${b.vn_kv} kV`;
    g.appendChild(sub);

    g.addEventListener("mousedown", (evt) => onBusMouseDown(evt, b));
    g.addEventListener("click", (evt) => { evt.stopPropagation(); onBusClick(b); });
    svg.appendChild(g);
  }

  function renderBranch(el, kind, fromB, toB) {
    if (!fromB || !toB) return;
    const selected = state.selected && state.selected.type === kind && state.selected.id === el.id;
    const line = svgEl("line", {
      x1: fromB.x, y1: fromB.y, x2: toB.x, y2: toB.y,
      class: "branch-line" + (kind === "trafo" ? " trafo" : "") + (selected ? " selected" : ""),
      "stroke-width": selected ? 3 : 2,
    });
    line.addEventListener("click", (evt) => { evt.stopPropagation(); onElementClick(kind, el.id); });
    svg.appendChild(line);

    const mx = (fromB.x + toB.x) / 2, my = (fromB.y + toB.y) / 2;
    const label = svgEl("text", { x: mx, y: my - 6, "text-anchor": "middle", class: "bus-sub" });
    label.textContent = kind === "trafo" ? (el.std_type || "Trafo") : `${el.length_km} km`;
    svg.appendChild(label);
  }

  function renderExtGrid(g, bus) {
    if (!bus) return;
    const x = bus.x, y = bus.y - 46;
    const grp = svgEl("g", {});
    grp.appendChild(svgEl("line", { x1: x, y1: y + 10, x2: bus.x, y2: bus.y - 9, class: "ext-grid-glyph" }));
    grp.appendChild(svgEl("path", { d: `M ${x - 10} ${y} L ${x + 10} ${y} L ${x} ${y - 14} Z`, class: "ext-grid-glyph" }));
    const label = svgEl("text", { x: x + 16, y: y - 2, class: "bus-sub" });
    label.textContent = "GRID";
    grp.appendChild(label);
    grp.addEventListener("click", (evt) => { evt.stopPropagation(); onElementClick("ext_grid", g.id); });
    svg.appendChild(grp);
  }

  function renderLoad(ld, bus) {
    if (!bus) return;
    const x = bus.x - 34, y = bus.y + 34;
    const grp = svgEl("g", {});
    grp.appendChild(svgEl("line", { x1: bus.x, y1: bus.y + 9, x2: x, y2: y - 8, class: "load-glyph" }));
    grp.appendChild(svgEl("path", { d: `M ${x - 8} ${y - 6} L ${x + 8} ${y - 6} L ${x} ${y + 8} Z`, class: "load-glyph" }));
    const label = svgEl("text", { x, y: y + 20, "text-anchor": "middle", class: "bus-sub" });
    label.textContent = `${ld.p_mw} MW`;
    grp.appendChild(label);
    grp.addEventListener("click", (evt) => { evt.stopPropagation(); onElementClick("load", ld.id); });
    svg.appendChild(grp);
  }

  function renderMotor(m, bus) {
    if (!bus) return;
    const x = bus.x + 34, y = bus.y + 34;
    const grp = svgEl("g", {});
    grp.appendChild(svgEl("line", { x1: bus.x, y1: bus.y + 9, x2: x, y2: y - 12, class: "motor-glyph" }));
    grp.appendChild(svgEl("circle", { cx: x, cy: y, r: 12, class: "motor-glyph" }));
    const label = svgEl("text", { x, y: y + 4, "text-anchor": "middle", class: "bus-sub" });
    label.textContent = "M";
    label.setAttribute("fill", "var(--cyan)");
    grp.appendChild(label);
    grp.addEventListener("click", (evt) => { evt.stopPropagation(); onElementClick("motor", m.id); });
    svg.appendChild(grp);
  }

  function renderFaultBadge(bus, row, isWorst) {
    const x = bus.x + 20, y = bus.y - 32;
    const grp = svgEl("g", { class: "fault-badge" });
    grp.appendChild(svgEl("rect", { x: x - 4, y: y - 12, width: 78, height: 16, rx: 2 }));
    const label = svgEl("text", { x: x, y: y, class: isWorst ? "worst" : "" });
    label.textContent = `${row.ikss_ka.toFixed(2)} kA`;
    grp.appendChild(label);
    svg.appendChild(grp);
  }

  // ------------------------------------------------------------- tools --

  document.querySelectorAll(".tool").forEach(btn => {
    btn.addEventListener("click", () => selectTool(btn.dataset.tool));
  });

  const TOOL_HINTS = {
    select: "Drag buses to move them. Click an element to see its properties.",
    bus: "Click anywhere on the canvas to place a bus.",
    ext_grid: "Click a bus to attach an external grid (fault in-feed) there.",
    line: "Click a bus to start a line, then click another bus to finish it.",
    trafo: "Click the HV-side bus, then the LV-side bus, to place a transformer.",
    load: "Click a bus to attach a load.",
    motor: "Click a bus to attach a motor (contributes fault current).",
    delete: "Click any bus, line, transformer, or attachment to delete it.",
  };

  function selectTool(tool) {
    state.tool = tool;
    state.pending = null;
    document.querySelectorAll(".tool").forEach(b => b.classList.toggle("active", b.dataset.tool === tool));
    paletteHint.textContent = TOOL_HINTS[tool] || "";
    clearSelection();
    render();
  }

  // ------------------------------------------------------ canvas events --

  svg.addEventListener("click", (evt) => {
    if (state.dragBus) return; // drag just ended, ignore synthetic click
    const pt = canvasPoint(evt);
    if (state.tool === "bus") {
      openCreateBusForm(pt.x, pt.y);
    } else if (state.tool === "select") {
      clearSelection();
    }
  });

  function onBusMouseDown(evt, bus) {
    if (state.tool !== "select") return;
    evt.stopPropagation();
    const pt = canvasPoint(evt);
    state.dragBus = { id: bus.id, offsetX: pt.x - bus.x, offsetY: pt.y - bus.y, moved: false };
    const onMove = (mv) => {
      const p = canvasPoint(mv);
      bus.x = p.x - state.dragBus.offsetX;
      bus.y = p.y - state.dragBus.offsetY;
      state.dragBus.moved = true;
      render();
    };
    const onUp = async () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      const moved = state.dragBus && state.dragBus.moved;
      if (moved) {
        try { await api(`/api/bus/${bus.id}/move`, { method: "POST", headers: jsonHeaders(), body: JSON.stringify({ x: bus.x, y: bus.y }) }); }
        catch (e) { setStatus("Could not save bus position: " + e.message); }
      }
      setTimeout(() => { state.dragBus = null; }, 0);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  function onBusClick(bus) {
    if (state.tool === "select") {
      selectElement("bus", bus.id);
    } else if (state.tool === "delete") {
      deleteElement("bus", bus.id);
    } else if (state.tool === "ext_grid") {
      openExtGridForm(bus);
    } else if (state.tool === "load") {
      openLoadForm(bus);
    } else if (state.tool === "motor") {
      openMotorForm(bus);
    } else if (state.tool === "line" || state.tool === "trafo") {
      handleConnectClick(bus);
    }
  }

  function handleConnectClick(bus) {
    const kind = state.tool;
    if (!state.pending || state.pending.kind !== kind) {
      state.pending = { kind, fromBus: bus.id };
      setStatus(`${kind === "line" ? "Line" : "Transformer"}: pick the second bus.`);
      render();
      return;
    }
    if (state.pending.fromBus === bus.id) return; // same bus, ignore
    if (kind === "line") {
      openLineForm(state.pending.fromBus, bus.id);
    } else {
      openTrafoForm(state.pending.fromBus, bus.id);
    }
    state.pending = null;
  }

  function onElementClick(kind, id) {
    if (state.tool === "delete") {
      deleteElement(kind, id);
    } else if (state.tool === "select") {
      selectElement(kind, id);
    }
  }

  // ------------------------------------------------------------- forms --

  const propsEmpty = document.getElementById("props-empty");
  const propsForm = document.getElementById("props-form");

  function jsonHeaders() { return { "Content-Type": "application/json" }; }

  function showForm(html) {
    propsEmpty.classList.add("hidden");
    propsForm.classList.remove("hidden");
    propsForm.innerHTML = html;
    switchTab("props");
  }

  function clearSelection() {
    state.selected = null;
    propsForm.classList.add("hidden");
    propsForm.innerHTML = "";
    propsEmpty.classList.remove("hidden");
  }

  function openCreateBusForm(x, y) {
    showForm(`
      <div class="props-title">New bus</div>
      <div class="field"><label>Name</label><input name="name" value="Bus ${state.network.buses.length}"></div>
      <div class="field"><label>Nominal voltage (kV)</label><input name="vn_kv" type="number" step="any" value="20"></div>
      <div class="props-actions">
        <button type="submit" class="btn btn-primary">Place bus</button>
        <button type="button" class="btn btn-ghost" id="cancel-form">Cancel</button>
      </div>
    `);
    propsForm.onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(propsForm);
      try {
        const data = await api("/api/bus", { method: "POST", headers: jsonHeaders(), body: JSON.stringify({
          name: fd.get("name"), vn_kv: parseFloat(fd.get("vn_kv")), x, y
        }) });
        applyNetwork(data);
        setStatus("Bus placed.");
        clearSelection();
      } catch (err) { setStatus("Error: " + err.message); }
    };
    document.getElementById("cancel-form").onclick = clearSelection;
  }

  function openExtGridForm(bus) {
    showForm(`
      <div class="props-title">External grid — ${bus.name}</div>
      <div class="field field-hint">Fault in-feed at this bus. Values typically come from the upstream utility's fault-level study.</div>
      <div class="field"><label>S"sc max (MVA)</label><input name="s_sc_max_mva" type="number" step="any" value="500"></div>
      <div class="field"><label>R/X max</label><input name="rx_max" type="number" step="any" value="0.1"></div>
      <div class="field"><label>S"sc min (MVA)</label><input name="s_sc_min_mva" type="number" step="any" value="300"></div>
      <div class="field"><label>R/X min</label><input name="rx_min" type="number" step="any" value="0.1"></div>
      <div class="props-actions">
        <button type="submit" class="btn btn-primary">Attach</button>
        <button type="button" class="btn btn-ghost" id="cancel-form">Cancel</button>
      </div>
    `);
    propsForm.onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(propsForm);
      try {
        const data = await api("/api/ext_grid", { method: "POST", headers: jsonHeaders(), body: JSON.stringify({
          bus: bus.id, s_sc_max_mva: parseFloat(fd.get("s_sc_max_mva")), rx_max: parseFloat(fd.get("rx_max")),
          s_sc_min_mva: parseFloat(fd.get("s_sc_min_mva")), rx_min: parseFloat(fd.get("rx_min")),
        }) });
        applyNetwork(data);
        setStatus("External grid attached.");
        clearSelection();
      } catch (err) { setStatus("Error: " + err.message); }
    };
    document.getElementById("cancel-form").onclick = clearSelection;
  }

  async function openLineForm(fromBus, toBus) {
    let types = [];
    try { types = await api("/api/std_types/line"); } catch (e) { setStatus("Could not load line types."); }
    const options = types.map(t => `<option value="${t}">${t}</option>`).join("");
    showForm(`
      <div class="props-title">Line — bus ${fromBus} &rarr; bus ${toBus}</div>
      <div class="field"><label>Cable / conductor type</label><select name="std_type">${options}</select></div>
      <div class="field"><label>Length (km)</label><input name="length_km" type="number" step="any" value="1.0"></div>
      <div class="props-actions">
        <button type="submit" class="btn btn-primary">Add line</button>
        <button type="button" class="btn btn-ghost" id="cancel-form">Cancel</button>
      </div>
    `);
    propsForm.onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(propsForm);
      try {
        const data = await api("/api/line", { method: "POST", headers: jsonHeaders(), body: JSON.stringify({
          from_bus: fromBus, to_bus: toBus, std_type: fd.get("std_type"), length_km: parseFloat(fd.get("length_km"))
        }) });
        applyNetwork(data);
        setStatus("Line added.");
        clearSelection();
      } catch (err) { setStatus("Error: " + err.message); }
    };
    document.getElementById("cancel-form").onclick = clearSelection;
  }

  async function openTrafoForm(hvBus, lvBus) {
    let types = [];
    try { types = await api("/api/std_types/trafo"); } catch (e) { setStatus("Could not load transformer types."); }
    const options = types.map(t => `<option value="${t}">${t}</option>`).join("");
    showForm(`
      <div class="props-title">Transformer — HV bus ${hvBus} &rarr; LV bus ${lvBus}</div>
      <div class="field"><label>Transformer type</label><select name="std_type">${options}</select></div>
      <div class="props-actions">
        <button type="submit" class="btn btn-primary">Add transformer</button>
        <button type="button" class="btn btn-ghost" id="cancel-form">Cancel</button>
      </div>
    `);
    propsForm.onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(propsForm);
      try {
        const data = await api("/api/trafo", { method: "POST", headers: jsonHeaders(), body: JSON.stringify({
          hv_bus: hvBus, lv_bus: lvBus, std_type: fd.get("std_type")
        }) });
        applyNetwork(data);
        setStatus("Transformer added.");
        clearSelection();
      } catch (err) { setStatus("Error: " + err.message); }
    };
    document.getElementById("cancel-form").onclick = clearSelection;
  }

  function openLoadForm(bus) {
    showForm(`
      <div class="props-title">Load — ${bus.name}</div>
      <div class="field"><label>Active power (MW)</label><input name="p_mw" type="number" step="any" value="1.0"></div>
      <div class="field"><label>Reactive power (Mvar)</label><input name="q_mvar" type="number" step="any" value="0.2"></div>
      <div class="props-actions">
        <button type="submit" class="btn btn-primary">Attach</button>
        <button type="button" class="btn btn-ghost" id="cancel-form">Cancel</button>
      </div>
    `);
    propsForm.onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(propsForm);
      try {
        const data = await api("/api/loads", { method: "POST", headers: jsonHeaders(), body: JSON.stringify({
          bus: bus.id, p_mw: parseFloat(fd.get("p_mw")), q_mvar: parseFloat(fd.get("q_mvar"))
        }) });
        applyNetwork(data);
        setStatus("Load attached.");
        clearSelection();
      } catch (err) { setStatus("Error: " + err.message); }
    };
    document.getElementById("cancel-form").onclick = clearSelection;
  }

  function openMotorForm(bus) {
    showForm(`
      <div class="props-title">Motor — ${bus.name}</div>
      <div class="field field-hint">Motors add fault current in-feed. LRC is the locked-rotor / starting current ratio (typ. 5&ndash;7).</div>
      <div class="field"><label>Rated power (MW)</label><input name="p_mw" type="number" step="any" value="0.5"></div>
      <div class="field"><label>Locked-rotor current ratio</label><input name="lrc_pu" type="number" step="any" value="6"></div>
      <div class="field"><label>R/X ratio</label><input name="rx" type="number" step="any" value="0.1"></div>
      <div class="props-actions">
        <button type="submit" class="btn btn-primary">Attach</button>
        <button type="button" class="btn btn-ghost" id="cancel-form">Cancel</button>
      </div>
    `);
    propsForm.onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(propsForm);
      try {
        const data = await api("/api/motor", { method: "POST", headers: jsonHeaders(), body: JSON.stringify({
          bus: bus.id, p_mw: parseFloat(fd.get("p_mw")), lrc_pu: parseFloat(fd.get("lrc_pu")), rx: parseFloat(fd.get("rx"))
        }) });
        applyNetwork(data);
        setStatus("Motor attached.");
        clearSelection();
      } catch (err) { setStatus("Error: " + err.message); }
    };
    document.getElementById("cancel-form").onclick = clearSelection;
  }

  function selectElement(type, id) {
    state.selected = { type, id };
    render();
    const el = findElement(type, id);
    if (!el) { clearSelection(); return; }
    const rows = Object.entries(el).map(([k, v]) => `
      <div class="field"><label>${k}</label><input value="${v}" disabled></div>
    `).join("");
    showForm(`
      <div class="props-title">${type} #${id}</div>
      ${rows}
      <div class="props-actions">
        <button type="button" class="btn btn-danger" id="delete-selected">Delete</button>
      </div>
    `);
    propsForm.onsubmit = (e) => e.preventDefault();
    document.getElementById("delete-selected").onclick = () => deleteElement(type, id);
  }

  function findElement(type, id) {
    const map = { bus: "buses", line: "lines", trafo: "trafos", ext_grid: "ext_grids", load: "loads", motor: "motors" };
    const arr = state.network[map[type]] || [];
    return arr.find(e => e.id === id);
  }

  async function deleteElement(type, id) {
    try {
      const data = await api(`/api/element/${type}/${id}`, { method: "DELETE" });
      applyNetwork(data);
      clearSelection();
      setStatus(`Deleted ${type} #${id}.`);
    } catch (err) { setStatus("Error: " + err.message); }
  }

  function applyNetwork(data) {
    state.network = { buses: data.buses, lines: data.lines, trafos: data.trafos,
                       ext_grids: data.ext_grids, loads: data.loads, motors: data.motors };
    render();
  }

  // -------------------------------------------------------------- tabs --

  document.querySelectorAll(".rail-tab").forEach(btn => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
  function switchTab(tab) {
    document.querySelectorAll(".rail-tab").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
    document.getElementById("panel-props").classList.toggle("hidden", tab !== "props");
    document.getElementById("panel-results").classList.toggle("hidden", tab !== "results");
  }

  // --------------------------------------------------------- short circuit

  document.getElementById("btn-run-sc").addEventListener("click", async () => {
    const caseVal = document.getElementById("sc-case").value;
    const faultVal = document.getElementById("sc-fault").value;
    const errBox = document.getElementById("sc-error");
    errBox.textContent = "";
    try {
      const data = await api("/api/shortcircuit", { method: "POST", headers: jsonHeaders(),
        body: JSON.stringify({ case: caseVal, fault: faultVal }) });
      state.scResults = data;
      renderResultsTable(data);
      render();
      setStatus(`Fault study complete (${data.case}, ${data.fault}).`);
    } catch (err) {
      errBox.textContent = err.message;
      document.getElementById("sc-results").innerHTML = "";
    }
  });

  function renderResultsTable(data) {
    const rows = data.results;
    const worstId = rows.reduce((a, b) => (b.ikss_ka || 0) > (a.ikss_ka || 0) ? b : a, rows[0] || {}).bus;
    const body = rows.map(r => `
      <tr class="${r.bus === worstId ? 'worst' : ''}">
        <td>${(busById(r.bus) || {}).name || r.bus}</td>
        <td>${r.ikss_ka != null ? r.ikss_ka.toFixed(2) : '—'}</td>
        <td>${r.ip_ka != null ? r.ip_ka.toFixed(2) : '—'}</td>
        <td>${r.ith_ka != null ? r.ith_ka.toFixed(2) : '—'}</td>
      </tr>
    `).join("");
    document.getElementById("sc-results").innerHTML = `
      <table class="sc-table">
        <thead><tr><th>Bus</th><th>Ik" (kA)</th><th>Ip (kA)</th><th>Ith (kA)</th></tr></thead>
        <tbody>${body}</tbody>
      </table>
      <div class="results-note">Ik" is the initial symmetrical short-circuit current, Ip the peak, Ith the thermal-equivalent current (IEC 60909 conventions). The highlighted row is the highest fault level in this study.</div>
    `;
  }

  // ------------------------------------------------------------ toolbar --

  document.getElementById("btn-new").addEventListener("click", async () => {
    if (!confirm("Start a new network? Unsaved changes will be lost.")) return;
    const data = await api("/api/network/reset", { method: "POST" });
    state.scResults = null;
    applyNetwork(data);
    clearSelection();
    switchTab("props");
    setStatus("New network.");
  });

  document.getElementById("btn-save").addEventListener("click", () => {
    window.location.href = "/api/save";
  });

  document.getElementById("btn-open").addEventListener("click", () => {
    document.getElementById("file-input").click();
  });
  document.getElementById("file-input").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      const data = await api("/api/load", { method: "POST", body: fd });
      state.scResults = null;
      applyNetwork(data);
      setStatus(`Loaded ${file.name}.`);
    } catch (err) { setStatus("Error loading file: " + err.message); }
    e.target.value = "";
  });

  // ------------------------------------------------------------- license --

  const gate = document.getElementById("license-gate");
  const appEl = document.getElementById("app");

  async function checkLicense() {
    const status = await api("/api/license/status");
    if (status.activated) {
      gate.classList.add("hidden");
      appEl.classList.remove("hidden");
      init();
    } else {
      gate.classList.remove("hidden");
      appEl.classList.add("hidden");
    }
  }

  document.getElementById("license-submit").addEventListener("click", async () => {
    const key = document.getElementById("license-input").value;
    const errBox = document.getElementById("license-error");
    errBox.textContent = "";
    try {
      await api("/api/license/activate", { method: "POST", headers: jsonHeaders(), body: JSON.stringify({ key }) });
      checkLicense();
    } catch (err) {
      errBox.textContent = (err.data && err.data.message) || err.message;
    }
  });

  // --------------------------------------------------------------- init --

  async function init() {
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);
    selectTool("select");
    try {
      const data = await api("/api/network");
      applyNetwork(data);
    } catch (err) { setStatus("Error loading network: " + err.message); }
  }

  checkLicense();
})();
