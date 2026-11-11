// Run with: node --test tests/alternatif_ui.test.cjs
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../webapp/static/araclar.js'), 'utf8');
const handler = source.slice(source.indexOf('    let creatingAlternative = false;'), source.indexOf('    const draw = async id =>'));

function setup(api, floors = '4', units = '2') {
  const elements = Object.fromEntries(Object.entries({
    'alt-name': {value: 'Alternative'}, 'alt-floors': {value: floors},
    'alt-ut': {value: '2+1'}, 'alt-upf': {value: units},
    'alt-ack': {checked: true}, 'alt-go': {}, 'alt-msg': {}, 'cm-alt': {},
  }).map(([id, value]) => ['#' + id, value]));
  const controls = Object.values(elements);
  elements['#cm-alt-form'] = {querySelectorAll: () => controls};
  const window = {location: {href: '', reloaded: false, reload() { this.reloaded = true; }}};
  const context = vm.createContext({$: id => elements[id], api, P: {id: 'source'}, window,
    setTimeout: fn => fn(), encodeURIComponent});
  vm.runInContext(handler + '\nglobalThis.submit = createAlternative;', context);
  return {submit: context.submit, elements, window};
}

test('numeric units are sent as numbers and success navigates to project hash', async () => {
  let body;
  const ui = setup(async (_, request) => {
    body = JSON.parse(request.body);
    return {alternative: {name: 'Alternative', id: 'new-project'}};
  });
  await ui.submit();
  assert.equal(body.units_per_floor, 2);
  assert.equal(body.floors, 4);
  assert.equal(ui.window.location.href, '/#new-project');
  assert.equal(ui.window.location.reloaded, true);
});

test('duplicate submissions are blocked while request is pending', async () => {
  let calls = 0, finish;
  const ui = setup(() => { calls++; return new Promise(resolve => { finish = resolve; }); });
  const pending = ui.submit();
  await ui.submit();
  assert.equal(calls, 1);
  assert.equal(ui.elements['#alt-go'].disabled, true);
  finish({alternative: {name: 'Alternative', id: 'new-project'}});
  await pending;
});

test('failure permits retry and auto selection remains a string', async () => {
  let calls = 0;
  const ui = setup(async (_, request) => {
    calls++;
    assert.equal(JSON.parse(request.body).units_per_floor, 'auto');
    throw new Error('Failed');
  }, '4', 'auto');
  await ui.submit();
  assert.equal(ui.elements['#alt-go'].disabled, false);
  assert.equal(ui.elements['#alt-msg'].textContent, 'Failed');
  await ui.submit();
  assert.equal(calls, 2);
});

test('fractional floors are rejected rather than silently truncated', async () => {
  const ui = setup(() => assert.fail('No request expected'), '2.5');
  await ui.submit();
  assert.match(ui.elements['#alt-msg'].textContent, /tam sayı/);
});
