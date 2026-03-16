/**
 * JavaScript страницы почтовых сервисов
 */

// Состояние
let outlookServices = [];
let customServices = [];
let selectedOutlook = new Set();
let selectedCustom = new Set();

// DOM-элементы
const elements = {
    // Статистика
    outlookCount: document.getElementById('outlook-count'),
    customCount: document.getElementById('custom-count'),
    tempmailStatus: document.getElementById('tempmail-status'),
    totalEnabled: document.getElementById('total-enabled'),

    // Импорт Outlook
    toggleOutlookImport: document.getElementById('toggle-outlook-import'),
    outlookImportBody: document.getElementById('outlook-import-body'),
    outlookImportData: document.getElementById('outlook-import-data'),
    outlookImportEnabled: document.getElementById('outlook-import-enabled'),
    outlookImportPriority: document.getElementById('outlook-import-priority'),
    outlookImportBtn: document.getElementById('outlook-import-btn'),
    clearImportBtn: document.getElementById('clear-import-btn'),
    importResult: document.getElementById('import-result'),

    // Список Outlook
    outlookTable: document.getElementById('outlook-accounts-table'),
    selectAllOutlook: document.getElementById('select-all-outlook'),
    batchDeleteOutlookBtn: document.getElementById('batch-delete-outlook-btn'),

    // Свои домены
    customTable: document.getElementById('custom-services-table'),
    addCustomBtn: document.getElementById('add-custom-btn'),
    selectAllCustom: document.getElementById('select-all-custom'),

    // Временная почта
    tempmailForm: document.getElementById('tempmail-form'),
    tempmailApi: document.getElementById('tempmail-api'),
    tempmailEnabled: document.getElementById('tempmail-enabled'),
    testTempmailBtn: document.getElementById('test-tempmail-btn'),

    // Модальное окно добавления домена
    addCustomModal: document.getElementById('add-custom-modal'),
    addCustomForm: document.getElementById('add-custom-form'),
    closeCustomModal: document.getElementById('close-custom-modal'),
    cancelAddCustom: document.getElementById('cancel-add-custom'),

    // Модальное окно редактирования домена
    editCustomModal: document.getElementById('edit-custom-modal'),
    editCustomForm: document.getElementById('edit-custom-form'),
    closeEditCustomModal: document.getElementById('close-edit-custom-modal'),
    cancelEditCustom: document.getElementById('cancel-edit-custom'),

    // Модальное окно редактирования Outlook
    editOutlookModal: document.getElementById('edit-outlook-modal'),
    editOutlookForm: document.getElementById('edit-outlook-form'),
    closeEditOutlookModal: document.getElementById('close-edit-outlook-modal'),
    cancelEditOutlook: document.getElementById('cancel-edit-outlook')
};

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadOutlookServices();
    loadCustomServices();
    loadTempmailConfig();
    initEventListeners();
});

// Обработчики событий
function initEventListeners() {
    // Импорт Outlook: свернуть/развернуть
    elements.toggleOutlookImport.addEventListener('click', () => {
        const isHidden = elements.outlookImportBody.style.display === 'none';
        elements.outlookImportBody.style.display = isHidden ? 'block' : 'none';
        elements.toggleOutlookImport.textContent = isHidden ? 'Свернуть' : 'Развернуть';
    });

    // Импорт Outlook
    elements.outlookImportBtn.addEventListener('click', handleOutlookImport);
    elements.clearImportBtn.addEventListener('click', () => {
        elements.outlookImportData.value = '';
        elements.importResult.style.display = 'none';
    });

    // Выбрать все Outlook
    elements.selectAllOutlook.addEventListener('change', (e) => {
        const checkboxes = elements.outlookTable.querySelectorAll('input[type="checkbox"][data-id]');
        checkboxes.forEach(cb => {
            cb.checked = e.target.checked;
            const id = parseInt(cb.dataset.id);
            if (e.target.checked) {
                selectedOutlook.add(id);
            } else {
                selectedOutlook.delete(id);
            }
        });
        updateBatchButtons();
    });

    // Массовое удаление Outlook
    elements.batchDeleteOutlookBtn.addEventListener('click', handleBatchDeleteOutlook);

    // Добавление домена
    elements.addCustomBtn.addEventListener('click', () => {
        elements.addCustomModal.classList.add('active');
    });

    elements.closeCustomModal.addEventListener('click', () => {
        elements.addCustomModal.classList.remove('active');
    });

    elements.cancelAddCustom.addEventListener('click', () => {
        elements.addCustomModal.classList.remove('active');
    });

    elements.addCustomForm.addEventListener('submit', handleAddCustom);

    // Модальное окно редактирования домена
    elements.closeEditCustomModal.addEventListener('click', () => {
        elements.editCustomModal.classList.remove('active');
    });

    elements.cancelEditCustom.addEventListener('click', () => {
        elements.editCustomModal.classList.remove('active');
    });

    elements.editCustomForm.addEventListener('submit', handleEditCustom);

    // Модальное окно редактирования Outlook
    elements.closeEditOutlookModal.addEventListener('click', () => {
        elements.editOutlookModal.classList.remove('active');
    });

    elements.cancelEditOutlook.addEventListener('click', () => {
        elements.editOutlookModal.classList.remove('active');
    });

    elements.editOutlookForm.addEventListener('submit', handleEditOutlook);

    // Выбрать все домены
    elements.selectAllCustom.addEventListener('change', (e) => {
        const checkboxes = elements.customTable.querySelectorAll('input[type="checkbox"][data-id]');
        checkboxes.forEach(cb => {
            cb.checked = e.target.checked;
            const id = parseInt(cb.dataset.id);
            if (e.target.checked) {
                selectedCustom.add(id);
            } else {
                selectedCustom.delete(id);
            }
        });
    });

    // Настройки временной почты
    elements.tempmailForm.addEventListener('submit', handleSaveTempmail);
    elements.testTempmailBtn.addEventListener('click', handleTestTempmail);
}

// Загрузка статистики
async function loadStats() {
    try {
        const data = await api.get('/email-services/stats');
        elements.outlookCount.textContent = data.outlook_count || 0;
        elements.customCount.textContent = data.custom_count || 0;
        elements.tempmailStatus.textContent = data.tempmail_available ? 'Доступна' : 'Недоступна';
        elements.totalEnabled.textContent = data.enabled_count || 0;
    } catch (error) {
        console.error('Ошибка загрузки статистики:', error);
    }
}

// Загрузка Outlook-сервисов
async function loadOutlookServices() {
    try {
        const data = await api.get('/email-services?service_type=outlook');
        outlookServices = data.services || [];

        if (outlookServices.length === 0) {
            elements.outlookTable.innerHTML = `
                <tr>
                    <td colspan="7">
                        <div class="empty-state">
                            <div class="empty-state-icon">📭</div>
                            <div class="empty-state-title">Нет аккаунтов Outlook</div>
                            <div class="empty-state-description">Используйте импорт выше</div>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        elements.outlookTable.innerHTML = outlookServices.map(service => `
            <tr data-id="${service.id}">
                <td>
                    <input type="checkbox" data-id="${service.id}"
                        ${selectedOutlook.has(service.id) ? 'checked' : ''}>
                </td>
                <td>${escapeHtml(service.config?.email || service.name)}</td>
                <td>
                    <span class="status-badge ${service.config?.has_oauth ? 'active' : 'pending'}">
                        ${service.config?.has_oauth ? 'OAuth' : 'Password'}
                    </span>
                </td>
                <td>
                    <span class="status-badge ${service.enabled ? 'active' : 'disabled'}">
                        ${service.enabled ? 'Вкл.' : 'Откл.'}
                    </span>
                </td>
                <td>${service.priority}</td>
                <td>${format.date(service.last_used)}</td>
                <td>
                    <div class="action-buttons">
                        <button class="btn btn-ghost btn-sm" onclick="editOutlookService(${service.id})" title="Редактировать">
                            ✏️
                        </button>
                        <button class="btn btn-ghost btn-sm" onclick="toggleService(${service.id}, ${!service.enabled})" title="${service.enabled ? 'Отключить' : 'Включить'}">
                            ${service.enabled ? '🔇' : '🔊'}
                        </button>
                        <button class="btn btn-ghost btn-sm" onclick="testService(${service.id})" title="Тест">
                            🔌
                        </button>
                        <button class="btn btn-ghost btn-sm" onclick="deleteService(${service.id}, '${escapeHtml(service.name)}')" title="Удалить">
                            🗑️
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');

        // Привязка событий чекбоксов
        elements.outlookTable.querySelectorAll('input[type="checkbox"][data-id]').forEach(cb => {
            cb.addEventListener('change', (e) => {
                const id = parseInt(e.target.dataset.id);
                if (e.target.checked) {
                    selectedOutlook.add(id);
                } else {
                    selectedOutlook.delete(id);
                }
                updateBatchButtons();
            });
        });

    } catch (error) {
        console.error('Ошибка загрузки Outlook:', error);
        elements.outlookTable.innerHTML = `
            <tr>
                <td colspan="7">
                    <div class="empty-state">
                        <div class="empty-state-icon">❌</div>
                        <div class="empty-state-title">Ошибка загрузки</div>
                    </div>
                </td>
            </tr>
        `;
    }
}

// Загрузка сервисов своих доменов
async function loadCustomServices() {
    try {
        const data = await api.get('/email-services?service_type=custom_domain');
        customServices = data.services || [];

        if (customServices.length === 0) {
            elements.customTable.innerHTML = `
                <tr>
                    <td colspan="7">
                        <div class="empty-state">
                            <div class="empty-state-icon">📭</div>
                            <div class="empty-state-title">Нет сервисов своих доменов</div>
                            <div class="empty-state-description">Нажмите «Добавить сервис»</div>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        elements.customTable.innerHTML = customServices.map(service => `
            <tr data-id="${service.id}">
                <td>
                    <input type="checkbox" data-id="${service.id}"
                        ${selectedCustom.has(service.id) ? 'checked' : ''}>
                </td>
                <td>${escapeHtml(service.name)}</td>
                <td style="font-size: 0.75rem;">${escapeHtml(service.config?.base_url || '-')}</td>
                <td>
                    <span class="status-badge ${service.enabled ? 'active' : 'disabled'}">
                        ${service.enabled ? 'Вкл.' : 'Откл.'}
                    </span>
                </td>
                <td>${service.priority}</td>
                <td>${format.date(service.last_used)}</td>
                <td>
                    <div class="action-buttons">
                        <button class="btn btn-ghost btn-sm" onclick="editCustomService(${service.id})" title="Редактировать">
                            ✏️
                        </button>
                        <button class="btn btn-ghost btn-sm" onclick="toggleService(${service.id}, ${!service.enabled})" title="${service.enabled ? 'Отключить' : 'Включить'}">
                            ${service.enabled ? '🔇' : '🔊'}
                        </button>
                        <button class="btn btn-ghost btn-sm" onclick="testService(${service.id})" title="Тест">
                            🔌
                        </button>
                        <button class="btn btn-ghost btn-sm" onclick="deleteService(${service.id}, '${escapeHtml(service.name)}')" title="Удалить">
                            🗑️
                        </button>
                    </div>
                </td>
            </tr>
        `).join('');

        // Привязка событий чекбоксов
        elements.customTable.querySelectorAll('input[type="checkbox"][data-id]').forEach(cb => {
            cb.addEventListener('change', (e) => {
                const id = parseInt(e.target.dataset.id);
                if (e.target.checked) {
                    selectedCustom.add(id);
                } else {
                    selectedCustom.delete(id);
                }
            });
        });

    } catch (error) {
        console.error('Ошибка загрузки сервисов:', error);
    }
}

// Загрузка настроек временной почты
async function loadTempmailConfig() {
    try {
        const settings = await api.get('/settings');
        if (settings.tempmail) {
            elements.tempmailApi.value = settings.tempmail.api_url || '';
            elements.tempmailEnabled.checked = settings.tempmail.enabled !== false;
        }
    } catch (error) {
        // Игнорируем ошибку
    }
}

// Импорт Outlook
async function handleOutlookImport() {
    const data = elements.outlookImportData.value.trim();
    if (!data) {
        toast.error('Введите данные для импорта');
        return;
    }

    elements.outlookImportBtn.disabled = true;
    elements.outlookImportBtn.textContent = 'Импорт...';

    try {
        const result = await api.post('/email-services/outlook/batch-import', {
            data: data,
            enabled: elements.outlookImportEnabled.checked,
            priority: parseInt(elements.outlookImportPriority.value) || 0
        });

        elements.importResult.style.display = 'block';
        elements.importResult.innerHTML = `
            <div class="import-stats">
                <span>✅ Успешно: <strong>${result.success_count || 0}</strong></span>
                <span>❌ Ошибок: <strong>${result.failed_count || 0}</strong></span>
            </div>
            ${result.errors?.length ? `
                <div class="import-errors" style="margin-top: var(--spacing-sm);">
                    <strong>Детали ошибок:</strong>
                    <ul>
                        ${result.errors.map(e => `<li>${escapeHtml(e)}</li>`).join('')}
                    </ul>
                </div>
            ` : ''}
        `;

        if (result.success_count > 0) {
            toast.success(`Успешно импортировано: ${result.success_count}`);
            loadOutlookServices();
            loadStats();
            elements.outlookImportData.value = '';
        }

    } catch (error) {
        toast.error('Ошибка импорта: ' + error.message);
    } finally {
        elements.outlookImportBtn.disabled = false;
        elements.outlookImportBtn.textContent = '📥 Начать импорт';
    }
}

// Добавление сервиса домена
async function handleAddCustom(e) {
    e.preventDefault();

    const formData = new FormData(e.target);
    const data = {
        service_type: 'custom_domain',
        name: formData.get('name'),
        config: {
            base_url: formData.get('api_url'),
            api_key: formData.get('api_key'),
            default_domain: formData.get('domain')
        },
        enabled: formData.get('enabled') === 'on',
        priority: parseInt(formData.get('priority')) || 0
    };

    try {
        await api.post('/email-services', data);
        toast.success('Сервис добавлен');
        elements.addCustomModal.classList.remove('active');
        e.target.reset();
        loadCustomServices();
        loadStats();
    } catch (error) {
        toast.error('Ошибка добавления: ' + error.message);
    }
}

// Переключение состояния сервиса
async function toggleService(id, enabled) {
    try {
        await api.patch(`/email-services/${id}`, { enabled });
        toast.success(enabled ? 'Включено' : 'Отключено');
        loadOutlookServices();
        loadCustomServices();
        loadStats();
    } catch (error) {
        toast.error('Ошибка операции: ' + error.message);
    }
}

// Тест сервиса
async function testService(id) {
    try {
        const result = await api.post(`/email-services/${id}/test`);
        if (result.success) {
            toast.success('Тест успешен');
        } else {
            toast.error('Ошибка тестирования: ' + (result.error || 'Неизвестная ошибка'));
        }
    } catch (error) {
        toast.error('Ошибка тестирования: ' + error.message);
    }
}

// Удаление сервиса
async function deleteService(id, name) {
    const confirmed = await confirm(`Удалить "${name}"?`);
    if (!confirmed) return;

    try {
        await api.delete(`/email-services/${id}`);
        toast.success('Удалено');
        selectedOutlook.delete(id);
        selectedCustom.delete(id);
        loadOutlookServices();
        loadCustomServices();
        loadStats();
    } catch (error) {
        toast.error('Ошибка удаления: ' + error.message);
    }
}

// Массовое удаление Outlook
async function handleBatchDeleteOutlook() {
    if (selectedOutlook.size === 0) return;

    const confirmed = await confirm(`Удалить ${selectedOutlook.size} выбранных аккаунтов?`);
    if (!confirmed) return;

    try {
        const result = await api.request('/email-services/outlook/batch', {
            method: 'DELETE',
            body: Array.from(selectedOutlook)
        });
        toast.success(`Удалено: ${result.deleted || selectedOutlook.size}`);
        selectedOutlook.clear();
        loadOutlookServices();
        loadStats();
    } catch (error) {
        toast.error('Ошибка удаления: ' + error.message);
    }
}

// Сохранение настроек временной почты
async function handleSaveTempmail(e) {
    e.preventDefault();

    try {
        await api.post('/settings/tempmail', {
            api_url: elements.tempmailApi.value,
            enabled: elements.tempmailEnabled.checked
        });
        toast.success('Настройки сохранены');
    } catch (error) {
        toast.error('Ошибка сохранения: ' + error.message);
    }
}

// Тест временной почты
async function handleTestTempmail() {
    elements.testTempmailBtn.disabled = true;
    elements.testTempmailBtn.textContent = 'Тестирование...';

    try {
        const result = await api.post('/email-services/test-tempmail', {
            api_url: elements.tempmailApi.value
        });

        if (result.success) {
            toast.success('Временная почта доступна');
        } else {
            toast.error('Ошибка соединения: ' + (result.error || 'Неизвестная ошибка'));
        }
    } catch (error) {
        toast.error('Ошибка тестирования: ' + error.message);
    } finally {
        elements.testTempmailBtn.disabled = false;
        elements.testTempmailBtn.textContent = '🔌 Тест соединения';
    }
}

// Обновление кнопок массовых операций
function updateBatchButtons() {
    const count = selectedOutlook.size;
    elements.batchDeleteOutlookBtn.disabled = count === 0;
    elements.batchDeleteOutlookBtn.textContent = count > 0 ? `🗑️ Удалить (${count})` : '🗑️ Удалить выбранные';
}

// HTML-экранирование
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============== Редактирование ==============

// Редактирование сервиса домена
async function editCustomService(id) {
    try {
        const service = await api.get(`/email-services/${id}/full`);

        document.getElementById('edit-custom-id').value = service.id;
        document.getElementById('edit-custom-name').value = service.name || '';
        document.getElementById('edit-custom-api-url').value = service.config?.base_url || '';
        document.getElementById('edit-custom-api-key').value = service.config?.api_key || '';
        document.getElementById('edit-custom-domain').value = service.config?.domain || '';
        document.getElementById('edit-custom-priority').value = service.priority || 0;
        document.getElementById('edit-custom-enabled').checked = service.enabled;

        document.getElementById('edit-custom-api-key').placeholder = service.config?.has_api_key ? 'Установлено, оставьте пустым' : 'API Key';

        elements.editCustomModal.classList.add('active');

    } catch (error) {
        toast.error('Ошибка получения данных: ' + error.message);
    }
}

// Сохранение редактирования сервиса домена
async function handleEditCustom(e) {
    e.preventDefault();

    const id = document.getElementById('edit-custom-id').value;
    const formData = new FormData(e.target);

    const updateData = {
        name: formData.get('name'),
        priority: parseInt(formData.get('priority')) || 0,
        enabled: formData.get('enabled') === 'on'
    };

    const config = {
        base_url: formData.get('api_url'),
        default_domain: formData.get('domain')
    };

    const apiKey = formData.get('api_key');
    if (apiKey && apiKey.trim()) {
        config.api_key = apiKey.trim();
    }

    updateData.config = config;

    try {
        await api.patch(`/email-services/${id}`, updateData);
        toast.success('Сервис обновлён');
        elements.editCustomModal.classList.remove('active');
        loadCustomServices();
        loadStats();
    } catch (error) {
        toast.error('Ошибка обновления: ' + error.message);
    }
}

// Редактирование Outlook-сервиса
async function editOutlookService(id) {
    try {
        const service = await api.get(`/email-services/${id}/full`);

        document.getElementById('edit-outlook-id').value = service.id;
        document.getElementById('edit-outlook-email').value = service.config?.email || service.name || '';
        document.getElementById('edit-outlook-password').value = '';
        document.getElementById('edit-outlook-password').placeholder = service.config?.password ? 'Установлено, оставьте пустым' : 'Введите пароль';
        document.getElementById('edit-outlook-client-id').value = service.config?.client_id || '';
        document.getElementById('edit-outlook-refresh-token').value = '';
        document.getElementById('edit-outlook-refresh-token').placeholder = service.config?.refresh_token ? 'Установлено, оставьте пустым' : 'OAuth Refresh Token';
        document.getElementById('edit-outlook-priority').value = service.priority || 0;
        document.getElementById('edit-outlook-enabled').checked = service.enabled;

        elements.editOutlookModal.classList.add('active');

    } catch (error) {
        toast.error('Ошибка получения данных');
    }
}

// Сохранение редактирования Outlook-сервиса
async function handleEditOutlook(e) {
    e.preventDefault();

    const id = document.getElementById('edit-outlook-id').value;
    const formData = new FormData(e.target);

    let currentService;
    try {
        currentService = await api.get(`/email-services/${id}/full`);
    } catch (error) {
        toast.error('Ошибка получения данных');
        return;
    }

    const updateData = {
        name: formData.get('email'),
        priority: parseInt(formData.get('priority')) || 0,
        enabled: formData.get('enabled') === 'on'
    };

    const config = {
        email: formData.get('email'),
        password: formData.get('password')?.trim() || currentService.config?.password || '',
        client_id: formData.get('client_id')?.trim() || currentService.config?.client_id || '',
        refresh_token: formData.get('refresh_token')?.trim() || currentService.config?.refresh_token || ''
    };

    updateData.config = config;

    try {
        await api.patch(`/email-services/${id}`, updateData);
        toast.success('Аккаунт обновлён');
        elements.editOutlookModal.classList.remove('active');
        loadOutlookServices();
        loadStats();
    } catch (error) {
        toast.error('Ошибка обновления: ' + error.message);
    }
}
