'use strict';
// Native dialog supplies modal focus handling and Escape-key dismissal.
const imageDialog = document.getElementById('image-dialog');
const expandedImage = document.getElementById('image-expanded');
const caption = document.getElementById('image-caption');
let imageOpener;
for (const trigger of document.querySelectorAll('.image-open')) {
  trigger.addEventListener('click', () => {
    const source = trigger.querySelector('img');
    imageOpener = trigger;
    expandedImage.src = source.src;
    expandedImage.alt = source.alt;
    caption.textContent = source.alt;
    imageDialog.showModal();
    document.body.classList.add('image-modal-open');
    imageDialog.querySelector('.image-viewport').scrollTo(0, 0);
  });
}
document.getElementById('image-close').addEventListener('click', () => imageDialog.close());
imageDialog.addEventListener('click', (event) => {
  if (event.target !== imageDialog) return;
  const box = imageDialog.getBoundingClientRect();
  if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) {
    imageDialog.close();
  }
});
imageDialog.addEventListener('close', () => {
  document.body.classList.remove('image-modal-open');
  expandedImage.removeAttribute('src');
  imageOpener?.focus({preventScroll: true});
});
