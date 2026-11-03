/* Official release checks are read-only; downloads never restart the app. */
(() => {
  'use strict';
  const find = id => document.getElementById(id);
  const checkButton = find('btn-check-update'), downloadButton = find('btn-download-update');
  const releaseButton = find('btn-open-release'), folderButton = find('btn-open-update-folder');
  const internalButton = find('btn-open-internal-release');
  const banner = find('app-update-banner'), status = find('app-update-status');
  const progressWrap = find('app-update-progress-wrap'), progress = find('app-update-progress');
  let release = null, checking = false, downloading = false, dismissed = false, started = false;
  let internalChannel = false;

  function ready() { return !!window.pywebview?.api; }
  function canDownload() { return !!(release?.available && release.can_download && release.supported !== false); }
  async function call(method) {
    if(!ready()) throw new Error('请在桌面程序中使用更新功能。');
    const result = await window.pywebview.api[method]();
    if(!result || result.ok === false || result.error) throw new Error(result?.error || '更新操作未能完成。');
    return result;
  }
  function sync() {
    checkButton.hidden = releaseButton.hidden = internalChannel;
    internalButton.hidden = !internalChannel;
    checkButton.disabled = !ready() || checking || downloading;
    releaseButton.disabled = !ready();
    downloadButton.hidden = !canDownload();
    downloadButton.disabled = checking || downloading;
    folderButton.disabled = downloading;
    checkButton.textContent = checking ? '检查中…' : '检查更新';
    downloadButton.textContent = downloading ? '下载中…' : '下载新版';
  }
  function message(text, error = false) {
    status.textContent = text;
    status.classList.toggle('err', error);
  }
  function render(info) {
    find('app-current-version').textContent = '当前版本：' + (info.current_version || '未读取');
    find('app-latest-version').textContent = '最新正式版本：' + (info.latest_version || '未读取');
    find('app-release-notes').textContent = info.release_notes || '该版本暂未提供更新说明。';
    find('app-release-details').hidden = !info.latest_version;
    const label = info.same_version ? '当前版本有补丁更新' : '发现新版 ' + info.latest_version;
    banner.hidden = !info.available || dismissed;
    find('app-update-banner-text').textContent = label + '，可在设置与帮助中查看。';
    message(info.reason || (info.available ? label + '。下载前可先查看更新说明。' : '未发现需要下载的正式版本更新。'));
    if(info.supported === false) message((info.reason || '') + (info.reason ? '\n' : '') + '当前运行环境不支持下载 Windows 更新包，可打开官方发布页查看。');
    sync();
  }
  async function check() {
    if(internalChannel || checking || downloading || !ready()) return;
    checking = true; release = null; banner.hidden = true;
    progressWrap.hidden = true; folderButton.hidden = true; find('app-release-details').hidden = true;
    find('app-latest-version').textContent = '最新版本：检查中…';
    message('正在连接官方 GitHub Release…'); sync();
    try {
      release = await call('check_app_update');
      if(!release.latest_version) throw new Error('未读取到有效的正式版本信息。');
      render(release);
    } catch(error) {
      release = null;
      find('app-latest-version').textContent = '最新版本：未能确认';
      message('检查失败：' + (error.message || error) + '\n可稍后重试或打开官方发布页。', true);
    } finally { checking = false; sync(); }
  }
  async function download() {
    if(checking || downloading || !canDownload() || !ready()) return;
    downloading = true; folderButton.hidden = true;
    progressWrap.hidden = false; progress.removeAttribute('value');
    find('app-update-progress-text').textContent = '等待选择保存位置';
    message('请选择新的保存位置。不会覆盖当前正在运行的程序。'); sync();
    let polling = false;
    const timer = setInterval(async () => {
      if(polling || !downloading) return;
      polling = true;
      try {
        const state = await call('app_update_status');
        if(!downloading || state.state !== 'downloading') return;
        const done = Math.max(0, Number(state.downloaded) || 0), total = Math.max(0, Number(state.total) || 0);
        if(total) progress.value = Math.min(100, done / total * 100);
        else progress.removeAttribute('value');
        find('app-update-progress-text').textContent = '已下载 ' + (done / 1048576).toFixed(1) + (total ? ' / ' + (total / 1048576).toFixed(1) : '') + ' MB';
      } catch(error) {
        // The download response remains authoritative if a progress read fails.
      } finally { polling = false; }
    }, 1000);
    try {
      const result = await call('download_app_update');
      if(result.cancelled) {
        progressWrap.hidden = true; message('已取消下载，当前程序和数据未改变。');
      } else {
        progress.value = 100; find('app-update-progress-text').textContent = '下载完成';
        folderButton.hidden = !result.path;
        message('下载完成' + (result.sha256 ? '，已通过 SHA-256 校验' : '') + '。\n' + (result.path || '') + '\n请先保存当前工作，再关闭旧版并启动下载的新版。车型数据和方案继续保留在原工作目录；自定义目录请沿用原启动参数。');
      }
    } catch(error) {
      progressWrap.hidden = true;
      message('下载失败：' + (error.message || error) + '\n可重试或从官方发布页下载。', true);
    } finally { clearInterval(timer); downloading = false; sync(); }
  }
  async function open(method) {
    try { await call(method); }
    catch(error) { message(error.message || String(error), true); }
  }
  checkButton.addEventListener('click', check);
  downloadButton.addEventListener('click', download);
  releaseButton.addEventListener('click', () => open('open_app_release_page'));
  internalButton.addEventListener('click', () => open('open_internal_release_page'));
  folderButton.addEventListener('click', () => open('open_app_update_folder'));
  find('btn-view-update').addEventListener('click', () => { showPage('settings'); find('app-update-heading').scrollIntoView({block:'start'}); });
  find('btn-dismiss-update').addEventListener('click', () => { dismissed = true; banner.hidden = true; });
  function start() {
    if(started || !ready()) return;
    started = true;
    if(window.pywebview.api.ping) {
      void call('ping').then(info => {
        if(info.version) find('app-current-version').textContent = '当前版本：' + info.version;
        internalChannel = !!info.has_internal_release_page;
        if(internalChannel) {
          find('app-update-description').textContent = '通过公司飞书更新页查看更新说明并下载新版。';
          find('app-latest-version').textContent = '更新渠道：公司飞书';
          message('点击“打开飞书更新页”，使用公司飞书账号下载。');
          sync();
        }
      }).catch(() => {}).finally(check);
    } else {
      void check();
    }
  }
  window.addEventListener('pywebviewready', start);
  if(ready()) start();
  else { message('在桌面程序中启动后自动检查；浏览器预览不会联网检查更新。'); sync(); }
})();
