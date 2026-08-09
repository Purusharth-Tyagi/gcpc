/* Demo console frontend.
 * Consumes websocket messages only. Knows nothing about how turns are produced,
 * so swapping the server's mock generator for the real pipeline changes nothing here.
 *
 * Messages in : {type:"state"}  {type:"history"}  {type:"turn"}
 * Messages out: {type:"toggle", lexicon_enabled}
 */

const MAX_ROWS = 12;

const els = {
  toggleBtn: document.getElementById('toggle-btn'),
  toggleLabel: document.getElementById('toggle-label'),
  toggleCaption: document.getElementById('toggle-caption'),
  connStatus: document.getElementById('conn-status'),
  p50Value: document.getElementById('p50-value'),
  turnCount: document.getElementById('turn-count'),
  latencyBody: document.getElementById('latency-body'),
  resolutionList: document.getElementById('resolution-list')
};

let lexiconEnabled = true;
let turnsSeen = 0;
let ws = null;

// --- toggle ---------------------------------------------------------------

function paintToggle(on) {
  lexiconEnabled = on;
  document.body.classList.toggle('lexicon-off', !on);
  els.toggleBtn.setAttribute('aria-checked', String(on));
  els.toggleLabel.textContent = on ? 'LEXICON: ON' : 'LEXICON: OFF';
  els.toggleCaption.textContent = on
    ? 'vector resolution active — fuzzy speech canonicalized'
    : 'NO VECTOR LOOKUP — raw ASR passed straight through';
}

els.toggleBtn.addEventListener('click', () => {
  // optimistic flip; the server broadcast is authoritative and repaints anyway
  const next = !lexiconEnabled;
  paintToggle(next);
  send({ type: 'toggle', lexicon_enabled: next });
});

function send(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}

// --- latency panel --------------------------------------------------------

function addLatencyRow(turn) {
  const tr = document.createElement('tr');
  if (!turn.lexicon_enabled) tr.classList.add('row-off');
  const s = turn.stages;
  const cells = [
    turn.turn_id,
    s.asr_ms,
    s.route_ms,
    s.resolve_ms,
    s.llm_ms,
    s.tts_ms,
    turn.total_ms
  ];
  cells.forEach((v, i) => {
    const td = document.createElement('td');
    td.textContent = v;
    if (i === 3 && s.resolve_ms === 0) td.classList.add('zero');
    if (i === 6) td.classList.add('total');
    tr.appendChild(td);
  });

  els.latencyBody.prepend(tr); // newest on top
  while (els.latencyBody.children.length > MAX_ROWS) {
    els.latencyBody.removeChild(els.latencyBody.lastChild);
  }

  els.p50Value.textContent = turn.p50_ms + ' ms';
  turnsSeen = turn.turn_id;
  els.turnCount.textContent = turnsSeen + ' turns';
}

// --- resolution panel -----------------------------------------------------

function addResolutionRow(turn) {
  const r = turn.resolution;
  const row = document.createElement('div');
  row.className = 'res-row ' + (r.ok ? 'ok' : 'fail');

  const mark = document.createElement('span');
  mark.className = 'mark';
  mark.textContent = r.ok ? '✓' : '✗';

  const heard = document.createElement('span');
  heard.className = 'heard';
  heard.textContent = '"' + r.heard + '"';

  const arrow = document.createElement('span');
  arrow.className = 'arrow';
  arrow.textContent = '→';

  const resolved = document.createElement('span');
  resolved.className = 'resolved';
  resolved.textContent = r.resolved === null ? 'UNRESOLVED' : r.resolved;

  const score = document.createElement('span');
  score.className = 'score';
  score.textContent = r.similarity.toFixed(2);

  row.append(mark, heard, arrow, resolved, score);

  els.resolutionList.prepend(row); // newest on top
  while (els.resolutionList.children.length > 40) {
    els.resolutionList.removeChild(els.resolutionList.lastChild);
  }
}

function handleTurn(turn) {
  addLatencyRow(turn);
  addResolutionRow(turn);
}

// --- websocket ------------------------------------------------------------

function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(proto + '//' + location.host);

  ws.onopen = () => {
    els.connStatus.textContent = 'connected';
    els.connStatus.className = 'conn up';
  };

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === 'state') {
      paintToggle(msg.lexicon_enabled);
    } else if (msg.type === 'history') {
      msg.turns.forEach(handleTurn); // oldest first -> prepend leaves newest on top
    } else if (msg.type === 'turn') {
      handleTurn(msg);
    }
  };

  ws.onclose = () => {
    els.connStatus.textContent = 'disconnected — retrying';
    els.connStatus.className = 'conn down';
    setTimeout(connect, 1000);
  };

  ws.onerror = () => ws.close();
}

connect();
