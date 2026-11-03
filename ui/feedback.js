/* Public GitHub feedback is prepared locally; only the user submits it. */
(() => {
  'use strict';
  const maxImage = 5 * 1024 * 1024, maxTotal = 10 * 1024 * 1024;
  let dialog, images = [], busy = false, reading = false, prepared = null;
  const el = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const call = async (method, ...args) => {
    if (!window.pywebview?.api?.[method]) throw new Error('请在程序中使用反馈窗口；浏览器预览无法保存反馈。');
    const result = await window.pywebview.api[method](...args);
    if (!result || result.ok === false || result.error) throw new Error(result?.error || '操作未完成，请重试。');
    return result;
  };
  let title, description, input, previews, consent, state, submit, add, copy, folder;
  function message(text, error = false) { state.textContent = text; state.dataset.error = String(error); }
  function sync() {
    submit.disabled = busy || reading || !consent.checked || !title.value.trim() || (!description.value.trim() && !images.length);
    add.disabled = busy || reading || images.length >= 3;
    title.disabled = description.disabled = consent.disabled = busy;
    copy.hidden = folder.hidden = !prepared;
    copy.disabled = folder.disabled = busy;
  }
  function changed() { prepared = null; consent.checked = false; message(''); sync(); }
  function renderImages() {
    previews.replaceChildren(...images.map((image, index) => {
      const figure = el('figure', '', 'feedback-image'), preview = el('img');
      preview.src = image.data_url; preview.alt = '待上传截图' + (index + 1);
      const remove = el('button', '移除'); remove.type = 'button';
      remove.disabled = busy; remove.addEventListener('click', () => { images.splice(index, 1); renderImages(); changed(); });
      figure.append(preview, el('figcaption', image.name), remove); return figure;
    }));
  }
  async function selectImages() {
    const files = [...input.files]; input.value = '';
    if (!files.length) return;
    if (images.length + files.length > 3) return message('最多添加3张截图，请移除后重试。', true);
    if (files.some(file => !['image/png', 'image/jpeg'].includes(file.type) || file.size > maxImage)) return message('截图仅支持PNG/JPEG，单张不超过5MB。', true);
    if (images.reduce((sum, image) => sum + image.size, 0) + files.reduce((sum, file) => sum + file.size, 0) > maxTotal) return message('截图总大小不能超过10MB。', true);
    reading = true; sync();
    try {
      const added = await Promise.all(files.map(file => new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve({name:file.name, size:file.size, data_url:reader.result});
        reader.onerror = () => reject(new Error('截图读取失败，请重新选择。'));
        reader.readAsDataURL(file);
      })));
      images.push(...added); renderImages(); changed();
    } catch (error) { message(error.message, true); }
    finally { reading = false; sync(); }
  }
  async function copyBody() {
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(prepared.body);
      else {
        const field = el('textarea'); field.value = prepared.body; dialog.append(field); field.select();
        try { if (!document.execCommand('copy')) throw new Error('无法访问剪贴板'); }
        finally { field.remove(); }
      }
      message('已复制完整反馈正文，请在GitHub页面粘贴；截图仍需单独上传。');
    } catch (_) { message('未能复制。可打开反馈文件夹，从“反馈说明.md”复制文字。', true); }
  }
  function mount() {
    if (dialog) return;
    dialog = el('dialog'); dialog.id = 'feedback-dialog'; dialog.setAttribute('aria-labelledby', 'feedback-title');
    const content = el('div', '', 'feedback-content'), heading = el('div', '', 'feedback-heading');
    const h = el('h2', '反馈使用情况'); h.id = 'feedback-title';
    const close = el('button', '关闭'); close.type = 'button'; close.addEventListener('click', () => { if (!busy) dialog.close(); });
    heading.append(h, close);
    content.append(heading, el('p', '反馈将发布到公开 GitHub Issues，任何人都可能查看。请删除内部产品资料、个人信息和不希望公开的内容。程序不会自动提交或上传截图。', 'feedback-public'));
    const titleLabel = el('label', '反馈标题（必填）', 'feedback-field');
    title = el('input'); title.type = 'text'; title.maxLength = 120; title.placeholder = '例如：修改座椅配置后显示异常'; titleLabel.append(title);
    const bodyLabel = el('label', '反馈说明（也可只添加截图）', 'feedback-field');
    description = el('textarea'); description.maxLength = 10000; description.placeholder = '请描述操作步骤、期望结果和实际情况。不要填写密码、令牌或内部敏感资料。'; bodyLabel.append(description);
    content.append(titleLabel, bodyLabel);
    const actions = el('div', '', 'feedback-actions'); add = el('button', '添加截图'); add.type = 'button';
    input = el('input'); input.type = 'file'; input.accept = 'image/png,image/jpeg'; input.multiple = true; input.hidden = true;
    add.addEventListener('click', () => input.click()); input.addEventListener('change', selectImages);
    actions.append(add, input); content.append(actions, el('p', '最多3张PNG/JPEG；单张≤5MB，总计≤10MB。添加后只在本机预览，提交时请在GitHub页面拖入或粘贴上传。', 'feedback-hint'));
    previews = el('div', '', 'feedback-images'); content.append(previews);
    const confirm = el('label', '', 'feedback-confirm'); consent = el('input'); consent.type = 'checkbox'; confirm.append(consent, el('span', '我已确认文字和截图可以公开，并将在GitHub页面核对后提交。')); content.append(confirm);
    const submitActions = el('div', '', 'feedback-actions'); submit = el('button', '准备反馈并前往GitHub'); submit.type = 'button'; submit.className = 'primary';
    copy = el('button', '复制反馈正文'); copy.type = 'button'; copy.addEventListener('click', copyBody);
    folder = el('button', '打开反馈文件夹'); folder.type = 'button'; folder.addEventListener('click', async () => { try { await call('open_feedback_folder'); } catch (error) { message(error.message, true); } });
    submitActions.append(submit, copy, folder); content.append(submitActions);
    state = el('p', '', 'feedback-state'); state.setAttribute('role', 'status'); state.setAttribute('aria-live', 'polite'); content.append(state);
    dialog.append(content); document.body.append(dialog);
    [title, description].forEach(field => field.addEventListener('input', changed)); consent.addEventListener('change', sync);
    dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
    submit.addEventListener('click', async () => {
      if (submit.disabled) return;
      busy = true; sync(); renderImages(); message('正在本地准备反馈…');
      try {
        prepared = await call('prepare_feedback', {title:title.value.trim(), description:description.value.trim(), images:images.map(({name, data_url}) => ({name, data_url}))});
        await call('open_feedback_issue');
        message(prepared.requires_paste ? '已打开GitHub，尚未提交。正文较长，请先“复制反馈正文”并粘贴到网页，再上传截图并提交。' : prepared.has_images ? '已打开GitHub，尚未提交。请“打开反馈文件夹”，将截图拖入GitHub页面后确认提交。' : '已打开GitHub，尚未提交。请在网页核对文字并提交。');
      } catch (error) { message(error.message, true); }
      finally { busy = false; sync(); renderImages(); }
    });
    sync();
  }
  window.CarkitFeedback = {open() { mount(); if (!dialog.open) { consent.checked = false; sync(); dialog.showModal(); title.focus(); } }};
  ['btn-open-feedback', 'btn-open-feedback-sidebar'].forEach(id => {
    document.getElementById(id)?.addEventListener('click', () => window.CarkitFeedback.open());
  });
})();
