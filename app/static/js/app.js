/* Baymax — small shared behaviours. No inline handlers anywhere in the templates. */
(function () {
  'use strict';

  // Show / hide a password field: <button data-toggle-password="field-id">
  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-toggle-password]');
    if (!button) { return; }
    var input = document.getElementById(button.getAttribute('data-toggle-password'));
    if (!input) { return; }
    var reveal = input.type === 'password';
    input.type = reveal ? 'text' : 'password';
    button.textContent = reveal ? 'Hide' : 'Show';
    button.setAttribute('aria-pressed', reveal ? 'true' : 'false');
    button.setAttribute('aria-label', (reveal ? 'Hide' : 'Show') + ' password');
  });
})();