(() => {
  const $ = id => document.getElementById(id);
  let busy = false;
  const status = message => { $('batch5r-status').textContent = message; };
  async function api(url, options) {
    const response = await fetch(url, options), data = await response.json();
    if (!response.ok) throw Error(data.error || '讀取失敗');
    return data;
  }
  function lock(value) {
    busy = value;
    for (const id of ['batch5r-start', 'batch5r-pick', 'batch5r-folder', 'batch5r-machine']) $(id).disabled = value;
  }
  async function poll(id) {
    try {
      const job = await api('/api/5r/batches/' + id);
      $('batch5r-folder').value = job.folder;
      $('batch5r-machine').value = job.machine.id;
      $('batch5r-progress').max = Math.max(1, job.total);
      $('batch5r-progress').value = job.completed;
      status(`已處理 ${job.completed} / ${job.total} 張` + (job.current ? ' · ' + job.current : ''));
      if (job.state === 'running' || job.state === 'reporting') {
        if (job.state === 'reporting') status('照片處理完成，正在產出並核對完整報表…');
        setTimeout(() => poll(id), 1500);
        return;
      }
      lock(false);
      if (job.state !== 'done') throw Error(job.error || '批次未完成');
      const s = job.summary;
      status(`完成：NG 未檢出 ${s.ng_missed} 張；OK 誤報 ${s.ok_false_alarm} 張；處理失敗 ${s.errors} 張；參照自比 ${s.reference_self} 張。`);
      $('batch5r-report').href = job.report; $('batch5r-report').hidden = false;
    } catch (error) { lock(false); status(error.message + '（重新整理可讀取此批進度）'); }
  }
  $('batch5r-pick').onclick = async () => {
    const path = await window.pickXRayFolder($('batch5r-folder').value);
    if (path) $('batch5r-folder').value = path;
  };
  $('batch5r-form').onsubmit = async event => {
    event.preventDefault(); if (busy) return; lock(true); $('batch5r-report').hidden = true;
    status('正在確認資料夾及模型…');
    try {
      const job = await api('/api/5r/batches', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({folder:$('batch5r-folder').value.trim(), machine_id:$('batch5r-machine').value})});
      history.replaceState(null, '', '/5r/batch?job=' + job.id); poll(job.id);
    } catch (error) { lock(false); status(error.message); }
  };
  lock(true);
  api('/api/machines').then(data => {
    for (const machine of data.items.filter(m => m.ready)) {
      const option = document.createElement('option'); option.value = machine.id;
      option.textContent = machine.name + ' · ' + machine.reference_name;
      option.selected = machine.id === data.selected; $('batch5r-machine').append(option);
    }
    const id = new URLSearchParams(location.search).get('job');
    if (id) poll(id); else lock(false);
  }).catch(error => status(error.message));
})();
