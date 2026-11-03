// Constellation graph: d3-force layout drawn on a canvas. All item text goes through textContent, never innerHTML.
const $ = (id) => document.getElementById(id);
const canvas = $("graph");
const ctx = canvas.getContext("2d");
const FADE = 0.1; // alpha of nodes outside the hovered neighbourhood
const css = getComputedStyle(document.documentElement);
const token = (name) => css.getPropertyValue(name).trim();
const kindColor = (kind) => token(`--k-${kind}`) || token("--k-other");

let nodes = [], links = [], byId = new Map(), neighbours = new Map(), clusterOf = new Map();
let transform = d3.zoomIdentity, hover = null, selected = null, width = 0, height = 0, sim;

fetch("/api/constellation")
  .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
  .then(start)
  .catch((e) => say(`Could not load the constellation: ${e.message}`));

function say(text) {
  $("msg").textContent = text;
  $("msg").hidden = false;
}

function start(data) {
  const clusters = data.clusters || [];
  clusters.forEach((c) => c.item_ids.forEach((id) => clusterOf.set(id, c.name)));

  nodes = data.items.map((it) => ({ ...it, label: (data.labels || {})[it.id] || "", cluster: clusterOf.get(it.id), degree: 0 }));
  nodes.forEach((n) => { byId.set(n.id, n); neighbours.set(n.id, new Set()); });
  links = (data.relations || [])
    .filter((r) => byId.has(r.source) && byId.has(r.target))
    .map((r) => ({ source: r.source, target: r.target, kind: r.kind, a: 1 }));
  links.forEach((l) => {
    neighbours.get(l.source).add(l.target);
    neighbours.get(l.target).add(l.source);
  });
  nodes.forEach((n) => { n.degree = neighbours.get(n.id).size; n.r = 4 + Math.min(9, Math.sqrt(n.degree) * 2.2); n.a = 1; });
  nodes.forEach((n) => (n.color = kindColor(n.kind)));
  // 27 clusters is far past what colour can encode (dataviz: <= 8), so colour = kind and clusters shape the layout.
  const counts = d3.rollups(nodes, (v) => v.length, (n) => n.kind).sort((a, b) => b[1] - a[1]);
  $("legend").replaceChildren(...counts.map(([kind, k]) => {
    const el = document.createElement("span"), dot = document.createElement("i");
    dot.style.color = kindColor(kind);
    el.append(dot, `${kind.replace("_", " ")} ${k}`);
    return el;
  }));
  $("stats").textContent = `${nodes.length} items · ${links.length} relations · ${clusters.length} clusters`;

  sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id((n) => n.id).distance(46).strength(0.5))
    .force("charge", d3.forceManyBody().strength(-70).distanceMax(400))
    .force("collide", d3.forceCollide((n) => n.r + 2))
    .force("x", d3.forceX().strength(0.07))
    .force("y", d3.forceY().strength(0.07))
    .force("cluster", clusterPull(0.06))
    .alphaDecay(0.02)
    .velocityDecay(0.35);

  d3.select(canvas)
    .call(d3.drag().container(canvas).subject(pick).on("start", dragStart).on("drag", dragging).on("end", dragEnd))
    .call(zoom)
    .on("dblclick.zoom", null)
    .on("mousemove", (e) => { hover = pick(e); canvas.classList.toggle("over", !!hover); })
    .on("mouseleave", () => (hover = null))
    .on("click", (e) => { if (!e.defaultPrevented) { const n = pick(e); if (n) select(n); } });
  $("close").onclick = () => { selected = null; $("inspector").hidden = true; };
  resize();
  addEventListener("resize", resize);
  requestAnimationFrame(frame);
}

// Gently pulls each node toward its cluster centroid so clusters read as regions, not just colours.
function clusterPull(strength) {
  return (alpha) => {
    const sums = new Map();
    for (const n of nodes) {
      if (!n.cluster) continue;
      const s = sums.get(n.cluster) || { x: 0, y: 0, k: 0 };
      s.x += n.x; s.y += n.y; s.k++;
      sums.set(n.cluster, s);
    }
    for (const n of nodes) {
      const s = sums.get(n.cluster);
      if (!s) continue;
      n.vx += (s.x / s.k - n.x) * strength * alpha;
      n.vy += (s.y / s.k - n.y) * strength * alpha;
    }
  };
}

const zoom = d3.zoom().scaleExtent([0.2, 8]).filter((e) => e.type === "wheel" || !pick(e)).on("zoom", (e) => (transform = e.transform));

// Pointer position in graph coordinates; nearest node within its radius (plus a little slack).
function pick(event) {
  const [mx, my] = d3.pointer(event.sourceEvent || event, canvas);
  const [x, y] = transform.invert([mx, my]);
  let best = null, bestD = Infinity;
  for (const n of nodes) {
    const d = Math.hypot(n.x - x, n.y - y);
    if (d < n.r + 4 / transform.k && d < bestD) { best = n; bestD = d; }
  }
  return best;
}

// Dragging pins the node under the pointer and reheats the sim; on release the pin lifts and the springs pull it back.
function dragStart(e) {
  if (!e.active) sim.alphaTarget(0.3).restart();
  e.subject.fx = e.subject.x; e.subject.fy = e.subject.y;
}
function dragging(e) {
  const [x, y] = transform.invert([e.x, e.y]);
  e.subject.fx = x; e.subject.fy = y;
}
function dragEnd(e) {
  if (!e.active) sim.alphaTarget(0);
  e.subject.fx = null; e.subject.fy = null;
}

function select(n) {
  selected = n;
  const k = Math.max(transform.k, 1.8);
  const t = d3.zoomIdentity.translate(width / 2 - (width < 800 ? 0 : 180), height / 2).scale(k).translate(-n.x, -n.y); // leave room for the inspector
  d3.select(canvas).transition().duration(800).ease(d3.easeCubicInOut).call(zoom.transform, t);
  inspect(n);
}

function inspect(n) {
  const kindEl = $("i-kind");
  kindEl.textContent = n.kind;
  kindEl.style.color = n.color;
  $("i-name").textContent = n.name;
  $("i-label").textContent = n.label;
  $("i-cluster").textContent = n.cluster || "none";
  $("i-source").textContent = n.source;
  $("i-desc").textContent = n.description || "No description.";
  const list = $("i-rel");
  list.replaceChildren();
  for (const l of links) {
    const out = l.source.id === n.id;
    if (!out && l.target.id !== n.id) continue;
    const other = out ? l.target : l.source;
    const li = document.createElement("li");
    const kind = document.createElement("small");
    kind.textContent = out ? l.kind : `${l.kind} by`;
    const btn = document.createElement("button");
    btn.textContent = other.name;
    btn.onclick = () => select(other);
    li.append(kind, btn);
    list.append(li);
  }
  if (!list.children.length) list.textContent = "None";
  $("inspector").hidden = false;
}

function resize() {
  const dpr = devicePixelRatio || 1;
  width = innerWidth; height = innerHeight;
  canvas.width = width * dpr; canvas.height = height * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (transform === d3.zoomIdentity) d3.select(canvas).call(zoom.transform, d3.zoomIdentity.translate(width / 2, height / 2));
}

const lerp = (a, b, t) => a + (b - a) * t;
const active = () => hover || selected;
const near = (n, f) => !f || n === f || neighbours.get(f.id).has(n.id);

function frame() {
  const f = active();
  for (const n of nodes) n.a = lerp(n.a, near(n, f) ? 1 : FADE, 0.18);
  for (const l of links) l.a = lerp(l.a, !f || l.source === f || l.target === f ? 1 : FADE * 0.6, 0.18);

  ctx.clearRect(0, 0, width, height);
  ctx.save();
  ctx.translate(transform.x, transform.y);
  ctx.scale(transform.k, transform.k);

  ctx.lineWidth = 1 / transform.k;
  for (const l of links) {
    ctx.globalAlpha = l.a * 0.45;
    ctx.strokeStyle = f && (l.source === f || l.target === f) ? token("--link-hot") : token("--link");
    ctx.beginPath(); ctx.moveTo(l.source.x, l.source.y); ctx.lineTo(l.target.x, l.target.y); ctx.stroke();
  }

  ctx.shadowBlur = +token("--glow");
  for (const n of nodes) {
    const c = n.color;
    ctx.globalAlpha = n.a;
    ctx.shadowColor = c; ctx.fillStyle = c;
    ctx.beginPath(); ctx.arc(n.x, n.y, n.r * (n === f ? 1.25 : 1), 0, 2 * Math.PI); ctx.fill();
  }
  ctx.shadowBlur = 0;

  // Labels fade in with zoom; hubs appear sooner, and the focused neighbourhood is always named.
  ctx.font = `${12 / transform.k}px ui-sans-serif, system-ui, sans-serif`;
  ctx.textAlign = "center"; ctx.textBaseline = "top";
  ctx.fillStyle = token("--text");
  ctx.strokeStyle = token("--bg"); ctx.lineWidth = 3 / transform.k; ctx.lineJoin = "round"; // halo keeps labels legible over links
  for (const n of nodes) {
    const zoomAlpha = d3.scaleLinear().domain([n.degree >= 4 ? 0 : 1.2 - Math.min(0.5, n.degree * 0.05), 2.2]).range([0, 1]).clamp(true)(transform.k);
    const a = n === f ? 1 : zoomAlpha * n.a; // only the focused node is named regardless of zoom
    if (a < 0.03) continue;
    ctx.globalAlpha = a;
    const y = n.y + n.r + 3 / transform.k;
    ctx.strokeText(n.name, n.x, y);
    ctx.fillText(n.name, n.x, y);
  }
  ctx.restore();
  requestAnimationFrame(frame);
}
