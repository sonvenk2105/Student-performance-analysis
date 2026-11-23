document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.querySelector('.nav-toggle');
  toggle?.addEventListener('click', () => {
    const open = document.body.classList.toggle('nav-open');
    toggle.setAttribute('aria-expanded', String(open));
  });
  const rows = document.querySelector('#subject-rows');
  const syncMarkLimits = row => {
    const maximumInput = row.querySelector('[name="maximum[]"]');
    const obtainedInput = row.querySelector('[name="obtained[]"]');
    const passingInput = row.querySelector('[name="passing[]"]');
    const enteredMaximum = Number(maximumInput.value);
    const rowMaximum = Number.isFinite(enteredMaximum) && enteredMaximum > 0 ? Math.min(enteredMaximum, 100) : 100;
    obtainedInput.max = String(rowMaximum);
    passingInput.max = String(Math.min(rowMaximum, 40));
  };
  rows?.querySelectorAll('.subject-row').forEach(syncMarkLimits);
  document.querySelector('#add-row')?.addEventListener('click', () => {
    const first = rows.querySelector('.subject-row');
    const clone = first.cloneNode(true);
    clone.querySelectorAll('input').forEach(input => { input.value = ''; });
    syncMarkLimits(clone);
    rows.append(clone);
  });
  rows?.addEventListener('click', event => {
    if (event.target.matches('.remove-row')) {
      if (rows.querySelectorAll('.subject-row').length > 1) event.target.closest('.subject-row').remove();
    }
  });
  rows?.addEventListener('input', event => {
    if (event.target.matches('[name="maximum[]"], [name="obtained[]"], [name="passing[]"]')) syncMarkLimits(event.target.closest('.subject-row'));
  });
  rows?.addEventListener('change', event => {
    const row = event.target.closest('.subject-row');
    if (!event.target.matches('[name="subject[]"]')) return;
    const option = [...document.querySelectorAll('#catalog-subjects option')].find(item => item.value === event.target.value);
    if (!option) return;
    row.querySelector('[name="maximum[]"]').value = option.dataset.maximum || '';
    row.querySelector('[name="passing[]"]').value = option.dataset.passing || '';
    syncMarkLimits(row);
  });
  document.querySelector('#marks-form')?.addEventListener('submit', event => {
    const form = event.currentTarget;
    if (!form.reportValidity()) { event.preventDefault(); return; }
    const names = [...form.querySelectorAll('[name="subject[]"]')].map(e => e.value.trim().toLocaleLowerCase());
    if (new Set(names).size !== names.length) { event.preventDefault(); alert('Subject names must be unique.'); return; }
    const submit = form.querySelector('button[type="submit"],button:not([type])');
    if (submit) { submit.disabled = true; submit.textContent = submit.dataset.waitText || 'Analyzing…'; }
  });

  const accountDialog = document.querySelector('#account-dialog');
  const accountToggle = document.querySelector('#account-menu-toggle');
  accountToggle?.addEventListener('click', () => accountDialog?.showModal());
  accountDialog?.querySelector('[data-close-account]')?.addEventListener('click', () => accountDialog.close());
  accountDialog?.addEventListener('click', event => {
    if (event.target === accountDialog) accountDialog.close();
  });
});
