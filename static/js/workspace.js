/**
 * Рабочие области — клиентская логика
 */

let workspaces = [];
let selectedWorkspaceId = null;
let monitoringWs = null;

// ============================================
// Загрузка рабочих областей
// ============================================

async function loadWorkspaces() {
    try {
        const data = await api.get('/workspaces');
        workspaces = Array.isArray(data) ? data : (data.workspaces || []);
        renderWorkspaces();
        updateStats();
    } catch (e) {
        toast.error('Ошибка загрузки рабочих областей');
    }
}

function updateStats() {
    const total = workspaces.length;
    const active = workspaces.filter(w => w.status === 'active').length;
    const banned = workspaces.filter(w => w.status === 'banned').length;
    const members = workspaces.reduce((sum, w) => sum + (w.used_seats || 0), 0);

    document.getElementById('total-workspaces').textContent = total;
    document.getElementById('active-workspaces').textContent = active;
    document.getElementById('banned-workspaces').textContent = banned;
    document.getElementById('total-members').textContent = members;
}

function renderWorkspaces() {
    const grid = document.getElementById('workspace-grid');

    if (!workspaces.length) {
        grid.innerHTML = `
            <div style="grid-column: 1 / -1;">
                <div class="empty-state">
                    <div class="empty-state-icon">🏢</div>
                    <div class="empty-state-title">Нет рабочих областей</div>
                    <p style="color: var(--text-muted);">Добавьте первую рабочую область</p>
                </div>
            </div>`;
        return;
    }

    grid.innerHTML = workspaces.map(ws => {
        const pct = ws.max_seats ? Math.round((ws.used_seats || 0) / ws.max_seats * 100) : 0;
        const barColor = ws.status === 'banned'
            ? 'var(--danger-color)'
            : pct > 80
                ? 'var(--warning-color)'
                : 'var(--success-color)';
        const statusClass = ws.status === 'active' ? 'active' : 'banned';
        const statusText = ws.status === 'active' ? 'Активна' : 'Заблокирована';
        const selected = ws.id === selectedWorkspaceId ? ' selected' : '';
        const lastChecked = ws.last_checked
            ? new Date(ws.last_checked).toLocaleString('ru-RU')
            : '—';

        return `
            <div class="workspace-card${selected}" data-id="${ws.id}" onclick="selectWorkspace(${ws.id})">
                <div class="workspace-card-header">
                    <h4>${escapeHtml(ws.name)}</h4>
                    <span class="status-badge ${statusClass}">${statusText}</span>
                </div>
                <div class="workspace-card-meta">
                    <div class="meta-row">
                        <span>План</span>
                        <strong>${escapeHtml(ws.plan_type || 'team')}</strong>
                    </div>
                    <div class="meta-row">
                        <span>Мест</span>
                        <strong>${ws.used_seats || 0} / ${ws.max_seats || '—'}</strong>
                    </div>
                    <div class="slots-bar">
                        <div class="slots-bar-fill" style="width:${pct}%; background:${barColor};"></div>
                    </div>
                    <div class="meta-row">
                        <span>Проверено</span>
                        <span>${lastChecked}</span>
                    </div>
                </div>
                <div class="workspace-card-actions">
                    <button class="btn btn-primary btn-sm" onclick="event.stopPropagation(); checkWorkspace(${ws.id})">🔍 Проверить</button>
                    <button class="btn btn-ghost btn-sm" onclick="event.stopPropagation(); deleteWorkspace(${ws.id})">🗑️</button>
                </div>
            </div>`;
    }).join('');
}

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

// ============================================
// Добавление рабочей области
// ============================================

async function addWorkspace(data) {
    try {
        await api.post('/workspaces', data);
        toast.success('Рабочая область добавлена');
        closeAddModal();
        await loadWorkspaces();
    } catch (e) {
        toast.error(e.message || 'Ошибка добавления');
    }
}

async function deleteWorkspace(id) {
    const ok = await confirm('Удалить рабочую область?');
    if (!ok) return;
    try {
        await api.delete(`/workspaces/${id}`);
        toast.success('Рабочая область удалена');
        if (selectedWorkspaceId === id) {
            selectedWorkspaceId = null;
            document.getElementById('detail-panel').classList.remove('active');
        }
        await loadWorkspaces();
    } catch (e) {
        toast.error(e.message || 'Ошибка удаления');
    }
}

// ============================================
// Детали рабочей области
// ============================================

async function selectWorkspace(id) {
    selectedWorkspaceId = id;
    renderWorkspaces();
    await loadWorkspaceDetail(id);
}

async function loadWorkspaceDetail(id) {
    try {
        const data = await api.get(`/workspaces/${id}`);
        const panel = document.getElementById('detail-panel');
        panel.classList.add('active');

        document.getElementById('detail-ws-name').textContent = data.name || '—';

        renderMembers(data.members || []);
        renderBanList(data.banned_emails || []);
    } catch (e) {
        toast.error('Ошибка загрузки деталей');
    }
}

function renderMembers(members) {
    const tbody = document.getElementById('members-table');

    if (!members.length) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7">
                    <div class="empty-state" style="padding: var(--spacing-md);">
                        <div class="empty-state-icon">👥</div>
                        <div class="empty-state-title">Нет участников</div>
                    </div>
                </td>
            </tr>`;
        return;
    }

    tbody.innerHTML = members.map(m => {
        const invitedAt = m.invited_at ? new Date(m.invited_at).toLocaleDateString('ru-RU') : '—';
        const expiresAt = m.expires_at ? new Date(m.expires_at).toLocaleDateString('ru-RU') : '—';

        let daysClass = 'days-left-ok';
        let daysText = '—';
        if (m.days_left !== undefined && m.days_left !== null) {
            daysText = m.days_left;
            if (m.days_left <= 0) daysClass = 'days-left-expired';
            else if (m.days_left <= 7) daysClass = 'days-left-warn';
        }

        const statusClass = m.status === 'active' ? 'active' : (m.status === 'pending' ? 'pending' : 'warning');

        return `
            <tr>
                <td>${escapeHtml(m.email || '—')}</td>
                <td>${escapeHtml(m.role || '—')}</td>
                <td><span class="status-badge ${statusClass}">${escapeHtml(m.status || '—')}</span></td>
                <td>${invitedAt}</td>
                <td>${expiresAt}</td>
                <td><span class="${daysClass}">${daysText}</span></td>
                <td>
                    <button class="btn btn-danger btn-sm" onclick="kickMember(${selectedWorkspaceId}, '${m.id || m.user_id || ''}')">
                        Удалить
                    </button>
                </td>
            </tr>`;
    }).join('');
}

function renderBanList(emails) {
    const section = document.getElementById('ban-section');
    const list = document.getElementById('ban-list');

    if (!emails || !emails.length) {
        section.style.display = 'none';
        return;
    }

    section.style.display = 'block';
    list.innerHTML = emails.map(e => `<span class="ban-tag">${escapeHtml(e)}</span>`).join('');
}

// ============================================
// Действия с рабочей областью
// ============================================

async function checkWorkspace(id) {
    try {
        loading.show(event?.target);
        const data = await api.post(`/workspaces/${id}/check`);
        toast.success('Проверка завершена');
        if (id === selectedWorkspaceId) await loadWorkspaceDetail(id);
        await loadWorkspaces();
    } catch (e) {
        toast.error(e.message || 'Ошибка проверки');
    } finally {
        if (event?.target) loading.hide(event.target);
    }
}

async function inviteMember(wsId, email) {
    try {
        await api.post(`/workspaces/${wsId}/invite`, { email });
        toast.success(`Приглашение отправлено: ${email}`);
        await loadWorkspaceDetail(wsId);
    } catch (e) {
        toast.error(e.message || 'Ошибка приглашения');
    }
}

async function kickMember(wsId, memberId) {
    const ok = await confirm('Удалить участника из рабочей области?');
    if (!ok) return;
    try {
        await api.post(`/workspaces/${wsId}/kick/${memberId}`);
        toast.success('Участник удалён');
        await loadWorkspaceDetail(wsId);
    } catch (e) {
        toast.error(e.message || 'Ошибка удаления участника');
    }
}

async function checkBan(id) {
    try {
        const data = await api.post(`/workspaces/${id}/check-ban`);
        toast.success('Проверка бана завершена');
        if (id === selectedWorkspaceId) await loadWorkspaceDetail(id);
    } catch (e) {
        toast.error(e.message || 'Ошибка проверки бана');
    }
}

async function redistribute(id) {
    try {
        const data = await api.post(`/workspaces/${id}/redistribute`);
        toast.success('Перераспределение завершено');
        if (id === selectedWorkspaceId) await loadWorkspaceDetail(id);
        await loadWorkspaces();
    } catch (e) {
        toast.error(e.message || 'Ошибка перераспределения');
    }
}

// ============================================
// Мониторинг
// ============================================

async function getMonitoringStatus() {
    try {
        const data = await api.get('/workspaces/monitoring/status');
        updateMonitoringUI(data);
    } catch (e) {
        // Молча игнорируем, если мониторинг не настроен
    }
}

function updateMonitoringUI(data) {
    const dot = document.getElementById('monitoring-dot');
    const text = document.getElementById('monitoring-status-text');
    const cycles = document.getElementById('monitor-cycles');
    const lastCheck = document.getElementById('monitor-last-check');

    const running = data.running || data.status === 'running';
    dot.className = 'monitoring-dot ' + (running ? 'running' : 'stopped');
    text.textContent = running ? 'Запущен' : 'Остановлен';

    if (data.cycles !== undefined) cycles.textContent = data.cycles;
    if (data.last_check) {
        lastCheck.textContent = new Date(data.last_check).toLocaleString('ru-RU');
    }
}

async function startMonitoring() {
    try {
        await api.post('/workspaces/monitoring/start');
        toast.success('Мониторинг запущен');
        await getMonitoringStatus();
        connectMonitoringWs();
    } catch (e) {
        toast.error(e.message || 'Ошибка запуска мониторинга');
    }
}

async function stopMonitoring() {
    try {
        await api.post('/workspaces/monitoring/stop');
        toast.success('Мониторинг остановлен');
        await getMonitoringStatus();
        if (monitoringWs) {
            monitoringWs.close();
            monitoringWs = null;
        }
    } catch (e) {
        toast.error(e.message || 'Ошибка остановки мониторинга');
    }
}

function connectMonitoringWs() {
    if (monitoringWs) {
        monitoringWs.close();
        monitoringWs = null;
    }

    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${location.host}/api/ws/workspace-monitor`;

    monitoringWs = new WebSocket(url);

    monitoringWs.onopen = () => {
        appendMonitorLog('[WS] Подключено к мониторингу', 'success');
    };

    monitoringWs.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            const level = msg.level || 'info';
            const text = msg.message || event.data;
            appendMonitorLog(text, level);

            if (msg.cycles !== undefined) {
                document.getElementById('monitor-cycles').textContent = msg.cycles;
            }
            if (msg.last_check) {
                document.getElementById('monitor-last-check').textContent =
                    new Date(msg.last_check).toLocaleString('ru-RU');
            }
        } catch {
            appendMonitorLog(event.data);
        }
    };

    monitoringWs.onclose = () => {
        appendMonitorLog('[WS] Отключено от мониторинга', 'warning');
    };

    monitoringWs.onerror = () => {
        appendMonitorLog('[WS] Ошибка соединения', 'error');
    };
}

function appendMonitorLog(text, level = '') {
    const log = document.getElementById('monitoring-log');
    const line = document.createElement('div');
    line.className = 'log-line' + (level ? ' ' + level : '');
    line.textContent = text;
    log.appendChild(line);

    // Автопрокрутка
    log.scrollTop = log.scrollHeight;

    // Ограничиваем до 500 строк
    while (log.children.length > 500) {
        log.removeChild(log.firstChild);
    }
}

// ============================================
// Модальное окно
// ============================================

function openAddModal() {
    document.getElementById('add-workspace-modal').classList.add('active');
}

function closeAddModal() {
    document.getElementById('add-workspace-modal').classList.remove('active');
    document.getElementById('add-workspace-form').reset();
}

// ============================================
// Инициализация
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    // Загрузка данных
    loadWorkspaces();
    getMonitoringStatus();

    // Кнопки тулбара
    document.getElementById('add-workspace-btn').addEventListener('click', openAddModal);
    document.getElementById('refresh-workspaces-btn').addEventListener('click', loadWorkspaces);

    // Модальное окно
    document.getElementById('close-add-modal').addEventListener('click', closeAddModal);
    document.getElementById('cancel-add-btn').addEventListener('click', closeAddModal);

    document.getElementById('add-workspace-modal').addEventListener('click', (e) => {
        if (e.target.classList.contains('modal')) closeAddModal();
    });

    // Форма добавления
    document.getElementById('add-workspace-form').addEventListener('submit', (e) => {
        e.preventDefault();
        const form = e.target;
        addWorkspace({
            name: form.name.value,
            account_id: form.account_id.value,
            access_token: form.access_token.value,
            plan_type: form.plan_type.value,
            max_seats: parseInt(form.max_seats.value, 10) || 5,
        });
    });

    // Панель деталей — кнопки действий
    document.getElementById('detail-check-btn').addEventListener('click', () => {
        if (selectedWorkspaceId) checkWorkspace(selectedWorkspaceId);
    });

    document.getElementById('detail-check-ban-btn').addEventListener('click', () => {
        if (selectedWorkspaceId) checkBan(selectedWorkspaceId);
    });

    document.getElementById('detail-redistribute-btn').addEventListener('click', () => {
        if (selectedWorkspaceId) redistribute(selectedWorkspaceId);
    });

    document.getElementById('detail-close-btn').addEventListener('click', () => {
        selectedWorkspaceId = null;
        document.getElementById('detail-panel').classList.remove('active');
        renderWorkspaces();
    });

    // Приглашение
    document.getElementById('invite-btn').addEventListener('click', () => {
        const input = document.getElementById('invite-email');
        const email = input.value.trim();
        if (!email) {
            toast.warning('Введите email');
            return;
        }
        if (selectedWorkspaceId) {
            inviteMember(selectedWorkspaceId, email);
            input.value = '';
        }
    });

    document.getElementById('invite-email').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            document.getElementById('invite-btn').click();
        }
    });

    // Мониторинг
    document.getElementById('monitoring-start-btn').addEventListener('click', startMonitoring);
    document.getElementById('monitoring-stop-btn').addEventListener('click', stopMonitoring);

    // Попытка подключения WS при загрузке
    connectMonitoringWs();
});
