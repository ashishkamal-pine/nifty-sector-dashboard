const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');

const html = fs.readFileSync('RRG.html', 'utf8');
const script = html.slice(html.indexOf('let rrgGen = 0;'), html.lastIndexOf('</script>'));
const settle = async () => { for(let i=0; i<3; i++) await new Promise(setImmediate); };
const payload = tf => ({
  scope:'sectors', timeframe:tf, smoothing:tf==='daily'?20:10,
  points:[{name:'Fixture', quadrant:tf==='daily'?'Leading':'Weakening'}],
  sectors:[], skipped:[], short_history:[], benchmark:'Benchmark',
  as_of:'2026-10-26', generated_at:'2026-10-26T17:00:00', method:'test', source:'fixture'
});

function harness(fetchImpl = async url => ({ok:true, json:async()=>payload(new URLSearchParams(url.split('?')[1]).get('tf'))})) {
  const nodes = {}, timers = new Map(), events = {}, renders = [], requests = [];
  let timerId = 0;
  const node = id => nodes[id] ||= {textContent:'', classList:{add(){}, remove(){}}, addEventListener(){}};
  const document = {hidden:false, getElementById:node, addEventListener:(name,fn)=>events[name]=fn};
  const context = vm.createContext({
    state:{scope:'sectors', sector:null, tf:'weekly', tail:12, bench:'nifty'},
    document, window:{addEventListener:(name,fn)=>events[name]=fn, requestIdleCallback(){}},
    URLSearchParams, Date,
    fetch:url=>{ requests.push(url); return fetchImpl(url); },
    render:()=>renders.push(context.state.data), buildScopeSelect(){},
    requestIdleCallback(){},
    setTimeout:(fn,ms)=>{ timers.set(++timerId,{fn,ms}); return timerId; },
    clearTimeout:id=>timers.delete(id)
  });
  vm.runInContext(script + '\nthis.loadRrg=load; this.isLoading=()=>rrgLoading;', context);
  return {context, document, events, renders, requests, nodes, timers,
    tick(){
      const [id,timer] = [...timers].find(([,t])=>t.ms===120000) || [];
      assert(timer, 'a refresh must be scheduled');
      timers.delete(id);
      timer.fn();
    }
  };
}

test('refresh updates the graph/table payload for the current selection every two minutes', async()=>{
  const h = harness();
  await settle();
  assert.equal(h.renders.length,1);
  h.context.state.tf='daily';
  h.context.state.scope='sector';
  h.context.state.sector='IT';
  h.context.state.bench='sector';
  h.tick();
  await settle();
  const query=new URLSearchParams(h.requests.at(-1).split('?')[1]);
  assert.equal(query.get('tf'),'daily');
  assert.equal(query.get('name'),'IT');
  assert.equal(query.get('bench'),'sector');
  assert.equal(h.renders.at(-1).points[0].quadrant,'Leading');
  assert.equal(h.nodes.mUpdated.textContent,'2026-10-26 17:00:00');
  assert.equal(h.timers.size,1);
});

test('hidden tabs stop polling and returning to the tab refreshes once', async()=>{
  const h = harness();
  await settle();
  h.document.hidden=true;
  h.events.visibilitychange();
  assert.equal(h.timers.size,0);
  h.events.focus();
  assert.equal(h.requests.length,1);
  h.document.hidden=false;
  h.events.visibilitychange();
  h.events.focus(); // focus and visibility events must not double up
  await settle();
  assert.equal(h.requests.length,2);
  assert.equal(h.timers.size,1);
});

test('an older Weekly response cannot overwrite a newer Daily selection', async()=>{
  let resolveOld;
  const h = harness(url=>new URLSearchParams(url.split('?')[1]).get('tf')==='weekly'
    ? new Promise(resolve=>resolveOld=resolve)
    : Promise.resolve({ok:true,json:async()=>payload('daily')}));
  h.context.state.tf='daily';
  await h.context.loadRrg();
  resolveOld({ok:true,json:async()=>payload('weekly')});
  await settle();
  assert.equal(h.renders.length,1);
  assert.equal(h.renders[0].timeframe,'daily');
  assert.equal(h.context.isLoading(),false);
  assert.equal(h.timers.size,1);
});

test('failed refresh preserves the displayed data and schedules a retry', async()=>{
  let fail=false;
  const h = harness(async()=>{
    if(fail) throw Error('source unavailable');
    return {ok:true,json:async()=>payload('weekly')};
  });
  await settle();
  fail=true;
  h.tick();
  await settle();
  assert.equal(h.renders.length,1);
  assert.match(h.nodes.status.textContent,/source unavailable/);
  assert.equal(h.context.isLoading(),false);
  fail=false;
  h.tick();
  await settle();
  assert.equal(h.renders.length,2);
});

test('manual refresh retains the force flag', async()=>{
  const h=harness();
  await settle();
  await h.context.loadRrg(true);
  assert.equal(new URLSearchParams(h.requests.at(-1).split('?')[1]).get('force'),'1');
  assert.equal(h.timers.size,1);
});
