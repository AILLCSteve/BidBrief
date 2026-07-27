/* The signature element: a luminous planet suspended in deep space behind every
   screen. Ported from Sources/DesignSystem/OrbBackground.swift - the star field
   uses the same deterministic sin-hash so it never shimmers between renders. */
(function (window) {
  'use strict';
  var BB = window.BB = window.BB || {};

  function frac(x) { var v = x % 1; return v < 0 ? -v : v; }

  /** Deterministic star specks - no randomness, stable across renders. */
  function starPoints(count, width, height) {
    var pts = [];
    for (var i = 0; i < count; i++) {
      var n = i;
      var x = frac(Math.sin(n * 12.9898) * 43758.5453);
      var y = frac(Math.sin(n * 78.233) * 96321.9134);
      pts.push({
        x: x * width,
        y: y * height,
        r: 0.6 + Math.abs(x * y) * 1.6,
        opacity: 0.2 + y * 0.45
      });
    }
    return pts;
  }

  /** Drift in page units for tab `index` of `count` (iOS HomeView.drift). */
  function driftFor(index, count) {
    return index - (count - 1) / 2;
  }

  var host = null;

  function paintStars() {
    if (!host) return;
    var canvas = host.querySelector('canvas.bb-orb-stars');
    if (!canvas || !canvas.getContext) return;
    var w = canvas.width = host.offsetWidth;
    var h = canvas.height = host.offsetHeight;
    var ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, w, h);
    starPoints(90, w, h).forEach(function (p) {
      ctx.fillStyle = 'rgba(255,255,255,' + p.opacity.toFixed(3) + ')';
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  function mount(hostElement) {
    if (!hostElement) return;
    host = hostElement;
    paintStars();
    window.addEventListener('resize', paintStars);
    setDrift(0);
  }

  /** Shift the planet and its lighting; CSS custom properties do the work. */
  function setDrift(units) {
    if (!host) return;
    host.style.setProperty('--bb-drift', String(units));
  }

  BB.orb = { mount: mount, setDrift: setDrift, starPoints: starPoints, driftFor: driftFor };
})(typeof window !== 'undefined' ? window : this);
