from __future__ import annotations

LIVE_MARKUP = r"""<div id="app">
<header>
  <div class="brand"><div class="brand-mark">E</div><div class="brand-copy"><strong>ExecWeave</strong><span>Live execution</span></div></div>
  <span id="status"><span class="status-dot"></span><span id="status-label">LIVE</span></span>
  <div class="header-metrics"><span id="stats" class="metric-pill">Waiting for events…</span><span id="evidence" class="metric-pill optional">OS <strong>0</strong> · specialized <strong>0</strong></span></div>
  <div class="header-spacer"></div>
  <div class="search-wrap"><input id="search" placeholder="Search nodes, types, relations…" aria-label="Search graph"></div>
  <button id="theme-toggle" class="icon-btn" type="button" aria-label="Switch to light theme" title="Switch to light theme">Light</button>
</header>
<section id="graph-panel">
  <div class="panel-bar"><span class="panel-title">Execution Graph</span><span id="graph-subtitle" class="panel-subtitle">Live topology and evidence flow</span><div class="panel-spacer"></div>
    <div class="segmented" aria-label="Camera mode"><button type="button" data-camera="manual" class="active">Manual</button><button type="button" data-camera="fit">Fit graph</button><button type="button" data-camera="follow">Follow latest</button></div>
    <div class="graph-actions"><button id="zoom-out" type="button" aria-label="Zoom out" title="Zoom out">−</button><button id="zoom-in" type="button" aria-label="Zoom in" title="Zoom in">+</button><button id="fit" type="button" aria-label="Fit once" title="Fit graph once">Fit</button></div>
  </div>
  <div id="wrap"><button id="jump-latest" type="button" hidden>Jump to latest</button><div id="protective" hidden><div><strong>LARGE GRAPH PROTECTIVE MODE</strong><p id="protective-summary"></p><p>Live SVG rendering has stopped to protect browser memory. Collection continues and no evidence is deleted or reclassified.</p></div></div><svg id="svg"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="context-stroke"></path></marker></defs><g id="viewport"><g id="edges"></g><g id="labels"></g><g id="nodes"></g></g></svg><div id="camera-hint">Camera <strong id="camera-label">Manual</strong></div></div>
</section>
<aside id="inspector">
  <div class="inspector-section"><div class="eyebrow">Current activity</div><div id="current-title" class="current-title">Waiting for events</div><div id="current-sub" class="current-sub">The newest graph transition will appear here.</div><dl id="current-kv" class="kv"></dl></div>
  <div class="inspector-section"><div class="eyebrow">Selection</div><div id="details-empty">Click a node, edge, or activity row.</div><div id="details"></div></div>
</aside>
<section id="activity-panel">
  <div class="activity-toolbar"><span class="panel-title">Live Activity</span><span id="activity-count" class="count">0 transitions</span><div class="filter-group" aria-label="Activity filters"><button type="button" class="active" data-filter="all">All</button><button type="button" data-filter="process">Process</button><button type="button" data-filter="file">File</button><button type="button" data-filter="network">Network</button><button type="button" data-filter="tool">Tool</button><button type="button" data-filter="model">Model</button></div></div>
  <div id="activity-list"><div class="activity-head"><span>Time</span><span>Kind</span><span>Relation</span><span>Transition</span><span>Evidence</span></div><div id="activity-rows"><div class="empty-activity">Waiting for graph activity…</div></div></div>
</section>
</div>"""
