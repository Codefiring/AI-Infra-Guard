let _sidebarDrag = null;
let _scanDrag = null;

function initResizeHandlers() {
  const h = document.getElementById("resize-sidebar");
  if (!h) return;
  h.addEventListener("mousedown", e => {
    e.preventDefault();
    _sidebarDrag = { startX: e.clientX, startW: document.getElementById("sidebar").offsetWidth };
    h.classList.add("dragging");
    document.addEventListener("mousemove", _onSidebarMove);
    document.addEventListener("mouseup", _onSidebarUp);
  });
}

function _onSidebarMove(e) {
  if (!_sidebarDrag) return;
  const newW = Math.max(160, Math.min(480, _sidebarDrag.startW + (e.clientX - _sidebarDrag.startX)));
  document.getElementById("sidebar").style.width = newW + "px";
  AppState.layout.sidebarWidth = newW;
}

function _onSidebarUp() {
  _sidebarDrag = null;
  document.getElementById("resize-sidebar")?.classList.remove("dragging");
  document.removeEventListener("mousemove", _onSidebarMove);
  document.removeEventListener("mouseup", _onSidebarUp);
}

function startScanResize(e) {
  e.preventDefault();
  const left = document.getElementById("scan-left");
  if (!left) return;
  const handle = e.currentTarget;
  _scanDrag = {
    startX: e.clientX,
    startW: left.offsetWidth,
    containerW: left.parentElement.offsetWidth,
    handle,
  };
  handle.classList.add("dragging");
  document.addEventListener("mousemove", _onScanMove);
  document.addEventListener("mouseup", _onScanUp);
}

function _onScanMove(e) {
  if (!_scanDrag) return;
  const newW = Math.max(200, Math.min(_scanDrag.containerW - 200, _scanDrag.startW + (e.clientX - _scanDrag.startX)));
  const pct = Math.round((newW / _scanDrag.containerW) * 100);
  document.getElementById("scan-left").style.width = pct + "%";
  AppState.layout.scanLeftPct = pct;
}

function _onScanUp() {
  _scanDrag?.handle.classList.remove("dragging");
  _scanDrag = null;
  document.removeEventListener("mousemove", _onScanMove);
  document.removeEventListener("mouseup", _onScanUp);
}
