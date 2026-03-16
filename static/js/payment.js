/**
 * JavaScript страницы оплаты
 */

let selectedPlan = 'plus';
let generatedLink = '';

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    loadAccounts();
});

// Загрузка списка аккаунтов
async function loadAccounts() {
    try {
        const resp = await fetch('/api/accounts?page=1&page_size=100&status=active');
        const data = await resp.json();
        const sel = document.getElementById('account-select');
        sel.innerHTML = '<option value="">-- Выберите аккаунт --</option>';
        (data.accounts || []).forEach(acc => {
            const opt = document.createElement('option');
            opt.value = acc.id;
            opt.textContent = acc.email;
            sel.appendChild(opt);
        });
    } catch (e) {
        console.error('Ошибка загрузки аккаунтов:', e);
    }
}

// Выбор тарифа
function selectPlan(plan) {
    selectedPlan = plan;
    document.getElementById('plan-plus').classList.toggle('selected', plan === 'plus');
    document.getElementById('plan-team').classList.toggle('selected', plan === 'team');
    document.getElementById('team-options').classList.toggle('show', plan === 'team');
    // Скрыть сгенерированную ссылку
    document.getElementById('link-box').classList.remove('show');
    generatedLink = '';
}

// Генерация ссылки на оплату
async function generateLink() {
    const accountId = document.getElementById('account-select').value;
    if (!accountId) {
        ui.showToast('Сначала выберите аккаунт', 'warning');
        return;
    }

    const body = {
        account_id: parseInt(accountId),
        plan_type: selectedPlan,
    };

    if (selectedPlan === 'team') {
        body.workspace_name = document.getElementById('workspace-name').value || 'MyTeam';
        body.seat_quantity = parseInt(document.getElementById('seat-quantity').value) || 5;
        body.price_interval = document.getElementById('price-interval').value;
    }

    try {
        const resp = await fetch('/api/payment/generate-link', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (data.success && data.link) {
            generatedLink = data.link;
            document.getElementById('link-text').value = data.link;
            document.getElementById('link-box').classList.add('show');
            document.getElementById('open-status').textContent = '';
            ui.showToast('Ссылка на оплату создана', 'success');
        } else {
            ui.showToast(data.detail || 'Ошибка генерации ссылки', 'error');
        }
    } catch (e) {
        ui.showToast('Ошибка запроса: ' + e.message, 'error');
    }
}

// Копирование ссылки
function copyLink() {
    if (!generatedLink) return;
    navigator.clipboard.writeText(generatedLink).then(() => {
        ui.showToast('Скопировано в буфер обмена', 'success');
    }).catch(() => {
        // Резервный способ
        const ta = document.getElementById('link-text');
        ta.select();
        document.execCommand('copy');
        ui.showToast('Скопировано в буфер обмена', 'success');
    });
}

// Открыть в режиме инкогнито
async function openIncognito() {
    if (!generatedLink) {
        ui.showToast('Сначала сгенерируйте ссылку', 'warning');
        return;
    }
    const statusEl = document.getElementById('open-status');
    statusEl.textContent = 'Открытие...';
    try {
        const resp = await fetch('/api/payment/open-incognito', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: generatedLink }),
        });
        const data = await resp.json();
        if (data.success) {
            statusEl.textContent = 'Браузер открыт в режиме инкогнито';
            ui.showToast('Инкогнито-режим открыт', 'success');
        } else {
            statusEl.textContent = data.message || 'Браузер не найден, скопируйте ссылку вручную';
            ui.showToast(data.message || 'Браузер не найден', 'warning');
        }
    } catch (e) {
        statusEl.textContent = 'Ошибка запроса: ' + e.message;
        ui.showToast('Ошибка запроса', 'error');
    }
}
