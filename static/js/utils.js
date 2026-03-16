/**
 * Общая библиотека утилит
 * Toast-уведомления, переключение темы, вспомогательные функции
 */

// ============================================
// Система Toast-уведомлений
// ============================================

class ToastManager {
    constructor() {
        this.container = null;
        this.init();
    }

    init() {
        this.container = document.createElement('div');
        this.container.className = 'toast-container';
        document.body.appendChild(this.container);
    }

    show(message, type = 'info', duration = 4000) {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const icon = this.getIcon(type);
        toast.innerHTML = `
            <span class="toast-icon">${icon}</span>
            <span class="toast-message">${this.escapeHtml(message)}</span>
            <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
        `;

        this.container.appendChild(toast);

        // Автоудаление
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease forwards';
            setTimeout(() => toast.remove(), 300);
        }, duration);

        return toast;
    }

    getIcon(type) {
        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ'
        };
        return icons[type] || icons.info;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    success(message, duration) {
        return this.show(message, 'success', duration);
    }

    error(message, duration) {
        return this.show(message, 'error', duration);
    }

    warning(message, duration) {
        return this.show(message, 'warning', duration);
    }

    info(message, duration) {
        return this.show(message, 'info', duration);
    }
}

// Глобальный экземпляр Toast
const toast = new ToastManager();

// ============================================
// Управление темой
// ============================================

class ThemeManager {
    constructor() {
        this.theme = this.loadTheme();
        this.applyTheme();
    }

    loadTheme() {
        return localStorage.getItem('theme') || 'light';
    }

    saveTheme(theme) {
        localStorage.setItem('theme', theme);
    }

    applyTheme() {
        document.documentElement.setAttribute('data-theme', this.theme);
        this.updateToggleButtons();
    }

    toggle() {
        this.theme = this.theme === 'light' ? 'dark' : 'light';
        this.saveTheme(this.theme);
        this.applyTheme();
    }

    setTheme(theme) {
        this.theme = theme;
        this.saveTheme(theme);
        this.applyTheme();
    }

    updateToggleButtons() {
        const buttons = document.querySelectorAll('.theme-toggle');
        buttons.forEach(btn => {
            btn.innerHTML = this.theme === 'light' ? '🌙' : '☀️';
            btn.title = this.theme === 'light' ? 'Тёмная тема' : 'Светлая тема';
        });
    }
}

// Глобальный экземпляр темы
const theme = new ThemeManager();

// ============================================
// Управление состоянием загрузки
// ============================================

class LoadingManager {
    constructor() {
        this.activeLoaders = new Set();
    }

    show(element, text = 'Загрузка...') {
        if (typeof element === 'string') {
            element = document.getElementById(element);
        }
        if (!element) return;

        element.classList.add('loading');
        element.dataset.originalText = element.innerHTML;
        element.innerHTML = `<span class="loading-spinner"></span> ${text}`;
        element.disabled = true;
        this.activeLoaders.add(element);
    }

    hide(element) {
        if (typeof element === 'string') {
            element = document.getElementById(element);
        }
        if (!element) return;

        element.classList.remove('loading');
        if (element.dataset.originalText) {
            element.innerHTML = element.dataset.originalText;
            delete element.dataset.originalText;
        }
        element.disabled = false;
        this.activeLoaders.delete(element);
    }

    hideAll() {
        this.activeLoaders.forEach(element => this.hide(element));
    }
}

const loading = new LoadingManager();

// ============================================
// Обёртка API-запросов
// ============================================

class ApiClient {
    constructor(baseUrl = '/api') {
        this.baseUrl = baseUrl;
    }

    async request(path, options = {}) {
        const url = `${this.baseUrl}${path}`;

        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
            },
        };

        const finalOptions = { ...defaultOptions, ...options };

        if (finalOptions.body && typeof finalOptions.body === 'object') {
            finalOptions.body = JSON.stringify(finalOptions.body);
        }

        try {
            const response = await fetch(url, finalOptions);
            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                const error = new Error(data.detail || `HTTP ${response.status}`);
                error.response = response;
                error.data = data;
                throw error;
            }

            return data;
        } catch (error) {
            // Обработка сетевых ошибок
            if (!error.response) {
                toast.error('Ошибка сети, проверьте подключение');
            }
            throw error;
        }
    }

    get(path, options = {}) {
        return this.request(path, { ...options, method: 'GET' });
    }

    post(path, body, options = {}) {
        return this.request(path, { ...options, method: 'POST', body });
    }

    put(path, body, options = {}) {
        return this.request(path, { ...options, method: 'PUT', body });
    }

    patch(path, body, options = {}) {
        return this.request(path, { ...options, method: 'PATCH', body });
    }

    delete(path, options = {}) {
        return this.request(path, { ...options, method: 'DELETE' });
    }
}

const api = new ApiClient();

// ============================================
// Помощник делегирования событий
// ============================================

function delegate(element, eventType, selector, handler) {
    element.addEventListener(eventType, (e) => {
        const target = e.target.closest(selector);
        if (target && element.contains(target)) {
            handler.call(target, e, target);
        }
    });
}

// ============================================
// Debounce и Throttle
// ============================================

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function throttle(func, limit) {
    let inThrottle;
    return function executedFunction(...args) {
        if (!inThrottle) {
            func(...args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// ============================================
// Утилиты форматирования
// ============================================

const format = {
    date(dateStr) {
        if (!dateStr) return '-';
        const date = new Date(dateStr);
        return date.toLocaleString('ru-RU', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    },

    dateShort(dateStr) {
        if (!dateStr) return '-';
        const date = new Date(dateStr);
        return date.toLocaleDateString('ru-RU');
    },

    relativeTime(dateStr) {
        if (!dateStr) return '-';
        const date = new Date(dateStr);
        const now = new Date();
        const diff = now - date;
        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (seconds < 60) return 'только что';
        if (minutes < 60) return `${minutes} мин. назад`;
        if (hours < 24) return `${hours} ч. назад`;
        if (days < 7) return `${days} дн. назад`;
        return this.dateShort(dateStr);
    },

    bytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    number(num) {
        if (num === null || num === undefined) return '-';
        return num.toLocaleString('ru-RU');
    }
};

// ============================================
// Маппинг статусов
// ============================================

const statusMap = {
    account: {
        active: { text: 'Активный', class: 'active' },
        expired: { text: 'Истёкший', class: 'expired' },
        banned: { text: 'Заблокирован', class: 'banned' },
        failed: { text: 'Ошибка', class: 'failed' }
    },
    task: {
        pending: { text: 'Ожидание', class: 'pending' },
        running: { text: 'Выполняется', class: 'running' },
        completed: { text: 'Завершено', class: 'completed' },
        failed: { text: 'Ошибка', class: 'failed' },
        cancelled: { text: 'Отменено', class: 'disabled' }
    },
    service: {
        tempmail: 'Tempmail.lol',
        outlook: 'Outlook',
        custom_domain: 'Свой домен'
    }
};

function getStatusText(type, status) {
    return statusMap[type]?.[status]?.text || status;
}

function getStatusClass(type, status) {
    return statusMap[type]?.[status]?.class || '';
}

function getServiceTypeText(type) {
    return statusMap.service[type] || type;
}

// ============================================
// Диалог подтверждения
// ============================================

function confirm(message, title = 'Подтверждение') {
    return new Promise((resolve) => {
        const modal = document.createElement('div');
        modal.className = 'modal active';
        modal.innerHTML = `
            <div class="modal-content" style="max-width: 400px;">
                <div class="modal-header">
                    <h3>${title}</h3>
                </div>
                <div class="modal-body">
                    <p style="margin-bottom: var(--spacing-lg);">${message}</p>
                    <div class="form-actions" style="margin-top: 0; padding-top: 0; border-top: none;">
                        <button class="btn btn-secondary" id="confirm-cancel">Отмена</button>
                        <button class="btn btn-danger" id="confirm-ok">Подтвердить</button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        const cancelBtn = modal.querySelector('#confirm-cancel');
        const okBtn = modal.querySelector('#confirm-ok');

        cancelBtn.onclick = () => {
            modal.remove();
            resolve(false);
        };

        okBtn.onclick = () => {
            modal.remove();
            resolve(true);
        };

        modal.onclick = (e) => {
            if (e.target === modal) {
                modal.remove();
                resolve(false);
            }
        };
    });
}

// ============================================
// Копирование в буфер обмена
// ============================================

async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        toast.success('Скопировано в буфер обмена');
        return true;
    } catch (err) {
        toast.error('Ошибка копирования');
        return false;
    }
}

// ============================================
// Помощник локального хранилища
// ============================================

const storage = {
    get(key, defaultValue = null) {
        try {
            const value = localStorage.getItem(key);
            return value ? JSON.parse(value) : defaultValue;
        } catch {
            return defaultValue;
        }
    },

    set(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
            return true;
        } catch {
            return false;
        }
    },

    remove(key) {
        localStorage.removeItem(key);
    }
};

// ============================================
// Инициализация страницы
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    // Инициализация темы
    theme.applyTheme();

    // Глобальные горячие клавиши
    document.addEventListener('keydown', (e) => {
        // Ctrl/Cmd + K: фокус на поиск
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            const searchInput = document.querySelector('#search-input, [type="search"]');
            if (searchInput) searchInput.focus();
        }

        // Escape: закрыть модальное окно
        if (e.key === 'Escape') {
            const activeModal = document.querySelector('.modal.active');
            if (activeModal) activeModal.classList.remove('active');
        }
    });
});

// Экспорт глобальных объектов
window.toast = toast;
window.theme = theme;
window.loading = loading;
window.api = api;
window.format = format;
window.confirm = confirm;
window.copyToClipboard = copyToClipboard;
window.storage = storage;
window.delegate = delegate;
window.debounce = debounce;
window.throttle = throttle;
window.getStatusText = getStatusText;
window.getStatusClass = getStatusClass;
window.getServiceTypeText = getServiceTypeText;
