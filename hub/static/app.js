'use strict';
const $ = (id) => document.getElementById(id);
const state = { csrf: null, selected: null, editing: null, trash: false, offset: 0, total: 0, limit: 30 };
const fields = ['title','artist','album','release_year','genre','subgenre','bpm','musical_key','time_signature','musical_version','description'];
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const assetUrl = (p,a) => `/api/v1/projects/${encodeURIComponent(p)}/assets/${encodeURIComponent(a)}/content`;

async function api(path, options={}) {
  const headers = {...(options.headers || {})};
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  if (options.method && !['GET','HEAD'].includes(options.method.toUpperCase())) headers['X-CSRF-Token'] = state.csrf || '';
  const resp = await fetch('/api/v1' + path, {...options, headers, credentials:'same-origin'});
  if (resp.status === 401 && path !== '/session/login') { showLogin(); throw new Error('Session expired; sign in again'); }
  if (!resp.ok) {
    let detail = `Request failed (${resp.status})`;
    try { const err = await resp.json(); detail = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail); } catch (_) { /* plain response */ }
    throw new Error(detail);
  }
  return resp.json();
}

let toastTimer;
function toast(message, error=false) {
  const el=$('toast'); el.textContent=message; el.className = 'visible' + (error ? ' error' : '');
  clearTimeout(toastTimer); toastTimer = setTimeout(()=>el.className='',4000);
}
function fail(error) { console.error(error); toast(error.message || String(error),true); }
function showLogin() { $('loginView').hidden=false; $('appView').hidden=true; state.csrf=null; }
function showApp() { $('loginView').hidden=true; $('appView').hidden=false; loadProjects().catch(fail); }

async function boot() {
  const session = await api('/session');
  if (session.authenticated) { state.csrf=session.csrf_token; showApp(); } else showLogin();
}

$('loginForm').addEventListener('submit',async(e)=>{
  e.preventDefault(); $('loginError').textContent='';
  try {
    const data=await api('/session/login',{method:'POST',body:JSON.stringify({password:e.target.password.value})});
    state.csrf=data.csrf_token; e.target.reset(); showApp();
  } catch(error) { $('loginError').textContent=error.message; }
});
$('logoutBtn').addEventListener('click',async()=>{try{await api('/session/logout',{method:'POST'});showLogin();}catch(error){fail(error);}});

function filters() {
  const params = new URLSearchParams({limit:String(state.limit),offset:String(state.offset),trash:String(state.trash)});
  for (const [id,key] of [['search','q'],['filterArtist','artist'],['filterGenre','genre'],['filterBpm','bpm']]) {
    if ($(id).value.trim()) params.set(key,$(id).value.trim());
  }
  return params.toString();
}
async function loadProjects() {
  const data=await api('/projects?'+filters());
  state.total=data.total;
  $('countText').textContent=`${data.total} ${state.trash?'trashed':'saved'} project${data.total===1?'':'s'}`;
  $('pageInfo').textContent=data.total ? `${state.offset+1}–${state.offset+data.items.length} of ${data.total}` : '';
  $('previousBtn').disabled=state.offset===0;
  $('nextBtn').disabled=state.offset+state.limit>=data.total;
  const grid=$('projects');
  grid.innerHTML = data.items.length ? data.items.map(p=>{
    const cover=p.cover_asset_id ? `<img loading="lazy" src="${assetUrl(p.id,p.cover_asset_id)}" alt="Artwork for ${escapeHtml(p.title)}">` : '♫';
    return `<article class="project-card" data-project="${p.id}" tabindex="0" role="button" aria-label="Open ${escapeHtml(p.title)}"><div class="cover">${cover}</div><h3>${escapeHtml(p.title)}</h3><p>${escapeHtml(p.artist||'Unknown artist')} · ${escapeHtml(p.album||'Unreleased')}</p><div class="tags"><span class="tag">${escapeHtml(p.bpm)} BPM</span><span class="tag">${escapeHtml(p.genre||'Uncategorized')}</span><span class="tag">r${p.revision}</span></div></article>`;
  }).join('') : `<div class="empty"><h3>${state.trash?'Trash is empty':'No projects found'}</h3><p>${state.trash?'Deleted projects can be restored here.':'Create a project or adjust the filters.'}</p></div>`;
  grid.querySelectorAll('[data-project]').forEach(card=>{
    const open=()=>openProject(card.dataset.project).catch(fail);
    card.addEventListener('click',open);
    card.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}});
  });
}
function setTrash(enabled){state.trash=enabled;state.offset=0;$('libraryNav').classList.toggle('active',!enabled);$('trashNav').classList.toggle('active',enabled);$('pageTitle').textContent=enabled?'Trash':'Your library';$('newBtn').hidden=enabled;loadProjects().catch(fail);}
$('libraryNav').onclick=()=>setTrash(false);
$('trashNav').onclick=()=>setTrash(true);
$('searchBtn').onclick=()=>{state.offset=0;loadProjects().catch(fail);};
$('clearBtn').onclick=()=>{for(const id of ['search','filterArtist','filterGenre','filterBpm'])$(id).value='';state.offset=0;loadProjects().catch(fail);};
$('search').onkeydown=e=>{if(e.key==='Enter'){state.offset=0;loadProjects().catch(fail);}};
$('previousBtn').onclick=()=>{state.offset=Math.max(0,state.offset-state.limit);loadProjects().catch(fail);};
$('nextBtn').onclick=()=>{state.offset+=state.limit;loadProjects().catch(fail);};

function editProject(project=null){
  state.editing=project;
  $('editHeading').textContent=project?'Edit metadata':'Create project';
  $('editForm').reset();
  const defaults={title:'',artist:'',album:'',release_year:'',genre:'',subgenre:'',bpm:120,musical_key:'C major',time_signature:'4/4',musical_version:'Demo',description:''};
  for(const key of fields) $('editForm').elements.namedItem(key).value=project?.[key] ?? defaults[key];
  $('editDialog').showModal();
}
$('newBtn').onclick=()=>editProject();
$('closeEdit').onclick=()=>$('editDialog').close();
$('cancelEdit').onclick=()=>$('editDialog').close();
$('editForm').addEventListener('submit',async e=>{
  e.preventDefault();
  const data=Object.fromEntries(fields.map(k=>[k,e.target.elements.namedItem(k).value]));
  data.bpm=Number(data.bpm); data.release_year=data.release_year?Number(data.release_year):null;
  try{
    if(state.editing){
      const result=await api(`/projects/${state.editing.id}/metadata`,{method:'PATCH',body:JSON.stringify({expected_revision:state.editing.revision,metadata:data})});
      state.selected=result;
    }else{
      await api('/projects',{method:'POST',body:JSON.stringify(data)});
    }
    $('editDialog').close();toast('Project saved');await loadProjects();
    if(state.editing) await openProject(state.editing.id);
  }catch(error){fail(error);}
});

async function openProject(id){
  // Trash list has deliberately restricted actions; fetch is only for active projects.
  if(state.trash){
    if(!confirm('Restore this project from trash?'))return;
    await api(`/projects/${id}/restore`,{method:'POST'}); toast('Project restored'); await loadProjects();return;
  }
  const p=await api(`/projects/${id}`);state.selected=p;
  $('detailTitle').textContent=p.title;
  $('detailSubtitle').textContent=[p.artist,p.album,p.musical_version].filter(Boolean).join(' · ') || 'Unreleased';
  $('detailMeta').innerHTML=[`${p.bpm} BPM`,p.musical_key,p.time_signature,p.genre||'Uncategorized',`Revision ${p.revision}`].map(v=>`<span class="tag">${escapeHtml(v)}</span>`).join('');
  $('assetList').innerHTML=p.assets.length?p.assets.map(a=>`<div class="asset-row"><div class="file-meta"><strong>${escapeHtml(a.filename)}</strong><small>${escapeHtml(a.kind.toUpperCase())} · ${(a.size/1024).toFixed(1)} KB</small></div><div class="row-actions"><a href="${assetUrl(p.id,a.id)}">Download</a><button data-remove-asset="${a.id}" aria-label="Remove ${escapeHtml(a.filename)}">Remove</button></div></div>`).join(''):'<p class="muted">No uploaded files yet.</p>';
  $('assetList').querySelectorAll('[data-remove-asset]').forEach(button=>button.onclick=()=>removeAsset(button.dataset.removeAsset));
  const rev=await api(`/projects/${id}/revisions`);
  $('revisionList').innerHTML=rev.items.map(r=>`<div class="revision-row"><span>Revision ${r.number} <span class="muted">· ${escapeHtml(new Date(r.created_at).toLocaleString())}</span></span>${r.number===p.revision?'<span class="tag">Current</span>':`<button data-revision="${r.number}">Restore</button>`}</div>`).join('');
  $('revisionList').querySelectorAll('[data-revision]').forEach(button=>button.onclick=()=>restoreRevision(Number(button.dataset.revision)));
  $('uploadForm').reset();$('detailDialog').showModal();
}
$('closeDetail').onclick=()=>$('detailDialog').close();
$('editProject').onclick=()=>{$('detailDialog').close();editProject(state.selected);};
$('deleteProject').onclick=async()=>{
  const p=state.selected;
  if(!p||!confirm(`Move "${p.title}" to trash?`))return;
  try{await api(`/projects/${p.id}`,{method:'DELETE',body:JSON.stringify({expected_revision:p.revision})});$('detailDialog').close();toast('Moved to trash');await loadProjects();}catch(error){fail(error);}
};
$('uploadForm').addEventListener('submit',async e=>{
  e.preventDefault();const p=state.selected;if(!p)return;
  const form=new FormData(e.target);form.append('expected_revision',String(p.revision));
  try{await api(`/projects/${p.id}/assets`,{method:'POST',body:form});toast('File uploaded');await openProject(p.id);await loadProjects();}catch(error){fail(error);}
});
async function removeAsset(id){
  const p=state.selected;if(!p||!confirm('Remove this file from the current revision? Older revisions will retain it.'))return;
  try{await api(`/projects/${p.id}/assets/${id}`,{method:'DELETE',body:JSON.stringify({expected_revision:p.revision})});toast('File removed');await openProject(p.id);await loadProjects();}catch(error){fail(error);}
}
async function restoreRevision(number){
  const p=state.selected;if(!p||!confirm(`Restore revision ${number} as a new revision?`))return;
  try{await api(`/projects/${p.id}/revisions/${number}/restore`,{method:'POST',body:JSON.stringify({expected_revision:p.revision})});toast('Revision restored');await openProject(p.id);await loadProjects();}catch(error){fail(error);}
}
$('documentBtn').onclick=()=>{$('manifestInput').value=JSON.stringify(state.selected.manifest,null,2);$('documentDialog').showModal();};
$('closeDocument').onclick=()=>$('documentDialog').close();
$('cancelDocument').onclick=()=>$('documentDialog').close();
$('documentForm').addEventListener('submit',async e=>{
  e.preventDefault();const p=state.selected;if(!p)return;
  try{
    const manifest=JSON.parse($('manifestInput').value);
    await api(`/projects/${p.id}/document`,{method:'PUT',body:JSON.stringify({expected_revision:p.revision,manifest})});
    $('documentDialog').close();toast('Manifest saved as new revision');await openProject(p.id);await loadProjects();
  }catch(error){fail(error);}
});
boot().catch(fail);
