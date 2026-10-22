/* ShiftGrid — клиентский код без зависимостей. */
(function () {
  'use strict';

  // HTML5-валидация с подсветкой Bootstrap и подтверждение опасных действий (data-confirm).
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (form.classList.contains('needs-validation') && !form.checkValidity()) {
      event.preventDefault();
      event.stopPropagation();
      form.classList.add('was-validated');
      return;
    }
    var message = form.getAttribute('data-confirm');
    if (message && !window.confirm(message)) {
      event.preventDefault();
    }
  });

  // Поле «повторите пароль»: data-match="id исходного поля".
  document.querySelectorAll('[data-match]').forEach(function (field) {
    var source = document.getElementById(field.getAttribute('data-match'));
    function check() {
      field.setCustomValidity(field.value && field.value !== source.value ? 'Пароли не совпадают' : '');
    }
    source.addEventListener('input', check);
    field.addEventListener('input', check);
  });

  // Фильтры, которые применяются сразу при выборе.
  document.querySelectorAll('[data-autosubmit]').forEach(function (select) {
    select.addEventListener('change', function () { select.form.submit(); });
  });

  // Быстрый вход в демо-аккаунт.
  var loginForm = document.getElementById('loginForm');
  document.querySelectorAll('[data-demo-username]').forEach(function (button) {
    button.addEventListener('click', function () {
      loginForm.elements.namedItem('username').value = button.getAttribute('data-demo-username');
      loginForm.elements.namedItem('password').value = button.getAttribute('data-demo-password');
      loginForm.submit();
    });
  });

  initShiftForm();

  function initShiftForm() {
    var form = document.getElementById('shiftForm');
    if (!form) { return; }
    var MAX_MINUTES = 16 * 60;
    var start = document.getElementById('start_time');
    var end = document.getElementById('end_time');
    var overnight = document.getElementById('overnight');
    var hint = document.getElementById('durationHint');
    var feedback = document.getElementById('endFeedback');
    var employee = document.getElementById('user_id');
    var position = document.getElementById('position');

    function toMinutes(value) {
      var parts = value.split(':');
      return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
    }

    function validateTime() {
      end.setCustomValidity('');
      if (!start.value || !end.value) {
        hint.textContent = '';
        feedback.textContent = 'Укажите время окончания.';
        return;
      }
      var diff = toMinutes(end.value) - toMinutes(start.value);
      var error = '';
      if (diff === 0) {
        error = 'Время начала и окончания совпадают.';
      } else if (diff < 0 && !overnight.checked) {
        error = 'Окончание раньше начала. Если смена ночная — отметьте «Смена через полночь».';
      } else if (diff > 0 && overnight.checked) {
        error = 'Отмечено «через полночь», но окончание позже начала.';
      }
      if (diff <= 0) { diff += 24 * 60; }
      if (!error && diff > MAX_MINUTES) {
        error = 'Смена не может длиться дольше 16 часов.';
      }
      end.setCustomValidity(error);
      feedback.textContent = error || 'Укажите время окончания.';
      hint.className = 'form-text mb-3 ' + (error ? 'text-danger' : 'text-success');
      if (error) {
        hint.textContent = error;
      } else {
        var minutes = diff % 60;
        hint.textContent = 'Длительность: ' + Math.floor(diff / 60) + ' ч' + (minutes ? ' ' + minutes + ' мин' : '');
      }
    }

    start.addEventListener('input', validateTime);
    end.addEventListener('input', validateTime);
    overnight.addEventListener('change', validateTime);

    document.querySelectorAll('.time-preset').forEach(function (button) {
      button.addEventListener('click', function () {
        start.value = button.getAttribute('data-start');
        end.value = button.getAttribute('data-end');
        overnight.checked = toMinutes(end.value) <= toMinutes(start.value);
        validateTime();
      });
    });

    // При выборе сотрудника подставляем его должность, если её не меняли вручную.
    function defaultPosition() {
      var option = employee.options[employee.selectedIndex];
      return option ? option.getAttribute('data-position') || '' : '';
    }
    var lastDefault = defaultPosition();
    employee.addEventListener('change', function () {
      var next = defaultPosition();
      if (!position.value || position.value === lastDefault) {
        position.value = next;
      }
      lastDefault = next;
    });

    validateTime();
  }
})();
