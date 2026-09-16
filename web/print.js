/* Print button for the report export page. A separate file rather than an
   inline onclick handler, which the Content Security Policy blocks. */
document.addEventListener('click', function (ev) {
  if (ev.target.id === 'printBtn') window.print();
});
