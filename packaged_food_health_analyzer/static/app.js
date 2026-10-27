const input = document.getElementById('label_image');
if (input) {
  input.addEventListener('change', () => {
    const file = input.files && input.files[0];
    if (!file) return;
    document.getElementById('file-title').textContent = file.name;
    document.getElementById('file-subtitle').textContent = `${(file.size / (1024 * 1024)).toFixed(2)} MB selected`;
    const wrap = document.getElementById('preview-wrap');
    const preview = document.getElementById('image-preview');
    preview.src = URL.createObjectURL(file);
    document.getElementById('preview-name').textContent = 'Preview of selected label';
    wrap.hidden = false;
  });
  const dropzone = document.querySelector('.dropzone');
  ['dragenter', 'dragover'].forEach(evt => dropzone.addEventListener(evt, e => { e.preventDefault(); dropzone.classList.add('dragging'); }));
  ['dragleave', 'drop'].forEach(evt => dropzone.addEventListener(evt, e => { e.preventDefault(); dropzone.classList.remove('dragging'); }));
  dropzone.addEventListener('drop', e => { if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; input.dispatchEvent(new Event('change')); } });
}
