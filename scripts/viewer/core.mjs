// Pure functions shared by the browser and the offline tests.
export const units = s => (s.match(/[\u3400-\u9fff\uf900-\ufaff]|[A-Za-z0-9]+(?:['’.-][A-Za-z0-9]+)*/g) || []).length;
export function sentences(s) {
  const result=[];
  for(const part of s.split(/(?<=[。！？；!?;])|(?<=\n)|(?<=\.)(?= [A-Z])/).filter(Boolean)){
    if(/^\s+$/.test(part)&&result.length)result[result.length-1]+=part;
    else result.push(part);
  }
  return result;
}
function bigrams(s) {
  const text = s.replace(/\s/g, '');
  return new Set(text.length < 2 ? [text] : Array.from({length: text.length - 1}, (_, i) => text.slice(i, i + 2)));
}
export function dice(a, b) {
  const x = bigrams(a), y = bigrams(b);
  return 2 * [...x].filter(v => y.has(v)).length / Math.max(1, x.size + y.size);
}
export function align(a, b, similarity = dice, threshold = .3) {
  const n = a.length, m = b.length;
  const table = Array.from({length: n + 1}, () => new Float64Array(m + 1));
  const sim = a.map(x => b.map(y => similarity(x, y)));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) {
    table[i][j] = Math.max(table[i + 1][j], table[i][j + 1], sim[i][j] >= threshold ? table[i + 1][j + 1] + sim[i][j] : -1);
  }
  let i = 0, j = 0;
  const rows = [];
  while (i < n || j < m) {
    if (i < n && j < m && sim[i][j] >= threshold && Math.abs(table[i][j] - table[i + 1][j + 1] - sim[i][j]) < 1e-8) rows.push([a[i++], b[j++]]);
    else if (j < m && (i === n || table[i][j] === table[i][j + 1])) rows.push([null, b[j++]]);
    else rows.push([a[i++], null]);
  }
  return rows;
}
export function threeWay(base, others) {
  const pairs = others.map(text => align(base, text));
  const insertions = others.map(() => Array.from({length: base.length + 1}, () => []));
  const matched = others.map(() => Array(base.length).fill(null));
  pairs.forEach((rows, k) => {
    let i = 0;
    for (const [a, b] of rows) {
      if (a === null) insertions[k][i].push(b);
      else matched[k][i++] = b;
    }
  });
  const result = [];
  for (let i = 0; i <= base.length; i++) {
    const count = Math.max(0, ...insertions.map(xs => xs[i].length));
    for (let j = 0; j < count; j++) result.push([null, ...insertions.map(xs => xs[i][j] ?? null)]);
    if (i < base.length) result.push([base[i], ...matched.map(xs => xs[i])]);
  }
  return result;
}
export function defaultRun(runs, bad = false) {
  let candidates = runs.filter(r => (r.has_text || r.text?.trim()) && !r.fail_type?.startsWith('infra_'));
  if (bad && candidates.some(r => r.correct === 0)) candidates = candidates.filter(r => r.correct === 0);
  if (!candidates.length) return null;
  const mean = candidates.reduce((s, r) => s + r.len_units, 0) / candidates.length;
  return [...candidates].sort((a, b) => Math.abs(a.len_units - mean) - Math.abs(b.len_units - mean) || a.rep - b.rep)[0];
}
export function files(text) {
  const markers = [...text.matchAll(/^=== FILE: (.+?) ===\s*\n/gm)];
  if (!markers.length) return null;
  const result = {};
  if (markers[0].index) result['回答开头'] = text.slice(0, markers[0].index);
  markers.forEach((m, i) => { result[m[1]] = text.slice(m.index + m[0].length, markers[i + 1]?.index ?? text.length); });
  return result;
}
export const lines = s => s.match(/[^\n]*\n|[^\n]+$/g) || [];
export function quoteRange(original, quote, fragment) {
  if(!quote)return null;
  const q=original.indexOf(quote);
  if(q<0)return null;
  const start=original.indexOf(fragment,Math.max(0,q-fragment.length+1));
  if(start<0||start>=q+quote.length||start+fragment.length<=q)return null;
  return [Math.max(0,q-start),Math.min(fragment.length,q+quote.length-start)];
}
export function wordDiff(a, b) {
  const segmenter = new Intl.Segmenter('zh', {granularity: 'word'});
  const words = s => Array.from(segmenter.segment(s), x => x.segment);
  const left = words(a), right = words(b);
  // Strip the exact common prefix/suffix before allocating the DP matrix.
  let first = 0, tail = 0;
  while (first < Math.min(left.length, right.length) && left[first] === right[first]) first++;
  while (tail < Math.min(left.length, right.length) - first && left.at(-1 - tail) === right.at(-1 - tail)) tail++;
  const midA = left.slice(first, left.length - tail), midB = right.slice(first, right.length - tail);
  const rows = midA.length * midB.length > 1500000 ? [...midA.map(x => [x, null]), ...midB.map(x => [null, x])] : align(midA, midB, (x, y) => x === y ? 1 : 0, 1);
  const groups = [];
  for (const [x, y] of [[left.slice(0, first).join(''), right.slice(0, first).join('')], ...rows, [tail ? left.slice(-tail).join('') : '', tail ? right.slice(-tail).join('') : '']]) {
    const kind = x === y ? 'same' : x === null ? 'add' : 'del';
    const text = x ?? y;
    if (!text) continue;
    if (groups.at(-1)?.kind === kind) groups.at(-1).text += text;
    else groups.push({kind, text});
  }
  return groups;
}
