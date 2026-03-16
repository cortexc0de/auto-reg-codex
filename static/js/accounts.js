/**
 * JavaScript страницы управления аккаунтами
 * Использует библиотеку утилит из utils.js
 */

// Состояние
let currentPage = 1;
let pageSize = 20;
let totalAccounts = 0;
let selectedAccounts = new Set();
let isLoading = false;
let selectAllPages = false;  // Выбраны ли все страницы
let currentFilters = { status: '', email_service: '', search: '' };  // Текущие фильтры

// DOM-элементы
const elements = {
    table: document.getElementById('accounts-table'),
    totalAccounts: document.getElementById('total-accounts'),
    activeAccounts: document.getElementById('active-accounts'),
    expiredAccounts: document.getElementById('expired-accounts'),
    failedAccounts: document.getElementById('failed-accounts'),
    filterStatus: document.getElementById('filter-status'),
    filterService: document.getElementById('filter-service'),
    searchInput: document.getElementById('search-input'),
    refreshBtn: document.getElementById('refresh-btn'),
    batchRefreshBtn: document.getElementById('batch-refresh-btn'),
    batchValidateBtn: document.getElementById('batch-validate-btn'),
    batchUploadCpaBtn: document.getElementById('batch-upload-cpa-btn'),
    batchCheckSubBtn: document.getElementById('batch-check-sub-btn'),
    batchUploadTmBtn: document.getElementById('batch-upload-tm-btn'),
    batchDeleteBtn: document.getElementById('batch-delete-btn'),
    exportBtn: document.getElementById('export-btn'),
    exportMenu: document.getElementById('export-menu'),
    selectAll: document.getElementById('select-all'),
    prevPage: document.getElementById('prev-page'),
    nextPage: document.getElementById('next-page'),
    pageInfo: document.getElementById('page-info'),
    detailModal: document.getElementById('detail-modal'),
    modalBody: document.getElementById('modal-body'),
    closeModal: document.getElementById('close-modal')
};

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadAccounts();
    initEventListeners();
    updateBatchButtons();  // Начальное состояние кнопок
    renderSelectAllBanner();
});

// Обработчики событий
function initEventListeners() {
    // Фильтрация
    elements.filterStatus.addEventListener('change', () => {
        currentPage = 1;
        resetSelectAllPages();
        loadAccounts();
    });

    elements.filterService.addEventListener('change', () => {
        currentPage = 1;
        resetSelectAllPages();
        loadAccounts();
    });

    // Поиск (с debounce)
    elements.searchInput.addEventListener('input', debounce(() => {
        currentPage = 1;
        resetSelectAllPages();
        loadAccounts();
    }, 300));

    // Горячая клавиша для поиска
    elements.searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            elements.searchInput.blur();
            elements.searchInput.value = '';
            resetSelectAllPages();
            loadAccounts();
        }
    });

    // Обновление
    elements.refreshBtn.addEventListener('click', () => {
        loadStats();
        loadAccounts();
        toast.info('Обновлено');
    });

    // Массовое обновление Token
    elements.batchRefreshBtn.addEventListener('click', handleBatchRefresh);

    // Массовая проверка Token
    elements.batchValidateBtn.addEventListener('click', handleBatchValidate);

    // Массовая загрузка в CPA
    elements.batchUploadCpaBtn.addEventListener('click', handleBatchUploadCpa);

    // Массовая проверка подписки
    elements.batchCheckSubBtn.addEventListener('click', handleBatchCheckSubscription);

    // Массовая загрузка в TM
    elements.batchUploadTmBtn.addEventListener('click', handleBatchUploadTm);

    // Массовое удаление
    elements.batchDeleteBtn.addEventListener('click', handleBatchDelete);

    // Выбрать все (текущая страница)
    elements.selectAll.addEventListener('change', (e) => {
        const checkboxes = elements.table.querySelectorAll('input[type="checkbox"][data-id]');
        checkboxes.forEach(cb => {
            cb.checked = e.target.checked;
            const id = parseInt(cb.dataset.id);
            if (e.target.checked) {
                selectedAccounts.add(id);
            } else {
                selectedAccounts.delete(id);
            }
        });
        if (!e.target.checked) {
            selectAllPages = false;
        }
        updateBatchButtons();
        renderSelectAllBanner();
    });

    // Пагинация
    elements.prevPage.addEventListener('click', () => {
        if (currentPage > 1 && !isLoading) {
            currentPage--;
            loadAccounts();
        }
    });

    elements.nextPage.addEventListener('click', () => {
        const totalPages = Math.ceil(totalAccounts / pageSize);
        if (currentPage < totalPages && !isLoading) {
            currentPage++;
            loadAccounts();
        }
    });

    // Экспорт
    elements.exportBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        elements.exportMenu.classList.toggle('active');
    });

    delegate(elements.exportMenu, 'click', '.dropdown-item', (e, target) => {
        e.preventDefault();
        const format = target.dataset.format;
        exportAccounts(format);
        elements.exportMenu.classList.remove('active');
    });

    // Закрытие модального окна
    elements.closeModal.addEventListener('click', () => {
        elements.detailModal.classList.remove('active');
    });

    elements.detailModal.addEventListener('click', (e) => {
        if (e.target === elements.detailModal) {
            elements.detailModal.classList.remove('active');
        }
    });

    // Закрытие выпадающего меню при клике вне его
    document.addEventListener('click', () => {
        elements.exportMenu.classList.remove('active');
    });
}

// Загрузка статистики
async function loadStats() {
    try {
        const data = await api.get('/accounts/stats/summary');

        elements.totalAccounts.textContent = format.number(data.total || 0);
        elements.activeAccounts.textContent = format.number(data.by_status?.active || 0);
        elements.expiredAccounts.textContent = format.number(data.by_status?.expired || 0);
        elements.failedAccounts.textContent = format.number(data.by_status?.failed || 0);

        // Анимация
        animateValue(elements.totalAccounts, data.total || 0);
    } catch (error) {
        console.error('Ошибка загрузки статистики:', error);
    }
}

// Анимация числа
function animateValue(element, value) {
    element.style.transition = 'transform 0.2s ease';
    element.style.transform = 'scale(1.1)';
    setTimeout(() => {
        element.style.transform = 'scale(1)';
    }, 200);
}

// Загрузка списка аккаунтов
async function loadAccounts() {
    if (isLoading) return;
    isLoading = true;

    // Отображение состояния загрузки
    elements.table.innerHTML = `
        <tr>
            <td colspan="9">
                <div class="empty-state">
                    <div class="skeleton skeleton-text" style="width: 60%;"></div>
                    <div class="skeleton skeleton-text" style="width: 80%;"></div>
                    <div class="skeleton skeleton-text" style="width: 40%;"></div>
                </div>
            </td>
        </tr>
    `;

    // Сохранение текущих фильтров
    currentFilters.status = elements.filterStatus.value;
    currentFilters.email_service = elements.filterService.value;
    currentFilters.search = elements.searchInput.value.trim();

    const params = new URLSearchParams({
        page: currentPage,
        page_size: pageSize,
    });

    if (currentFilters.status) {
        params.append('status', currentFilters.status);
    }

    if (currentFilters.email_service) {
        params.append('email_service', currentFilters.email_service);
    }

    if (currentFilters.search) {
        params.append('search', currentFilters.search);
    }

    try {
        const data = await api.get(`/accounts?${params}`);
        totalAccounts = data.total;
        renderAccounts(data.accounts);
        updatePagination();
    } catch (error) {
        console.error('Ошибка загрузки аккаунтов:', error);
        elements.table.innerHTML = `
            <tr>
                <td colspan="9">
                    <div class="empty-state">
                        <div class="empty-state-icon">❌</div>
                        <div class="empty-state-title">Ошибка загрузки</div>
                        <div class="empty-state-description">Проверьте подключение и повторите</div>
                    </div>
                </td>
            </tr>
        `;
    } finally {
        isLoading = false;
    }
}

// Отрисовка списка аккаунтов
function renderAccounts(accounts) {
    if (accounts.length === 0) {
        elements.table.innerHTML = `
            <tr>
                <td colspan="9">
                    <div class="empty-state">
                        <div class="empty-state-icon">📭</div>
                        <div class="empty-state-title">Нет данных</div>
                        <div class="empty-state-description">Не найдено аккаунтов по заданным критериям</div>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    elements.table.innerHTML = accounts.map(account => `
        <tr data-id="${account.id}">
            <td>
                <input type="checkbox" data-id="${account.id}"
                    ${selectedAccounts.has(account.id) ? 'checked' : ''}>
            </td>
            <td>${account.id}</td>
            <td>
                <span class="email-cell" title="${escapeHtml(account.email)}">
                    ${escapeHtml(account.email)}
                </span>
            </td>
            <td class="password-cell">
                ${account.password
                    ? `<span class="password-hidden" onclick="togglePassword(this, '${escapeHtml(account.password)}')" title="Нажмите для просмотра">${escapeHtml(account.password.substring(0, 4) + '****')}</span>`
                    : '-'}
            </td>
            <td>${getServiceTypeText(account.email_service)}</td>
            <td>
                <span class="status-badge ${getStatusClass('account', account.status)}">
                    ${getStatusText('account', account.status)}
                </span>
            </td>
            <td>
                <div class="cpa-status">
                    ${account.cpa_uploaded
                        ? `<span class="badge uploaded" title="Загружено ${format.date(account.cpa_uploaded_at)}">✓</span>`
                        : `<span class="badge pending">-</span>`}
                </div>
            </td>
            <td>
                <div class="cpa-status">
                    ${account.subscription_type
                        ? `<span class="badge uploaded" title="${account.subscription_type}">${account.subscription_type}</span>`
                        : `<span class="badge pending">-</span>`}
                </div>
            </td>
            <td>${format.date(account.last_refresh) || '-'}</td>
            <td>
                <div class="action-buttons">
                    <button class="btn btn-ghost btn-sm" onclick="refreshToken(${account.id})" title="Обновить Token">
                        🔄
                    </button>
                    <button class="btn btn-ghost btn-sm" onclick="uploadToCpa(${account.id})" title="Загрузить в CPA">
                        ☁️
                    </button>
                    <button class="btn btn-ghost btn-sm" onclick="markSubscription(${account.id})" title="Отметить подписку">
                        🏷️
                    </button>
                    <button class="btn btn-ghost btn-sm" onclick="uploadToTm(${account.id})" title="Загрузить в Team Manager">
                        🚀
                    </button>
                    <button class="btn btn-ghost btn-sm" onclick="viewAccount(${account.id})" title="Подробнее">
                        👁️
                    </button>
                    <button class="btn btn-ghost btn-sm" onclick="copyEmail('${escapeHtml(account.email)}')" title="Копировать email">
                        📋
                    </button>
                    ${account.password ? `<button class="btn btn-ghost btn-sm" onclick="copyToClipboard('${escapeHtml(account.password)}')" title="Копировать пароль">🔑</button>` : ''}
                    <button class="btn btn-ghost btn-sm" onclick="deleteAccount(${account.id}, '${escapeHtml(account.email)}')" title="Удалить">
                        🗑️
                    </button>
                </div>
            </td>
        </tr>
    `).join('');

    // Привязка событий чекбоксов
    elements.table.querySelectorAll('input[type="checkbox"][data-id]').forEach(cb => {
        cb.addEventListener('change', (e) => {
            const id = parseInt(e.target.dataset.id);
            if (e.target.checked) {
                selectedAccounts.add(id);
            } else {
                selectedAccounts.delete(id);
                selectAllPages = false;
            }
            // Синхронизация состояния «Выбрать все»
            const allChecked = elements.table.querySelectorAll('input[type="checkbox"][data-id]');
            const checkedCount = elements.table.querySelectorAll('input[type="checkbox"][data-id]:checked').length;
            elements.selectAll.checked = allChecked.length > 0 && checkedCount === allChecked.length;
            elements.selectAll.indeterminate = checkedCount > 0 && checkedCount < allChecked.length;
            updateBatchButtons();
            renderSelectAllBanner();
        });
    });

    // Синхронизация «Выбрать все» после отрисовки
    const allCbs = elements.table.querySelectorAll('input[type="checkbox"][data-id]');
    const checkedCbs = elements.table.querySelectorAll('input[type="checkbox"][data-id]:checked');
    elements.selectAll.checked = allCbs.length > 0 && checkedCbs.length === allCbs.length;
    elements.selectAll.indeterminate = checkedCbs.length > 0 && checkedCbs.length < allCbs.length;
    renderSelectAllBanner();
}

// Переключение отображения пароля
function togglePassword(element, password) {
    if (element.dataset.revealed === 'true') {
        element.textContent = password.substring(0, 4) + '****';
        element.classList.add('password-hidden');
        element.dataset.revealed = 'false';
    } else {
        element.textContent = password;
        element.classList.remove('password-hidden');
        element.dataset.revealed = 'true';
    }
}

// Обновление пагинации
function updatePagination() {
    const totalPages = Math.max(1, Math.ceil(totalAccounts / pageSize));

    elements.prevPage.disabled = currentPage <= 1;
    elements.nextPage.disabled = currentPage >= totalPages;

    elements.pageInfo.textContent = `Стр. ${currentPage} / ${totalPages}`;
}

// Сброс выделения всех страниц
function resetSelectAllPages() {
    selectAllPages = false;
    selectedAccounts.clear();
    updateBatchButtons();
    renderSelectAllBanner();
}

// Формирование тела массового запроса (с select_all и фильтрами)
function buildBatchPayload(extraFields = {}) {
    if (selectAllPages) {
        return {
            ids: [],
            select_all: true,
            status_filter: currentFilters.status || null,
            email_service_filter: currentFilters.email_service || null,
            search_filter: currentFilters.search || null,
            ...extraFields
        };
    }
    return { ids: Array.from(selectedAccounts), ...extraFields };
}

// Получение эффективного количества выбранных (при select_all — общее число)
function getEffectiveCount() {
    return selectAllPages ? totalAccounts : selectedAccounts.size;
}

// Отрисовка баннера «Выбрать все»
function renderSelectAllBanner() {
    let banner = document.getElementById('select-all-banner');
    const totalPages = Math.ceil(totalAccounts / pageSize);
    const currentPageSize = elements.table.querySelectorAll('input[type="checkbox"][data-id]').length;
    const checkedOnPage = elements.table.querySelectorAll('input[type="checkbox"][data-id]:checked').length;
    const allPageSelected = currentPageSize > 0 && checkedOnPage === currentPageSize;

    // Показывать баннер только при полном выделении текущей страницы и наличии нескольких страниц
    if (!allPageSelected || totalPages <= 1 || totalAccounts <= pageSize) {
        if (banner) banner.remove();
        return;
    }

    if (!banner) {
        banner = document.createElement('div');
        banner.id = 'select-all-banner';
        banner.style.cssText = 'background:var(--primary-light,#e8f0fe);color:var(--primary-color,#1a73e8);padding:8px 16px;text-align:center;font-size:0.875rem;border-bottom:1px solid var(--border-color);';
        const tableContainer = document.querySelector('.table-container');
        if (tableContainer) tableContainer.insertAdjacentElement('beforebegin', banner);
    }

    if (selectAllPages) {
        banner.innerHTML = `Выбраны все <strong>${totalAccounts}</strong> записей.<button onclick="resetSelectAllPages()" style="margin-left:8px;color:var(--primary-color,#1a73e8);background:none;border:none;cursor:pointer;text-decoration:underline;">Снять выделение</button>`;
    } else {
        banner.innerHTML = `На этой странице выбрано <strong>${checkedOnPage}</strong>.<button onclick="selectAllPagesAction()" style="margin-left:8px;color:var(--primary-color,#1a73e8);background:none;border:none;cursor:pointer;text-decoration:underline;">Выбрать все ${totalAccounts}</button>`;
    }
}

// Выбрать все страницы
function selectAllPagesAction() {
    selectAllPages = true;
    updateBatchButtons();
    renderSelectAllBanner();
}

// Обновление кнопок массовых операций
function updateBatchButtons() {
    const count = getEffectiveCount();
    elements.batchDeleteBtn.disabled = count === 0;
    elements.batchRefreshBtn.disabled = count === 0;
    elements.batchValidateBtn.disabled = count === 0;
    elements.batchUploadCpaBtn.disabled = count === 0;
    elements.batchCheckSubBtn.disabled = count === 0;
    elements.batchUploadTmBtn.disabled = count === 0;
    elements.exportBtn.disabled = count === 0;

    elements.batchDeleteBtn.textContent = count > 0 ? `🗑️ Удалить (${count})` : '🗑️ Удалить выбранные';
    elements.batchRefreshBtn.textContent = count > 0 ? `🔄 Обновить (${count})` : '🔄 Обновить Token';
    elements.batchValidateBtn.textContent = count > 0 ? `✅ Проверить (${count})` : '✅ Проверить Token';
    elements.batchUploadCpaBtn.textContent = count > 0 ? `☁️ Загрузить (${count})` : '☁️ Загрузить CPA';
    elements.batchCheckSubBtn.textContent = count > 0 ? `🔍 Проверить (${count})` : '🔍 Проверить подписку';
    elements.batchUploadTmBtn.textContent = count > 0 ? `🚀 Загрузить TM (${count})` : '🚀 Загрузить TM';
}

// Обновление Token одного аккаунта
async function refreshToken(id) {
    try {
        toast.info('Обновление Token...');
        const result = await api.post(`/accounts/${id}/refresh`);

        if (result.success) {
            toast.success('Token обновлён');
            loadAccounts();
        } else {
            toast.error('Ошибка обновления: ' + (result.error || 'Неизвестная ошибка'));
        }
    } catch (error) {
        toast.error('Ошибка обновления: ' + error.message);
    }
}

// Массовое обновление Token
async function handleBatchRefresh() {
    const count = getEffectiveCount();
    if (count === 0) return;

    const confirmed = await confirm(`Обновить Token для ${count} выбранных аккаунтов?`);
    if (!confirmed) return;

    elements.batchRefreshBtn.disabled = true;
    elements.batchRefreshBtn.textContent = 'Обновление...';

    try {
        const result = await api.post('/accounts/batch-refresh', buildBatchPayload());
        toast.success(`Успешно: ${result.success_count}, ошибок: ${result.failed_count}`);
        loadAccounts();
    } catch (error) {
        toast.error('Ошибка массового обновления: ' + error.message);
    } finally {
        updateBatchButtons();
    }
}

// Массовая проверка Token
async function handleBatchValidate() {
    if (getEffectiveCount() === 0) return;

    elements.batchValidateBtn.disabled = true;
    elements.batchValidateBtn.textContent = 'Проверка...';

    try {
        const result = await api.post('/accounts/batch-validate', buildBatchPayload());
        toast.info(`Действительных: ${result.valid_count}, недействительных: ${result.invalid_count}`);
        loadAccounts();
    } catch (error) {
        toast.error('Ошибка массовой проверки: ' + error.message);
    } finally {
        updateBatchButtons();
    }
}

// Просмотр деталей аккаунта
async function viewAccount(id) {
    try {
        const account = await api.get(`/accounts/${id}`);
        const tokens = await api.get(`/accounts/${id}/tokens`);

        elements.modalBody.innerHTML = `
            <div class="info-grid">
                <div class="info-item">
                    <span class="label">Email</span>
                    <span class="value">
                        ${escapeHtml(account.email)}
                        <button class="btn btn-ghost btn-sm" onclick="copyToClipboard('${escapeHtml(account.email)}')" title="Копировать">
                            📋
                        </button>
                    </span>
                </div>
                <div class="info-item">
                    <span class="label">Пароль</span>
                    <span class="value">
                        ${account.password
                            ? `<code style="font-size: 0.75rem;">${escapeHtml(account.password)}</code>
                               <button class="btn btn-ghost btn-sm" onclick="copyToClipboard('${escapeHtml(account.password)}')" title="Копировать">📋</button>`
                            : '-'}
                    </span>
                </div>
                <div class="info-item">
                    <span class="label">Почтовый сервис</span>
                    <span class="value">${getServiceTypeText(account.email_service)}</span>
                </div>
                <div class="info-item">
                    <span class="label">Статус</span>
                    <span class="value">
                        <span class="status-badge ${getStatusClass('account', account.status)}">
                            ${getStatusText('account', account.status)}
                        </span>
                    </span>
                </div>
                <div class="info-item">
                    <span class="label">Дата регистрации</span>
                    <span class="value">${format.date(account.registered_at)}</span>
                </div>
                <div class="info-item">
                    <span class="label">Последнее обновление</span>
                    <span class="value">${format.date(account.last_refresh) || '-'}</span>
                </div>
                <div class="info-item" style="grid-column: span 2;">
                    <span class="label">Account ID</span>
                    <span class="value" style="font-size: 0.75rem; word-break: break-all;">
                        ${escapeHtml(account.account_id || '-')}
                    </span>
                </div>
                <div class="info-item" style="grid-column: span 2;">
                    <span class="label">Workspace ID</span>
                    <span class="value" style="font-size: 0.75rem; word-break: break-all;">
                        ${escapeHtml(account.workspace_id || '-')}
                    </span>
                </div>
                <div class="info-item" style="grid-column: span 2;">
                    <span class="label">Client ID</span>
                    <span class="value" style="font-size: 0.75rem; word-break: break-all;">
                        ${escapeHtml(account.client_id || '-')}
                    </span>
                </div>
                <div class="info-item" style="grid-column: span 2;">
                    <span class="label">Access Token</span>
                    <div class="value" style="font-size: 0.7rem; word-break: break-all; font-family: var(--font-mono); background: var(--surface-hover); padding: 8px; border-radius: 4px;">
                        ${escapeHtml(tokens.access_token || '-')}
                        ${tokens.access_token ? `<button class="btn btn-ghost btn-sm" onclick="copyToClipboard('${escapeHtml(tokens.access_token)}')" style="margin-left: 8px;">📋</button>` : ''}
                    </div>
                </div>
                <div class="info-item" style="grid-column: span 2;">
                    <span class="label">Refresh Token</span>
                    <div class="value" style="font-size: 0.7rem; word-break: break-all; font-family: var(--font-mono); background: var(--surface-hover); padding: 8px; border-radius: 4px;">
                        ${escapeHtml(tokens.refresh_token || '-')}
                        ${tokens.refresh_token ? `<button class="btn btn-ghost btn-sm" onclick="copyToClipboard('${escapeHtml(tokens.refresh_token)}')" style="margin-left: 8px;">📋</button>` : ''}
                    </div>
                </div>
            </div>
            <div style="margin-top: var(--spacing-lg); display: flex; gap: var(--spacing-sm);">
                <button class="btn btn-primary" onclick="refreshToken(${id}); elements.detailModal.classList.remove('active');">
                    🔄 Обновить Token
                </button>
            </div>
        `;

        elements.detailModal.classList.add('active');
    } catch (error) {
        toast.error('Ошибка загрузки деталей: ' + error.message);
    }
}

// Копирование email
function copyEmail(email) {
    copyToClipboard(email);
}

// Удаление аккаунта
async function deleteAccount(id, email) {
    const confirmed = await confirm(`Удалить аккаунт ${email}? Это действие необратимо.`);
    if (!confirmed) return;

    try {
        await api.delete(`/accounts/${id}`);
        toast.success('Аккаунт удалён');
        selectedAccounts.delete(id);
        loadStats();
        loadAccounts();
    } catch (error) {
        toast.error('Ошибка удаления: ' + error.message);
    }
}

// Массовое удаление
async function handleBatchDelete() {
    const count = getEffectiveCount();
    if (count === 0) return;

    const confirmed = await confirm(`Удалить ${count} выбранных аккаунтов? Это действие необратимо.`);
    if (!confirmed) return;

    try {
        const result = await api.post('/accounts/batch-delete', buildBatchPayload());
        toast.success(`Удалено ${result.deleted_count} аккаунтов`);
        selectedAccounts.clear();
        selectAllPages = false;
        loadStats();
        loadAccounts();
    } catch (error) {
        toast.error('Ошибка удаления: ' + error.message);
    }
}

// Экспорт аккаунтов
async function exportAccounts(format) {
    const count = getEffectiveCount();
    if (count === 0) {
        toast.warning('Сначала выберите аккаунты для экспорта');
        return;
    }

    toast.info(`Экспорт ${count} аккаунтов...`);

    try {
        const response = await fetch('/api/accounts/export/' + format, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(buildBatchPayload())
        });

        if (!response.ok) {
            throw new Error(`Ошибка экспорта: HTTP ${response.status}`);
        }

        // Получение содержимого файла
        const blob = await response.blob();

        // Получение имени файла из Content-Disposition
        const disposition = response.headers.get('Content-Disposition');
        let filename = `accounts_${Date.now()}.${format === 'cpa' ? 'json' : format}`;
        if (disposition) {
            const match = disposition.match(/filename=(.+)/);
            if (match) {
                filename = match[1];
            }
        }

        // Создание ссылки для скачивания
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();

        toast.success('Экспорт завершён');
    } catch (error) {
        console.error('Ошибка экспорта:', error);
        toast.error('Ошибка экспорта: ' + error.message);
    }
}

// HTML-экранирование
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Загрузка одного аккаунта в CPA
async function uploadToCpa(id) {
    try {
        toast.info('Загрузка в CPA...');
        const result = await api.post(`/accounts/${id}/upload-cpa`);

        if (result.success) {
            toast.success('Загружено');
            loadAccounts();
        } else {
            toast.error('Ошибка загрузки: ' + (result.error || 'Неизвестная ошибка'));
        }
    } catch (error) {
        toast.error('Ошибка загрузки: ' + error.message);
    }
}

// Массовая загрузка в CPA
async function handleBatchUploadCpa() {
    const count = getEffectiveCount();
    if (count === 0) return;

    const confirmed = await confirm(`Загрузить ${count} аккаунтов в CPA?`);
    if (!confirmed) return;

    elements.batchUploadCpaBtn.disabled = true;
    elements.batchUploadCpaBtn.textContent = 'Загрузка...';

    try {
        const result = await api.post('/accounts/batch-upload-cpa', buildBatchPayload());

        let message = `Успешно: ${result.success_count}`;
        if (result.failed_count > 0) {
            message += `, ошибок: ${result.failed_count}`;
        }
        if (result.skipped_count > 0) {
            message += `, пропущено: ${result.skipped_count}`;
        }

        toast.success(message);
        loadAccounts();
    } catch (error) {
        toast.error('Ошибка массовой загрузки: ' + error.message);
    } finally {
        updateBatchButtons();
    }
}

// ============== Статус подписки ==============

// Ручная отметка типа подписки
async function markSubscription(id) {
    const type = prompt('Введите тип подписки (plus / team / free):', 'plus');
    if (!type) return;
    if (!['plus', 'team', 'free'].includes(type.trim().toLowerCase())) {
        toast.error('Недопустимый тип, введите plus, team или free');
        return;
    }
    try {
        await api.post(`/payment/accounts/${id}/mark-subscription`, {
            subscription_type: type.trim().toLowerCase()
        });
        toast.success('Статус подписки обновлён');
        loadAccounts();
    } catch (e) {
        toast.error('Ошибка обновления: ' + e.message);
    }
}

// Массовая проверка подписки
async function handleBatchCheckSubscription() {
    const count = getEffectiveCount();
    if (count === 0) return;
    const confirmed = await confirm(`Проверить подписку для ${count} аккаунтов?`);
    if (!confirmed) return;

    elements.batchCheckSubBtn.disabled = true;
    elements.batchCheckSubBtn.textContent = 'Проверка...';

    try {
        const result = await api.post('/payment/accounts/batch-check-subscription', buildBatchPayload());
        let message = `Успешно: ${result.success_count}`;
        if (result.failed_count > 0) message += `, ошибок: ${result.failed_count}`;
        toast.success(message);
        loadAccounts();
    } catch (e) {
        toast.error('Ошибка проверки: ' + e.message);
    } finally {
        updateBatchButtons();
    }
}

// ============== Загрузка в Team Manager ==============

// Загрузка одного аккаунта в Team Manager
async function uploadToTm(id) {
    try {
        toast.info('Загрузка в Team Manager...');
        const result = await api.post(`/payment/accounts/${id}/upload-tm`);
        if (result.success) {
            toast.success('Загружено');
        } else {
            toast.error('Ошибка загрузки: ' + (result.message || 'Неизвестная ошибка'));
        }
    } catch (e) {
        toast.error('Ошибка загрузки: ' + e.message);
    }
}

// Массовая загрузка в Team Manager
async function handleBatchUploadTm() {
    const count = getEffectiveCount();
    if (count === 0) return;
    const confirmed = await confirm(`Загрузить ${count} аккаунтов в Team Manager?`);
    if (!confirmed) return;

    elements.batchUploadTmBtn.disabled = true;
    elements.batchUploadTmBtn.textContent = 'Загрузка...';

    try {
        const result = await api.post('/payment/accounts/batch-upload-tm', buildBatchPayload());
        let message = `Успешно: ${result.success_count}`;
        if (result.failed_count > 0) message += `, ошибок: ${result.failed_count}`;
        if (result.skipped_count > 0) message += `, пропущено: ${result.skipped_count}`;
        toast.success(message);
        loadAccounts();
    } catch (e) {
        toast.error('Ошибка массовой загрузки: ' + e.message);
    } finally {
        updateBatchButtons();
    }
}
