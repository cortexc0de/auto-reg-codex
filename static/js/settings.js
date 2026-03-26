/**
 * JavaScript страницы настроек
 * Использует библиотеку утилит из utils.js
 */

// DOM-элементы
const elements = {
    tabs: document.querySelectorAll('.tab-btn'),
    tabContents: document.querySelectorAll('.tab-content'),
    proxyForm: document.getElementById('proxy-form'),
    registrationForm: document.getElementById('registration-settings-form'),
    testProxyBtn: document.getElementById('test-proxy-btn'),
    backupBtn: document.getElementById('backup-btn'),
    cleanupBtn: document.getElementById('cleanup-btn'),
    addEmailServiceBtn: document.getElementById('add-email-service-btn'),
    addServiceModal: document.getElementById('add-service-modal'),
    addServiceForm: document.getElementById('add-service-form'),
    closeServiceModal: document.getElementById('close-service-modal'),
    cancelAddService: document.getElementById('cancel-add-service'),
    serviceType: document.getElementById('service-type'),
    serviceConfigFields: document.getElementById('service-config-fields'),
    emailServicesTable: document.getElementById('email-services-table'),
    // Импорт Outlook
    toggleImportBtn: document.getElementById('toggle-import-btn'),
    outlookImportBody: document.getElementById('outlook-import-body'),
    outlookImportBtn: document.getElementById('outlook-import-btn'),
    clearImportBtn: document.getElementById('clear-import-btn'),
    outlookImportData: document.getElementById('outlook-import-data'),
    importResult: document.getElementById('import-result'),
    // Массовые операции
    selectAllServices: document.getElementById('select-all-services'),
    // Список прокси
    proxiesTable: document.getElementById('proxies-table'),
    addProxyBtn: document.getElementById('add-proxy-btn'),
    testAllProxiesBtn: document.getElementById('test-all-proxies-btn'),
    bulkImportProxiesBtn: document.getElementById('bulk-import-proxies-btn'),
    bulkImportProxyModal: document.getElementById('bulk-import-proxy-modal'),
    closeBulkImportModal: document.getElementById('close-bulk-import-modal'),
    cancelBulkImportBtn: document.getElementById('cancel-bulk-import-btn'),
    doBulkImportBtn: document.getElementById('do-bulk-import-btn'),
    addProxyModal: document.getElementById('add-proxy-modal'),
    proxyItemForm: document.getElementById('proxy-item-form'),
    closeProxyModal: document.getElementById('close-proxy-modal'),
    cancelProxyBtn: document.getElementById('cancel-proxy-btn'),
    proxyModalTitle: document.getElementById('proxy-modal-title'),
    // Настройки динамического прокси
    dynamicProxyForm: document.getElementById('dynamic-proxy-form'),
    testDynamicProxyBtn: document.getElementById('test-dynamic-proxy-btn'),
    // Настройки CPA
    cpaForm: document.getElementById('cpa-form'),
    testCpaBtn: document.getElementById('test-cpa-btn'),
    // Настройки Team Manager
    tmForm: document.getElementById('tm-form'),
    testTmBtn: document.getElementById('test-tm-btn'),
    // Настройки Abuzovo
    abuzovoForm: document.getElementById('abuzovo-form'),
    testAbuzvoBtn: document.getElementById('test-abuzovo-btn'),
    // Настройки AxiomLauncher
    axiomlaucherForm: document.getElementById('axiomlauncher-form'),
    testAxiomlauncherBtn: document.getElementById('test-axiomlauncher-btn'),
    // Настройки кода подтверждения
    emailCodeForm: document.getElementById('email-code-form'),
    // Настройки Outlook
    outlookSettingsForm: document.getElementById('outlook-settings-form')
};

// Выбранные ID сервисов
let selectedServiceIds = new Set();

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    loadSettings();
    loadEmailServices();
    loadDatabaseInfo();
    loadProxies();
    initEventListeners();
});

// Инициализация вкладок
function initTabs() {
    elements.tabs.forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;

            elements.tabs.forEach(b => b.classList.remove('active'));
            elements.tabContents.forEach(c => c.classList.remove('active'));

            btn.classList.add('active');
            document.getElementById(`${tab}-tab`).classList.add('active');
        });
    });
}

// Обработчики событий
function initEventListeners() {
    // Форма прокси
    if (elements.proxyForm) {
        elements.proxyForm.addEventListener('submit', handleSaveProxy);
    }

    // Тест прокси
    if (elements.testProxyBtn) {
        elements.testProxyBtn.addEventListener('click', handleTestProxy);
    }

    // Форма настроек регистрации
    if (elements.registrationForm) {
        elements.registrationForm.addEventListener('submit', handleSaveRegistration);
    }

    // Резервное копирование БД
    if (elements.backupBtn) {
        elements.backupBtn.addEventListener('click', handleBackup);
    }

    // Очистка данных
    if (elements.cleanupBtn) {
        elements.cleanupBtn.addEventListener('click', handleCleanup);
    }

    // Добавление почтового сервиса
    if (elements.addEmailServiceBtn) {
        elements.addEmailServiceBtn.addEventListener('click', () => {
            elements.addServiceModal.classList.add('active');
            loadServiceConfigFields(elements.serviceType.value);
        });
    }

    if (elements.closeServiceModal) {
        elements.closeServiceModal.addEventListener('click', () => {
            elements.addServiceModal.classList.remove('active');
        });
    }

    if (elements.cancelAddService) {
        elements.cancelAddService.addEventListener('click', () => {
            elements.addServiceModal.classList.remove('active');
        });
    }

    if (elements.addServiceModal) {
        elements.addServiceModal.addEventListener('click', (e) => {
            if (e.target === elements.addServiceModal) {
                elements.addServiceModal.classList.remove('active');
            }
        });
    }

    // Переключение типа сервиса
    if (elements.serviceType) {
        elements.serviceType.addEventListener('change', (e) => {
            loadServiceConfigFields(e.target.value);
        });
    }

    // Форма добавления сервиса
    if (elements.addServiceForm) {
        elements.addServiceForm.addEventListener('submit', handleAddService);
    }

    // Импорт Outlook: свернуть/развернуть
    if (elements.toggleImportBtn) {
        elements.toggleImportBtn.addEventListener('click', () => {
            const isHidden = elements.outlookImportBody.style.display === 'none';
            elements.outlookImportBody.style.display = isHidden ? 'block' : 'none';
            elements.toggleImportBtn.textContent = isHidden ? 'Свернуть' : 'Развернуть';
        });
    }

    // Массовый импорт Outlook
    if (elements.outlookImportBtn) {
        elements.outlookImportBtn.addEventListener('click', handleOutlookBatchImport);
    }

    // Очистка данных импорта
    if (elements.clearImportBtn) {
        elements.clearImportBtn.addEventListener('click', () => {
            elements.outlookImportData.value = '';
            elements.importResult.style.display = 'none';
        });
    }

    // Выбрать все / снять выделение
    if (elements.selectAllServices) {
        elements.selectAllServices.addEventListener('change', (e) => {
            const checkboxes = document.querySelectorAll('.service-checkbox');
            checkboxes.forEach(cb => cb.checked = e.target.checked);
            updateSelectedServices();
        });
    }

    // Список прокси
    if (elements.addProxyBtn) {
        elements.addProxyBtn.addEventListener('click', () => openProxyModal());
    }

    if (elements.testAllProxiesBtn) {
        elements.testAllProxiesBtn.addEventListener('click', handleTestAllProxies);
    }

    if (elements.closeProxyModal) {
        elements.closeProxyModal.addEventListener('click', closeProxyModal);
    }

    if (elements.cancelProxyBtn) {
        elements.cancelProxyBtn.addEventListener('click', closeProxyModal);
    }

    if (elements.addProxyModal) {
        elements.addProxyModal.addEventListener('click', (e) => {
            if (e.target === elements.addProxyModal) {
                closeProxyModal();
            }
        });
    }

    if (elements.proxyItemForm) {
        elements.proxyItemForm.addEventListener('submit', handleSaveProxyItem);
    }

    // Быстрая вставка прокси (модал)
    const quickPaste = document.getElementById('proxy-quick-paste');
    if (quickPaste) {
        quickPaste.addEventListener('input', handleProxyQuickPaste);
    }

    // Быстрая вставка прокси (форма по умолчанию)
    const quickInput = document.getElementById('proxy-quick-input');
    if (quickInput) {
        quickInput.addEventListener('input', (e) => {
            const value = e.target.value.trim();
            if (!value) return;
            const parsed = parseProxyStringClient(value);
            if (parsed) {
                document.getElementById('proxy-type').value = parsed.type;
                document.getElementById('proxy-host').value = parsed.host;
                document.getElementById('proxy-port').value = parsed.port;
                document.getElementById('proxy-username').value = parsed.username || '';
                document.getElementById('proxy-password').value = parsed.password || '';
                document.getElementById('proxy-enabled').checked = true;
                e.target.style.borderColor = 'var(--success)';
            }
        });
    }

    // Массовый импорт прокси
    if (elements.bulkImportProxiesBtn) {
        elements.bulkImportProxiesBtn.addEventListener('click', openBulkImportModal);
    }
    if (elements.closeBulkImportModal) {
        elements.closeBulkImportModal.addEventListener('click', closeBulkImportModal);
    }
    if (elements.cancelBulkImportBtn) {
        elements.cancelBulkImportBtn.addEventListener('click', closeBulkImportModal);
    }
    if (elements.doBulkImportBtn) {
        elements.doBulkImportBtn.addEventListener('click', bulkImportProxies);
    }
    if (elements.bulkImportProxyModal) {
        elements.bulkImportProxyModal.addEventListener('click', (e) => {
            if (e.target === elements.bulkImportProxyModal) {
                closeBulkImportModal();
            }
        });
    }

    // Настройки динамического прокси
    if (elements.dynamicProxyForm) {
        elements.dynamicProxyForm.addEventListener('submit', handleSaveDynamicProxy);
    }
    if (elements.testDynamicProxyBtn) {
        elements.testDynamicProxyBtn.addEventListener('click', handleTestDynamicProxy);
    }

    // Настройки CPA
    if (elements.cpaForm) {
        elements.cpaForm.addEventListener('submit', handleSaveCpa);
    }

    if (elements.testCpaBtn) {
        elements.testCpaBtn.addEventListener('click', handleTestCpa);
    }

    // Настройки кода подтверждения
    if (elements.emailCodeForm) {
        elements.emailCodeForm.addEventListener('submit', handleSaveEmailCode);
    }

    // Настройки Outlook
    if (elements.outlookSettingsForm) {
        elements.outlookSettingsForm.addEventListener('submit', handleSaveOutlookSettings);
    }

    // Настройки Team Manager
    if (elements.tmForm) {
        elements.tmForm.addEventListener('submit', handleSaveTm);
    }
    if (elements.testTmBtn) {
        elements.testTmBtn.addEventListener('click', handleTestTm);
    }

    // Настройки Abuzovo
    if (elements.abuzovoForm) {
        elements.abuzovoForm.addEventListener('submit', handleSaveAbuzovo);
    }
    if (elements.testAbuzvoBtn) {
        elements.testAbuzvoBtn.addEventListener('click', handleTestAbuzovo);
    }

    // Настройки AxiomLauncher
    if (elements.axiomlaucherForm) {
        elements.axiomlaucherForm.addEventListener('submit', handleSaveAxiomLauncher);
    }
    if (elements.testAxiomlauncherBtn) {
        elements.testAxiomlauncherBtn.addEventListener('click', handleTestAxiomLauncher);
    }
}

// Загрузка настроек
async function loadSettings() {
    try {
        const data = await api.get('/settings');

        // Настройки прокси
        document.getElementById('proxy-enabled').checked = data.proxy?.enabled || false;
        document.getElementById('proxy-type').value = data.proxy?.type || 'http';
        document.getElementById('proxy-host').value = data.proxy?.host || '127.0.0.1';
        document.getElementById('proxy-port').value = data.proxy?.port || 7890;
        document.getElementById('proxy-username').value = data.proxy?.username || '';

        // Настройки динамического прокси
        document.getElementById('dynamic-proxy-enabled').checked = data.proxy?.dynamic_enabled || false;
        document.getElementById('dynamic-proxy-api-url').value = data.proxy?.dynamic_api_url || '';
        document.getElementById('dynamic-proxy-api-key-header').value = data.proxy?.dynamic_api_key_header || 'X-API-Key';
        document.getElementById('dynamic-proxy-result-field').value = data.proxy?.dynamic_result_field || '';

        // Настройки регистрации
        document.getElementById('max-retries').value = data.registration?.max_retries || 3;
        document.getElementById('timeout').value = data.registration?.timeout || 120;
        document.getElementById('password-length').value = data.registration?.default_password_length || 12;
        document.getElementById('sleep-min').value = data.registration?.sleep_min || 5;
        document.getElementById('sleep-max').value = data.registration?.sleep_max || 30;

        // Настройки ожидания кода подтверждения
        if (data.email_code) {
            document.getElementById('email-code-timeout').value = data.email_code.timeout || 120;
            document.getElementById('email-code-poll-interval').value = data.email_code.poll_interval || 3;
        }

        // Загрузка настроек CPA
        loadCpaSettings();
        // Загрузка настроек Outlook
        loadOutlookSettings();
        // Загрузка настроек Team Manager
        loadTmSettings();
        // Загрузка настроек Abuzovo
        loadAbuzovoSettings();
        // Загрузка настроек AxiomLauncher
        loadAxiomLauncherSettings();

    } catch (error) {
        console.error('Ошибка загрузки настроек:', error);
        toast.error('Ошибка загрузки настроек');
    }
}

// Загрузка почтовых сервисов
async function loadEmailServices() {
    if (!elements.emailServicesTable) return;

    try {
        const data = await api.get('/email-services');
        renderEmailServices(data.services);
    } catch (error) {
        console.error('Ошибка загрузки сервисов:', error);
        if (elements.emailServicesTable) {
            elements.emailServicesTable.innerHTML = `
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
}

// Отрисовка почтовых сервисов
function renderEmailServices(services) {
    if (!elements.emailServicesTable) return;

    if (services.length === 0) {
        elements.emailServicesTable.innerHTML = `
            <tr>
                <td colspan="7">
                    <div class="empty-state">
                        <div class="empty-state-icon">📭</div>
                        <div class="empty-state-title">Нет настроек</div>
                        <div class="empty-state-description">Нажмите «Добавить сервис» выше</div>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    elements.emailServicesTable.innerHTML = services.map(service => `
        <tr data-service-id="${service.id}">
            <td>
                <input type="checkbox" class="service-checkbox" data-id="${service.id}"
                    onchange="updateSelectedServices()">
            </td>
            <td>${escapeHtml(service.name)}</td>
            <td>${getServiceTypeText(service.service_type)}</td>
            <td>
                <span class="status-badge ${service.enabled ? 'active' : 'disabled'}">
                    ${service.enabled ? 'Включено' : 'Отключено'}
                </span>
            </td>
            <td>${service.priority}</td>
            <td>${format.date(service.last_used)}</td>
            <td>
                <div class="action-buttons">
                    <button class="btn btn-ghost btn-sm" onclick="testService(${service.id})" title="Тест">
                        🔌
                    </button>
                    <button class="btn btn-ghost btn-sm" onclick="toggleService(${service.id}, ${!service.enabled})" title="${service.enabled ? 'Отключить' : 'Включить'}">
                        ${service.enabled ? '🔒' : '🔓'}
                    </button>
                    <button class="btn btn-ghost btn-sm" onclick="deleteService(${service.id})" title="Удалить">
                        🗑️
                    </button>
                </div>
            </td>
        </tr>
    `).join('');
}

// Загрузка информации о БД
async function loadDatabaseInfo() {
    try {
        const data = await api.get('/settings/database');

        document.getElementById('db-size').textContent = `${data.database_size_mb} MB`;
        document.getElementById('db-accounts').textContent = format.number(data.accounts_count);
        document.getElementById('db-services').textContent = format.number(data.email_services_count);
        document.getElementById('db-tasks').textContent = format.number(data.tasks_count);

    } catch (error) {
        console.error('Ошибка загрузки информации о БД:', error);
    }
}

// Сохранение настроек прокси
async function handleSaveProxy(e) {
    e.preventDefault();

    const data = {
        enabled: document.getElementById('proxy-enabled').checked,
        type: document.getElementById('proxy-type').value,
        host: document.getElementById('proxy-host').value,
        port: parseInt(document.getElementById('proxy-port').value),
        username: document.getElementById('proxy-username').value || null,
        password: document.getElementById('proxy-password').value || null,
    };

    try {
        await api.post('/settings/proxy', data);
        toast.success('Настройки прокси сохранены');
    } catch (error) {
        toast.error('Ошибка сохранения: ' + error.message);
    }
}

// Тест прокси
async function handleTestProxy() {
    elements.testProxyBtn.disabled = true;
    elements.testProxyBtn.innerHTML = '<span class="loading-spinner"></span> Тестирование...';

    try {
        const data = {
            enabled: document.getElementById('proxy-enabled').checked,
            type: document.getElementById('proxy-type').value,
            host: document.getElementById('proxy-host').value,
            port: parseInt(document.getElementById('proxy-port').value),
            username: document.getElementById('proxy-username').value || null,
            password: document.getElementById('proxy-password').value || null,
        };

        const result = await api.post('/settings/proxy/test', data);

        if (result.success) {
            toast.success(result.message);
        } else {
            toast.error(result.message);
        }
    } catch (error) {
        toast.error('Ошибка тестирования: ' + error.message);
    } finally {
        elements.testProxyBtn.disabled = false;
        elements.testProxyBtn.textContent = '🔌 Тест соединения';
    }
}

// Сохранение настроек регистрации
async function handleSaveRegistration(e) {
    e.preventDefault();

    const data = {
        max_retries: parseInt(document.getElementById('max-retries').value),
        timeout: parseInt(document.getElementById('timeout').value),
        default_password_length: parseInt(document.getElementById('password-length').value),
        sleep_min: parseInt(document.getElementById('sleep-min').value),
        sleep_max: parseInt(document.getElementById('sleep-max').value),
    };

    try {
        await api.post('/settings/registration', data);
        toast.success('Настройки регистрации сохранены');
    } catch (error) {
        toast.error('Ошибка сохранения: ' + error.message);
    }
}

// Сохранение настроек кода подтверждения
async function handleSaveEmailCode(e) {
    e.preventDefault();

    const timeout = parseInt(document.getElementById('email-code-timeout').value);
    const pollInterval = parseInt(document.getElementById('email-code-poll-interval').value);

    // Валидация на клиенте
    if (timeout < 30 || timeout > 600) {
        toast.error('Таймаут должен быть 30-600 сек');
        return;
    }
    if (pollInterval < 1 || pollInterval > 30) {
        toast.error('Интервал должен быть 1-30 сек');
        return;
    }

    const data = {
        timeout: timeout,
        poll_interval: pollInterval
    };

    try {
        await api.post('/settings/email-code', data);
        toast.success('Настройки кода подтверждения сохранены');
    } catch (error) {
        toast.error('Ошибка сохранения: ' + error.message);
    }
}

// Резервное копирование БД
async function handleBackup() {
    elements.backupBtn.disabled = true;
    elements.backupBtn.innerHTML = '<span class="loading-spinner"></span> Резервное копирование...';

    try {
        const data = await api.post('/settings/database/backup');
        toast.success(`Резервная копия создана: ${data.backup_path}`);
    } catch (error) {
        toast.error('Ошибка резервного копирования: ' + error.message);
    } finally {
        elements.backupBtn.disabled = false;
        elements.backupBtn.textContent = '💾 Резервная копия БД';
    }
}

// Очистка данных
async function handleCleanup() {
    const confirmed = await confirm('Очистить устаревшие данные? Это действие необратимо.');
    if (!confirmed) return;

    elements.cleanupBtn.disabled = true;
    elements.cleanupBtn.innerHTML = '<span class="loading-spinner"></span> Очистка...';

    try {
        const data = await api.post('/settings/database/cleanup?days=30');
        toast.success(data.message);
        loadDatabaseInfo();
    } catch (error) {
        toast.error('Ошибка очистки: ' + error.message);
    } finally {
        elements.cleanupBtn.disabled = false;
        elements.cleanupBtn.textContent = '🧹 Очистить устаревшие';
    }
}

// Загрузка полей конфигурации сервиса
async function loadServiceConfigFields(serviceType) {
    try {
        const data = await api.get('/email-services/types');
        const typeInfo = data.types.find(t => t.value === serviceType);

        if (!typeInfo) {
            elements.serviceConfigFields.innerHTML = '';
            return;
        }

        elements.serviceConfigFields.innerHTML = typeInfo.config_fields.map(field => `
            <div class="form-group">
                <label for="config-${field.name}">${field.label}</label>
                <input type="${field.name.includes('password') || field.name.includes('token') ? 'password' : 'text'}"
                       id="config-${field.name}"
                       name="${field.name}"
                       value="${field.default || ''}"
                       placeholder="${field.label}"
                       ${field.required ? 'required' : ''}>
            </div>
        `).join('');

    } catch (error) {
        console.error('Ошибка загрузки полей:', error);
    }
}

// Добавление почтового сервиса
async function handleAddService(e) {
    e.preventDefault();

    const formData = new FormData(elements.addServiceForm);
    const config = {};

    elements.serviceConfigFields.querySelectorAll('input').forEach(input => {
        config[input.name] = input.value;
    });

    const data = {
        service_type: formData.get('service_type'),
        name: formData.get('name'),
        config: config,
        enabled: true,
        priority: 0,
    };

    try {
        await api.post('/email-services', data);
        toast.success('Почтовый сервис добавлен');
        elements.addServiceModal.classList.remove('active');
        elements.addServiceForm.reset();
        loadEmailServices();
    } catch (error) {
        toast.error('Ошибка добавления: ' + error.message);
    }
}

// Тест сервиса
async function testService(id) {
    try {
        const data = await api.post(`/email-services/${id}/test`);
        if (data.success) {
            toast.success('Соединение установлено');
        } else {
            toast.warning('Ошибка соединения: ' + data.message);
        }
    } catch (error) {
        toast.error('Ошибка тестирования: ' + error.message);
    }
}

// Переключение состояния сервиса
async function toggleService(id, enabled) {
    try {
        const endpoint = enabled ? 'enable' : 'disable';
        await api.post(`/email-services/${id}/${endpoint}`);
        toast.success(enabled ? 'Сервис включён' : 'Сервис отключён');
        loadEmailServices();
    } catch (error) {
        toast.error('Ошибка операции: ' + error.message);
    }
}

// Удаление сервиса
async function deleteService(id) {
    const confirmed = await confirm('Удалить настройки этого почтового сервиса?');
    if (!confirmed) return;

    try {
        await api.delete(`/email-services/${id}`);
        toast.success('Сервис удалён');
        loadEmailServices();
    } catch (error) {
        toast.error('Ошибка удаления: ' + error.message);
    }
}

// Обновление выбранных сервисов
function updateSelectedServices() {
    selectedServiceIds.clear();
    document.querySelectorAll('.service-checkbox:checked').forEach(cb => {
        selectedServiceIds.add(parseInt(cb.dataset.id));
    });
}

// Массовый импорт Outlook
async function handleOutlookBatchImport() {
    const data = elements.outlookImportData.value.trim();
    if (!data) {
        toast.warning('Введите данные для импорта');
        return;
    }

    const enabled = document.getElementById('outlook-import-enabled').checked;
    const priority = parseInt(document.getElementById('outlook-import-priority').value) || 0;

    // Разбор данных
    const lines = data.split('\n').filter(line => line.trim() && !line.trim().startsWith('#'));
    const accounts = [];
    const errors = [];

    lines.forEach((line, index) => {
        const parts = line.split('----').map(p => p.trim());
        if (parts.length < 2) {
            errors.push(`Ошибка формата в строке ${index + 1}`);
            return;
        }

        const account = {
            email: parts[0],
            password: parts[1],
            client_id: parts[2] || null,
            refresh_token: parts[3] || null,
            enabled: enabled,
            priority: priority
        };

        if (!account.email.includes('@')) {
            errors.push(`Неверный формат email в строке ${index + 1}: ${account.email}`);
            return;
        }

        accounts.push(account);
    });

    if (errors.length > 0) {
        elements.importResult.style.display = 'block';
        elements.importResult.innerHTML = `
            <div class="import-errors">${errors.map(e => `<div>${e}</div>`).join('')}</div>
        `;
        return;
    }

    elements.outlookImportBtn.disabled = true;
    elements.outlookImportBtn.innerHTML = '<span class="loading-spinner"></span> Импорт...';

    let successCount = 0;
    let failCount = 0;

    try {
        for (const account of accounts) {
            try {
                await api.post('/email-services', {
                    service_type: 'outlook',
                    name: account.email,
                    config: {
                        email: account.email,
                        password: account.password,
                        client_id: account.client_id,
                        refresh_token: account.refresh_token
                    },
                    enabled: account.enabled,
                    priority: account.priority
                });
                successCount++;
            } catch {
                failCount++;
            }
        }

        elements.importResult.style.display = 'block';
        elements.importResult.innerHTML = `
            <div class="import-stats">
                <span>✅ Успешно: ${successCount}</span>
                <span>❌ Ошибок: ${failCount}</span>
            </div>
        `;

        toast.success(`Импорт завершён, успешно: ${successCount}`);
        loadEmailServices();

    } catch (error) {
        toast.error('Ошибка импорта: ' + error.message);
    } finally {
        elements.outlookImportBtn.disabled = false;
        elements.outlookImportBtn.textContent = '📥 Начать импорт';
    }
}

// HTML-экранирование
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}


// ============================================================================
// Управление списком прокси
// ============================================================================

// Загрузка списка прокси
async function loadProxies() {
    try {
        const data = await api.get('/settings/proxies');
        renderProxies(data.proxies);
    } catch (error) {
        console.error('Ошибка загрузки прокси:', error);
        elements.proxiesTable.innerHTML = `
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

// Отрисовка списка прокси
function renderProxies(proxies) {
    if (!proxies || proxies.length === 0) {
        elements.proxiesTable.innerHTML = `
            <tr>
                <td colspan="7">
                    <div class="empty-state">
                        <div class="empty-state-icon">🌐</div>
                        <div class="empty-state-title">Нет прокси</div>
                        <div class="empty-state-description">Нажмите «Добавить прокси»</div>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    elements.proxiesTable.innerHTML = proxies.map(proxy => `
        <tr data-proxy-id="${proxy.id}">
            <td>${proxy.id}</td>
            <td>${escapeHtml(proxy.name)}</td>
            <td><span class="badge">${proxy.type.toUpperCase()}</span></td>
            <td><code>${escapeHtml(proxy.host)}:${proxy.port}</code></td>
            <td>
                <span class="status-badge ${proxy.enabled ? 'active' : 'disabled'}">
                    ${proxy.enabled ? 'Включено' : 'Отключено'}
                </span>
            </td>
            <td>${format.date(proxy.last_used)}</td>
            <td>
                <div class="action-buttons">
                    <button class="btn btn-ghost btn-sm" onclick="testProxyItem(${proxy.id})" title="Тест">
                        🔌
                    </button>
                    <button class="btn btn-ghost btn-sm" onclick="editProxyItem(${proxy.id})" title="Редактировать">
                        ✏️
                    </button>
                    <button class="btn btn-ghost btn-sm" onclick="toggleProxyItem(${proxy.id}, ${!proxy.enabled})" title="${proxy.enabled ? 'Отключить' : 'Включить'}">
                        ${proxy.enabled ? '🔒' : '🔓'}
                    </button>
                    <button class="btn btn-ghost btn-sm" onclick="deleteProxyItem(${proxy.id})" title="Удалить">
                        🗑️
                    </button>
                </div>
            </td>
        </tr>
    `).join('');
}

// Открытие модального окна прокси
function openProxyModal(proxy = null) {
    elements.proxyModalTitle.textContent = proxy ? 'Редактировать прокси' : 'Добавить прокси';
    elements.proxyItemForm.reset();

    document.getElementById('proxy-item-id').value = proxy ? proxy.id : '';

    if (proxy) {
        document.getElementById('proxy-item-name').value = proxy.name || '';
        document.getElementById('proxy-item-type').value = proxy.type || 'http';
        document.getElementById('proxy-item-host').value = proxy.host || '';
        document.getElementById('proxy-item-port').value = proxy.port || '';
        document.getElementById('proxy-item-username').value = proxy.username || '';
        document.getElementById('proxy-item-password').value = '';
    }

    elements.addProxyModal.classList.add('active');
}

// Закрытие модального окна прокси
function closeProxyModal() {
    elements.addProxyModal.classList.remove('active');
    elements.proxyItemForm.reset();
}

// Сохранение прокси
async function handleSaveProxyItem(e) {
    e.preventDefault();

    const proxyId = document.getElementById('proxy-item-id').value;
    const data = {
        name: document.getElementById('proxy-item-name').value,
        type: document.getElementById('proxy-item-type').value,
        host: document.getElementById('proxy-item-host').value,
        port: parseInt(document.getElementById('proxy-item-port').value),
        username: document.getElementById('proxy-item-username').value || null,
        password: document.getElementById('proxy-item-password').value || null,
        enabled: true
    };

    try {
        if (proxyId) {
            await api.patch(`/settings/proxies/${proxyId}`, data);
            toast.success('Прокси обновлён');
        } else {
            await api.post('/settings/proxies', data);
            toast.success('Прокси добавлен');
        }
        closeProxyModal();
        loadProxies();
    } catch (error) {
        toast.error('Ошибка сохранения: ' + error.message);
    }
}

// Редактирование прокси
async function editProxyItem(id) {
    try {
        const proxy = await api.get(`/settings/proxies/${id}`);
        openProxyModal(proxy);
    } catch (error) {
        toast.error('Ошибка получения данных прокси');
    }
}

// Тест одного прокси
async function testProxyItem(id) {
    try {
        const result = await api.post(`/settings/proxies/${id}/test`);
        if (result.success) {
            toast.success(result.message);
        } else {
            toast.error(result.message);
        }
    } catch (error) {
        toast.error('Ошибка тестирования: ' + error.message);
    }
}

// Переключение состояния прокси
async function toggleProxyItem(id, enabled) {
    try {
        const endpoint = enabled ? 'enable' : 'disable';
        await api.post(`/settings/proxies/${id}/${endpoint}`);
        toast.success(enabled ? 'Прокси включён' : 'Прокси отключён');
        loadProxies();
    } catch (error) {
        toast.error('Ошибка операции: ' + error.message);
    }
}

// Удаление прокси
async function deleteProxyItem(id) {
    const confirmed = await confirm('Удалить этот прокси?');
    if (!confirmed) return;

    try {
        await api.delete(`/settings/proxies/${id}`);
        toast.success('Прокси удалён');
        loadProxies();
    } catch (error) {
        toast.error('Ошибка удаления: ' + error.message);
    }
}

// Тест всех прокси
async function handleTestAllProxies() {
    elements.testAllProxiesBtn.disabled = true;
    elements.testAllProxiesBtn.innerHTML = '<span class="loading-spinner"></span> Тестирование...';

    try {
        const result = await api.post('/settings/proxies/test-all');
        toast.info(`Тест завершён: успешно ${result.success}, ошибок ${result.failed}`);
        loadProxies();
    } catch (error) {
        toast.error('Ошибка тестирования: ' + error.message);
    } finally {
        elements.testAllProxiesBtn.disabled = false;
        elements.testAllProxiesBtn.textContent = '🔌 Тестировать все';
    }
}

// Парсинг строки прокси (клиентский)
function parseProxyStringClient(str) {
    str = str.trim();
    if (!str) return null;

    let proxyType = 'http';
    let username = null;
    let password = null;
    let host, port;

    const schemeMatch = str.match(/^(https?|socks5h?|socks4):\/\//i);
    if (schemeMatch) {
        const scheme = schemeMatch[1].toLowerCase();
        str = str.slice(schemeMatch[0].length);
        proxyType = scheme.startsWith('socks5') ? 'socks5' : 'http';
    }

    if (str.includes('@')) {
        const atIdx = str.lastIndexOf('@');
        const authPart = str.slice(0, atIdx);
        const hostPart = str.slice(atIdx + 1);
        const colonIdx = authPart.indexOf(':');
        if (colonIdx !== -1) {
            username = authPart.slice(0, colonIdx);
            password = authPart.slice(colonIdx + 1);
        } else {
            username = authPart;
        }
        const lastColon = hostPart.lastIndexOf(':');
        if (lastColon === -1) return null;
        host = hostPart.slice(0, lastColon);
        port = parseInt(hostPart.slice(lastColon + 1));
    } else {
        const parts = str.split(':');
        if (parts.length === 2) {
            host = parts[0];
            port = parseInt(parts[1]);
        } else if (parts.length === 4) {
            host = parts[0];
            port = parseInt(parts[1]);
            username = parts[2];
            password = parts[3];
        } else {
            return null;
        }
    }

    if (!host || isNaN(port) || port < 1 || port > 65535) return null;
    return { type: proxyType, host, port, username, password };
}

// Быстрая вставка прокси
function handleProxyQuickPaste(e) {
    const value = e.target.value;
    if (!value || value.length < 5) return;

    const parsed = parseProxyStringClient(value);
    if (!parsed) return;

    document.getElementById('proxy-item-type').value = parsed.type;
    document.getElementById('proxy-item-host').value = parsed.host;
    document.getElementById('proxy-item-port').value = parsed.port;
    if (parsed.username) document.getElementById('proxy-item-username').value = parsed.username;
    if (parsed.password) document.getElementById('proxy-item-password').value = parsed.password;
    if (!document.getElementById('proxy-item-name').value) {
        document.getElementById('proxy-item-name').value = `${parsed.host}:${parsed.port}`;
    }
}

// Массовый импорт прокси — модальное окно
function openBulkImportModal() {
    document.getElementById('bulk-proxy-text').value = '';
    document.getElementById('bulk-proxy-default-type').value = 'http';
    const resultEl = document.getElementById('bulk-import-result');
    if (resultEl) { resultEl.style.display = 'none'; resultEl.innerHTML = ''; }
    elements.bulkImportProxyModal.classList.add('active');
}

function closeBulkImportModal() {
    elements.bulkImportProxyModal.classList.remove('active');
}

async function bulkImportProxies() {
    const text = document.getElementById('bulk-proxy-text').value.trim();
    if (!text) {
        toast.error('Введите список прокси');
        return;
    }

    const defaultType = document.getElementById('bulk-proxy-default-type').value;
    const btn = elements.doBulkImportBtn;
    btn.disabled = true;
    btn.innerHTML = '<span class="loading-spinner"></span> Импорт...';

    try {
        const result = await api.post('/settings/proxies/bulk-import', {
            proxies_text: text,
            default_type: defaultType
        });

        const resultEl = document.getElementById('bulk-import-result');
        let html = `<div style="padding: var(--spacing-sm); border-radius: var(--radius-sm); background: var(--bg-secondary);">`;
        html += `<strong>Результат:</strong> импортировано ${result.imported}, пропущено ${result.skipped}`;
        if (result.errors && result.errors.length > 0) {
            html += `<br><strong>Ошибки:</strong><ul style="margin: 4px 0; padding-left: 20px;">`;
            result.errors.forEach(e => { html += `<li style="color: var(--danger);">${escapeHtml(e)}</li>`; });
            html += `</ul>`;
        }
        html += `</div>`;
        resultEl.innerHTML = html;
        resultEl.style.display = 'block';

        if (result.imported > 0) {
            toast.success(`Импортировано ${result.imported} прокси`);
            loadProxies();
        }
    } catch (error) {
        toast.error('Ошибка импорта: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = '📥 Импортировать';
    }
}


// ============================================================================
// Управление настройками CPA
// ============================================================================

// Загрузка настроек CPA
async function loadCpaSettings() {
    try {
        const data = await api.get('/settings/cpa');

        document.getElementById('cpa-enabled').checked = data.enabled || false;
        document.getElementById('cpa-api-url').value = data.api_url || '';
        // Не заполняем token, только показываем наличие
        document.getElementById('cpa-api-token').value = '';
        document.getElementById('cpa-api-token').placeholder = data.has_token ? 'Настроено, оставьте пустым для сохранения' : 'Введите API Token';

    } catch (error) {
        console.error('Ошибка загрузки настроек CPA:', error);
    }
}

// Сохранение настроек CPA
async function handleSaveCpa(e) {
    e.preventDefault();

    const data = {
        enabled: document.getElementById('cpa-enabled').checked,
        api_url: document.getElementById('cpa-api-url').value,
        api_token: document.getElementById('cpa-api-token').value || ''
    };

    try {
        await api.post('/settings/cpa', data);
        toast.success('Настройки CPA сохранены');
        loadCpaSettings();
    } catch (error) {
        toast.error('Ошибка сохранения: ' + error.message);
    }
}

// ============================================================================
// Управление настройками Outlook
// ============================================================================

// Загрузка настроек Outlook
async function loadOutlookSettings() {
    try {
        const data = await api.get('/settings/outlook');
        const el = document.getElementById('outlook-default-client-id');
        if (el) el.value = data.default_client_id || '';
    } catch (error) {
        console.error('Ошибка загрузки настроек Outlook:', error);
    }
}

// Сохранение настроек Outlook
async function handleSaveOutlookSettings(e) {
    e.preventDefault();
    const data = {
        default_client_id: document.getElementById('outlook-default-client-id').value
    };
    try {
        await api.post('/settings/outlook', data);
        toast.success('Настройки Outlook сохранены');
    } catch (error) {
        toast.error('Ошибка сохранения: ' + error.message);
    }
}

// Тест соединения CPA
async function handleTestCpa() {
    const apiUrl = document.getElementById('cpa-api-url').value;
    const apiToken = document.getElementById('cpa-api-token').value;

    if (!apiUrl) {
        toast.warning('Введите API URL');
        return;
    }

    // Если token пуст, пробуем использовать сохранённый
    if (!apiToken) {
        const cpaSettings = await api.get('/settings/cpa');
        if (!cpaSettings.has_token) {
            toast.warning('Введите API Token');
            return;
        }
    }

    elements.testCpaBtn.disabled = true;
    elements.testCpaBtn.innerHTML = '<span class="loading-spinner"></span> Тестирование...';

    try {
        const result = await api.post('/settings/cpa/test', {
            api_url: apiUrl,
            api_token: apiToken || 'use_saved_token'
        });

        if (result.success) {
            toast.success(result.message);
        } else {
            toast.error(result.message);
        }
    } catch (error) {
        toast.error('Ошибка тестирования: ' + error.message);
    } finally {
        elements.testCpaBtn.disabled = false;
        elements.testCpaBtn.textContent = '🔌 Тест соединения';
    }
}

// ============== Настройки динамического прокси ==============

async function handleSaveDynamicProxy(e) {
    e.preventDefault();
    const data = {
        enabled: document.getElementById('dynamic-proxy-enabled').checked,
        api_url: document.getElementById('dynamic-proxy-api-url').value.trim(),
        api_key: document.getElementById('dynamic-proxy-api-key').value || null,
        api_key_header: document.getElementById('dynamic-proxy-api-key-header').value.trim() || 'X-API-Key',
        result_field: document.getElementById('dynamic-proxy-result-field').value.trim()
    };
    try {
        await api.post('/settings/proxy/dynamic', data);
        toast.success('Настройки динамического прокси сохранены');
        document.getElementById('dynamic-proxy-api-key').value = '';
    } catch (error) {
        toast.error('Ошибка сохранения: ' + error.message);
    }
}

async function handleTestDynamicProxy() {
    const apiUrl = document.getElementById('dynamic-proxy-api-url').value.trim();
    if (!apiUrl) {
        toast.warning('Сначала укажите адрес API');
        return;
    }
    const btn = elements.testDynamicProxyBtn;
    btn.disabled = true;
    btn.textContent = 'Тестирование...';
    try {
        const result = await api.post('/settings/proxy/dynamic/test', {
            api_url: apiUrl,
            api_key: document.getElementById('dynamic-proxy-api-key').value || null,
            api_key_header: document.getElementById('dynamic-proxy-api-key-header').value.trim() || 'X-API-Key',
            result_field: document.getElementById('dynamic-proxy-result-field').value.trim()
        });
        if (result.success) {
            toast.success(result.message);
        } else {
            toast.error(result.message);
        }
    } catch (error) {
        toast.error('Ошибка тестирования: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = '🔌 Тест динамического прокси';
    }
}

// ============== Настройки Team Manager ==============

async function loadTmSettings() {
    try {
        const data = await api.get('/settings/team-manager');
        document.getElementById('tm-enabled').checked = data.enabled || false;
        document.getElementById('tm-api-url').value = data.api_url || '';
        document.getElementById('tm-api-key').value = '';
        document.getElementById('tm-api-key').placeholder = data.has_api_key ? 'Настроено, оставьте пустым для сохранения' : 'Введите API Key';
    } catch (error) {
        console.error('Ошибка загрузки настроек TM:', error);
    }
}

async function handleSaveTm(e) {
    e.preventDefault();
    const data = {
        enabled: document.getElementById('tm-enabled').checked,
        api_url: document.getElementById('tm-api-url').value,
        api_key: document.getElementById('tm-api-key').value || ''
    };
    try {
        await api.post('/settings/team-manager', data);
        toast.success('Настройки Team Manager сохранены');
        loadTmSettings();
    } catch (error) {
        toast.error('Ошибка сохранения: ' + error.message);
    }
}

// ============================================================================
// Управление настройками Abuzovo
// ============================================================================

async function loadAbuzovoSettings() {
    try {
        const data = await api.get('/settings/abuzovo');

        document.getElementById('abuzovo-enabled').checked = data.enabled || false;
        document.getElementById('abuzovo-api-url').value = data.api_url || '';
        document.getElementById('abuzovo-api-token').value = '';
        document.getElementById('abuzovo-api-token').placeholder = data.has_token ? 'Настроено, оставьте пустым для сохранения' : 'Введите API токен';
        document.getElementById('abuzovo-default-domain-id').value = data.default_domain_id || '';
        document.getElementById('abuzovo-email-type').value = data.email_type || 'random';

    } catch (error) {
        console.error('Ошибка загрузки настроек Abuzovo:', error);
    }
}

async function handleSaveAbuzovo(e) {
    e.preventDefault();

    const data = {
        enabled: document.getElementById('abuzovo-enabled').checked,
        api_url: document.getElementById('abuzovo-api-url').value,
        api_token: document.getElementById('abuzovo-api-token').value || null,
        default_domain_id: document.getElementById('abuzovo-default-domain-id').value,
        email_type: document.getElementById('abuzovo-email-type').value,
    };

    try {
        await api.post('/settings/abuzovo', data);
        toast.success('Настройки Abuzovo сохранены');
        loadAbuzovoSettings();
    } catch (error) {
        toast.error('Ошибка сохранения: ' + error.message);
    }
}

async function handleTestAbuzovo() {
    elements.testAbuzvoBtn.disabled = true;
    elements.testAbuzvoBtn.innerHTML = '<span class="loading-spinner"></span> Тестирование...';

    try {
        const result = await api.post('/settings/abuzovo/test', {});
        if (result.success) {
            toast.success(result.message);
        } else {
            toast.error(result.message);
        }
    } catch (error) {
        toast.error('Ошибка тестирования: ' + error.message);
    } finally {
        elements.testAbuzvoBtn.disabled = false;
        elements.testAbuzvoBtn.textContent = '🔌 Тест подключения';
    }
}

// ============================================================================
// Управление настройками AxiomLauncher
// ============================================================================

async function loadAxiomLauncherSettings() {
    try {
        const data = await api.get('/settings/axiomlauncher');

        document.getElementById('axiomlauncher-enabled').checked = data.enabled || false;
        document.getElementById('axiomlauncher-api-url').value = data.api_url || '';
        document.getElementById('axiomlauncher-api-token').value = '';
        document.getElementById('axiomlauncher-api-token').placeholder = data.has_token ? 'Настроено, оставьте пустым для сохранения' : 'Введите API токен';
        document.getElementById('axiomlauncher-default-domain').value = data.default_domain || '';
        document.getElementById('axiomlauncher-email-prefix').value = data.email_prefix || 'user_';

    } catch (error) {
        console.error('Ошибка загрузки настроек AxiomLauncher:', error);
    }
}

async function handleSaveAxiomLauncher(e) {
    e.preventDefault();

    const data = {
        enabled: document.getElementById('axiomlauncher-enabled').checked,
        api_url: document.getElementById('axiomlauncher-api-url').value,
        api_token: document.getElementById('axiomlauncher-api-token').value || null,
        default_domain: document.getElementById('axiomlauncher-default-domain').value,
        email_prefix: document.getElementById('axiomlauncher-email-prefix').value,
    };

    try {
        await api.post('/settings/axiomlauncher', data);
        toast.success('Настройки AxiomLauncher сохранены');
        loadAxiomLauncherSettings();
    } catch (error) {
        toast.error('Ошибка сохранения: ' + error.message);
    }
}

async function handleTestAxiomLauncher() {
    elements.testAxiomlauncherBtn.disabled = true;
    elements.testAxiomlauncherBtn.innerHTML = '<span class="loading-spinner"></span> Тестирование...';

    try {
        const result = await api.post('/settings/axiomlauncher/test', {});
        if (result.success) {
            toast.success(result.message);
        } else {
            toast.error(result.message);
        }
    } catch (error) {
        toast.error('Ошибка тестирования: ' + error.message);
    } finally {
        elements.testAxiomlauncherBtn.disabled = false;
        elements.testAxiomlauncherBtn.textContent = '🔌 Тест подключения';
    }
}

async function handleTestTm() {
    const apiUrl = document.getElementById('tm-api-url').value;
    const apiKey = document.getElementById('tm-api-key').value;

    if (!apiUrl) {
        toast.error('Сначала укажите API URL');
        return;
    }

    let keyToTest = apiKey;
    if (!keyToTest) {
        const saved = await api.get('/settings/team-manager');
        if (!saved.has_api_key) {
            toast.error('Сначала укажите API Key');
            return;
        }
        keyToTest = 'use_saved_key';
    }

    elements.testTmBtn.disabled = true;
    elements.testTmBtn.innerHTML = '<span class="loading-spinner"></span> Тестирование...';

    try {
        const result = await api.post('/settings/team-manager/test', {
            api_url: apiUrl,
            api_key: keyToTest
        });
        if (result.success) {
            toast.success(result.message);
        } else {
            toast.error(result.message);
        }
    } catch (error) {
        toast.error('Ошибка тестирования: ' + error.message);
    } finally {
        elements.testTmBtn.disabled = false;
        elements.testTmBtn.textContent = '🔌 Тест соединения';
    }
}


// ============== Настройки Workspace Manager ==============

async function loadWorkspaceSettings() {
    try {
        const data = await api.get('/settings/workspace');
        document.getElementById('ws-monitoring-enabled').checked = data.monitoring_enabled || false;
        document.getElementById('ws-monitoring-interval').value = data.monitoring_interval || 300;
        document.getElementById('ws-auto-kick-enabled').checked = data.auto_kick_enabled || false;
        document.getElementById('ws-auto-kick-duration').value = data.auto_kick_duration || 1;
        document.getElementById('ws-auto-redistribute-enabled').checked = data.auto_redistribute_enabled || false;
        document.getElementById('ws-ban-detection-enabled').checked = data.ban_detection_enabled || false;
        document.getElementById('ws-ban-keywords').value = data.ban_keywords || '[]';
        document.getElementById('ws-long-duration-days').value = data.long_duration_days || 30;
    } catch (error) {
        console.error('Ошибка загрузки настроек Workspace:', error);
    }
}

async function handleSaveWorkspace(e) {
    e.preventDefault();
    const data = {
        monitoring_enabled: document.getElementById('ws-monitoring-enabled').checked,
        monitoring_interval: parseInt(document.getElementById('ws-monitoring-interval').value) || 300,
        auto_kick_enabled: document.getElementById('ws-auto-kick-enabled').checked,
        auto_kick_duration: parseInt(document.getElementById('ws-auto-kick-duration').value) || 1,
        auto_redistribute_enabled: document.getElementById('ws-auto-redistribute-enabled').checked,
        ban_detection_enabled: document.getElementById('ws-ban-detection-enabled').checked,
        ban_keywords: document.getElementById('ws-ban-keywords').value || '[]',
        long_duration_days: parseInt(document.getElementById('ws-long-duration-days').value) || 30
    };
    try {
        await api.post('/settings/workspace', data);
        toast.success('Настройки Workspace Manager сохранены');
    } catch (error) {
        toast.error('Ошибка сохранения: ' + error.message);
    }
}

// Инициализация формы Workspace
(function initWorkspaceSettings() {
    const wsForm = document.getElementById('workspace-form');
    if (wsForm) {
        wsForm.addEventListener('submit', handleSaveWorkspace);
        loadWorkspaceSettings();
    }
})();
