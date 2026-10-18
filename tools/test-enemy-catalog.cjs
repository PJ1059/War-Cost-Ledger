// Executes the actual page script with a small DOM substitute; no browser automation.
// Run from war-cost-ledger: node tools/test-enemy-catalog.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '../docs/enemy-catalog');
const page = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const baseline = JSON.parse(page.match(/<script id="catalog-data" type="application\/json">([\s\S]*?)<\/script>/)[1]);
const script = page.match(/<script>([\s\S]*?)<\/script>/)[1];
const storageKey = 'hd2-enemy-catalog-roles-v1';
const passed = [];
function test(name, fn) { fn(); passed.push(name); }

class Node {
  constructor(text = '') {
    this.textContent = text;
    this.value = '';
    this.className = '';
    this.hidden = false;
    this.open = false;
    this.dataset = {};
    this.children = [];
    this.listeners = new Map();
  }
  addEventListener(type, callback) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(callback);
  }
  fire(type, event = {}) {
    for (const callback of this.listeners.get(type) || []) callback(event);
  }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.children = children; }
  remove() { this.removed = true; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  click() { this.fire('click'); }
}

function environment(store = new Map(), options = {}) {
  const ids = ['search', 'faction', 'class', 'state', 'result', 'empty', 'reset',
    'catalog-data', 'role-editor', 'edit-class', 'edit-tags', 'edit-note',
    'editor-error', 'editor-title', 'editor-english', 'role-form', 'restore-role',
    'cancel-role', 'export-roles', 'save-message', 'edit-summary'];
  const controls = Object.fromEntries(ids.map(id => [id, new Node()]));
  controls['catalog-data'].textContent = JSON.stringify(baseline);
  const rows = baseline.units.map(unit => {
    const row = new Node();
    row.dataset = { unit: unit.name_en, faction: unit.faction,
      class: unit.display_class, state: unit.classification_status, search: '' };
    const fields = Object.fromEntries(['.badge', '.status', '.note', '.tags',
      '[data-edit-unit]'].map(selector => [selector, new Node()]));
    row.querySelector = selector => {
      assert.ok(fields[selector], 'Unexpected row selector: ' + selector);
      return fields[selector];
    };
    return row;
  });
  const summaries = ['终结族', '机器人', '光能者', '合计'].map(group => {
    const row = new Node();
    row.children = [new Node(group), ...Array.from({length: 7}, () => new Node())];
    return row;
  });
  const blobs = [];
  const downloads = [];
  const document = {
    getElementById: id => { assert.ok(controls[id], 'Unknown control: ' + id); return controls[id]; },
    querySelectorAll: selector => {
      if (selector === '#units tr') return rows;
      if (selector === '.summary tbody tr') return summaries;
      throw Error('Unexpected document selector: ' + selector);
    },
    createElement: tag => {
      const node = new Node();
      if (tag === 'a') node.addEventListener('click', () => downloads.push({href: node.href, name: node.download}));
      return node;
    },
    body: new Node()
  };
  const localStorage = {
    getItem: key => {
      if (options.readFailure) throw Error('Storage unavailable');
      return store.get(key) || null;
    },
    setItem: (key, value) => {
      if (options.writeFailure) throw Error('Storage unavailable');
      store.set(key, value);
    }
  };
  const context = vm.createContext({ document, localStorage, Blob,
    URL: { createObjectURL: blob => { blobs.push(blob); return 'blob:test-' + blobs.length; }, revokeObjectURL() {} },
    setTimeout: callback => callback() });
  vm.runInContext(script, context);
  const get = expression => JSON.parse(vm.runInContext('JSON.stringify(' + expression + ')', context));
  function edit(name, fields) {
    const row = rows.find(r => r.dataset.unit === name);
    row.querySelector('[data-edit-unit]').click();
    assert.equal(controls['role-editor'].open, true);
    if (fields.class !== undefined) controls['edit-class'].value = fields.class;
    if (fields.tags !== undefined) controls['edit-tags'].value = fields.tags;
    if (fields.note !== undefined) controls['edit-note'].value = fields.note;
    controls['role-form'].fire('submit', {preventDefault() {}});
    return row;
  }
  function filter(values) {
    for (const id of ['search', 'faction', 'class', 'state']) controls[id].value = values[id] || '';
    controls.search.fire('input');
    return rows.filter(row => !row.hidden).map(row => row.dataset.unit);
  }
  return { controls, rows, summaries, blobs, downloads, get, edit, filter, store };
}

test('83 units, 83 images and one edit button per unit', () => {
  assert.equal(baseline.units.length, 83);
  assert.equal((page.match(/src="data:image\//g) || []).length, 83);
  const names = [...page.matchAll(/data-edit-unit="([^"]+)"/g)].map(m => m[1]);
  assert.equal(names.length, 83);
  assert.deepEqual(names, baseline.units.map(unit => unit.name_en));
});

test('Edit updates row, confirmation, search and whole-catalog counts', () => {
  const env = environment();
  const row = env.edit('Stingray', {class: '重型', tags: '飞行，飞行、压制, 护盾', note: '用于测试的单位定位。'});
  const unit = env.get('unitsByName.get("Stingray")');
  assert.equal(unit.display_class, '重型');
  assert.equal(unit.main_class, '重型');
  assert.equal(unit.subclass, '');
  assert.deepEqual(unit.tags, ['飞行', '压制', '护盾']);
  assert.equal(unit.note, '用于测试的单位定位。');
  assert.equal(unit.classification_status, '已确认');
  assert.equal(row.querySelector('.badge').textContent, '重型');
  assert.equal(row.querySelector('.note').textContent, unit.note);
  assert.match(row.querySelector('.status').textContent, /你已修改/);
  const total = env.summaries[3].children;
  assert.equal(total[3].textContent, '15');
  assert.equal(total[4].textContent, '23');
  assert.equal(total[7].textContent, '83');
  assert.ok(env.filter({faction: '光能者', class: '重型', search: '用于测试'}).includes('Stingray'));
  assert.equal(env.controls['role-editor'].open, false);
  assert.match(env.controls['save-message'].textContent, /已保存：刺魟/);
});

test('Saved edits survive another page initialization and another edit', () => {
  const store = new Map();
  environment(store).edit('Stingray', {class: '巨型', tags: '飞行、扫射', note: '保留这条修改'});
  const reload = environment(store);
  assert.equal(reload.get('unitsByName.get("Stingray").display_class'), '巨型');
  assert.equal(reload.get('unitsByName.get("Stingray").note'), '保留这条修改');
  assert.match(reload.controls['save-message'].textContent, /已恢复/);
  reload.edit('Alpha Commander', {class: '中型'});
  const next = environment(store);
  assert.equal(next.get('unitsByName.get("Stingray").display_class'), '巨型');
  assert.equal(next.get('unitsByName.get("Alpha Commander").display_class'), '中型');
  assert.equal(JSON.parse(store.get(storageKey)).units.length, 2);
});

test('All six classifications preserve the medium/elite hierarchy', () => {
  for (const classification of ['轻型', '中型', '中型精英', '重型', '巨型', 'BOSS']) {
    const env = environment();
    env.edit('Scavenger', {class: classification});
    const unit = env.get('unitsByName.get("Scavenger")');
    assert.equal(unit.main_class, classification === '中型精英' ? '中型' : classification);
    assert.equal(unit.subclass, classification === '中型精英' ? '精英' : '');
    assert.equal(env.summaries[3].children[7].textContent, '83');
  }
});

test('Cancel and fill-original do not silently save changes', () => {
  const env = environment();
  const row = env.rows.find(r => r.dataset.unit === 'Stingray');
  row.querySelector('[data-edit-unit]').click();
  env.controls['edit-class'].value = 'BOSS';
  env.controls['cancel-role'].click();
  assert.equal(env.get('unitsByName.get("Stingray").display_class'), '中型精英');
  assert.equal(env.store.size, 0);
  env.edit('Stingray', {class: '重型'});
  row.querySelector('[data-edit-unit]').click();
  env.controls['restore-role'].click();
  assert.equal(env.controls['edit-class'].value, '中型精英');
  assert.equal(env.get('unitsByName.get("Stingray").display_class'), '重型');
  env.controls['cancel-role'].click();
});

test('Existing search and parent-category filter work after editing', () => {
  const env = environment();
  assert.equal(env.filter({class: '中型全部'}).length, 30);
  assert.equal(env.filter({search: 'Charger'}).length, 4);
  assert.deepEqual(env.filter({class: 'BOSS'}), ['Hive Lord', 'Illuminate Overship']);
  env.edit('Stingray', {class: '重型'});
  assert.equal(env.filter({class: '中型全部'}).length, 29);
  assert.equal(env.filter({search: '不存在的单位'}).length, 0);
  assert.equal(env.controls.empty.hidden, false);
  env.controls.reset.click();
  assert.equal(env.rows.filter(row => !row.hidden).length, 83);
});

test('Storage failure reports the limitation while keeping the current edit', () => {
  const env = environment(new Map(), {readFailure: true, writeFailure: true});
  env.edit('Stingray', {class: '重型', note: '浏览器未能保存也可导出'});
  assert.equal(env.get('unitsByName.get("Stingray").display_class'), '重型');
  assert.equal(env.store.size, 0);
  assert.match(env.controls['save-message'].textContent, /未能保存.*导出定位表/);
  env.controls['export-roles'].click();
  assert.equal(env.blobs.length, 1);
});

test('Incorporated export does not overwrite corrected default notes', () => {
  const unit = baseline.units.find(u => u.name_en === 'Gunship');
  assert.ok(unit.classification_edited_at);
  const cached = {name_en: unit.name_en, display_class: unit.display_class,
    tags: unit.tags, note: '旧说明：与刺魟采用一致口径。',
    classification_edited_at: unit.classification_edited_at};
  const store = new Map([[storageKey, JSON.stringify({version: 1, units: [cached]})]]);
  const env = environment(store);
  assert.equal(env.get('unitsByName.get("Gunship").note'), unit.note);
  assert.equal(env.get('overrides.size'), 0);
  assert.match(env.controls['save-message'].textContent, /已成为当前默认定位/);
  assert.equal(store.get(storageKey), JSON.stringify({version: 1, units: [cached]}));
});

test('Later browser edit remains effective after an exported baseline is adopted', () => {
  const unit = baseline.units.find(u => u.name_en === 'Gunship');
  const cached = {name_en: unit.name_en, display_class: '重型',
    tags: ['飞行'], note: '这条是后来修改的定位',
    classification_edited_at: '2099-01-01T00:00:00.000Z'};
  const store = new Map([[storageKey, JSON.stringify({version: 1, units: [cached]})]]);
  const env = environment(store);
  assert.equal(env.get('unitsByName.get("Gunship").display_class'), '重型');
  assert.equal(env.get('unitsByName.get("Gunship").note'), cached.note);
  assert.equal(env.get('overrides.size'), 1);
});

(async () => {
  try {
    const env = environment();
    env.edit('Stingray', {class: '重型', tags: '飞行、扫射', note: '新定位 <保留原文>'});
    env.filter({class: 'BOSS'});
    env.controls['export-roles'].click();
    const exported = JSON.parse(await env.blobs[0].text());
    assert.equal(exported.units.length, 83, 'Export must include filtered-out units');
    const unit = exported.units.find(u => u.name_en === 'Stingray');
    assert.equal(unit.display_class, '重型');
    assert.equal(unit.main_class, '重型');
    assert.equal(unit.note, '新定位 <保留原文>');
    assert.ok(unit.image_sha256 && unit.source_zh && unit.source_en);
    assert.match(env.downloads[0].name, /^HD2-敌军定位表-\d{4}-\d{2}-\d{2}\.json$/);
    assert.equal(baseline.units.find(u => u.name_en === 'Stingray').display_class, '中型精英');
    passed.push('Export includes all 83 units, edited roles, Chinese text and original sources');
    console.log(JSON.stringify({status: 'passed', method: 'Actual page script with DOM/storage/download substitutes; no visual browser verification', checks: passed}, null, 2));
  } catch (error) { console.error(error); process.exitCode = 1; }
})();
