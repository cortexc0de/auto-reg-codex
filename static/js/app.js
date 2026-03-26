/**
 * JavaScript страницы регистрации
 * Использует библиотеку утилит из utils.js
 */

// Состояние
let currentTask = null;
let currentBatch = null;
let logPollingInterval = null;
let batchPollingInterval = null;
let accountsPollingInterval = null;
let isBatchMode = false;
let isOutlookBatchMode = false;
let outlookAccounts = [];
let taskCompleted = false;  // задача завершена
let batchCompleted = false;  // пакетная задача завершена
let taskFinalStatus = null;  // финальный статус задачи
let batchFinalStatus = null;  // финальный статус пакетной задачи
let displayedLogs = new Set();  // дедупликация логов
let toastShown = false;  // toast уже показан
let availableServices = {
    tempmail: { available: true, services: [] },
    outlook: { available: false, services: [] },
    custom_domain: { available: false, services: [] },
    abuzovo: { available: false, services: [] },
    axiomlauncher: { available: false, services: [] }
};

// Переменные WebSocket
let webSocket = null;
let batchWebSocket = null;  // WebSocket пакетной задачи
let useWebSocket = true;  // использовать WebSocket
let wsHeartbeatInterval = null;  // таймер heartbeat
let batchWsHeartbeatInterval = null;  // таймер heartbeat пакетной задачи
let activeTaskUuid = null;   // UUID активной задачи (для переподключения)
let activeBatchId = null;    // ID активной пакетной задачи (для переподключения)

// DOM-элементы
const elements = {
    form: document.getElementById('registration-form'),
    emailService: document.getElementById('email-service'),
    regMode: document.getElementById('reg-mode'),
    regModeGroup: document.getElementById('reg-mode-group'),
    batchCountGroup: document.getElementById('batch-count-group'),
    batchCount: document.getElementById('batch-count'),
    batchOptions: document.getElementById('batch-options'),
    intervalMin: document.getElementById('interval-min'),
    intervalMax: document.getElementById('interval-max'),
    startBtn: document.getElementById('start-btn'),
    cancelBtn: document.getElementById('cancel-btn'),
    taskStatusRow: document.getElementById('task-status-row'),
    batchProgressSection: document.getElementById('batch-progress-section'),
    consoleLog: document.getElementById('console-log'),
    clearLogBtn: document.getElementById('clear-log-btn'),
    // Статус задачи
    taskId: document.getElementById('task-id'),
    taskEmail: document.getElementById('task-email'),
    taskStatus: document.getElementById('task-status'),
    taskService: document.getElementById('task-service'),
    taskStatusBadge: document.getElementById('task-status-badge'),
    // Статус пакетной задачи
    batchProgressText: document.getElementById('batch-progress-text'),
    batchProgressPercent: document.getElementById('batch-progress-percent'),
    progressBar: document.getElementById('progress-bar'),
    batchSuccess: document.getElementById('batch-success'),
    batchFailed: document.getElementById('batch-failed'),
    batchRemaining: document.getElementById('batch-remaining'),
    // Зарегистрированные аккаунты
    recentAccountsTable: document.getElementById('recent-accounts-table'),
    refreshAccountsBtn: document.getElementById('refresh-accounts-btn'),
    // Пакетная регистрация Outlook
    outlookBatchSection: document.getElementById('outlook-batch-section'),
    outlookAccountsContainer: document.getElementById('outlook-accounts-container'),
    outlookIntervalMin: document.getElementById('outlook-interval-min'),
    outlookIntervalMax: document.getElementById('outlook-interval-max'),
    outlookSkipRegistered: document.getElementById('outlook-skip-registered'),
    outlookConcurrencyMode: document.getElementById('outlook-concurrency-mode'),
    outlookConcurrencyCount: document.getElementById('outlook-concurrency-count'),
    outlookConcurrencyHint: document.getElementById('outlook-concurrency-hint'),
    outlookIntervalGroup: document.getElementById('outlook-interval-group'),
    // Управление параллелизмом
    concurrencyMode: document.getElementById('concurrency-mode'),
    concurrencyCount: document.getElementById('concurrency-count'),
    concurrencyHint: document.getElementById('concurrency-hint'),
    intervalGroup: document.getElementById('interval-group')
};

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    loadAvailableServices();
    loadRecentAccounts();
    startAccountsPolling();
    initVisibilityReconnect();
    restoreActiveTask();
});

// Обработчики событий
function initEventListeners() {
    // Отправка формы регистрации
    elements.form.addEventListener('submit', handleStartRegistration);

    // Переключение режима
    elements.regMode.addEventListener('change', handleModeChange);

    // Переключение почтового сервиса
    elements.emailService.addEventListener('change', handleServiceChange);

    // Кнопка отмены
    elements.cancelBtn.addEventListener('click', handleCancelTask);

    // Очистка журнала
    elements.clearLogBtn.addEventListener('click', () => {
        elements.consoleLog.innerHTML = '<div class="log-line info">[Система] Журнал очищен</div>';
        displayedLogs.clear();  // очистка дедупликации логов
    });

    // Обновить список аккаунтов
    elements.refreshAccountsBtn.addEventListener('click', () => {
        loadRecentAccounts();
        toast.info('Обновлено');
    });

    // Переключение режима параллелизма
    elements.concurrencyMode.addEventListener('change', () => {
        handleConcurrencyModeChange(elements.concurrencyMode, elements.concurrencyHint, elements.intervalGroup);
    });
    elements.outlookConcurrencyMode.addEventListener('change', () => {
        handleConcurrencyModeChange(elements.outlookConcurrencyMode, elements.outlookConcurrencyHint, elements.outlookIntervalGroup);
    });
}

// Загрузка доступных почтовых сервисов
async function loadAvailableServices() {
    try {
        const data = await api.get('/registration/available-services');
        availableServices = data;

        // Обновление списка сервисов
        updateEmailServiceOptions();

        addLog('info', '[Система] Список почтовых сервисов загружен');
    } catch (error) {
        console.error('Ошибка загрузки списка сервисов:', error);
        addLog('warning', '[Предупр.] Ошибка загрузки списка сервисов');
    }
}

// Обновление списка сервисов
function updateEmailServiceOptions() {
    const select = elements.emailService;
    select.innerHTML = '';

    // Tempmail
    if (availableServices.tempmail.available) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = '🌐 Временная почта';

        availableServices.tempmail.services.forEach(service => {
            const option = document.createElement('option');
            option.value = `tempmail:${service.id || 'default'}`;
            option.textContent = service.name;
            option.dataset.type = 'tempmail';
            optgroup.appendChild(option);
        });

        select.appendChild(optgroup);
    }

    // Outlook
    if (availableServices.outlook.available) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = `📧 Outlook (${availableServices.outlook.count} аккаунтов)`;

        availableServices.outlook.services.forEach(service => {
            const option = document.createElement('option');
            option.value = `outlook:${service.id}`;
            option.textContent = service.name + (service.has_oauth ? ' (OAuth)' : '');
            option.dataset.type = 'outlook';
            option.dataset.serviceId = service.id;
            optgroup.appendChild(option);
        });

        select.appendChild(optgroup);

        // Пакетная регистрация Outlook
        const batchOption = document.createElement('option');
        batchOption.value = 'outlook_batch:all';
        batchOption.textContent = `📋 Пакетная регистрация Outlook (${availableServices.outlook.count} аккаунтов)`;
        batchOption.dataset.type = 'outlook_batch';
        optgroup.appendChild(batchOption);
    } else {
        const optgroup = document.createElement('optgroup');
        optgroup.label = '📧 Outlook (не настроено)';

        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'Сначала импортируйте на стр. Почтовых сервисов';
        option.disabled = true;
        optgroup.appendChild(option);

        select.appendChild(optgroup);
    }

    // Свой домен
    if (availableServices.custom_domain.available) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = `🔗 Свой домен (${availableServices.custom_domain.count} сервисов)`;

        availableServices.custom_domain.services.forEach(service => {
            const option = document.createElement('option');
            option.value = `custom_domain:${service.id || 'default'}`;
            option.textContent = service.name;
            option.dataset.type = 'custom_domain';
            if (service.id) {
                option.dataset.serviceId = service.id;
            }
            optgroup.appendChild(option);
        });

        select.appendChild(optgroup);
    } else {
        const optgroup = document.createElement('optgroup');
        optgroup.label = '🔗 Свой домен (не настроено)';

        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'Сначала добавьте сервис на стр. Почтовых сервисов';
        option.disabled = true;
        optgroup.appendChild(option);

        select.appendChild(optgroup);
    }

    // Abuzovo
    if (availableServices.abuzovo && availableServices.abuzovo.available) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = '📨 Abuzovo';

        availableServices.abuzovo.services.forEach(service => {
            const option = document.createElement('option');
            option.value = `abuzovo:${service.id || 'default'}`;
            option.textContent = service.name;
            option.dataset.type = 'abuzovo';
            optgroup.appendChild(option);
        });

        select.appendChild(optgroup);
    }

    // AxiomLauncher
    if (availableServices.axiomlauncher && availableServices.axiomlauncher.available) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = '📧 AxiomLauncher';

        availableServices.axiomlauncher.services.forEach(service => {
            const option = document.createElement('option');
            option.value = `axiomlauncher:${service.id || 'default'}`;
            option.textContent = service.name;
            option.dataset.type = 'axiomlauncher';
            optgroup.appendChild(option);
        });

        select.appendChild(optgroup);
    }
}

// Обработка переключения сервиса
function handleServiceChange(e) {
    const value = e.target.value;
    if (!value) return;

    const [type, id] = value.split(':');
    const selectedOption = e.target.options[e.target.selectedIndex];

    // обработка режима пакетной регистрации Outlook
    if (type === 'outlook_batch') {
        isOutlookBatchMode = true;
        elements.outlookBatchSection.style.display = 'block';
        elements.regModeGroup.style.display = 'none';
        elements.batchCountGroup.style.display = 'none';
        elements.batchOptions.style.display = 'none';
        loadOutlookAccounts();
        addLog('info', '[Система] Переключено на пакетную регистрацию Outlook');
        return;
    } else {
        isOutlookBatchMode = false;
        elements.outlookBatchSection.style.display = 'none';
        elements.regModeGroup.style.display = 'block';
    }

    // Отображение информации о сервисе
    if (type === 'outlook') {
        const service = availableServices.outlook.services.find(s => s.id == id);
        if (service) {
            addLog('info', `[Система] Выбран аккаунт Outlook: ${service.name}`);
        }
    } else if (type === 'custom_domain') {
        const service = availableServices.custom_domain.services.find(s => s.id == id);
        if (service) {
            addLog('info', `[Система] Выбран сервис домена: ${service.name}`);
        }
    }
}

// Переключение режима
function handleModeChange(e) {
    const mode = e.target.value;
    isBatchMode = mode === 'batch';

    elements.batchCountGroup.style.display = isBatchMode ? 'block' : 'none';
    elements.batchOptions.style.display = isBatchMode ? 'block' : 'none';
}

// Переключение режима параллелизма (пакетный)
function handleConcurrencyModeChange(selectEl, hintEl, intervalGroupEl) {
    const mode = selectEl.value;
    if (mode === 'parallel') {
        hintEl.textContent = 'Все задачи разделяются на N параллельных пакетов';
        intervalGroupEl.style.display = 'none';
    } else {
        hintEl.textContent = 'Макс. N задач одновременно, новая каждые interval сек.';
        intervalGroupEl.style.display = 'block';
    }
}

// Начало регистрации
async function handleStartRegistration(e) {
    e.preventDefault();

    const selectedValue = elements.emailService.value;
    if (!selectedValue) {
        toast.error('Выберите почтовый сервис');
        return;
    }

    // обработка режима пакетной регистрации Outlook
    if (isOutlookBatchMode) {
        await handleOutlookBatchRegistration();
        return;
    }

    const [emailServiceType, serviceId] = selectedValue.split(':');

    // Блокировка кнопки старта
    elements.startBtn.disabled = true;
    elements.cancelBtn.disabled = false;

    // Очистка журнала
    elements.consoleLog.innerHTML = '';

    // Формирование данных запроса
    const requestData = {
        email_service_type: emailServiceType
    };

    // Передача service_id если выбран сервис из БД
    if (serviceId && serviceId !== 'default') {
        requestData.email_service_id = parseInt(serviceId);
    }

    if (isBatchMode) {
        await handleBatchRegistration(requestData);
    } else {
        await handleSingleRegistration(requestData);
    }
}

// Одиночная регистрация
async function handleSingleRegistration(requestData) {
    // Сброс статуса задачи
    taskCompleted = false;
    taskFinalStatus = null;
    displayedLogs.clear();  // очистка дедупликации логов
    toastShown = false;  // сброс флага toast

    addLog('info', '[Система] Запуск задачи регистрации...');

    try {
        const data = await api.post('/registration/start', requestData);

        currentTask = data;
        activeTaskUuid = data.task_uuid;  // сохранение для переподключения
        // сохранение в sessionStorage для восстановления
        sessionStorage.setItem('activeTask', JSON.stringify({ task_uuid: data.task_uuid, mode: 'single' }));
        addLog('info', `[Система] Задача создана: ${data.task_uuid}`);
        showTaskStatus(data);
        updateTaskStatus('running');

        // приоритет WebSocket
        connectWebSocket(data.task_uuid);

    } catch (error) {
        addLog('error', `[Ошибка] Ошибка запуска: ${error.message}`);
        toast.error(error.message);
        resetButtons();
    }
}


// ============== Функции WebSocket ==============

// Подключение WebSocket
function connectWebSocket(taskUuid) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws/task/${taskUuid}`;

    try {
        webSocket = new WebSocket(wsUrl);

        webSocket.onopen = () => {
            console.log('WebSocket подключён');
            useWebSocket = true;
            // остановка опроса если был
            stopLogPolling();
            // запуск heartbeat
            startWebSocketHeartbeat();
        };

        webSocket.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === 'log') {
                const logType = getLogType(data.message);
                addLog(logType, data.message);
            } else if (data.type === 'status') {
                updateTaskStatus(data.status);

                // проверка завершения
                if (['completed', 'failed', 'cancelled', 'cancelling'].includes(data.status)) {
                    // сохранение финального статуса
                    taskFinalStatus = data.status;
                    taskCompleted = true;

                    // отключение WebSocket
                    disconnectWebSocket();

                    // сброс кнопок после завершения
                    resetButtons();

                    // показ toast только раз
                    if (!toastShown) {
                        toastShown = true;
                        if (data.status === 'completed') {
                            addLog('success', '[Успех] Регистрация завершена!');
                            toast.success('Регистрация завершена!');
                            // Обновить список аккаунтов
                            loadRecentAccounts();
                        } else if (data.status === 'failed') {
                            addLog('error', '[Ошибка] Ошибка регистрации');
                            toast.error('Ошибка регистрации');
                        } else if (data.status === 'cancelled' || data.status === 'cancelling') {
                            addLog('warning', '[Предупр.] Задача отменена');
                        }
                    }
                }
            } else if (data.type === 'pong') {
                // ответ heartbeat, игнорируем
            }
        };

        webSocket.onclose = (event) => {
            console.log('WebSocket отключён:', event.code);
            stopWebSocketHeartbeat();

            // переход на опрос если задача не завершена
            // используем taskFinalStatus т.к. currentTask может быть сброшен
            const shouldPoll = !taskCompleted &&
                               taskFinalStatus === null;  // если есть значение — задача завершена

            if (shouldPoll && currentTask) {
                console.log('переход на опрос');
                useWebSocket = false;
                startLogPolling(currentTask.task_uuid);
            }
        };

        webSocket.onerror = (error) => {
            console.error('Ошибка WebSocket:', error);
            // переход на опрос
            useWebSocket = false;
            stopWebSocketHeartbeat();
            startLogPolling(taskUuid);
        };

    } catch (error) {
        console.error('Ошибка подключения WebSocket:', error);
        useWebSocket = false;
        startLogPolling(taskUuid);
    }
}

// Отключение WebSocket
function disconnectWebSocket() {
    stopWebSocketHeartbeat();
    if (webSocket) {
        webSocket.close();
        webSocket = null;
    }
}

// запуск heartbeat
function startWebSocketHeartbeat() {
    stopWebSocketHeartbeat();
    wsHeartbeatInterval = setInterval(() => {
        if (webSocket && webSocket.readyState === WebSocket.OPEN) {
            webSocket.send(JSON.stringify({ type: 'ping' }));
        }
    }, 25000);  // heartbeat каждые 25 сек
}

// Остановка heartbeat
function stopWebSocketHeartbeat() {
    if (wsHeartbeatInterval) {
        clearInterval(wsHeartbeatInterval);
        wsHeartbeatInterval = null;
    }
}

// Отправка запроса на отмену
function cancelViaWebSocket() {
    if (webSocket && webSocket.readyState === WebSocket.OPEN) {
        webSocket.send(JSON.stringify({ type: 'cancel' }));
    }
}

// Пакетная регистрация
async function handleBatchRegistration(requestData) {
    // сброс статуса пакетной задачи
    batchCompleted = false;
    batchFinalStatus = null;
    displayedLogs.clear();  // очистка дедупликации логов
    toastShown = false;  // сброс флага toast

    const count = parseInt(elements.batchCount.value) || 5;
    const intervalMin = parseInt(elements.intervalMin.value) || 5;
    const intervalMax = parseInt(elements.intervalMax.value) || 30;
    const concurrency = parseInt(elements.concurrencyCount.value) || 3;
    const mode = elements.concurrencyMode.value || 'pipeline';

    requestData.count = count;
    requestData.interval_min = intervalMin;
    requestData.interval_max = intervalMax;
    requestData.concurrency = Math.min(50, Math.max(1, concurrency));
    requestData.mode = mode;

    addLog('info', `[Система] Запуск пакетной регистрации (кол-во: ${count})...`);

    try {
        const data = await api.post('/registration/batch', requestData);

        currentBatch = data;
        activeBatchId = data.batch_id;  // сохранение для переподключения
        // сохранение в sessionStorage для восстановления
        sessionStorage.setItem('activeTask', JSON.stringify({ batch_id: data.batch_id, mode: 'batch', total: data.count }));
        addLog('info', `[Система] Пакетная задача создана: ${data.batch_id}`);
        addLog('info', `[Система] ${data.count} задач добавлено в очередь`);
        showBatchStatus(data);

        // приоритет WebSocket
        connectBatchWebSocket(data.batch_id);

    } catch (error) {
        addLog('error', `[Ошибка] Ошибка запуска: ${error.message}`);
        toast.error(error.message);
        resetButtons();
    }
}

// Отмена задачи
async function handleCancelTask() {
    // блокировка кнопки для предотвращения дублирования
    elements.cancelBtn.disabled = true;
    addLog('info', '[Система] Отправка запроса на отмену...');

    try {
        // отмена пакетной задачи
        if (currentBatch && (isBatchMode || isOutlookBatchMode)) {
            // приоритет отмены через WebSocket
            if (batchWebSocket && batchWebSocket.readyState === WebSocket.OPEN) {
                batchWebSocket.send(JSON.stringify({ type: 'cancel' }));
                addLog('warning', '[Предупр.] Запрос на отмену отправлен');
                toast.info('Запрос на отмену отправлен');
            } else {
                // откат на REST API
                const endpoint = isOutlookBatchMode
                    ? `/registration/outlook-batch/${currentBatch.batch_id}/cancel`
                    : `/registration/batch/${currentBatch.batch_id}/cancel`;

                await api.post(endpoint);
                addLog('warning', '[Предупр.] Запрос на отмену отправлен');
                toast.info('Запрос на отмену отправлен');
                stopBatchPolling();
                resetButtons();
            }
        }
        // отмена одиночной задачи
        else if (currentTask) {
            // приоритет отмены через WebSocket
            if (webSocket && webSocket.readyState === WebSocket.OPEN) {
                webSocket.send(JSON.stringify({ type: 'cancel' }));
                addLog('warning', '[Предупр.] Запрос на отмену отправлен');
                toast.info('Запрос на отмену отправлен');
            } else {
                // откат на REST API
                await api.post(`/registration/tasks/${currentTask.task_uuid}/cancel`);
                addLog('warning', '[Предупр.] Задача отменена');
                toast.info('Задача отменена');
                stopLogPolling();
                resetButtons();
            }
        }
        // нет активных задач
        else {
            addLog('warning', '[Предупр.] Нет активных задач для отмены');
            toast.warning('Нет активных задач');
            resetButtons();
        }
    } catch (error) {
        addLog('error', `[Ошибка] Ошибка отмены: ${error.message}`);
        toast.error(error.message);
        // восстановление кнопки для повторной попытки
        elements.cancelBtn.disabled = false;
    }
}

// Начало опроса логов
function startLogPolling(taskUuid) {
    let lastLogIndex = 0;

    logPollingInterval = setInterval(async () => {
        try {
            const data = await api.get(`/registration/tasks/${taskUuid}/logs`);

            // Обновление статуса задачи
            updateTaskStatus(data.status);

            // обновление информации о почте
            if (data.email) {
                elements.taskEmail.textContent = data.email;
            }
            if (data.email_service) {
                elements.taskService.textContent = getServiceTypeText(data.email_service);
            }

            // добавление новых логов
            const logs = data.logs || [];
            for (let i = lastLogIndex; i < logs.length; i++) {
                const log = logs[i];
                const logType = getLogType(log);
                addLog(logType, log);
            }
            lastLogIndex = logs.length;

            // проверка завершения задачи
            if (['completed', 'failed', 'cancelled'].includes(data.status)) {
                stopLogPolling();
                resetButtons();

                // показ toast только раз
                if (!toastShown) {
                    toastShown = true;
                    if (data.status === 'completed') {
                        addLog('success', '[Успех] Регистрация завершена!');
                        toast.success('Регистрация завершена!');
                        // Обновить список аккаунтов
                        loadRecentAccounts();
                    } else if (data.status === 'failed') {
                        addLog('error', '[Ошибка] Ошибка регистрации');
                        toast.error('Ошибка регистрации');
                    } else if (data.status === 'cancelled') {
                        addLog('warning', '[Предупр.] Задача отменена');
                    }
                }
            }
        } catch (error) {
            console.error('Ошибка опроса логов:', error);
        }
    }, 1000);
}

// Остановка опроса логов
function stopLogPolling() {
    if (logPollingInterval) {
        clearInterval(logPollingInterval);
        logPollingInterval = null;
    }
}

// Начало опроса статуса пакетной задачи
function startBatchPolling(batchId) {
    batchPollingInterval = setInterval(async () => {
        try {
            const data = await api.get(`/registration/batch/${batchId}`);
            updateBatchProgress(data);

            // проверка завершения
            if (data.finished) {
                stopBatchPolling();
                resetButtons();

                // показ toast только раз
                if (!toastShown) {
                    toastShown = true;
                    addLog('info', `[Завершено] Пакетная задача завершена! Успешно: ${data.success}, ошибок: ${data.failed}`);
                    if (data.success > 0) {
                        toast.success(`Пакетная регистрация завершена, успешно ${data.success} `);
                        // Обновить список аккаунтов
                        loadRecentAccounts();
                    } else {
                        toast.warning('Пакетная регистрация завершена без успешных регистраций');
                    }
                }
            }
        } catch (error) {
            console.error('Ошибка опроса статуса:', error);
        }
    }, 2000);
}

// Остановка опроса статуса
function stopBatchPolling() {
    if (batchPollingInterval) {
        clearInterval(batchPollingInterval);
        batchPollingInterval = null;
    }
}

// Отображение статуса задачи
function showTaskStatus(task) {
    elements.taskStatusRow.style.display = 'grid';
    elements.batchProgressSection.style.display = 'none';
    elements.taskStatusBadge.style.display = 'inline-flex';
    elements.taskId.textContent = task.task_uuid.substring(0, 8) + '...';
    elements.taskEmail.textContent = '-';
    elements.taskService.textContent = '-';
}

// Обновление статуса задачи
function updateTaskStatus(status) {
    const statusInfo = {
        pending: { text: 'Ожидание', class: 'pending' },
        running: { text: 'Выполняется', class: 'running' },
        completed: { text: 'Завершено', class: 'completed' },
        failed: { text: 'Ошибка', class: 'failed' },
        cancelled: { text: 'Отменено', class: 'disabled' }
    };

    const info = statusInfo[status] || { text: status, class: '' };
    elements.taskStatusBadge.textContent = info.text;
    elements.taskStatusBadge.className = `status-badge ${info.class}`;
    elements.taskStatus.textContent = info.text;
}

// Отображение статуса пакетной задачи
function showBatchStatus(batch) {
    elements.batchProgressSection.style.display = 'block';
    elements.taskStatusRow.style.display = 'none';
    elements.taskStatusBadge.style.display = 'none';
    elements.batchProgressText.textContent = `0/${batch.count}`;
    elements.batchProgressPercent.textContent = '0%';
    elements.progressBar.style.width = '0%';
    elements.batchSuccess.textContent = '0';
    elements.batchFailed.textContent = '0';
    elements.batchRemaining.textContent = batch.count;

    // сброс счётчиков
    elements.batchSuccess.dataset.last = '0';
    elements.batchFailed.dataset.last = '0';
}

// Обновление прогресса
function updateBatchProgress(data) {
    const progress = ((data.completed / data.total) * 100).toFixed(0);
    elements.batchProgressText.textContent = `${data.completed}/${data.total}`;
    elements.batchProgressPercent.textContent = `${progress}%`;
    elements.progressBar.style.width = `${progress}%`;
    elements.batchSuccess.textContent = data.success;
    elements.batchFailed.textContent = data.failed;
    elements.batchRemaining.textContent = data.total - data.completed;

    // логирование (без дублирования)
    if (data.completed > 0) {
        const lastSuccess = parseInt(elements.batchSuccess.dataset.last || '0');
        const lastFailed = parseInt(elements.batchFailed.dataset.last || '0');

        if (data.success > lastSuccess) {
            addLog('success', `[Успех] Аккаунт # ${data.success} зарегистрирован`);
        }
        if (data.failed > lastFailed) {
            addLog('error', `[Ошибка] Аккаунт #${data.failed} не зарегистрирован`);
        }

        elements.batchSuccess.dataset.last = data.success;
        elements.batchFailed.dataset.last = data.failed;
    }
}

// Загрузка недавних аккаунтов
async function loadRecentAccounts() {
    try {
        const data = await api.get('/accounts?page=1&page_size=10');

        if (data.accounts.length === 0) {
            elements.recentAccountsTable.innerHTML = `
                <tr>
                    <td colspan="5">
                        <div class="empty-state" style="padding: var(--spacing-md);">
                            <div class="empty-state-icon">📭</div>
                            <div class="empty-state-title">Нет зарегистрированных аккаунтов</div>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        elements.recentAccountsTable.innerHTML = data.accounts.map(account => `
            <tr data-id="${account.id}">
                <td>${account.id}</td>
                <td>
                    <span title="${escapeHtml(account.email)}">${escapeHtml(account.email)}</span>
                </td>
                <td class="password-cell">
                    ${account.password ? `<span class="password-hidden" title="Нажмите для просмотра">${escapeHtml(account.password.substring(0, 8))}...</span>` : '-'}
                </td>
                <td>
                    <span class="status-badge ${getStatusClass('account', account.status)}" style="font-size: 0.7rem;">
                        ${getStatusText('account', account.status)}
                    </span>
                </td>
                <td>
                    <div class="action-buttons">
                        <button class="btn btn-ghost btn-sm" onclick="copyToClipboard('${escapeHtml(account.email)}')" title="Копировать email">
                            📋
                        </button>
                        ${account.password ? `<button class="btn btn-ghost btn-sm" onclick="copyToClipboard('${escapeHtml(account.password)}')" title="Копировать пароль">🔑</button>` : ''}
                    </div>
                </td>
            </tr>
        `).join('');

    } catch (error) {
        console.error('Ошибка загрузки аккаунтов:', error);
    }
}

// Запуск опроса списка аккаунтов
function startAccountsPolling() {
    // обновление списка каждые 30 сек
    accountsPollingInterval = setInterval(() => {
        loadRecentAccounts();
    }, 30000);
}

// Добавление лога
function addLog(type, message) {
    // дедупликация по хэшу сообщения
    const logKey = `${type}:${message}`;
    if (displayedLogs.has(logKey)) {
        return;  // уже показано, пропуск
    }
    displayedLogs.add(logKey);

    // ограничение размера для предотвращения утечки памяти
    if (displayedLogs.size > 1000) {
        // очистка половины записей
        const keys = Array.from(displayedLogs);
        keys.slice(0, 500).forEach(k => displayedLogs.delete(k));
    }

    const line = document.createElement('div');
    line.className = `log-line ${type}`;

    // добавление метки времени
    const timestamp = new Date().toLocaleTimeString('ru-RU', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    line.innerHTML = `<span class="timestamp">[${timestamp}]</span>${escapeHtml(message)}`;
    elements.consoleLog.appendChild(line);

    // автопрокрутка вниз
    elements.consoleLog.scrollTop = elements.consoleLog.scrollHeight;

    // ограничение количества строк
    const lines = elements.consoleLog.querySelectorAll('.log-line');
    if (lines.length > 500) {
        lines[0].remove();
    }
}

// Определение типа лога
function getLogType(log) {
    if (typeof log !== 'string') return 'info';

    const lowerLog = log.toLowerCase();
    if (lowerLog.includes('error') || lowerLog.includes('Ошибка') || lowerLog.includes('ошибка')) {
        return 'error';
    }
    if (lowerLog.includes('warning') || lowerLog.includes('предупреждение')) {
        return 'warning';
    }
    if (lowerLog.includes('success') || lowerLog.includes('успех') || lowerLog.includes('завершено')) {
        return 'success';
    }
    return 'info';
}

// Сброс состояния кнопок
function resetButtons() {
    elements.startBtn.disabled = false;
    elements.cancelBtn.disabled = true;
    currentTask = null;
    currentBatch = null;
    isBatchMode = false;
    // сброс флагов завершения
    taskCompleted = false;
    batchCompleted = false;
    // сброс флагов финального статуса
    taskFinalStatus = null;
    batchFinalStatus = null;
    // очистка идентификаторов активных задач
    activeTaskUuid = null;
    activeBatchId = null;
    // очистка sessionStorage
    sessionStorage.removeItem('activeTask');
    // Отключение WebSocket
    disconnectWebSocket();
    disconnectBatchWebSocket();
    // не сбрасываем isOutlookBatchMode — пользователь может продолжить
}

// Экранирование HTML
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}


// ============== Функция пакетной регистрации Outlook ==============

// Загрузка списка аккаунтов Outlook
async function loadOutlookAccounts() {
    try {
        elements.outlookAccountsContainer.innerHTML = '<div class="loading-placeholder" style="text-align: center; padding: var(--spacing-md); color: var(--text-muted);">Загрузка...</div>';

        const data = await api.get('/registration/outlook-accounts');
        outlookAccounts = data.accounts || [];

        renderOutlookAccountsList();

        addLog('info', `[Система] Загружено ${data.total} аккаунтов Outlook (зарег.: ${data.registered_count}, незарег.: ${data.unregistered_count})`);

    } catch (error) {
        console.error('Ошибка загрузки аккаунтов Outlook:', error);
        elements.outlookAccountsContainer.innerHTML = `<div style="text-align: center; padding: var(--spacing-md); color: var(--text-muted);">Ошибка загрузки: ${error.message}</div>`;
        addLog('error', `[Ошибка] Ошибка загрузки аккаунтов Outlook: ${error.message}`);
    }
}

// Рендеринг списка аккаунтов Outlook
function renderOutlookAccountsList() {
    if (outlookAccounts.length === 0) {
        elements.outlookAccountsContainer.innerHTML = '<div style="text-align: center; padding: var(--spacing-md); color: var(--text-muted);">Нет доступных аккаунтов Outlook</div>';
        return;
    }

    const html = outlookAccounts.map(account => `
        <label class="outlook-account-item" style="display: flex; align-items: center; padding: var(--spacing-sm); border-bottom: 1px solid var(--border-light); cursor: pointer; ${account.is_registered ? 'opacity: 0.6;' : ''}" data-id="${account.id}" data-registered="${account.is_registered}">
            <input type="checkbox" class="outlook-account-checkbox" value="${account.id}" ${account.is_registered ? '' : 'checked'} style="margin-right: var(--spacing-sm);">
            <div style="flex: 1;">
                <div style="font-weight: 500;">${escapeHtml(account.email)}</div>
                <div style="font-size: 0.75rem; color: var(--text-muted);">
                    ${account.is_registered
                        ? `<span style="color: var(--success-color);">✓ Зарегистрирован</span>`
                        : '<span style="color: var(--primary-color);">Не зарегистрирован</span>'
                    }
                    ${account.has_oauth ? ' | OAuth' : ''}
                </div>
            </div>
        </label>
    `).join('');

    elements.outlookAccountsContainer.innerHTML = html;
}

// Выбрать все
function selectAllOutlookAccounts() {
    const checkboxes = document.querySelectorAll('.outlook-account-checkbox');
    checkboxes.forEach(cb => cb.checked = true);
}

// только незарегистрированные
function selectUnregisteredOutlook() {
    const items = document.querySelectorAll('.outlook-account-item');
    items.forEach(item => {
        const checkbox = item.querySelector('.outlook-account-checkbox');
        const isRegistered = item.dataset.registered === 'true';
        checkbox.checked = !isRegistered;
    });
}

// Снять выделение
function deselectAllOutlookAccounts() {
    const checkboxes = document.querySelectorAll('.outlook-account-checkbox');
    checkboxes.forEach(cb => cb.checked = false);
}

// обработка пакетной регистрации Outlook
async function handleOutlookBatchRegistration() {
    // сброс статуса пакетной задачи
    batchCompleted = false;
    batchFinalStatus = null;
    displayedLogs.clear();  // очистка дедупликации логов
    toastShown = false;  // сброс флага toast

    // получение выбранных аккаунтов
    const selectedIds = [];
    document.querySelectorAll('.outlook-account-checkbox:checked').forEach(cb => {
        selectedIds.push(parseInt(cb.value));
    });

    if (selectedIds.length === 0) {
        toast.error('Выберите хотя бы один аккаунт Outlook');
        return;
    }

    const intervalMin = parseInt(elements.outlookIntervalMin.value) || 5;
    const intervalMax = parseInt(elements.outlookIntervalMax.value) || 30;
    const skipRegistered = elements.outlookSkipRegistered.checked;
    const concurrency = parseInt(elements.outlookConcurrencyCount.value) || 3;
    const mode = elements.outlookConcurrencyMode.value || 'pipeline';

    // Блокировка кнопки старта
    elements.startBtn.disabled = true;
    elements.cancelBtn.disabled = false;

    // Очистка журнала
    elements.consoleLog.innerHTML = '';

    const requestData = {
        service_ids: selectedIds,
        skip_registered: skipRegistered,
        interval_min: intervalMin,
        interval_max: intervalMax,
        concurrency: Math.min(50, Math.max(1, concurrency)),
        mode: mode
    };

    addLog('info', `[Система] Запуск пакетной регистрации Outlook (${selectedIds.length} аккаунтов)...`);

    try {
        const data = await api.post('/registration/outlook-batch', requestData);

        if (data.to_register === 0) {
            addLog('warning', '[Предупр.] Все выбранные email уже зарегистрированы');
            toast.warning('Все выбранные email уже зарегистрированы');
            resetButtons();
            return;
        }

        currentBatch = { batch_id: data.batch_id, ...data };
        activeBatchId = data.batch_id;  // сохранение для переподключения
        // сохранение в sessionStorage для восстановления
        sessionStorage.setItem('activeTask', JSON.stringify({ batch_id: data.batch_id, mode: isOutlookBatchMode ? 'outlook_batch' : 'batch', total: data.to_register }));
        addLog('info', `[Система] Пакетная задача создана: ${data.batch_id}`);
        addLog('info', `[Система] Всего: ${data.total}, пропущено зарег.: ${data.skipped}, к регистрации: ${data.to_register}`);

        // инициализация отображения статуса
        showBatchStatus({ count: data.to_register });

        // приоритет WebSocket
        connectBatchWebSocket(data.batch_id);

    } catch (error) {
        addLog('error', `[Ошибка] Ошибка запуска: ${error.message}`);
        toast.error(error.message);
        resetButtons();
    }
}

// ============== Функции WebSocket пакетных задач ==============

// Подключение WebSocket пакетной задачи
function connectBatchWebSocket(batchId) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws/batch/${batchId}`;

    try {
        batchWebSocket = new WebSocket(wsUrl);

        batchWebSocket.onopen = () => {
            console.log('WebSocket пакетной задачи подключён');
            // остановка опроса если был
            stopBatchPolling();
            // запуск heartbeat
            startBatchWebSocketHeartbeat();
        };

        batchWebSocket.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === 'log') {
                const logType = getLogType(data.message);
                addLog(logType, data.message);
            } else if (data.type === 'status') {
                // обновление прогресса
                if (data.total !== undefined) {
                    updateBatchProgress({
                        total: data.total,
                        completed: data.completed || 0,
                        success: data.success || 0,
                        failed: data.failed || 0
                    });
                }

                // проверка завершения
                if (['completed', 'failed', 'cancelled', 'cancelling'].includes(data.status)) {
                    // сохранение финального статуса
                    batchFinalStatus = data.status;
                    batchCompleted = true;

                    // отключение WebSocket
                    disconnectBatchWebSocket();

                    // сброс кнопок после завершения
                    resetButtons();

                    // показ toast только раз
                    if (!toastShown) {
                        toastShown = true;
                        if (data.status === 'completed') {
                            addLog('success', `[Завершено] Пакетная задача Outlook завершена! Успешно: ${data.success}, ошибок: ${data.failed}, пропущено: ${data.skipped || 0}`);
                            if (data.success > 0) {
                                toast.success(`Пакетная регистрация Outlook завершена, успешно ${data.success} `);
                                loadRecentAccounts();
                            } else {
                                toast.warning('Пакетная регистрация Outlook завершена без успехов');
                            }
                        } else if (data.status === 'failed') {
                            addLog('error', '[Ошибка] Ошибка выполнения пакетной задачи');
                            toast.error('Ошибка выполнения пакетной задачи');
                        } else if (data.status === 'cancelled' || data.status === 'cancelling') {
                            addLog('warning', '[Предупр.] Пакетная задача отменена');
                        }
                    }
                }
            } else if (data.type === 'pong') {
                // ответ heartbeat, игнорируем
            }
        };

        batchWebSocket.onclose = (event) => {
            console.log('WebSocket пакетной задачи отключён:', event.code);
            stopBatchWebSocketHeartbeat();

            // переход на опрос если задача не завершена
            // используем batchFinalStatus
            const shouldPoll = !batchCompleted &&
                               batchFinalStatus === null;  // если есть значение — задача завершена

            if (shouldPoll && currentBatch) {
                console.log('переход на опрос');
                startOutlookBatchPolling(currentBatch.batch_id);
            }
        };

        batchWebSocket.onerror = (error) => {
            console.error('WebSocket пакетной задачи ошибка:', error);
            stopBatchWebSocketHeartbeat();
            // переход на опрос
            startOutlookBatchPolling(batchId);
        };

    } catch (error) {
        console.error('Ошибка подключения WebSocket пакетной задачи:', error);
        startOutlookBatchPolling(batchId);
    }
}

// Отключение WebSocket пакетной задачи
function disconnectBatchWebSocket() {
    stopBatchWebSocketHeartbeat();
    if (batchWebSocket) {
        batchWebSocket.close();
        batchWebSocket = null;
    }
}

// Запуск heartbeat пакетной задачи
function startBatchWebSocketHeartbeat() {
    stopBatchWebSocketHeartbeat();
    batchWsHeartbeatInterval = setInterval(() => {
        if (batchWebSocket && batchWebSocket.readyState === WebSocket.OPEN) {
            batchWebSocket.send(JSON.stringify({ type: 'ping' }));
        }
    }, 25000);  // heartbeat каждые 25 сек
}

// Остановка heartbeat пакетной задачи
function stopBatchWebSocketHeartbeat() {
    if (batchWsHeartbeatInterval) {
        clearInterval(batchWsHeartbeatInterval);
        batchWsHeartbeatInterval = null;
    }
}

// Отправка запроса на отмену пакетной задачи
function cancelBatchViaWebSocket() {
    if (batchWebSocket && batchWebSocket.readyState === WebSocket.OPEN) {
        batchWebSocket.send(JSON.stringify({ type: 'cancel' }));
    }
}

// Начало опроса статуса Outlook (откат)
function startOutlookBatchPolling(batchId) {
    batchPollingInterval = setInterval(async () => {
        try {
            const data = await api.get(`/registration/outlook-batch/${batchId}`);

            // обновление прогресса
            updateBatchProgress({
                total: data.total,
                completed: data.completed,
                success: data.success,
                failed: data.failed
            });

            // вывод логов
            if (data.logs && data.logs.length > 0) {
                const lastLogIndex = batchPollingInterval.lastLogIndex || 0;
                for (let i = lastLogIndex; i < data.logs.length; i++) {
                    const log = data.logs[i];
                    const logType = getLogType(log);
                    addLog(logType, log);
                }
                batchPollingInterval.lastLogIndex = data.logs.length;
            }

            // проверка завершения
            if (data.finished) {
                stopBatchPolling();
                resetButtons();

                // показ toast только раз
                if (!toastShown) {
                    toastShown = true;
                    addLog('info', `[Завершено] Пакетная задача Outlook завершена! Успешно: ${data.success}, ошибок: ${data.failed}, пропущено: ${data.skipped || 0}`);
                    if (data.success > 0) {
                        toast.success(`Пакетная регистрация Outlook завершена, успешно ${data.success} `);
                        loadRecentAccounts();
                    } else {
                        toast.warning('Пакетная регистрация Outlook завершена без успехов');
                    }
                }
            }
        } catch (error) {
            console.error('Ошибка опроса статуса Outlook:', error);
        }
    }, 2000);

    batchPollingInterval.lastLogIndex = 0;
}

// ============== Переподключение при видимости страницы ==============

function initVisibilityReconnect() {
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState !== 'visible') return;

        // переподключение при возвращении на вкладку
        const wsDisconnected = !webSocket || webSocket.readyState === WebSocket.CLOSED;
        const batchWsDisconnected = !batchWebSocket || batchWebSocket.readyState === WebSocket.CLOSED;

        // переподключение одиночной задачи
        if (activeTaskUuid && !taskCompleted && wsDisconnected) {
            console.log('[Переподключение] Страница видима, переподключение WebSocket задачи:', activeTaskUuid);
            addLog('info', '[Система] Переподключение мониторинга задачи...');
            connectWebSocket(activeTaskUuid);
        }

        // переподключение пакетной задачи
        if (activeBatchId && !batchCompleted && batchWsDisconnected) {
            console.log('[Переподключение] Переподключение WebSocket пакетной задачи:', activeBatchId);
            addLog('info', '[Система] Переподключение мониторинга пакетной задачи...');
            connectBatchWebSocket(activeBatchId);
        }
    });
}

// Восстановление активной задачи при загрузке страницы
async function restoreActiveTask() {
    const saved = sessionStorage.getItem('activeTask');
    if (!saved) return;

    let state;
    try {
        state = JSON.parse(saved);
    } catch {
        sessionStorage.removeItem('activeTask');
        return;
    }

    const { mode, task_uuid, batch_id, total } = state;

    if (mode === 'single' && task_uuid) {
        // проверка что задача ещё выполняется
        try {
            const data = await api.get(`/registration/tasks/${task_uuid}`);
            if (['completed', 'failed', 'cancelled'].includes(data.status)) {
                sessionStorage.removeItem('activeTask');
                return;
            }
            // задача ещё выполняется, восстановление
            currentTask = data;
            activeTaskUuid = task_uuid;
            taskCompleted = false;
            taskFinalStatus = null;
            toastShown = false;
            displayedLogs.clear();
            elements.startBtn.disabled = true;
            elements.cancelBtn.disabled = false;
            showTaskStatus(data);
            updateTaskStatus(data.status);
            addLog('info', `[Система] Обнаружена активная задача, переподключение... (${task_uuid.substring(0, 8)})`);
            connectWebSocket(task_uuid);
        } catch {
            sessionStorage.removeItem('activeTask');
        }
    } else if ((mode === 'batch' || mode === 'outlook_batch') && batch_id) {
        // проверка что пакетная задача ещё выполняется
        const endpoint = mode === 'outlook_batch'
            ? `/registration/outlook-batch/${batch_id}`
            : `/registration/batch/${batch_id}`;
        try {
            const data = await api.get(endpoint);
            if (data.finished) {
                sessionStorage.removeItem('activeTask');
                return;
            }
            // пакетная задача ещё выполняется, восстановление
            currentBatch = { batch_id, ...data };
            activeBatchId = batch_id;
            isOutlookBatchMode = (mode === 'outlook_batch');
            batchCompleted = false;
            batchFinalStatus = null;
            toastShown = false;
            displayedLogs.clear();
            elements.startBtn.disabled = true;
            elements.cancelBtn.disabled = false;
            showBatchStatus({ count: total || data.total });
            updateBatchProgress(data);
            addLog('info', `[Система] Обнаружена активная пакетная задача, переподключение... (${batch_id.substring(0, 8)})`);
            connectBatchWebSocket(batch_id);
        } catch {
            sessionStorage.removeItem('activeTask');
        }
    }
}
