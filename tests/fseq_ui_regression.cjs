const {readFileSync}=require('node:fs');const vm=require('node:vm');const assert=require('node:assert/strict');
const elements=new Map();
function el(id){if(!elements.has(id))elements.set(id,{value:'',hidden:false,textContent:'',children:[],append(...x){this.children.push(...x)},replaceChildren(...x){this.children=x;this.value=x[0]?.value||''},querySelector(sel){return el(sel)},querySelectorAll(){return []},insertBefore(){},classList:{}});return elements.get(id)}
const calls=[];let fail=false;
const data={id:'first',media_name:'First.mp3',duration_ms:1000,tracks:[{name:'Lead',cue_count:3}]};
const context={document:{querySelector:el,createElement:()=>el(Symbol()),head:{append(){}}},Option:function(text,value){this.text=text;this.value=value},fetch:async(path,opts)=>{calls.push([path,opts]);let body={};if(path==='/api/fpp/settings')body={enabled:true};if(path==='/api/fpp/sequences')body={files:['First.fseq','Second.fseq']};if(path.includes('/import')){if(fail)throw Error('Import failed');body=data;}if(path.includes('/prepare'))body={track:'Lead',media_name:'First.mp3'};return {ok:true,json:async()=>body}},console};
vm.runInNewContext(readFileSync('src/skelly_ai/static/fseq.js','utf8'),context);
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{await tick();const box=[...elements.values()].find(x=>x.id==='fpp-song-library');const q=id=>el('#'+id);
// The box uses its own querySelector; all ids are routed through el.
await q('fseq-list').onclick();await q('fseq-import').onclick();assert.equal(q('fseq-media').value,'First.mp3');assert.equal(q('fseq-prepare').hidden,false);
q('fseq-files').value='Second.fseq';q('fseq-files').onchange();assert.equal(q('fseq-prepare').hidden,true);assert.equal(q('fseq-media').value,'');assert.equal(q('fseq-track').children.length,0);
let n=calls.length;q('fseq-prepare').onsubmit({preventDefault(){}});await tick();assert.equal(calls.length,n,'stale form must not submit');
await q('fseq-import').onclick();q('fseq-track').value='Lead';q('fseq-prepare').onsubmit({preventDefault(){}});await tick();await tick();assert.equal(q('fseq-prepare').hidden,true);assert.equal(q('fseq-media').value,'');assert.match(q('fseq-result').textContent,/Ready: Lead/);
await q('fseq-import').onclick();fail=true;await q('fseq-import').onclick();assert.equal(q('fseq-prepare').hidden,true);assert.equal(q('fseq-media').value,'');
console.log('PASS: sequence change, stale submission guard, successful creation reset, failed import reset');})();
