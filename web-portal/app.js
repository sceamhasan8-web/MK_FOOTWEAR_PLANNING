/**
 * Footwear Manufacturing Production Planning ERP Web Management Client
 * Light Theme Default + Authoritative Dynamic Daily Target Recalculation
 * Resilient API Pipeline: Centralized Client, Request Correlation, Complete State Machine
 */

const API_BASE = '/api/v1';

let authToken = localStorage.getItem('erp_token') || null;
let currentUser = JSON.parse(localStorage.getItem('erp_user') || 'null');
let currentOrderDetails = null;

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initAuth();
    initNavigation();
    initForms();
    initOrderFilters();
    initSettingsModule();
    initAdminModule();
    // Order selectors use simple native <select> dropdowns (populated on sheet load)
    initEditOrderForm();
    initOrderDeleteAndCancelModals();

    // Default today's date in entry form
    const todayStr = new Date().toISOString().split('T')[0];
    const entryDateInput = document.getElementById('entry-date');
    if (entryDateInput) entryDateInput.value = todayStr;
    const newOrderDeliv = document.getElementById('new-order-delivery');
    if (newOrderDeliv) {
        const d = new Date();
        d.setDate(d.getDate() + 15);
        newOrderDeliv.value = d.toISOString().split('T')[0];
    }
});

// Helper for demo login buttons
window.setLogin = function(username, password) {
    document.getElementById('login-username').value = username;
    document.getElementById('login-password').value = password;
};

// HTML escaping utility for safe UI rendering
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// ----------------- THEME MANAGEMENT (Section 19: Light Theme by default) -----------------
function initTheme() {
    const savedTheme = localStorage.getItem('erp_theme');
    const btnLight = document.getElementById('theme-btn-light');
    const btnDark = document.getElementById('theme-btn-dark');

    // Default is LIGHT THEME unless user explicitly selected 'dark'
    if (savedTheme === 'dark') {
        setTheme('dark', false);
    } else {
        setTheme('light', false);
    }

    if (btnLight) {
        btnLight.addEventListener('click', () => setTheme('light', true));
    }
    if (btnDark) {
        btnDark.addEventListener('click', () => setTheme('dark', true));
    }
}

function setTheme(theme, save = true) {
    const btnLight = document.getElementById('theme-btn-light');
    const btnDark = document.getElementById('theme-btn-dark');

    if (theme === 'dark') {
        document.body.classList.remove('light-theme');
        document.body.classList.add('dark-theme');
        if (btnDark) btnDark.classList.add('active');
        if (btnLight) btnLight.classList.remove('active');
        if (save) localStorage.setItem('erp_theme', 'dark');
    } else {
        document.body.classList.remove('dark-theme');
        document.body.classList.add('light-theme');
        if (btnLight) btnLight.classList.add('active');
        if (btnDark) btnDark.classList.remove('active');
        if (save) localStorage.setItem('erp_theme', 'light');
    }
}

// ----------------- TOAST NOTIFICATIONS -----------------
function showToast(message, isSuccess = true) {
    const toast = document.getElementById('toast-notification');
    const icon = document.getElementById('toast-icon');
    const msg = document.getElementById('toast-message');
    if (!toast) return;

    msg.textContent = message;
    icon.textContent = isSuccess ? '✓' : '⚠️';
    toast.className = isSuccess ? 'toast-banner' : 'toast-banner alert-danger';
    toast.classList.remove('hidden');

    setTimeout(() => {
        toast.classList.add('hidden');
    }, 4500);
}

// ----------------- AUTHENTICATION -----------------
function initAuth() {
    const loginOverlay = document.getElementById('login-overlay');
    const loginForm = document.getElementById('login-form');
    const btnLogout = document.getElementById('btn-logout');
    const btnTogglePwd = document.getElementById('btn-toggle-password');
    const pwdInput = document.getElementById('login-password');
    const userInput = document.getElementById('login-username');
    const rememberMeCheck = document.getElementById('login-remember-me');
    const linkForgotPwd = document.getElementById('link-forgot-password');
    const errBanner = document.getElementById('login-error');
    const errText = document.getElementById('login-error-text');
    const btnSubmit = document.getElementById('btn-login-submit');

    // Restore remembered username if present
    const remembered = localStorage.getItem('mk_remember_user');
    if (remembered && userInput) {
        userInput.value = remembered;
        if (rememberMeCheck) rememberMeCheck.checked = true;
    }

    // Toggle Password Visibility
    if (btnTogglePwd && pwdInput) {
        btnTogglePwd.addEventListener('click', () => {
            const isPassword = pwdInput.type === 'password';
            pwdInput.type = isPassword ? 'text' : 'password';
            const icon = document.getElementById('pwd-toggle-icon');
            if (icon) icon.textContent = isPassword ? '🙈' : '👁️';
        });
    }

    // Forgot Password modal trigger
    if (linkForgotPwd) {
        linkForgotPwd.addEventListener('click', (e) => {
            e.preventDefault();
            openModal('forgot-password-modal');
        });
    }

    // Check active session
    if (authToken && currentUser) {
        loginOverlay.classList.remove('active');
        updateUserUI();
        loadAllData();
    } else {
        loginOverlay.classList.add('active');
    }

    // Handle Login Submission
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = (userInput ? userInput.value : '').trim();
        const password = pwdInput ? pwdInput.value : '';

        if (!username || !password) {
            if (errBanner && errText) {
                errText.textContent = 'Please enter both username and password';
                errBanner.classList.remove('hidden');
            }
            return;
        }

        if (errBanner) errBanner.classList.add('hidden');
        if (btnSubmit) {
            btnSubmit.classList.add('loading');
            btnSubmit.disabled = true;
        }

        try {
            const res = await fetch(`${API_BASE}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({ username, password })
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                let msg = errData.detail || 'Invalid username or password';
                if (typeof msg !== 'string') msg = 'Invalid username or password';
                throw new Error(msg);
            }

            const data = await res.json();
            authToken = data.access_token;
            currentUser = {
                id: data.user_id,
                username: data.username,
                full_name: data.full_name,
                role: data.role,
                is_admin: data.is_admin || String(data.role).toLowerCase() === 'admin'
            };

            localStorage.setItem('erp_token', authToken);
            localStorage.setItem('erp_user', JSON.stringify(currentUser));

            // Remember Me
            if (rememberMeCheck && rememberMeCheck.checked) {
                localStorage.setItem('mk_remember_user', username);
            } else {
                localStorage.removeItem('mk_remember_user');
            }

            loginOverlay.classList.remove('active');
            updateUserUI();
            loadAllData();
            showToast(`Welcome back, ${currentUser.full_name}!`);
        } catch (err) {
            let errorMsg = err.message;
            if (err.name === 'TypeError' || errorMsg.includes('Failed to fetch')) {
                errorMsg = 'Unable to connect to the server. Please check your connection and try again.';
            }
            if (errBanner) {
                if (errText) errText.textContent = errorMsg;
                else errBanner.textContent = errorMsg;
                errBanner.classList.remove('hidden');
            }
        } finally {
            if (btnSubmit) {
                btnSubmit.classList.remove('loading');
                btnSubmit.disabled = false;
            }
        }
    });

    // Handle Logout
    btnLogout.addEventListener('click', () => {
        if (authToken) {
            fetch(`${API_BASE}/auth/logout`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${authToken}` }
            }).catch(() => {});
        }

        localStorage.removeItem('erp_token');
        localStorage.removeItem('erp_user');
        authToken = null;
        currentUser = null;

        const adminNav = document.getElementById('nav-item-admin');
        if (adminNav) adminNav.style.display = 'none';

        if (pwdInput) pwdInput.value = '';
        loginOverlay.classList.add('active');

        if (errBanner) errBanner.classList.add('hidden');
        showToast('You have been signed out successfully.');
    });
}

function handleSessionExpired(message) {
    authToken = null;
    currentUser = null;
    localStorage.removeItem('erp_token');
    localStorage.removeItem('erp_user');

    const adminNav = document.getElementById('nav-item-admin');
    if (adminNav) adminNav.style.display = 'none';

    const loginOverlay = document.getElementById('login-overlay');
    if (loginOverlay) {
        loginOverlay.classList.add('active');
        const errBanner = document.getElementById('login-error');
        const errText = document.getElementById('login-error-text');
        if (errBanner) {
            const msg = message || 'Your session has expired. Please sign in again.';
            if (errText) errText.textContent = msg;
            else errBanner.textContent = msg;
            errBanner.classList.remove('hidden');
        }
    }
}

function updateUserUI() {
    if (!currentUser) return;
    const nameEl = document.getElementById('user-full-name');
    const roleEl = document.getElementById('user-role');
    const avatarEl = document.getElementById('user-avatar');

    if (nameEl) nameEl.textContent = currentUser.full_name;
    const roleStr = String(currentUser.role || 'USER').toUpperCase();
    if (roleEl) roleEl.textContent = roleStr;
    if (avatarEl) avatarEl.textContent = (currentUser.full_name || 'U').charAt(0).toUpperCase();

    // Role-based visibility for Admin Control Panel in navigation
    const isAdmin = currentUser && (
        String(currentUser.role).toLowerCase() === 'admin' ||
        String(currentUser.role).toLowerCase() === 'userrole.admin' ||
        currentUser.is_admin === true
    );
    const adminNav = document.getElementById('nav-item-admin');
    if (adminNav) {
        adminNav.style.display = isAdmin ? 'flex' : 'none';
    }

    // If a non-admin was viewing the admin section, redirect them to dashboard
    if (!isAdmin) {
        const adminSection = document.getElementById('admin-section');
        if (adminSection && adminSection.classList.contains('active')) {
            navigateToSection('dashboard-section');
        }
    }
}

/**
 * Resilient Centralized API Client (Sections 6, 17, 18, 20, 28)
 * Features:
 * - 15-second timeout via AbortController
 * - Automatic X-Request-ID client & server correlation
 * - Bearer authorization header injection
 * - Handles 401 session expiry without reload loops
 * - Traps network disconnects and server errors
 * - Always returns normalized { ok, status, error, requestId, data }
 */
async function apiFetch(endpoint, options = {}) {
    const timeoutMs = options.timeout || 15000;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    const headers = options.headers || {};
    headers['Accept'] = 'application/json';
    if (!headers['Content-Type'] && options.body && typeof options.body === 'string' && options.body.startsWith('{')) {
        headers['Content-Type'] = 'application/json';
    }

    if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
    }

    const clientReqId = 'ERP-' + Date.now().toString(36).toUpperCase() + '-' + Math.random().toString(36).substring(2, 6).toUpperCase();
    headers['X-Request-ID'] = clientReqId;

    try {
        const fetchOptions = {
            ...options,
            headers,
            signal: controller.signal
        };

        const res = await fetch(`${API_BASE}${endpoint}`, fetchOptions);
        clearTimeout(timer);

        const requestId = res.headers.get('X-Request-ID') || clientReqId;

        // Handle 401 Unauthorized
        if (res.status === 401) {
            handleSessionExpired('Your session has expired. Please sign in again.');
            return {
                ok: false,
                status: 401,
                error: 'Authentication required. Please sign in.',
                requestId,
                data: null
            };
        }

        // Handle 403 Forbidden
        if (res.status === 403) {
            return {
                ok: false,
                status: 403,
                error: 'Access denied: You do not have permission for this action.',
                requestId,
                data: null
            };
        }

        // Parse Response Body
        let data = null;
        const contentType = res.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            try {
                data = await res.json();
            } catch (e) {
                data = null;
            }
        } else if (contentType.includes('text/')) {
            data = await res.text();
        }

        if (!res.ok) {
            const errorMsg = (data && data.detail) ? data.detail : (typeof data === 'string' && data ? data : `Server HTTP Error ${res.status}`);
            return {
                ok: false,
                status: res.status,
                error: errorMsg,
                requestId,
                data
            };
        }

        return {
            ok: true,
            status: res.status,
            error: null,
            requestId,
            data
        };
    } catch (err) {
        clearTimeout(timer);
        if (err.name === 'AbortError') {
            return {
                ok: false,
                status: 408,
                error: 'Request timed out after 15 seconds. The server did not respond.',
                requestId: clientReqId,
                data: null
            };
        }
        return {
            ok: false,
            status: 0,
            error: `Unable to connect to ERP server (${err.message || 'Network error'}). Ensure backend is running.`,
            requestId: clientReqId,
            data: null
        };
    }
}

// ----------------- NAVIGATION -----------------
function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const sections = document.querySelectorAll('.content-section');
    const titleEl = document.getElementById('current-page-title');

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            navItems.forEach(i => i.classList.remove('active'));
            sections.forEach(s => s.classList.remove('active'));

            item.classList.add('active');
            const targetId = item.getAttribute('data-target');
            const targetSection = document.getElementById(targetId);
            if (targetSection) targetSection.classList.add('active');

            titleEl.textContent = item.querySelector('.nav-label').textContent;

            if (targetId === 'dashboard-section') loadDashboard();
            if (targetId === 'buyers-section') loadBuyers();
            if (targetId === 'orders-section') loadOrders();
            if (targetId === 'production-section') loadProductionOptions();
            if (targetId === 'matrix-planning-section' || targetId === 'planning-sheet-section') {
                loadMatrixPlanningSheet();
            }
            if (targetId === 'wip-flow-section') {
                loadWipFlowSheet();
            }
            if (targetId === 'calendar-section') loadFactoryCalendar();
            if (targetId === 'reports-section') loadReportOrders();
            if (targetId === 'departments-section') loadDepartments();
            if (targetId === 'settings-section') loadSettingsModule();
            if (targetId === 'admin-section') {
                const isAdmin = currentUser && (
                    String(currentUser.role).toLowerCase() === 'admin' ||
                    String(currentUser.role).toLowerCase() === 'userrole.admin' ||
                    currentUser.is_admin === true
                );
                if (!isAdmin) {
                    showToast('Access Denied: Administrator role required.', false);
                    navigateToSection('dashboard-section');
                    return;
                }
                loadAdminPanel();
            }
        });
    });

    // Hash-based direct URL route listener with RBAC enforcement
    function handleHashRouting() {
        const hash = (window.location.hash || '').replace('#', '').trim();
        if (!hash) return;
        if (hash === 'admin') {
            const isAdmin = currentUser && (
                String(currentUser.role).toLowerCase() === 'admin' ||
                String(currentUser.role).toLowerCase() === 'userrole.admin' ||
                currentUser.is_admin === true
            );
            if (!isAdmin) {
                showToast('Access Denied: Administrator permissions required.', false);
                window.location.hash = '#dashboard';
                navigateToSection('dashboard-section');
                return;
            }
            navigateToSection('admin-section');
            return;
        }
        const targetSectionId = hash.endsWith('-section') ? hash : `${hash}-section`;
        const matchingNav = document.querySelector(`.nav-item[data-target="${targetSectionId}"]`);
        if (matchingNav) {
            matchingNav.click();
        }
    }
    window.addEventListener('hashchange', handleHashRouting);
    if (window.location.hash && window.location.hash !== '#') {
        setTimeout(handleHashRouting, 150);
    }

    document.getElementById('btn-refresh-data').addEventListener('click', () => {
        loadAllData();
        showToast('System data refreshed successfully.');
    });

    document.getElementById('btn-quick-new-order').addEventListener('click', () => {
        openModal('create-order-modal');
        loadBuyerDropdownForNewOrder();
    });

    // Production Planning Sheet (View 1 - Matrix with T/G, ON HAND, O/T)
    const btnRecalcMatrix = document.getElementById('btn-recalculate-matrix-plan');
    if (btnRecalcMatrix) {
        btnRecalcMatrix.addEventListener('click', async () => {
            const orderSelect = document.getElementById('matrix-filter-order');
            const orderId = orderSelect?.value;
            if (!orderId) {
                showToast('Please select an active order to recalculate.');
                return;
            }
            showToast('Recalculating production plan...');
            const res = await apiFetch(`/orders/${orderId}/recalculate-plan`, { method: 'POST' });
            if (res.ok) {
                showToast('Production plan recalculated successfully.');
                loadMatrixPlanningSheet(orderId);
            } else {
                showToast('Error recalculating: ' + res.error);
            }
        });
    }

    const btnExportMatrixXlsx = document.getElementById('btn-export-matrix-xlsx');
    if (btnExportMatrixXlsx) {
        btnExportMatrixXlsx.addEventListener('click', () => {
            const orderId = document.getElementById('matrix-filter-order')?.value;
            if (!orderId) {
                showToast('Please select an order to export.');
                return;
            }
            const token = localStorage.getItem('token');
            const url = `${API_BASE}/exports/orders/${orderId}/matrix-planning/xlsx`;
            fetch(url, { headers: { 'Authorization': `Bearer ${token}` } })
                .then(resp => {
                    if (!resp.ok) throw new Error('Export failed');
                    return resp.blob();
                })
                .then(blob => {
                    const dlUrl = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = dlUrl;
                    a.download = `Planning_Matrix_${orderId}.xlsx`;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    showToast('Production Planning Matrix XLSX downloaded.');
                })
                .catch(err => showToast('Export error: ' + err.message));
        });
    }

    const btnExportMatrixCsv = document.getElementById('btn-export-matrix-csv');
    if (btnExportMatrixCsv) {
        btnExportMatrixCsv.addEventListener('click', () => {
            const orderId = document.getElementById('matrix-filter-order')?.value;
            if (!orderId) {
                showToast('Please select an order to export.');
                return;
            }
            const token = localStorage.getItem('token');
            const url = `${API_BASE}/exports/orders/${orderId}/matrix-planning/csv`;
            fetch(url, { headers: { 'Authorization': `Bearer ${token}` } })
                .then(resp => resp.blob())
                .then(blob => {
                    const dlUrl = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = dlUrl;
                    a.download = `Planning_Matrix_${orderId}.csv`;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    showToast('Production Planning Matrix CSV downloaded.');
                })
                .catch(err => showToast('CSV error: ' + err.message));
        });
    }

    const matrixBuyerFilter = document.getElementById('matrix-filter-buyer');
    if (matrixBuyerFilter) {
        matrixBuyerFilter.addEventListener('change', () => {
            filterMatrixOrdersByBuyer(matrixBuyerFilter.value);
        });
    }

    const matrixOrderFilter = document.getElementById('matrix-filter-order');
    if (matrixOrderFilter) {
        matrixOrderFilter.addEventListener('change', () => {
            loadMatrixPlanningSheet(matrixOrderFilter.value);
        });
    }

    const matrixDateRange = document.getElementById('matrix-filter-date-range');
    if (matrixDateRange) {
        matrixDateRange.addEventListener('change', () => {
            renderMatrixPlanningSheetTable();
        });
    }

    // WIP Flow Planning Sheet (View 2 - Serial Flow)
    const btnRecalcWip = document.getElementById('btn-recalculate-wip-plan');
    if (btnRecalcWip) {
        btnRecalcWip.addEventListener('click', async () => {
            const orderSelect = document.getElementById('wip-filter-order');
            const orderId = orderSelect?.value;
            if (!orderId) {
                showToast('Please select an active order to recalculate.');
                return;
            }
            showToast('Recalculating WIP flow planning...');
            const res = await apiFetch(`/orders/${orderId}/recalculate-plan`, { method: 'POST' });
            if (res.ok) {
                showToast('WIP flow planning recalculated successfully.');
                loadWipFlowSheet(orderId);
            } else {
                showToast('Error recalculating: ' + res.error);
            }
        });
    }

    const btnExportWipXlsx = document.getElementById('btn-export-wip-xlsx');
    if (btnExportWipXlsx) {
        btnExportWipXlsx.addEventListener('click', () => {
            const orderId = document.getElementById('wip-filter-order')?.value;
            if (!orderId) {
                showToast('Please select an order to export.');
                return;
            }
            const token = localStorage.getItem('token');
            const url = `${API_BASE}/exports/orders/${orderId}/wip-flow/xlsx`;
            fetch(url, { headers: { 'Authorization': `Bearer ${token}` } })
                .then(resp => {
                    if (!resp.ok) throw new Error('Export failed');
                    return resp.blob();
                })
                .then(blob => {
                    const dlUrl = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = dlUrl;
                    a.download = `WIP_Flow_Plan_${orderId}.xlsx`;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    showToast('WIP Flow 5-Sheet XLSX downloaded.');
                })
                .catch(err => showToast('Export error: ' + err.message));
        });
    }

    const btnExportWipCsv = document.getElementById('btn-export-wip-csv');
    if (btnExportWipCsv) {
        btnExportWipCsv.addEventListener('click', () => {
            const orderId = document.getElementById('wip-filter-order')?.value;
            if (!orderId) {
                showToast('Please select an order to export.');
                return;
            }
            const token = localStorage.getItem('token');
            const url = `${API_BASE}/exports/orders/${orderId}/wip-flow/csv`;
            fetch(url, { headers: { 'Authorization': `Bearer ${token}` } })
                .then(resp => resp.blob())
                .then(blob => {
                    const dlUrl = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = dlUrl;
                    a.download = `WIP_Flow_Plan_${orderId}.csv`;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    showToast('WIP Flow Planning CSV downloaded.');
                })
                .catch(err => showToast('CSV error: ' + err.message));
        });
    }

    const wipOrderFilter = document.getElementById('wip-filter-order');
    if (wipOrderFilter) {
        wipOrderFilter.addEventListener('change', () => {
            loadWipFlowSheet(wipOrderFilter.value);
        });
    }

    const wipDateRange = document.getElementById('wip-filter-date-range');
    if (wipDateRange) {
        wipDateRange.addEventListener('change', () => {
            renderSerialFlowRows();
        });
    }

    const wipStatusFilter = document.getElementById('wip-filter-status');
    if (wipStatusFilter) {
        wipStatusFilter.addEventListener('change', () => {
            renderSerialFlowRows();
        });
    }


    ['sheet-filter-buyer', 'sheet-filter-order', 'sheet-filter-category', 'sheet-filter-status'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', () => loadPlanningSheet());
        }
    });

    // System Diagnostics Button & Modal Trigger
    const btnDiagnostics = document.getElementById('btn-open-diagnostics');
    if (btnDiagnostics) {
        btnDiagnostics.addEventListener('click', () => {
            openModal('diagnostics-modal');
            runDiagnostics();
        });
    }

    const btnRunDiag = document.getElementById('btn-run-diagnostics');
    if (btnRunDiag) {
        btnRunDiag.addEventListener('click', () => {
            runDiagnostics();
        });
    }
}

window.navigateToSection = function(sectionId) {
    const targetItem = document.querySelector(`.nav-item[data-target="${sectionId}"]`);
    if (targetItem) targetItem.click();
};

function loadAllData() {
    loadDashboard();
    loadBuyers();
    loadOrders();
    loadProductionOptions();
    loadMatrixPlanningSheet();
    loadWipFlowSheet();
    loadReportOrders();
    loadDepartments();
    loadSettingsModule();
}

// ----------------- DASHBOARD (Section 5, 22, 23, 26) -----------------
async function loadDashboard() {
    const tableTbody = document.querySelector('#dashboard-orders-table tbody');
    const perfTbody = document.querySelector('#section-perf-table tbody');

    try {
        const res = await apiFetch('/dashboard/summary');
        if (!res.ok) {
            if (tableTbody) {
                tableTbody.innerHTML = `<tr><td colspan="11" class="text-center text-danger" style="padding:20px;">
                    ⚠️ Unable to load dashboard data: ${escapeHtml(res.error)}
                    <small style="display:block; color:var(--text-dim); margin-top:4px;">Error ID: ${res.requestId}</small>
                    <button class="btn btn-sm btn-outline" style="margin-top:8px;" onclick="loadDashboard()">🔄 Retry</button>
                </td></tr>`;
            }
            if (perfTbody) {
                perfTbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger" style="padding:15px;">
                    ⚠️ Department metrics unavailable: ${escapeHtml(res.error)}
                    <button class="btn btn-sm btn-outline" style="margin-top:6px;" onclick="loadDashboard()">🔄 Retry</button>
                </td></tr>`;
            }
            ['kpi-active-orders', 'kpi-total-ordered', 'kpi-total-balance', 'kpi-today-planned', 'kpi-today-actual', 'kpi-wip-waiting', 'kpi-at-risk', 'kpi-overdue'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.textContent = '--';
            });
            showToast(`Dashboard loading error: ${res.error}`, false);
            return;
        }

        const s = res.data;

        // Section 5: Authoritative Business Date Display
        if (s.planning_date_display) {
            document.getElementById('planning-date-display').textContent = `📅 Planning Date: ${s.planning_date_display}`;
        }

        // Section 26: 8 Summary KPI Cards
        document.getElementById('kpi-active-orders').textContent = Number(s.active_orders_count || 0).toLocaleString();
        const elTotalOrdered = document.getElementById('kpi-total-ordered');
        if (elTotalOrdered) elTotalOrdered.textContent = Number(s.total_ordered_pairs || 0).toLocaleString();
        document.getElementById('kpi-total-balance').textContent = Number(s.total_balance ?? s.outstanding_production_pairs ?? 0).toLocaleString();
        document.getElementById('kpi-today-planned').textContent = Number(s.today_total_planned || 0).toLocaleString();
        document.getElementById('kpi-today-actual').textContent = Number(s.today_total_actual || 0).toLocaleString();
        const elWipWaiting = document.getElementById('kpi-wip-waiting');
        if (elWipWaiting) elWipWaiting.textContent = Number(s.wip_waiting_qty || 0).toLocaleString();
        document.getElementById('kpi-at-risk').textContent = s.at_risk_orders_count || 0;
        document.getElementById('kpi-overdue').textContent = s.overdue_orders_count || 0;

        document.getElementById('today-planned-total').textContent = Number(s.today_total_planned || 0).toLocaleString() + ' pairs';
        document.getElementById('today-actual-total').textContent = Number(s.today_total_actual || 0).toLocaleString() + ' pairs';

        // Load dashboard orders table
        loadDashboardOrdersTable();

        // Department performance table
        if (perfTbody) {
            perfTbody.innerHTML = '';
            if (!s.section_performances || s.section_performances.length === 0) {
                perfTbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No department performance data recorded today</td></tr>';
            } else {
                s.section_performances.forEach(p => {
                    const tr = document.createElement('tr');
                    const varianceClass = p.variance >= 0 ? 'text-success' : 'text-danger';
                    const statusBadge = p.is_behind
                        ? '<span class="status-badge status-OVERDUE">Behind Plan</span>'
                        : '<span class="status-badge status-PRODUCTION_COMPLETE">On Track</span>';

                    tr.innerHTML = `
                        <td><strong>${escapeHtml(p.section_name)}</strong></td>
                        <td>${escapeHtml(p.category_name)}</td>
                        <td>${Number(p.total_planned_today).toLocaleString()}</td>
                        <td>${Number(p.total_actual_today).toLocaleString()}</td>
                        <td class="${varianceClass}"><strong>${p.variance > 0 ? '+' : ''}${Number(p.variance).toLocaleString()}</strong></td>
                        <td>${statusBadge}</td>
                    `;
                    perfTbody.appendChild(tr);
                });
            }
        }
    } catch (e) {
        console.error('Error in loadDashboard', e);
    }
}

// Section 22 & 23: Dashboard Orders Planning Table
async function loadDashboardOrdersTable() {
    const tbody = document.querySelector('#dashboard-orders-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="11" class="text-center">Loading order planning schedule...</td></tr>';

    try {
        const res = await apiFetch('/orders');
        if (!res.ok) {
            tbody.innerHTML = `<tr><td colspan="11" class="text-center text-danger" style="padding:18px;">
                ⚠️ Unable to load orders: ${escapeHtml(res.error)}
                <small style="display:block; color:var(--text-dim); margin-top:4px;">Request ID: ${res.requestId}</small>
                <button class="btn btn-sm btn-outline" style="margin-top:8px;" onclick="loadDashboardOrdersTable()">🔄 Retry</button>
            </td></tr>`;
            return;
        }

        const orders = res.data || [];
        tbody.innerHTML = '';
        if (orders.length === 0) {
            tbody.innerHTML = `<tr><td colspan="11" class="text-center text-muted" style="padding:18px;">
                No active orders found in system.
                <button class="btn btn-sm btn-primary" style="margin-left:10px;" onclick="openModal('create-order-modal'); loadBuyerDropdownForNewOrder();">+ New Order</button>
            </td></tr>`;
            return;
        }

        orders.forEach(o => {
            const tr = document.createElement('tr');
            const targetDisplay = o.daily_target > 0 ? `${Number(o.daily_target).toLocaleString()} pairs/day` : (o.is_overdue ? 'OVERDUE' : '0');
            const actualTodayDisplay = Number(o.today_actual || 0).toLocaleString();

            tr.innerHTML = `
                <td><strong>${escapeHtml(o.buyer_name || 'N/A')}</strong></td>
                <td><code>${escapeHtml(o.order_code)}</code></td>
                <td>${Number(o.total_quantity).toLocaleString()}</td>
                <td>${Number(o.completed_pairs).toLocaleString()}</td>
                <td><span class="cell-balance">${Number(o.outstanding_pairs).toLocaleString()}</span></td>
                <td>${escapeHtml(o.current_delivery_date)}</td>
                <td><span class="badge ${o.remaining_working_days <= 2 ? 'text-danger' : ''}"><strong>${o.remaining_working_days} d</strong></span></td>
                <td><span class="cell-target">${targetDisplay}</span></td>
                <td><span class="cell-actual">${actualTodayDisplay}</span></td>
                <td><span class="status-badge status-${escapeHtml(o.status)}">${escapeHtml(o.status.replace('_', ' '))}</span></td>
                <td>
                    <button class="btn btn-sm btn-primary" onclick="openOrderDetails(${o.id})">Plan Details</button>
                    <button class="btn btn-sm btn-outline" onclick="openEditOrderModal(${o.id})" style="margin-left:4px;">✏️ Edit</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Error loading dashboard orders table', e);
        tbody.innerHTML = `<tr><td colspan="11" class="text-center text-danger">⚠️ Exception: ${escapeHtml(e.message)} <button class="btn btn-sm btn-outline" onclick="loadDashboardOrdersTable()">Retry</button></td></tr>`;
    }
}

// ----------------- BUYERS (Section 24) -----------------
async function loadBuyers() {
    const tbody = document.querySelector('#buyers-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="9" class="text-center">Loading buyers...</td></tr>';

    try {
        const search = document.getElementById('buyer-search-input')?.value.trim() || '';
        const url = search ? `/buyers?search=${encodeURIComponent(search)}` : '/buyers';
        const res = await apiFetch(url);

        if (!res.ok) {
            tbody.innerHTML = `<tr><td colspan="9" class="text-center text-danger" style="padding:18px;">
                ⚠️ Unable to load buyers: ${escapeHtml(res.error)}
                <small style="display:block; color:var(--text-dim); margin-top:4px;">Request ID: ${res.requestId}</small>
                <button class="btn btn-sm btn-outline" style="margin-top:8px;" onclick="loadBuyers()">🔄 Retry</button>
            </td></tr>`;
            return;
        }

        const buyers = res.data || [];
        tbody.innerHTML = '';
        if (buyers.length === 0) {
            tbody.innerHTML = `<tr><td colspan="9" class="text-center text-muted" style="padding:18px;">
                No buyers found in system.
                <button class="btn btn-sm btn-primary" style="margin-left:10px;" onclick="openModal('add-buyer-modal')">+ Add Buyer</button>
            </td></tr>`;
            return;
        }

        buyers.forEach(b => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><code>${escapeHtml(b.buyer_code)}</code></td>
                <td><strong>${escapeHtml(b.name)}</strong></td>
                <td>${escapeHtml(b.contact_person || 'N/A')}</td>
                <td>${escapeHtml(b.phone || '')} ${b.email ? `(${escapeHtml(b.email)})` : ''}</td>
                <td>${b.active_orders_count}</td>
                <td>${Number(b.total_ordered_pairs).toLocaleString()}</td>
                <td class="text-warning"><strong>${Number(b.outstanding_production_pairs).toLocaleString()}</strong></td>
                <td><span class="status-badge ${b.is_active ? 'status-PRODUCTION_COMPLETE' : 'status-ON_HOLD'}">${b.is_active ? 'Active' : 'Inactive'}</span></td>
                <td>
                    <button class="btn btn-sm btn-outline" onclick="filterOrdersByBuyer(${b.id})">View Orders</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Error loading buyers', e);
        tbody.innerHTML = `<tr><td colspan="9" class="text-center text-danger">⚠️ Exception: ${escapeHtml(e.message)} <button class="btn btn-sm btn-outline" onclick="loadBuyers()">Retry</button></td></tr>`;
    }
}

window.filterOrdersByBuyer = function(buyerId) {
    document.querySelector('.nav-item[data-target="orders-section"]').click();
    loadOrders(buyerId);
};

// ----------------- ORDERS (Section 25) -----------------
async function loadOrders(filterBuyerId = null) {
    const tbody = document.querySelector('#orders-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="13" class="text-center">Loading orders...</td></tr>';

    try {
        const search = document.getElementById('order-search-input')?.value.trim() || '';
        const status = document.getElementById('order-status-filter')?.value || '';
        const priority = document.getElementById('order-priority-filter')?.value || '';

        let query = [];
        if (search) query.push(`search=${encodeURIComponent(search)}`);
        if (status === 'ARCHIVED') {
            query.push('order_status=ARCHIVED&include_archived=true');
        } else if (status === 'ALL_INCLUDING_ARCHIVED') {
            query.push('include_archived=true');
        } else if (status) {
            query.push(`order_status=${encodeURIComponent(status)}`);
        }
        if (priority) query.push(`priority=${encodeURIComponent(priority)}`);
        if (filterBuyerId) query.push(`buyer_id=${filterBuyerId}`);

        const url = `/orders${query.length ? '?' + query.join('&') : ''}`;
        const res = await apiFetch(url);

        if (!res.ok) {
            tbody.innerHTML = `<tr><td colspan="13" class="text-center text-danger" style="padding:18px;">
                ⚠️ Unable to load orders: ${escapeHtml(res.error)}
                <small style="display:block; color:var(--text-dim); margin-top:4px;">Request ID: ${res.requestId}</small>
                <button class="btn btn-sm btn-outline" style="margin-top:8px;" onclick="loadOrders()">🔄 Retry</button>
            </td></tr>`;
            return;
        }

        const orders = res.data || [];
        tbody.innerHTML = '';
        if (orders.length === 0) {
            tbody.innerHTML = `<tr><td colspan="13" class="text-center text-muted" style="padding:18px;">
                No orders match the selected filters.
                <button class="btn btn-sm btn-primary" style="margin-left:10px;" onclick="openModal('create-order-modal'); loadBuyerDropdownForNewOrder();">+ New Order</button>
            </td></tr>`;
            return;
        }

        orders.forEach(o => {
            const tr = document.createElement('tr');
            const targetDisplay = o.daily_target > 0 ? `${Number(o.daily_target).toLocaleString()} pairs/day` : (o.is_overdue ? 'OVERDUE' : '0');
            const isArchived = Boolean(o.is_archived || o.status === 'ARCHIVED');

            tr.innerHTML = `
                <td><strong>${escapeHtml(o.buyer_name || 'N/A')}</strong></td>
                <td><code>${escapeHtml(o.order_code)}</code></td>
                <td>${escapeHtml(o.customer_ref)} ${o.po_number ? `<small>(${escapeHtml(o.po_number)})</small>` : ''}</td>
                <td>${escapeHtml(o.style_model)}</td>
                <td><strong>${Number(o.total_quantity).toLocaleString()}</strong></td>
                <td>${Number(o.completed_pairs).toLocaleString()} <small>(${o.completion_percentage}%)</small></td>
                <td><span class="cell-balance">${Number(o.outstanding_pairs).toLocaleString()}</span></td>
                <td>${escapeHtml(o.current_delivery_date)}</td>
                <td><span class="badge ${o.remaining_working_days <= 2 ? 'text-danger' : ''}"><strong>${o.remaining_working_days} d</strong></span></td>
                <td><span class="cell-target">${targetDisplay}</span></td>
                <td><span class="priority-badge priority-${escapeHtml(o.priority)}">${escapeHtml(o.priority)}</span></td>
                <td><span class="status-badge status-${escapeHtml(o.status)}">${escapeHtml(o.status.replace('_', ' '))}</span></td>
                <td style="white-space: nowrap;">
                    <button class="btn btn-sm btn-primary" onclick="openOrderDetails(${o.id})">Planning View</button>
                    <button class="btn btn-sm btn-outline" onclick="openEditOrderModal(${o.id})" style="margin-left:4px;">✏️ Edit</button>
                    ${isArchived
                        ? `<button class="btn btn-sm btn-outline" onclick="restoreOrder(${o.id})" style="margin-left:4px; color:#0369a1;">♻️ Restore</button>`
                        : `<button class="btn btn-sm btn-outline text-danger" onclick="openDeleteOrderModal(${o.id})" style="margin-left:4px; color:#dc2626; border-color:#fca5a5;">🗑️ Delete</button>`
                    }
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Error loading orders', e);
        tbody.innerHTML = `<tr><td colspan="13" class="text-center text-danger">⚠️ Exception: ${escapeHtml(e.message)} <button class="btn btn-sm btn-outline" onclick="loadOrders()">Retry</button></td></tr>`;
    }
}

function initOrderFilters() {
    document.getElementById('order-search-input')?.addEventListener('input', () => loadOrders());
    document.getElementById('order-status-filter')?.addEventListener('change', () => loadOrders());
    document.getElementById('order-priority-filter')?.addEventListener('change', () => loadOrders());
    document.getElementById('buyer-search-input')?.addEventListener('input', () => loadBuyers());
}

// ----------------- ORDER PLANNING MODAL (Section 23, 27) -----------------
window.openOrderDetails = async function(orderId) {
    try {
        const res = await apiFetch(`/orders/${orderId}`);
        if (!res.ok) {
            showToast(`Unable to open order plan: ${res.error}`, false);
            return;
        }
        const det = res.data;
        currentOrderDetails = det;

        document.getElementById('modal-order-code').textContent = det.order_code;
        document.getElementById('modal-order-sub').textContent = `${det.buyer_name} | Style: ${det.style_model} | Customer Ref: ${det.customer_ref}`;

        // Header Specs
        document.getElementById('spec-buyer-name').textContent = det.buyer_name || 'N/A';
        document.getElementById('spec-order-code').textContent = det.order_code;
        document.getElementById('spec-order-qty').textContent = `${Number(det.total_quantity).toLocaleString()} Pairs`;
        document.getElementById('spec-produced-qty').textContent = `${Number(det.completed_pairs).toLocaleString()} Pairs`;
        document.getElementById('spec-balance-qty').textContent = `${Number(det.outstanding_pairs).toLocaleString()} Pairs`;
        document.getElementById('spec-shipment-date').textContent = det.current_delivery_date;
        document.getElementById('spec-days-remaining').textContent = `${det.remaining_working_days} Days`;

        // Prominent Auto Daily Target Banner
        const targetValEl = document.getElementById('spec-prominent-target');
        if (det.is_overdue && det.outstanding_pairs > 0) {
            targetValEl.textContent = 'OVERDUE';
            targetValEl.style.color = 'var(--danger)';
        } else if (det.outstanding_pairs <= 0) {
            targetValEl.textContent = '0 (Complete)';
            targetValEl.style.color = 'var(--success)';
        } else {
            targetValEl.textContent = `${Number(det.daily_target).toLocaleString()} Pairs / Day`;
            targetValEl.style.color = 'var(--primary)';
        }

        const statusBadge = document.getElementById('modal-order-status-badge');
        statusBadge.className = `status-badge status-${det.status}`;
        statusBadge.textContent = det.status.replace('_', ' ');

        const varBadge = document.getElementById('spec-variance-badge');
        if (det.today_variance > 0) {
            varBadge.innerHTML = `<span class="text-success">Ahead by +${Number(det.today_variance).toLocaleString()} pairs today</span>`;
        } else if (det.today_variance < 0) {
            varBadge.innerHTML = `<span class="text-danger">Behind by ${Number(Math.abs(det.today_variance)).toLocaleString()} pairs today</span>`;
        } else {
            varBadge.innerHTML = `<span>On Target for today</span>`;
        }

        // Render Routes & Operations (Tab 1)
        renderModalRoutes(det.routes);

        // Populate operation dropdown for schedule (Tab 3)
        const opSelect = document.getElementById('modal-op-schedule-select');
        opSelect.innerHTML = '';
        det.routes.forEach(r => {
            r.operations.forEach(op => {
                const opt = document.createElement('option');
                opt.value = op.id;
                opt.textContent = `${r.section_name} -> ${op.operation_name} (Bal: ${Number(op.balance_quantity).toLocaleString()})`;
                opSelect.appendChild(opt);
            });
        });

        if (det.routes.length > 0 && det.routes[0].operations.length > 0) {
            loadOperationSchedule(det.id, det.routes[0].operations[0].id);
        }

        opSelect.onchange = () => {
            loadOperationSchedule(det.id, opSelect.value);
        };

        // Render Category WIP Flow Chain (Tab 2, Section 27)
        try {
            const resFlow = await apiFetch(`/orders/${det.id}/category-flow`);
            if (resFlow.ok && resFlow.data) {
                renderModalCategoryFlow(resFlow.data);
            }
        } catch (errFlow) {
            console.error('Error fetching category flow', errFlow);
        }

        // Render Revisions (Tab 4)
        renderModalRevisions(det.delivery_revisions);

        // Download actions
        document.getElementById('btn-modal-dl-xlsx').onclick = () => {
            window.location.href = `${API_BASE}/exports/orders/${det.id}/xlsx`;
        };
        document.getElementById('btn-modal-dl-csv').onclick = () => {
            window.location.href = `${API_BASE}/exports/orders/${det.id}/csv`;
        };
        document.getElementById('btn-modal-revise-date').onclick = () => {
            openReviseDateModal(det.id, det.current_delivery_date);
        };

        initModalTabs();
        openModal('order-detail-modal');
    } catch (e) {
        console.error('Error opening order details', e);
    }
};

// Section 27: Category WIP Flow Chain Cards
function renderModalCategoryFlow(flowData) {
    const container = document.getElementById('modal-category-flow-container');
    if (!container) return;
    container.innerHTML = '';

    if (!flowData || !flowData.categories || flowData.categories.length === 0) {
        container.innerHTML = '<div class="text-center" style="grid-column: 1/-1; padding: 20px;">No category flow information found.</div>';
        return;
    }

    flowData.categories.forEach((cat, idx) => {
        const stepNum = idx + 1;
        const card = document.createElement('div');
        card.className = `cat-flow-card cat-step-${Math.min(stepNum, 3)}`;

        let badgeClass = 'badge-ready';
        if (cat.wip_status === 'WAITING FOR WIP') badgeClass = 'badge-waiting-wip';
        else if (cat.wip_status === 'PARTIALLY AVAILABLE') badgeClass = 'badge-partial';
        else if (cat.wip_status === 'NOT REQUIRED') badgeClass = 'badge-not-req';

        card.innerHTML = `
            <div class="cat-flow-header">
                <div>
                    <span style="font-size: 11px; font-weight: 700; color: var(--text-dim); text-transform: uppercase;">STEP ${stepNum}</span>
                    <div class="cat-flow-title">Category ${stepNum}: ${escapeHtml(cat.category_name)}</div>
                </div>
                <span class="status-badge ${badgeClass}">${escapeHtml(cat.wip_status)}</span>
            </div>
            <div class="cat-flow-stats">
                <div class="cat-flow-stat-item">
                    <span class="cat-flow-stat-label">Opening On Hand</span>
                    <span class="cat-flow-stat-val">${Number(cat.opening_on_hand).toLocaleString()}</span>
                </div>
                <div class="cat-flow-stat-item">
                    <span class="cat-flow-stat-label">Incoming WIP</span>
                    <span class="cat-flow-stat-val text-primary">+${Number(cat.incoming_wip).toLocaleString()}</span>
                </div>
                <div class="cat-flow-stat-item">
                    <span class="cat-flow-stat-label">Available On Hand</span>
                    <span class="cat-flow-stat-val text-success">${Number(cat.available_on_hand).toLocaleString()}</span>
                </div>
                <div class="cat-flow-stat-item">
                    <span class="cat-flow-stat-label">Output Completed</span>
                    <span class="cat-flow-stat-val">${Number(cat.completed_output).toLocaleString()}</span>
                </div>
                <div class="cat-flow-stat-item">
                    <span class="cat-flow-stat-label">Closing On Hand</span>
                    <span class="cat-flow-stat-val">${Number(cat.closing_on_hand).toLocaleString()}</span>
                </div>
                <div class="cat-flow-stat-item">
                    <span class="cat-flow-stat-label">Balance Remaining</span>
                    <span class="cat-flow-stat-val cell-balance">${Number(cat.balance).toLocaleString()}</span>
                </div>
            </div>
        `;
        container.appendChild(card);
    });
}

// Section 18: Category / Section Summary
function renderModalRoutes(routes) {
    const container = document.getElementById('routes-container');
    container.innerHTML = '';

    routes.forEach(r => {
        const secDiv = document.createElement('div');
        secDiv.className = 'card';
        secDiv.style.marginBottom = '12px';

        let opsHtml = '';
        r.operations.forEach(op => {
            let compsHtml = '';
            if (op.components && op.components.length > 0) {
                compsHtml = `<div style="margin-top:6px; padding-left:14px; border-left:2px solid var(--border-color);">
                    <small style="color:var(--text-muted); font-weight:600;">Part Tracking:</small>
                    ${op.components.map(c => `
                        <div style="font-size:12px; display:flex; justify-content:space-between; margin-top:2px;">
                            <span>• ${escapeHtml(c.component_name)} (${c.pieces_per_pair} pcs/pair):</span>
                            <span>Done: ${Number(c.accepted_total_qty).toLocaleString()} / ${Number(c.required_total_qty).toLocaleString()} ${escapeHtml(c.unit)} (${Number(c.pair_equivalent_accepted).toLocaleString()} pair-eq)</span>
                        </div>
                    `).join('')}
                </div>`;
            }

            const targetDisplay = op.daily_target > 0 ? `${Number(op.daily_target).toLocaleString()} pairs/day` : '0';

            opsHtml += `
                <div style="background:var(--bg-surface-elevated); padding:12px; border-radius:6px; margin-top:8px; border:1px solid var(--border-color);">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <strong style="font-size:14px;">${escapeHtml(op.operation_name)}</strong>
                            <span style="color:var(--text-dim); margin-left:8px; font-size:12px;">Required: <strong>${Number(op.required_quantity).toLocaleString()} ${escapeHtml(op.unit)}</strong></span>
                        </div>
                        <div>
                            <span class="status-badge status-${escapeHtml(op.status)}">${escapeHtml(op.status)}</span>
                        </div>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:12.5px; margin-top:8px; color:var(--text-muted); flex-wrap:wrap; gap:8px;">
                        <span>Produced: <strong class="text-success">${Number(op.completed_quantity).toLocaleString()}</strong></span>
                        <span>Balance: <strong class="cell-balance">${Number(op.balance_quantity).toLocaleString()}</strong></span>
                        <span>Auto Target: <strong class="cell-target">${targetDisplay}</strong></span>
                        <span>Today Actual: <strong>${Number(op.today_actual || 0).toLocaleString()}</strong></span>
                        <span>Progress: <strong>${op.completion_percentage}%</strong></span>
                    </div>
                    ${compsHtml}
                </div>
            `;
        });

        secDiv.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <h4>${escapeHtml(r.section_name)} <small style="color:var(--text-muted);">(${escapeHtml(r.category_name)})</small></h4>
                <div>
                    <span class="status-badge ${r.status === 'REQUIRED' ? 'status-IN_PRODUCTION' : 'status-NOT_REQUIRED'}">${r.status}</span>
                    <span class="status-badge ${r.is_completed ? 'status-PRODUCTION_COMPLETE' : 'status-AT_RISK'}" style="margin-left:6px;">
                        ${r.is_completed ? 'COMPLETED' : 'IN PROGRESS'}
                    </span>
                </div>
            </div>
            ${opsHtml}
        `;
        container.appendChild(secDiv);
    });
}

// Section 10: Future Daily Plan Table
async function loadOperationSchedule(orderId, operationId) {
    const tbody = document.querySelector('#modal-daily-schedule-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="10" class="text-center">Loading daily schedule...</td></tr>';

    try {
        const res = await apiFetch(`/orders/${orderId}/operations/${operationId}/daily-schedule`);
        if (!res.ok) {
            tbody.innerHTML = `<tr><td colspan="10" class="text-center text-danger">⚠️ Unable to load schedule: ${escapeHtml(res.error)}</td></tr>`;
            return;
        }
        const sched = res.data;
        tbody.innerHTML = '';
        if (!sched.rows || sched.rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">No remaining days or zero balance.</td></tr>';
            return;
        }

        sched.rows.forEach(row => {
            const tr = document.createElement('tr');
            const targetDisplay = row.planned_quantity > 0 ? Number(row.planned_quantity).toLocaleString() : '0';
            const actualDisplay = row.actual_accepted_quantity > 0 ? `<strong class="text-success">${Number(row.actual_accepted_quantity).toLocaleString()}</strong>` : '-';
            const varClass = row.variance >= 0 ? 'text-success' : 'text-danger';
            const varText = row.variance !== 0 ? (row.variance > 0 ? `+${Number(row.variance).toLocaleString()}` : `${Number(row.variance).toLocaleString()}`) : '-';
            const statusBadge = row.actual_accepted_quantity > 0
                ? '<span class="status-badge status-PRODUCTION_COMPLETE">Actual</span>'
                : '<span class="status-badge status-SCHEDULED">Planned</span>';

            tr.innerHTML = `
                <td><code>${escapeHtml(row.date)}</code></td>
                <td>${escapeHtml(row.day_name)}</td>
                <td><strong>${Number(row.opening_balance).toLocaleString()}</strong></td>
                <td><span class="cell-target">${targetDisplay}</span></td>
                <td>${actualDisplay}</td>
                <td><strong>${Number(row.closing_balance).toLocaleString()}</strong></td>
                <td>${Number(row.cumulative_accepted_quantity).toLocaleString()}</td>
                <td>${row.completion_percentage}%</td>
                <td class="${varClass}"><strong>${varText}</strong></td>
                <td>${statusBadge}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Error loading schedule', e);
        tbody.innerHTML = `<tr><td colspan="10" class="text-center text-danger">⚠️ Exception: ${escapeHtml(e.message)}</td></tr>`;
    }
}

function renderModalRevisions(revisions) {
    const tbody = document.querySelector('#modal-revisions-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (!revisions || revisions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No delivery date revisions recorded.</td></tr>';
        return;
    }
    revisions.forEach(rev => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><code>${escapeHtml(rev.previous_delivery_date)}</code></td>
            <td><code class="text-warning">${escapeHtml(rev.revised_delivery_date)}</code></td>
            <td>${escapeHtml(rev.reason)}</td>
            <td>${escapeHtml(rev.revised_by_name || 'System')}</td>
            <td>${new Date(rev.created_at).toLocaleString()}</td>
        `;
        tbody.appendChild(tr);
    });
}

function initModalTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');

    tabBtns.forEach(btn => {
        btn.onclick = () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            const target = btn.getAttribute('data-tab');
            const targetPane = document.getElementById(target);
            if (targetPane) targetPane.classList.add('active');
        };
    });
}

// ----------------- REVISE DATE MODAL -----------------
function openReviseDateModal(orderId, currentDate) {
    document.getElementById('revise-order-id').value = orderId;
    document.getElementById('revise-current-date').value = currentDate;
    document.getElementById('revise-new-date').value = currentDate;
    document.getElementById('revise-reason').value = '';
    openModal('revise-date-modal');
}

// ----------------- PRODUCTION ENTRY FORM (Section 8, 24, 26) -----------------
async function loadProductionOptions() {
    const orderSelect = document.getElementById('entry-order-select');
    if (!orderSelect) return;
    orderSelect.innerHTML = '<option value="">-- Loading Orders... --</option>';

    try {
        const resOrders = await apiFetch('/orders');
        if (!resOrders.ok) {
            orderSelect.innerHTML = `<option value="">-- Error loading orders: ${escapeHtml(resOrders.error)} --</option>`;
            return;
        }

        const orders = resOrders.data || [];
        orderSelect.innerHTML = '<option value="">-- Choose Order --</option>';
        if (orders.length === 0) {
            orderSelect.innerHTML = '<option value="">-- No active production orders available --</option>';
            return;
        }

        orders.forEach(o => {
            const opt = document.createElement('option');
            opt.value = o.id;
            opt.textContent = `${o.order_code} - ${o.customer_ref} (${o.style_model})`;
            orderSelect.appendChild(opt);
        });

        orderSelect.onchange = async () => {
            const orderId = orderSelect.value;
            if (!orderId) {
                resetBalanceBanner();
                return;
            }

            const resDet = await apiFetch(`/orders/${orderId}`);
            if (!resDet.ok) {
                showToast(`Unable to load order routes: ${resDet.error}`, false);
                return;
            }
            const det = resDet.data;

            let catFlowData = null;
            try {
                const resFlow = await apiFetch(`/orders/${orderId}/category-flow`);
                if (resFlow.ok) {
                    catFlowData = resFlow.data;
                }
            } catch (e) {}

            // Populate Routes
            const routeSelect = document.getElementById('entry-route-select');
            routeSelect.innerHTML = '<option value="">-- Choose Section --</option>';
            det.routes.forEach(r => {
                if (r.status === 'REQUIRED' && r.is_active !== false && r.section_is_active !== false) {
                    const opt = document.createElement('option');
                    opt.value = r.id;
                    opt.textContent = `${r.section_name} (${r.category_name})`;
                    routeSelect.appendChild(opt);
                }
            });

            routeSelect.onchange = () => {
                const routeId = routeSelect.value;
                const r = det.routes.find(x => x.id == routeId);
                const opSelect = document.getElementById('entry-operation-select');
                opSelect.innerHTML = '<option value="">-- Choose Operation --</option>';
                if (!r) {
                    resetBalanceBanner();
                    return;
                }

                r.operations.forEach(op => {
                    const opt = document.createElement('option');
                    opt.value = op.id;
                    opt.textContent = `${op.operation_name} (Bal: ${Number(op.balance_quantity).toLocaleString()} ${op.unit})`;
                    opSelect.appendChild(opt);
                });

                opSelect.onchange = () => {
                    const op = r.operations.find(x => x.id == opSelect.value);
                    if (!op) {
                        resetBalanceBanner();
                        return;
                    }

                    let availOnHand = null;
                    let execTarget = null;
                    if (catFlowData && catFlowData.categories) {
                        const matchedCat = catFlowData.categories.find(c =>
                            c.category_name.toLowerCase() === (r.category_name || '').toLowerCase() ||
                            c.category_name.toLowerCase().includes((r.category_name || '').toLowerCase()) ||
                            (r.category_name || '').toLowerCase().includes(c.category_name.toLowerCase())
                        );
                        if (matchedCat) {
                            availOnHand = matchedCat.available_on_hand;
                            execTarget = Math.min(op.daily_target, availOnHand);
                        }
                    }

                    updateBalanceBanner(op.balance_quantity, op.daily_target, det.remaining_working_days, op.unit, availOnHand, execTarget);

                    // Check components
                    const compRow = document.getElementById('component-select-row');
                    const compSelect = document.getElementById('entry-component-select');
                    compSelect.innerHTML = '<option value="">-- Direct Operation Output --</option>';

                    if (op.components && op.components.length > 0) {
                        compRow.classList.remove('hidden');
                        op.components.forEach(c => {
                            const opt = document.createElement('option');
                            opt.value = c.id;
                            opt.textContent = `${c.component_name} (Bal: ${Number(c.balance_total_qty).toLocaleString()} ${c.unit})`;
                            compSelect.appendChild(opt);
                        });
                    } else {
                        compRow.classList.add('hidden');
                    }
                };
            };
        };

        loadRecentProductionEntries();
    } catch (e) {
        console.error('Error loading production options', e);
    }
}

function updateBalanceBanner(balance, dailyTarget, remainingDays, unit = 'PAIRS', availOnHand = null, execTarget = null) {
    document.getElementById('lbl-current-balance').textContent = `${Number(balance).toLocaleString()} ${unit}`;
    const targetText = dailyTarget > 0 ? `${Number(dailyTarget).toLocaleString()} pairs/day` : '0 (Complete)';
    document.getElementById('lbl-current-target').textContent = targetText;
    document.getElementById('lbl-current-days').textContent = `${remainingDays} days`;

    const lblAvail = document.getElementById('lbl-available-on-hand');
    if (lblAvail) {
        lblAvail.textContent = availOnHand !== null && availOnHand !== undefined ? `${Number(availOnHand).toLocaleString()} ${unit}` : '--';
    }
    const lblExec = document.getElementById('lbl-executable-target');
    if (lblExec) {
        lblExec.textContent = execTarget !== null && execTarget !== undefined ? `${Number(execTarget).toLocaleString()} ${unit}/day` : '--';
    }
}

function resetBalanceBanner() {
    document.getElementById('lbl-current-balance').textContent = '--';
    document.getElementById('lbl-current-target').textContent = '--';
    document.getElementById('lbl-current-days').textContent = '--';
    const lblAvail = document.getElementById('lbl-available-on-hand');
    if (lblAvail) lblAvail.textContent = '--';
    const lblExec = document.getElementById('lbl-executable-target');
    if (lblExec) lblExec.textContent = '--';
}

async function loadRecentProductionEntries() {
    const tbody = document.querySelector('#recent-entries-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="10" class="text-center">Loading entries...</td></tr>';

    try {
        const res = await apiFetch('/production/entries?limit=50&include_reversed=true');
        if (!res.ok) {
            tbody.innerHTML = `<tr><td colspan="10" class="text-center text-danger" style="padding:15px;">
                ⚠️ Unable to load entries: ${escapeHtml(res.error)}
                <button class="btn btn-sm btn-outline" style="margin-top:6px;" onclick="loadRecentProductionEntries()">🔄 Retry</button>
            </td></tr>`;
            return;
        }

        const entries = res.data || [];
        tbody.innerHTML = '';
        if (entries.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted" style="padding:15px;">No production entries recorded yet.</td></tr>';
            return;
        }

        entries.forEach(e => {
            const tr = document.createElement('tr');
            const isCancelled = Boolean(e.is_reversed);
            tr.innerHTML = `
                <td><code>${escapeHtml(e.entry_date)}</code></td>
                <td><strong>${escapeHtml(e.buyer_name || '-')}</strong></td>
                <td><code>${escapeHtml(e.order_code || 'ORD')}</code></td>
                <td>${escapeHtml(e.section_name || '-')}</td>
                <td>${escapeHtml(e.operation_name || '')}</td>
                <td class="${isCancelled ? 'text-muted' : 'text-success'}" style="text-align:right;">
                    <strong>${Number(e.accepted_quantity).toLocaleString()}</strong>
                </td>
                <td style="text-align:right;">${Number(e.rejected_quantity).toLocaleString()}</td>
                <td>
                    <span class="status-badge ${isCancelled ? 'status-OVERDUE' : 'status-PRODUCTION_COMPLETE'}">
                        ${isCancelled ? 'VOIDED / CANCELLED' : 'ACCEPTED'}
                    </span>
                </td>
                <td><small>${escapeHtml(e.entered_by_name || 'User #' + e.entered_by_id)}</small></td>
                <td style="text-align:center;">
                    ${!isCancelled 
                        ? `<button class="btn btn-sm btn-outline text-danger" onclick="openCancelEntryModal(${e.id})" style="padding:2px 8px; font-size:11px; color:#dc2626; border-color:#fca5a5;">🗑️ Cancel / Void</button>`
                        : `<span class="text-muted" style="font-size:11px;">Voided</span>`
                    }
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error('Error loading recent entries', err);
        tbody.innerHTML = `<tr><td colspan="10" class="text-center text-danger">⚠️ Exception: ${escapeHtml(err.message)}</td></tr>`;
    }
}

window.reverseEntry = async function(entryId) {
    const reason = prompt('Please enter the reason for reversing this production entry:');
    if (!reason) return;

    try {
        const res = await apiFetch(`/production/entries/${entryId}/reverse`, {
            method: 'POST',
            body: JSON.stringify({ reason })
        });
        if (!res.ok) {
            alert('Failed to reverse entry: ' + res.error);
            return;
        }
        showToast('Entry reversed successfully. Planning targets recalculated automatically.');
        loadRecentProductionEntries();
        loadDashboard();
        loadOrders();
        loadPlanningSheet();
    } catch (e) {
        alert('Error: ' + e.message);
    }
};

// =========================================================================
// VIEW 1: PRODUCTION PLANNING SHEET (Date-Wise T/G, ON HAND, O/T)
// =========================================================================
let currentMatrixPlanData = null;
let allMatrixOrders = [];
let allMatrixBuyers = [];

function filterMatrixOrdersByBuyer(buyerId) {
    const orderSelect = document.getElementById('matrix-filter-order');
    if (!orderSelect) return;

    const filtered = buyerId
        ? allMatrixOrders.filter(o => String(o.buyer_id) === String(buyerId))
        : allMatrixOrders;

    orderSelect.innerHTML = '';
    if (filtered.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'No orders for this buyer';
        orderSelect.appendChild(opt);
        loadMatrixPlanningSheet('');
        return;
    }

    filtered.forEach(o => {
        const opt = document.createElement('option');
        opt.value = o.id;
        opt.textContent = `${o.order_code} - ${o.buyer_name || 'Buyer'} (${Number(o.total_quantity).toLocaleString()} prs)`;
        orderSelect.appendChild(opt);
    });

    // Select the first order in the filtered list and load its plan
    orderSelect.value = filtered[0].id;
    loadMatrixPlanningSheet(filtered[0].id);
}

async function loadMatrixPlanningSheet(targetOrderId = null) {
    const tbody = document.getElementById('planning-matrix-tbody');
    const orderSelect = document.getElementById('matrix-filter-order');
    const buyerSelect = document.getElementById('matrix-filter-buyer');
    const warningContainer = document.getElementById('matrix-warning-container');
    const valSummaryEl = document.getElementById('matrix-validation-summary');
    if (!tbody) return;

    // Discard previous displayed planning data immediately to avoid stale data (Section 24 & 25)
    currentMatrixPlanData = null;
    tbody.innerHTML = '<tr><td colspan="16" class="text-center" style="padding:24px;">Loading Production Plan...</td></tr>';
    if (warningContainer) warningContainer.style.display = 'none';
    if (valSummaryEl) valSummaryEl.style.display = 'none';

    try {
        // 1. Populate Buyers and Orders Selectors if not already populated
        if (allMatrixOrders.length === 0) {
            const [bRes, ordRes] = await Promise.all([
                apiFetch('/buyers'),
                apiFetch('/orders')
            ]);

            if (bRes.ok && bRes.data && buyerSelect) {
                allMatrixBuyers = bRes.data;
                buyerSelect.innerHTML = '<option value="">All Buyers</option>';
                bRes.data.forEach(b => {
                    const opt = document.createElement('option');
                    opt.value = b.id;
                    opt.textContent = b.name;
                    buyerSelect.appendChild(opt);
                });
            }

            if (ordRes.ok && ordRes.data && orderSelect) {
                allMatrixOrders = ordRes.data;
                orderSelect.innerHTML = '';
                ordRes.data.forEach(o => {
                    const opt = document.createElement('option');
                    opt.value = o.id;
                    opt.textContent = `${o.order_code} - ${o.buyer_name || 'Buyer'} (${Number(o.total_quantity).toLocaleString()} prs)`;
                    orderSelect.appendChild(opt);
                });
            }
        }

        const selectedOrderId = targetOrderId || orderSelect?.value || '';
        if (!selectedOrderId) {
            tbody.innerHTML = '<tr><td colspan="16" class="text-center text-muted" style="padding:24px;">No active production order selected.</td></tr>';
            return;
        }

        const url = `/orders/matrix-planning?order_id=${selectedOrderId}`;
        const res = await apiFetch(url);

        if (!res.ok) {
            // Error State (Section 26)
            tbody.innerHTML = `<tr><td colspan="16" class="text-center text-danger" style="padding:24px;">
                ⚠️ Unable to load production planning for this order: ${escapeHtml(res.error || 'Server Error')}
                <small style="display:block; color:var(--text-dim); margin-top:4px;">Request ID: ${res.requestId || 'N/A'}</small>
                <button class="btn btn-sm btn-outline" style="margin-top:8px;" onclick="loadMatrixPlanningSheet('${selectedOrderId}')">🔄 Retry</button>
            </td></tr>`;
            return;
        }

        if (!res.data) {
            tbody.innerHTML = '<tr><td colspan="16" class="text-center text-muted" style="padding:24px;">No plan available for this order. <button class="btn btn-sm btn-primary" onclick="openModal(\'create-order-modal\')">+ Create Order</button></td></tr>';
            return;
        }

        currentMatrixPlanData = res.data;
        if (orderSelect && currentMatrixPlanData.order_id) {
            orderSelect.value = currentMatrixPlanData.order_id;
        }


        // Synchronize Buyer selector if empty or changed
        if (buyerSelect && currentMatrixPlanData.buyer_id && buyerSelect.value !== String(currentMatrixPlanData.buyer_id)) {
            // Only update if not explicitly filtering all
            if (buyerSelect.value !== '') {
                buyerSelect.value = currentMatrixPlanData.buyer_id;
            }
        }

        // 2. Update Top Overview Banner (Section 40 & 14)
        const setEl = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };
        const orderQty = currentMatrixPlanData.total_quantity || 0;
        const completedQty = currentMatrixPlanData.completed_quantity || 0;
        const balanceQty = currentMatrixPlanData.current_balance != null ? currentMatrixPlanData.current_balance : currentMatrixPlanData.final_balance;
        const plannedTgQty = currentMatrixPlanData.total_planned_target != null ? currentMatrixPlanData.total_planned_target : balanceQty;
        const workingDays = currentMatrixPlanData.working_days != null ? currentMatrixPlanData.working_days : currentMatrixPlanData.remaining_working_days;

        setEl('matrix-banner-planning-date', currentMatrixPlanData.planning_date || currentMatrixPlanData.running_date || '-');
        setEl('matrix-banner-order-code', currentMatrixPlanData.order_code || '-');
        setEl('matrix-banner-buyer', currentMatrixPlanData.buyer_name || '-');
        setEl('matrix-banner-order-qty', `${Number(orderQty).toLocaleString()} Pairs`);
        setEl('matrix-banner-completed', `${Number(completedQty).toLocaleString()} Pairs`);
        setEl('matrix-banner-final-balance', `${Number(balanceQty).toLocaleString()} Pairs`);
        setEl('matrix-banner-shipment-date', currentMatrixPlanData.shipment_date || '-');
        setEl('matrix-banner-days-remaining', `${workingDays} Days`);
        setEl('matrix-banner-planned-tg', `${Number(plannedTgQty).toLocaleString()} Pairs`);

        // Plan Validation Status
        const valEl = document.getElementById('matrix-banner-validation');
        if (valEl) {
            const valObj = currentMatrixPlanData.validation;
            if (valObj && valObj.target_equals_balance) {
                valEl.innerHTML = `<span style="color: #16a34a; font-weight: 700;">✓ Target matches balance</span>`;
            } else {
                const msg = valObj?.message || 'Target mismatch detected';
                valEl.innerHTML = `<span style="color: #dc2626; font-weight: 700;">⚠️ ${escapeHtml(msg)}</span>`;
            }
        }

        // Overall Status Badge
        const statusEl = document.getElementById('matrix-banner-overall-status');
        if (statusEl) {
            const st = currentMatrixPlanData.overall_status || 'ON TRACK';
            let badgeCls = 'wip-badge-ontrack';
            if (st === 'COMPLETED') badgeCls = 'wip-badge-completed';
            else if (st === 'OVERDUE') badgeCls = 'wip-badge-overdue';
            else if (st === 'BEHIND TARGET' || st === 'AT RISK') badgeCls = 'wip-badge-behind';
            statusEl.innerHTML = `<span class="wip-badge ${badgeCls}">${escapeHtml(st)}</span>`;
        }

        // Warning Display (e.g., Shipment Date is an off-day or overdue)
        if (warningContainer) {
            if (currentMatrixPlanData.validation?.warning) {
                warningContainer.innerHTML = `<div class="alert alert-warning" style="margin: 0; padding: 10px 16px; background: #fffbeb; border-left: 4px solid #f59e0b; color: #92400e; font-size: 13px;">
                    ⚠️ ${escapeHtml(currentMatrixPlanData.validation.warning)}
                </div>`;
                warningContainer.style.display = 'block';
            } else {
                warningContainer.style.display = 'none';
            }
        }

        // 3. Render Planning Matrix Table
        renderMatrixPlanningSheetTable();

        // 4. Render Target Total Validation Footer Bar (Section 28)
        if (valSummaryEl && currentMatrixPlanData.validation?.section_validations) {
            const secVals = currentMatrixPlanData.validation.section_validations;
            let valHtml = `<div style="display:flex; flex-wrap:wrap; gap:16px; align-items:center;">
                <span style="font-weight:700; color:#1e293b;">Target Total Validation:</span>`;
            for (const [secName, sv] of Object.entries(secVals)) {
                const isMatched = sv.target_matches_balance;
                const statusBadge = isMatched
                    ? `<span style="color:#16a34a; font-weight:700;">✓ Validated</span>`
                    : `<span style="color:#dc2626; font-weight:700;">⚠️ Mismatch</span>`;
                valHtml += `<span style="background:#ffffff; border:1px solid #cbd5e1; padding:4px 10px; border-radius:4px; font-size:12px;">
                    <strong>${escapeHtml(secName)}:</strong> Planned T/G: ${Number(sv.future_target_total || sv.total_tg).toLocaleString()} | Balance: ${Number(sv.current_balance).toLocaleString()} (${statusBadge})
                </span>`;
            }
            valHtml += `</div>`;
            valSummaryEl.innerHTML = valHtml;
            valSummaryEl.style.display = 'block';
        }

    } catch (e) {
        console.error('Error loading Production Planning Sheet', e);
        tbody.innerHTML = `<tr><td colspan="16" class="text-center text-danger">⚠️ Exception: ${escapeHtml(e.message)} <button class="btn btn-sm btn-outline" onclick="loadMatrixPlanningSheet()">Retry</button></td></tr>`;
    }
}

function getSectionDataFromDict(dataDict, sectionName) {
    if (!dataDict || !sectionName) return null;
    if (dataDict[sectionName]) return dataDict[sectionName];
    const upper = sectionName.toUpperCase();
    if (dataDict[upper]) return dataDict[upper];
    const lower = sectionName.toLowerCase();
    if (dataDict[lower]) return dataDict[lower];
    const key = Object.keys(dataDict).find(k => k.trim().toLowerCase() === sectionName.trim().toLowerCase());
    return key ? dataDict[key] : null;
}

function renderMatrixPlanningSheetTable() {
    if (!currentMatrixPlanData) return;
    const thead = document.getElementById('planning-matrix-thead');
    const tbody = document.getElementById('planning-matrix-tbody');
    if (!thead || !tbody) return;

    let sections = currentMatrixPlanData.sections || [];
    let rows = currentMatrixPlanData.rows || [];

    // Fallback: If sections array is empty, derive from row section_data or summary
    if (sections.length === 0) {
        if (rows.length > 0 && rows[0].section_data) {
            sections = Object.keys(rows[0].section_data).map(k => ({ section_name: k }));
        } else if (currentMatrixPlanData.summary) {
            sections = Object.keys(currentMatrixPlanData.summary).map(k => ({ section_name: k }));
        }
    }

    // 1. Build Multi-Level Header:
    // Row 1: Date (rowspan=2) | <SEC1> (colspan=3) | <SEC2> (colspan=3) ...
    // Row 2: T/G | ON HAND | O/T | T/G | ON HAND | O/T ...
    let thRow1 = `<tr><th class="col-date" rowspan="2" style="background:#1f4e79; color:#fff; padding:8px;">Date</th>`;
    let thRow2 = `<tr>`;

    sections.forEach(s => {
        const sName = typeof s === 'string' ? s : (s.section_name || s.name || 'Section');
        thRow1 += `<th colspan="3" style="background:#1f4e79; color:#fff; text-align:center; border-left:1px solid #335d88; padding:8px;">${escapeHtml(sName)}</th>`;
        thRow2 += `<th style="background:#285b88; color:#fff; font-size:11px; text-align:right; padding:6px 8px;">T/G</th><th style="background:#285b88; color:#fff; font-size:11px; text-align:right; padding:6px 8px;">ON HAND</th><th style="background:#285b88; color:#fff; font-size:11px; text-align:right; padding:6px 8px;">O/T</th>`;
    });
    thRow1 += `</tr>`;
    thRow2 += `</tr>`;
    thead.innerHTML = thRow1 + thRow2;

    // Date filtering
    const dateFilter = document.getElementById('matrix-filter-date-range')?.value || 'ALL';
    const todayStr = new Date().toISOString().split('T')[0];
    if (dateFilter === 'TODAY') {
        rows = rows.filter(r => r.date === todayStr);
    } else if (dateFilter === 'THIS_WEEK') {
        rows = rows.slice(0, 7);
    } else if (dateFilter === 'SHIPMENT_WEEK') {
        rows = rows.slice(-7);
    }

    tbody.innerHTML = '';
    const totalCols = sections.length * 3 + 1;
    if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${totalCols}" class="text-center text-muted" style="padding:20px;">No planning rows match the current filter.</td></tr>`;
        return;
    }

    // 2. Render Date Rows
    rows.forEach(r => {
        const tr = document.createElement('tr');
        if (!r.is_workday) tr.style.backgroundColor = '#f8fafc';
        const dayLabel = r.day_name ? `<small style="display:block; font-size:10px; color:var(--text-muted);">${r.day_name.substring(0,3)}</small>` : '';
        const offBadge = !r.is_workday ? ' <span style="font-size:9px; background:#e2e8f0; padding:1px 4px; border-radius:3px; color:#64748b; font-weight:700;">OFF</span>' : '';
        let cellsHtml = `<td class="col-date" style="padding:6px 8px; font-weight:600;">${escapeHtml(r.date)} ${dayLabel}${offBadge}</td>`;

        sections.forEach(s => {
            const sName = typeof s === 'string' ? s : (s.section_name || s.name || '');
            const sData = getSectionDataFromDict(r.section_data, sName) || { tg: 0, on_hand: 0, ot: 0, status_code: 'GREEN' };
            const tgDisplay = !r.is_workday ? '<span style="color:#94a3b8;">0</span>' : (sData.tg > 0 ? Number(sData.tg).toLocaleString() : '0');
            const ohDisplay = Number(sData.on_hand || 0).toLocaleString();
            const otDisplay = sData.ot > 0 ? Number(sData.ot).toLocaleString() : '-';

            let cellCls = '';
            const sc = (sData.status_code || '').toUpperCase();
            if (sc === 'GREEN') cellCls = 'cell-green';
            else if (sc === 'YELLOW') cellCls = 'cell-yellow';
            else if (sc === 'ORANGE') cellCls = 'cell-orange';
            else if (sc === 'RED') cellCls = 'cell-red';
            else if (sc === 'GRAY') cellCls = 'cell-gray';

            cellsHtml += `
                <td class="num-cell ${cellCls}" style="text-align:right; padding:6px 8px;">${tgDisplay}</td>
                <td class="num-cell ${cellCls}" style="text-align:right; padding:6px 8px;">${ohDisplay}</td>
                <td class="num-cell ${cellCls}" style="text-align:right; padding:6px 8px;"><strong>${otDisplay}</strong></td>
            `;
        });

        tr.innerHTML = cellsHtml;
        tbody.appendChild(tr);
    });

    // 3. Render Summary Row: TOTAL / FINAL (Section 29)
    const summaryTr = document.createElement('tr');
    summaryTr.className = 'summary-row';
    summaryTr.style.background = '#d9e1f2';
    summaryTr.style.fontWeight = '700';
    let sumHtml = `<td class="col-date" style="padding:8px; font-weight:700;">TOTAL / FINAL</td>`;

    sections.forEach(s => {
        const sName = typeof s === 'string' ? s : (s.section_name || s.name || '');
        const sumData = getSectionDataFromDict(currentMatrixPlanData.summary, sName) || { total_tg: 0, final_on_hand: 0, total_ot: 0 };
        sumHtml += `
            <td class="num-cell" style="text-align:right; padding:8px;">${Number(sumData.total_tg || 0).toLocaleString()}</td>
            <td class="num-cell" style="text-align:right; padding:8px; color:#0284c7;">${Number(sumData.final_on_hand || 0).toLocaleString()}</td>
            <td class="num-cell" style="text-align:right; padding:8px; color:#16a34a;">${Number(sumData.total_ot || 0).toLocaleString()}</td>
        `;
    });

    summaryTr.innerHTML = sumHtml;
    tbody.appendChild(summaryTr);

    // Render Live Section Target Calculation Breakdown Card (Section 17)
    renderSectionExplanationCard();
}


// =========================================================================
// VIEW 2: SERIAL WIP FLOW PLANNING SHEET (Workflow, Incoming WIP, Movement)
// =========================================================================
let currentWipPlanData = null;

async function loadWipFlowSheet(targetOrderId = null) {
    const serialTbody = document.getElementById('serial-flow-tbody');
    const orderSelect = document.getElementById('wip-filter-order');
    if (!serialTbody) return;

    currentWipPlanData = null;
    serialTbody.innerHTML = '<tr><td colspan="12" class="text-center" style="padding:24px;">Loading date-wise serial WIP flow sheet...</td></tr>';

    try {
        // 1. Populate Order Selector if empty
        if (orderSelect && (orderSelect.options.length <= 1 || orderSelect.options[0].value === '')) {
            const ordRes = await apiFetch('/orders');
            if (ordRes.ok && ordRes.data) {
                orderSelect.innerHTML = '';
                ordRes.data.forEach(o => {
                    const opt = document.createElement('option');
                    opt.value = o.id;
                    opt.textContent = `${o.order_code} - ${o.buyer_name || 'Buyer'} (${Number(o.total_quantity).toLocaleString()} prs)`;
                    orderSelect.appendChild(opt);
                });
            }
        }

        const selectedOrderId = targetOrderId || orderSelect?.value || '';
        const url = `/orders/wip-flow-plan${selectedOrderId ? '?order_id=' + selectedOrderId : ''}`;
        const res = await apiFetch(url);

        if (!res.ok) {
            serialTbody.innerHTML = `<tr><td colspan="12" class="text-center text-danger" style="padding:24px;">
                ⚠️ Unable to load WIP Flow Plan: ${escapeHtml(res.error)}
                <small style="display:block; color:var(--text-dim); margin-top:4px;">Request ID: ${res.requestId}</small>
                <button class="btn btn-sm btn-outline" style="margin-top:8px;" onclick="loadWipFlowSheet('${selectedOrderId}')">🔄 Retry</button>
            </td></tr>`;
            return;
        }

        if (!res.data) {
            serialTbody.innerHTML = '<tr><td colspan="12" class="text-center text-muted" style="padding:24px;">No active production orders found in database. <button class="btn btn-sm btn-primary" onclick="openModal(\'create-order-modal\')">+ Create Order</button></td></tr>';
            return;
        }

        currentWipPlanData = res.data;
        if (orderSelect && currentWipPlanData.order_id) {
            orderSelect.value = currentWipPlanData.order_id;
        }


        // 2. Update Top Overview Banner
        const setEl = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };
        setEl('banner-buyer', currentWipPlanData.buyer_name || '-');
        setEl('banner-order-code', currentWipPlanData.order_code || '-');
        setEl('banner-order-qty', `${Number(currentWipPlanData.order_quantity || currentWipPlanData.total_quantity || 0).toLocaleString()} pairs`);
        setEl('banner-shipment-date', currentWipPlanData.shipment_date || '-');
        setEl('banner-days-remaining', `${currentWipPlanData.remaining_working_days} days`);
        setEl('banner-final-balance', `${Number(currentWipPlanData.final_balance).toLocaleString()} pairs`);
        setEl('banner-bottleneck', currentWipPlanData.current_bottleneck || currentWipPlanData.bottleneck_process || 'None');
        setEl('banner-wip-waiting', `${Number(currentWipPlanData.wip_waiting || currentWipPlanData.wip_waiting_quantity || 0).toLocaleString()} pairs`);

        const statusEl = document.getElementById('banner-overall-status');
        if (statusEl) {
            const st = currentWipPlanData.overall_status || 'ON TRACK';
            let badgeCls = 'wip-badge-ontrack';
            if (st === 'COMPLETED') badgeCls = 'wip-badge-completed';
            else if (st === 'OVERDUE') badgeCls = 'wip-badge-overdue';
            else if (st === 'WIP SHORTAGE') badgeCls = 'wip-badge-shortage';
            else if (st === 'AT RISK' || st === 'BEHIND TARGET') badgeCls = 'wip-badge-behind';
            statusEl.innerHTML = `<span class="wip-badge ${badgeCls}">${escapeHtml(st)}</span>`;
        }

        // 3. Render Serial Flow Rows
        renderSerialFlowRows();

        // 4. Render Workflow Summary Table
        renderWorkflowSummary(currentWipPlanData.workflow_summary || currentWipPlanData.summary || currentWipPlanData.workflow || []);

        // 5. Render Order Completion Summary
        renderOrderCompletionSummary(currentWipPlanData.completion_summary);

    } catch (e) {
        console.error('Error loading WIP flow planning sheet', e);
        serialTbody.innerHTML = `<tr><td colspan="12" class="text-center text-danger">⚠️ Exception: ${escapeHtml(e.message)} <button class="btn btn-sm btn-outline" onclick="loadWipFlowSheet()">Retry</button></td></tr>`;
    }
}

function renderSerialFlowRows() {
    if (!currentWipPlanData) return;
    const tbody = document.getElementById('serial-flow-tbody');
    if (!tbody) return;

    let rows = currentWipPlanData.daily_plan_rows || currentWipPlanData.rows || [];
    const dateFilter = document.getElementById('wip-filter-date-range')?.value || 'ALL';
    const statusHighlight = document.getElementById('wip-filter-status')?.value || 'ALL';

    // Date filtering
    const todayStr = new Date().toISOString().split('T')[0];
    if (dateFilter === 'TODAY') {
        rows = rows.filter(r => r.date === todayStr);
    } else if (dateFilter === 'THIS_WEEK') {
        const uniqueDates = Array.from(new Set(rows.map(r => r.date))).slice(0, 7);
        rows = rows.filter(r => uniqueDates.includes(r.date));
    } else if (dateFilter === 'SHIPMENT_WEEK') {
        const uniqueDates = Array.from(new Set(rows.map(r => r.date))).slice(-7);
        rows = rows.filter(r => uniqueDates.includes(r.date));
    }

    // Status filtering
    if (statusHighlight !== 'ALL') {
        rows = rows.filter(r => r.status === statusHighlight);
    }

    tbody.innerHTML = '';
    if (rows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="12" class="text-center text-muted" style="padding:20px;">No planning rows match the current filter criteria.</td></tr>';
        return;
    }

    let lastDate = null;
    rows.forEach(r => {
        // Date group separator if date changes
        if (r.date !== lastDate) {
            lastDate = r.date;
            const sepTr = document.createElement('tr');
            sepTr.className = 'date-group-header';
            const dayLabel = r.day_name ? ` (${r.day_name})` : '';
            const isWorkday = (r.is_workday !== undefined) ? r.is_workday : r.is_working_day;
            const offLabel = !isWorkday ? ' &mdash; <span class="wip-badge wip-badge-offday">FACTORY OFF DAY</span>' : '';
            sepTr.innerHTML = `<td colspan="12" style="padding: 7px 12px; font-weight:700; background:#f1f5f9; border-top: 2px solid #cbd5e1;">
                📅 <strong>${escapeHtml(r.date_display || r.date_str || r.date)}</strong>${dayLabel}${offLabel}
            </td>`;
            tbody.appendChild(sepTr);
        }

        const tr = document.createElement('tr');
        const isWorkday = (r.is_workday !== undefined) ? r.is_workday : r.is_working_day;
        if (!isWorkday) tr.className = 'row-off-day';

        let badgeClass = 'wip-badge-ontrack';
        if (r.status === 'COMPLETED') badgeClass = 'wip-badge-completed';
        else if (r.status === 'WIP SHORTAGE') badgeClass = 'wip-badge-shortage';
        else if (r.status === 'BEHIND TARGET' || r.status === 'AT RISK') badgeClass = 'wip-badge-behind';
        else if (r.status === 'OVERDUE') badgeClass = 'wip-badge-overdue';
        else if (r.status === 'NOT STARTED') badgeClass = 'wip-badge-notstarted';

        const rawTg = (r.target !== undefined && r.target !== null) ? r.target : r.tg;
        const tgDisplay = rawTg > 0 ? Number(rawTg).toLocaleString() : '-';
        const openOhDisplay = Number(r.opening_on_hand || 0).toLocaleString();
        const incomingDisplay = r.incoming_wip > 0 ? `+${Number(r.incoming_wip).toLocaleString()}` : '0';
        const rawAct = (r.actual !== undefined && r.actual !== null && r.actual > 0) ? r.actual : (r.actual_production > 0 ? r.actual_production : 0);
        const actDisplay = rawAct > 0 ? Number(rawAct).toLocaleString() : '-';
        const compDisplay = Number(r.complete || 0).toLocaleString();
        const closeOhDisplay = Number(r.closing_on_hand || 0).toLocaleString();
        const balDisplay = Number(r.balance || 0).toLocaleString();
        const remDays = (r.remaining_working_days !== undefined) ? r.remaining_working_days : (r.remaining_days || 0);

        const dateShort = (typeof r.date === 'string' && r.date.length >= 5) ? r.date.substring(5) : r.date;

        tr.innerHTML = `
            <td style="text-align: center; color: var(--text-dim); font-size: 11px;">${escapeHtml(String(dateShort))}</td>
            <td style="text-align: center; font-weight: 700;">${r.serial_no}</td>
            <td style="font-weight: 600;">${escapeHtml(r.section_name)}</td>
            <td class="num-val ${rawTg > 0 ? 'num-bold' : ''}">${tgDisplay}</td>
            <td class="num-val">${openOhDisplay}</td>
            <td class="num-val text-primary">${incomingDisplay}</td>
            <td class="num-val num-actual">${actDisplay}</td>
            <td class="num-val num-complete">${compDisplay}</td>
            <td class="num-val num-closing">${closeOhDisplay}</td>
            <td class="num-val text-danger">${balDisplay}</td>
            <td style="text-align: center;">${remDays}</td>
            <td style="text-align: center;"><span class="wip-badge ${badgeClass}">${escapeHtml(r.status)}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

function renderWorkflowSummary(workflowSummary) {
    const tbody = document.getElementById('workflow-summary-tbody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!workflowSummary || workflowSummary.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No workflow summary available.</td></tr>';
        return;
    }

    workflowSummary.forEach(item => {
        const tr = document.createElement('tr');
        let badgeCls = 'wip-badge-ontrack';
        if (item.status === 'COMPLETED') badgeCls = 'wip-badge-completed';
        else if (item.status === 'WIP SHORTAGE') badgeCls = 'wip-badge-shortage';
        else if (item.status === 'RUNNING') badgeCls = 'wip-badge-ontrack';

        const reqQty = (item.required_quantity !== undefined) ? item.required_quantity : (item.required_qty || 0);

        tr.innerHTML = `
            <td style="text-align: center; font-weight: 700;">${item.serial_no}</td>
            <td><strong>${escapeHtml(item.section_name)}</strong></td>
            <td style="text-align: right;">${Number(reqQty).toLocaleString()}</td>
            <td style="text-align: right;">${Number(item.total_tg || item.total_target || 0).toLocaleString()}</td>
            <td style="text-align: right;" class="text-success"><strong>${Number(item.complete || 0).toLocaleString()}</strong></td>
            <td style="text-align: right;" class="text-primary"><strong>${Number(item.final_on_hand || item.closing_on_hand || 0).toLocaleString()}</strong></td>
            <td style="text-align: right;" class="text-danger"><strong>${Number(item.balance || 0).toLocaleString()}</strong></td>
            <td style="text-align: center;"><span class="wip-badge ${badgeCls}">${escapeHtml(item.status)}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

function renderOrderCompletionSummary(summary) {
    if (!summary) return;
    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    };

    setVal('summary-order-qty', `${Number(summary.order_quantity || 0).toLocaleString()} pairs`);
    setVal('summary-completed-qty', `${Number(summary.completed_quantity || 0).toLocaleString()} pairs`);
    setVal('summary-outstanding-bal', `${Number(summary.final_balance !== undefined ? summary.final_balance : (summary.remaining_balance || 0)).toLocaleString()} pairs`);
    setVal('summary-days-remaining', `${summary.remaining_working_days !== undefined ? summary.remaining_working_days : (summary.days_remaining || 0)} working days`);
    setVal('summary-bottleneck', summary.current_bottleneck || summary.bottleneck_section || 'None');
    setVal('summary-wip-waiting', `${Number(summary.wip_waiting !== undefined ? summary.wip_waiting : (summary.wip_waiting_quantity || 0)).toLocaleString()} pairs`);
    
    const prodStatusEl = document.getElementById('summary-prod-status');
    if (prodStatusEl) {
        const st = summary.overall_status || 'ON TRACK';
        prodStatusEl.textContent = st;
        prodStatusEl.className = `wip-badge ${st === 'COMPLETED' ? 'wip-badge-completed' : (st === 'OVERDUE' ? 'wip-badge-overdue' : 'wip-badge-ontrack')}`;
    }
}

// Global convenience wrapper to reload both sheets
async function loadPlanningSheet(targetOrderId = null) {
    await Promise.allSettled([
        loadMatrixPlanningSheet(targetOrderId),
        loadWipFlowSheet(targetOrderId)
    ]);
}
async function loadPlanningSheetFilterDropdowns() {
    // Kept for backwards compatibility
}


// ----------------- REPORTS & EXPORTS TABLE -----------------
async function loadReportOrders() {
    const tbody = document.querySelector('#export-orders-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="10" class="text-center">Loading exportable orders...</td></tr>';

    try {
        const res = await apiFetch('/orders');
        if (!res.ok) {
            tbody.innerHTML = `<tr><td colspan="10" class="text-center text-danger" style="padding:15px;">
                ⚠️ Unable to load orders: ${escapeHtml(res.error)}
                <button class="btn btn-sm btn-outline" style="margin-top:6px;" onclick="loadReportOrders()">🔄 Retry</button>
            </td></tr>`;
            return;
        }

        const orders = res.data || [];
        tbody.innerHTML = '';
        if (orders.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted" style="padding:15px;">No orders found in database.</td></tr>';
            return;
        }

        orders.forEach(o => {
            const tr = document.createElement('tr');
            const targetDisplay = o.daily_target > 0 ? `${Number(o.daily_target).toLocaleString()} /day` : '0';
            tr.innerHTML = `
                <td><code>${escapeHtml(o.order_code)}</code></td>
                <td>${escapeHtml(o.buyer_name || '')}</td>
                <td>${escapeHtml(o.style_model)}</td>
                <td><strong>${Number(o.total_quantity).toLocaleString()}</strong></td>
                <td>${escapeHtml(o.current_delivery_date)}</td>
                <td>${o.remaining_working_days} days</td>
                <td><span class="cell-target">${targetDisplay}</span></td>
                <td><span class="status-badge status-${escapeHtml(o.status)}">${escapeHtml(o.status)}</span></td>
                <td><a class="btn btn-sm btn-primary" href="${API_BASE}/exports/orders/${o.id}/xlsx" target="_blank">Download XLSX</a></td>
                <td><a class="btn btn-sm btn-secondary" href="${API_BASE}/exports/orders/${o.id}/csv" target="_blank">Download CSV</a></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Error loading reports table', e);
        tbody.innerHTML = `<tr><td colspan="10" class="text-center text-danger">⚠️ Exception: ${escapeHtml(e.message)}</td></tr>`;
    }
}

// ----------------- DEPARTMENTS -----------------
async function loadDepartments() {
    const grid = document.getElementById('departments-display-grid');
    if (!grid) return;
    grid.innerHTML = '<div class="text-center" style="grid-column: 1/-1; padding: 20px;">Loading department catalog...</div>';

    try {
        const res = await apiFetch('/departments/categories');
        if (!res.ok) {
            grid.innerHTML = `<div class="text-center text-danger" style="grid-column: 1/-1; padding: 20px;">
                ⚠️ Unable to load departments: ${escapeHtml(res.error)}
                <button class="btn btn-sm btn-outline" style="margin-top:8px;" onclick="loadDepartments()">🔄 Retry</button>
            </div>`;
            return;
        }

        const categories = res.data || [];
        grid.innerHTML = '';
        if (categories.length === 0) {
            grid.innerHTML = '<div class="text-center text-muted" style="grid-column: 1/-1; padding: 20px;">No departments found.</div>';
            return;
        }

        categories.forEach(cat => {
            const card = document.createElement('div');
            card.className = 'dept-cat-card';
            card.innerHTML = `
                <h4>Category: ${escapeHtml(cat.name)}</h4>
                ${cat.sections.map(s => `
                    <div class="dept-sec-item">
                        <strong>${escapeHtml(s.name)}</strong>
                        ${s.templates && s.templates.length > 0 ? `
                            <div style="font-size:12px; color:var(--text-muted); margin-top:2px;">
                                Sub-processes: ${s.templates.map(t => escapeHtml(t.name)).join(', ')}
                            </div>
                        ` : '<div style="font-size:12px; color:var(--text-dim);">Single process section</div>'}
                    </div>
                `).join('')}
            `;
            grid.appendChild(card);
        });
    } catch (e) {
        console.error('Error loading departments', e);
        grid.innerHTML = `<div class="text-center text-danger" style="grid-column: 1/-1; padding: 20px;">⚠️ Exception: ${escapeHtml(e.message)}</div>`;
    }
}

// ----------------- SYSTEM DIAGNOSTICS (Section 30) -----------------
async function runDiagnostics() {
    const listEl = document.getElementById('diagnostics-probe-list');
    const overallEl = document.getElementById('diag-overall-status');
    const reqIdEl = document.getElementById('diag-req-id');
    if (!listEl) return;

    listEl.innerHTML = '<div class="text-center" style="padding:20px; color:var(--text-muted);">Probing system subsystems...</div>';
    overallEl.className = 'status-badge status-IN_PRODUCTION';
    overallEl.textContent = 'PROBING...';

    const res = await apiFetch('/diagnostics');
    if (!res.ok) {
        overallEl.className = 'status-badge status-OVERDUE';
        overallEl.textContent = 'FAIL';
        listEl.innerHTML = `<div class="error-banner" style="display:block;">
            Diagnostic Probe Failed: ${escapeHtml(res.error)}
            <small style="display:block; margin-top:4px;">Request ID: ${res.requestId}</small>
        </div>`;
        return;
    }

    const d = res.data;
    overallEl.className = d.overall_status === 'PASS' ? 'status-badge status-PRODUCTION_COMPLETE' : 'status-badge status-OVERDUE';
    overallEl.textContent = d.overall_status;
    if (reqIdEl) reqIdEl.textContent = `Req ID: ${d.request_id}`;

    listEl.innerHTML = '';
    d.subsystems.forEach(s => {
        const item = document.createElement('div');
        item.style.cssText = 'display:flex; justify-content:space-between; align-items:center; padding:10px 14px; background:var(--bg-surface); border-radius:6px; border:1px solid var(--border-color);';
        const isPass = s.status === 'PASS';
        const badge = isPass
            ? `<span class="status-badge status-PRODUCTION_COMPLETE">PASS</span>`
            : `<span class="status-badge status-OVERDUE">FAIL</span>`;

        item.innerHTML = `
            <div>
                <strong>${escapeHtml(s.subsystem)}</strong>
                <div style="font-size:12px; color:var(--text-muted); margin-top:2px;">${escapeHtml(s.details)}</div>
            </div>
            <div style="text-align:right;">
                ${badge}
                <div style="font-size:11px; color:var(--text-dim); margin-top:2px;">${s.latency_ms} ms</div>
            </div>
        `;
        listEl.appendChild(item);
    });
}

// ----------------- FORM SUBMISSIONS & MODALS -----------------
function initForms() {
    // Add Buyer Form
    const btnAddBuyer = document.getElementById('btn-add-buyer');
    if (btnAddBuyer) {
        btnAddBuyer.onclick = () => openModal('add-buyer-modal');
    }

    document.getElementById('add-buyer-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const errBanner = document.getElementById('buyer-error');
        errBanner.classList.add('hidden');

        const payload = {
            name: document.getElementById('buyer-name').value.trim(),
            buyer_code: document.getElementById('buyer-code').value.trim(),
            contact_person: document.getElementById('buyer-contact').value.trim(),
            phone: document.getElementById('buyer-phone').value.trim(),
            email: document.getElementById('buyer-email').value.trim(),
            address: document.getElementById('buyer-address').value.trim(),
            is_active: true
        };

        const res = await apiFetch('/buyers', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            errBanner.textContent = res.error;
            errBanner.classList.remove('hidden');
            return;
        }

        closeModal('add-buyer-modal');
        loadBuyers();
        showToast('Buyer created successfully.');
    });

    // Workflow Builder for New Order
    initWorkflowBuilder();

    // Factory Calendar Forms & WIP Adjustment Handlers
    initCalendarForms();
    initWipAdjustmentModal();

    // Create Order Form
    document.getElementById('create-order-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const errBanner = document.getElementById('new-order-error');
        errBanner.classList.add('hidden');

        if (!newOrderWorkflow || newOrderWorkflow.length === 0) {
            errBanner.textContent = 'Please configure at least one production workflow section.';
            errBanner.classList.remove('hidden');
            return;
        }

        const routesPayload = newOrderWorkflow.map((item, idx) => ({
            serial_no: idx + 1,
            section_name: item.section_name.trim(),
            transfer_rule: item.transfer_rule || 'IMMEDIATE',
            status: 'REQUIRED'
        }));

        const payload = {
            buyer_id: parseInt(document.getElementById('new-order-buyer').value),
            order_code: document.getElementById('new-order-code').value.trim() || null,
            customer_ref: document.getElementById('new-order-ref').value.trim(),
            po_number: document.getElementById('new-order-po').value.trim() || null,
            style_model: document.getElementById('new-order-style').value.trim(),
            total_quantity: parseFloat(document.getElementById('new-order-qty').value),
            production_start_date: document.getElementById('new-order-start').value || null,
            original_delivery_date: document.getElementById('new-order-delivery').value,
            priority: document.getElementById('new-order-priority').value,
            description: document.getElementById('new-order-desc').value.trim() || null,
            routes: routesPayload
        };

        const res = await apiFetch('/orders', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            errBanner.textContent = res.error;
            errBanner.classList.remove('hidden');
            return;
        }

        closeModal('create-order-modal');
        loadOrders();
        loadDashboard();
        loadPlanningSheet(res.data?.id);
        showToast('Order created with serial production workflow (S/N 1 -> 2 -> 3...).');
    });

    // Revise Date Form
    document.getElementById('revise-date-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const orderId = document.getElementById('revise-order-id').value;
        const newDate = document.getElementById('revise-new-date').value;
        const reason = document.getElementById('revise-reason').value.trim();

        const res = await apiFetch(`/orders/${orderId}/revise-delivery-date`, {
            method: 'POST',
            body: JSON.stringify({
                revised_delivery_date: newDate,
                reason: reason
            })
        });

        if (!res.ok) {
            alert('Failed to revise deadline: ' + res.error);
            return;
        }

        closeModal('revise-date-modal');
        openOrderDetails(orderId);
        loadOrders();
        loadDashboard();
        showToast('Delivery date revised. Daily targets and schedule recalculated.');
    });

    // Production Entry Form
    document.getElementById('production-entry-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const alertEl = document.getElementById('entry-alert');
        alertEl.classList.add('hidden');

        const orderId = document.getElementById('entry-order-select').value;
        const routeId = document.getElementById('entry-route-select').value;
        const opId = document.getElementById('entry-operation-select').value;
        const compId = document.getElementById('entry-component-select').value || null;

        const payload = {
            entry_date: document.getElementById('entry-date').value,
            order_id: parseInt(orderId),
            route_id: parseInt(routeId),
            operation_id: parseInt(opId),
            component_id: compId ? parseInt(compId) : null,
            quantity: parseFloat(document.getElementById('entry-qty').value),
            accepted_quantity: parseFloat(document.getElementById('entry-accepted-qty').value),
            rejected_quantity: parseFloat(document.getElementById('entry-rejected-qty').value || '0'),
            unit: 'PAIRS',
            remarks: document.getElementById('entry-remarks').value.trim() || null,
            is_override: document.getElementById('entry-override').checked
        };

        const res = await apiFetch('/production/entry', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            alertEl.textContent = res.error;
            alertEl.classList.remove('hidden');
            return;
        }

        const result = res.data;
        showToast('Production saved successfully. Planning target updated automatically.');

        if (result.updated_balance !== null && result.updated_balance !== undefined) {
            updateBalanceBanner(
                result.updated_balance,
                result.updated_daily_target,
                result.remaining_days,
                result.unit,
                result.available_on_hand,
                result.executable_target
            );
        }

        // Reset inputs
        document.getElementById('entry-qty').value = '';
        document.getElementById('entry-accepted-qty').value = '';
        document.getElementById('entry-rejected-qty').value = '0';
        document.getElementById('entry-override').checked = false;

        loadRecentProductionEntries();
        loadDashboard();
        loadOrders();
        loadPlanningSheet();

        if (currentOrderDetails && currentOrderDetails.id == orderId) {
            openOrderDetails(orderId);
        }
    });

    document.getElementById('btn-refresh-entries').onclick = () => loadRecentProductionEntries();
}

async function loadBuyerDropdownForNewOrder() {
    const select = document.getElementById('new-order-buyer');
    if (!select) return;
    select.innerHTML = '<option value="">Loading buyers...</option>';
    const res = await apiFetch('/buyers');
    if (!res.ok || !res.data) {
        select.innerHTML = `<option value="">Error loading buyers: ${res.error}</option>`;
        return;
    }
    const buyers = res.data;
    select.innerHTML = '';
    if (buyers.length === 0) {
        select.innerHTML = '<option value="">-- No buyers available. Please create buyer first --</option>';
        return;
    }
    buyers.forEach(b => {
        const opt = document.createElement('option');
        opt.value = b.id;
        opt.textContent = `${b.name} (${b.buyer_code})`;
        select.appendChild(opt);
    });

    // Initialize default dates
    const startInp = document.getElementById('new-order-start');
    if (startInp && !startInp.value) {
        startInp.value = new Date().toISOString().split('T')[0];
    }
    const delivInp = document.getElementById('new-order-delivery');
    if (delivInp && !delivInp.value) {
        const d = new Date();
        d.setDate(d.getDate() + 14);
        delivInp.value = d.toISOString().split('T')[0];
    }

    renderNewOrderWorkflowTable();
}

// ----------------- WORKFLOW BUILDER -----------------
let newOrderWorkflow = [
    { section_name: 'Cutting', transfer_rule: 'IMMEDIATE' },
    { section_name: 'Printing', transfer_rule: 'IMMEDIATE' },
    { section_name: 'Embosse', transfer_rule: 'IMMEDIATE' },
    { section_name: 'Sewing', transfer_rule: 'IMMEDIATE' },
    { section_name: 'Lasting', transfer_rule: 'IMMEDIATE' }
];

const STANDARD_SECTIONS = [
    'Cutting', 'Printing', 'Embosse', 'Sewing', 'Stockfitting', 'Lasting', 
    'Upper Prep', 'Stitching', 'Dip', 'Finishing', 'Quality', 'Packing'
];

function initWorkflowBuilder() {
    const btnPresetStd = document.getElementById('btn-wf-preset-standard');
    const btnPresetBasic = document.getElementById('btn-wf-preset-basic');
    const btnWfAddSec = document.getElementById('btn-wf-add-section');

    if (btnPresetStd) {
        btnPresetStd.addEventListener('click', () => {
            newOrderWorkflow = [
                { section_name: 'Cutting', transfer_rule: 'IMMEDIATE' },
                { section_name: 'Printing', transfer_rule: 'IMMEDIATE' },
                { section_name: 'Embosse', transfer_rule: 'IMMEDIATE' },
                { section_name: 'Sewing', transfer_rule: 'IMMEDIATE' },
                { section_name: 'Lasting', transfer_rule: 'IMMEDIATE' }
            ];
            renderNewOrderWorkflowTable();
        });
    }

    if (btnPresetBasic) {
        btnPresetBasic.addEventListener('click', () => {
            newOrderWorkflow = [
                { section_name: 'Cutting', transfer_rule: 'IMMEDIATE' },
                { section_name: 'Sewing', transfer_rule: 'IMMEDIATE' },
                { section_name: 'Lasting', transfer_rule: 'IMMEDIATE' }
            ];
            renderNewOrderWorkflowTable();
        });
    }

    if (btnWfAddSec) {
        btnWfAddSec.addEventListener('click', () => {
            newOrderWorkflow.push({ section_name: 'Lasting', transfer_rule: 'IMMEDIATE' });
            renderNewOrderWorkflowTable();
        });
    }

    renderNewOrderWorkflowTable();
}

function renderNewOrderWorkflowTable() {
    const tbody = document.getElementById('new-order-workflow-tbody');
    if (!tbody) return;
    tbody.innerHTML = '';

    newOrderWorkflow.forEach((item, index) => {
        const tr = document.createElement('tr');
        
        let sectionOptions = STANDARD_SECTIONS.map(s => 
            `<option value="${s}" ${s.toLowerCase() === item.section_name.toLowerCase() ? 'selected' : ''}>${s}</option>`
        ).join('');
        
        const isCustom = !STANDARD_SECTIONS.some(s => s.toLowerCase() === item.section_name.toLowerCase());
        if (isCustom && item.section_name) {
            sectionOptions += `<option value="${escapeHtml(item.section_name)}" selected>${escapeHtml(item.section_name)} (Custom)</option>`;
        }
        sectionOptions += `<option value="__custom__">+ Custom Process...</option>`;

        tr.innerHTML = `
            <td style="text-align: center; font-weight: 700; color: #1f4e79;">${index + 1}</td>
            <td>
                <select class="wf-sec-select" data-index="${index}">
                    ${sectionOptions}
                </select>
                <input type="text" class="wf-sec-custom ${isCustom ? '' : 'hidden'}" data-index="${index}" value="${escapeHtml(item.section_name)}" placeholder="Enter custom section name" style="margin-top:4px;">
            </td>
            <td>
                <select class="wf-transfer-select" data-index="${index}">
                    <option value="IMMEDIATE" ${item.transfer_rule === 'IMMEDIATE' ? 'selected' : ''}>Immediate (Same Day)</option>
                    <option value="NEXT_WORKING_DAY" ${item.transfer_rule === 'NEXT_WORKING_DAY' ? 'selected' : ''}>Next Working Day</option>
                </select>
            </td>
            <td style="text-align: center; white-space: nowrap;">
                <button type="button" class="btn-icon-xs btn-move-up" data-index="${index}" title="Move Up" ${index === 0 ? 'disabled' : ''}>⬆️</button>
                <button type="button" class="btn-icon-xs btn-move-down" data-index="${index}" title="Move Down" ${index === newOrderWorkflow.length - 1 ? 'disabled' : ''}>⬇️</button>
                <button type="button" class="btn-icon-xs btn-remove" data-index="${index}" title="Remove Section">❌</button>
            </td>
        `;
        tbody.appendChild(tr);
    });

    tbody.querySelectorAll('.wf-sec-select').forEach(sel => {
        sel.addEventListener('change', (e) => {
            const idx = parseInt(e.target.dataset.index);
            const val = e.target.value;
            const customInput = e.target.closest('td').querySelector('.wf-sec-custom');
            if (val === '__custom__') {
                customInput.classList.remove('hidden');
                customInput.focus();
                newOrderWorkflow[idx].section_name = customInput.value || 'Custom Section';
            } else {
                customInput.classList.add('hidden');
                newOrderWorkflow[idx].section_name = val;
            }
        });
    });

    tbody.querySelectorAll('.wf-sec-custom').forEach(inp => {
        inp.addEventListener('input', (e) => {
            const idx = parseInt(e.target.dataset.index);
            newOrderWorkflow[idx].section_name = e.target.value.trim();
        });
    });

    tbody.querySelectorAll('.wf-transfer-select').forEach(sel => {
        sel.addEventListener('change', (e) => {
            const idx = parseInt(e.target.dataset.index);
            newOrderWorkflow[idx].transfer_rule = e.target.value;
        });
    });

    tbody.querySelectorAll('.btn-move-up').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const idx = parseInt(e.target.dataset.index);
            if (idx > 0) {
                const temp = newOrderWorkflow[idx];
                newOrderWorkflow[idx] = newOrderWorkflow[idx - 1];
                newOrderWorkflow[idx - 1] = temp;
                renderNewOrderWorkflowTable();
            }
        });
    });

    tbody.querySelectorAll('.btn-move-down').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const idx = parseInt(e.target.dataset.index);
            if (idx < newOrderWorkflow.length - 1) {
                const temp = newOrderWorkflow[idx];
                newOrderWorkflow[idx] = newOrderWorkflow[idx + 1];
                newOrderWorkflow[idx + 1] = temp;
                renderNewOrderWorkflowTable();
            }
        });
    });

    tbody.querySelectorAll('.btn-remove').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const idx = parseInt(e.target.dataset.index);
            if (newOrderWorkflow.length <= 1) {
                showToast('Workflow must have at least one section.');
                return;
            }
            newOrderWorkflow.splice(idx, 1);
            renderNewOrderWorkflowTable();
        });
    });
}

// ----------------- FACTORY CALENDAR MANAGEMENT -----------------
let activeCalendar = null;

async function loadFactoryCalendar() {
    const res = await apiFetch('/calendar/active');
    if (!res.ok || !res.data) {
        showToast('Error loading factory calendar: ' + (res.error || 'Not found'));
        return;
    }
    activeCalendar = res.data;
    
    const setCb = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.checked = Boolean(val);
    };
    setCb('cal-work-friday', activeCalendar.work_friday);
    setCb('cal-work-saturday', activeCalendar.work_saturday);
    setCb('cal-work-sunday', activeCalendar.work_sunday);
    setCb('cal-work-monday', activeCalendar.work_monday);
    setCb('cal-work-tuesday', activeCalendar.work_tuesday);
    setCb('cal-work-wednesday', activeCalendar.work_wednesday);
    setCb('cal-work-thursday', activeCalendar.work_thursday);
    
    const cutH = document.getElementById('cal-cutoff-hour');
    if (cutH) cutH.value = activeCalendar.daily_cutoff_hour ?? 18;
    const cutM = document.getElementById('cal-cutoff-minute');
    if (cutM) cutM.value = activeCalendar.daily_cutoff_minute ?? 0;

    renderCalendarExceptions(activeCalendar.exceptions || []);
}

function renderCalendarExceptions(exceptions) {
    const tbody = document.getElementById('calendar-exceptions-tbody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!exceptions || exceptions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted" style="padding:16px;">No calendar exceptions configured. Click "+ Add Factory Holiday" or "+ Add Special Working Day" to add one.</td></tr>';
        return;
    }

    const sorted = [...exceptions].sort((a, b) => a.exception_date.localeCompare(b.exception_date));
    sorted.forEach(ex => {
        const tr = document.createElement('tr');
        const isWorking = ex.exception_type === 'special_working_day';
        const impactBadge = isWorking 
            ? '<span class="wip-badge wip-badge-completed">WORKING (+ T/G)</span>' 
            : '<span class="wip-badge wip-badge-overdue">OFF DAY (Excluded)</span>';
        
        const typeLabels = {
            'factory_holiday': 'Factory Holiday',
            'government_holiday': 'Government Holiday',
            'emergency_off': 'Emergency Off Day',
            'factory_shutdown': 'Factory Shutdown',
            'special_working_day': 'Special Working Day',
            'custom_off_day': 'Custom Off Day'
        };
        const typeLabel = typeLabels[ex.exception_type] || ex.exception_type;

        tr.innerHTML = `
            <td style="font-weight: 600;">${escapeHtml(ex.exception_date)}</td>
            <td>${escapeHtml(typeLabel)}</td>
            <td>${escapeHtml(ex.description || '-')}</td>
            <td style="text-align: center;">${impactBadge}</td>
            <td style="text-align: center;">
                <button type="button" class="btn-icon-xs btn-remove" onclick="deleteCalendarException(${ex.id})" title="Delete Exception">🗑️</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

window.deleteCalendarException = async function(id) {
    if (!confirm('Remove this calendar exception? Future planning targets will automatically recalculate.')) return;
    const res = await apiFetch(`/calendar/exceptions/${id}`, { method: 'DELETE' });
    if (res.ok) {
        showToast('Calendar exception removed. Recalculating targets...');
        loadFactoryCalendar();
        loadPlanningSheet();
    } else {
        showToast('Error removing exception: ' + res.error);
    }
};

function initCalendarForms() {
    const formWeekly = document.getElementById('form-weekly-schedule');
    if (formWeekly) {
        formWeekly.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (!activeCalendar) return;
            const payload = {
                work_friday: document.getElementById('cal-work-friday')?.checked,
                work_saturday: document.getElementById('cal-work-saturday')?.checked,
                work_sunday: document.getElementById('cal-work-sunday')?.checked,
                work_monday: document.getElementById('cal-work-monday')?.checked,
                work_tuesday: document.getElementById('cal-work-tuesday')?.checked,
                work_wednesday: document.getElementById('cal-work-wednesday')?.checked,
                work_thursday: document.getElementById('cal-work-thursday')?.checked,
                daily_cutoff_hour: parseInt(document.getElementById('cal-cutoff-hour')?.value || '18'),
                daily_cutoff_minute: parseInt(document.getElementById('cal-cutoff-minute')?.value || '0')
            };
            const res = await apiFetch(`/calendar/${activeCalendar.id}`, {
                method: 'PUT',
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                showToast('Weekly schedule updated! Targets recalculated automatically.');
                loadFactoryCalendar();
                loadPlanningSheet();
            } else {
                showToast('Error updating schedule: ' + res.error);
            }
        });
    }

    document.getElementById('btn-open-add-holiday')?.addEventListener('click', () => {
        openModal('add-holiday-modal');
        document.getElementById('holiday-date').value = new Date().toISOString().split('T')[0];
    });

    document.getElementById('btn-open-add-workday')?.addEventListener('click', () => {
        openModal('add-workday-modal');
        document.getElementById('workday-date').value = new Date().toISOString().split('T')[0];
    });

    document.getElementById('form-add-holiday')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!activeCalendar) return;
        const dateVal = document.getElementById('holiday-date').value;
        const typeVal = document.getElementById('holiday-type').value;
        const descVal = document.getElementById('holiday-reason').value;
        const res = await apiFetch(`/calendar/${activeCalendar.id}/exceptions`, {
            method: 'POST',
            body: JSON.stringify({
                exception_date: dateVal,
                exception_type: typeVal,
                description: descVal
            })
        });
        if (res.ok) {
            closeModal('add-holiday-modal');
            showToast('Holiday added. Future planning targets updated automatically.');
            loadFactoryCalendar();
            loadPlanningSheet();
        } else {
            const err = document.getElementById('holiday-error');
            if (err) {
                err.textContent = res.error;
                err.classList.remove('hidden');
            }
        }
    });

    document.getElementById('form-add-workday')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!activeCalendar) return;
        const dateVal = document.getElementById('workday-date').value;
        const descVal = document.getElementById('workday-reason').value;
        const res = await apiFetch(`/calendar/${activeCalendar.id}/exceptions`, {
            method: 'POST',
            body: JSON.stringify({
                exception_date: dateVal,
                exception_type: 'special_working_day',
                description: descVal
            })
        });
        if (res.ok) {
            closeModal('add-workday-modal');
            showToast('Special working day added. Targets recalculated automatically.');
            loadFactoryCalendar();
            loadPlanningSheet();
        } else {
            const err = document.getElementById('workday-error');
            if (err) {
                err.textContent = res.error;
                err.classList.remove('hidden');
            }
        }
    });
}

// ----------------- CONTROLLED WIP ADJUSTMENT -----------------
function initWipAdjustmentModal() {
    const btnOpen = document.getElementById('btn-open-wip-adj');
    if (!btnOpen) return;

    btnOpen.addEventListener('click', async () => {
        const orderSelect = document.getElementById('wip-adj-order');
        const flowSelect = document.getElementById('wip-adj-workflow');
        const curOrder = document.getElementById('matrix-filter-order')?.value;
        
        const ordRes = await apiFetch('/orders');
        if (ordRes.ok && ordRes.data && orderSelect) {
            orderSelect.innerHTML = '';
            ordRes.data.forEach(o => {
                const opt = document.createElement('option');
                opt.value = o.id;
                opt.textContent = `${o.order_code} - ${o.customer_ref}`;
                orderSelect.appendChild(opt);
            });
            if (curOrder) orderSelect.value = curOrder;
        }

        async function loadWorkflowForOrder(orderId) {
            if (!orderId || !flowSelect) return;
            flowSelect.innerHTML = '<option value="">Loading sections...</option>';
            const planRes = await apiFetch(`/orders/${orderId}/wip-flow-plan`);
            if (planRes.ok && planRes.data && planRes.data.sections) {
                flowSelect.innerHTML = '';
                planRes.data.sections.forEach(s => {
                    const opt = document.createElement('option');
                    opt.value = s.id;
                    opt.textContent = `${s.serial_no}. ${s.section_name}`;
                    flowSelect.appendChild(opt);
                });
            }
        }

        orderSelect.onchange = () => loadWorkflowForOrder(orderSelect.value);
        if (orderSelect.value) {
            await loadWorkflowForOrder(orderSelect.value);
        }

        document.getElementById('wip-adj-date').value = new Date().toISOString().split('T')[0];
        document.getElementById('wip-adj-qty').value = '';
        document.getElementById('wip-adj-reason').value = '';
        document.getElementById('wip-adj-error')?.classList.add('hidden');
        openModal('wip-adjustment-modal');
    });

    document.getElementById('form-wip-adjustment')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const orderId = document.getElementById('wip-adj-order').value;
        const workflowId = document.getElementById('wip-adj-workflow').value;
        const adjDate = document.getElementById('wip-adj-date').value;
        const qty = parseFloat(document.getElementById('wip-adj-qty').value);
        const reason = document.getElementById('wip-adj-reason').value.trim();

        const res = await apiFetch(`/orders/${orderId}/wip-adjustments`, {
            method: 'POST',
            body: JSON.stringify({
                workflow_id: parseInt(workflowId),
                date: adjDate,
                quantity: qty,
                reason: reason
            })
        });

        if (res.ok) {
            closeModal('wip-adjustment-modal');
            showToast('Controlled WIP adjustment recorded and applied to live On Hand.');
            loadPlanningSheet(orderId);
        } else {
            const err = document.getElementById('wip-adj-error');
            if (err) {
                err.textContent = res.error;
                err.classList.remove('hidden');
            }
        }
    });
}

window.openModal = function(id) {
    const m = document.getElementById(id);
    if (m) m.classList.add('active');
};

window.closeModal = function(id) {
    const m = document.getElementById(id);
    if (m) m.classList.remove('active');
};

// ----------------- SECTION TARGET EXPLANATION CARD (Section 17) -----------------
function renderSectionExplanationCard(selectedSecName = null) {
    const card = document.getElementById('matrix-section-explanation-card');
    const select = document.getElementById('matrix-inspect-section-select');
    const body = document.getElementById('matrix-section-explanation-body');
    if (!card || !select || !body || !currentMatrixPlanData) {
        if (card) card.style.display = 'none';
        return;
    }

    const sections = currentMatrixPlanData.sections || [];
    if (sections.length === 0) {
        card.style.display = 'none';
        return;
    }

    // Populate dropdown if options changed
    const currentVal = selectedSecName || select.value;
    select.innerHTML = '';
    sections.forEach(s => {
        const sName = typeof s === 'string' ? s : (s.section_name || s.name || '');
        const opt = document.createElement('option');
        opt.value = sName;
        opt.textContent = sName;
        select.appendChild(opt);
    });

    if (currentVal && Array.from(select.options).some(o => o.value === currentVal)) {
        select.value = currentVal;
    } else if (select.options.length > 0) {
        select.selectedIndex = 0;
    }

    const activeSecName = select.value;
    const summary = currentMatrixPlanData.summary || {};
    const sumData = getSectionDataFromDict(summary, activeSecName) || {};
    
    // Find section metadata
    const secMeta = sections.find(s => {
        const n = typeof s === 'string' ? s : (s.section_name || s.name || '');
        return n.toLowerCase() === activeSecName.toLowerCase();
    }) || {};

    const effMin = sumData.effective_minimum_target != null ? sumData.effective_minimum_target : (secMeta.minimum_daily_target != null ? secMeta.minimum_daily_target : 0);
    const effMax = sumData.maximum_daily_target != null ? sumData.maximum_daily_target : (secMeta.maximum_daily_target != null ? secMeta.maximum_daily_target : 0);
    const curBal = sumData.balance != null ? sumData.balance : (secMeta.balance != null ? secMeta.balance : (currentMatrixPlanData.current_balance || 0));
    const remDays = currentMatrixPlanData.remaining_working_days || currentMatrixPlanData.working_days || 1;
    const reqDailyRate = sumData.required_daily_rate != null ? sumData.required_daily_rate : (secMeta.required_daily_rate != null ? secMeta.required_daily_rate : (remDays > 0 ? Math.ceil(curBal / remDays) : curBal));
    
    // Look at today or first future date for planned T/G and On Hand
    const rows = currentMatrixPlanData.rows || [];
    const todayStr = new Date().toISOString().split('T')[0];
    let activeRow = rows.find(r => r.date === todayStr);
    if (!activeRow) {
        activeRow = rows.find(r => r.date >= todayStr) || rows[0];
    }
    const secRowData = activeRow ? (getSectionDataFromDict(activeRow.section_data, activeSecName) || {}) : {};
    
    const plannedTg = secRowData.tg != null ? secRowData.tg : (sumData.executable_daily_target != null ? sumData.executable_daily_target : 0);
    const onHand = sumData.allocatable_wip != null ? sumData.allocatable_wip : (secMeta.allocatable_wip != null ? secMeta.allocatable_wip : (secRowData.on_hand != null ? secRowData.on_hand : (sumData.final_on_hand || 0)));
    const statusStr = secRowData.status || (sumData.status || (onHand <= 0 && curBal > 0 ? 'WAITING FOR WIP' : 'ON TRACK'));
    
    let reason = "Normal balanced rate allocated across available working days.";
    if (onHand <= 0 && curBal > 0) {
        reason = "No upstream WIP received yet. Target cannot be planned until actual stock arrives.";
    } else if (onHand > 0 && onHand < reqDailyRate) {
        reason = "Current WIP availability limits today's executable target.";
    } else if (effMin > reqDailyRate && plannedTg === effMin) {
        reason = "Configured minimum daily target applies, accelerating production timeline.";
    } else if (effMax > 0 && reqDailyRate > effMax) {
        reason = `Configured maximum capacity (${effMax} prs) caps the daily schedule below required rate.`;
    } else if (curBal <= 0) {
        reason = "Section requirement completed.";
    }

    let badgeColor = '#16a34a';
    if (statusStr === 'WAITING FOR WIP' || statusStr === 'WIP SHORTAGE') badgeColor = '#ea580c';
    else if (statusStr === 'PARTIALLY AVAILABLE' || statusStr === 'BEHIND TARGET') badgeColor = '#ca8a04';
    else if (statusStr === 'OVERDUE' || statusStr === 'CAPACITY CONSTRAINT') badgeColor = '#dc2626';

    body.innerHTML = `
        <div style="background:#fff; padding:10px 14px; border-radius:6px; border:1px solid #e2e8f0;">
            <div style="font-size:11px; color:#64748b; font-weight:600; text-transform:uppercase;">Section</div>
            <div style="font-size:15px; font-weight:700; color:#0f172a;">${escapeHtml(activeSecName)}</div>
        </div>
        <div style="background:#fff; padding:10px 14px; border-radius:6px; border:1px solid #e2e8f0;">
            <div style="font-size:11px; color:#64748b; font-weight:600; text-transform:uppercase;">Required Daily Rate</div>
            <div style="font-size:15px; font-weight:700; color:#0284c7;">${Number(reqDailyRate).toLocaleString()} prs</div>
        </div>
        <div style="background:#fff; padding:10px 14px; border-radius:6px; border:1px solid #e2e8f0;">
            <div style="font-size:11px; color:#64748b; font-weight:600; text-transform:uppercase;">Min / Max Target</div>
            <div style="font-size:14px; font-weight:700; color:#475569;">${effMin > 0 ? Number(effMin).toLocaleString() : '0'} / ${effMax > 0 ? Number(effMax).toLocaleString() : 'Unlimited'}</div>
        </div>
        <div style="background:#fff; padding:10px 14px; border-radius:6px; border:1px solid #e2e8f0;">
            <div style="font-size:11px; color:#64748b; font-weight:600; text-transform:uppercase;">Actual Available WIP</div>
            <div style="font-size:15px; font-weight:700; color:${onHand > 0 ? '#16a34a' : '#ea580c'};">${Number(onHand).toLocaleString()} prs</div>
        </div>
        <div style="background:#fff; padding:10px 14px; border-radius:6px; border:1px solid #e2e8f0;">
            <div style="font-size:11px; color:#64748b; font-weight:600; text-transform:uppercase;">Executable T/G</div>
            <div style="font-size:15px; font-weight:700; color:#1e3a8a;">${Number(plannedTg).toLocaleString()} prs</div>
        </div>
        <div style="background:#fff; padding:10px 14px; border-radius:6px; border:1px solid #e2e8f0;">
            <div style="font-size:11px; color:#64748b; font-weight:600; text-transform:uppercase;">Status</div>
            <div style="font-size:13px; font-weight:700; color:${badgeColor};">${escapeHtml(statusStr)}</div>
        </div>
        <div style="grid-column: 1 / -1; background:#ffffff; padding:10px 14px; border-radius:6px; border:1px solid #e2e8f0; font-size:12px; color:#334155;">
            <strong>Calculation Reason:</strong> ${escapeHtml(reason)}
        </div>
    `;

    card.style.display = 'block';

    select.onchange = () => {
        renderSectionExplanationCard(select.value);
    };
}

// ----------------- DEPARTMENT STRUCTURE & TARGET SETTINGS -----------------
let allTargetSettings = [];

async function loadDepartments() {
    const grid = document.getElementById('departments-display-grid');
    if (grid) {
        grid.innerHTML = '<div style="padding:20px; text-align:center;">Loading department structure...</div>';
        const res = await apiFetch('/departments');
        if (res.ok && res.data) {
            let html = '';
            res.data.forEach(cat => {
                html += `
                    <div class="card" style="margin-bottom:14px; border:1px solid #e2e8f0;">
                        <div class="card-header" style="background:#f8fafc; padding:10px 14px;">
                            <h4 style="margin:0; font-size:14px; color:#1e293b;">${escapeHtml(cat.name)}</h4>
                        </div>
                        <div style="padding:10px 14px; display:flex; flex-wrap:wrap; gap:8px;">
                            ${(cat.sections || []).map(s => `
                                <span style="background:#e2e8f0; color:#334155; font-size:12px; padding:4px 10px; border-radius:14px; font-weight:500;">
                                    ${escapeHtml(s.name)}
                                </span>
                            `).join('')}
                        </div>
                    </div>
                `;
            });
            grid.innerHTML = html || '<div class="text-muted" style="padding:14px;">No departments found.</div>';
        } else {
            grid.innerHTML = '<div class="text-danger" style="padding:14px;">Failed to load departments.</div>';
        }
    }
    loadProductionTargetSettings();
}

async function loadProductionTargetSettings() {
    const tbody = document.getElementById('target-settings-tbody');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="8" class="text-center" style="padding:20px;">Loading target settings...</td></tr>';
    const res = await apiFetch('/departments/target-settings');
    if (!res.ok) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center text-danger" style="padding:20px;">Failed to load target settings: ${escapeHtml(res.error)}</td></tr>`;
        return;
    }

    allTargetSettings = res.data || [];
    renderTargetSettingsTable();
}

function renderTargetSettingsTable() {
    const tbody = document.getElementById('target-settings-tbody');
    const searchVal = (document.getElementById('target-settings-search')?.value || '').toLowerCase().trim();
    if (!tbody) return;

    let items = allTargetSettings;
    if (searchVal) {
        items = items.filter(i => 
            (i.section_name || '').toLowerCase().includes(searchVal) ||
            (i.category_name || '').toLowerCase().includes(searchVal)
        );
    }

    if (items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted" style="padding:20px;">No target settings found matching search filter.</td></tr>';
        return;
    }

    tbody.innerHTML = items.map(i => {
        const minStr = i.minimum_daily_target != null ? Number(i.minimum_daily_target).toLocaleString() : '0';
        const maxStr = (i.maximum_daily_target != null && i.maximum_daily_target > 0)
            ? Number(i.maximum_daily_target).toLocaleString()
            : '<span class="text-muted">Unlimited</span>';
        const statusBadge = i.is_active
            ? '<span class="status-badge" style="background:#dcfce7; color:#15803d; font-weight:600;">Active</span>'
            : '<span class="status-badge" style="background:#f1f5f9; color:#64748b; font-weight:600;">Inactive</span>';
        const changedAt = i.updated_at ? new Date(i.updated_at).toLocaleString() : 'System Default';
        const changedBy = i.updated_by_name || 'System';

        return `
            <tr>
                <td style="font-weight:600; color:#334155;">${escapeHtml(i.category_name)}</td>
                <td style="font-weight:700; color:#0f172a;">${escapeHtml(i.section_name)}</td>
                <td style="text-align:right; font-weight:700; color:#0369a1;">${minStr}</td>
                <td style="text-align:right; font-weight:700; color:#2563eb;">${maxStr}</td>
                <td style="color:#64748b;">${escapeHtml(i.unit || 'Pairs/day')}</td>
                <td>${statusBadge}</td>
                <td style="font-size:12px; color:#64748b;">${escapeHtml(changedAt)}</td>
                <td style="font-size:12px; color:#64748b;">${escapeHtml(changedBy)}</td>
                <td style="text-align:center;">
                    <button class="btn btn-sm btn-outline" onclick="openEditTargetSettingModal(${i.section_id})">
                        ✏️ Edit
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

// -----------------------------------------------------------------------------
// CENTRAL SETTINGS & CONFIGURATION MODULE (Sections 1-24)
// Authoritative, DB-driven, light-theme, 10 subpages, validation & diagnostics
// -----------------------------------------------------------------------------
let allSettingsSections = [];
let allSettingsCategories = [];
let allSettingsTargets = [];
let allSettingsUsers = [];
let pendingImpactAction = null;

function initSettingsModule() {
    // 1. Settings Subpage Tabs Navigation
    const tabBtns = document.querySelectorAll('.settings-tab-btn');
    const panes = document.querySelectorAll('.settings-pane');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            panes.forEach(p => p.classList.remove('active'));

            btn.classList.add('active');
            const targetPaneId = btn.getAttribute('data-tab');
            const targetPane = document.getElementById(targetPaneId);
            if (targetPane) {
                targetPane.classList.add('active');
            }

            // Route to appropriate subpage loader
            if (targetPaneId === 'tab-cfg-sections') loadSettingsSections();
            if (targetPaneId === 'tab-cfg-targets') loadSettingsTargets();
            if (targetPaneId === 'tab-cfg-calendar') loadSettingsCalendar();
            if (targetPaneId === 'tab-cfg-wip') loadSettingsWip();
            if (targetPaneId === 'tab-cfg-entry') loadSettingsEntry();
            if (targetPaneId === 'tab-cfg-general') loadSettingsGeneral();
            if (targetPaneId === 'tab-cfg-permissions') loadSettingsPermissions();
            if (targetPaneId === 'tab-cfg-reports') loadSettingsReports();
            if (targetPaneId === 'tab-cfg-audit') loadSettingsAudit();
            if (targetPaneId === 'tab-cfg-diagnostics') loadSettingsDiagnostics();
        });
    });

    // 2. Top Header Action Buttons
    const btnRefreshSettings = document.getElementById('btn-refresh-settings');
    if (btnRefreshSettings) {
        btnRefreshSettings.addEventListener('click', () => {
            loadSettingsModule();
            showToast('Settings reloaded from database.');
        });
    }

    const btnRecalcAll = document.getElementById('btn-recalculate-all-plans');
    if (btnRecalcAll) {
        btnRecalcAll.addEventListener('click', async () => {
            showToast('Triggering plan recalculation across all active orders...');
            const res = await apiFetch('/settings/recalculate', {
                method: 'POST',
                body: JSON.stringify({
                    setting_type: 'all',
                    reason: 'Manual administrative trigger to refresh all active planning sheets'
                })
            });
            if (res.ok) {
                showToast(res.data.message || 'All active order schedules recalculated successfully.');
            } else {
                showToast('Error: ' + res.error, false);
            }
        });
    }

    // 3. Subpage 1: Section & Category Listeners
    const secSearch = document.getElementById('settings-section-search');
    if (secSearch) {
        secSearch.addEventListener('input', () => renderSettingsSectionsTable());
    }
    const secStatusFilter = document.getElementById('settings-section-status-filter');
    if (secStatusFilter) {
        secStatusFilter.addEventListener('change', () => renderSettingsSectionsTable());
    }
    const btnOpenAddCat = document.getElementById('btn-open-add-category');
    if (btnOpenAddCat) {
        btnOpenAddCat.addEventListener('click', () => openAddCategoryModal());
    }
    const btnBarAddCat = document.getElementById('btn-manage-add-cat-bar');
    if (btnBarAddCat) {
        btnBarAddCat.addEventListener('click', () => openAddCategoryModal());
    }
    const btnOpenAddSec = document.getElementById('btn-open-add-section');
    if (btnOpenAddSec) {
        btnOpenAddSec.addEventListener('click', () => openAddSectionModal());
    }

    // Category Edit Form Submit
    const formCatEdit = document.getElementById('form-category-edit');
    if (formCatEdit) {
        formCatEdit.addEventListener('submit', async (e) => {
            e.preventDefault();
            const catId = document.getElementById('cat-modal-id').value;
            const name = document.getElementById('cat-modal-name').value.trim();
            const order = parseInt(document.getElementById('cat-modal-order').value, 10) || 0;
            const active = document.getElementById('cat-modal-active').checked;
            const desc = document.getElementById('cat-modal-desc').value.trim();

            const payload = {
                name,
                display_order: order,
                is_active: active,
                description: desc,
                reason: desc || `Saved category ${name}`
            };

            const endpoint = catId ? `/settings/categories/${catId}` : '/settings/categories';
            const method = catId ? 'PUT' : 'POST';

            const res = await apiFetch(endpoint, { method, body: JSON.stringify(payload) });
            if (res.ok) {
                closeModal('category-modal');
                showToast(`Category "${name}" saved successfully.`);
                loadSettingsSections();
            } else {
                const err = document.getElementById('cat-modal-error');
                if (err) {
                    err.textContent = res.error || 'Failed to save category.';
                    err.classList.remove('hidden');
                }
            }
        });
    }

    // Section Edit Form Submit
    const formSecEdit = document.getElementById('form-section-edit');
    if (formSecEdit) {
        formSecEdit.addEventListener('submit', async (e) => {
            e.preventDefault();
            const secId = document.getElementById('sec-modal-id').value;
            const catId = parseInt(document.getElementById('sec-modal-category').value, 10);
            const name = document.getElementById('sec-modal-name').value.trim();
            const order = parseInt(document.getElementById('sec-modal-order').value, 10) || 0;
            const unit = document.getElementById('sec-modal-unit').value;
            const minVal = parseInt(document.getElementById('sec-modal-min').value, 10) || 0;
            const maxVal = parseInt(document.getElementById('sec-modal-max').value, 10) || 0;
            const mode = document.getElementById('sec-modal-mode').value;
            const active = document.getElementById('sec-modal-active').checked;
            const reason = document.getElementById('sec-modal-reason').value.trim();

            const err = document.getElementById('sec-modal-error');
            if (order <= 0) {
                if (err) { err.textContent = 'Planning ID must be a valid positive integer.'; err.classList.remove('hidden'); }
                return;
            }
            if (minVal < 0) {
                if (err) { err.textContent = 'Minimum target cannot be negative.'; err.classList.remove('hidden'); }
                return;
            }
            if (maxVal < 0) {
                if (err) { err.textContent = 'Maximum target cannot be negative.'; err.classList.remove('hidden'); }
                return;
            }
            if (maxVal > 0 && minVal > maxVal) {
                if (err) { err.textContent = `Minimum daily target (${minVal}) cannot exceed maximum daily target (${maxVal}).`; err.classList.remove('hidden'); }
                return;
            }

            const payload = {
                name,
                category_id: catId,
                display_order: order,
                planning_id: order,
                is_active: active,
                counting_unit: unit,
                minimum_daily_target: minVal,
                maximum_daily_target: maxVal,
                calculation_mode: mode,
                reason: reason || `Updated section ${name}`
            };

            const endpoint = secId ? `/settings/sections/${secId}` : '/settings/sections';
            const method = secId ? 'PUT' : 'POST';

            const res = await apiFetch(endpoint, { method, body: JSON.stringify(payload) });
            if (res.ok) {
                closeModal('section-edit-modal');
                showToast(`Section "${name}" saved successfully.`);
                loadSettingsSections();
                loadProductionTargetSettings();
                const activeOrder = document.getElementById('matrix-filter-order')?.value;
                if (activeOrder) loadMatrixPlanningSheet(activeOrder);
            } else {
                if (err) {
                    err.textContent = res.error || 'Failed to save section.';
                    err.classList.remove('hidden');
                }
            }
        });
    }

    // Section Deactivation Confirmation Submit
    const btnConfirmDeact = document.getElementById('btn-confirm-deact-sec');
    if (btnConfirmDeact) {
        btnConfirmDeact.addEventListener('click', async () => {
            const secId = document.getElementById('deact-sec-id').value;
            const reason = document.getElementById('deact-sec-reason').value.trim();
            const removeWorkflows = document.getElementById('deact-remove-from-workflows')?.checked !== false;

            const res = await apiFetch(`/settings/sections/${secId}/deactivate`, {
                method: 'POST',
                body: JSON.stringify({
                    reason: reason || 'Administrative section deactivation',
                    force_confirm: true,
                    remove_from_active_workflows: removeWorkflows
                })
            });

            if (res.ok) {
                closeModal('deactivate-section-modal');
                showToast(res.data.message || 'Section deactivated successfully.');
                loadSettingsSections();
                loadSettingsTargets();
                loadProductionTargetSettings();
                loadDepartmentsData();
                loadMatrixPlanningSheet();
                loadWipFlowSheet();
            } else {
                const err = document.getElementById('deact-sec-error');
                if (err) {
                    err.textContent = res.error || 'Failed to deactivate section.';
                    err.classList.remove('hidden');
                }
            }
        });
    }

    // 4. Subpage 2: Automatic Target Settings Listeners
    const btnReloadTargets = document.getElementById('btn-reload-target-settings');
    if (btnReloadTargets) {
        btnReloadTargets.addEventListener('click', () => loadSettingsTargets());
    }

    const btnConfigureTargets = document.getElementById('btn-configure-target-setting');
    if (btnConfigureTargets) {
        btnConfigureTargets.addEventListener('click', () => {
            const firstSecId = (allSettingsTargets && allSettingsTargets[0]?.section_id) ||
                               (allSettingsSections && allSettingsSections[0]?.id) ||
                               (allTargetSettings && allTargetSettings[0]?.section_id);
            openEditTargetSettingModal(firstSecId);
        });
    }

    const btnSaveGlobalMode = document.getElementById('btn-save-global-target-mode');
    if (btnSaveGlobalMode) {
        btnSaveGlobalMode.addEventListener('click', async () => {
            const mode = document.getElementById('cfg-global-target-mode').value;
            const res = await apiFetch('/settings/general', {
                method: 'PUT',
                body: JSON.stringify({ default_target_calculation_mode: mode })
            });
            if (res.ok) {
                showToast(`Default target calculation mode set to ${mode}.`);
            } else {
                showToast('Failed to save default mode: ' + res.error, false);
            }
        });
    }

    // Edit Target Setting Modal Form Submit
    const formEditTarget = document.getElementById('form-edit-target-setting');
    if (formEditTarget) {
        formEditTarget.addEventListener('submit', async (e) => {
            e.preventDefault();
            const secIdVal = document.getElementById('target-setting-section-id').value ||
                             document.getElementById('target-setting-section-select')?.value;
            const secId = parseInt(secIdVal, 10);
            const minVal = parseInt(document.getElementById('target-setting-min').value, 10);
            const maxVal = parseInt(document.getElementById('target-setting-max').value, 10);
            const unitVal = document.getElementById('target-setting-unit').value;
            const modeVal = document.getElementById('target-setting-mode').value;
            const policyVal = document.getElementById('target-setting-override-policy').value;
            const activeVal = document.getElementById('target-setting-active').checked;
            const notesVal = document.getElementById('target-setting-notes').value.trim();

            const err = document.getElementById('target-setting-error');
            if (err) {
                err.classList.add('hidden');
                err.textContent = '';
            }

            if (!secId || isNaN(secId)) {
                if (err) {
                    err.textContent = 'Please select a valid production section.';
                    err.classList.remove('hidden');
                }
                return;
            }

            if (isNaN(minVal) || minVal < 0) {
                if (err) {
                    err.textContent = 'Minimum daily target must be a non-negative integer (>= 0).';
                    err.classList.remove('hidden');
                }
                return;
            }
            if (isNaN(maxVal) || maxVal < 0) {
                if (err) {
                    err.textContent = 'Maximum daily target must be a non-negative integer (>= 0, 0 = unlimited).';
                    err.classList.remove('hidden');
                }
                return;
            }
            if (maxVal > 0 && minVal > maxVal) {
                if (err) {
                    err.textContent = 'Minimum Target cannot be greater than Maximum Target.';
                    err.classList.remove('hidden');
                }
                return;
            }

            const saveBtn = document.getElementById('btn-save-target-setting-submit');
            const originalBtnText = saveBtn ? saveBtn.textContent : 'Save Target Limits';
            if (saveBtn) {
                saveBtn.disabled = true;
                saveBtn.textContent = 'Saving target settings...';
            }

            try {
                const res = await apiFetch(`/settings/target-settings/${secId}`, {
                    method: 'PUT',
                    body: JSON.stringify({
                        section_id: secId,
                        minimum_daily_target: minVal,
                        maximum_daily_target: maxVal,
                        unit: unitVal,
                        calculation_mode: modeVal,
                        override_policy: policyVal,
                        is_active: activeVal,
                        notes: notesVal
                    })
                });

                if (res.ok && res.data) {
                    const savedData = res.data;
                    // Update in-memory collections with authoritative data
                    const idxSettings = allSettingsTargets.findIndex(t => t.section_id === secId);
                    if (idxSettings !== -1) {
                        allSettingsTargets[idxSettings] = { ...allSettingsTargets[idxSettings], ...savedData };
                    } else {
                        allSettingsTargets.push(savedData);
                    }

                    const idxDept = allTargetSettings.findIndex(t => t.section_id === secId);
                    if (idxDept !== -1) {
                        allTargetSettings[idxDept] = { ...allTargetSettings[idxDept], ...savedData };
                    } else {
                        allTargetSettings.push(savedData);
                    }

                    closeModal('edit-target-setting-modal');
                    closeModal('impact-confirmation-modal');
                    showToast('Target settings saved successfully.');

                    renderSettingsTargetsTable();
                    renderTargetSettingsTable();

                    const activeOrder = document.getElementById('matrix-filter-order')?.value;
                    if (activeOrder) loadMatrixPlanningSheet(activeOrder);
                } else {
                    const failMsg = (res && res.error) || 'Unable to save target settings. Please check the values and try again.';
                    if (err) {
                        err.textContent = failMsg;
                        err.classList.remove('hidden');
                    }
                    showToast(failMsg, false);
                }
            } catch (ex) {
                const failMsg = 'Unable to save target settings. Please check the values and try again.';
                if (err) {
                    err.textContent = failMsg;
                    err.classList.remove('hidden');
                }
                showToast(failMsg, false);
            } finally {
                if (saveBtn) {
                    saveBtn.disabled = false;
                    saveBtn.textContent = originalBtnText;
                }
            }
        });
    }

    // 5. Subpage 3: Calendar Listeners
    const formCalWeekly = document.getElementById('cfg-weekly-calendar-form');
    if (formCalWeekly) {
        formCalWeekly.addEventListener('submit', async (e) => {
            e.preventDefault();
            const payload = {
                work_friday: document.getElementById('cfg-cal-friday').checked,
                work_saturday: document.getElementById('cfg-cal-saturday').checked,
                work_sunday: document.getElementById('cfg-cal-sunday').checked,
                work_monday: document.getElementById('cfg-cal-monday').checked,
                work_tuesday: document.getElementById('cfg-cal-tuesday').checked,
                work_wednesday: document.getElementById('cfg-cal-wednesday').checked,
                work_thursday: document.getElementById('cfg-cal-thursday').checked,
                cutoff_hour: parseInt(document.getElementById('cfg-cal-cutoff-hour').value, 10) || 18,
                cutoff_minute: parseInt(document.getElementById('cfg-cal-cutoff-minute').value, 10) || 0
            };

            const res = await apiFetch('/settings/calendar', {
                method: 'PUT',
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                showToast('Factory working schedule updated successfully.');
                loadSettingsCalendar();
            } else {
                showToast('Failed to update calendar: ' + res.error, false);
            }
        });
    }

    const btnSettingsAddHoliday = document.getElementById('btn-settings-add-holiday');
    if (btnSettingsAddHoliday) {
        btnSettingsAddHoliday.addEventListener('click', () => {
            openModal('add-holiday-modal');
        });
    }

    const btnSettingsAddWorkday = document.getElementById('btn-settings-add-workday');
    if (btnSettingsAddWorkday) {
        btnSettingsAddWorkday.addEventListener('click', () => {
            openModal('add-workday-modal');
        });
    }

    const btnRecalcCal = document.getElementById('btn-recalculate-calendar-plans');
    if (btnRecalcCal) {
        btnRecalcCal.addEventListener('click', async () => {
            showToast('Recalculating production plans after calendar change...');
            const res = await apiFetch('/settings/recalculate', {
                method: 'POST',
                body: JSON.stringify({
                    setting_type: 'calendar',
                    reason: 'Recalculation triggered after calendar update'
                })
            });
            if (res.ok) {
                showToast(res.data.message || 'Plans recalculated successfully.');
            } else {
                showToast('Error: ' + res.error, false);
            }
        });
    }

    // 6. Subpage 4: WIP Rules Form Save
    const btnSaveWip = document.getElementById('btn-save-wip-settings');
    if (btnSaveWip) {
        btnSaveWip.addEventListener('click', async () => {
            const payload = {
                transfer_timing: document.getElementById('wip-cfg-timing').value,
                enforce_wip_limit: document.getElementById('wip-cfg-qty-control').checked,
                require_override_reason: document.getElementById('wip-cfg-override-reason').checked,
                auto_recalculate_plans: document.getElementById('wip-cfg-auto-recalc').checked,
                reason: 'Updated WIP & workflow behavior rules'
            };

            const res = await apiFetch('/settings/wip', {
                method: 'PUT',
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                showToast('WIP & workflow behavior settings saved successfully.');
            } else {
                showToast('Failed to save WIP settings: ' + res.error, false);
            }
        });
    }

    // 7. Subpage 5: Production Entry Rules Form Save
    const btnSaveEntry = document.getElementById('btn-save-entry-settings');
    if (btnSaveEntry) {
        btnSaveEntry.addEventListener('click', async () => {
            const payload = {
                default_production_unit: document.getElementById('entry-cfg-unit').value,
                roles_can_edit_history: document.getElementById('entry-cfg-edit-roles').value,
                track_rejected_quantity: document.getElementById('entry-cfg-rejected').checked,
                supervisor_approval_required: document.getElementById('entry-cfg-supervisor').checked,
                overproduction_warnings: document.getElementById('entry-cfg-overprod').checked,
                reversal_reason_mandatory: document.getElementById('entry-cfg-reversal-reason').checked,
                reason: 'Updated production entry validation rules'
            };

            const res = await apiFetch('/settings/production-entry', {
                method: 'PUT',
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                showToast('Production entry validation rules saved successfully.');
            } else {
                showToast('Failed to save entry rules: ' + res.error, false);
            }
        });
    }

    // 8. Subpage 6: General ERP Settings Form Save
    const btnSaveGeneral = document.getElementById('btn-save-general-settings');
    if (btnSaveGeneral) {
        btnSaveGeneral.addEventListener('click', async () => {
            const cutoffVal = document.getElementById('gen-cutoff').value || '18:00';
            const parts = cutoffVal.split(':');
            const cutoffHour = parseInt(parts[0], 10) || 18;
            const cutoffMin = parseInt(parts[1], 10) || 0;

            const payload = {
                company_name: document.getElementById('gen-company-name').value.trim(),
                company_address: document.getElementById('gen-factory-location').value.trim(),
                reporting_title: document.getElementById('gen-report-title').value.trim(),
                timezone: document.getElementById('gen-timezone').value,
                date_format: document.getElementById('gen-date-format').value,
                planning_cutoff_hour: cutoffHour,
                planning_cutoff_minute: cutoffMin,
                default_unit: document.getElementById('gen-default-unit').value,
                theme_default: document.getElementById('gen-default-theme').value,
                thousand_separator: document.getElementById('gen-thousand-separator').value !== 'none',
                default_order_priority: document.getElementById('gen-default-priority').value,
                reason: 'Updated company & general ERP preferences'
            };

            const res = await apiFetch('/settings/general', {
                method: 'PUT',
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                showToast('General ERP preferences saved successfully.');
                if (payload.theme_default) setTheme(payload.theme_default, true);
            } else {
                showToast('Failed to save general settings: ' + res.error, false);
            }
        });
    }

    // 9. Subpage 7: Permissions Listeners
    const btnReloadUsers = document.getElementById('btn-reload-users-permissions');
    if (btnReloadUsers) {
        btnReloadUsers.addEventListener('click', () => loadSettingsPermissions());
    }

    // 10. Subpage 8: Reports Settings Form Save
    const btnSaveReport = document.getElementById('btn-save-report-settings');
    if (btnSaveReport) {
        btnSaveReport.addEventListener('click', async () => {
            const payload = {
                default_xlsx_filename_format: document.getElementById('rpt-cfg-filename').value.trim(),
                date_display_format: document.getElementById('rpt-cfg-dateformat').value,
                include_summary_rows: document.getElementById('rpt-cfg-summary').checked,
                include_inactive_sections: document.getElementById('rpt-cfg-inactive').checked,
                reason: 'Updated reports and export configuration'
            };

            const res = await apiFetch('/settings/reports', {
                method: 'PUT',
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                showToast('Reports & export configuration saved successfully.');
            } else {
                showToast('Failed to save export settings: ' + res.error, false);
            }
        });
    }

    // 11. Subpage 9: Audit History Listeners
    const btnRefreshAudit = document.getElementById('btn-refresh-audit-log');
    if (btnRefreshAudit) {
        btnRefreshAudit.addEventListener('click', () => loadSettingsAudit());
    }
    const btnFilterAudit = document.getElementById('btn-apply-audit-filter');
    if (btnFilterAudit) {
        btnFilterAudit.addEventListener('click', () => loadSettingsAudit());
    }

    // 12. Subpage 10: Diagnostics Listeners
    const btnLiveDiag = document.getElementById('btn-run-live-diagnostics');
    if (btnLiveDiag) {
        btnLiveDiag.addEventListener('click', () => runLiveDiagnosticsProbe());
    }
}

// Global entrypoint when navigating to #settings-section
function loadSettingsModule() {
    const activeBtn = document.querySelector('.settings-tab-btn.active');
    const tabId = activeBtn ? activeBtn.getAttribute('data-tab') : 'tab-cfg-sections';

    if (tabId === 'tab-cfg-sections') loadSettingsSections();
    else if (tabId === 'tab-cfg-targets') loadSettingsTargets();
    else if (tabId === 'tab-cfg-calendar') loadSettingsCalendar();
    else if (tabId === 'tab-cfg-wip') loadSettingsWip();
    else if (tabId === 'tab-cfg-entry') loadSettingsEntry();
    else if (tabId === 'tab-cfg-general') loadSettingsGeneral();
    else if (tabId === 'tab-cfg-permissions') loadSettingsPermissions();
    else if (tabId === 'tab-cfg-reports') loadSettingsReports();
    else if (tabId === 'tab-cfg-audit') loadSettingsAudit();
    else if (tabId === 'tab-cfg-diagnostics') loadSettingsDiagnostics();
}

// -----------------------------------------------------------------------------
// SUBPAGE 1: SECTION & CATEGORY SETTINGS
// -----------------------------------------------------------------------------
async function loadSettingsSections() {
    const tbody = document.getElementById('settings-sections-tbody');
    if (tbody) {
        tbody.innerHTML = '<tr><td colspan="10" class="text-center" style="padding:20px;">Loading production sections...</td></tr>';
    }

    const [resSec, resCat] = await Promise.all([
        apiFetch('/settings/sections'),
        apiFetch('/settings/categories')
    ]);

    if (!resSec.ok) {
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="10" class="text-center text-danger" style="padding:20px;">Failed to load sections: ${escapeHtml(resSec.error)}</td></tr>`;
        }
        return;
    }

    allSettingsSections = resSec.data || [];
    allSettingsCategories = resCat.ok ? (resCat.data || []) : [];

    renderSettingsCategoriesBar();
    renderSettingsSectionsTable();
}

function renderSettingsCategoriesBar() {
    const bar = document.getElementById('settings-categories-list');
    if (!bar) return;

    if (!allSettingsCategories.length) {
        bar.innerHTML = '<span class="text-muted" style="font-size:12px;">No categories configured.</span>';
        return;
    }

    bar.innerHTML = allSettingsCategories.map(c => `
        <span style="display:inline-flex; align-items:center; gap:6px; padding:4px 10px; background:#ffffff; border:1px solid #cbd5e1; border-radius:16px; font-size:12px;">
            <strong style="color:#0f172a;">${escapeHtml(c.name)}</strong>
            <span style="color:#64748b; font-size:11px;">(${c.section_count || 0})</span>
            <button type="button" class="btn-link" style="border:none; background:none; cursor:pointer; padding:0; font-size:12px; color:#2563eb;" title="Edit / Rename Category" onclick="openEditCategoryModal(${c.id})">✏️</button>
        </span>
    `).join('');
}

function renderSettingsSectionsTable() {
    const tbody = document.getElementById('settings-sections-tbody');
    if (!tbody) return;

    const query = (document.getElementById('settings-section-search')?.value || '').toLowerCase().trim();
    const statusFilter = document.getElementById('settings-section-status-filter')?.value || 'ALL';

    const filtered = allSettingsSections.filter(s => {
        if (statusFilter === 'ACTIVE' && !s.is_active) return false;
        if (statusFilter === 'INACTIVE' && s.is_active) return false;
        if (!query) return true;
        const pid = String(s.planning_id || s.display_order || s.id);
        return (s.name || '').toLowerCase().includes(query) ||
               (s.category_name || '').toLowerCase().includes(query) ||
               String(s.id).includes(query) ||
               pid.includes(query);
    });

    // Authoritative sorting by planning_id ASC
    filtered.sort((a, b) => {
        const pA = a.planning_id != null ? a.planning_id : (a.display_order || a.id);
        const pB = b.planning_id != null ? b.planning_id : (b.display_order || b.id);
        return pA - pB;
    });

    if (!filtered.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted" style="padding:20px;">No sections found matching your filter.</td></tr>';
        return;
    }

    tbody.innerHTML = filtered.map(s => {
        const planningId = s.planning_id != null ? s.planning_id : (s.display_order || s.id);
        const minTargetStr = (s.minimum_daily_target != null && s.minimum_daily_target > 0)
            ? Number(s.minimum_daily_target).toLocaleString()
            : '<span class="text-muted" style="font-weight:normal;">Not Set</span>';
        const maxTargetStr = (s.maximum_daily_target != null && s.maximum_daily_target > 0)
            ? Number(s.maximum_daily_target).toLocaleString()
            : '<span class="text-muted" style="font-weight:normal;">Not Set</span>';
        const statusBadge = s.is_active
            ? '<span class="status-badge status-IN_PRODUCTION">Active</span>'
            : '<span class="status-badge status-DRAFT" style="background:#f1f5f9; color:#64748b;">Inactive</span>';

        return `
            <tr>
                <td style="text-align:center;">
                    <span style="font-family:var(--font-mono); font-weight:700; color:#1e40af; background:#eff6ff; padding:3px 8px; border-radius:4px; font-size:12px;">${planningId}</span>
                </td>
                <td>
                    <strong>${escapeHtml(s.name)}</strong>
                    <span style="font-size:10px; color:#94a3b8; margin-left:4px;" title="Internal DB ID">#${s.id}</span>
                </td>
                <td><span style="padding:2px 8px; background:#f1f5f9; border-radius:4px; font-size:12px; font-weight:600;">${escapeHtml(s.category_name || 'General')}</span></td>
                <td style="text-align:center;">${statusBadge}</td>
                <td style="text-align:right; font-weight:600; color:#16a34a;">${minTargetStr}</td>
                <td style="text-align:right; font-weight:600; color:#2563eb;">${maxTargetStr}</td>
                <td style="text-align:center;">
                    <div style="display:inline-flex; gap:4px;">
                        <button type="button" class="btn btn-outline btn-sm" style="font-size:11px; padding:3px 8px;" onclick="openEditSectionModal(${s.id})">Edit</button>
                        ${s.is_active ? `
                            <button type="button" class="btn btn-outline btn-sm text-danger" style="font-size:11px; padding:3px 8px;" onclick="openDeactivateSectionModal(${s.id})">Deactivate</button>
                        ` : `
                            <button type="button" class="btn btn-outline btn-sm text-success" style="font-size:11px; padding:3px 8px;" onclick="toggleActivateSection(${s.id}, true)">Activate</button>
                        `}
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

window.openAddCategoryModal = function() {
    document.getElementById('category-modal-title').textContent = '+ Add Production Category';
    document.getElementById('cat-modal-id').value = '';
    document.getElementById('cat-modal-name').value = '';
    document.getElementById('cat-modal-order').value = allSettingsCategories.length + 1;
    document.getElementById('cat-modal-active').checked = true;
    document.getElementById('cat-modal-desc').value = '';
    document.getElementById('cat-modal-error')?.classList.add('hidden');
    openModal('category-modal');
};

window.openEditCategoryModal = function(catId) {
    const cat = allSettingsCategories.find(c => c.id === catId);
    if (!cat) return;
    document.getElementById('category-modal-title').textContent = `✏️ Edit Category: ${cat.name}`;
    document.getElementById('cat-modal-id').value = cat.id;
    document.getElementById('cat-modal-name').value = cat.name;
    document.getElementById('cat-modal-order').value = cat.display_order;
    document.getElementById('cat-modal-active').checked = !!cat.is_active;
    document.getElementById('cat-modal-desc').value = cat.description || '';
    document.getElementById('cat-modal-error')?.classList.add('hidden');
    openModal('category-modal');
};

window.openAddSectionModal = function() {
    populateCategoryDropdownForSectionModal();
    const maxPid = allSettingsSections.reduce((max, s) => Math.max(max, s.planning_id || s.display_order || 0), 0);
    document.getElementById('section-modal-title').textContent = '+ Add Production Section';
    document.getElementById('sec-modal-id').value = '';
    document.getElementById('sec-modal-stable-id-display').style.display = 'none';
    document.getElementById('sec-modal-name').value = '';
    document.getElementById('sec-modal-order').value = maxPid + 1;
    document.getElementById('sec-modal-unit').value = 'Pairs';
    document.getElementById('sec-modal-min').value = '0';
    document.getElementById('sec-modal-max').value = '0';
    document.getElementById('sec-modal-mode').value = 'BALANCED';
    document.getElementById('sec-modal-active').checked = true;
    document.getElementById('sec-modal-reason').value = '';
    document.getElementById('sec-modal-error')?.classList.add('hidden');
    openModal('section-edit-modal');
};

window.openEditSectionModal = function(secId) {
    const sec = allSettingsSections.find(s => s.id === secId);
    if (!sec) return;
    populateCategoryDropdownForSectionModal();

    document.getElementById('section-modal-title').textContent = `✏️ Edit Section: ${sec.name}`;
    document.getElementById('sec-modal-id').value = sec.id;
    document.getElementById('sec-modal-stable-id-display').style.display = 'block';
    document.getElementById('sec-modal-stable-id-val').textContent = `#${sec.id}`;
    document.getElementById('sec-modal-category').value = sec.category_id;
    document.getElementById('sec-modal-name').value = sec.name;
    document.getElementById('sec-modal-order').value = sec.planning_id != null ? sec.planning_id : (sec.display_order || sec.id);
    document.getElementById('sec-modal-unit').value = sec.counting_unit || 'Pairs';
    document.getElementById('sec-modal-min').value = sec.minimum_daily_target != null ? sec.minimum_daily_target : 0;
    document.getElementById('sec-modal-max').value = sec.maximum_daily_target != null ? sec.maximum_daily_target : 0;
    document.getElementById('sec-modal-mode').value = sec.calculation_mode || 'BALANCED';
    document.getElementById('sec-modal-active').checked = !!sec.is_active;
    document.getElementById('sec-modal-reason').value = '';
    document.getElementById('sec-modal-error')?.classList.add('hidden');
    openModal('section-edit-modal');
};

function populateCategoryDropdownForSectionModal() {
    const select = document.getElementById('sec-modal-category');
    if (!select) return;
    select.innerHTML = allSettingsCategories.map(c => `
        <option value="${c.id}">${escapeHtml(c.name)}</option>
    `).join('');
}

window.openDeactivateSectionModal = async function(secId) {
    const sec = allSettingsSections.find(s => s.id === secId);
    if (!sec) return;

    document.getElementById('deact-sec-id').value = sec.id;
    document.getElementById('deact-sec-reason').value = '';
    const warningEl = document.getElementById('deactivate-warning-text');
    warningEl.innerHTML = `<em>Checking active order workflows and production impact for Section #${sec.id} (${escapeHtml(sec.name)})...</em>`;
    document.getElementById('deact-sec-error')?.classList.add('hidden');
    openModal('deactivate-section-modal');

    try {
        const checkRes = await apiFetch(`/settings/sections/${secId}/deactivate`, {
            method: 'POST',
            body: JSON.stringify({ force_confirm: false })
        });
        if (checkRes.ok && checkRes.data.requires_confirmation) {
            const data = checkRes.data;
            let ordersListHtml = '';
            if (data.affected_orders && data.affected_orders.length > 0) {
                ordersListHtml = `<div style="margin-top:8px; max-height:100px; overflow-y:auto; font-size:11px; background:#fff; border:1px solid #fecaca; border-radius:4px; padding:6px;">
                    <strong>Affected Active Orders (${data.affected_orders.length}):</strong><br>` +
                    data.affected_orders.map(o => `• Order <strong>${escapeHtml(o.order_code)}</strong> (${escapeHtml(o.style_model || '')}) — Status: ${escapeHtml(o.status)}, Recorded: ${o.recorded_quantity} pairs`).join('<br>') +
                `</div>`;
            }
            warningEl.innerHTML = `
                <strong>⚠️ Impact Warning for Section #${sec.id} (${escapeHtml(sec.name)}):</strong><br>
                ${escapeHtml(data.message)}
                ${ordersListHtml}
            `;
        } else {
            warningEl.innerHTML = `
                <strong>Deactivating Section #${sec.id} (${escapeHtml(sec.name)}):</strong><br>
                This section will be deactivated. Future orders will not use it, while all historical production records remain preserved.
            `;
        }
    } catch (e) {
        warningEl.innerHTML = `
            <strong>Deactivating Section #${sec.id} (${escapeHtml(sec.name)}):</strong><br>
            Deactivating will exclude this section from active planning views while preserving historical records.
        `;
    }
};

window.toggleActivateSection = async function(secId, activate) {
    const sec = allSettingsSections.find(s => s.id === secId);
    if (!sec) return;

    const res = await apiFetch(`/settings/sections/${secId}`, {
        method: 'PUT',
        body: JSON.stringify({
            name: sec.name,
            category_id: sec.category_id,
            display_order: sec.display_order,
            is_active: activate,
            counting_unit: sec.counting_unit,
            reason: `Reactivated section ${sec.name}`
        })
    });

    if (res.ok) {
        showToast(`Section "${sec.name}" ${activate ? 'activated' : 'deactivated'}.`);
        loadSettingsSections();
        loadSettingsTargets();
        loadProductionTargetSettings();
        loadDepartmentsData();
        loadMatrixPlanningSheet();
        loadWipFlowSheet();
    } else {
        showToast('Error updating section status: ' + res.error, false);
    }
};

// -----------------------------------------------------------------------------
// SUBPAGE 2: AUTOMATIC TARGET SETTINGS
// -----------------------------------------------------------------------------
async function loadSettingsTargets() {
    const tbody = document.getElementById('settings-targets-tbody');
    if (tbody) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center" style="padding:20px;">Loading target rules...</td></tr>';
    }

    const [resTgt, resGen] = await Promise.all([
        apiFetch('/settings/target-settings'),
        apiFetch('/settings/general')
    ]);

    if (!resTgt.ok) {
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="9" class="text-center text-danger" style="padding:20px;">Failed to load target settings: ${escapeHtml(resTgt.error)}</td></tr>`;
        }
        return;
    }

    allSettingsTargets = resTgt.data || [];

    if (resGen.ok && resGen.data && resGen.data.default_target_calculation_mode) {
        const modeSelect = document.getElementById('cfg-global-target-mode');
        if (modeSelect) modeSelect.value = resGen.data.default_target_calculation_mode;
    }

    renderSettingsTargetsTable();
}

function renderSettingsTargetsTable() {
    const tbody = document.getElementById('settings-targets-tbody');
    if (!tbody) return;

    if (!allSettingsTargets.length) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted" style="padding:20px;">No target settings found.</td></tr>';
        return;
    }

    tbody.innerHTML = allSettingsTargets.map(t => {
        const minStr = t.minimum_daily_target != null ? Number(t.minimum_daily_target).toLocaleString() : '0';
        const maxStr = t.maximum_daily_target ? Number(t.maximum_daily_target).toLocaleString() : '<span class="text-muted">Unlimited</span>';
        const statusBadge = t.is_active
            ? '<span class="status-badge status-IN_PRODUCTION">Active</span>'
            : '<span class="status-badge status-DRAFT">Inactive</span>';
        const updatedStr = t.updated_at ? new Date(t.updated_at).toLocaleDateString() : 'System benchmark';

        let modeLabel = 'Mode A — Balanced';
        if (t.calculation_mode === 'MINIMUM_DRIVEN') modeLabel = 'Mode B — Min-Driven';
        if (t.calculation_mode === 'SHIPMENT_PRIORITY') modeLabel = 'Mode C — Shipment Priority';
        if (t.calculation_mode === 'MANUAL_OVERRIDE') modeLabel = 'Mode D — Manual Override';

        return `
            <tr>
                <td><span style="padding:2px 8px; background:#f1f5f9; border-radius:4px; font-size:12px; font-weight:600;">${escapeHtml(t.category_name || 'General')}</span></td>
                <td><strong>${escapeHtml(t.section_name)}</strong></td>
                <td style="text-align:right; font-weight:700; color:#16a34a;">${minStr}</td>
                <td style="text-align:right; font-weight:700; color:#2563eb;">${maxStr}</td>
                <td><span class="text-muted">${escapeHtml(t.unit || 'Pairs/day')}</span></td>
                <td><span style="font-size:12px; font-weight:500; color:#475569;">${modeLabel}</span></td>
                <td style="text-align:center;">${statusBadge}</td>
                <td style="font-size:11px; color:#64748b;">${updatedStr}</td>
                <td style="text-align:center;">
                    <button type="button" class="btn btn-outline btn-sm" style="font-size:11px; padding:3px 8px;" onclick="openEditTargetSettingModal(${t.section_id})">Edit Limits</button>
                </td>
            </tr>
        `;
    }).join('');
}

window.loadSectionTargetIntoForm = async function(secId) {
    if (!secId) return;
    const secIdInt = parseInt(secId, 10);

    let item = (allSettingsTargets || []).find(s => s.section_id === secIdInt) ||
               (allTargetSettings || []).find(s => s.section_id === secIdInt);

    let secMeta = (allSettingsSections || []).find(s => s.id === secIdInt);

    if (!item) {
        const res = await apiFetch('/settings/target-settings');
        if (res.ok && Array.isArray(res.data)) {
            allSettingsTargets = res.data;
            item = allSettingsTargets.find(s => s.section_id === secIdInt);
        }
    }

    const secName = (item && item.section_name) || (secMeta && secMeta.name) || `Section #${secIdInt}`;
    const catName = (item && item.category_name) || (secMeta && secMeta.category_name) || 'General';
    const minTarget = item && item.minimum_daily_target != null ? item.minimum_daily_target : 0;
    const maxTarget = item && item.maximum_daily_target != null ? item.maximum_daily_target : 0;
    const unitVal = (item && item.unit) || (secMeta && secMeta.counting_unit ? `${secMeta.counting_unit}/day` : 'Pairs/day');
    const modeVal = (item && item.calculation_mode) || 'BALANCED';
    const policyVal = (item && item.override_policy) || 'ALLOWED';
    const isActive = item ? !!item.is_active : true;
    const notesVal = (item && item.notes) || '';

    const secIdInput = document.getElementById('target-setting-section-id');
    if (secIdInput) secIdInput.value = secIdInt;

    const secSelect = document.getElementById('target-setting-section-select');
    if (secSelect) secSelect.value = secIdInt;

    const secInput = document.getElementById('target-setting-section');
    if (secInput) secInput.value = secName;

    const catInput = document.getElementById('target-setting-category');
    if (catInput) catInput.value = catName;

    const minInput = document.getElementById('target-setting-min');
    if (minInput) minInput.value = minTarget;

    const maxInput = document.getElementById('target-setting-max');
    if (maxInput) maxInput.value = maxTarget;

    const unitInput = document.getElementById('target-setting-unit');
    if (unitInput) unitInput.value = unitVal;

    const modeInput = document.getElementById('target-setting-mode');
    if (modeInput) modeInput.value = modeVal;

    const policyInput = document.getElementById('target-setting-override-policy');
    if (policyInput) policyInput.value = policyVal;

    const activeInput = document.getElementById('target-setting-active');
    if (activeInput) activeInput.checked = isActive;

    const notesInput = document.getElementById('target-setting-notes');
    if (notesInput) notesInput.value = notesVal;

    document.getElementById('target-setting-error')?.classList.add('hidden');

    const impactBanner = document.getElementById('target-setting-impact-banner');
    if (impactBanner) {
        impactBanner.style.display = 'block';
        impactBanner.innerHTML = '⚡ Checking potential schedule impact across active orders...';
        const impact = await apiFetch('/settings/impact-check', {
            method: 'POST',
            body: JSON.stringify({
                setting_type: 'target',
                entity_id: secIdInt
            })
        });
        if (impact.ok && impact.data) {
            impactBanner.innerHTML = `ℹ️ <strong>Impact Assessment:</strong> ${escapeHtml(impact.data.message)}`;
        } else {
            impactBanner.style.display = 'none';
        }
    }
};

window.openEditTargetSettingModal = async function(sectionId) {
    if (!allSettingsSections || allSettingsSections.length === 0) {
        const secRes = await apiFetch('/departments/sections');
        if (secRes.ok && Array.isArray(secRes.data)) {
            allSettingsSections = secRes.data;
        }
    }
    if (!allSettingsTargets || allSettingsTargets.length === 0) {
        const tgtRes = await apiFetch('/settings/target-settings');
        if (tgtRes.ok && Array.isArray(tgtRes.data)) {
            allSettingsTargets = tgtRes.data;
        }
    }

    const secSelect = document.getElementById('target-setting-section-select');
    if (secSelect) {
        let sectionsList = [];
        if (allSettingsSections && allSettingsSections.length > 0) {
            sectionsList = allSettingsSections;
        } else if (allSettingsTargets && allSettingsTargets.length > 0) {
            sectionsList = allSettingsTargets.map(t => ({ id: t.section_id, name: t.section_name, category_name: t.category_name }));
        }

        secSelect.innerHTML = '<option value="">-- Select Production Section --</option>' +
            sectionsList.map(s => `<option value="${s.id}">${escapeHtml(s.name)}${s.category_name ? ' (' + escapeHtml(s.category_name) + ')' : ''}</option>`).join('');

        if (!secSelect.dataset.hasChangeListener) {
            secSelect.dataset.hasChangeListener = 'true';
            secSelect.addEventListener('change', (e) => {
                const newId = parseInt(e.target.value, 10);
                if (newId) {
                    window.loadSectionTargetIntoForm(newId);
                }
            });
        }
    }

    const chosenId = sectionId || (allSettingsTargets && allSettingsTargets[0]?.section_id) || (allSettingsSections && allSettingsSections[0]?.id) || null;
    if (chosenId) {
        await window.loadSectionTargetIntoForm(chosenId);
    }

    openModal('edit-target-setting-modal');
};

// -----------------------------------------------------------------------------
// SUBPAGE 3: FACTORY CALENDAR
// -----------------------------------------------------------------------------
async function loadSettingsCalendar() {
    const tbody = document.getElementById('cfg-calendar-exceptions-tbody');
    if (tbody) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center">Loading calendar exceptions...</td></tr>';
    }

    const res = await apiFetch('/settings/calendar');
    if (!res.ok) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">${escapeHtml(res.error)}</td></tr>`;
        return;
    }

    const cal = res.data;
    settingsAllCalendar = cal;

    document.getElementById('cfg-cal-friday').checked = !!cal.work_friday;
    document.getElementById('cfg-cal-saturday').checked = !!cal.work_saturday;
    document.getElementById('cfg-cal-sunday').checked = !!cal.work_sunday;
    document.getElementById('cfg-cal-monday').checked = !!cal.work_monday;
    document.getElementById('cfg-cal-tuesday').checked = !!cal.work_tuesday;
    document.getElementById('cfg-cal-wednesday').checked = !!cal.work_wednesday;
    document.getElementById('cfg-cal-thursday').checked = !!cal.work_thursday;

    if (document.getElementById('cfg-cal-cutoff-hour')) {
        document.getElementById('cfg-cal-cutoff-hour').value = cal.cutoff_hour != null ? cal.cutoff_hour : 18;
    }
    if (document.getElementById('cfg-cal-cutoff-minute')) {
        document.getElementById('cfg-cal-cutoff-minute').value = cal.cutoff_minute != null ? cal.cutoff_minute : 0;
    }

    const exceptions = cal.exceptions || [];
    if (!exceptions.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No factory holidays or overrides configured.</td></tr>';
        return;
    }

    tbody.innerHTML = exceptions.map(ex => {
        const isSpecialWork = ex.exception_type === 'special_workday';
        const impactBadge = isSpecialWork
            ? '<span class="status-badge status-IN_PRODUCTION">Working Day Catch-up</span>'
            : '<span class="status-badge status-OVERDUE">Factory Off (Targets Deferred)</span>';
        const typeBadge = `<span style="font-size:11px; font-weight:600; text-transform:uppercase;">${escapeHtml(ex.exception_type)}</span>`;

        return `
            <tr>
                <td><strong>${escapeHtml(ex.exception_date)}</strong></td>
                <td>${typeBadge}</td>
                <td>${escapeHtml(ex.description || 'Calendar Exception')}</td>
                <td>${impactBadge}</td>
                <td style="text-align:center;">
                    <button type="button" class="btn btn-outline btn-sm text-danger" style="font-size:11px; padding:2px 6px;" onclick="deleteCalendarException(${ex.id})">Delete</button>
                </td>
            </tr>
        `;
    }).join('');
}

window.deleteCalendarException = async function(exId) {
    if (!confirm('Are you sure you want to remove this calendar exception? Future planning schedules will adjust accordingly.')) {
        return;
    }
    const res = await apiFetch(`/settings/calendar/exceptions/${exId}`, { method: 'DELETE' });
    if (res.ok) {
        showToast('Calendar exception removed.');
        loadSettingsCalendar();
    } else {
        showToast('Error: ' + res.error, false);
    }
};

// -----------------------------------------------------------------------------
// SUBPAGE 4: WIP & WORKFLOW SETTINGS
// -----------------------------------------------------------------------------
async function loadSettingsWip() {
    const res = await apiFetch('/settings/wip');
    if (!res.ok) return;
    const w = res.data;

    const elTiming = document.getElementById('wip-cfg-timing');
    if (elTiming && w.transfer_timing) elTiming.value = w.transfer_timing;

    const elIncomplete = document.getElementById('wip-cfg-incomplete');
    if (elIncomplete && w.incomplete_workflow_handling) elIncomplete.value = w.incomplete_workflow_handling;

    const elQty = document.getElementById('wip-cfg-qty-control');
    if (elQty) elQty.checked = w.enforce_wip_limit !== false;

    const elReason = document.getElementById('wip-cfg-override-reason');
    if (elReason) elReason.checked = w.require_override_reason !== false;

    const elRecalc = document.getElementById('wip-cfg-auto-recalc');
    if (elRecalc) elRecalc.checked = w.auto_recalculate_plans !== false;
}

// -----------------------------------------------------------------------------
// SUBPAGE 5: PRODUCTION ENTRY RULES
// -----------------------------------------------------------------------------
async function loadSettingsEntry() {
    const res = await apiFetch('/settings/production-entry');
    if (!res.ok) return;
    const e = res.data;

    const elUnit = document.getElementById('entry-cfg-unit');
    if (elUnit && e.default_production_unit) elUnit.value = e.default_production_unit.toLowerCase();

    const elRoles = document.getElementById('entry-cfg-edit-roles');
    if (elRoles && e.roles_can_edit_history) elRoles.value = e.roles_can_edit_history;

    const elRej = document.getElementById('entry-cfg-rejected');
    if (elRej) elRej.checked = e.track_rejected_quantity !== false;

    const elSup = document.getElementById('entry-cfg-supervisor');
    if (elSup) elSup.checked = e.supervisor_approval_required !== false;

    const elOver = document.getElementById('entry-cfg-overprod');
    if (elOver) elOver.checked = e.overproduction_warnings !== false;

    const elRev = document.getElementById('entry-cfg-reversal-reason');
    if (elRev) elRev.checked = e.reversal_reason_mandatory !== false;
}

// -----------------------------------------------------------------------------
// SUBPAGE 6: GENERAL ERP PREFERENCES
// -----------------------------------------------------------------------------
async function loadSettingsGeneral() {
    const res = await apiFetch('/settings/general');
    if (!res.ok) return;
    const g = res.data;

    if (g.company_name) document.getElementById('gen-company-name').value = g.company_name;
    if (g.company_address) document.getElementById('gen-factory-location').value = g.company_address;
    if (g.reporting_title) document.getElementById('gen-report-title').value = g.reporting_title;
    if (g.timezone) document.getElementById('gen-timezone').value = g.timezone;
    if (g.date_format) document.getElementById('gen-date-format').value = g.date_format;
    if (g.planning_cutoff_hour != null) {
        const hh = String(g.planning_cutoff_hour).padStart(2, '0');
        const mm = String(g.planning_cutoff_minute || 0).padStart(2, '0');
        document.getElementById('gen-cutoff').value = `${hh}:${mm}`;
    }
    if (g.default_unit) document.getElementById('gen-default-unit').value = g.default_unit.toLowerCase();
    if (g.theme_default) document.getElementById('gen-default-theme').value = g.theme_default;
    if (g.default_order_priority) document.getElementById('gen-default-priority').value = g.default_order_priority;
}

// -----------------------------------------------------------------------------
// SUBPAGE 7: USER & PERMISSION SETTINGS
// -----------------------------------------------------------------------------
async function loadSettingsPermissions() {
    if (currentUser) {
        const userEl = document.getElementById('settings-signed-in-user');
        const roleEl = document.getElementById('settings-signed-in-role');
        if (userEl) userEl.textContent = currentUser.full_name;
        if (roleEl) roleEl.textContent = (currentUser.role || 'ADMIN').toUpperCase();
    }

    const tbody = document.getElementById('settings-users-tbody');
    if (!tbody) return;

    const res = await apiFetch('/settings/permissions/users');
    if (!res.ok) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted" style="padding:16px;">Only Administrators have permission to view registered users accounts (${escapeHtml(res.error)}).</td></tr>`;
        return;
    }

    allSettingsUsers = res.data || [];
    if (!allSettingsUsers.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted" style="padding:16px;">No user accounts found.</td></tr>';
        return;
    }

    tbody.innerHTML = allSettingsUsers.map(u => {
        const roleVal = (u.role || '').toUpperCase();
        return `
            <tr>
                <td style="text-align:center;">#${u.id}</td>
                <td><strong>${escapeHtml(u.full_name)}</strong></td>
                <td><span style="font-family:var(--font-mono); color:#475569;">${escapeHtml(u.username)}</span></td>
                <td>
                    <select id="user-role-select-${u.id}" class="select-filter" style="padding:4px 8px; font-size:12px; width:180px;">
                        <option value="admin" ${roleVal === 'ADMIN' ? 'selected' : ''}>ADMINISTRATOR</option>
                        <option value="planning_manager" ${roleVal === 'PLANNING_MANAGER' ? 'selected' : ''}>PLANNING MANAGER</option>
                        <option value="supervisor" ${roleVal === 'SUPERVISOR' ? 'selected' : ''}>SECTION SUPERVISOR</option>
                        <option value="viewer" ${roleVal === 'VIEWER' ? 'selected' : ''}>VIEWER</option>
                    </select>
                </td>
                <td style="text-align:center;">
                    <label class="switch" style="transform:scale(0.85);">
                        <input type="checkbox" id="user-active-toggle-${u.id}" ${u.is_active ? 'checked' : ''}>
                        <span class="switch-slider"></span>
                    </label>
                </td>
                <td style="text-align:center;">
                    <button type="button" class="btn btn-primary btn-sm" style="font-size:11px; padding:3px 8px;" onclick="saveUserPermission(${u.id})">Save Role</button>
                </td>
            </tr>
        `;
    }).join('');
}

window.saveUserPermission = async function(userId) {
    const roleSelect = document.getElementById(`user-role-select-${userId}`);
    const activeToggle = document.getElementById(`user-active-toggle-${userId}`);
    if (!roleSelect) return;

    const newRole = roleSelect.value;
    const isActive = activeToggle ? activeToggle.checked : true;

    const res = await apiFetch(`/settings/permissions/users/${userId}`, {
        method: 'PUT',
        body: JSON.stringify({
            role: newRole,
            is_active: isActive,
            reason: `Administrative role change to ${newRole}`
        })
    });

    if (res.ok) {
        showToast(`User permissions updated successfully.`);
        loadSettingsPermissions();
    } else {
        showToast('Error updating role: ' + res.error, false);
    }
};

// -----------------------------------------------------------------------------
// SUBPAGE 8: REPORTS & EXPORT PREFERENCES
// -----------------------------------------------------------------------------
async function loadSettingsReports() {
    const res = await apiFetch('/settings/reports');
    if (!res.ok) return;
    const r = res.data;

    if (r.default_xlsx_filename_format) document.getElementById('rpt-cfg-filename').value = r.default_xlsx_filename_format;
    if (r.date_display_format) document.getElementById('rpt-cfg-dateformat').value = r.date_display_format;
    if (r.include_summary_rows != null) document.getElementById('rpt-cfg-summary').checked = r.include_summary_rows !== false;
    if (r.include_inactive_sections != null) document.getElementById('rpt-cfg-inactive').checked = !!r.include_inactive_sections;
}

// -----------------------------------------------------------------------------
// SUBPAGE 9: AUDIT HISTORY
// -----------------------------------------------------------------------------
async function loadSettingsAudit() {
    const tbody = document.getElementById('settings-audit-tbody');
    if (tbody) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center" style="padding:20px;">Loading settings audit logs...</td></tr>';
    }

    const typeFilter = document.getElementById('audit-filter-type')?.value || '';
    const searchFilter = (document.getElementById('audit-filter-search')?.value || '').toLowerCase().trim();

    let query = '?limit=100';
    if (typeFilter) query += `&setting_type=${encodeURIComponent(typeFilter.toLowerCase())}`;

    const res = await apiFetch(`/settings/audit${query}`);
    if (!res.ok) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="8" class="text-center text-danger" style="padding:20px;">${escapeHtml(res.error)}</td></tr>`;
        return;
    }

    const logs = res.data || [];
    const filtered = logs.filter(l => {
        if (!searchFilter) return true;
        return (l.reason || '').toLowerCase().includes(searchFilter) ||
               (l.details || '').toLowerCase().includes(searchFilter) ||
               (l.user_name || '').toLowerCase().includes(searchFilter);
    });

    if (!filtered.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted" style="padding:20px;">No audit entries found matching your criteria.</td></tr>';
        return;
    }

    tbody.innerHTML = filtered.map(l => {
        const timeStr = l.timestamp ? new Date(l.timestamp).toLocaleString() : '-';
        let detailSnippet = l.details || '';
        try {
            const parsed = JSON.parse(detailSnippet);
            detailSnippet = JSON.stringify(parsed, null, 1).replace(/[{}\[\]"]/g, '');
        } catch (e) {}

        return `
            <tr>
                <td style="font-size:11px; color:#64748b; white-space:nowrap;">${timeStr}</td>
                <td><span style="font-size:11px; font-weight:700; text-transform:uppercase; padding:2px 6px; background:#eff6ff; color:#1e40af; border-radius:4px;">${escapeHtml(l.setting_type)}</span></td>
                <td><strong>${escapeHtml(l.entity_name || 'System')} #${l.entity_id || '-'}</strong></td>
                <td colspan="2" style="font-size:11px; font-family:var(--font-mono); color:#334155; max-width:260px; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(detailSnippet.substring(0, 120))}</td>
                <td><span style="font-size:12px; font-weight:600;">${escapeHtml(l.user_name)}</span></td>
                <td style="font-size:12px; color:#475569;">${escapeHtml(l.reason || 'Setting updated')}</td>
                <td style="text-align:center; font-weight:700; color:#2563eb;">${l.affected_order_count || 0}</td>
            </tr>
        `;
    }).join('');
}

// -----------------------------------------------------------------------------
// SUBPAGE 10: SYSTEM DIAGNOSTICS PROBE (Comprehensive 10-Subsystem Checks)
// -----------------------------------------------------------------------------
async function loadSettingsDiagnostics() {
    await runLiveDiagnosticsProbe(false);
}

async function runLiveDiagnosticsProbe(isExplicitRun = true) {
    const grid = document.getElementById('diagnostics-cards-grid');
    const banner = document.getElementById('diagnostics-summary-banner');
    const lastChecked = document.getElementById('diagnostics-last-checked');

    if (grid) {
        grid.innerHTML = '<div style="grid-column:1/-1; text-align:center; padding:30px; color:#64748b;">⚡ Probing all 10 ERP subsystems in real-time...</div>';
    }

    const endpoint = isExplicitRun ? '/settings/diagnostics/run' : '/settings/diagnostics';
    const method = isExplicitRun ? 'POST' : 'GET';

    const res = await apiFetch(endpoint, { method });
    if (!res.ok) {
        if (banner) {
            banner.style.background = '#fef2f2';
            banner.style.color = '#991b1b';
            banner.style.borderColor = '#fca5a5';
            banner.innerHTML = `<span>⚠️ Diagnostics Endpoint Error: ${escapeHtml(res.error)}</span>`;
        }
        return;
    }

    const diag = res.data;
    if (banner) {
        if (diag.overall_status === 'PASS') {
            banner.style.background = '#dcfce7';
            banner.style.color = '#15803d';
            banner.style.borderColor = '#86efac';
            banner.innerHTML = `<span>✓ All 10 Core ERP Subsystems Operating Normally</span><span style="font-size:11px; font-weight:400; color:#166534;">Timestamp: ${escapeHtml(diag.timestamp)}</span>`;
        } else {
            banner.style.background = '#fef2f2';
            banner.style.color = '#991b1b';
            banner.style.borderColor = '#fca5a5';
            banner.innerHTML = `<span>⚠️ Failure Detected in One or More Subsystems</span><span style="font-size:11px; font-weight:400; color:#991b1b;">Timestamp: ${escapeHtml(diag.timestamp)}</span>`;
        }
    }

    if (grid && diag.subsystems) {
        grid.innerHTML = diag.subsystems.map(s => {
            const isPass = s.status === 'PASS';
            const icon = isPass ? '✓' : '✗';
            const badgeClass = isPass ? 'status-PRODUCTION_COMPLETE' : 'status-OVERDUE';
            const statusText = isPass ? 'HEALTHY' : 'FAILED';
            const borderCol = isPass ? '#bbf7d0' : '#fecaca';
            const bgCol = isPass ? '#f0fdf4' : '#fef2f2';

            return `
                <div style="background:#ffffff; border:1px solid ${borderCol}; border-radius:6px; padding:14px; display:flex; flex-direction:column; justify-content:space-between; box-shadow:0 1px 2px rgba(0,0,0,0.03);">
                    <div>
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                            <strong style="font-size:13px; color:#0f172a;">${escapeHtml(s.subsystem)}</strong>
                            <span class="status-badge ${badgeClass}" style="font-size:10px;">${icon} ${statusText}</span>
                        </div>
                        <div style="font-size:12px; color:${isPass ? '#166534' : '#991b1b'}; margin-bottom:8px; line-height:1.4;">
                            ${escapeHtml(s.details || (isPass ? 'Operational' : 'Error detected'))}
                            ${s.error ? `<br><small style="color:#b91c1c; font-family:var(--font-mono);">${escapeHtml(s.error)}</small>` : ''}
                        </div>
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:center; font-size:11px; color:#94a3b8; border-top:1px solid #f1f5f9; padding-top:6px; margin-top:6px;">
                        <span>Latency: <strong>${s.latency_ms} ms</strong></span>
                        <span>${escapeHtml(s.last_checked || 'Just now')}</span>
                    </div>
                </div>
            `;
        }).join('');
    }

    if (isExplicitRun) {
        showToast('Subsystem diagnostics completed successfully.');
    }
}

// ==========================================================================
// 12. ROLE-BASED ADMIN PANEL MODULE (Sections 8, 10, 16, 17)
// ==========================================================================

function initAdminModule() {
    // 1. Sub-tab Switching in Admin Panel
    const adminTabs = document.querySelectorAll('.admin-tab-btn');
    const adminPanes = document.querySelectorAll('.admin-tab-pane');

    adminTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetPaneId = tab.getAttribute('data-tab');
            adminTabs.forEach(t => t.classList.remove('active'));
            adminPanes.forEach(p => p.classList.remove('active'));

            tab.classList.add('active');
            const targetPane = document.getElementById(targetPaneId);
            if (targetPane) targetPane.classList.add('active');

            if (targetPaneId === 'admin-pane-overview') loadAdminPanel();
            if (targetPaneId === 'admin-pane-users') loadAdminUsers();
            if (targetPaneId === 'admin-pane-audit') loadAdminAuditLogs();
        });
    });

    // 2. Overview Buttons
    const btnAdminRefresh = document.getElementById('btn-admin-refresh-all');
    if (btnAdminRefresh) btnAdminRefresh.addEventListener('click', () => {
        loadAdminPanel();
        showToast('Admin statistics refreshed.');
    });

    const btnQuickAddUser = document.getElementById('btn-admin-quick-add-user');
    if (btnQuickAddUser) btnQuickAddUser.addEventListener('click', () => openModal('admin-create-user-modal'));

    const btnQuickDiag = document.getElementById('btn-admin-quick-run-diag');
    if (btnQuickDiag) btnQuickDiag.addEventListener('click', () => {
        const diagTab = document.querySelector('.admin-tab-btn[data-tab="admin-pane-diagnostics"]');
        if (diagTab) diagTab.click();
        runAdminDiagnostics();
    });

    const btnQuickSettings = document.getElementById('btn-admin-quick-go-settings');
    if (btnQuickSettings) btnQuickSettings.addEventListener('click', () => navigateToSection('settings-section'));

    // 3. User Management Toolbar & Search
    const btnOpenCreateUser = document.getElementById('btn-admin-open-create-user');
    if (btnOpenCreateUser) btnOpenCreateUser.addEventListener('click', () => openModal('admin-create-user-modal'));

    const userSearchInput = document.getElementById('admin-user-search');
    if (userSearchInput) userSearchInput.addEventListener('input', debounce(() => loadAdminUsers(), 300));

    const userRoleFilter = document.getElementById('admin-user-role-filter');
    if (userRoleFilter) userRoleFilter.addEventListener('change', () => loadAdminUsers());

    const userStatusFilter = document.getElementById('admin-user-status-filter');
    if (userStatusFilter) userStatusFilter.addEventListener('change', () => loadAdminUsers());

    // 4. Create User Form Submit
    const createUserForm = document.getElementById('admin-create-user-form');
    if (createUserForm) {
        createUserForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const errBanner = document.getElementById('admin-create-user-error');
            if (errBanner) errBanner.classList.add('hidden');

            const username = document.getElementById('admin-new-username')?.value.trim();
            const full_name = document.getElementById('admin-new-fullname')?.value.trim();
            const email = document.getElementById('admin-new-email')?.value.trim();
            const password = document.getElementById('admin-new-password')?.value;
            const role = document.getElementById('admin-new-role')?.value;
            const is_active = document.getElementById('admin-new-active')?.checked ?? true;

            const res = await apiFetch('/admin/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, full_name, email, password, role, is_active })
            });

            if (!res.ok) {
                if (errBanner) {
                    errBanner.textContent = res.error || 'Failed to create user account';
                    errBanner.classList.remove('hidden');
                }
                return;
            }

            closeModal('admin-create-user-modal');
            createUserForm.reset();
            showToast(`User account '${res.data.username}' created successfully.`);
            loadAdminUsers();
            loadAdminPanel();
        });
    }

    // 5. Edit User Form Submit
    const editUserForm = document.getElementById('admin-edit-user-form');
    if (editUserForm) {
        editUserForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const errBanner = document.getElementById('admin-edit-user-error');
            if (errBanner) errBanner.classList.add('hidden');

            const userId = document.getElementById('admin-edit-user-id')?.value;
            const full_name = document.getElementById('admin-edit-fullname')?.value.trim();
            const email = document.getElementById('admin-edit-email')?.value.trim();
            const role = document.getElementById('admin-edit-role')?.value;
            const is_active = document.getElementById('admin-edit-active')?.checked ?? true;

            const res = await apiFetch(`/admin/users/${userId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ full_name, email, role, is_active })
            });

            if (!res.ok) {
                if (errBanner) {
                    errBanner.textContent = res.error || 'Failed to update user';
                    errBanner.classList.remove('hidden');
                }
                return;
            }

            closeModal('admin-edit-user-modal');
            showToast(`User '${res.data.username}' updated successfully.`);
            loadAdminUsers();
            loadAdminPanel();

            // If admin updated their own name
            if (currentUser && currentUser.id === parseInt(userId, 10)) {
                currentUser.full_name = res.data.full_name;
                currentUser.role = res.data.role;
                localStorage.setItem('erp_user', JSON.stringify(currentUser));
                updateUserUI();
            }
        });
    }

    // 6. Reset Password Form Submit
    const resetPwdForm = document.getElementById('admin-reset-pwd-form');
    if (resetPwdForm) {
        resetPwdForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const errBanner = document.getElementById('admin-reset-pwd-error');
            if (errBanner) errBanner.classList.add('hidden');

            const userId = document.getElementById('admin-reset-user-id')?.value;
            const new_password = document.getElementById('admin-reset-new-password')?.value;

            const res = await apiFetch(`/admin/users/${userId}/reset-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_password })
            });

            if (!res.ok) {
                if (errBanner) {
                    errBanner.textContent = res.error || 'Failed to reset password';
                    errBanner.classList.remove('hidden');
                }
                return;
            }

            closeModal('admin-reset-pwd-modal');
            resetPwdForm.reset();
            showToast('User password reset successfully.');
        });
    }

    // 7. Audit Toolbar
    const auditSearch = document.getElementById('admin-audit-search');
    if (auditSearch) auditSearch.addEventListener('input', debounce(() => loadAdminAuditLogs(), 300));

    const auditActionFilter = document.getElementById('admin-audit-action-filter');
    if (auditActionFilter) auditActionFilter.addEventListener('change', () => loadAdminAuditLogs());

    const btnRefreshAudit = document.getElementById('btn-admin-refresh-audit');
    if (btnRefreshAudit) btnRefreshAudit.addEventListener('click', () => loadAdminAuditLogs());

    // 8. Diagnostics Button
    const btnRunDiag = document.getElementById('btn-admin-run-diagnostics');
    if (btnRunDiag) btnRunDiag.addEventListener('click', () => runAdminDiagnostics());
}

async function loadAdminPanel() {
    const res = await apiFetch('/admin/dashboard');
    if (!res.ok) {
        showToast(res.error || 'Failed to load administrator dashboard data', false);
        return;
    }

    const d = res.data;
    const metrics = d.metrics || {};

    const elTotal = document.getElementById('admin-kpi-total-users');
    const elActive = document.getElementById('admin-kpi-active-users');
    const elInactive = document.getElementById('admin-kpi-inactive-users');
    const elOrders = document.getElementById('admin-kpi-active-orders');
    const elHealth = document.getElementById('admin-kpi-health');

    if (elTotal) elTotal.textContent = metrics.total_users || 0;
    if (elActive) elActive.textContent = metrics.active_users || 0;
    if (elInactive) elInactive.textContent = metrics.inactive_users || 0;
    if (elOrders) elOrders.textContent = metrics.active_orders || 0;
    if (elHealth) elHealth.textContent = (d.system_health || 'HEALTHY').toUpperCase();

    // Render Recent Audit
    const auditBody = document.getElementById('admin-recent-audit-body');
    if (auditBody) {
        const list = d.recent_activity || [];
        if (list.length === 0) {
            auditBody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">No recent administrative activity logged.</td></tr>`;
        } else {
            auditBody.innerHTML = list.map(a => {
                const timeStr = a.timestamp ? new Date(a.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—';
                return `
                    <tr>
                        <td style="color:#64748B; font-size:12px;">${timeStr}</td>
                        <td><span class="role-pill" style="background:#EFF6FF; color:#1D4ED8;">${escapeHtml(a.action)}</span></td>
                        <td><strong>${escapeHtml(a.entity_name || 'System')}</strong></td>
                        <td>User #${a.user_id || 'System'}</td>
                        <td style="font-size:12px; color:#475569;">${escapeHtml(a.reason || a.details || '—')}</td>
                    </tr>
                `;
            }).join('');
        }
    }
}

async function loadAdminUsers() {
    const searchVal = document.getElementById('admin-user-search')?.value.trim();
    const roleVal = document.getElementById('admin-user-role-filter')?.value;
    const statusVal = document.getElementById('admin-user-status-filter')?.value;

    const params = new URLSearchParams();
    if (searchVal) params.append('search', searchVal);
    if (roleVal) params.append('role', roleVal);
    if (statusVal !== '' && statusVal !== null && statusVal !== undefined) params.append('is_active', statusVal);

    const res = await apiFetch(`/admin/users?${params.toString()}`);
    const tableBody = document.getElementById('admin-users-table-body');
    if (!tableBody) return;

    if (!res.ok) {
        tableBody.innerHTML = `<tr><td colspan="8" class="text-center text-danger">${escapeHtml(res.error || 'Failed to load user accounts')}</td></tr>`;
        return;
    }

    const users = res.data || [];
    if (users.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">No user accounts found matching current filter.</td></tr>`;
        return;
    }

    tableBody.innerHTML = users.map(u => {
        const roleClean = String(u.role || '').toLowerCase().replace('userrole.', '');
        const roleClass = roleClean;
        const roleLabel = roleClean.replace('_', ' ').toUpperCase();
        const statusClass = u.is_active ? 'active' : 'inactive';
        const statusLabel = u.is_active ? 'Active' : 'Inactive';
        const lastLoginStr = u.last_login_at ? new Date(u.last_login_at).toLocaleString() : 'Never';

        return `
            <tr>
                <td style="font-family:var(--font-mono); color:#64748B;">#${u.id}</td>
                <td><strong>${escapeHtml(u.username)}</strong></td>
                <td>${escapeHtml(u.full_name)}</td>
                <td style="color:#64748B;">${escapeHtml(u.email)}</td>
                <td><span class="role-pill ${roleClass}">${roleLabel}</span></td>
                <td><span class="status-pill ${statusClass}">● ${statusLabel}</span></td>
                <td style="font-size:12px; color:#64748B;">${escapeHtml(lastLoginStr)}</td>
                <td style="text-align: right;">
                    <div class="admin-action-btn-group" style="justify-content: flex-end;">
                        <button type="button" class="btn-action-sm" onclick="openAdminEditUser(${u.id}, '${escapeHtml(u.username)}', '${escapeHtml(u.full_name)}', '${escapeHtml(u.email)}', '${roleClean}', ${u.is_active})">✏️ Edit</button>
                        <button type="button" class="btn-action-sm" onclick="openAdminResetPwd(${u.id}, '${escapeHtml(u.username)}')">🔑 Reset</button>
                        <button type="button" class="btn-action-sm" onclick="adminToggleUserStatus(${u.id}, ${u.is_active}, '${escapeHtml(u.username)}', '${roleClean}')">${u.is_active ? 'Deactivate' : 'Activate'}</button>
                        <button type="button" class="btn-action-sm danger" onclick="adminDeleteUser(${u.id}, '${escapeHtml(u.username)}', '${roleClean}')">🗑️ Delete</button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

window.openAdminEditUser = function(id, username, full_name, email, role, is_active) {
    document.getElementById('admin-edit-user-id').value = id;
    document.getElementById('admin-edit-username').value = username;
    document.getElementById('admin-edit-fullname').value = full_name;
    document.getElementById('admin-edit-email').value = email;
    document.getElementById('admin-edit-role').value = role;
    document.getElementById('admin-edit-active').checked = is_active;
    const errBanner = document.getElementById('admin-edit-user-error');
    if (errBanner) errBanner.classList.add('hidden');
    openModal('admin-edit-user-modal');
};

window.openAdminResetPwd = function(id, username) {
    document.getElementById('admin-reset-user-id').value = id;
    document.getElementById('admin-reset-username-display').textContent = username;
    document.getElementById('admin-reset-new-password').value = '';
    const errBanner = document.getElementById('admin-reset-pwd-error');
    if (errBanner) errBanner.classList.add('hidden');
    openModal('admin-reset-pwd-modal');
};

window.adminToggleUserStatus = async function(userId, currentActive, username, role) {
    if (role === 'admin' && currentActive) {
        if (!confirm(`Warning: Are you sure you want to deactivate Administrator account '${username}'?`)) {
            return;
        }
    }

    const res = await apiFetch(`/admin/users/${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !currentActive })
    });

    if (!res.ok) {
        showToast(res.error || 'Failed to update user account status', false);
        return;
    }

    const newState = !currentActive ? 'activated' : 'deactivated';
    showToast(`User account '${username}' ${newState} successfully.`);
    loadAdminUsers();
    loadAdminPanel();
};

window.adminDeleteUser = async function(userId, username, role) {
    if (role === 'admin') {
        if (!confirm(`Warning: You are about to delete Administrator account '${username}'. Continue?`)) {
            return;
        }
    } else {
        if (!confirm(`Are you sure you want to delete user account '${username}'?`)) {
            return;
        }
    }

    const res = await apiFetch(`/admin/users/${userId}`, {
        method: 'DELETE'
    });

    if (!res.ok) {
        showToast(res.error || 'Failed to delete user account', false);
        return;
    }

    if (res.data && res.data.status === 'deactivated') {
        showToast(res.data.message || `User '${username}' deactivated to protect historical records.`);
    } else {
        showToast(`User account '${username}' deleted successfully.`);
    }

    loadAdminUsers();
    loadAdminPanel();
};

async function runAdminDiagnostics() {
    const listEl = document.getElementById('admin-diagnostics-results-list');
    if (!listEl) return;

    listEl.innerHTML = `<div class="text-muted" style="padding: 24px; text-align: center;">⚡ Probing all system components in real-time...</div>`;

    const res = await apiFetch('/admin/diagnostics');
    if (!res.ok) {
        listEl.innerHTML = `<div class="error-banner">Diagnostic Probe Error: ${escapeHtml(res.error || 'Unable to probe backend')}</div>`;
        return;
    }

    const d = res.data;
    const checks = d.checks || [];

    listEl.innerHTML = `
        <div style="margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between;">
            <span style="font-weight: 700; font-size: 13.5px; color: ${d.status === 'healthy' ? '#166534' : '#991B1B'};">
                Overall System Status: ${d.status === 'healthy' ? '✓ HEALTHY (ALL SUBSYSTEMS OPERATIONAL)' : '⚠️ WARNING'}
            </span>
            <span style="font-size: 12px; color: #64748B;">Probed at: ${new Date(d.timestamp).toLocaleTimeString()}</span>
        </div>
        ${checks.map(c => {
            const isPass = c.status === 'PASS';
            const badgeClass = isPass ? 'diag-badge-pass' : 'diag-badge-fail';
            return `
                <div class="diag-row-item">
                    <div>
                        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                            <strong style="color: #153B66; font-size: 13.5px;">${escapeHtml(c.component)}</strong>
                            <span class="${badgeClass}">${c.status}</span>
                        </div>
                        <div style="font-size: 12px; color: ${isPass ? '#1E293B' : '#DC2626'};">
                            ${escapeHtml(c.detail)}
                        </div>
                    </div>
                    <div style="font-size: 12px; font-weight: 600; color: #64748B;">
                        ${c.latency_ms} ms
                    </div>
                </div>
            `;
        }).join('')}
    `;

    showToast('Admin diagnostics completed successfully.');
}

async function loadAdminAuditLogs() {
    const searchVal = document.getElementById('admin-audit-search')?.value.trim();
    const actionVal = document.getElementById('admin-audit-action-filter')?.value;

    const params = new URLSearchParams();
    params.append('limit', '50');
    if (actionVal) params.append('action', actionVal);

    const res = await apiFetch(`/admin/audit?${params.toString()}`);
    const tableBody = document.getElementById('admin-audit-table-body');
    if (!tableBody) return;

    if (!res.ok) {
        tableBody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">${escapeHtml(res.error || 'Failed to load audit history')}</td></tr>`;
        return;
    }

    let logs = res.data || [];
    if (searchVal) {
        const lowerSearch = searchVal.toLowerCase();
        logs = logs.filter(l =>
            (l.reason && l.reason.toLowerCase().includes(lowerSearch)) ||
            (l.details && l.details.toLowerCase().includes(lowerSearch)) ||
            (l.entity_name && l.entity_name.toLowerCase().includes(lowerSearch))
        );
    }

    if (logs.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No audit log records found matching current query.</td></tr>`;
        return;
    }

    tableBody.innerHTML = logs.map(l => {
        const timeStr = l.timestamp ? new Date(l.timestamp).toLocaleString() : '—';
        return `
            <tr>
                <td style="font-size:12px; color:#64748B;">${escapeHtml(timeStr)}</td>
                <td><span class="role-pill" style="background:#EFF6FF; color:#1D4ED8;">${escapeHtml(l.action)}</span></td>
                <td><strong>${escapeHtml(l.entity_name || 'System')}</strong></td>
                <td>User #${l.user_id || 'System'}</td>
                <td style="font-size:12px; color:#334155;">${escapeHtml(l.reason || '—')}</td>
                <td style="font-size:11.5px; font-family:var(--font-mono); color:#64748B; max-width:300px; word-break:break-all;">
                    ${escapeHtml(l.details || '—')}
                </td>
            </tr>
        `;
    }).join('');
}


// =========================================================================
// PART 2: EDIT EXISTING ORDER & SHIPMENT DATE REVISION (Requirements 11 - 20)
// =========================================================================
let currentEditingOrder = null;

window.openEditOrderModal = async function(orderId) {
    if (!orderId) {
        showToast('Please select a valid order to edit.', false);
        return;
    }

    try {
        const res = await apiFetch(`/orders/${orderId}`);
        if (!res.ok) {
            showToast('Unable to load order details: ' + res.error, false);
            return;
        }

        const o = res.data;
        currentEditingOrder = o;

        document.getElementById('edit-order-id').value = o.id;
        document.getElementById('edit-order-orig-delivery').value = o.current_delivery_date || o.original_delivery_date || '';
        document.getElementById('edit-order-buyer').value = o.buyer_name || 'N/A';
        document.getElementById('edit-order-code').value = o.order_code;
        document.getElementById('edit-order-ref').value = o.customer_ref || '';
        document.getElementById('edit-order-po').value = o.po_number || '';
        document.getElementById('edit-order-style').value = o.style_model || '';
        document.getElementById('edit-order-qty').value = o.total_quantity;

        const producedHint = document.getElementById('edit-order-produced-hint');
        if (producedHint) {
            const comp = Number(o.completed_pairs || 0).toLocaleString();
            const bal = Number(o.outstanding_pairs || o.total_quantity).toLocaleString();
            producedHint.textContent = `Completed production: ${comp} pairs • Remaining balance: ${bal} pairs.`;
        }

        document.getElementById('edit-order-start').value = o.production_start_date || '';
        document.getElementById('edit-order-orig-date-display').value = o.original_delivery_date || 'N/A';
        document.getElementById('edit-order-current-date-display').value = o.current_delivery_date || 'N/A';
        document.getElementById('edit-order-new-delivery').value = o.current_delivery_date || '';
        document.getElementById('edit-order-priority').value = o.priority || 'MEDIUM';
        document.getElementById('edit-order-status').value = o.status || 'SCHEDULED';
        document.getElementById('edit-order-notes').value = o.notes || '';
        document.getElementById('edit-order-change-reason').value = '';

        const noticeEl = document.getElementById('edit-order-date-change-notice');
        if (noticeEl) noticeEl.style.display = 'none';

        const errEl = document.getElementById('edit-order-error');
        if (errEl) errEl.classList.add('hidden');

        openModal('edit-order-modal');
    } catch (e) {
        console.error('Error opening edit order modal', e);
        showToast('Error: ' + e.message, false);
    }
};

function initEditOrderForm() {
    const newDeliveryInput = document.getElementById('edit-order-new-delivery');
    if (newDeliveryInput) {
        const checkDateDiff = () => {
            const origDate = document.getElementById('edit-order-orig-delivery').value;
            const newDate = newDeliveryInput.value;
            const noticeEl = document.getElementById('edit-order-date-change-notice');
            if (noticeEl) {
                noticeEl.style.display = (newDate && origDate && newDate !== origDate) ? 'block' : 'none';
            }
        };
        newDeliveryInput.addEventListener('input', checkDateDiff);
        newDeliveryInput.addEventListener('change', checkDateDiff);
    }

    const editForm = document.getElementById('edit-order-form');
    if (editForm) {
        editForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const orderId = document.getElementById('edit-order-id').value;
            const origDate = document.getElementById('edit-order-orig-delivery').value;
            const newDate = document.getElementById('edit-order-new-delivery').value;
            const reason = document.getElementById('edit-order-change-reason').value.trim();

            if (newDate && origDate && newDate !== origDate) {
                // Show Confirmation Summary Dialog before saving shipment date change (Requirement 14)
                document.getElementById('confirm-rev-order-code').textContent = currentEditingOrder?.order_code || `Order #${orderId}`;
                document.getElementById('confirm-rev-order-name').textContent = currentEditingOrder?.customer_ref || '';
                document.getElementById('confirm-rev-prev-date').textContent = origDate;
                document.getElementById('confirm-rev-new-date').textContent = newDate;
                document.getElementById('confirm-rev-reason').textContent = reason || 'Shipment deadline extension / replanning';
                openModal('confirm-delivery-revision-modal');
                return;
            }

            // No delivery date change -> save directly
            await executeSaveOrder(orderId, false);
        });
    }

    const btnConfirmDate = document.getElementById('btn-confirm-date-change');
    if (btnConfirmDate) {
        btnConfirmDate.addEventListener('click', async () => {
            closeModal('confirm-delivery-revision-modal');
            const orderId = document.getElementById('edit-order-id').value;
            await executeSaveOrder(orderId, true);
        });
    }
}

async function executeSaveOrder(orderId, isDateRevised) {
    const errEl = document.getElementById('edit-order-error');
    if (errEl) errEl.classList.add('hidden');

    const customerRef = document.getElementById('edit-order-ref').value.trim();
    const poNumber = document.getElementById('edit-order-po').value.trim() || null;
    const styleModel = document.getElementById('edit-order-style').value.trim();
    const totalQty = parseFloat(document.getElementById('edit-order-qty').value);
    const startDate = document.getElementById('edit-order-start').value;
    const newDelivery = document.getElementById('edit-order-new-delivery').value;
    const priority = document.getElementById('edit-order-priority').value;
    const statusVal = document.getElementById('edit-order-status').value;
    const notes = document.getElementById('edit-order-notes').value.trim();
    const reason = document.getElementById('edit-order-change-reason').value.trim() || 
                   (isDateRevised ? 'Shipment date revised' : 'Order information update');

    const payload = {
        customer_ref: customerRef,
        po_number: poNumber,
        style_model: styleModel,
        total_quantity: totalQty,
        production_start_date: startDate,
        current_delivery_date: newDelivery,
        priority: priority,
        status: statusVal,
        notes: notes,
        reason: reason,
        confirm_workflow_change: true
    };

    const res = await apiFetch(`/orders/${orderId}`, {
        method: 'PUT',
        body: JSON.stringify(payload)
    });

    if (!res.ok) {
        if (errEl) {
            errEl.textContent = 'Failed to save order: ' + res.error;
            errEl.classList.remove('hidden');
        } else {
            showToast('Error saving order: ' + res.error, false);
        }
        return;
    }

    closeModal('edit-order-modal');
    showToast(isDateRevised
        ? 'Shipment date revised! Remaining working days and future targets recalculated.'
        : 'Order updated successfully.');

    // 1. Refresh active Order Details modal if currently viewed
    if (typeof currentOrderDetails !== 'undefined' && currentOrderDetails && String(currentOrderDetails.id) === String(orderId)) {
        openOrderDetails(orderId);
    }

    // 2. Refresh Orders table & Dashboard
    loadOrders();
    loadDashboard();

    // 3. Reload order selector dropdowns
    allMatrixOrders = []; // force selector repopulation on next sheet load

    // 4. If current matrix planning sheet is showing this order, refresh its plan
    const curMatrixId = document.getElementById('matrix-filter-order')?.value;
    if (curMatrixId && String(curMatrixId) === String(orderId)) {
        loadMatrixPlanningSheet(orderId);
    }

    // 5. If current WIP flow sheet is showing this order, refresh its plan
    const curWipId = document.getElementById('wip-filter-order')?.value;
    if (curWipId && String(curWipId) === String(orderId)) {
        loadWipFlowSheet(orderId);
    }
}


// =========================================================================
// PART 3: ORDER DELETE / ARCHIVE & PRODUCTION ENTRY DELETE (Requirements 11-23)
// =========================================================================

// Global modal handlers
window.openDeleteOrderModal = async function(orderId) {
    if (!orderId) {
        showToast('Please select a valid order.', false);
        return;
    }

    try {
        const res = await apiFetch(`/orders/${orderId}/dependency-check`);
        if (!res.ok) {
            showToast('Unable to check order dependencies: ' + res.error, false);
            return;
        }

        const data = res.data;
        document.getElementById('order-delete-target-id').value = data.order_id;
        document.getElementById('order-del-code').textContent = data.order_code;
        document.getElementById('order-del-buyer').textContent = data.buyer_name || '-';
        document.getElementById('order-del-ref').textContent = data.customer_ref || '-';
        document.getElementById('order-del-qty').textContent = Number(data.total_quantity || 0).toLocaleString();
        document.getElementById('order-del-entries-count').textContent = data.production_entries_count;
        document.getElementById('order-del-wip-count').textContent = data.wip_adjustments_count;
        document.getElementById('order-del-reason').value = '';

        const diagEl = document.getElementById('order-del-diagnosis');
        const btnDelete = document.getElementById('btn-confirm-delete-order');
        const btnArchive = document.getElementById('btn-confirm-archive-order');

        if (data.can_permanently_delete) {
            diagEl.style.background = '#eff6ff';
            diagEl.style.border = '1px solid #bfdbfe';
            diagEl.style.color = '#1e40af';
            diagEl.innerHTML = `✅ <strong>Eligible for Permanent Deletion:</strong> This order has 0 production entries and 0 WIP records. It can be safely and permanently deleted from the database without breaking manufacturing history.`;
            btnDelete.style.display = 'inline-block';
            btnArchive.style.display = 'inline-block';
            btnArchive.textContent = '📦 Archive Instead';
        } else {
            diagEl.style.background = '#fffbeb';
            diagEl.style.border = '1px solid #fde68a';
            diagEl.style.color = '#92400e';
            diagEl.innerHTML = `⚠️ <strong>Protected Historical Records:</strong> This order contains <strong>${data.production_entries_count} production entries</strong> and <strong>${data.wip_adjustments_count} WIP records</strong>.<br>To protect manufacturing audit integrity, <strong>Archive/Cancel</strong> this order. Archiving safely excludes it from active planning sheets, default selectors, and active counts while preserving history.`;
            btnDelete.style.display = 'none';
            btnArchive.style.display = 'inline-block';
            btnArchive.textContent = '📦 Confirm Archive / Cancel';
        }

        openModal('order-delete-modal');
    } catch (e) {
        console.error('Error in openDeleteOrderModal', e);
        showToast('Error: ' + e.message, false);
    }
};

window.executeDeleteOrder = async function() {
    const orderId = document.getElementById('order-delete-target-id').value;
    if (!orderId) return;

    const btnDelete = document.getElementById('btn-confirm-delete-order');
    btnDelete.disabled = true;
    btnDelete.textContent = 'Deleting...';

    try {
        const res = await apiFetch(`/orders/${orderId}`, {
            method: 'DELETE'
        });

        if (!res.ok) {
            showToast('Delete failed: ' + res.error, false);
            btnDelete.disabled = false;
            btnDelete.textContent = '🗑️ Confirm Permanent Delete';
            return;
        }

        closeModal('order-delete-modal');
        closeModal('order-detail-modal');
        showToast('Order permanently deleted successfully.');

        // Refresh UI
        loadOrders();
        loadDashboard();
        // Reload order selectors (they will repopulate on next load)
        allMatrixOrders = [];

        // Clear planning sheet selects if this deleted order was displayed
        const curMatrixId = document.getElementById('matrix-filter-order')?.value;
        if (curMatrixId && String(curMatrixId) === String(orderId)) {
            const matSel = document.getElementById('matrix-filter-order');
            if (matSel) matSel.value = '';
            loadMatrixPlanningSheet('');
        }
        const curWipId = document.getElementById('wip-filter-order')?.value;
        if (curWipId && String(curWipId) === String(orderId)) {
            const wipSel = document.getElementById('wip-filter-order');
            if (wipSel) wipSel.value = '';
            loadWipFlowSheet('');
        }
    } catch (e) {
        showToast('Exception: ' + e.message, false);
    } finally {
        btnDelete.disabled = false;
        btnDelete.textContent = '🗑️ Confirm Permanent Delete';
    }
};

window.executeArchiveOrder = async function() {
    const orderId = document.getElementById('order-delete-target-id').value;
    if (!orderId) return;

    const reason = document.getElementById('order-del-reason').value.trim() || 'Archived from Order Management';
    const btnArchive = document.getElementById('btn-confirm-archive-order');
    btnArchive.disabled = true;
    btnArchive.textContent = 'Archiving...';

    try {
        const res = await apiFetch(`/orders/${orderId}/archive`, {
            method: 'POST',
            body: JSON.stringify({ reason })
        });

        if (!res.ok) {
            showToast('Archive failed: ' + res.error, false);
            btnArchive.disabled = false;
            btnArchive.textContent = '📦 Confirm Archive / Cancel';
            return;
        }

        closeModal('order-delete-modal');
        closeModal('order-detail-modal');
        showToast('Order successfully archived. Excluded from active planning sheets and default selectors.');

        // Refresh UI
        loadOrders();
        loadDashboard();
        // Reload order selectors
        allMatrixOrders = [];

        // Clear planning sheet selects if this archived order was displayed
        const curMatrixId = document.getElementById('matrix-filter-order')?.value;
        if (curMatrixId && String(curMatrixId) === String(orderId)) {
            const matSel = document.getElementById('matrix-filter-order');
            if (matSel) matSel.value = '';
            loadMatrixPlanningSheet('');
        }
        const curWipId = document.getElementById('wip-filter-order')?.value;
        if (curWipId && String(curWipId) === String(orderId)) {
            const wipSel = document.getElementById('wip-filter-order');
            if (wipSel) wipSel.value = '';
            loadWipFlowSheet('');
        }
    } catch (e) {
        showToast('Exception: ' + e.message, false);
    } finally {
        btnArchive.disabled = false;
        btnArchive.textContent = '📦 Confirm Archive / Cancel';
    }
};

window.restoreOrder = async function(orderId) {
    if (!orderId) return;
    if (!confirm('Are you sure you want to restore this order to active planning?')) return;

    try {
        const res = await apiFetch(`/orders/${orderId}/restore`, {
            method: 'POST',
            body: JSON.stringify({ reason: 'Restored to active planning by user' })
        });

        if (!res.ok) {
            showToast('Failed to restore order: ' + res.error, false);
            return;
        }

        showToast('Order successfully restored to active planning.');
        loadOrders();
        loadDashboard();
        allMatrixOrders = []; // force selector repopulation on next load
    } catch (e) {
        showToast('Exception: ' + e.message, false);
    }
};

window.openCancelEntryModal = async function(entryId) {
    if (!entryId) return;

    try {
        const res = await apiFetch(`/production/entries/${entryId}`);
        if (!res.ok) {
            showToast('Unable to load entry details: ' + res.error, false);
            return;
        }

        const e = res.data;
        document.getElementById('entry-cancel-target-id').value = e.id;
        document.getElementById('entry-cancel-id').textContent = '#' + e.id;
        document.getElementById('entry-cancel-date').textContent = e.entry_date || '-';
        document.getElementById('entry-cancel-order').textContent = e.order_code || `Order #${e.order_id}`;
        document.getElementById('entry-cancel-section').textContent = e.section_name || '-';
        document.getElementById('entry-cancel-operation').textContent = e.operation_name || '-';
        document.getElementById('entry-cancel-qty').textContent = `${Number(e.accepted_quantity).toLocaleString()} pairs`;
        document.getElementById('entry-cancel-user').textContent = e.entered_by_name || `User #${e.entered_by_id}`;
        document.getElementById('entry-cancel-reason').value = '';

        openModal('entry-cancel-modal');
    } catch (err) {
        console.error('Error opening cancel entry modal', err);
        showToast('Error: ' + err.message, false);
    }
};

window.executeCancelEntry = async function() {
    const entryId = document.getElementById('entry-cancel-target-id').value;
    const reason = document.getElementById('entry-cancel-reason').value.trim();

    if (!entryId) return;
    if (!reason) {
        alert('Please enter a cancellation reason.');
        return;
    }

    const btn = document.getElementById('btn-confirm-cancel-entry');
    btn.disabled = true;
    btn.textContent = 'Cancelling...';

    try {
        const res = await apiFetch(`/production/entries/${entryId}/cancel`, {
            method: 'POST',
            body: JSON.stringify({ reason })
        });

        if (!res.ok) {
            showToast('Failed to cancel entry: ' + res.error, false);
            btn.disabled = false;
            btn.textContent = 'Confirm Cancel / Void';
            return;
        }

        closeModal('entry-cancel-modal');

        const data = res.data;
        if (data && data.downstream_conflicts && data.downstream_conflicts.length > 0) {
            alert(`⚠️ Production entry cancelled, but downstream WIP integrity conflict detected!\n\n` +
                data.downstream_conflicts.join('\n') +
                `\n\nPlease review downstream processes and record an authorized reconciliation.`);
        } else {
            showToast('Production entry cancelled and voided. Totals and WIP recalculated successfully.');
        }

        // Refresh all affected tables and plans
        loadRecentProductionEntries();
        loadDashboard();
        loadOrders();

        const curMatrixId = document.getElementById('matrix-filter-order')?.value;
        if (curMatrixId) {
            loadMatrixPlanningSheet(curMatrixId);
        }

        const curWipId = document.getElementById('wip-filter-order')?.value;
        if (curWipId) {
            loadWipFlowSheet(curWipId);
        }

        if (currentOrderDetails) {
            openOrderDetails(currentOrderDetails.id);
        }
    } catch (err) {
        showToast('Exception: ' + err.message, false);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Confirm Cancel / Void';
    }
};

function initOrderDeleteAndCancelModals() {
    const btnDel = document.getElementById('btn-confirm-delete-order');
    if (btnDel) {
        btnDel.addEventListener('click', executeDeleteOrder);
    }

    const btnArch = document.getElementById('btn-confirm-archive-order');
    if (btnArch) {
        btnArch.addEventListener('click', executeArchiveOrder);
    }

    const btnCancelEntry = document.getElementById('btn-confirm-cancel-entry');
    if (btnCancelEntry) {
        btnCancelEntry.addEventListener('click', executeCancelEntry);
    }
}
