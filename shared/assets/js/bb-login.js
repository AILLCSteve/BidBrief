/* Login page behaviour: mount the orb, surface the ?error= reason, and block
   an empty submit before it round-trips. */
(function (window) {
  'use strict';
  var document = window.document;

  var MESSAGES = {
    invalid: 'Invalid username or password. Please try again.',
    session: 'Your session has expired. Please log in again.'
  };

  document.addEventListener('DOMContentLoaded', function () {
    window.BB.orb.mount(document.getElementById('bb-orb'));

    var box = document.getElementById('errorMessage');
    var error = new window.URLSearchParams(window.location.search).get('error');
    if (error) {
      box.textContent = MESSAGES[error] || 'An error occurred. Please try again.';
      box.classList.add('show');
    }

    document.getElementById('loginForm').addEventListener('submit', function (e) {
      var user = document.getElementById('username').value.trim();
      var pass = document.getElementById('password').value;
      if (user && pass) return;
      e.preventDefault();
      box.textContent = 'Please enter both username and password.';
      box.classList.add('show');
    });
  });
})(window);
