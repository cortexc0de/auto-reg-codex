/**
 * Почтовые ящики — клиентская логика
 */

let currentService = null;
let mailboxes = [];
let selectedMailboxId = null;

// ============================================
// Инициализация
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    loadServices();
});

// ============================================
// Загрузка сервисов
// ============================================

async function loadServices() {
    try {
        const data = await api.get('/mailbox/services');
        const services = data.services || [];
        renderServiceTabs(services);

        const enabled = services.find(s => s.enabled);
        if (enabled) {
            selectService(enabled.name);
        }
    } catch (e) {
        toast.error('Ошибка загрузки сервисов');
    }
}

function renderServiceTabs(services) {
    const container = document.getElementById('service-tabs');
    container.innerHTML = services.map(s => {
        const disabledClass = s.enabled ? '' : ' disabled';
        const disabledAttr = s.enabled ? '' : ' disabled';
        return `<button class="tab-btn${disabledClass}" id="tab-${s.name}" onclick="selectService('${s.name}')"${disabledAttr}>
            ${s.label} ${s.enabled ? '✓' : '✕'}
        </button>`;
    }).join('');
}

// ============================================
// Выбор сервиса
// ============================================

function selectService(service) {
    currentService = service;
    selectedMailboxId = null;

    document.querySelectorAll('#service-tabs .tab-btn').forEach(btn => btn.classList.remove('active'));
    const tab = document.getElementById(`tab-${service}`);
    if (tab) tab.classList.add('active');

    renderMessages([]);
    loadMailboxes(service);
}

// ============================================
// Загрузка ящиков
// ============================================

async function loadMailboxes(service) {
    const listEl = document.getElementById('mailbox-list');
    listEl.innerHTML = '<div class="skeleton-text" style="height:40px;margin-bottom:8px"></div>'.repeat(3);

    try {
        const data = await api.get(`/mailbox/list?service=${encodeURIComponent(service)}`);
        mailboxes = Array.isArray(data) ? data : (data.mailboxes || data.data || []);
        renderMailboxes();
    } catch (e) {
        listEl.innerHTML = '';
        toast.error('Ошибка загрузки ящиков');
    }
}

function renderMailboxes() {
    const listEl = document.getElementById('mailbox-list');
    const countEl = document.getElementById('mailbox-count');
    if (countEl) countEl.textContent = mailboxes.length;

    if (!mailboxes.length) {
        listEl.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📭</div>
                <div class="empty-state-title">Нет ящиков</div>
                <p class="empty-state-description">Создайте первый ящик</p>
            </div>`;
        return;
    }

    listEl.innerHTML = mailboxes.map(mb => {
        const id = mb.id || mb.mailbox_id || '';
        const email = mb.email || mb.address || id;
        const selected = id === selectedMailboxId ? ' style="background:var(--bg-tertiary)"' : '';
        return `<div class="mailbox-row" data-id="${id}"${selected} onclick="viewMailbox('${id}')">
            <span class="mailbox-email" title="${email}">${email}</span>
            <button class="btn btn-ghost btn-sm btn-icon" onclick="event.stopPropagation(); deleteMailbox('${id}')" title="Удалить">🗑️</button>
        </div>`;
    }).join('');
}

// ============================================
// Просмотр сообщений
// ============================================

async function viewMailbox(mailboxId) {
    selectedMailboxId = mailboxId;
    renderMailboxes();

    const mb = mailboxes.find(m => (m.id || m.mailbox_id) === mailboxId);
    const label = mb ? (mb.email || mb.address || mailboxId) : mailboxId;
    document.getElementById('messages-title').textContent = `Входящие для ${label}`;

    const msgEl = document.getElementById('messages-list');
    msgEl.innerHTML = '<div class="skeleton-text" style="height:60px;margin-bottom:8px"></div>'.repeat(3);

    try {
        const data = await api.get(`/mailbox/messages?service=${encodeURIComponent(currentService)}&mailbox_id=${encodeURIComponent(mailboxId)}`);
        const messages = Array.isArray(data) ? data : (data.messages || data.data || []);
        renderMessages(messages);
    } catch (e) {
        msgEl.innerHTML = '';
        toast.error('Ошибка загрузки сообщений');
    }
}

function renderMessages(messages) {
    const msgEl = document.getElementById('messages-list');

    if (!messages.length) {
        msgEl.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📬</div>
                <div class="empty-state-title">Нет сообщений</div>
                <p class="empty-state-description">${selectedMailboxId ? 'Входящих пока нет' : 'Выберите ящик слева'}</p>
            </div>`;
        return;
    }

    msgEl.innerHTML = messages.map((msg, idx) => {
        const from = msg.from || msg.from_addr || msg.sender || '—';
        const subject = msg.subject || '(без темы)';
        const body = msg.text || msg.body || msg.html || '';
        const date = msg.date || msg.created_at || msg.received_at || '';
        const formattedDate = date ? new Date(date).toLocaleString('ru-RU') : '';
        const preview = body.length > 150 ? body.substring(0, 150) + '…' : body;
        const hasMore = body.length > 150;

        return `<div class="message-card" onclick="toggleMessage(${idx})" style="cursor:pointer">
            <div class="message-header">
                <span class="message-from">От: <strong>${escapeHtml(from)}</strong></span>
                <span class="message-date">${formattedDate}</span>
            </div>
            <div class="message-subject">📩 ${escapeHtml(subject)}</div>
            <div class="message-preview" id="msg-preview-${idx}">${escapeHtml(preview)}</div>
            <div class="message-full" id="msg-full-${idx}" style="display:none; margin-top:8px; padding:12px; background:var(--bg-secondary); border-radius:8px; white-space:pre-wrap; font-size:0.9em; max-height:500px; overflow-y:auto;">${escapeHtml(body)}</div>
            ${hasMore ? `<div class="message-toggle" id="msg-toggle-${idx}" style="margin-top:4px; color:var(--primary); font-size:0.85em;">▸ Показать полностью</div>` : ''}
        </div>`;
    }).join('');
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function toggleMessage(idx) {
    const preview = document.getElementById(`msg-preview-${idx}`);
    const full = document.getElementById(`msg-full-${idx}`);
    const toggle = document.getElementById(`msg-toggle-${idx}`);
    if (!full) return;

    const isOpen = full.style.display !== 'none';
    if (isOpen) {
        full.style.display = 'none';
        if (preview) preview.style.display = '';
        if (toggle) toggle.textContent = '▸ Показать полностью';
    } else {
        full.style.display = '';
        if (preview) preview.style.display = 'none';
        if (toggle) toggle.textContent = '▾ Свернуть';
    }
}

// ============================================
// Создание ящика
// ============================================

async function createMailbox() {
    if (!currentService) {
        toast.warning('Сначала выберите сервис');
        return;
    }

    try {
        await api.post('/mailbox/create', { service: currentService });
        toast.success('Ящик создан');
        loadMailboxes(currentService);
    } catch (e) {
        toast.error('Ошибка создания ящика');
    }
}

// ============================================
// Удаление ящика
// ============================================

async function deleteMailbox(mailboxId) {
    if (!currentService) return;
    if (!confirm('Удалить этот почтовый ящик?')) return;

    try {
        await api.delete('/mailbox/delete', { service: currentService, mailbox_id: mailboxId });
        toast.success('Ящик удалён');
        if (selectedMailboxId === mailboxId) {
            selectedMailboxId = null;
            renderMessages([]);
            document.getElementById('messages-title').textContent = 'Входящие';
        }
        loadMailboxes(currentService);
    } catch (e) {
        toast.error('Ошибка удаления ящика');
    }
}

// ============================================
// Обновление
// ============================================

async function refreshMailboxes() {
    if (!currentService) return;
    loadMailboxes(currentService);
}
