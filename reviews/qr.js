/*
 * Small self-contained QR code encoder (byte mode, error correction level M).
 * Based on the structure of Project Nayuki's QR Code generator (MIT licence).
 * Usage: QR.encode("https://example.com") -> { size, modules: boolean[][] }
 *        QR.toSvg(qr, { dark, light, margin }) -> SVG string
 */
(function (root) {
  'use strict';

  // Level M tables, indexed by version (index 0 unused).
  var ECC_PER_BLOCK = [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28];
  var NUM_BLOCKS = [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49];
  var FORMAT_ECL_M = 0;

  function rawDataModules(ver) {
    var result = (16 * ver + 128) * ver + 64;
    if (ver >= 2) {
      var numAlign = Math.floor(ver / 7) + 2;
      result -= (25 * numAlign - 10) * numAlign - 55;
      if (ver >= 7) result -= 36;
    }
    return result;
  }

  function dataCodewords(ver) {
    return Math.floor(rawDataModules(ver) / 8) - ECC_PER_BLOCK[ver] * NUM_BLOCKS[ver];
  }

  function gfMul(x, y) {
    var z = 0;
    for (var i = 7; i >= 0; i--) {
      z = (z << 1) ^ ((z >>> 7) * 0x11D);
      z ^= ((y >>> i) & 1) * x;
    }
    return z;
  }

  function rsDivisor(degree) {
    var result = [];
    for (var i = 0; i < degree - 1; i++) result.push(0);
    result.push(1);
    var r = 1;
    for (i = 0; i < degree; i++) {
      for (var j = 0; j < result.length; j++) {
        result[j] = gfMul(result[j], r);
        if (j + 1 < result.length) result[j] ^= result[j + 1];
      }
      r = gfMul(r, 0x02);
    }
    return result;
  }

  function rsRemainder(data, divisor) {
    var result = divisor.map(function () { return 0; });
    data.forEach(function (b) {
      var factor = b ^ result.shift();
      result.push(0);
      divisor.forEach(function (coef, i) { result[i] ^= gfMul(coef, factor); });
    });
    return result;
  }

  function utf8Bytes(str) {
    var s = unescape(encodeURIComponent(str));
    var out = [];
    for (var i = 0; i < s.length; i++) out.push(s.charCodeAt(i));
    return out;
  }

  function encode(text) {
    var bytes = utf8Bytes(text);
    var ver;
    for (ver = 1; ; ver++) {
      if (ver > 40) throw new Error('Text too long for a QR code');
      var used = 4 + (ver < 10 ? 8 : 16) + bytes.length * 8;
      if (used <= dataCodewords(ver) * 8) break;
    }

    // Build the bit stream.
    var bits = [];
    function push(val, len) { for (var i = len - 1; i >= 0; i--) bits.push((val >>> i) & 1); }
    push(4, 4);
    push(bytes.length, ver < 10 ? 8 : 16);
    bytes.forEach(function (b) { push(b, 8); });
    var capacity = dataCodewords(ver) * 8;
    push(0, Math.min(4, capacity - bits.length));
    push(0, (8 - bits.length % 8) % 8);
    for (var pad = 0xEC; bits.length < capacity; pad ^= 0xEC ^ 0x11) push(pad, 8);
    var data = [];
    for (var i = 0; i < bits.length; i += 8) {
      var v = 0;
      for (var k = 0; k < 8; k++) v = (v << 1) | bits[i + k];
      data.push(v);
    }

    // Split into blocks, add error correction, interleave.
    var numBlocks = NUM_BLOCKS[ver];
    var eccLen = ECC_PER_BLOCK[ver];
    var rawCodewords = Math.floor(rawDataModules(ver) / 8);
    var numShort = numBlocks - rawCodewords % numBlocks;
    var shortLen = Math.floor(rawCodewords / numBlocks);
    var div = rsDivisor(eccLen);
    var blocks = [];
    for (i = 0, k = 0; i < numBlocks; i++) {
      var dat = data.slice(k, k + shortLen - eccLen + (i < numShort ? 0 : 1));
      k += dat.length;
      var ecc = rsRemainder(dat, div);
      if (i < numShort) dat.push(0);
      blocks.push(dat.concat(ecc));
    }
    var codewords = [];
    for (i = 0; i < blocks[0].length; i++) {
      for (var j = 0; j < blocks.length; j++) {
        if (i !== shortLen - eccLen || j >= numShort) codewords.push(blocks[j][i]);
      }
    }

    // Lay out the symbol.
    var size = ver * 4 + 17;
    var modules = [], isFn = [];
    for (i = 0; i < size; i++) {
      modules.push(new Array(size).fill(false));
      isFn.push(new Array(size).fill(false));
    }
    function setFn(x, y, dark) { modules[y][x] = dark; isFn[y][x] = true; }

    for (i = 0; i < size; i++) { setFn(6, i, i % 2 === 0); setFn(i, 6, i % 2 === 0); }

    function finder(cx, cy) {
      for (var dy = -4; dy <= 4; dy++) {
        for (var dx = -4; dx <= 4; dx++) {
          var d = Math.max(Math.abs(dx), Math.abs(dy)), x = cx + dx, y = cy + dy;
          if (x >= 0 && x < size && y >= 0 && y < size) setFn(x, y, d !== 2 && d !== 4);
        }
      }
    }
    finder(3, 3); finder(size - 4, 3); finder(3, size - 4);

    var align = [];
    if (ver > 1) {
      var numAlign = Math.floor(ver / 7) + 2;
      var step = Math.floor((ver * 8 + numAlign * 3 + 5) / (numAlign * 4 - 4)) * 2;
      for (var pos = size - 7; align.length < numAlign - 1; pos -= step) align.unshift(pos);
      align.unshift(6);
    }
    for (i = 0; i < align.length; i++) {
      for (j = 0; j < align.length; j++) {
        if ((i === 0 && j === 0) || (i === 0 && j === align.length - 1) || (i === align.length - 1 && j === 0)) continue;
        for (var ay = -2; ay <= 2; ay++) {
          for (var ax = -2; ax <= 2; ax++) setFn(align[i] + ax, align[j] + ay, Math.max(Math.abs(ax), Math.abs(ay)) !== 1);
        }
      }
    }

    function drawFormat(mask) {
      var d = (FORMAT_ECL_M << 3) | mask, rem = d;
      for (var n = 0; n < 10; n++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
      var b = ((d << 10) | rem) ^ 0x5412;
      function bit(n) { return ((b >>> n) & 1) !== 0; }
      for (n = 0; n <= 5; n++) setFn(8, n, bit(n));
      setFn(8, 7, bit(6)); setFn(8, 8, bit(7)); setFn(7, 8, bit(8));
      for (n = 9; n < 15; n++) setFn(14 - n, 8, bit(n));
      for (n = 0; n < 8; n++) setFn(size - 1 - n, 8, bit(n));
      for (n = 8; n < 15; n++) setFn(8, size - 15 + n, bit(n));
      setFn(8, size - 8, true);
    }
    drawFormat(0);

    if (ver >= 7) {
      var rem = ver;
      for (i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1F25);
      var vb = (ver << 12) | rem;
      for (i = 0; i < 18; i++) {
        var on = ((vb >>> i) & 1) !== 0, a = size - 11 + i % 3, bb = Math.floor(i / 3);
        setFn(a, bb, on); setFn(bb, a, on);
      }
    }

    // Place the codewords in the zigzag pattern.
    var bitIdx = 0;
    for (var right = size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      for (var vert = 0; vert < size; vert++) {
        for (j = 0; j < 2; j++) {
          var x = right - j;
          var y = ((right + 1) & 2) === 0 ? size - 1 - vert : vert;
          if (!isFn[y][x] && bitIdx < codewords.length * 8) {
            modules[y][x] = ((codewords[bitIdx >>> 3] >>> (7 - (bitIdx & 7))) & 1) !== 0;
            bitIdx++;
          }
        }
      }
    }

    function maskBit(m, x, y) {
      switch (m) {
        case 0: return (x + y) % 2 === 0;
        case 1: return y % 2 === 0;
        case 2: return x % 3 === 0;
        case 3: return (x + y) % 3 === 0;
        case 4: return (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0;
        case 5: return (x * y) % 2 + (x * y) % 3 === 0;
        case 6: return ((x * y) % 2 + (x * y) % 3) % 2 === 0;
        default: return ((x + y) % 2 + (x * y) % 3) % 2 === 0;
      }
    }
    function applyMask(m) {
      for (var y = 0; y < size; y++) {
        for (var x = 0; x < size; x++) if (!isFn[y][x] && maskBit(m, x, y)) modules[y][x] = !modules[y][x];
      }
    }
    function penalty() {
      var score = 0, dark = 0, x, y, run;
      var lineAt = [function (i, n) { return modules[i][n]; }, function (i, n) { return modules[n][i]; }];
      lineAt.forEach(function (get) {
        for (var i = 0; i < size; i++) {
          var line = '';
          run = 1;
          for (var n = 0; n < size; n++) {
            var c = get(i, n);
            line += c ? '1' : '0';
            if (n > 0) {
              if (c === get(i, n - 1)) { run++; if (run === 5) score += 3; else if (run > 5) score++; }
              else run = 1;
            }
          }
          var padded = '0000' + line + '0000';
          var re = /(?=(10111010000|00001011101))/g;
          while (re.exec(padded)) { score += 40; re.lastIndex++; }
        }
      });
      for (y = 0; y < size; y++) {
        for (x = 0; x < size; x++) {
          if (modules[y][x]) dark++;
          if (x < size - 1 && y < size - 1) {
            var c = modules[y][x];
            if (c === modules[y][x + 1] && c === modules[y + 1][x] && c === modules[y + 1][x + 1]) score += 3;
          }
        }
      }
      var total = size * size;
      score += Math.floor(Math.abs(dark * 20 - total * 10) / total) * 10;
      return score;
    }

    var best = 0, bestScore = Infinity;
    for (var m = 0; m < 8; m++) {
      applyMask(m);
      drawFormat(m);
      var p = penalty();
      if (p < bestScore) { bestScore = p; best = m; }
      applyMask(m);
    }
    applyMask(best);
    drawFormat(best);

    return { size: size, version: ver, modules: modules };
  }

  function toSvg(qr, opts) {
    opts = opts || {};
    var margin = opts.margin == null ? 4 : opts.margin;
    var dim = qr.size + margin * 2;
    var path = '';
    for (var y = 0; y < qr.size; y++) {
      for (var x = 0; x < qr.size; x++) {
        if (qr.modules[y][x]) path += 'M' + (x + margin) + ' ' + (y + margin) + 'h1v1h-1z';
      }
    }
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + dim + ' ' + dim + '" shape-rendering="crispEdges"' +
      (opts.attrs ? ' ' + opts.attrs : '') + '>' +
      '<rect width="' + dim + '" height="' + dim + '" fill="' + (opts.light || '#ffffff') + '"/>' +
      '<path d="' + path + '" fill="' + (opts.dark || '#000000') + '"/></svg>';
  }

  function toCanvas(qr, canvas, scale, opts) {
    opts = opts || {};
    var margin = opts.margin == null ? 4 : opts.margin;
    var dim = (qr.size + margin * 2) * scale;
    canvas.width = dim; canvas.height = dim;
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = opts.light || '#ffffff';
    ctx.fillRect(0, 0, dim, dim);
    ctx.fillStyle = opts.dark || '#000000';
    for (var y = 0; y < qr.size; y++) {
      for (var x = 0; x < qr.size; x++) {
        if (qr.modules[y][x]) ctx.fillRect((x + margin) * scale, (y + margin) * scale, scale, scale);
      }
    }
    return canvas;
  }

  var api = { encode: encode, toSvg: toSvg, toCanvas: toCanvas };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.QR = api;
})(this);
