/* Shared behaviour for the research pages: the status modal, the delete
   modal and the small helpers they rely on. */
(function () {
    'use strict';

    const STATUS_META = (function () {
        const node = document.getElementById('status-colors');
        const colors = {};
        if (node) {
            try {
                Object.assign(colors, JSON.parse(node.textContent));
            } catch (e) {
                /* ignore malformed json */
            }
        }
        return {
            active: { label: 'Active', color: colors.active || '#e25252' },
            paused: { label: 'Paused', color: colors.paused || '#e2c452' },
            finished: { label: 'Finished', color: colors.finished || '#52c48a' },
        };
    })();

    window.RESEARCH_STATUS_META = STATUS_META;

    /* The CSRF token is read from the page instead of a javascript variable:
       a `const` in a script block is not a property of `window`, so relying on
       one silently sends an empty token and every post is rejected with a 403. */
    function getCookie(name) {
        if (!document.cookie) return null;
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                return decodeURIComponent(cookie.substring(name.length + 1));
            }
        }
        return null;
    }

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.getAttribute('content')) return meta.getAttribute('content');
        return getCookie('csrftoken') || '';
    }

    window.escapeHtml = function (value) {
        const div = document.createElement('div');
        div.textContent = value === undefined || value === null ? '' : String(value);
        return div.innerHTML;
    };

    window.postResearch = async function (url, fields) {
        const body = new URLSearchParams();
        Object.keys(fields).forEach(function (key) {
            if (Array.isArray(fields[key])) {
                fields[key].forEach(function (value) { body.append(key, value); });
            } else {
                body.append(key, fields[key]);
            }
        });
        const token = csrfToken();
        body.append('csrfmiddlewaretoken', token);
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': token,
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: body.toString(),
        });
        let data = null;
        try {
            data = await response.json();
        } catch (e) {
            data = null;
        }
        return { ok: response.ok, data: data };
    };

    /* ------------------------------------------------- status modal ------ */
    function openStatusModal(badge) {
        const id = badge.dataset.id;
        const current = badge.dataset.status;
        const options = Object.keys(STATUS_META).map(function (key) {
            const meta = STATUS_META[key];
            const selected = key === current ? ' checked' : '';
            return '<span class="status-option' + selected + '" data-status="' + key +
                '" style="--status-color: ' + meta.color + '; --status-bg: ' + meta.color + '22">' +
                '<span class="status-dot"></span>' + meta.label + '</span>';
        }).join('');

        showModal('Change Status', `
            <p class="modal-hint">Pick a status for <strong>${escapeHtml(badge.dataset.acronym || '')}</strong>.</p>
            <div class="status-picker" id="status-picker">${options}</div>
        `, [
            { text: 'Cancel', className: 'modal-btn' },
            {
                text: 'Save',
                className: 'modal-btn modal-btn-primary',
                callback: async () => {
                    const picked = document.querySelector('#status-picker .status-option.checked');
                    const value = picked ? picked.dataset.status : current;
                    if (!value || value === current) return;
                    try {
                        const result = await postResearch(RESEARCH_UPDATE_URL, { id: id, status: value });
                        if (result.ok) {
                            // the colour follows the data-status attribute
                            // through the css, so the badge repaints itself
                            badge.dataset.status = value;
                            badge.querySelector('.status-label').textContent = STATUS_META[value].label;
                        } else {
                            showModal('Error', escapeHtml((result.data && result.data.error) || 'Failed to update status'));
                        }
                    } catch (err) {
                        showModal('Error', 'An error occurred');
                    }
                }
            }
        ]);
    }

    document.addEventListener('click', function (e) {
        const badge = e.target.closest ? e.target.closest('.status-badge') : null;
        if (!badge) return;
        e.stopPropagation();
        openStatusModal(badge);
    });

    /* ------------------------------------------------- delete modal ------ */
    document.addEventListener('click', function (e) {
        const btn = e.target.closest ? e.target.closest('.research-delete') : null;
        if (!btn) return;
        e.stopPropagation();
        const id = btn.dataset.id;
        showModal('Confirm Delete', 'Are you sure you want to delete this research project?', [
            { text: 'Cancel', className: 'modal-btn' },
            {
                text: 'Delete',
                className: 'modal-btn modal-btn-danger',
                callback: async () => {
                    try {
                        const result = await postResearch(RESEARCH_DELETE_URL, { id: id });
                        if (result.ok) {
                            window.location.reload();
                        } else {
                            showModal('Error', escapeHtml((result.data && result.data.error) || 'Failed to delete project'));
                        }
                    } catch (err) {
                        showModal('Error', 'An error occurred');
                    }
                }
            }
        ]);
    });

    /* --------------------------------------- status options in modals --- */
    document.addEventListener('click', function (e) {
        const option = e.target.closest ? e.target.closest('.status-option') : null;
        if (!option) return;
        e.preventDefault();
        const picker = option.parentElement;
        if (!picker) return;
        picker.querySelectorAll('.status-option').forEach(function (o) {
            o.classList.remove('checked');
        });
        option.classList.add('checked');
    });

    /* ------------------------------------------------- delete modal ----- */
    /* Any form with data-confirm asks for confirmation in the site modal
       instead of the browser alert. */
    document.addEventListener('submit', function (e) {
        const form = e.target.closest ? e.target.closest('form[data-confirm]') : null;
        if (!form) return;
        e.preventDefault();
        const message = form.dataset.confirm || 'Are you sure you want to delete this?';
        showModal('Confirm Delete', message, [
            { text: 'Cancel', className: 'modal-btn' },
            {
                text: 'Delete',
                className: 'modal-btn modal-btn-danger',
                callback: function () {
                    // submit() does not fire the submit event again, so the
                    // form goes straight to the server
                    form.submit();
                },
            },
        ]);
    });
})();
