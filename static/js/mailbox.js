/**
 * Почта — Gmail-style клиентская логика
 * Состояния: inbox (список писем) | reading (чтение письма)
 */

let currentService = null;
let mailboxes = [];
let currentMessages = [];
let selectedMailboxId = null;
let currentView = 'inbox'; // 'inbox' | 'reading'

document.addEventListener('DOMContentLoaded', () => loadServices());

// ──────────────────────────────────────
// Services
// ──────────────────────────────────────

async function loadServices() {
    try {
        const data = await api.get('/mailbox/services');
        const services = data.services || [];
        renderServiceTabs(services);
        const enabled = services.find(s => s.enabled);
        if (enabled) selectService(enabled.name);
    } catch (e) {
        toast.error('Ошибка загрузки сервисов');
    }
}

function renderServiceTabs(services) {
    const c = document.getElementById('service-tabs');
    c.innerHTML = services.map(s =>
        `<button class="tab-btn${s.enabled ? '' : ' disabled'}" id="tab-${s.name}"
            onclick="selectService('${s.name}')" ${s.enabled ? '' : 'disabled'}>
            ${s.label} ${s.enabled ? '✓' : '✕'}
        </button>`
    ).join('');
}

function selectService(service) {
    currentService = service;
    selectedMailboxId = null;
    currentView = 'inbox';
    document.querySelectorAll('#service-tabs .tab-btn').forEach(b => b.classList.remove('active'));
    const tab = document.getElementById(`tab-${service}`);
    if (tab) tab.classList.add('active');
    showInbox();
    loadMailboxes(service);
}

// ──────────────────────────────────────
// Mailbox sidebar
// ──────────────────────────────────────

async function loadMailboxes(service) {
    const el = document.getElementById('mailbox-list');
    el.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-muted)">Загрузка...</div>';
    try {
        const data = await api.get(`/mailbox/list?service=${encodeURIComponent(service)}`);
        mailboxes = data.items || data.mailboxes || data.data || [];
        renderMailboxes();
    } catch (e) {
        el.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-muted)">Ошибка загрузки</div>';
    }
}

function renderMailboxes() {
    const el = document.getElementById('mailbox-list');
    document.getElementById('mailbox-count').textContent = `(${mailboxes.length})`;

    if (!mailboxes.length) {
        el.innerHTML = '<div style="padding:40px 16px;text-align:center;color:var(--text-muted)"><div style="font-size:2rem;margin-bottom:8px;">📭</div>Нет ящиков</div>';
        return;
    }

    el.innerHTML = mailboxes.map(mb => {
        const id = mb.id || mb.mailbox_id || '';
        const email = mb.email || mb.address || id;
        const initial = email.charAt(0).toUpperCase();
        const active = id === selectedMailboxId ? ' active' : '';
        const date = mb.created_at ? new Date(mb.created_at).toLocaleDateString('ru-RU') : '';
        return `<div class="mail-sidebar-item${active}" onclick="viewMailbox('${id}')">
            <div class="mail-avatar">${initial}</div>
            <div class="mail-info">
                <div class="mail-addr">${esc(email)}</div>
                <div class="mail-meta">${date}</div>
            </div>
            <button class="mail-del" onclick="event.stopPropagation();deleteMailbox('${id}')" title="Удалить">🗑️</button>
        </div>`;
    }).join('');
}

// ──────────────────────────────────────
// Inbox — message list
// ──────────────────────────────────────

function showInbox() {
    currentView = 'inbox';
    const toolbar = document.getElementById('mail-toolbar');
    const mb = mailboxes.find(m => (m.id || m.mailbox_id) === selectedMailboxId);
    const label = mb ? (mb.email || mb.address) : 'Входящие';
    toolbar.innerHTML = `
        <h3 id="toolbar-title">📨 ${esc(label)}</h3>
        <button class="btn btn-ghost btn-sm" onclick="refreshMessages()" title="Обновить">🔄</button>
    `;
    renderMessageList();
}

async function viewMailbox(mailboxId) {
    selectedMailboxId = mailboxId;
    currentView = 'inbox';
    renderMailboxes();

    const content = document.getElementById('mail-content');
    content.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-muted)">Загрузка сообщений...</div>';

    const mb = mailboxes.find(m => (m.id || m.mailbox_id) === mailboxId);
    const label = mb ? (mb.email || mb.address) : mailboxId;
    document.getElementById('mail-toolbar').innerHTML = `
        <h3 id="toolbar-title">📨 ${esc(label)}</h3>
        <button class="btn btn-ghost btn-sm" onclick="refreshMessages()" title="Обновить">🔄</button>
    `;

    try {
        const data = await api.get(`/mailbox/messages?service=${encodeURIComponent(currentService)}&mailbox_id=${encodeURIComponent(mailboxId)}`);
        currentMessages = data.messages || data.items || data.data || [];
        renderMessageList();
    } catch (e) {
        content.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-muted)">Ошибка загрузки</div>';
    }
}

function renderMessageList() {
    const el = document.getElementById('mail-content');
    if (!currentMessages.length) {
        el.innerHTML = `<div style="padding:60px 16px;text-align:center;color:var(--text-muted)">
            <div style="font-size:3rem;margin-bottom:12px;">📬</div>
            <div>Нет входящих сообщений</div>
        </div>`;
        return;
    }

    el.innerHTML = currentMessages.map((msg, i) => {
        const from = msg.from || msg.from_addr || msg.sender || '—';
        const subject = msg.subject || '(без темы)';
        const body = msg.text || msg.body || msg.html || '';
        const snippet = body.length > 80 ? body.substring(0, 80).replace(/\n/g, ' ') + '…' : body.replace(/\n/g, ' ');
        const date = msg.date || msg.created_at || msg.received_at || '';
        const time = date ? formatDate(date) : '';

        return `<div class="msg-row unread" onclick="openMessage(${i})">
            <div class="msg-sender">${esc(from)}</div>
            <div class="msg-subject">${esc(subject)} <span class="msg-snippet">— ${esc(snippet)}</span></div>
            <div class="msg-time">${time}</div>
        </div>`;
    }).join('');
}

// ──────────────────────────────────────
// Reading view — single message
// ──────────────────────────────────────

function openMessage(index) {
    const msg = currentMessages[index];
    if (!msg) return;

    currentView = 'reading';
    const from = msg.from || msg.from_addr || msg.sender || '—';
    const subject = msg.subject || '(без темы)';
    const body = msg.text || msg.body || msg.html || '';
    const date = msg.date || msg.created_at || msg.received_at || '';
    const fullDate = date ? new Date(date).toLocaleString('ru-RU') : '';
    const initial = from.charAt(0).toUpperCase();

    // Update toolbar with back button
    document.getElementById('mail-toolbar').innerHTML = `
        <button class="btn-back" onclick="backToInbox()" title="Назад">← Назад</button>
        <h3 style="flex:1;margin:0;font-size:0.9rem;color:var(--text-muted);">Сообщение ${index + 1} из ${currentMessages.length}</h3>
    `;

    // Render full message
    document.getElementById('mail-content').innerHTML = `
        <div class="msg-view">
            <div class="msg-view-subject">${esc(subject)}</div>
            <div class="msg-view-header">
                <div class="msg-view-avatar">${initial}</div>
                <div>
                    <div class="msg-view-sender">${esc(from)}</div>
                    <div class="msg-view-email">кому: мне</div>
                </div>
                <div class="msg-view-date">${fullDate}</div>
            </div>
            <div class="msg-view-body">${esc(body)}</div>
        </div>
    `;
}

function backToInbox() {
    showInbox();
}

// ──────────────────────────────────────
// Actions
// ──────────────────────────────────────

async function createMailbox() {
    if (!currentService) { toast.warning('Выберите сервис'); return; }
    try {
        await api.post('/mailbox/create', { service: currentService });
        toast.success('Ящик создан');
        loadMailboxes(currentService);
    } catch (e) {
        toast.error('Ошибка создания');
    }
}

async function deleteMailbox(mailboxId) {
    if (!currentService || !confirm('Удалить ящик?')) return;
    try {
        await api.delete('/mailbox/delete', { service: currentService, mailbox_id: mailboxId });
        toast.success('Ящик удалён');
        if (selectedMailboxId === mailboxId) {
            selectedMailboxId = null;
            currentMessages = [];
            showInbox();
        }
        loadMailboxes(currentService);
    } catch (e) {
        toast.error('Ошибка удаления');
    }
}

async function refreshMessages() {
    if (selectedMailboxId) viewMailbox(selectedMailboxId);
}

async function refreshMailboxes() {
    if (currentService) loadMailboxes(currentService);
}

// ──────────────────────────────────────
// Helpers
// ──────────────────────────────────────

function esc(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

function formatDate(dateStr) {
    try {
        const d = new Date(dateStr);
        const now = new Date();
        const isToday = d.toDateString() === now.toDateString();
        if (isToday) return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
        return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
    } catch { return dateStr; }
}
