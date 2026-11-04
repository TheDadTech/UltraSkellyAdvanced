/* Optional USA integrations. State/results stay in the backend. */
(() => {
  const $ = (selector) => document.querySelector(selector);
  const setup = $('#panel-setup');
  const features = document.createElement('section');
  features.id = 'optional-integrations';
  features.innerHTML = `<p class="section-kicker">OPTIONAL FEATURES</p><h2>Optional integrations</h2>
    <label class="check-setting"><input id="feature-fpp" type="checkbox"><span><strong>FPP synchronized singing</strong><small>Follow FPP using local vocals or prepared jaw tracks.</small></span></label>
    <p id="feature-result" class="result" role="status"></p>`;
  setup.append(features);
  const fppCard = document.createElement('section');
  fppCard.id = 'fpp-integration'; fppCard.hidden = true;
  fppCard.innerHTML = `<div class="section-heading"><h2>FPP singing integration</h2><span id="fpp-connected" class="driver-badge neutral" role="status">Disconnected</span></div>
    <p class="muted help-copy">Connect to your Main FPP player here. Add songs and choose singing parts in The Lab → Pi → FPP singing.</p>
    <form id="fpp-feature-form"><label>Main FPP IP address or hostname<input id="fpp-master" inputmode="decimal" placeholder="192.168.1.20" required></label>
    <input id="fpp-audible" type="checkbox" hidden>
    <p id="fpp-capability" class="muted help-copy">FPP sends only the song name and timing. USA plays the track saved on this controller to move Skelly’s jaw. No song audio is streamed from FPP.</p>
    <button type="button" id="fpp-discover">Find FPP players</button><label>Discovered players<select id="fpp-discovered"><option value="">Choose Main FPP</option></select></label><button>Save FPP settings</button></form><p id="fpp-save-result" class="result" role="status"></p>`;
  setup.append(fppCard);
  const style=document.createElement('style');style.textContent='#fpp-feature-form{display:block}.fpp-now-playing{padding:12px 18px;margin-top:14px;border:1px solid var(--border-strong);border-radius:12px;background:var(--panel-soft)}.fpp-override-control{display:inline-flex;align-items:center;gap:7px;margin-left:18px;font-size:.82rem}.fpp-override-control input{width:16px;height:16px}.fpp-song-library>summary .fpp-override-control{float:right}@media(max-width:600px){.fpp-song-library>summary .fpp-override-control{float:none;margin:8px 0 0 12px}}';document.head.append(style);
  const now=document.createElement('div');now.className='fpp-now-playing';now.hidden=true;now.setAttribute('role','status');$('#panel-operate').prepend(now);
  let fppSettings={},busy=false,overrideSaving=false;
  const api=(path,body)=>request(path, body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  function syncOverrideControls(value=fppSettings.override_ai){
    for(const host of [$('.ai-trigger-strip'),$('#fpp-song-library>summary')].filter(Boolean)){
      let label=host.querySelector('.fpp-override-control');
      if(!label){label=document.createElement('label');label.className='fpp-override-control';label.title='Pause AI listening and lures during a matching FPP song; resume when it stops.';const input=document.createElement('input');input.type='checkbox';input.dataset.fppOverride='';const text=document.createElement('span');text.textContent='FPP Override';label.append(input,text);label.addEventListener('click',e=>e.stopPropagation());input.onchange=async()=>{if(overrideSaving)return;const enabled=input.checked,previous=fppSettings.override_ai;overrideSaving=true;fppSettings.override_ai=enabled;syncOverrideControls();try{const current=await api('/api/fpp/settings');fppSettings=await api('/api/fpp/settings',{...current,override_ai:enabled});}catch(err){fppSettings.override_ai=previous;$('#feature-result').textContent=err.message;}finally{overrideSaving=false;syncOverrideControls();}};host.append(label);}
      label.hidden=!fppSettings.enabled;const input=label.querySelector('input');input.checked=!!value;input.disabled=overrideSaving;
    }
  }
  function renderSettings(){
    syncOverrideControls();
    $('#feature-fpp').checked=!!fppSettings.enabled; fppCard.hidden=!fppSettings.enabled;
    const songLibrary=$('#fpp-song-library');if(songLibrary)songLibrary.hidden=!fppSettings.enabled;
    if($('#installation-profile'))$('#installation-profile').value=fppSettings.enabled?'fpp':'standard';$('#fpp-master').value=fppSettings.master_ip||'';$('#fpp-audible').checked=!!fppSettings.play_audio;

  }
  async function saveFpp(enabled){if(enabled){const resolved=await api('/api/fpp/resolve',{host:$('#fpp-master').value.trim()});$('#fpp-master').value=resolved.address;}fppSettings=await api('/api/fpp/settings',{...fppSettings,enabled,master_ip:$('#fpp-master').value.trim()||null,play_audio:$('#fpp-audible').checked});renderSettings();}
  $('#installation-profile').onchange=async e=>{const enabled=e.target.value==='fpp';fppCard.hidden=!enabled;if(enabled&&!fppSettings.master_ip){$('#fpp-audible').checked=true;$('#feature-fpp').checked=true;$('#fpp-save-result').textContent='Enter the Main FPP address and save to finish enabling FPP.';fppCard.scrollIntoView({behavior:'smooth',block:'center'});$('#fpp-master').focus();return;}try{await saveFpp(enabled);}catch(err){$('#fpp-save-result').textContent=err.message;renderSettings();}};
  $('#feature-fpp').onchange=async e=>{const enabled=e.target.checked;fppCard.hidden=!enabled;if(enabled&&!fppSettings.master_ip){$('#fpp-audible').checked=true;$('#fpp-master').focus();$('#fpp-save-result').textContent='Enter the Main FPP address, then save to enable.';return;}try{await saveFpp(enabled);}catch(err){$('#feature-result').textContent=err.message;renderSettings();}};
  $('#fpp-discover').onclick=async()=>{const button=$('#fpp-discover');button.disabled=true;$('#fpp-save-result').textContent='Looking for FPP players…';try{const found=await api('/api/fpp/discover');$('#fpp-discovered').replaceChildren(new Option('Choose Main FPP',''),...found.players.map(p=>new Option(`${p.hostname} · ${p.address}${p.sending_sync?' · sending sync':''}`,p.address)));$('#fpp-save-result').textContent=found.players.length?'Choose your Main player, then save.':'No players found. Enter the Main player address manually.';}catch(e){$('#fpp-save-result').textContent=e.message}finally{button.disabled=false}};
  $('#fpp-discovered').onchange=e=>{$('#fpp-master').value=e.target.value;};
  $('#fpp-feature-form').onsubmit=async e=>{e.preventDefault();try{await saveFpp(true);$('#fpp-save-result').textContent='FPP settings saved.';}catch(err){$('#fpp-save-result').textContent=err.message;}};
  function renderFppConnection(status){const configured=!!status.enabled&&!!status.configured;const label=!configured?'Not Setup':status.connected?'Connected':'Disconnected';const state=!configured?'off':status.connected?'ok':'error';const header=$('#header-fpp-status'),light=$('#fpp-status-light'),badge=$('#fpp-connected');if(header)header.textContent=label;if(light)light.className='status-light '+state;if(badge){badge.textContent='● '+label;badge.style.color=!configured?'var(--muted)':status.connected?'var(--green)':'var(--red)';}}
  async function poll(){if(busy)return;busy=true;try{const status=await api('/api/fpp/status');renderFppConnection(status);if(!overrideSaving){fppSettings.override_ai=status.override_ai;syncOverrideControls();}now.hidden=!(status.enabled&&status.playing&&status.local_match);if(!now.hidden){const seconds=Math.floor(status.position_seconds||0);now.textContent=`♫ FPP · Now playing · ${status.filename} · ${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;}if(status.playback_error||status.listener_error)$('#fpp-save-result').textContent=status.playback_error||status.listener_error;}catch{now.hidden=true;renderFppConnection({enabled:fppSettings.enabled,configured:!!fppSettings.master_ip,connected:false});}finally{busy=false;}}
  api('/api/fpp/settings').then(f=>{fppSettings=f;renderSettings();poll();}).catch(err=>$('#feature-result').textContent=err.message);
  setInterval(poll,2000);
})();
