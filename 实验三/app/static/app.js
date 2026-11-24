(() => {
  'use strict';
  const audio = document.getElementById('audio-engine');
  const panel = document.getElementById('music-player');
  const status = document.getElementById('player-status');
  const toggle = document.getElementById('player-toggle');
  const seek = document.getElementById('player-seek');
  const volume = document.getElementById('player-volume');
  const navStatus = document.getElementById('navigation-status');
  const lyricsPanel=document.getElementById('lyrics-panel'), lyricsBox=document.getElementById('lyrics-lines'), lyricsToggle=document.getElementById('player-lyrics');
  let lyricsLines=[], currentLyric=-1, lyricsRequest=0, lyricsAbort=null;
  let queue = [], index = -1, navigation = 0, writing = false, playRequest = 0;
  const time = seconds => Number.isFinite(seconds) ? `${Math.floor(seconds/60)}:${String(Math.floor(seconds%60)).padStart(2,'0')}` : '0:00';
  const track = () => queue[index];
  function markTrack() {
    document.querySelectorAll('.song-row').forEach(row => {
      const active = track() && Number(row.dataset.songId) === track().id;
      row.classList.toggle('is-playing', Boolean(active));
      const button = row.querySelector('[data-play-song]');
      if (button && !button.disabled) {
        button.textContent = active && !audio.paused ? 'Ⅱ' : '▶';
        button.setAttribute('aria-pressed', active && !audio.paused ? 'true' : 'false');
      }
    });
  }
  function controls() {
    toggle.textContent = audio.paused ? '播放' : '暂停';
    toggle.setAttribute('aria-label', audio.paused ? '播放' : '暂停');
    document.getElementById('player-prev').disabled = index <= 0;
    document.getElementById('player-next').disabled = index < 0 || index >= queue.length-1;
    markTrack();
  }
  function syncLyrics(force=false) {
    let low=0,high=lyricsLines.length-1,active=-1;
    while(low<=high){const mid=(low+high)>>1;if(lyricsLines[mid].time<=audio.currentTime){active=mid;low=mid+1;}else high=mid-1;}
    if(active===currentLyric&&!force)return;
    currentLyric=active;
    lyricsBox.querySelectorAll('[data-lyric-time]').forEach((line,i)=>{
      line.classList.toggle('current',i===active);
      if(i===active)line.setAttribute('aria-current','true');else line.removeAttribute('aria-current');
    });
    const line=lyricsBox.querySelector('[aria-current="true"]');
    if(line&&!lyricsPanel.hidden)lyricsBox.scrollTo({top:Math.max(0,line.offsetTop-lyricsBox.clientHeight/2+line.clientHeight/2),behavior:'smooth'});
  }
  function lyricsMessage(message){lyricsBox.replaceChildren();const p=document.createElement('p');p.className='muted lyrics-message';p.textContent=message;lyricsBox.append(p);}
  async function loadLyrics(item) {
    const generation=++lyricsRequest;
    if(lyricsAbort)lyricsAbort.abort();lyricsAbort=new AbortController();
    lyricsLines=[];currentLyric=-1;document.getElementById('lyrics-track').textContent=item.title;
    lyricsMessage('正在读取歌词…');
    try{
      const response=await fetch(`/api/songs/${item.id}/lyrics`,{signal:lyricsAbort.signal,credentials:'same-origin'});
      if(!response.ok)throw new Error('lyrics request failed');
      const data=await response.json();if(generation!==lyricsRequest)return;
      lyricsLines=data.lines;
      if(!lyricsLines.length){lyricsMessage('暂无歌词，音乐仍可正常播放。');return;}
      lyricsBox.replaceChildren();
      lyricsLines.forEach(cue=>{
        const button=document.createElement('button');button.type='button';button.className='lyric-line';button.dataset.lyricTime=String(cue.time);
        const original=document.createElement('span');original.textContent=cue.text||'♪';button.append(original);
        if(cue.translation){const translation=document.createElement('small');translation.textContent=cue.translation;button.append(translation);}
        lyricsBox.append(button);
      });
      syncLyrics(true);
    }catch(error){if(generation===lyricsRequest&&error.name!=='AbortError')lyricsMessage('歌词暂时不可用，请稍后重新选择歌曲。');}
  }
  lyricsToggle.addEventListener('click',()=>{lyricsPanel.hidden=!lyricsPanel.hidden;lyricsToggle.setAttribute('aria-expanded',String(!lyricsPanel.hidden));syncLyrics(true);});
  document.getElementById('lyrics-close').addEventListener('click',()=>{lyricsPanel.hidden=true;lyricsToggle.setAttribute('aria-expanded','false');});
  function stop() {
    lyricsRequest++; if(lyricsAbort)lyricsAbort.abort();lyricsLines=[];currentLyric=-1;lyricsPanel.hidden=true;lyricsToggle.setAttribute('aria-expanded','false');lyricsMessage('暂无歌词');
    playRequest++; audio.pause(); audio.removeAttribute('src'); audio.load(); queue=[]; index=-1;
    panel.hidden=true; document.body.classList.remove('has-player'); markTrack();
    if ('mediaSession' in navigator) navigator.mediaSession.metadata = null;
  }
  async function play() {
    if (!track()) return;
    const attempt=++playRequest, source=audio.src;
    try {
      await audio.play();
      if(attempt===playRequest && source===audio.src)status.textContent=`播放队列 ${index+1} / ${queue.length}`;
    } catch(error) {
      if(attempt!==playRequest || source!==audio.src || error.name==='AbortError')return;
      status.textContent='暂时无法播放，请点击播放重试；也可以选择其他歌曲。';
    }
    controls();
  }
  function load(at) {
    if (at<0 || at>=queue.length) return;
    index=at; const item=track();
    panel.hidden=false; document.body.classList.add('has-player');
    document.getElementById('player-title').textContent=item.title;
    document.getElementById('player-artist').textContent=item.artist;
    document.getElementById('player-current').textContent='0:00';
    document.getElementById('player-total').textContent='0:00'; seek.value=0;
    loadLyrics(item);
    audio.src=`/media/songs/${item.id}`; status.textContent='正在加载音频…';
    if ('mediaSession' in navigator && 'MediaMetadata' in window) navigator.mediaSession.metadata=new MediaMetadata({title:item.title,artist:item.artist});
    controls(); play();
  }
  toggle.addEventListener('click', () => audio.paused ? play() : audio.pause());
  document.getElementById('player-prev').addEventListener('click',()=>load(index-1));
  document.getElementById('player-next').addEventListener('click',()=>load(index+1));
  document.getElementById('player-close').addEventListener('click',stop);
  audio.addEventListener('play',controls); audio.addEventListener('pause',controls);
  audio.addEventListener('loadedmetadata',()=>{document.getElementById('player-total').textContent=time(Math.ceil(audio.duration));seek.disabled=!Number.isFinite(audio.duration);});
  audio.addEventListener('timeupdate',()=>{document.getElementById('player-current').textContent=time(audio.currentTime); if(Number.isFinite(audio.duration)&&audio.duration>0)seek.value=Math.round(audio.currentTime/audio.duration*1000);syncLyrics();});
  audio.addEventListener('ended',()=>{if(index+1<queue.length)load(index+1);else{status.textContent='这组歌曲已播放完毕。';controls();}});
  audio.addEventListener('error',()=>{if(track())status.textContent='音频加载失败，文件可能已被移除或格式不受当前浏览器支持。';controls();});
  seek.addEventListener('input',()=>{if(Number.isFinite(audio.duration))audio.currentTime=Number(seek.value)/1000*audio.duration;});
  audio.volume=0.7;
  try {const saved=Number(localStorage.getItem('tongpin-volume'));if(localStorage.getItem('tongpin-volume')!==null&&saved>=0&&saved<=1)audio.volume=saved;}catch{}
  volume.value=audio.volume;
  volume.addEventListener('input',()=>{audio.volume=Number(volume.value);try{localStorage.setItem('tongpin-volume',volume.value);}catch{}});
  if ('mediaSession' in navigator) {
    for(const [name,fn] of Object.entries({play, pause:()=>audio.pause(),previoustrack:()=>load(index-1),nexttrack:()=>load(index+1)}))try{navigator.mediaSession.setActionHandler(name,fn);}catch{}
  }

  // Replace the rendered content only. The single audio element remains mounted across navigation.
  async function navigate(url, options={}, historyMode='push') {
    const current=++navigation;
    navStatus.hidden=false;navStatus.textContent=options.method==='POST'?'正在保存，请稍候…':'正在加载…';
    try {
      const response=await fetch(url,{...options,credentials:'same-origin',headers:{'X-Tongpin-Navigation':'1'}});
      const html=await response.text();
      if(current!==navigation)return;
      const documentNext=new DOMParser().parseFromString(html,'text/html');
      const next=documentNext.getElementById('site-content');
      const old=document.getElementById('site-content');
      if(!next||!old)throw new Error('invalid response');
      if(old.dataset.userId!==next.dataset.userId)stop();
      // Saving a song on the current page must not move the listener back to the top.
      const samePage=new URL(response.url,location.href).pathname===location.pathname;
      const keepPosition=options.method==='POST' && samePage;
      const position=keepPosition?{left:window.scrollX,top:window.scrollY}:{left:0,top:0};
      const expanded=keepPosition?Array.from(old.querySelectorAll('details'),item=>item.open):[];
      const focusedSong=keepPosition && document.activeElement?.classList.contains('like')
        ? document.activeElement.closest('.song-row')?.dataset.songId : null;
      if(keepPosition)next.querySelectorAll('details').forEach((item,i)=>{
        if(i<expanded.length)item.open=expanded[i];
      });
      old.replaceWith(next);document.title=documentNext.title;
      if(historyMode==='push' && keepPosition)history.replaceState({},'',response.url);
      else if(historyMode==='push')history.pushState({},'',response.url);
      else if(historyMode==='replace')history.replaceState({},'',response.url);
      window.scrollTo({...position,behavior:'instant'});markTrack();
      const main=document.querySelector('main');main.setAttribute('tabindex','-1');
      const focusTarget=focusedSong?document.querySelector(`.song-row[data-song-id="${focusedSong}"] .like`):null;
      (focusTarget || main).focus({preventScroll:true});
      navStatus.hidden=true;
    } catch {
      if(current===navigation){navStatus.hidden=false;navStatus.textContent='页面加载失败，当前播放已保留。请检查连接后重试。';}
    }
  }
  document.addEventListener('click',async event=>{
    const lyric=event.target.closest('[data-lyric-time]');
    if(lyric){if(Number.isFinite(audio.duration)){audio.currentTime=Math.min(Number(lyric.dataset.lyricTime),audio.duration);syncLyrics(true);play();}return;}
    const pickerTrigger=event.target.closest('[data-add-to-playlist]');
    if(pickerTrigger){
      if(writing)return;
      const dialog=document.getElementById('playlist-picker');
      if(!dialog)return;
      const sid=Number(pickerTrigger.dataset.addToPlaylist);
      document.getElementById('playlist-picker-song').textContent=pickerTrigger.dataset.songTitle;
      const form=document.getElementById('playlist-picker-form');
      if(form){
        form.elements.song_id.value=String(sid); form.removeAttribute('action');
        const select=document.getElementById('playlist-picker-select');
        let available=0;
        Array.from(select.options).forEach(option=>{
          if(!option.value)return;
          const added=JSON.parse(option.dataset.songs).includes(sid);
          option.disabled=added;
          option.textContent=option.dataset.name+' · '+(option.dataset.visibility==='private'?'私密':'公开')+(added?' · 已收录':'');
          if(!added)available++;
        });
        select.value=''; document.getElementById('playlist-picker-submit').disabled=true;
        document.getElementById('playlist-picker-hint').textContent=available?'只显示你自己创建的歌单；已收录的歌单无需重复添加。':'这首歌已收录到你的所有歌单。';
      }
      dialog.showModal(); return;
    }
    if(event.target.closest('[data-close-picker]')){document.getElementById('playlist-picker').close();return;}
    const copy=event.target.closest('[data-copy]');
    if(copy){const target=document.getElementById('copy-status');try{await navigator.clipboard.writeText(copy.dataset.copy);target.textContent='分享链接已复制。';}catch{target.textContent='请复制链接：'+copy.dataset.copy;}return;}
    const add=event.target.closest('[data-add-artist]');
    if(add){const fields=document.getElementById('artist-fields');if(fields.children.length<20){const row=fields.firstElementChild.cloneNode(true);row.querySelector('input').value='';fields.append(row);}return;}
    const button=event.target.closest('[data-play-song]');
    if(button&&!button.disabled){
      const id=Number(button.dataset.playSong);
      if(track()?.id===id){audio.paused?play():audio.pause();return;}
      queue=Array.from(document.querySelectorAll('.song-row[data-playable="true"]')).map(row=>({id:Number(row.dataset.songId),title:row.querySelector('.song-name strong').textContent,artist:row.querySelector('.song-name>span').textContent}));
      load(queue.findIndex(item=>item.id===id));return;
    }
    const anchor=event.target.closest('a');
    if(!anchor||event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey||anchor.target||anchor.hasAttribute('download'))return;
    const target=new URL(anchor.href,location.href);
    if(target.origin!==location.origin||target.hash||!['http:','https:'].includes(target.protocol)||!anchor.closest('#site-content'))return;
    event.preventDefault();if(writing)return;
    navigate(target.href);
  });
  document.addEventListener('change',event=>{
    if(event.target.id!=='playlist-picker-select')return;
    const option=event.target.selectedOptions[0];
    const valid=option && option.value && !option.disabled;
    const form=document.getElementById('playlist-picker-form');
    if(valid)form.action=option.dataset.action;else form.removeAttribute('action');
    document.getElementById('playlist-picker-submit').disabled=!valid;
  });
  document.addEventListener('submit',event=>{
    const form=event.target;
    if(!form.closest('#site-content'))return;
    event.preventDefault();if(writing)return;
    if(form.id==='playlist-picker-form' && !form.hasAttribute('action'))return;
    if(form.dataset.confirm&&!confirm(form.dataset.confirm))return;
    const data=new FormData(form);
    if(form.method.toUpperCase()==='GET'){
      const target=new URL(form.action,location.href);target.search=new URLSearchParams(data).toString();navigate(target.href);return;
    }
    const buttons=Array.from(form.querySelectorAll('button'));buttons.forEach(button=>button.disabled=true);
    const note=form.querySelector('.form-status');if(note)note.textContent=form.enctype==='multipart/form-data'?'正在上传并校验，请稍候…':'正在保存…';
    writing=true;
    navigate(form.action,{method:'POST',body:data}).finally(()=>{writing=false;buttons.forEach(button=>button.disabled=false);});
  });
  window.addEventListener('popstate',()=>navigate(location.href,{},'none'));
  history.replaceState({},'',location.href);
})();
